"""
Vercel serverless entry point.
Vercel imports `app` from this file and serves it as a WSGI function.
"""
import sys
import os

# Make sure the project root is on the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: F401 — Vercel picks this up automatically
