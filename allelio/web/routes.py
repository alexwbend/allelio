"""API routes for Allelio web interface."""

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

from allelio import __version__
from allelio.parsers import parse_genotype_file
from allelio.database.store import AllelioDB
from allelio.analysis.lookup import analyze_variants, VariantResult
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
    """Bucket a result into the four badges the results list knows how to draw."""
    for entry in (variant.clinvar_entries or []):
        significance = (entry.clinical_significance or "").lower()
        if "pathogenic" in significance and "benign" not in significance:
            return "pathogenic"
        if "risk" in significance:
            return "risk"
    if variant.gwas_entries:
        return "risk"
    for entry in (variant.clinvar_entries or []):
        if "benign" in (entry.clinical_significance or "").lower():
            return "benign"
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

        # Save uploaded file to temp location
        temp_dir = tempfile.gettempdir()
        temp_file_path = Path(temp_dir) / file.filename
        
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        
        with open(temp_file_path, "wb") as f:
            f.write(content)

        _progress.update(stage="Reading your file", done=0, total=0)

        # Parse genotype file
        loop = asyncio.get_event_loop()
        genotypes = await loop.run_in_executor(
            None, parse_genotype_file, str(temp_file_path)
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

        # Get top 50 significant variants
        sorted_results = sorted(
            analysis_results,
            key=lambda x: x.significance_score if hasattr(x, 'significance_score') else 0,
            reverse=True
        )
        top_variants = sorted_results[:50]

        # Generate AI explanations for significant variants. One call per
        # variant, run a few at a time — sequentially this took 12 minutes.
        explanations = {}
        if ai_available:
            _progress.update(
                stage="Writing explanations", done=0, total=len(top_variants)
            )

            def on_explained(done: int, total: int) -> None:
                _progress.update(done=done, total=total)

            explanations = await ai_engine.explain_variants_batch(
                top_variants, progress_callback=on_explained
            )

        # Generate executive summary
        _progress.update(stage="Summarising", done=0, total=0)
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
        _save_last_analysis(payload)
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


LAST_ANALYSIS_PATH = Path(os.path.expanduser("~/.allelio/last_analysis.json"))

# A whole-genome run takes minutes. Without real numbers the page looks hung,
# so the analyse route publishes its stage here and the browser polls it.
_progress: Dict[str, Any] = {"stage": "idle", "done": 0, "total": 0}


@router.get("/api/progress")
async def get_progress() -> Dict[str, Any]:
    """Where the current analysis has got to."""
    return _progress


def _save_last_analysis(payload: Dict[str, Any]) -> None:
    """Keep the most recent run so a page reload does not mean a re-upload."""
    try:
        LAST_ANALYSIS_PATH.parent.mkdir(parents=True, exist_ok=True)
        LAST_ANALYSIS_PATH.write_text(json.dumps(payload))
    except Exception:
        pass


@router.get("/api/last")
async def get_last_analysis() -> Dict[str, Any]:
    """Return the most recent analysis, or 404 if there has not been one."""
    if not LAST_ANALYSIS_PATH.exists():
        raise HTTPException(status_code=404, detail="No previous analysis")
    return json.loads(LAST_ANALYSIS_PATH.read_text())


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

        # Create temp file for report
        temp_dir = tempfile.gettempdir()
        temp_report_path = Path(temp_dir) / f"allelio_report_{_get_timestamp()}.html"

        with open(temp_report_path, "w") as f:
            f.write(html_content)

        return FileResponse(
            path=str(temp_report_path),
            filename=f"allelio_report_{_get_timestamp()}.html",
            media_type="text/html",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Report generation failed: {str(e)}"
        )


def _get_top_categories(results: List[VariantResult]) -> List[str]:
    """Extract top categories from analysis results."""
    categories = {}
    for result in results:
        category = result.category if hasattr(result, 'category') else "Unknown"
        categories[category] = categories.get(category, 0) + 1
    
    sorted_cats = sorted(categories.items(), key=lambda x: x[1], reverse=True)
    return [cat[0] for cat in sorted_cats[:5]]


def _get_timestamp() -> str:
    """Get current timestamp in ISO format."""
    from datetime import datetime
    return datetime.now().isoformat().replace(":", "-").split(".")[0]


def _generate_html_report(analysis_data: Dict[str, Any]) -> str:
    """Generate HTML report from analysis data."""
    summary = analysis_data.get("summary", "No summary available")
    results = analysis_data.get("results", [])
    total_variants = analysis_data.get("total_variants", 0)
    analyzed_at = analysis_data.get("analyzed_at", "Unknown")

    # Build results table HTML
    results_html = ""
    for result in results[:100]:  # Limit to first 100 for report
        rsid = result.get("rsid", "N/A")
        chrom = result.get("chromosome", "N/A")
        pos = result.get("position", "N/A")
        genotype = result.get("genotype", "N/A")
        category = result.get("category", "N/A")
        explanation = result.get("explanation", "N/A")
        
        results_html += f"""
        <tr>
            <td>{rsid}</td>
            <td>{chrom}</td>
            <td>{pos}</td>
            <td>{genotype}</td>
            <td>{category}</td>
            <td>{explanation}</td>
        </tr>
        """

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Allelio Analysis Report</title>
        <style>
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
