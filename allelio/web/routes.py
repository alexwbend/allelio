"""API routes for Allelio web interface."""

import asyncio
import json
import os
import tempfile
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Dict, Any, Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from starlette.background import BackgroundTask

from allelio import __version__
from allelio.parsers import parse_genotype_file
from allelio.database.store import AllelioDB
from allelio.analysis.lookup import analyze_variants
from allelio.ai.attribution import Explanation, attribution
from allelio.ai.engine import AIEngine, REFUSED, UNREACHABLE
from allelio.ai.safety import get_variant_warnings
from allelio.web.app import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def read_root(request: Request) -> str:
    """Serve the main HTML page."""
    try:
        return templates.TemplateResponse(request, "index.html")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load index page: {str(e)}")


@router.get("/api/status")
async def get_status() -> Dict[str, Any]:
    """System status: which model is answering, and whether the database is built."""
    # Named, not just "connected": with a model server configurable by
    # environment, "AI ready" on its own does not tell anyone which model wrote
    # the explanations they are about to read, or where it is running.
    ai: Dict[str, Any] = {
        "available": False,
        "model_available": False,
        # The five-way answer the pill switches on. Present even when there is
        # no engine to ask, because a key that appears only sometimes is a key
        # the page has to guess about.
        "status": UNREACHABLE,
        "provider": None,
        "model": None,
        "host": None,
        "error": None,
    }
    try:
        ai_engine = AIEngine()
    except ValueError as exc:
        # A model server that is not on this machine, refused rather than used.
        # Say that on the page; "disconnected" would send them looking for a
        # crash that never happened.
        ai["error"] = str(exc)
        ai_engine = None
    except Exception:
        ai_engine = None

    if ai_engine is not None:
        await ai_engine.check_connection()
        ai["available"] = ai_engine.available
        # "Reachable", "not serving that", "will not say what it serves" and
        # "nothing there" are four different things to put on a status pill, and
        # two booleans cannot carry four.
        ai["status"] = ai_engine.status
        # A server that answered with a model this tool will not use is not a
        # server that is down, and the page should not say it is.
        ai["error"] = ai_engine.refusal
        # Reachable is not the same as loaded: a server answering with a dozen
        # models it will happily list, none of them the one configured, would
        # otherwise show green beside a name that explains nothing.
        ai["model_available"] = ai_engine.check_model_available()
        ai["provider"] = ai_engine.provider
        # Read after check_connection, which is where a server holding a single
        # model gets to name it.
        ai["model"] = ai_engine.model
        ai["host"] = ai_engine.host

    # Get database stats
    db_ready = False
    db_stats = {
        "clinvar_entries": 0,
        "gwas_entries": 0,
        "last_update": None,
    }

    try:
        db = AllelioDB()
        db_ready = db.is_initialized()
        if db_ready:
            stats = db.get_stats()
            db_stats = {
                "clinvar_entries": stats.get("clinvar_entries", 0),
                "gwas_entries": stats.get("gwas_entries", 0),
                "last_update": stats.get("last_update"),
            }
    except Exception:
        pass

    return {
        "ai": ai,
        "db_ready": db_ready,
        "db_stats": db_stats,
        "version": __version__,
    }


def _text_of(explanation) -> str:
    """The card's text. Nothing was written for it below the top 50."""
    return explanation.text if explanation is not None else ""


def _model_of(explanation) -> Optional[str]:
    """Who wrote the card, or None — including "nobody asked" below the top 50."""
    return explanation.model if explanation is not None else None


def _gene_of(variant) -> Optional[str]:
    """Gene symbol for a result, from ClinVar first and GWAS as a fallback."""
    for entry in (variant.clinvar_entries or []):
        if entry.gene:
            return entry.gene
    for entry in (variant.gwas_entries or []):
        if entry.mapped_gene:
            return entry.mapped_gene
    return None


def _significance_of(variant) -> str:
    """Bucket a result into the badges the results list knows how to draw.

    ClinVar has the last word. "Conflicting classifications of pathogenicity"
    is 130,833 rsIDs and "Uncertain significance" is 1,236,063 — both sort high
    enough to reach the report, and neither is a trait or a benign call.
    """
    for entry in (variant.clinvar_entries or []):
        significance = (entry.clinical_significance or "").lower()
        if "conflicting" in significance:
            return "conflicting"
        if "uncertain" in significance:
            return "uncertain"
        if "pathogenic" in significance and "benign" not in significance:
            return "pathogenic"
        if "benign" in significance or "protective" in significance:
            return "benign"
        if "risk" in significance:
            return "risk"
    if variant.gwas_entries:
        # A GWAS row on its own is an association and nothing stronger — 37,108
        # of the 62,057 findings on a real genome. Calling them all a risk
        # over-states every one; calling them all a trait quietly demotes type 2
        # diabetes and coronary artery disease. Say what the row actually is.
        return "association"
    return "trait"


@router.post("/api/analyze")
async def analyze_file(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Analyze uploaded genotype file.
    
    Returns analysis results with AI explanations.
    """
    temp_file_path = None
    try:
        # Settle the model address first. A local model is optional — the README
        # promises the tool still works without one, minus the plain-English
        # explanations — but an address that is not on this machine is a refusal,
        # and it should arrive now rather than half an hour into the analysis.
        # Construction only parses and resolves; nothing is contacted yet, so an
        # empty upload still gets its 400 without waiting on a connect timeout.
        try:
            ai_engine = AIEngine()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        # Validate file
        if not file.filename:
            raise HTTPException(status_code=400, detail="No filename provided")

        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        await ai_engine.check_connection()
        # Refused, not unreachable: the same answer construction gives a remote
        # address, for the same reason. Reporting it as a run with no
        # explanations would hide why there are none.
        if ai_engine.status == REFUSED:
            raise HTTPException(status_code=400, detail=ai_engine.refusal)
        # Nothing to switch off here any more. A listing that contradicts the
        # configured name, a server that is not there, and one that will not
        # enumerate are all answered by engine.will_explain(), which explain
        # and generate_summary ask themselves — so no caller has to reach in and
        # set `available = False` to keep a prompt from going out.

        # The multipart filename is raw header data: "../../../.zshenv" resolves
        # out of the temp directory, and multipart is CORS-safelisted, so any
        # page could have posted here. mkstemp picks the name and the mode —
        # this file is the user's entire genome and the temp directory is shared.
        # Only the .gz suffix matters to the parser.
        suffix = ".gz" if file.filename.endswith(".gz") else ""
        fd, temp_file_path = tempfile.mkstemp(prefix="allelio_upload_", suffix=suffix)
        with os.fdopen(fd, "wb") as f:
            f.write(content)

        _progress.update(stage="Reading your file", done=0, total=0)

        # Parse genotype file
        loop = asyncio.get_event_loop()
        genotypes = await loop.run_in_executor(
            None, parse_genotype_file, temp_file_path
        )
        
        if not genotypes:
            raise HTTPException(
                status_code=400, 
                detail="No valid genotype data found in file"
            )

        # Open database and run analysis
        db = AllelioDB()
        if not db.is_initialized():
            raise HTTPException(
                status_code=503,
                detail="Database is not initialized. Please run 'allelio setup-db' first."
            )

        # Analyze variants
        _progress.update(stage=f"Matching {len(genotypes):,} variants against ClinVar and GWAS")
        analysis_results = await loop.run_in_executor(
            None, analyze_variants, genotypes, db
        )

        if not analysis_results:
            raise HTTPException(
                status_code=400,
                detail="No variants found in database"
            )

        # analyze_variants already returns these most-significant-first, so the
        # top 50 are the 50 worth spending an AI call on.
        top_variants = analysis_results[:50]

        # Generate AI explanations for significant variants. One call per
        # variant, run a few at a time — sequentially this took 12 minutes.
        _progress.update(
            stage="Writing explanations", done=0, total=len(top_variants)
        )

        def on_explained(done: int, total: int) -> None:
            _progress.update(done=done, total=total)

        # rsID -> Explanation. The credit rides on the card from here to the
        # browser; nothing else on this payload decides who wrote what.
        explanations = await ai_engine.explain_variants_batch(
            top_variants, progress_callback=on_explained
        )

        # Generate executive summary
        _progress.update(stage="Summarizing", done=0, total=0)
        try:
            if not ai_engine.will_explain():
                raise RuntimeError("no model server answering")
            summary = await ai_engine.generate_summary(top_variants)
        except Exception:
            summary = ("AI summary unavailable. Variant findings below come "
                       "straight from ClinVar and the GWAS Catalog.")

        # Format results
        _progress.update(stage="Building your report", done=0, total=0)
        formatted_results = []
        for i, variant in enumerate(analysis_results):
            warnings = get_variant_warnings(variant)
            
            result_dict = {
                "rsid": variant.rsid,
                "chromosome": variant.chromosome,
                "position": variant.position,
                "genotype": variant.genotype if hasattr(variant, 'genotype') else None,
                "category": variant.category if hasattr(variant, 'category') else "Unknown",
                "significance_rank": i + 1,
                "explanation": _text_of(explanations.get(variant.rsid)),
                # Null on a card the model did not write. The page reads this
                # and nothing else: a card cannot be credited to a model that
                # did not write it, because the credit is on the card.
                "explained_by": _model_of(explanations.get(variant.rsid)),
                "gene": _gene_of(variant),
                "significance": _significance_of(variant),
                "pubmed_id": next(
                    (e.pubmed_id for e in (variant.gwas_entries or []) if e.pubmed_id),
                    None,
                ),
                "warnings": warnings,
            }
            formatted_results.append(result_dict)

        payload = {
            "summary": summary,
            "results": formatted_results,
            "total_variants": len(analysis_results),
            "analyzed_at": _get_timestamp(),
            # Counted off the cards above, for the saved-analysis report and
            # for anything reading the payload that is not the page. "none" is
            # a run where no card was written by a model.
            "model_used": attribution(explanations).model or "none",
        }
        return payload

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {str(e)}"
        )
    finally:
        # Clean up temp file
        _progress.update(stage="idle", done=0, total=0)
        if temp_file_path and Path(temp_file_path).exists():
            try:
                Path(temp_file_path).unlink()
            except Exception:
                pass


# A whole-genome run takes minutes. Without real numbers the page looks hung,
# so the analyse route publishes its stage here and the browser polls it.
_progress: Dict[str, Any] = {"stage": "idle", "done": 0, "total": 0}


@router.get("/api/progress")
async def get_progress() -> Dict[str, Any]:
    """Where the current analysis has got to."""
    return _progress


@router.post("/api/export")
async def export_report(analysis_data: Dict[str, Any]) -> FileResponse:
    """
    Export analysis results as HTML report.
    
    Takes analysis results and generates downloadable HTML report.
    """
    try:
        if not analysis_data:
            raise HTTPException(status_code=400, detail="No analysis data provided")

        # Generate HTML report (using report generator when available)
        html_content = _generate_html_report(analysis_data)

        # mkstemp gives the file 0600, and the report holds the user's
        # genotypes. Explicit encoding because the report declares UTF-8 and
        # the model writes em dashes.
        fd, temp_report_path = tempfile.mkstemp(
            prefix="allelio_report_", suffix=".html"
        )
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(html_content)

        return FileResponse(
            path=temp_report_path,
            filename=f"allelio_report_{_get_timestamp()}.html",
            media_type="text/html",
            background=BackgroundTask(_unlink, temp_report_path),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Report generation failed: {str(e)}"
        )


def _unlink(path: str) -> None:
    """Delete a file we are done with, where failing to is not worth reporting."""
    try:
        os.unlink(path)
    except OSError:
        pass


# A whole-genome run is half an hour, and the results only live in the tab that
# ran it — a reload throws them away. Saving is opt-in and stays on this
# machine: the file is the user's genome and never leaves it.
SAVED_ANALYSIS_PATH = os.path.expanduser("~/.allelio/last_analysis.json")


# No lock around any of this, and none needed: every writer gets its own mkstemp
# temp file, os.replace is atomic, and the delete treats "already gone" as
# success. Concurrent saves and deletes can only order differently, never tear.
def _write_saved_analysis(analysis_data: Dict[str, Any]) -> None:
    """Write the saved analysis atomically, readable only by its owner."""
    directory = os.path.dirname(SAVED_ANALYSIS_PATH)
    # 0700 only bites when this creates the directory; ~/.allelio usually
    # already exists for the database, and silently tightening a directory
    # this module does not own is not this feature's call to make.
    os.makedirs(directory, mode=0o700, exist_ok=True)

    # Same directory so os.replace stays on one filesystem, and mkstemp so a
    # crash mid-write leaves the previous save intact rather than a half file.
    fd, temp_path = tempfile.mkstemp(prefix=".last_analysis_", dir=directory)
    try:
        # os.fdopen owns the descriptor once it succeeds; if it raises, nothing
        # else is going to close it.
        try:
            handle = os.fdopen(fd, "w", encoding="utf-8")
        except BaseException:
            os.close(fd)
            raise
        with handle as f:
            json.dump(analysis_data, f)
            # os.replace orders this rename against other renames, not against
            # the data blocks. Without the fsync a power cut can land the
            # rename and lose the contents — the truncated file this whole
            # dance exists to prevent.
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, SAVED_ANALYSIS_PATH)
    except BaseException:
        # BaseException on purpose: a KeyboardInterrupt here would otherwise
        # strand 15 MB of genotypes under a dotfile name nothing cleans up.
        _unlink(temp_path)
        raise


def _read_saved_analysis() -> Optional[Dict[str, Any]]:
    """Return the saved analysis, or None if there isn't a usable one."""
    try:
        with open(SAVED_ANALYSIS_PATH, encoding="utf-8") as f:
            analysis_data = json.load(f)
    except (OSError, ValueError):
        # Missing, unreadable, or truncated by a crash mid-write. Any of those
        # means "nothing to restore" — none of them should wedge the page.
        return None
    # A file holding a valid JSON list, string or number parses fine and then
    # fails serialisation on the way out as a 500. It is not a saved analysis.
    return analysis_data if isinstance(analysis_data, dict) else None


@router.get("/api/saved")
async def get_saved_analysis_info() -> Dict[str, Any]:
    """Whether there is a saved analysis worth offering to restore."""
    try:
        saved_at = os.path.getmtime(SAVED_ANALYSIS_PATH)
    except OSError:
        return {"saved": False, "saved_at": None}
    # Reading it to answer costs a parse of 15 MB on every page load, so the
    # banner is offered on the strength of the file existing. /api/saved/data
    # is the one that can still say no; the page handles that.
    return {
        "saved": True,
        "saved_at": datetime.fromtimestamp(saved_at).isoformat(timespec="seconds"),
    }


@router.get("/api/saved/data")
async def get_saved_analysis() -> Dict[str, Any]:
    """The saved analysis itself, for restoring the results view."""
    analysis_data = await asyncio.to_thread(_read_saved_analysis)
    if analysis_data is None:
        raise HTTPException(status_code=404, detail="No saved analysis")
    return analysis_data


@router.post("/api/saved")
async def save_analysis(analysis_data: Dict[str, Any]) -> Dict[str, Any]:
    """Save the current analysis to this machine, at the user's request."""
    if not analysis_data:
        raise HTTPException(status_code=400, detail="No analysis data provided")

    try:
        # A whole genome is 15 MB of JSON and encoding it takes a quarter of a
        # second, which on the event loop is a quarter of a second nothing else
        # is served. FastAPI has already spent its own on decoding the body;
        # this is the half we get to move off.
        await asyncio.to_thread(_write_saved_analysis, analysis_data)
    except (OSError, TypeError, ValueError):
        # The path is under the user's home directory — saying which home is
        # not the browser's business.
        raise HTTPException(status_code=500, detail="Could not save the analysis")

    return {"saved": True}


def _delete_saved_analysis() -> None:
    """Remove the saved analysis. Absent already is success, not an error."""
    try:
        os.unlink(SAVED_ANALYSIS_PATH)
    except FileNotFoundError:
        pass


@router.delete("/api/saved")
async def delete_saved_analysis() -> Dict[str, Any]:
    """Forget the saved analysis, and only say so if it is really gone."""
    try:
        await asyncio.to_thread(_delete_saved_analysis)
    except OSError:
        # The page says "deleted" on any 200. Reporting success over a genome
        # file still sitting on the disk is the one lie this feature cannot
        # afford.
        raise HTTPException(
            status_code=500, detail="Could not delete the saved analysis"
        )
    return {"saved": False}


def _get_timestamp() -> str:
    """Get current timestamp in ISO format."""
    return datetime.now().isoformat().replace(":", "-").split(".")[0]


def _generate_html_report(analysis_data: Dict[str, Any]) -> str:
    """Generate HTML report from analysis data."""
    summary = escape(str(analysis_data.get("summary") or "No summary available"))
    results = analysis_data.get("results", [])
    total_variants = escape(str(analysis_data.get("total_variants", 0)))
    analyzed_at = escape(str(analysis_data.get("analyzed_at") or "Unknown"))

    # The table below stops at a hundred rows, and this line describes the rows
    # underneath it rather than the run they came from — so it is counted off
    # the same hundred. Counted off all of them, a genome with four hundred
    # significant variants reads "340 of 512" over a table holding a hundred.
    rows = results[:100]

    # Counted off the cards in the payload, by the same rule the analysis used
    # when it wrote them.
    cards = [r for r in rows if isinstance(r, dict)]
    if any("explained_by" in r for r in cards):
        credit = attribution({
            # Keyed by position: two rows with one rsID would otherwise count
            # as one.
            i: Explanation(str(r.get("explanation") or ""), r.get("explained_by"))
            for i, r in enumerate(cards)
        })
        model_used = (
            f"{escape(str(credit.model))} "
            f"({credit.written} of {credit.total} explanations)"
            if credit.model
            else "none"
        )
    elif analysis_data.get("model_used"):
        # Saved before the cards carried their own credit: one name for the
        # whole run is all there is, and it is reported as that.
        model_used = escape(str(analysis_data["model_used"])) + " (whole run)"
    else:
        # Saved before even that. Not "no model" — nobody wrote it down.
        model_used = "not recorded"

    # Build results table HTML
    results_html = ""
    for result in rows:
        # These come from the uploaded file and the model, and the report is
        # opened in a browser — none of it is trusted markup.
        def field(name):
            return escape(str(result.get(name) or "N/A"))

        rsid = field("rsid")
        chrom = field("chromosome")
        pos = field("position")
        genotype = field("genotype")
        category = field("category")
        explanation = field("explanation")

        # The safety layer computes these for BRCA1/2, TP53, Lynch and APOE.
        # A report that omits them is the one place they matter most.
        # explain folds these into the explanation via
        # wrap_with_disclaimer — but only on the path where the model answered.
        # A fallback explanation carries no warning, so test the text itself.
        explanation_text = str(result.get("explanation") or "")
        warnings = "".join(
            f'<p class="warning">{escape(str(w))}</p>'
            for w in (result.get("warnings") or [])
            if str(w) not in explanation_text
        )

        results_html += f"""
        <tr>
            <td>{rsid}</td>
            <td>{chrom}</td>
            <td>{pos}</td>
            <td>{genotype}</td>
            <td>{category}</td>
            <td>{explanation}{warnings}</td>
        </tr>
        """

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Allelio Analysis Report</title>
        <style>
            td {{
                white-space: pre-wrap;
            }}
            .warning {{
                margin: 0.5em 0 0;
                padding: 0.5em;
                border-left: 3px solid #B45309;
                background: #FEF3C7;
                color: #78350F;
            }}
            body {{
                font-family: Arial, sans-serif;
                margin: 20px;
                color: #333;
            }}
            h1 {{
                color: #2c3e50;
            }}
            .summary {{
                background-color: #ecf0f1;
                padding: 15px;
                border-radius: 5px;
                margin: 20px 0;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin: 20px 0;
            }}
            th {{
                background-color: #34495e;
                color: white;
                padding: 10px;
                text-align: left;
            }}
            td {{
                padding: 10px;
                border-bottom: 1px solid #ddd;
            }}
            tr:hover {{
                background-color: #f5f5f5;
            }}
            .metadata {{
                font-size: 0.9em;
                color: #666;
                margin: 10px 0;
            }}
        </style>
    </head>
    <body>
        <h1>Allelio Genomic Analysis Report</h1>
        <div class="metadata">
            <p><strong>Analysis Date:</strong> {analyzed_at}</p>
            <p><strong>Total Variants Analyzed:</strong> {total_variants}</p>
            <p><strong>AI Model:</strong> {model_used}</p>
        </div>
        
        <h2>Executive Summary</h2>
        <div class="summary">
            {summary}
        </div>
        
        <h2>Detailed Results</h2>
        <table>
            <thead>
                <tr>
                    <th>SNP ID</th>
                    <th>Chromosome</th>
                    <th>Position</th>
                    <th>Genotype</th>
                    <th>Category</th>
                    <th>Explanation</th>
                </tr>
            </thead>
            <tbody>
                {results_html}
            </tbody>
        </table>
        
        <p><em>Report generated by Allelio - Privacy-first local genomics analysis</em></p>
    </body>
    </html>
    """

    return html
