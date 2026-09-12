# Rebuild and publish the allele-aware frequency extract

The format-2 release uses the public rsIDs in the published format-1 extract.
Its selection provenance records the legacy checksum and number of selected
rsIDs. No private genotype file is needed, and old frequencies are not assigned
guessed identities. Every output allele and frequency comes from the pinned
v4.1.1 genome sites VCFs on GRCh38.

## Resumable build

```sh
python3 -u scripts/rebuild_gnomad_release.py \
  --legacy gnomad_v4.1.1_array_freq.tsv.gz \
  --work-dir build/gnomad-format2 --jobs 3
```

This streams up to three chromosomes at a time. Source VCFs are not kept on disk.
Each completed chromosome has a checksum and completion marker. The command
locks the work directory against duplicate runs, retries failed chromosomes
three times, and reuses verified checkpoints on rerun. A changed input selection
or builder invalidates old checkpoints. Keep the same work directory to resume.
`status.json`, `rebuild.log` (when redirected by the caller) and individual
`chr*.log` files describe progress. Large sources take hours; keep the computer
and network available. No GitHub Actions minutes are used for this build.

The final file is `gnomad_v4.1.1_array_freq_format2.tsv.gz`. Its
`manifest.unpublished.json` has provenance and checksum but deliberately has no
public URLs. Neither is advertised as a release until validated and uploaded.

## Validate

```sh
python3 scripts/validate_gnomad_release.py \
  build/gnomad-format2/manifest.unpublished.json \
  --report build/gnomad-format2/validation.json
```

A nonzero exit means stop and inspect the report. In particular, inspect any
selected rsIDs missing from the rebuilt source instead of silently narrowing
coverage. Validate the rebuilt data through a temporary database and the
example/ablation checks before publishing. The smaller test fixture uses the
v4.1 API and does not by itself establish release equivalence for v4.1.1.

## Publish

Upload the verified public extract to Arweave through an authenticated
Permavault session. Retain the returned transaction ID. Mirror the same bytes
on a new GitHub data release, preserving the old data release for reproducibility.
Download both copies and verify their SHA-256 before updating
`data/gnomad_manifest.json`. Preserve provenance fields from the unpublished
manifest and insert the verified URLs. Update the fallback in
`allelio/database/downloader.py` and add the new snapshot to
`data/archival_snapshots.json` in the same change. Do not replace a manifest URL
with an unverified or pending upload.

Then refresh the local reference database, run the real example and ablation
checks, and finish issue #23. If an upload requires sign-in or payment, surface
that concrete requirement; never put credentials in a file, log, commit or
manifest.
