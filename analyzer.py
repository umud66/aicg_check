"""Compatibility shim for the current analyzer implementation.

The public import surface stays stable for app.py, tests and benchmark.py while
v0.4 lives in analyzer_v04.py.
"""

from analyzer_v04 import *  # noqa: F401,F403
