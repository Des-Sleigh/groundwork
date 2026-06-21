"""Pytest rootdir marker.

Its mere presence puts the repo root on sys.path (pytest prepends the rootdir),
so tests can import the top-level packages — including ones not pip-installed
(evals, api, run_demo) — under a bare `pytest` invocation and in CI.
"""
