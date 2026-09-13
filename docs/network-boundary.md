# Observed local network boundary

`tests/test_network_boundary.py` exercises synthetic CLI and web annotations
with installed temporary references. Socket `connect` and `connect_ex` calls
are recorded and reject non-loopback destinations. Annotation-only requests
make no socket connections. CLI users select `--no-ai`; web users select
**Annotation only**, or send `no_ai=true` with the multipart upload.

Controlled HTTP servers on ephemeral loopback ports exercise the real Ollama
and OpenAI-compatible adapters. The tests cover successful requests, connection
loss, 307 redirects to a documentation-only remote address, and a hostname
whose mocked resolution changes after endpoint validation. Remote endpoints
are rejected before genotype-bearing model requests; the pin remains the
validated loopback address. Redirects are not followed, and failures do not
switch to a remote provider.

Upload temporary files are checked after success and parser failure. Unexpected
parser/analysis exception text is not returned to the browser or printed by the
CLI, since it can contain input content. Reports and evidence intentionally
contain observations when requested; tests distinguish those outputs from raw
input/error leakage. Model exception text and model-generated output remain
separate existing concerns; this experiment does not claim universal redaction.

Setup is outside this experiment: downloading reference data deliberately uses
network access. Status/model-discovery endpoints may contact the configured
local server even when a subsequent analysis is annotation-only. The browser
itself uses loopback HTTP to reach Allelio. These checks measure Allelio's
connection behavior, not what a separately operated model server does internally,
and do not establish a blanket zero-network or clinical privacy guarantee.
