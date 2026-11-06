"""Downloaded immutable execution packages, scoped to backend and database."""

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import re

from .config import DATASETS
from .experiment import load_predefined_data
from .predefined_sets import CatalogSet, parse_set_catalog


class PredefinedCache:
    def __init__(self, storage):
        self.storage = storage
        with self.connection() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS predefined_cache_sources (
                backend_key TEXT PRIMARY KEY, catalog_id TEXT NOT NULL)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS predefined_downloads (
                backend_key TEXT NOT NULL, catalog_id TEXT NOT NULL, set_id INTEGER NOT NULL,
                bundle_json TEXT NOT NULL, downloaded_at TEXT NOT NULL, available INTEGER NOT NULL,
                PRIMARY KEY (backend_key, catalog_id, set_id))""")

    @contextmanager
    def connection(self):
        conn = self.storage._get_connection()
        try:
            with conn:
                yield conn
        finally:
            if self.storage._connection_target != ":memory:":
                conn.close()

    @staticmethod
    def key(backend: str) -> str:
        return hashlib.sha256(backend.rstrip("/").encode()).hexdigest()

    def catalog_id(self, backend: str) -> str | None:
        with self.connection() as conn:
            row = conn.execute("SELECT catalog_id FROM predefined_cache_sources WHERE backend_key = ?",
                               (self.key(backend),)).fetchone()
            return row[0] if row else None

    def refresh(self, backend: str, data: dict) -> tuple[CatalogSet, ...]:
        if not isinstance(data, dict) or not isinstance(data.get("catalog_id"), str) or not re.fullmatch(r"[0-9a-f]{64}", data["catalog_id"]):
            raise ValueError("The server returned an invalid catalog identity.")
        items = parse_set_catalog(data.get("sets"))
        if any(not item.is_active for item in items):
            raise ValueError("The server returned an inactive set in the selection catalog.")
        key, identity = self.key(backend), data["catalog_id"]
        with self.connection() as conn:
            conn.execute("INSERT INTO predefined_cache_sources VALUES (?, ?) ON CONFLICT(backend_key) DO UPDATE SET catalog_id=excluded.catalog_id", (key, identity))
            conn.execute("UPDATE predefined_downloads SET available=0 WHERE backend_key=?", (key,))
            conn.executemany("UPDATE predefined_downloads SET available=1 WHERE backend_key=? AND catalog_id=? AND set_id=?",
                             [(key, identity, item.predefined_set_id) for item in items])
        return items

    def save(self, backend: str, bundle: dict) -> None:
        identity = self.catalog_id(backend)
        if identity is None or not isinstance(bundle, dict) or bundle.get("catalog_id") != identity:
            raise ValueError("The database catalog changed. Refresh sets before downloading.")
        config = DATASETS.get(bundle.get("dataset_name"))
        if config is None or bundle.get("is_active") is not True:
            raise ValueError("This set is inactive or its dataset is unsupported.")
        load_predefined_data(config, bundle["na_fraction"], bundle)
        with self.connection() as conn:
            conn.execute("""INSERT INTO predefined_downloads VALUES (?, ?, ?, ?, ?, 1)
                ON CONFLICT(backend_key, catalog_id, set_id) DO UPDATE SET
                bundle_json=excluded.bundle_json, downloaded_at=excluded.downloaded_at, available=1""",
                (self.key(backend), bundle["catalog_id"], bundle["predefined_set_id"], json.dumps(bundle, allow_nan=False),
                 datetime.now(timezone.utc).isoformat()))

    def downloaded(self, backend: str) -> tuple[CatalogSet, ...]:
        with self.connection() as conn:
            rows = conn.execute("""SELECT d.bundle_json FROM predefined_downloads d
                JOIN predefined_cache_sources s ON s.backend_key=d.backend_key AND s.catalog_id=d.catalog_id
                WHERE d.backend_key=? AND d.available=1 ORDER BY d.set_id""", (self.key(backend),)).fetchall()
        items = []
        for row in rows:
            try:
                items.extend(parse_set_catalog([json.loads(row[0])]))
            except (ValueError, TypeError):
                continue
        return tuple(items)

    def get(self, backend: str, set_id: int) -> dict | None:
        with self.connection() as conn:
            row = conn.execute("""SELECT d.bundle_json FROM predefined_downloads d
                JOIN predefined_cache_sources s ON s.backend_key=d.backend_key AND s.catalog_id=d.catalog_id
                WHERE d.backend_key=? AND d.set_id=? AND d.available=1""", (self.key(backend), set_id)).fetchone()
        if row is None:
            return None
        bundle = json.loads(row[0])
        config = DATASETS.get(bundle.get("dataset_name"))
        if config is None or bundle.get("predefined_set_id") != set_id or bundle.get("catalog_id") != self.catalog_id(backend):
            raise ValueError("Downloaded set is invalid. Download it again when connected.")
        load_predefined_data(config, bundle["na_fraction"], bundle)
        return bundle

    def unavailable(self, backend: str, set_id: int) -> None:
        with self.connection() as conn:
            conn.execute("UPDATE predefined_downloads SET available=0 WHERE backend_key=? AND set_id=?", (self.key(backend), set_id))
