"""CLI registration for developmental benchmark and evaluation workflows."""
import json
import sqlite3
from pathlib import Path
import click
from allelio.evidence import write_evidence_export


def register(group):
    @group.command('import-vep')
    @click.argument('manifest', type=click.Path(exists=True, dir_okay=False))
    @click.option('--output', required=True, type=click.Path(file_okay=False))
    def import_vep_command(manifest, output):
        """Preserve and adapt a frozen development-only offline VEP run."""
        from allelio.vep import import_vep
        try:
            report = import_vep(manifest, output)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(f"Imported {len(report['cases'])} development cases; parsing-only scope. Independent evaluation remains pending.")

    @group.command('benchmark')
    @click.argument('bundle',type=click.Path(exists=True,dir_okay=False))
    @click.option('--output',required=True,type=click.Path(file_okay=False))
    @click.option('--compare',type=click.Path(exists=True,dir_okay=False))
    def benchmark_command(bundle,output,compare):
        """Run licensed synthetic stage challenges into a new local directory."""
        from allelio.benchmark import run_benchmark,compare_benchmarks
        try:
            report=run_benchmark(bundle,output)
            if compare:
                write_evidence_export(compare_benchmarks(report,json.loads(Path(compare).read_text())),Path(output)/'comparison.json')
        except (ValueError,OSError,KeyError,TypeError,sqlite3.Error) as exc:raise click.ClickException(str(exc)) from exc
        click.echo(f"{len(report['cases'])} synthetic cases; contract checks {'passed' if report['passed'] else 'FAILED'}.")
        if not report['passed']:raise click.ClickException('Stage regressions found; inspect benchmark.json.')

    @group.command('evaluate-explanations')
    @click.argument('bundle',type=click.Path(exists=True,dir_okay=False))
    @click.option('--output',required=True,type=click.Path(file_okay=False))
    @click.option('--model',multiple=True,help='Opt-in local model arms; omit for template-only export.')
    @click.option('--repetitions',type=click.IntRange(1,10),default=1)
    def evaluate_command(bundle,output,model,repetitions):
        """Generate local frozen-evidence arms and blinded review cases."""
        from allelio.evaluation import generate_evaluation
        try:report=generate_evaluation(bundle,output,model,repetitions)
        except (ValueError,OSError,KeyError,TypeError) as exc:raise click.ClickException(str(exc)) from exc
        click.echo(f"Prepared {report['generated_cases']} blinded cases; {report['failed_outputs']} failed model outputs retained separately. No ratings or validation claimed.")

    @group.command('summarize-ratings')
    @click.argument('blinded',type=click.Path(exists=True,dir_okay=False))
    @click.argument('ratings',type=click.Path(exists=True,dir_okay=False))
    @click.option('--output',required=True,type=click.Path(dir_okay=False))
    def ratings_command(blinded,ratings,output):
        """Validate local ratings and retain missing/disputed observations."""
        from allelio.cli import _run_output_paths
        from allelio.evaluation import summarize_ratings
        _run_output_paths([blinded,ratings],[output])
        try:report=summarize_ratings(blinded,ratings);write_evidence_export(report,output)
        except (ValueError,OSError,KeyError,TypeError) as exc:raise click.ClickException(str(exc)) from exc
        click.echo(f"{report['received_rows']}/{report['expected_rows']} rating rows received; agreement is descriptive, not expert judgment.")
