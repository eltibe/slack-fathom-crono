"""
Pytest configuration.

Ensures the project root and src/ are on sys.path so tests can import modules
without relying on PYTHONPATH environment tweaks.
"""
import os
import sys

REPO_ROOT = os.path.abspath(os.path.dirname(__file__))
SRC_PATH = os.path.join(REPO_ROOT, "src")

for path in (REPO_ROOT, SRC_PATH):
    if path not in sys.path:
        sys.path.insert(0, path)
