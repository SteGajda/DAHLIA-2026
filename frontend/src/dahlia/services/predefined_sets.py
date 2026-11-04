"""In-memory authoring draft and validation for predefined set previews."""

from dataclasses import dataclass
import random
import re
from typing import Any

import pandas as pd

from dahlia.datasets import ExperimentSampler
from .config import MAX_SEED, NA_FRACTIONS, TOTAL_STEPS


def can_manage_predefined_sets(user: dict | None) -> bool:
    """UI visibility gate; the backend remains authoritative for permissions."""
    return bool(user and user.get("role") in {"RESEARCHER", "DEVELOPER"}
                and user.get("is_email_verified") is True
                and user.get("is_active", True) is True)


@dataclass(frozen=True, slots=True)
class CatalogDataset:
    dataset_id: int
    name: str
    row_count: int


def parse_dataset_catalog(data: Any) -> tuple[CatalogDataset, ...]:
    """Accept central metadata rather than the frontend's local DATASETS map."""
    if not isinstance(data, list):
        raise ValueError("The server returned an invalid dataset catalog.")
    result = []
    seen = set()
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("The server returned an invalid dataset catalog.")
        dataset_id, count, name = item.get("dataset_id"), item.get("row_count"), item.get("name")
        if (type(dataset_id) is not int or dataset_id <= 0 or dataset_id in seen
                or type(count) is not int or count <= 0
                or not isinstance(name, str) or not name.strip()):
            raise ValueError("The server returned an invalid dataset catalog.")
        seen.add(dataset_id)
        result.append(CatalogDataset(dataset_id, name, count))
    return tuple(result)


def _indices(text: str, label: str, row_count: int) -> tuple[int, ...]:
    tokens = text.strip().split(",")
    if any(not re.fullmatch(r"[+-]?[0-9]+", token.strip()) for token in tokens):
        raise ValueError(f"{label}: enter integer indices separated by commas.")
    values = tuple(int(token.strip()) for token in tokens)
    if any(index < 0 or index >= row_count for index in values):
        raise ValueError(f"{label}: indices must be between 0 and {row_count - 1}.")
    if len(values) != len(set(values)):
        raise ValueError(f"{label}: duplicate indices are not allowed.")
    return values


@dataclass(frozen=True, slots=True)
class PredefinedPreview:
    dataset: CatalogDataset
    na_fraction: float
    removed_indices: tuple[int, ...]
    annotation_indices: tuple[int, ...]

    def to_payload(self) -> dict:
        """Copy the approved definition; generation seed is not part of a set."""
        return {
            "dataset_id": self.dataset.dataset_id,
            "na_fraction": self.na_fraction,
            "removed_indices": list(self.removed_indices),
            "annotation_indices": list(self.annotation_indices),
        }


class PredefinedDraft:
    """An unsaved form; configuration/input changes invalidate its preview."""

    def __init__(self) -> None:
        self.dataset: CatalogDataset | None = None
        self.na_fraction = 0.1
        self.removed_text = ""
        self.annotation_text = ""
        self.preview: PredefinedPreview | None = None

    @property
    def missing_count(self) -> int:
        return int(self.dataset.row_count * self.na_fraction) if self.dataset else 0

    def select_dataset(self, dataset: CatalogDataset | None) -> None:
        if dataset != self.dataset:
            self.dataset = dataset
            self.clear_points()

    def select_fraction(self, fraction: float) -> None:
        if fraction not in NA_FRACTIONS:
            raise ValueError("NA fraction must be 0.1, 0.2 or 0.3.")
        if fraction != self.na_fraction:
            self.na_fraction = fraction
            self.clear_points()

    def clear_points(self) -> None:
        self.removed_text = ""
        self.annotation_text = ""
        self.preview = None

    def set_removed_text(self, value: str) -> None:
        self.removed_text = value
        self.preview = None

    def set_annotation_text(self, value: str) -> None:
        self.annotation_text = value
        self.preview = None

    def generate_from_seed(self, raw_seed: str) -> None:
        """Use the existing sampler on the central dataset's zero-based positions."""
        if self.dataset is None:
            raise ValueError("Select a dataset.")
        if self.missing_count < TOTAL_STEPS:
            raise ValueError("This fraction produces fewer than 15 missing points.")
        text = raw_seed.strip()
        if not re.fullmatch(r"[0-9]+", text) or int(text) > MAX_SEED:
            raise ValueError(f"Seed must be an integer between 0 and {MAX_SEED}.")
        # ExperimentSampler uses only df.index and len(df); no CSV values or
        # local DatasetConfig are needed, so every central dataset is supported.
        frame = pd.DataFrame(index=pd.RangeIndex(self.dataset.row_count))
        removed, annotations = ExperimentSampler(int(text)).select_experiment_points(
            frame, na_fraction=self.na_fraction, n_imputation_steps=TOTAL_STEPS,
        )
        self.removed_text = ", ".join(str(int(index)) for index in removed)
        self.annotation_text = ", ".join(str(int(index)) for index in annotations)
        self.preview = None

    def prepare_preview(self) -> PredefinedPreview:
        self.preview = None
        if self.dataset is None:
            raise ValueError("Select a dataset.")
        if self.missing_count < TOTAL_STEPS:
            raise ValueError("This fraction produces fewer than 15 missing points.")
        removed = _indices(self.removed_text, "Removed points", self.dataset.row_count)
        if len(removed) != self.missing_count:
            raise ValueError(f"Removed points: enter exactly {self.missing_count} indices.")
        automatic = not self.annotation_text.strip()
        if automatic:
            # OS entropy, independent of the optional seeded experiment sampler.
            annotations = tuple(random.SystemRandom().sample(sorted(removed), TOTAL_STEPS))
        else:
            annotations = _indices(self.annotation_text, "Evaluation points", self.dataset.row_count)
            if len(annotations) != TOTAL_STEPS:
                raise ValueError("Evaluation points: enter exactly 15 indices or leave the field empty.")
            if not set(annotations).issubset(removed):
                raise ValueError("Every evaluation point must belong to the removed points.")
        if automatic:
            # Filling the field makes repeated previews preserve the same order.
            self.annotation_text = ", ".join(map(str, annotations))
        self.preview = PredefinedPreview(self.dataset, self.na_fraction, tuple(sorted(removed)), annotations)
        return self.preview
