"""Unsaved preview rules, API metadata and navigation permissions."""

import asyncio
from unittest.mock import MagicMock

import httpx
import pytest

from dahlia.app.controller import AppController
from dahlia.core.api_client import ApiClient
from dahlia.services.local_storage import LocalStorage
from dahlia.services.predefined_sets import (
    CatalogDataset, PredefinedDraft, can_manage_predefined_sets, parse_dataset_catalog,
)


@pytest.fixture
def draft():
    form = PredefinedDraft()
    form.select_dataset(CatalogDataset(1, "iris", 150))
    form.select_fraction(0.2)
    form.set_removed_text(", ".join(map(str, range(30))))
    return form


def test_manual_order_is_preserved_and_removed_points_are_sorted(draft):
    draft.set_removed_text(", ".join(map(str, range(29, -1, -1))))
    draft.set_annotation_text(", ".join(map(str, range(14, -1, -1))))
    preview = draft.prepare_preview()
    assert preview.removed_indices == tuple(range(30))
    assert preview.annotation_indices == tuple(range(14, -1, -1))


@pytest.mark.parametrize("blank", ["", "  \n\t "])
def test_blank_field_draws_once_and_fills_visible_order(draft, monkeypatch, blank):
    sample = MagicMock(return_value=list(range(14, -1, -1)))
    monkeypatch.setattr("dahlia.services.predefined_sets.random.SystemRandom.sample", sample)
    draft.set_annotation_text(blank)
    first = draft.prepare_preview()
    assert first.annotation_indices == tuple(range(14, -1, -1))
    assert draft.annotation_text == ", ".join(map(str, range(14, -1, -1)))
    assert draft.prepare_preview() == first
    sample.assert_called_once_with(list(range(30)), 15)


def test_random_draw_is_a_unique_ordered_subset(draft):
    result = draft.prepare_preview()
    assert len(result.annotation_indices) == len(set(result.annotation_indices)) == 15
    assert set(result.annotation_indices).issubset(result.removed_indices)


@pytest.mark.parametrize("value", [
    "0,1,2,3,4,5,6", "0,1,", ",", "0,1.0", "0,a", "0,,1",
    ",".join(["0"] * 15), ",".join(map(str, range(14))) + ",30",
    ",".join(map(str, range(14))) + ",150",
])
def test_nonempty_bad_second_field_is_never_filled(draft, monkeypatch, value):
    sample = MagicMock()
    monkeypatch.setattr("dahlia.services.predefined_sets.random.SystemRandom.sample", sample)
    draft.set_annotation_text(value)
    with pytest.raises(ValueError):
        draft.prepare_preview()
    sample.assert_not_called()
    assert draft.annotation_text == value
    assert draft.preview is None


@pytest.mark.parametrize("value", ["", "0,1", "0,1,", ",".join(["0"] * 30),
                                   ",".join(map(str, range(29))) + ",-1",
                                   ",".join(map(str, range(29))) + ",150"])
def test_invalid_removed_points_are_rejected(draft, value):
    draft.set_removed_text(value)
    with pytest.raises(ValueError):
        draft.prepare_preview()
    assert draft.annotation_text == ""


@pytest.mark.parametrize("change", ["dataset", "fraction"])
def test_configuration_change_clears_both_lists_and_preview(draft, change):
    draft.prepare_preview()
    if change == "dataset":
        draft.select_dataset(CatalogDataset(2, "alloys", 400))
        assert draft.missing_count == 80
    else:
        draft.select_fraction(0.3)
        assert draft.missing_count == 45
    assert draft.removed_text == draft.annotation_text == ""
    assert draft.preview is None


@pytest.mark.parametrize("field", ["removed", "annotation"])
def test_editing_either_field_invalidates_preview(draft, field):
    draft.prepare_preview()
    if field == "removed":
        draft.set_removed_text("0,1")
    else:
        draft.set_annotation_text("0,1")
    assert draft.preview is None


def test_small_dataset_and_missing_selection_are_rejected():
    form = PredefinedDraft()
    with pytest.raises(ValueError, match="Select a dataset"):
        form.prepare_preview()
    form.select_dataset(CatalogDataset(2, "small", 40))
    form.select_fraction(0.3)
    assert form.missing_count == 12
    with pytest.raises(ValueError, match="fewer than 15"):
        form.prepare_preview()


def test_count_truncates_and_positions_include_zero_and_last_row(draft):
    draft.select_dataset(CatalogDataset(2, "other", 159))
    draft.select_fraction(0.1)
    assert draft.missing_count == 15
    draft.set_removed_text(",".join(map(str, [*range(14), 158])))
    result = draft.prepare_preview()
    assert set(result.annotation_indices) == {*range(14), 158}


def test_catalog_accepts_central_datasets_beyond_local_iris():
    datasets = parse_dataset_catalog([
        {"dataset_id": 1, "name": "iris", "row_count": 150},
        {"dataset_id": 7, "name": "alloys", "row_count": 400},
    ])
    assert datasets[1] == CatalogDataset(7, "alloys", 400)
    assert parse_dataset_catalog([]) == ()


@pytest.mark.parametrize("data", [None, {}, [None],
    [{"dataset_id": True, "name": "iris", "row_count": 150}],
    [{"dataset_id": 1, "name": "iris", "row_count": 0}],
    [{"dataset_id": 1, "name": "", "row_count": 150}],
    [{"dataset_id": 1, "name": "iris", "row_count": 150}] * 2,
])
def test_invalid_catalog_is_rejected(data):
    with pytest.raises(ValueError):
        parse_dataset_catalog(data)


@pytest.mark.parametrize("user,allowed", [
    (None, False), ({"role": "USER", "is_email_verified": True}, False),
    ({"role": "USER_PLUS", "is_email_verified": True}, False),
    ({"role": "RESEARCHER", "is_email_verified": False}, False),
    ({"role": "DEVELOPER"}, False),
    ({"role": "RESEARCHER", "is_email_verified": True, "is_active": False}, False),
    ({"role": "RESEARCHER", "is_email_verified": True}, True),
    ({"role": "DEVELOPER", "is_email_verified": True}, True),
])
def test_navigation_permissions(user, allowed):
    assert can_manage_predefined_sets(user) is allowed


def test_controller_navigation_is_guarded(monkeypatch):
    controller = AppController(MagicMock(), storage=LocalStorage(":memory:"))
    controller.show_profile = MagicMock()
    controller._clear = MagicMock()
    controller._set_exit_guard = MagicMock()
    render = MagicMock()
    monkeypatch.setattr("dahlia.app.controller.render_predefined_sets", render)
    controller.show_predefined_sets()
    controller.show_profile.assert_called_once()
    render.assert_not_called()
    controller.current_user = {"role": "RESEARCHER", "is_email_verified": True}
    controller.show_predefined_sets()
    assert controller.active_screen == "predefined_sets"
    render.assert_called_once_with(controller)


def test_catalog_request_uses_existing_authenticated_api_session():
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json=[{"dataset_id": 1, "name": "iris", "row_count": 150}])

    client = ApiClient(transport=httpx.MockTransport(handle))
    assert asyncio.run(client.list_active_datasets()).status_code == 401
    assert not requests
    client.access_token = "session-token"
    result = asyncio.run(client.list_active_datasets())
    assert result.success
    assert requests[0].url.path == "/api/v1/datasets"
    assert requests[0].headers["authorization"] == "Bearer session-token"
