"""Durable downloads, database isolation, revocation refresh and offline execution."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from nicegui import ui

from dahlia.app.controller import AppController
from dahlia.app.screens.setup import render_setup
from dahlia.core.api_client import ApiResult
from dahlia.services.local_storage import LocalStorage
from dahlia.services.predefined_cache import PredefinedCache
from test_predefined_execution import bundle, controller
from test_predefined_sets_load import simulation

BACKEND = "http://test"
IDENTITY = "a" * 64
SUMMARY = dict(predefined_set_id=8, dataset_id=1, dataset_name="iris", na_fraction=0.2, is_active=True)
CATALOG = dict(catalog_id=IDENTITY, sets=[SUMMARY])


def downloaded(cache):
    cache.refresh(BACKEND, CATALOG)
    data = {**bundle(), "catalog_id": IDENTITY}
    cache.save(BACKEND, data)
    return data


def test_download_survives_restart_and_is_scoped_to_backend_and_database(tmp_path):
    path = tmp_path / "offline.db"
    cache = PredefinedCache(LocalStorage(path))
    data = downloaded(cache)
    restarted = PredefinedCache(LocalStorage(path))
    assert restarted.get(BACKEND, 8) == data
    assert restarted.get("https://other-backend", 8) is None
    restarted.refresh(BACKEND, {**CATALOG, "catalog_id": "b" * 64})
    assert restarted.get(BACKEND, 8) is None
    assert restarted.downloaded(BACKEND) == ()
    restarted.refresh(BACKEND, CATALOG)
    assert restarted.get(BACKEND, 8) == data


def test_catalog_refresh_revokes_download_without_deleting_results_or_definition():
    storage = LocalStorage(":memory:")
    cache = PredefinedCache(storage)
    downloaded(cache)
    cache.refresh(BACKEND, dict(catalog_id=IDENTITY, sets=[]))
    assert cache.get(BACKEND, 8) is None
    assert cache.downloaded(BACKEND) == ()
    with cache.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM predefined_downloads").fetchone()[0] == 1
    assert storage.get_experiments() == []


def test_invalid_catalog_or_download_does_not_destroy_existing_cache():
    cache = PredefinedCache(LocalStorage(":memory:"))
    data = downloaded(cache)
    for catalog in ({"catalog_id": "invalid", "sets": []}, {**CATALOG, "sets": [{**SUMMARY, "is_active": False}]}):
        with pytest.raises(ValueError):
            cache.refresh(BACKEND, catalog)
    for changed in ({**data, "catalog_id": "b"*64}, {**data, "csv_sha256": "0"*64}):
        with pytest.raises(ValueError):
            cache.save(BACKEND, changed)
    assert cache.get(BACKEND, 8) == data


def test_corrupt_download_is_detected_before_execution():
    cache = PredefinedCache(LocalStorage(":memory:"))
    downloaded(cache)
    with cache.connection() as conn:
        conn.execute("UPDATE predefined_downloads SET bundle_json=replace(bundle_json, ?, ?)", ('"row_count": 150', '"row_count": 149'))
    with pytest.raises(ValueError, match="row count"):
        cache.get(BACKEND, 8)


def test_offline_controller_starts_downloaded_definition_without_sampling():
    ctrl = controller(bundle())
    data = downloaded(ctrl.predefined_cache)
    ctrl.api_client.get_execution_set.return_value = ApiResult(success=False, is_offline=True)
    with patch("dahlia.app.controller.start_algorithm_predictions", return_value="future"):
        asyncio.run(AppController.start_experiment(ctrl))
    ctrl.show_experiment.assert_called_once()
    assert ctrl.experiment.seed == 0 and ctrl.experiment.predefined_set_id == 8
    assert ctrl.experiment.annotation_indices.tolist() == data["annotation_indices"]


@pytest.mark.parametrize("status", [403, 404, 409, 500])
def test_server_rejection_never_falls_back_to_download(status):
    ctrl = controller(bundle())
    downloaded(ctrl.predefined_cache)
    ctrl.api_client.get_execution_set.return_value = ApiResult(success=False, status_code=status, error="Server rejected set")
    asyncio.run(AppController.start_experiment(ctrl))
    ctrl.show_experiment.assert_not_called()
    if status in (404, 409):
        assert ctrl.predefined_cache.get(BACKEND, 8) is None


def test_changed_database_invalidates_old_downloads_before_offline_retry():
    ctrl = controller(bundle())
    downloaded(ctrl.predefined_cache)
    ctrl.api_client.get_execution_set.return_value = ApiResult(success=True, data={**bundle(), "catalog_id": "b"*64})
    asyncio.run(AppController.start_experiment(ctrl))
    ctrl.show_experiment.assert_not_called()
    assert ctrl.predefined_cache.get(BACKEND, 8) is None


def test_download_button_and_offline_catalog_after_restart(tmp_path):
    async def scenario():
        path = tmp_path / "download.db"
        cache = PredefinedCache(LocalStorage(path))
        pending = asyncio.Future()
        async def download(_):
            return await pending
        api = SimpleNamespace(base_url=BACKEND,
            get_offline_set_catalog=AsyncMock(return_value=ApiResult(success=True, data=CATALOG)),
            get_execution_set=AsyncMock(side_effect=download))
        ctrl = SimpleNamespace(current_user=None, active_screen="setup", seed=42, dataset_name="iris", na_fraction=0.1,
            projection_name="pca", experiment_source="PREDEFINED", predefined_selection=None, predefined_cache=cache,
            api_client=api, is_online=True, start_experiment=AsyncMock(), generate_random_seed=Mock(),
            show_setup=Mock(), show_my_results=Mock(), show_profile=Mock(), _update_status_badge=Mock())
        ctrl.set_seed_text = lambda value: AppController.set_seed_text(ctrl, value)
        ctrl.bind_setup_elements = lambda **elements: setattr(ctrl, "setup_elements", elements)
        async with simulation(lambda: render_setup(ctrl)) as user:
            await user.open("/")
            await user.should_see("Select an active set.")
            def select():
                return next(e for e in ctrl.setup_elements["controls"] if isinstance(e, ui.select) and e.props.get("label") == "Predefined set")
            with user:
                select().value = 8
            user.find("Download for offline").click()
            user.find("Download for offline").click()
            await user.should_see("Downloading set and dataset...")
            assert api.get_execution_set.await_count == 1
            assert not ctrl.setup_elements["start_button"].enabled
            pending.set_result(ApiResult(success=True, data={**bundle(), "catalog_id": IDENTITY}))
            await user.should_see("Downloaded for offline use.")
            assert ctrl.setup_elements["start_button"].enabled
            # Recreate controller storage and screen, as after an application restart.
            ctrl.predefined_cache = PredefinedCache(LocalStorage(path))
            api.get_offline_set_catalog.return_value = ApiResult(success=False, is_offline=True)
            user.find("Refresh sets").click()
            await user.should_see("Downloaded for offline use.")
            # The selected set remains selected after an offline refresh.
            await asyncio.sleep(0)
            assert ctrl.predefined_selection.predefined_set_id == 8
            assert ctrl.setup_elements["start_button"].enabled
            api.get_offline_set_catalog.return_value = ApiResult(success=True, data={"catalog_id": IDENTITY, "sets": []})
            user.find("Refresh sets").click()
            await user.should_see("No active sets are available.")
            assert ctrl.predefined_selection is None and not ctrl.setup_elements["start_button"].enabled
            api.get_offline_set_catalog.return_value = ApiResult(success=False, is_offline=True)
            user.find("Refresh sets").click()
            await user.should_see("No downloaded sets are available. Connect to the internet to download a set.")
    asyncio.run(scenario())
