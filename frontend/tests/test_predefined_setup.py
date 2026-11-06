"""Public selection and seeded-mode isolation before predefined execution."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from nicegui import ui

from dahlia.app.controller import AppController
from dahlia.app.screens.setup import render_setup
from dahlia.core.api_client import ApiClient, ApiResult
from dahlia.services.local_storage import LocalStorage
from dahlia.services.predefined_cache import PredefinedCache
from test_predefined_sets_load import simulation


AVAILABLE = [dict(predefined_set_id=2, dataset_id=7, dataset_name="central only",
                  na_fraction=0.3, is_active=True)]


def test_selection_catalog_is_public_even_when_client_has_a_session():
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(200, json=AVAILABLE)
    client = ApiClient(transport=httpx.MockTransport(handle))
    for token in (None, "existing-session"):
        client.access_token = token
        assert asyncio.run(client.list_available_predefined_sets()).data == AVAILABLE
    assert all(r.url.path == "/api/v1/predefined-sets/available" for r in requests)
    assert all("authorization" not in r.headers for r in requests)


@pytest.mark.parametrize("stored_mode", ["SEEDED", "PREDEFINED"])
def test_controller_cannot_start_predefined_as_seeded(stored_mode):
    ctrl = SimpleNamespace(experiment_source=stored_mode,
        _preparing_experiment=False, predefined_selection=None,
        setup_elements={"source_toggle": SimpleNamespace(value="PREDEFINED")})
    with patch("dahlia.app.controller.ui.notify") as notify, patch("dahlia.app.controller.prepare_experiment") as prepare:
        asyncio.run(AppController.start_experiment(ctrl))
    notify.assert_called_once()
    prepare.assert_not_called()


def test_setup_select_refresh_offline_and_late_responses_preserve_seeded_mode():
    async def scenario():
        api = SimpleNamespace(base_url="http://test", get_offline_set_catalog=AsyncMock(return_value=ApiResult(success=True, data={"catalog_id": "a"*64, "sets": AVAILABLE})))
        ctrl = SimpleNamespace(current_user=None, active_screen="setup", seed=42, dataset_name="iris",
            na_fraction=0.2, projection_name="pca", experiment_source="SEEDED", predefined_selection=None,
            is_online=True, api_client=api, predefined_cache=PredefinedCache(LocalStorage(":memory:")), start_experiment=AsyncMock(), generate_random_seed=Mock(),
            show_setup=Mock(), show_my_results=Mock(), show_profile=Mock(), _update_status_badge=Mock())
        ctrl.set_seed_text = lambda value: AppController.set_seed_text(ctrl, value)
        ctrl.bind_setup_elements = lambda **elements: setattr(ctrl, "setup_elements", elements)
        async with simulation(lambda: render_setup(ctrl)) as user:
            await user.open("/")
            assert api.get_offline_set_catalog.await_count == 0
            controls = ctrl.setup_elements["controls"]
            toggle = next(e for e in controls if isinstance(e, ui.toggle))
            sets = next(e for e in controls if isinstance(e, ui.select) and e.props.get("label") == "Predefined set")
            selects = [e for e in controls if isinstance(e, ui.select) and e is not sets]
            dataset, fraction, projection = selects
            start = ctrl.setup_elements["start_button"]
            assert start.enabled and dataset.value == "iris"
            with user:
                toggle.value = "PREDEFINED"
            await user.should_see("Select an active set.")
            assert ctrl.current_user is None
            assert ctrl.predefined_selection is None and not start.enabled
            with user:
                sets.value = 2
                projection.value = "umap"
            await user.should_see("Set #2 | Dataset: central only | NA fraction: 0.3")
            assert ctrl.predefined_selection.predefined_set_id == 2
            assert dataset.value == "central only" and fraction.value == "0.3"
            assert not dataset.enabled and not fraction.enabled and projection.enabled
            assert ctrl.dataset_name == "iris" and ctrl.na_fraction == 0.2 and ctrl.seed == 42
            assert not start.enabled
            user.find("Start Experiment").click()
            ctrl.start_experiment.assert_not_awaited()
            api.get_offline_set_catalog.return_value = ApiResult(success=True, data={"catalog_id": "a"*64, "sets": []})
            user.find("Refresh sets").click()
            await user.should_see("No active sets are available.")
            assert ctrl.predefined_selection is None and sets.value is None and dataset.value is None
            api.get_offline_set_catalog.return_value = ApiResult(success=False, is_offline=True)
            user.find("Refresh sets").click()
            await user.should_see("No downloaded sets are available. Connect to the internet to download a set.")
            assert not sets.enabled
            api.get_offline_set_catalog.return_value = ApiResult(success=True,
                data={"catalog_id": "a"*64, "sets": [{**AVAILABLE[0], "dataset_name": "iris"}]})
            user.find("Refresh sets").click()
            await user.should_see("Select an active set.")
            with user:
                sets.value = 2
            await user.should_see("Set #2 | Dataset: iris | NA fraction: 0.3")
            assert start.enabled
            user.find("Start Experiment").click()
            await asyncio.sleep(0)
            ctrl.start_experiment.assert_awaited_once()
            with user:
                toggle.value = "SEEDED"
            await user.should_see("Insert seed")
            assert start.enabled and dataset.value == "iris" and fraction.value == "0.2"
            assert projection.value == "umap" and ctrl.seed == 42
            ctrl.setup_elements["seed_input"].value = "abc"
            assert not start.enabled
            with user:
                ctrl.setup_elements["seed_input"].value = "42"
            assert start.enabled
            pending = asyncio.Future()
            returned = asyncio.Event()
            async def delayed():
                result = await pending
                returned.set()
                return result
            api.get_offline_set_catalog.side_effect = delayed
            with user:
                toggle.value = "PREDEFINED"
            await user.should_see("Loading active sets...")
            with user:
                toggle.value = "SEEDED"
            await user.should_see("Insert seed")
            pending.set_result(ApiResult(success=True, data={"catalog_id": "a"*64, "sets": AVAILABLE}))
            await returned.wait()
            await asyncio.sleep(0)
            assert ctrl.experiment_source == "SEEDED" and ctrl.predefined_selection is None
            assert start.enabled and dataset.enabled and dataset.value == "iris"
    asyncio.run(scenario())
