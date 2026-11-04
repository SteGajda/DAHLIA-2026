"""Pure validation of complete predefined set definitions.

No database access, random selection or CSV parsing happens here. The caller
must obtain row_count from the selected central dataset. An empty annotation
field must be resolved during preview before calling this validator.
"""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ValidatedPredefinedPoints:
    """Validated row positions; annotation_indices preserves presentation order."""

    removed_indices: tuple[int, ...]
    annotation_indices: tuple[int, ...]


def _validate_indices(name: str, values: list[int] | tuple[int, ...],
                      row_count: int) -> tuple[int, ...]:
    if not isinstance(values, (list, tuple)):
        raise ValueError(f"{name} must be a list or tuple of integers.")
    for index in values:
        # bool is a subclass of int and must be rejected explicitly.
        if isinstance(index, bool) or not isinstance(index, int):
            raise ValueError(f"{name} must contain integers only.")
        if not 0 <= index < row_count:
            raise ValueError(f"{name} indices must be between 0 and {row_count - 1}.")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must not contain duplicates.")
    return tuple(values)


def validate_predefined_points(
    *,
    row_count: int,
    na_fraction: float | Decimal,
    removed_indices: list[int] | tuple[int, ...],
    annotation_indices: list[int] | tuple[int, ...],
) -> ValidatedPredefinedPoints:
    """Validate a final definition, raising ValueError for invalid input.

    Counts use int(row_count * float(na_fraction)), matching ExperimentSampler.
    Strings and implicit integer conversions are deliberately not accepted.
    The input collections are never changed and no points are generated.
    """
    if (isinstance(row_count, bool) or not isinstance(row_count, int)
            or row_count <= 0):
        raise ValueError("row_count must be a positive integer.")
    if (not isinstance(na_fraction, (float, Decimal))
            or Decimal(str(na_fraction)) not in
            (Decimal("0.1"), Decimal("0.2"), Decimal("0.3"))):
        raise ValueError("na_fraction must be 0.1, 0.2 or 0.3.")

    expected_count = int(row_count * float(na_fraction))
    if expected_count < 15:
        raise ValueError("The selected fraction must produce at least 15 missing points.")

    removed = _validate_indices("removed_indices", removed_indices, row_count)
    annotations = _validate_indices("annotation_indices", annotation_indices, row_count)
    if len(removed) != expected_count:
        raise ValueError(f"removed_indices must contain exactly {expected_count} indices.")
    if len(annotations) != 15:
        raise ValueError("annotation_indices must contain exactly 15 indices.")
    if not set(annotations).issubset(removed):
        raise ValueError("All annotation_indices must belong to removed_indices.")

    return ValidatedPredefinedPoints(removed, annotations)
