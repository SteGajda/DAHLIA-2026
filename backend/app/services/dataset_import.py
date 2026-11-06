"""Developer import of the two reviewed, immutable industrial CSV datasets."""

import csv
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import io
import json
import math
from pathlib import Path

from sqlalchemy import select, true
from sqlalchemy.orm import Session

from app.models.experiment import Dataset
from app.models.user import AppUser


@dataclass(frozen=True)
class ImportPreset:
    name: str
    row_count: int
    sha256: str
    imputed_column: str
    target_column: str
    precision: str
    reference_columns: tuple[str, ...]
    categorical_columns: tuple[str, ...]
    # Method parameters stay in the desktop DatasetConfig; not database columns.
    number_of_clusters: int
    knn_number_of_neighbors: int


PRESETS = (
    ImportPreset("wola", 926, "9c308a7b591bfbcbe85f672980970431388cb76fd432ab2451a0548b0ee11b85",
        "[Mg %]", "[LABELS]", "0.001", ("[Mn %]", "[C %]", "[Si %]", "[Cr %]", "[Ni %]", "[Cu %]"), (), 3, 5),
    ImportPreset("stamp_type", 462, "f05bda71764f660f68bae3f45ca8806d34bf8424bc07c77d0d766084079a5f45",
        "MEANS OF AMPLITUDE", "LABEL", "0.01", ("MEANS OF AVE. FREQ.", "TOTAL AE ENERGY", "No. OF COUNTS", "No. OF HITS", "TOTAL TRUE ENERGY", "MEANS OF RISE FREQ."),
        ("VENDOR", "STAMP TYPE"), 11, 3),
)


def prepare_imports(data_dir: Path) -> list[dict]:
    """Read exact bytes and validate positions, columns and finite model inputs."""
    result = []
    for preset in PRESETS:
        path = data_dir / f"{preset.name}.csv"
        content = path.read_bytes()
        digest = hashlib.sha256(content).digest()
        if digest.hex() != preset.sha256:
            raise ValueError(f"{path.name}: SHA-256 differs from the reviewed CSV; nothing was imported.")
        reader = csv.reader(io.StringIO(content.decode("utf-8-sig"), newline=""))
        header = next(reader)
        rows = list(reader)
        required = {preset.imputed_column, preset.target_column, *preset.reference_columns, *preset.categorical_columns}
        if len(set(header)) != len(header) or not required.issubset(header):
            raise ValueError(f"{path.name}: missing or duplicate columns.")
        if len(rows) != preset.row_count or any(len(row) != len(header) for row in rows):
            raise ValueError(f"{path.name}: unexpected row count or malformed CSV rows.")
        numeric_positions = [header.index(name) for name in (preset.imputed_column, *preset.reference_columns)]
        try:
            if any(not math.isfinite(float(row[position])) for row in rows for position in numeric_positions):
                raise ValueError("Nonfinite values")
        except ValueError as exc:
            raise ValueError(f"{path.name}: model columns must contain finite numbers without missing values.") from exc
        result.append(dict(
            name=preset.name, csv_file_name=path.name, csv_file=content, csv_sha256=digest,
            row_count=preset.row_count, imputed_column=preset.imputed_column,
            target_column=preset.target_column, reference_columns_json=json.dumps(preset.reference_columns),
            categorical_columns_json=json.dumps(preset.categorical_columns), precision_value=Decimal(preset.precision),
        ))
    return result


def import_datasets(db: Session, data_dir: Path, *, author_id: int | None = None, apply: bool = False) -> list[dict]:
    """Plan or atomically insert; existing datasets are never edited or reactivated."""
    try:
        prepared = prepare_imports(data_dir)
        eligible = db.scalars(select(AppUser).where(AppUser.role_code == "DEVELOPER",
            AppUser.is_active == true(), AppUser.is_email_verified == true()).order_by(AppUser.user_id)).all()
        if author_id is None:
            if len(eligible) != 1:
                ids = ", ".join(str(user.user_id) for user in eligible) or "none"
                raise ValueError(f"Specify --author-id for an active verified DEVELOPER. Eligible IDs: {ids}.")
            author_id = eligible[0].user_id
        if author_id not in {user.user_id for user in eligible}:
            raise ValueError("The author must be an active verified DEVELOPER.")
        plan = []
        pending = []
        for values in prepared:
            existing = db.scalar(select(Dataset).where(Dataset.name == values["name"]))
            if existing is not None:
                same = all(getattr(existing, key) == value for key, value in values.items()
                           if key not in {"reference_columns_json", "categorical_columns_json", "csv_file_name"})
                same = same and all(json.loads(getattr(existing, key)) == json.loads(values[key])
                                   for key in ("reference_columns_json", "categorical_columns_json"))
                if not same:
                    raise ValueError(f"Dataset '{existing.name}' exists with different content/configuration. Nothing was overwritten; use a new dataset name for a new version.")
                plan.append(dict(name=existing.name, row_count=existing.row_count, dataset_id=existing.dataset_id,
                                 status="unchanged" if existing.is_active else "unchanged (inactive)", created_by=existing.created_by))
            else:
                model = Dataset(**values, created_by=author_id, is_active=True)
                pending.append(model)
                plan.append(dict(name=model.name, row_count=model.row_count, dataset_id=None,
                                 status="created" if apply else "would create", created_by=author_id))
        if apply:
            db.add_all(pending)
            db.flush()
            ids = {model.name: model.dataset_id for model in pending}
            for item in plan:
                if item["name"] in ids:
                    item["dataset_id"] = ids[item["name"]]
            db.commit()
        else:
            db.rollback()
        return plan
    except Exception:
        db.rollback()
        raise
