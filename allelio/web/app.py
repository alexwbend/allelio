"""FastAPI application for Allelio web interface."""

import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.trustedhost import TrustedHostMiddleware

from allelio import __version__, __app_name__

app = FastAPI(
    title=__app_name__,
    version=__version__,
    description="Privacy-first local genomics analysis powered by AI",
)

# No CORS middleware: the UI is served from this same app, so nothing here is
# cross-origin. The wildcard that used to sit here, with credentials allowed,
# let any page the user happened to visit read their genome off localhost.

# Binding to 127.0.0.1 is not on its own a boundary: a page on a domain whose
# DNS re-resolves to 127.0.0.1 is same-origin by the browser's reckoning, and
# CORS never enters into it. Checking the Host header is what closes that, and
# it costs nothing when the host is what we bound to. `serve` widens this to
# whatever --host it was given.
#
# Starlette compares against the Host header with the port already stripped, so
# entries carry no port. It splits on ":" to do it, which leaves no spelling of
# a bracketed IPv6 literal that can ever match — "localhost" is how you reach
# this over IPv6.
# Loopback always stays on the list. It is the address the person running this
# actually types, and naming a LAN address should not lock them out of their own
# machine. It costs nothing: a rebound domain arrives in the Host header as its
# own name, never as "localhost", so this is not a way in.
#
# Lowercased because browsers send the host lowercased and starlette compares it
# exactly — an entry with a capital in it could never match.
ALLOWED_HOSTS = list(
    dict.fromkeys(
        ["localhost", "127.0.0.1"]
        + [
            h.strip().lower()
            for h in os.environ.get("ALLELIO_ALLOWED_HOSTS", "").split(",")
            if h.strip()
        ]
    )
)

# TrustedHostMiddleware only checks its patterns when the stack is first built,
# which is on the first request — a typo in the environment would otherwise take
# down a run that had already printed its URL. It checks with an assert, so it
# would also stop checking under -O. Both halves of starlette's rule, restated
# here and raising for real: no "*" past the first character, and a leading one
# has to be the "*." of a subdomain wildcard. "*example.com" fails both its
# check and this one — it is a forgotten dot, not a pattern.
_bad = [
    h
    for h in ALLOWED_HOSTS
    if "*" in h[1:] or (h.startswith("*") and h != "*" and not h.startswith("*."))
]
if _bad:
    raise ValueError(
        f"ALLELIO_ALLOWED_HOSTS: {', '.join(_bad)} — a wildcard host has to look "
        "like '*.example.com', or be '*' on its own."
    )

app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)

# Template directory
TEMPLATE_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# Import and include routes
from allelio.web.routes import router
app.include_router(router)
