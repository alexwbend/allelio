"""Allelio CLI interface using Click and Rich for user interaction."""

import asyncio
import os
import socket
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.markup import escape
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
    default=None,
    help="Model name for explanations (default: $ALLELIO_MODEL, else llama3.1:8b)",
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
    model: Optional[str],
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

    # Settle the model before anything is read. Construction only parses and
    # resolves the address, and the listing call costs one request — both are
    # cheap here and useless after half an hour of parsing and lookups, which is
    # where a refusal or a stale model name used to surface.
    engine = None
    if not no_ai:
        try:
            from allelio.ai.engine import (
                AIEngine,
                attribution,
                OLLAMA,
                OPENAI_COMPATIBLE,
                REFUSED,
                REFUTED,
                UNREACHABLE,
            )
        except ImportError:
            console.print("  [yellow]⚠[/yellow] AI module not available (pip install ollama)")
            console.print("    Skipping AI explanations.\n")
        else:
            try:
                engine = AIEngine(model=model)
            except ValueError as e:
                console.print(f"\n[bold red]✗[/bold red] {escape(str(e))}\n", style="red")
                raise click.Abort()

            if engine.client is None:
                # engine.py swallows the ImportError so the rest of the tool
                # still runs, which leaves this as the only place the missing
                # package can be told apart from a daemon that is not up.
                console.print("  [yellow]⚠[/yellow] AI module not available (pip install ollama)")
                console.print("    Skipping AI explanations.\n")
                engine = None
            elif engine.provider == OPENAI_COMPATIBLE:
                # One thing has to be known before the genome is read: a server
                # whose only model is an Ollama Cloud tag relays the prompt off
                # this machine, and adoption — the only place that name appears —
                # happens on this provider's path alone. Asking costs one
                # request to loopback. Nothing else is decided here: the listing
                # is advisory, and it is read again inside the explanation loop.
                asyncio.run(engine.check_connection())
                if engine.status == REFUSED:
                    console.print(f"\n[bold red]✗[/bold red] {escape(engine.refusal)}\n", style="red")
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
    # rsID -> Explanation: the text and, where the model wrote it, its name.
    # Everything printed about who wrote what is counted off this, so there is
    # no second number that can disagree with the pages in the report.
    explanations = {}
    if engine is not None:
        # Sort by significance and take top N
        top_variants = sorted(
            results, key=lambda x: x.significance_rank
        )[:top]

        try:
            # One loop for the whole run, the listing included. asyncio.run()
            # per variant closes the loop the ollama client's connection pool is
            # bound to, so every second call came back "Event loop is closed" —
            # swallowed into a fallback that reads like an explanation, on the
            # default provider. That is also why the listing is fetched in here
            # rather than beside the one above: for Ollama it would be the first
            # use of that pool, on a loop that then closes.
            async def explain_each():
                # Asked here, on the loop the prompts will run on: ollama's
                # client binds its connection pool to the first loop it is used
                # on, so a listing fetched anywhere else leaves every prompt
                # talking to a loop that has closed. The OpenAI-compatible
                # client builds a fresh httpx client per call and was already
                # asked above, for the refusal — so it is not asked twice.
                if engine.provider == OLLAMA:
                    await engine.check_connection()
                if not engine.will_explain():
                    return
                # engine.model, not the option, and read after the listing —
                # which is where a server holding a single model names it.
                console.print(
                    f"  Generating AI explanations for top {len(top_variants)} variants "
                    f"using {escape(engine.model)} "
                    f"({escape(engine.provider)} at {escape(engine.host)})...\n"
                )
                for idx, variant in enumerate(top_variants, 1):
                    try:
                        written = await engine.explain(variant)
                        explanations[variant.rsid] = written
                        # A failed call still returns text — the fallback, written
                        # from ClinVar and the GWAS Catalog. This card's own
                        # record says which of the two it got.
                        if written.model:
                            console.print(f"    [{idx}/{len(top_variants)}] {variant.rsid} ✓")
                        else:
                            # This card's own reason. The engine keeps one
                            # slot for the last error, which is a different
                            # sentence the moment anything runs concurrently.
                            said = f" ({escape(written.error)})" if written.error else ""
                            console.print(
                                f"    [{idx}/{len(top_variants)}] {variant.rsid} ✗{said}"
                            )
                    except Exception as e:
                        console.print(f"    [{idx}/{len(top_variants)}] {variant.rsid} ✗ ({escape(str(e))})")

            asyncio.run(explain_each())

            status = engine.status
            if status == REFUSED:
                # Unreachable as things stand — the OpenAI-compatible path is
                # the only one that adopts a served name, and it was refused
                # above, before the file was read. Kept because it is the lock
                # on a prompt leaving this machine, and the cost of keeping it
                # is one string comparison.
                console.print(f"\n[bold red]✗[/bold red] {escape(engine.refusal)}\n", style="red")
                raise click.Abort()
            elif status in (REFUTED, UNREACHABLE):
                # The analysis is still worth having; the attribution on it is
                # not. Say which of the two happened and what fixes it.
                console.print(f"\n  [yellow]⚠[/yellow] {escape(engine.reason())}")
                if status == REFUTED and engine.provider == OLLAMA:
                    console.print(
                        f"  Pull it: [bold cyan]ollama pull {escape(engine.model)}[/bold cyan]"
                    )
                elif status == REFUTED:
                    console.print(
                        "  Name one with [bold cyan]ALLELIO_MODEL[/bold cyan], "
                        "or run with [bold cyan]--no-ai[/bold cyan]."
                    )
                console.print("  Continuing without explanations.\n")
            # Counted off the cards, not off the run: a failed call still
            # returns text — the variant's own data, wrapped in the disclaimer —
            # and counting those would credit the model for pages it never wrote.
            elif attribution(explanations).written:
                console.print(
                    f"\n  [bold green]✓[/bold green] Generated "
                    f"{attribution(explanations).written} AI explanations\n"
                )
            else:
                # It answered and then wrote nothing. Its own sentence is the
                # diagnostic — "model 'x' not found" — and it is server text.
                # Read off the cards, like everything else here: the engine's
                # own slot holds whichever call wrote to it last.
                reasons = [w.error for w in explanations.values() if w.error]
                said = f" ({escape(reasons[-1])})" if reasons else ""
                console.print(
                    f"\n  [yellow]⚠[/yellow] No explanations generated.{said}\n"
                )
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
    # escape: rich reads "[" as the start of a style tag, and --host takes
    # whatever the shell hands it.
    console.print(f"Starting Allelio web interface on {escape(host)}:{port}...\n")

    # The app rejects Host headers it does not recognise, which is what stops a
    # remote page from reaching this server by pointing its own domain at
    # 127.0.0.1. Whatever the operator chose to bind belongs on the list; it has
    # to be set before the app module is imported.
    # An empty --host binds everywhere; there is no URL in it to print.
    browse_to = host or "localhost"
    if not os.environ.get("ALLELIO_ALLOWED_HOSTS"):
        try:
            # inet_aton takes every legacy spelling of "all interfaces" — 0,
            # 0.0, 0x0 — that comparing against "0.0.0.0" would miss, and it
            # does no lookups, so a hostname simply raises.
            binds_everywhere = socket.inet_aton(host) == b"\x00\x00\x00\x00"
        except OSError:
            binds_everywhere = False

        # Starlette strips the port by splitting the Host header on ":", so no
        # IPv6 literal on the list could ever match; neither could a bind
        # address nobody types into a browser. Lowercased because that is how
        # browsers send it and starlette compares exactly.
        # An empty --host binds everywhere too: asyncio special-cases it into a
        # getaddrinfo with AI_PASSIVE, which answers 0.0.0.0 and ::.
        extra = [] if binds_everywhere or not host or ":" in host else [host.lower()]
        os.environ["ALLELIO_ALLOWED_HOSTS"] = ",".join(
            dict.fromkeys(["localhost", "127.0.0.1"] + extra)
        )
        if not extra:
            # Printing the bound address here would send them to a URL that
            # answers 400.
            browse_to = "localhost"
            console.print(
                f"[bold yellow]⚠[/bold yellow] Bound to {escape(host) or 'every interface'}, but "
                "browse to "
                "localhost — "
                "the host check has no way to match that address.\n"
                "  That check is what stops a web page you visit from reading your genome "
                "off this server, which has no password on it.\n"
                "  To let another machine reach it, name that machine: "
                "ALLELIO_ALLOWED_HOSTS=192.168.1.50 allelio serve --host 0.0.0.0\n",
                style="yellow",
            )

    # A bare IPv6 literal needs brackets or the browser reads the last colon as
    # the port separator, and rich reads "[::1]" as a style tag.
    url = f"http://[{browse_to}]:{port}" if ":" in browse_to else f"http://{browse_to}:{port}"
    console.print(f"Open [bold cyan]{escape(url)}[/bold cyan] in your browser\n")

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
        
        # Which model would answer, and where it is running. Asked through the
        # engine rather than Ollama's own port, so this still tells the truth
        # when ALLELIO_OPENAI_BASE has pointed the tool somewhere else.
        console.print("\n[bold]AI/LLM Status[/bold]")
        try:
            from allelio.ai.engine import (
                AIEngine,
                OLLAMA,
                REFUSED,
                REFUTED,
                UNREACHABLE,
            )

            engine = AIEngine()
        except ValueError as e:
            console.print(f"[bold red]✗[/bold red] {escape(str(e))}")
        except Exception:
            console.print("[bold yellow]⚠[/bold yellow] AI module not available (pip install ollama)")
        else:
            if engine.client is None:
                # engine.py swallows the ImportError, so nothing above this can
                # tell the missing package from a server that is not answering.
                console.print("[bold yellow]⚠[/bold yellow] AI module not available (pip install ollama)")
            else:
                # The same five-way answer `analyze` gets, so the diagnostic
                # command and the one doing the work cannot disagree about the
                # same server — which they did, in both directions.
                asyncio.run(engine.check_connection())
                status = engine.status
                if status == REFUSED:
                    console.print(f"[bold red]✗[/bold red] {escape(engine.refusal)}")
                elif status == UNREACHABLE:
                    console.print(
                        f"[bold yellow]⚠[/bold yellow] {escape(engine.reason())} "
                        "(optional — Allelio runs without it)"
                    )
                else:
                    console.print(
                        f"[bold green]✓[/bold green] {escape(engine.provider)} answering at "
                        f"{escape(engine.host)}"
                    )
                    console.print(f"  Model: [bold cyan]{escape(engine.model)}[/bold cyan]")
                    if status == REFUTED:
                        console.print(
                            f"  [bold yellow]⚠[/bold yellow] {escape(engine.model)} is not on that server."
                        )
                        if engine.provider == OLLAMA:
                            console.print(
                                f"  Pull it: [bold cyan]ollama pull {escape(engine.model)}[/bold cyan]"
                            )
                        elif engine.served_models:
                            # A llama-swap config lists a dozen and none of them
                            # is named llama3.1:8b, so print the menu rather
                            # than a command that cannot work here.
                            offered = ", ".join(engine.served_models[:8])
                            console.print(f"  That server offers: {escape(offered)}")
                            console.print(
                                "  Name one with [bold cyan]ALLELIO_MODEL[/bold cyan]."
                            )
                    # UNLISTED says nothing about the model: this server does
                    # not enumerate, so there is nothing to contradict it with.
        
        console.print()
    except Exception as e:
        console.print(f"[bold red]✗[/bold red] Failed to get info: {e}\n", style="red")
        raise click.Abort()


main = allelio

if __name__ == "__main__":
    main()
