#!/usr/bin/env python3
"""Resumable format-2 rebuild over the rsIDs in a published legacy extract.

Streams each pinned source chromosome in a separate process (bounded by --jobs),
keeps successful outputs/checksums, and combines only a complete build. Does not
upload or mutate the live manifest. State and logs are under --work-dir.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import os

from build_gnomad_freq import ALL_CHROMOSOMES, GNOMAD_VCF_TEMPLATE, OUTPUT_COLUMNS


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def save_json(path, value):
    partial = path.with_name(path.name + '.tmp')
    partial.write_text(json.dumps(value, indent=2) + '\n')
    partial.replace(path)


def recover_sites(legacy, destination):
    """Recover only public rsIDs, never pretend to reconstruct old alleles."""
    sites = set()
    with gzip.open(legacy, 'rt') as source:
        for line in source:
            first = line.split('\t', 1)[0].strip()
            if first.startswith('rs') and first[2:].isdigit():
                sites.add(first)
    if not sites:
        raise ValueError('legacy extract contains no rsIDs')
    destination.write_text('\n'.join(sorted(sites)) + '\n')
    return len(sites)


def combine(chromosomes, work, output, config):
    """Validate completed chunks and atomically produce the full release."""
    rows, seen_sites = 0, set()
    partial = output.with_name(output.name + '.partial')
    with gzip.open(partial, 'wt', compresslevel=6) as target:
        target.write('## Allelio gnomAD frequency file\n## Format: 2\n')
        target.write(f"## Source: gnomAD v{config['version']} genome sites VCFs\n## Assembly: GRCh38\n")
        target.write('## License: CC0 1.0 (gnomAD primary data)\n')
        target.write(f"## Selection: rsIDs from legacy extract SHA-256 {config['legacy_sha256']}\n")
        target.write(f"## Selected rsIDs: {config['selected_sites']}\n")
        target.write('\t'.join(OUTPUT_COLUMNS) + '\n')
        for chromosome in chromosomes:
            chunk = work / (chromosome + '.tsv.gz')
            marker = json.loads((work / (chromosome + '.complete.json')).read_text())
            if marker['config'] != config or marker['sha256'] != digest(chunk):
                raise ValueError(f'{chromosome}: checkpoint identity/checksum mismatch')
            chunk_rows = 0
            header_seen = False
            with gzip.open(chunk, 'rt') as source:
                for line in source:
                    if line.startswith('##'):
                        continue
                    if not header_seen:
                        if line.rstrip('\n').split('\t') != OUTPUT_COLUMNS:
                            raise ValueError(f'{chromosome}: unexpected columns')
                        header_seen = True
                        continue
                    fields = line.rstrip('\n').split('\t')
                    if len(fields) != len(OUTPUT_COLUMNS) or 'chr' + fields[1] != chromosome:
                        raise ValueError(f'{chromosome}: inconsistent row identity')
                    if not fields[2].isdigit() or int(fields[2]) <= 0 or not fields[3] or not fields[4]:
                        raise ValueError(f'{chromosome}: missing position/allele')
                    target.write(line)
                    seen_sites.add(fields[0])
                    chunk_rows += 1
            if chunk_rows != marker['rows']:
                raise ValueError(f'{chromosome}: row count differs from checkpoint')
            rows += chunk_rows
    if not rows:
        raise ValueError('empty release')
    output.parent.mkdir(parents=True, exist_ok=True)
    partial.replace(output)
    return rows, len(seen_sites)


def run(args):
    work = Path(args.work_dir).resolve()
    work.mkdir(parents=True, exist_ok=True)
    lock = (work / 'build.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    sites = work / 'selected-rsids.txt'
    selected = recover_sites(args.legacy, sites)
    builder = Path(__file__).with_name('build_gnomad_freq.py').resolve()
    config = dict(version='4.1.1', legacy_sha256=digest(args.legacy),
                  sites_sha256=digest(sites), selected_sites=selected, builder_sha256=digest(builder))
    save_json(work / 'config.json', config)
    chromosomes = ALL_CHROMOSOMES
    # Small sources first give early completed checkpoints and real throughput.
    order = ['chrY', 'chr21', 'chr22'] + [c for c in reversed(chromosomes) if c not in ('chrY','chr21','chr22')]

    def build(chromosome):
        output = work / (chromosome + '.tsv.gz')
        marker = work / (chromosome + '.complete.json')
        if marker.exists() and output.exists():
            prior = json.loads(marker.read_text())
            if prior['config'] == config and prior['sha256'] == digest(output):
                print(f'{chromosome}: verified checkpoint reused', flush=True)
                return True
        for attempt in range(1, 4):
            print(f'{chromosome}: starting attempt {attempt}', flush=True)
            with (work / (chromosome + '.log')).open('w') as log:
                result = subprocess.run([sys.executable, '-u', str(builder), '--chromosomes', chromosome,
                    '--array-sites', str(sites), '--output', str(output), '--version', config['version']],
                    stdout=log, stderr=subprocess.STDOUT)
            if result.returncode == 0 and output.exists():
                with gzip.open(output, 'rt') as source:
                    rows = sum(1 for line in source if line.startswith('rs') and not line.startswith('rsid'))
                save_json(marker, dict(config=config, sha256=digest(output), rows=rows))
                print(f'{chromosome}: complete ({rows} rows)', flush=True)
                return True
            print(f'{chromosome}: attempt {attempt} failed; see {chromosome}.log', flush=True)
        return False

    save_json(work / 'status.json', dict(state='running', pid=os.getpid(), chromosomes=order, jobs=args.jobs))
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(build, order))
    if not all(results):
        save_json(work / 'status.json', dict(state='failed', failed=[c for c,ok in zip(order,results) if not ok]))
        return 1
    output = work / 'gnomad_v4.1.1_array_freq_format2.tsv.gz'
    rows, represented = combine(chromosomes, work, output, config)
    manifest = dict(schema=2, source='gnomAD', version='v4.1.1', format=2, assembly='GRCh38',
                    file=output.name, sha256=digest(output), rows=rows,
                    source_urls=[GNOMAD_VCF_TEMPLATE.format(version=config['version'], chrom=c) for c in chromosomes],
                    license='CC0 1.0', license_url='https://gnomad.broadinstitute.org/policies',
                    selection=dict(method='published-extract-rsids', legacy_sha256=config['legacy_sha256'],
                                   selected_rsids=selected, represented_rsids=represented), urls=[])
    save_json(work / 'manifest.unpublished.json', manifest)
    save_json(work / 'status.json', dict(state='complete', file=str(output), rows=rows, sha256=manifest['sha256']))
    print(f'Complete: {output} ({rows} rows). Validate and upload before setting public URLs.', flush=True)
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--legacy', required=True)
    parser.add_argument('--work-dir', default='build/gnomad-format2')
    parser.add_argument('--jobs', type=int, choices=range(1, 5), default=3)
    sys.exit(run(parser.parse_args()))
