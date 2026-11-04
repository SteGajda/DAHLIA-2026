"""Validation contract tests; runnable with unittest or the existing pytest suite."""

from decimal import Decimal
import unittest

from app.services.predefined_sets import validate_predefined_points


class PredefinedPointsTests(unittest.TestCase):
    def valid_input(self):
        return dict(row_count=150, na_fraction=0.2,
                    removed_indices=list(range(30)),
                    annotation_indices=list(range(14, -1, -1)))

    def test_preserves_manual_order_and_copies_input(self):
        data = self.valid_input()
        data["removed_indices"].reverse()
        result = validate_predefined_points(**data)
        self.assertEqual(result.annotation_indices, tuple(range(14, -1, -1)))
        self.assertEqual(result.removed_indices, tuple(range(29, -1, -1)))
        self.assertEqual(data["removed_indices"], list(range(29, -1, -1)))
        data["annotation_indices"].clear()
        self.assertEqual(len(result.annotation_indices), 15)

    def test_supported_fractions_and_database_decimal(self):
        for fraction in (0.1, 0.2, 0.3, Decimal("0.200000")):
            with self.subTest(fraction=fraction):
                data = self.valid_input()
                data.update(na_fraction=fraction,
                            removed_indices=list(range(int(150 * float(fraction)))))
                self.assertEqual(len(validate_predefined_points(**data).annotation_indices), 15)

    def test_uses_sampler_truncation(self):
        data = self.valid_input()
        data.update(row_count=159, na_fraction=0.1, removed_indices=list(range(15)))
        self.assertEqual(len(validate_predefined_points(**data).removed_indices), 15)

    def test_accepts_zero_and_last_row(self):
        data = self.valid_input()
        data["removed_indices"][-1] = 149
        data["annotation_indices"][0] = 149
        result = validate_predefined_points(**data)
        self.assertIn(0, result.annotation_indices)
        self.assertIn(149, result.annotation_indices)

    def test_accepts_tuple_inputs(self):
        data = self.valid_input()
        for name in ("removed_indices", "annotation_indices"):
            data[name] = tuple(data[name])
        self.assertEqual(len(validate_predefined_points(**data).removed_indices), 30)

    def test_rejects_invalid_row_count(self):
        for value in (0, -1, True, 150.0, "150", None):
            with self.subTest(value=value):
                data = self.valid_input()
                data["row_count"] = value
                with self.assertRaisesRegex(ValueError, "row_count"):
                    validate_predefined_points(**data)

    def test_rejects_unsupported_fraction(self):
        for value in (0.15, 0.0, 1.0, True, "0.2", None,
                      float("nan"), float("inf"), Decimal("NaN")):
            with self.subTest(value=value):
                data = self.valid_input()
                data["na_fraction"] = value
                with self.assertRaisesRegex(ValueError, "na_fraction"):
                    validate_predefined_points(**data)

    def test_rejects_fewer_than_fifteen_missing_points(self):
        data = self.valid_input()
        data.update(row_count=149, na_fraction=0.1,
                    removed_indices=list(range(14)))
        with self.assertRaisesRegex(ValueError, "at least 15"):
            validate_predefined_points(**data)

    def test_requires_exact_removed_count(self):
        for count in (0, 15, 29, 31):
            with self.subTest(count=count):
                data = self.valid_input()
                data["removed_indices"] = list(range(count))
                with self.assertRaisesRegex(ValueError, "exactly 30"):
                    validate_predefined_points(**data)

    def test_empty_or_partial_annotations_are_not_filled_automatically(self):
        for count in (0, 7, 14, 16):
            with self.subTest(count=count):
                data = self.valid_input()
                data["annotation_indices"] = list(range(count))
                with self.assertRaisesRegex(ValueError, "exactly 15"):
                    validate_predefined_points(**data)

    def test_rejects_duplicates_in_either_list(self):
        for name in ("removed_indices", "annotation_indices"):
            with self.subTest(name=name):
                data = self.valid_input()
                data[name][-1] = data[name][0]
                with self.assertRaisesRegex(ValueError, "duplicates"):
                    validate_predefined_points(**data)

    def test_rejects_non_integer_indices_in_either_list(self):
        for name in ("removed_indices", "annotation_indices"):
            for value in (True, False, 1.0, "1", None):
                with self.subTest(name=name, value=value):
                    data = self.valid_input()
                    data[name][0] = value
                    with self.assertRaisesRegex(ValueError, "integers only"):
                        validate_predefined_points(**data)

    def test_rejects_out_of_range_indices_in_either_list(self):
        for name in ("removed_indices", "annotation_indices"):
            for value in (-1, 150):
                with self.subTest(name=name, value=value):
                    data = self.valid_input()
                    data[name][0] = value
                    with self.assertRaisesRegex(ValueError, "between 0 and 149"):
                        validate_predefined_points(**data)

    def test_requires_annotations_to_be_removed(self):
        data = self.valid_input()
        data["annotation_indices"][0] = 30
        with self.assertRaisesRegex(ValueError, "belong to removed_indices"):
            validate_predefined_points(**data)

    def test_rejects_unparsed_text_and_missing_lists(self):
        for name in ("removed_indices", "annotation_indices"):
            for value in ("0,1,2", "", None, {0, 1, 2}):
                with self.subTest(name=name, value=value):
                    data = self.valid_input()
                    data[name] = value
                    with self.assertRaisesRegex(ValueError, "list or tuple"):
                        validate_predefined_points(**data)


if __name__ == "__main__":
    unittest.main()
