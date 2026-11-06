"""Stored definitions load atomically, preserve order, and save as new sets."""

import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from nicegui import app, ui
from nicegui.testing.general import prepare_simulation
from nicegui.testing.user import User

from dahlia.app.screens.predefined_sets import render_predefined_sets
from dahlia.core.api_client import ApiClient, ApiResult
from dahlia.services.predefined_sets import CatalogDataset, PredefinedDraft, parse_set_catalog


DATASETS = {1: CatalogDataset(1, "iris", 150), 2: CatalogDataset(2, "central", 200)}
ORDER = [29, 1, 27, 3, 25, 5, 23, 7, 21, 9, 19, 11, 17, 13, 15]
DEFINITION = dict(predefined_set_id=8, dataset_id=1, na_fraction=0.2,
                  removed_indices=list(range(30)), annotation_indices=ORDER, is_active=False)
SUMMARY = dict(predefined_set_id=8, dataset_id=1, dataset_name="iris", na_fraction=0.2, is_active=False)


def test_load_preserves_saved_order_without_sampling_and_requires_preview():
    draft = PredefinedDraft()
    draft.select_dataset(DATASETS[2])
    draft.generate_from_seed("42")
    with patch("dahlia.services.predefined_sets.random.SystemRandom", side_effect=AssertionError("Must not sample")):
        draft.load_definition(deepcopy(DEFINITION), DATASETS, expected_id=8)
        assert draft.preview is None
        preview = draft.prepare_preview()
    assert preview.annotation_indices == tuple(ORDER)
    assert preview.to_payload() == dict(dataset_id=1, na_fraction=0.2,
        removed_indices=list(range(30)), annotation_indices=ORDER)
    assert "predefined_set_id" not in preview.to_payload()


@pytest.mark.parametrize("changes", [
    {"predefined_set_id": 9}, {"predefined_set_id": True}, {"dataset_id": 99},
    {"dataset_id": True}, {"na_fraction": True}, {"na_fraction": "0.2"},
    {"annotation_indices": []}, {"annotation_indices": ORDER[:7]},
    {"annotation_indices": [1] * 15}, {"annotation_indices": [149] + ORDER[1:]},
    {"annotation_indices": [True] + ORDER[1:]}, {"removed_indices": list(range(29))},
    {"removed_indices": list(range(29)) + [150]}, {"removed_indices": [1] * 30},
])
def test_invalid_or_unavailable_definition_does_not_replace_draft(changes):
    draft = PredefinedDraft()
    draft.select_dataset(DATASETS[2])
    draft.generate_from_seed("4")
    before = draft.prepare_preview()
    text = draft.removed_text, draft.annotation_text
    with pytest.raises(ValueError):
        draft.load_definition({**DEFINITION, **changes}, DATASETS, expected_id=8)
    assert draft.preview == before
    assert (draft.removed_text, draft.annotation_text) == text


def test_catalog_includes_inactive_sets_and_rejects_duplicate_ids():
    assert parse_set_catalog([SUMMARY])[0].is_active is False
    with pytest.raises(ValueError):
        parse_set_catalog([SUMMARY, SUMMARY])


def test_catalog_and_detail_use_authenticated_get():
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(200, json=DEFINITION if request.url.path.endswith("/8") else [SUMMARY])
    client = ApiClient(transport=httpx.MockTransport(handle))
    assert asyncio.run(client.list_predefined_sets()).status_code == 401
    assert asyncio.run(client.get_predefined_set(8)).status_code == 401
    assert not requests
    client.access_token = "test-session"
    assert asyncio.run(client.list_predefined_sets()).success
    assert asyncio.run(client.get_predefined_set(8)).data == DEFINITION
    assert [r.url.path for r in requests] == ["/api/v1/predefined-sets", "/api/v1/predefined-sets/8"]
    assert all(r.method == "GET" and r.headers["authorization"] == "Bearer test-session" for r in requests)


def test_deactivation_uses_authenticated_post_without_retry():
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(403, json={"detail": "Permission denied"})
    client = ApiClient(transport=httpx.MockTransport(handle))
    assert asyncio.run(client.deactivate_predefined_set(8)).status_code == 401
    assert not requests
    client.access_token = "test-session"
    result = asyncio.run(client.deactivate_predefined_set(8))
    assert result.status_code == 403
    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert requests[0].url.path == "/api/v1/predefined-sets/8/deactivate"
    assert requests[0].headers["authorization"] == "Bearer test-session"


@asynccontextmanager
async def simulation(root):
    prepare_simulation()
    ui.page("/")(root)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
            yield User(client)


def test_screen_load_save_copy_and_failure_preserves_form():
    async def scenario():
        pending = asyncio.Future()
        api = SimpleNamespace(
            base_url="http://test",
            list_active_datasets=AsyncMock(return_value=ApiResult(success=True, data=[
                dict(dataset_id=item.dataset_id, name=item.name, row_count=item.row_count) for item in DATASETS.values()])),
            list_predefined_sets=AsyncMock(return_value=ApiResult(success=True, data=[SUMMARY])),
            get_predefined_set=AsyncMock(side_effect=lambda _: pending),
            create_predefined_set=AsyncMock(return_value=ApiResult(success=True, data={"predefined_set_id": 9})),
            deactivate_predefined_set=AsyncMock(),
        )
        # AsyncMock does not await a Future returned by a synchronous side effect.
        async def read(_):
            return await pending
        api.get_predefined_set.side_effect = read
        controller = SimpleNamespace(current_user=dict(user_id=1, role="RESEARCHER", is_email_verified=True),
            active_screen="predefined_sets", is_online=True, api_client=api, predefined_cache=Mock(),
            show_setup=lambda **kwargs: None, show_my_results=lambda: None,
            show_predefined_sets=lambda: None, show_profile=lambda: None, _update_status_badge=lambda: None)
        async with simulation(lambda: render_predefined_sets(controller)) as user:
            await user.open("/")
            await user.should_see("Choose a dataset and prepare the point lists.")
            assert api.list_predefined_sets.await_count == 0
            browser = next(e for e in user.client.elements.values() if isinstance(e, ui.dialog))
            assert browser.value is False
            user.find("Browse saved sets").click()
            await user.should_see("Select a set to load its saved point lists.")
            def field(kind, label):
                return next(e for e in user.client.elements.values() if isinstance(e, kind) and e.props.get("label") == label)
            dataset = field(ui.select, "Dataset")
            fraction = field(ui.select, "NA fraction")
            removed = field(ui.textarea, "All removed row indices")
            annotations = field(ui.textarea, "Evaluation row indices (optional)")
            with user:
                dataset.value = 2
            user.find("Load to edit").click()
            user.find("Load to edit").click()
            await user.should_see("Loading Set #8...")
            assert api.get_predefined_set.await_count == 1
            assert not dataset.enabled
            pending.set_result(ApiResult(success=True, data=deepcopy(DEFINITION)))
            await user.should_see("Loaded from Set #8. Saving will create a new set; Set #8 will stay unchanged.")
            assert dataset.value == 1 and fraction.value == 0.2
            assert list(map(int, annotations.value.split(","))) == ORDER
            await user.should_not_see("Save set")
            assert browser.value is False
            user.find("Prepare preview").click()
            api.create_predefined_set.return_value = ApiResult(success=False, status_code=409,
                error="An identical active set already exists: Set #8.")
            before = removed.value, annotations.value
            user.find("Save set").click()
            await user.should_see("An identical active set already exists: Set #8.")
            assert (removed.value, annotations.value) == before
            assert next(iter(user.find("Save set").elements)).enabled
            api.create_predefined_set.return_value = ApiResult(success=True, data={"predefined_set_id": 9})
            user.find("Save set").click()
            await user.should_see("Set #9 saved and active.")
            payload = api.create_predefined_set.call_args.args[0]
            assert payload == dict(dataset_id=1, na_fraction=0.2, removed_indices=list(range(30)), annotation_indices=ORDER)
            # Reloading the source permits another copy, even with identical points.
            api.get_predefined_set.side_effect = None
            api.get_predefined_set.return_value = ApiResult(success=True, data=deepcopy(DEFINITION))
            user.find("Browse saved sets").click()
            await user.should_see("Select a set to load its saved point lists.")
            user.find("Load to edit").click()
            await user.should_not_see("Set #9 saved and active.")
            await user.should_see("Loaded from Set #8. Saving will create a new set; Set #8 will stay unchanged.")
            user.find("Prepare preview").click()
            assert next(iter(user.find("Save set").elements)).enabled
            before = removed.value, annotations.value
            api.get_predefined_set.return_value = ApiResult(success=False, is_offline=True)
            user.find("Browse saved sets").click()
            await user.should_see("Select a set to load its saved point lists.")
            user.find("Load to edit").click()
            await user.should_see("Internet connection is required. Your current point lists have been kept.")
            assert (removed.value, annotations.value) == before
            api.list_predefined_sets.return_value = ApiResult(success=False, status_code=403, error="Permission denied")
            user.find("Refresh sets").click()
            await user.should_see("Permission denied")
            assert (removed.value, annotations.value) == before
            await user.should_not_see("Load to edit")
            api.list_predefined_sets.return_value = ApiResult(success=True, data=[])
            user.find("Refresh sets").click()
            await user.should_see("No saved sets are available.")
            assert (removed.value, annotations.value) == before
            api.list_predefined_sets.return_value = ApiResult(success=True, data=[{**SUMMARY, "is_active": True}])
            user.find("Refresh sets").click()
            await user.should_see(marker="deactivate-set-8")
            user.find(marker="deactivate-set-8").click()
            await user.should_see("Deactivate Set #8?")
            user.find("Cancel").click()
            assert api.deactivate_predefined_set.await_count == 0
            user.find(marker="deactivate-set-8").click()
            deactivation = asyncio.Future()
            async def deactivate(_):
                return await deactivation
            api.deactivate_predefined_set.side_effect = deactivate
            user.find("Deactivate set").click()
            user.find("Deactivate set").click()
            await user.should_see("Deactivating set...")
            assert api.deactivate_predefined_set.await_count == 1
            assert not next(iter(user.find("Cancel").elements)).enabled
            deactivation.set_result(ApiResult(success=False, status_code=403, error="Deactivation denied"))
            await user.should_see("Deactivation denied")
            assert (removed.value, annotations.value) == before
            api.deactivate_predefined_set.side_effect = None
            api.deactivate_predefined_set.return_value = ApiResult(success=True, data=dict(predefined_set_id=8, is_active=False))
            api.list_predefined_sets.return_value = ApiResult(success=True, data=[SUMMARY])
            user.find("Deactivate set").click()
            await user.should_see("Inactive")
            await user.should_not_see(marker="deactivate-set-8")
            assert api.deactivate_predefined_set.await_count == 2
            controller.predefined_cache.unavailable.assert_called_once_with("http://test", 8)
            assert (removed.value, annotations.value) == before
            confirmation = [e for e in user.client.elements.values() if isinstance(e, ui.dialog)][1]
            assert confirmation.value is False
    asyncio.run(scenario())
