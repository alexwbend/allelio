"""FastAPI application for Allelio web interface."""

import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from allelio import __version__, __app_name__

app = FastAPI(
    title=__app_name__,
    version=__version__,
    description="Privacy-first local genomics analysis powered by AI",
)

# No CORS middleware: the UI is served from this same app, so nothing here is
# cross-origin. The wildcard that used to sit here, with credentials allowed,
# let any page the user happened to visit read their genome off localhost.

# Template directory
TEMPLATE_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# Import and include routes
from allelio.web.routes import router
app.include_router(router)
