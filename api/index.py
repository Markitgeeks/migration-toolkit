"""Vercel serverless entry point — exposes the FastAPI app as a handler."""

from app.main import app  # noqa: F401

# Vercel looks for an `app` variable in this module.
# The import above is all that's needed.
