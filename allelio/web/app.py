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

# Add CORS middleware for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
