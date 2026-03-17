"""Vercel serverless entry point."""
from app.main import app

# Vercel's @vercel/python runtime detects this ASGI app automatically.
handler = app
