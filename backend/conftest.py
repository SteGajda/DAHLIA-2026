"""Root configuration for pytest.

This file is loaded before any test modules. It is used to register 
global warning filters early in the execution process. Actual test 
fixtures are defined in ``tests/conftest.py``.
"""

from __future__ import annotations

import warnings


def pytest_configure(config):  # noqa: ARG001
    """Register warning filters."""
    warnings.filterwarnings(
        "ignore",
        message="The anyio.abc.BlockingPortal alias is deprecated",
        category=DeprecationWarning,
    )
    warnings.filterwarnings(
        "ignore",
        message="Using `httpx` with `starlette.testclient` is deprecated",
    )
