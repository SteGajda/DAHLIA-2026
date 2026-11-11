"""Static configuration for the DAHLIA 1.1 desktop proof of concept."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

MAX_SEED = 2**32 - 1
TOTAL_STEPS = 15
APP_VERSION = "1.2.0"
METHOD_ORDER = (
    "Annotator",
    "Mean",
    "Cluster Mean",
    "KNN",
    "Cluster KNN",
    "Random Forest",
    "MICE",
)


@dataclass(frozen=True, slots=True)
class DatasetConfig:
    """Dataset-specific constants that are not editable by the annotator."""

    name: str
    path: Path
    precision: float
    incomplete_column: str
    target_column: str
    number_of_clusters: int
    knn_number_of_neighbors: int
    reference_columns: tuple[str, ...]
    categorical_columns: tuple[str, ...]

    @property
    def numeric_model_columns(self) -> tuple[str, ...]:
        return (self.incomplete_column, *self.reference_columns)


IRIS_CONFIG = DatasetConfig(
    name="iris",
    path=Path("data/iris.csv"),
    precision=0.1,
    incomplete_column="SepalLengthCm",
    target_column="Species",
    number_of_clusters=3,
    knn_number_of_neighbors=5,
    reference_columns=("SepalWidthCm", "PetalLengthCm", "PetalWidthCm"),
    categorical_columns=("Species",),
)

WOLA_CONFIG = DatasetConfig(
    name="wola", path=Path("data/wola.csv"), precision=0.001,
    incomplete_column="[Mg %]", target_column="[LABELS]",
    number_of_clusters=3, knn_number_of_neighbors=5,
    reference_columns=("[Mn %]", "[C %]", "[Si %]", "[Cr %]", "[Ni %]", "[Cu %]"),
    categorical_columns=(),
)

STAMP_TYPE_CONFIG = DatasetConfig(
    name="stamp_type", path=Path("data/stamp_type.csv"), precision=0.01,
    incomplete_column="MEANS OF AMPLITUDE", target_column="LABEL",
    number_of_clusters=11, knn_number_of_neighbors=3,
    reference_columns=("MEANS OF AVE. FREQ.", "TOTAL AE ENERGY", "No. OF COUNTS", "No. OF HITS", "TOTAL TRUE ENERGY", "MEANS OF RISE FREQ."),
    categorical_columns=("VENDOR", "STAMP TYPE"),
)

DATASETS = {config.name: config for config in (IRIS_CONFIG, WOLA_CONFIG, STAMP_TYPE_CONFIG)}
NA_FRACTIONS = (0.1, 0.2, 0.3)
PROJECTIONS = ("tsne", "pca", "umap")
