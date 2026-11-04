"""Seed generation parity and exact preview payloads sent to the API."""

import asyncio
import json

import httpx
import pandas as pd
import pytest

from dahlia.core.api_client import ApiClient
from dahlia.datasets import ExperimentSampler
from dahlia.services.predefined_sets import CatalogDataset, PredefinedDraft


@pytest.mark.parametrize("count,fraction", [(150, 0.1), (150, 0.2), (159, 0.3), (400, 0.2)])
@pytest.mark.parametrize("seed", [0, 42, 2**32 - 1])
def test_seed_generation_exactly_matches_existing_sampler(count, fraction, seed):
    draft = PredefinedDraft()
    draft.select_dataset(CatalogDataset(7, "central dataset", count))
    draft.select_fraction(fraction)
    draft.generate_from_seed(str(seed))
    assert draft.preview is None
    removed, annotations = ExperimentSampler(seed).select_experiment_points(
        pd.DataFrame(index=pd.RangeIndex(count)), na_fraction=fraction,
    )
    preview = draft.prepare_preview()
    assert preview.removed_indices == tuple(removed)
    assert preview.annotation_indices == tuple(annotations)
    draft.generate_from_seed(str(seed))
    assert draft.prepare_preview() == preview


@pytest.mark.parametrize("seed", ["", " ", "-1", "1.5", "abc", "4294967296"])
def test_invalid_seed_does_not_replace_current_lists(seed):
    draft = PredefinedDraft()
    draft.select_dataset(CatalogDataset(1, "iris", 150))
    draft.generate_from_seed("42")
    original = (draft.removed_text, draft.annotation_text)
    with pytest.raises(ValueError, match="Seed must"):
        draft.generate_from_seed(seed)
    assert (draft.removed_text, draft.annotation_text) == original


def test_seed_generation_requires_eligible_configuration():
    draft = PredefinedDraft()
    with pytest.raises(ValueError, match="Select a dataset"):
        draft.generate_from_seed("0")
    draft.select_dataset(CatalogDataset(1, "small", 40))
    with pytest.raises(ValueError, match="fewer than 15"):
        draft.generate_from_seed("0")


def test_generated_lists_can_be_edited_and_payload_uses_edited_preview():
    draft = PredefinedDraft()
    draft.select_dataset(CatalogDataset(1, "iris", 150))
    draft.select_fraction(0.2)
    draft.generate_from_seed("42")
    initial = draft.prepare_preview()
    reversed_order = tuple(reversed(initial.annotation_indices))
    draft.set_annotation_text(",".join(map(str, reversed_order)))
    assert draft.preview is None
    preview = draft.prepare_preview()
    payload = preview.to_payload()
    assert payload == {
        "dataset_id": 1, "na_fraction": 0.2,
        "removed_indices": list(initial.removed_indices),
        "annotation_indices": list(reversed_order),
    }
    assert "seed" not in payload
    draft.select_fraction(0.3)
    assert preview.to_payload() == payload
    payload["annotation_indices"].clear()
    assert preview.annotation_indices == reversed_order


def test_save_uses_authenticated_post_and_exact_payload_once():
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(201, json={"predefined_set_id": 123, "is_active": True})

    draft = PredefinedDraft()
    draft.select_dataset(CatalogDataset(1, "iris", 150))
    draft.generate_from_seed("0")
    payload = draft.prepare_preview().to_payload()
    client = ApiClient(transport=httpx.MockTransport(handle))
    assert asyncio.run(client.create_predefined_set(payload)).status_code == 401
    assert not requests
    client.access_token = "current-session"
    result = asyncio.run(client.create_predefined_set(payload))
    assert result.success and result.data["predefined_set_id"] == 123
    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert requests[0].url.path == "/api/v1/predefined-sets"
    assert requests[0].headers["authorization"] == "Bearer current-session"
    assert json.loads(requests[0].content) == payload


@pytest.mark.parametrize("status", [403, 409, 422, 500])
def test_failed_save_is_not_retried_automatically(status):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(status, json={"detail": "Save rejected"})

    client = ApiClient(transport=httpx.MockTransport(handle))
    client.access_token = "current-session"
    result = asyncio.run(client.create_predefined_set({}))
    assert result.success is False
    assert result.status_code == status
    assert len(requests) == 1
