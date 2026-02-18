"""Allelio CLI interface using Click and Rich for user interaction."""

import asyncio
import os
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from allelio.analysis.lookup import analyze_variants
from allelio.database import AllelioDB, setup_database
from allelio.parsers import parse_genotype_file
from allelio.report import generate_html_report

console = Console()


@click.group()
@click.version_option()
def allelio():
    """Allelio - Advanced genomic variant analysis and interpretation tool.
    
    Analyze your genetic variants against ClinVar and GWAS databases,
    with AI-powered explanations and interactive reporting.
    """
    pass


@allelio.command()
def setup():
    """Download and index ClinVar and GWAS databases.
    
    This command initializes the Allelio database by downloading
    variant annotations from ClinVar and GWAS catalogs.
    """
    console.print("\n[bold cyan]Allelio Database Setup[/bold cyan]\n")
    
    try:
        db_path = os.path.expanduser("~/.allelio/data/allelio.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        db = AllelioDB(db_path)

        setup_database(db, log=lambda msg: console.print(f"  {msg}"))

        console.print("\n[bold green]✓[/bold green] Database initialized successfully\n")
    except Exception as e:
        console.print(f"\n[bold red]✗[/bold red] Setup failed: {e}\n", style="red")
        raise click.Abort()


@allelio.command()
@click.argument("file", type=click.Path(exists=True))
@click.option(
    "-o",
    "--output",
    default="./allelio_report.html",
    help="Output HTML report path",
    type=click.Path(),
)
@click.option(
    "--no-ai",
    is_flag=True,
    default=False,
    help="Skip AI explanations",
)
@click.option(
    "--include-benign",
    is_flag=True,
    default=False,
    help="Include benign variants in analysis",
)
@click.option(
    "--model",
    default="llama3.1:8b",
    help="Ollama model name for explanations",
)
@click.option(
    "--top",
    default=20,
    type=int,
    help="Number of top variants to generate AI explanations for (default: 20)",
)
@click.option(
    "--traits-only",
    is_flag=True,
    default=False,
    help="Only show trait associations — exclude health conditions and risk factors",
)
def analyze(
    file: str,
    output: str,
    no_ai: bool,
    include_benign: bool,
    model: str,
    top: int,
    traits_only: bool,
):
    """Analyze a genotype file for significant variants.
    
    FILE: Path to genotype file (VCF, 23andMe, or custom format)
    
    Parses genetic variants, checks against ClinVar and GWAS databases,
    optionally generates AI explanations, and produces an HTML report.
    """
    console.print("\n[bold cyan]Allelio Variant Analysis[/bold cyan]\n")
    
    # Check if database exists
    db = AllelioDB()
    if not db.is_initialized():
        console.print(
            Panel(
                "[bold red]Database not found[/bold red]\n\n"
                "Run [cyan]allelio setup[/cyan] first to download and index databases.",
                title="Database Required",
                border_style="red",
            )
        )
        raise click.Abort()
    
    # Parse genotype file
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Parsing genotype file...", total=None)
            variants = parse_genotype_file(file)
            progress.update(task, description=f"✓ Parsed {len(variants)} variants")
    except Exception as e:
        console.print(f"\n[bold red]✗[/bold red] Failed to parse file: {e}\n", style="red")
        raise click.Abort()
    
    # Run analysis
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Analyzing variants...", total=None)
            results = analyze_variants(
                variants,
                db=db,
                include_benign=include_benign,
            )
            # Filter to traits only if requested
            if traits_only:
                results = [r for r in results if r.category == "Traits"]
            significant = [r for r in results if r.significance_rank <= 4]
            mode_label = "trait associations" if traits_only else "significant variants"
            progress.update(task, description=f"✓ Found {len(results)} {mode_label}")
    except Exception as e:
        console.print(f"\n[bold red]✗[/bold red] Analysis failed: {e}\n", style="red")
        raise click.Abort()
    
    # Generate AI explanations if enabled
    explanations = {}
    if not no_ai:
        # Sort by significance and take top N
        top_variants = sorted(
            results, key=lambda x: x.significance_rank
        )[:top]

        try:
            from allelio.ai.engine import AIEngine

            engine = AIEngine(model=model)
            # Skip model listing — just try to use the model directly
            engine.available = True

            console.print(f"  Generating AI explanations for top {len(top_variants)} variants using {model}...\n")
            for idx, variant in enumerate(top_variants, 1):
                try:
                    explanation = asyncio.run(engine.explain_variant(variant))
                    explanations[variant.rsid] = explanation
                    console.print(f"    [{idx}/{len(top_variants)}] {variant.rsid} ✓")
                except Exception as e:
                    console.print(f"    [{idx}/{len(top_variants)}] {variant.rsid} ✗ ({e})")

            if explanations:
                console.print(f"\n  [bold green]✓[/bold green] Generated {len(explanations)} AI explanations\n")
            else:
                console.print(f"\n  [yellow]⚠[/yellow] No explanations generated. Is Ollama running? (ollama serve)\n")
        except ImportError:
            console.print("  [yellow]⚠[/yellow] AI module not available (pip install ollama)")
            console.print("    Skipping AI explanations.\n")
    
    # Print summary table
    console.print("\n[bold]Analysis Results[/bold]\n")
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("rsID", style="cyan", width=15)
    table.add_column("Gene", style="green", width=15)
    table.add_column("Category", width=15)
    table.add_column("Significance", width=12)
    table.add_column("Genotype", width=12)
    
    for result in sorted(results, key=lambda x: x.significance_rank)[:top]:
        # Extract gene name from clinvar or gwas entries
        gene = "-"
        if result.clinvar_entries:
            gene = result.clinvar_entries[0].gene or "-"
        elif result.gwas_entries:
            gene = result.gwas_entries[0].mapped_gene or "-"

        # Color code by significance
        if result.category == "Health Conditions":
            sig_style = "bold red"
        elif result.category == "Risk Factors":
            sig_style = "bold yellow"
        elif result.category == "Traits":
            sig_style = "bold blue"
        else:
            sig_style = "green"

        table.add_row(
            result.rsid,
            gene,
            result.category,
            f"{result.significance_rank}",
            result.genotype or "-",
            style=sig_style if result.significance_rank <= 4 else "",
        )
    
    console.print(table)
    
    # Generate HTML report
    try:
        if traits_only:
            summary = f"Traits-only analysis of {len(variants):,} variants found {len(results)} trait associations."
        else:
            summary = f"Analysis of {len(variants):,} variants found {len(significant)} significant findings."
        metadata = {
            "generated_at": __import__("datetime").datetime.now().isoformat(),
            "db_version": db.version(),
            "model_used": model if not no_ai else "none",
            "file_analyzed": Path(file).name,
            "total_variants": len(variants),
            "significant_variants": len(significant),
        }
        
        html_content = generate_html_report(
            results=results,
            explanations=explanations,
            summary=summary,
            metadata=metadata,
        )
        
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html_content)
        
        console.print(f"\n[bold green]✓[/bold green] Report saved to: [cyan]{output_path.absolute()}[/cyan]\n")
    except Exception as e:
        console.print(f"\n[bold yellow]⚠[/bold yellow] Failed to generate HTML report: {e}\n", style="yellow")


@allelio.command()
@click.option(
    "-p",
    "--port",
    default=8080,
    type=int,
    help="Port to run server on",
)
@click.option(
    "--host",
    default="127.0.0.1",
    help="Host to bind to",
)
def serve(port: int, host: str):
    """Launch the Allelio web interface.
    
    Start an interactive web server for variant analysis and exploration.
    """
    console.print("\n[bold cyan]Allelio Web Interface[/bold cyan]\n")
    console.print(f"Starting Allelio web interface on {host}:{port}...\n")
    console.print(f"Open [bold cyan]http://{host}:{port}[/bold cyan] in your browser\n")
    
    try:
        import uvicorn
        from allelio.web.app import app
        
        uvicorn.run(app, host=host, port=port, log_level="info")
    except ImportError:
        console.print("[bold red]✗[/bold red] Web server dependencies not installed\n", style="red")
        console.print("Install with: pip install allelio[web]\n")
        raise click.Abort()
    except Exception as e:
        console.print(f"[bold red]✗[/bold red] Server failed: {e}\n", style="red")
        raise click.Abort()


@allelio.command()
def update():
    """Re-download and re-index all databases.
    
    Fetches the latest variant annotations from ClinVar and GWAS catalogs.
    """
    console.print("\n[bold cyan]Allelio Database Update[/bold cyan]\n")

    try:
        db_path = os.path.expanduser("~/.allelio/data/allelio.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        db = AllelioDB(db_path)

        setup_database(db, log=lambda msg: console.print(f"  {msg}"))

        console.print("\n[bold green]✓[/bold green] Databases updated successfully\n")
    except Exception as e:
        console.print(f"\n[bold red]✗[/bold red] Update failed: {e}\n", style="red")
        raise click.Abort()


@allelio.command()
def info():
    """Display database and system information.
    
    Shows database statistics, version info, and Ollama availability.
    """
    console.print("\n[bold cyan]Allelio System Information[/bold cyan]\n")
    
    try:
        db = AllelioDB()
        
        if db.is_initialized():
            info_table = Table(show_header=False)
            info_table.add_row("Database Status", "[bold green]✓ Initialized[/bold green]")
            info_table.add_row("Database Version", db.version())
            
            # Get database stats if available
            try:
                stats = db.get_stats()
                info_table.add_row("Variants Indexed", f"{stats.get('variant_count', 'Unknown'):,}")
                info_table.add_row("Genes Covered", f"{stats.get('gene_count', 'Unknown'):,}")
            except Exception:
                pass
        else:
            info_table = Table(show_header=False)
            info_table.add_row("Database Status", "[bold red]✗ Not initialized[/bold red]")
            info_table.add_row("Action", "Run [cyan]allelio setup[/cyan] to initialize")
        
        console.print(info_table)
        
        # Check Ollama status
        console.print("\n[bold]AI/LLM Status[/bold]")
        try:
            import httpx
            response = httpx.get("http://localhost:11434/api/tags", timeout=2.0)
            if response.status_code == 200:
                console.print("[bold green]✓[/bold green] Ollama available at localhost:11434")
                models = response.json().get("models", [])
                if models:
                    console.print(f"  Installed models: {', '.join([m.get('name', 'unknown') for m in models[:3]])}")
            else:
                console.print("[bold yellow]⚠[/bold yellow] Ollama not responding")
        except Exception:
            console.print("[bold yellow]⚠[/bold yellow] Ollama not available (install for AI features)")
        
        console.print()
    except Exception as e:
        console.print(f"[bold red]✗[/bold red] Failed to get info: {e}\n", style="red")
        raise click.Abort()


main = allelio

if __name__ == "__main__":
    main()
