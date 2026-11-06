"""Reviewed bytes, immutable imports, permissions, preview and rollback."""

from pathlib import Path
import hashlib

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.models.experiment import Dataset
from app.models.user import AppUser
from app.services.dataset_import import PRESETS, import_datasets, prepare_imports

DATA = Path(__file__).resolve().parents[2] / "frontend" / "data"


@pytest.fixture
def developer(sqlite_session):
    user = AppUser(email="import@example.com", display_name="Developer", password_hash="unused",
                   role_code="DEVELOPER", is_active=True, is_email_verified=True)
    sqlite_session.add(user)
    sqlite_session.commit()
    return user


def test_reviewed_csv_bytes_and_configs():
    prepared = prepare_imports(DATA)
    for values, preset in zip(prepared, PRESETS):
        assert hashlib.sha256(values["csv_file"]).hexdigest() == preset.sha256
        assert values["row_count"] == preset.row_count
        assert values["imputed_column"] == preset.imputed_column


def test_preview_is_read_only_and_apply_is_idempotent(sqlite_session, developer):
    preview = import_datasets(sqlite_session, DATA)
    assert all(item["status"] == "would create" for item in preview)
    assert sqlite_session.scalar(select(func.count()).select_from(Dataset)) == 0
    created = import_datasets(sqlite_session, DATA, apply=True)
    original = {row.name: (row.dataset_id, row.created_at, row.csv_file) for row in sqlite_session.scalars(select(Dataset))}
    assert {item["name"] for item in created} == {"wola", "stamp_type"}
    assert all(item["created_by"] == developer.user_id for item in created)
    again = import_datasets(sqlite_session, DATA, apply=True)
    assert all(item["status"] == "unchanged" for item in again)
    assert original == {row.name: (row.dataset_id, row.created_at, row.csv_file) for row in sqlite_session.scalars(select(Dataset))}


def test_inactive_dataset_is_not_reactivated(sqlite_session, developer):
    import_datasets(sqlite_session, DATA, apply=True)
    item = sqlite_session.scalar(select(Dataset).where(Dataset.name == "wola"))
    item.is_active = False
    sqlite_session.commit()
    result = import_datasets(sqlite_session, DATA, apply=True)
    assert result[0]["status"] == "unchanged (inactive)"
    sqlite_session.refresh(item)
    assert item.is_active is False


def test_name_conflict_aborts_entire_batch(sqlite_session, developer):
    values = prepare_imports(DATA)[1]
    values["csv_sha256"] = bytes(32)
    existing = Dataset(**values, created_by=developer.user_id, is_active=True)
    sqlite_session.add(existing)
    sqlite_session.commit()
    with pytest.raises(ValueError, match="different content"):
        import_datasets(sqlite_session, DATA, apply=True)
    assert sqlite_session.scalar(select(func.count()).select_from(Dataset)) == 1


@pytest.mark.parametrize("field,value", [("role_code", "RESEARCHER"), ("is_active", False), ("is_email_verified", False)])
def test_author_must_be_active_verified_developer(sqlite_session, developer, field, value):
    setattr(developer, field, value)
    sqlite_session.commit()
    with pytest.raises(ValueError, match="DEVELOPER"):
        import_datasets(sqlite_session, DATA, author_id=developer.user_id, apply=True)
    assert sqlite_session.scalar(select(func.count()).select_from(Dataset)) == 0


def test_unknown_author_and_multiple_authors_require_explicit_choice(sqlite_session, developer):
    with pytest.raises(ValueError):
        import_datasets(sqlite_session, DATA, author_id=999, apply=True)
    sqlite_session.add(AppUser(email="second@example.com", display_name="Other", password_hash="unused",
        role_code="DEVELOPER", is_active=True, is_email_verified=True))
    sqlite_session.commit()
    with pytest.raises(ValueError, match="Eligible IDs"):
        import_datasets(sqlite_session, DATA, apply=True)


def test_altered_csv_is_rejected_before_inserts(sqlite_session, developer, tmp_path):
    for preset in PRESETS:
        (tmp_path / f"{preset.name}.csv").write_bytes((DATA / f"{preset.name}.csv").read_bytes())
    with (tmp_path / "stamp_type.csv").open("ab") as out:
        out.write(b"\n")
    with pytest.raises(ValueError, match="SHA-256"):
        import_datasets(sqlite_session, tmp_path, apply=True)
    assert sqlite_session.scalar(select(func.count()).select_from(Dataset)) == 0


def test_commit_failure_rolls_back_both_datasets(sqlite_session, developer, monkeypatch):
    def fail():
        raise SQLAlchemyError("Injected failure")
    monkeypatch.setattr(sqlite_session, "commit", fail)
    with pytest.raises(SQLAlchemyError):
        import_datasets(sqlite_session, DATA, apply=True)
    assert sqlite_session.scalar(select(func.count()).select_from(Dataset)) == 0


@pytest.mark.parametrize("actual_server,actual_db", [("azure-server", "DAHLIA_DEV"), ("local-server", "DAHLIA")])
def test_cli_refuses_wrong_target(monkeypatch, capsys, actual_server, actual_db):
    import sys
    from types import SimpleNamespace
    from unittest.mock import MagicMock, Mock
    from app.db import session as session_module
    from app.scripts.import_industrial_datasets import main
    import app.services.dataset_import as service
    session = MagicMock()
    session.__enter__.return_value = session
    session.execute.return_value.one.return_value = (actual_server, actual_db)
    monkeypatch.setattr(session_module, "SessionLocal", lambda: session)
    engine = SimpleNamespace(dialect=SimpleNamespace(name="mssql"), dispose=Mock())
    monkeypatch.setattr(session_module, "engine", engine)
    imported = Mock()
    monkeypatch.setattr(service, "import_datasets", imported)
    monkeypatch.setattr(sys, "argv", ["import", "--expect-server", "local-server", "--expect-database", "DAHLIA_DEV", "--apply"])
    assert main() == 1
    imported.assert_not_called()
    assert "Nothing was imported" in capsys.readouterr().out


def test_cli_default_path_preview_and_secret_redaction(monkeypatch, capsys):
    import sys
    from types import SimpleNamespace
    from unittest.mock import MagicMock, Mock
    from app.db import session as session_module
    from app.scripts.import_industrial_datasets import main
    import app.services.dataset_import as service
    session = MagicMock()
    session.__enter__.return_value = session
    session.execute.return_value.one.return_value = ("local-server", "DAHLIA_DEV")
    monkeypatch.setattr(session_module, "SessionLocal", lambda: session)
    monkeypatch.setattr(session_module, "engine", SimpleNamespace(dialect=SimpleNamespace(name="mssql"), dispose=Mock()))
    imported = Mock(return_value=[])
    monkeypatch.setattr(service, "import_datasets", imported)
    monkeypatch.setattr(sys, "argv", ["import", "--expect-server", "local-server", "--expect-database", "DAHLIA_DEV"])
    assert main() == 0
    assert imported.call_args.args[1] == DATA
    assert imported.call_args.kwargs["apply"] is False
    assert "PREVIEW ONLY" in capsys.readouterr().out
    session.execute.side_effect = SQLAlchemyError("private-password-value")
    assert main() == 1
    assert "private-password-value" not in capsys.readouterr().out
