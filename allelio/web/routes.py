"""API routes for Allelio web interface."""

import asyncio
import os
import tempfile
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
from allelio.ai.engine import AIEngine
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
    """Get system status including ollama availability and database info."""
    try:
        # Check ollama availability
        ai_engine = AIEngine()
        ollama_available = await ai_engine.check_connection()
    except Exception:
        ollama_available = False

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
        "ollama_available": ollama_available,
        "db_ready": db_ready,
        "db_stats": db_stats,
        "version": __version__,
    }


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
        # A GWAS row on its own is an association, not a risk — 37,108 of the
        # 62,057 findings on a real genome. The analyser has already read the
        # trait text and decided which of them are risk factors.
        return "risk" if variant.category == "Risk Factors" else "trait"
    return "trait"


@router.post("/api/analyze")
async def analyze_file(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Analyze uploaded genotype file.
    
    Returns analysis results with AI explanations.
    """
    temp_file_path = None
    try:
        # Validate file
        if not file.filename:
            raise HTTPException(status_code=400, detail="No filename provided")

        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

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

        # Create AI engine. Ollama is optional — the README promises the tool
        # still works without it, minus the plain-English explanations.
        ai_engine = AIEngine()
        ai_available = await ai_engine.check_connection()

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

        explanations = await ai_engine.explain_variants_batch(
            top_variants, progress_callback=on_explained
        )

        # Generate executive summary
        _progress.update(stage="Summarizing", done=0, total=0)
        try:
            if not ai_available:
                raise RuntimeError("ollama unavailable")
            summary = await ai_engine.generate_summary(top_variants)
        except Exception:
            summary = ("AI summary unavailable. Variant findings below come "
                       "straight from ClinVar and the GWAS Catalog.")

        # Format results
        _progress.update(stage="Building your report")
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
                "explanation": explanations.get(variant.rsid, ""),
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
    """Remove the exported report once it has been sent."""
    try:
        os.unlink(path)
    except OSError:
        pass


def _get_timestamp() -> str:
    """Get current timestamp in ISO format."""
    from datetime import datetime
    return datetime.now().isoformat().replace(":", "-").split(".")[0]


def _generate_html_report(analysis_data: Dict[str, Any]) -> str:
    """Generate HTML report from analysis data."""
    summary = escape(str(analysis_data.get("summary") or "No summary available"))
    results = analysis_data.get("results", [])
    total_variants = escape(str(analysis_data.get("total_variants", 0)))
    analyzed_at = escape(str(analysis_data.get("analyzed_at") or "Unknown"))

    # Build results table HTML
    results_html = ""
    for result in results[:100]:  # Limit to first 100 for report
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
        # explain_variant runs these through wrap_with_disclaimer, so for the
        # variants that got an explanation they are already in it.
        warnings = "" if result.get("explanation") else "".join(
            f'<p class="warning">{escape(str(w))}</p>'
            for w in (result.get("warnings") or [])
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
