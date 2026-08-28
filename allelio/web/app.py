"""FastAPI application for Allelio web interface."""

import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from allelio import __version__, __app_name__

app = FastAPI(
    title=__app_name__,
    version=__version__,
    description="Privacy-first local genomics analysis powered by AI",
)

# The UI is served from this same app, so CORS only needs to cover a dev
# server on another loopback port. A wildcard with credentials let any page
# the user visited POST their genome to localhost and read the result back.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Template directory
TEMPLATE_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# Import and include routes
from allelio.web.routes import router
app.include_router(router)
