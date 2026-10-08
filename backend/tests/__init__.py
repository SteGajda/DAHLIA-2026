"""DAHLIA backend tests package.

Tests are divided into two categories:

* **Runtime tests** (this directory) — test FastAPI endpoints using SQLite
  initialized via ``Base.metadata.create_all()``. They do not require any
  external server and are executed with ``pytest``.

* **Integration tests** (future) — target MS SQL Server / Azure SQL
  to verify behavior with the actual production engine.

Naming convention
-----------------
* ``test_<module>.py`` — tests for a specific application module.
* ``conftest.py`` — shared fixtures (app, client, db session).
"""
