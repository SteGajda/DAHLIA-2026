"""Ownership, explicit assignment and precise server acknowledgements."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest

from dahlia.app.controller import AppController
from dahlia.core.api_client import ApiResult
from dahlia.services.config import METHOD_ORDER
from dahlia.services.local_storage import LocalStorage


def setup_controller():
    storage = LocalStorage(':memory:')
    controller = AppController(MagicMock(), storage=storage)
    controller.current_user = {'user_id': 1, 'email': 'one@example.com', 'role': 'USER'}
    controller.is_online = True
    return controller, storage


def save(storage, owner=None, complete=True, synced=False):
    indices = list(range(15))
    values = {str(i): 2.0 for i in indices}
    details = {
        'app_version': '1.1.0',
        'dataset_config': dict(incomplete_column='value', target_column=None,
                               reference_columns=[], categorical_columns=[], precision=0.1,
                               number_of_clusters=3, knn_number_of_neighbors=5),
        'removed_indices': indices, 'true_values': values,
        'algorithm_predictions': {name: dict(values) for name in METHOD_ORDER[1:]},
    }
    return storage.save_experiment(
        dataset_name='iris', seed=1, na_fraction=0.1, projection='pca',
        results_df=pd.DataFrame([dict(Method=name, MAE=0.0, RMSE=0.0) for name in METHOD_ORDER]),
        answers={i: 2.0 for i in indices}, annotation_indices=indices, user_id=owner,
        sync_status='Synced' if synced else 'Local only', completed_data=details if complete else None,
    )


def records(storage):
    return {record['experiment_uid']: record for record in storage.get_experiments()}


def acknowledgement(payload):
    return ApiResult(success=True, status_code=201,
                     data={'status': 'synced', 'experiment_uid': payload['experiment_uid']})


def test_login_does_not_claim_anonymous_records_or_upload():
    controller, storage = setup_controller()
    uid = save(storage)
    controller.api_client.sync_experiment = AsyncMock()
    controller._set_user_from_profile({'user_id': 1, 'email': 'one@example.com'})
    assert records(storage)[uid]['user_id'] is None
    controller.api_client.sync_experiment.assert_not_called()


def test_fallback_login_does_not_claim_anonymous_records():
    controller, storage = setup_controller()
    uid = save(storage)
    controller.current_user = None
    controller.api_client.login = AsyncMock(return_value=ApiResult(success=True))
    controller.api_client.get_me = AsyncMock(return_value=ApiResult(success=False))
    controller.api_client.get_current_role = MagicMock(return_value='USER')
    controller.api_client.access_token = 'mock'
    controller.api_client.decode_token_payload = MagicMock(return_value={'sub': '1'})
    assert asyncio.run(controller.do_login('one@example.com', 'password')) is None
    assert records(storage)[uid]['user_id'] is None


def test_assignment_only_changes_confirmed_anonymous_records():
    controller, storage = setup_controller()
    first = save(storage)
    foreign = save(storage, owner=2)
    already_synced = save(storage, synced=True)
    snapshot = controller.get_unassigned_experiment_uids()
    new_after_dialog = save(storage)
    assert controller.assign_unassigned_experiments(1, snapshot) == 1
    result = records(storage)
    assert result[first]['user_id'] == 1
    assert result[first]['payload']['user_id'] == 1
    assert result[foreign]['user_id'] == 2
    assert result[already_synced]['user_id'] is None
    assert result[new_after_dialog]['user_id'] is None
    assert result[first]['sync_status'] == 'Local only'


def test_account_change_invalidates_assignment_confirmation():
    controller, storage = setup_controller()
    uid = save(storage)
    controller.current_user['user_id'] = 2
    assert controller.assign_unassigned_experiments(1, [uid]) == 0
    assert records(storage)[uid]['user_id'] is None


def test_upload_only_sends_complete_records_of_current_owner():
    controller, storage = setup_controller()
    own = save(storage, owner=1)
    foreign = save(storage, owner=2)
    anonymous = save(storage)
    legacy = save(storage, owner=1, complete=False)
    done = save(storage, owner=1, synced=True)
    controller.api_client.sync_experiment = AsyncMock(side_effect=acknowledgement)
    assert asyncio.run(controller.sync_local_experiments()) == (1, 0)
    controller.api_client.sync_experiment.assert_awaited_once()
    sent = controller.api_client.sync_experiment.call_args.args[0]
    assert sent['experiment_uid'] == own and sent['user_id'] == 1
    for uid in (foreign, anonymous, legacy):
        assert records(storage)[uid]['sync_status'] == 'Local only'
    assert records(storage)[done]['sync_status'] == 'Synced'


@pytest.mark.parametrize('code,status', [(201, 'synced'), (200, 'already_synced')])
def test_only_explicit_matching_acknowledgement_marks_synced(code, status):
    controller, storage = setup_controller()
    uid = save(storage, owner=1)
    controller.api_client.sync_experiment = AsyncMock(return_value=ApiResult(
        success=True, status_code=code, data={'status': status, 'experiment_uid': uid},
    ))
    assert asyncio.run(controller.sync_local_experiments()) == (1, 0)
    assert records(storage)[uid]['sync_status'] == 'Synced'


@pytest.mark.parametrize('problem', ['conflict', 'wrong_uuid', 'wrong_status', 'missing_data'])
def test_conflict_or_invalid_acknowledgement_stays_unsynced(problem):
    controller, storage = setup_controller()
    uid = save(storage, owner=1)
    response = acknowledgement({'experiment_uid': uid})
    if problem == 'conflict': response = ApiResult(success=False, status_code=409, error='UUID conflict')
    elif problem == 'wrong_uuid': response.data['experiment_uid'] = 'other'
    elif problem == 'wrong_status': response.data['status'] = 'ok'
    else: response.data = None
    controller.api_client.sync_experiment = AsyncMock(return_value=response)
    assert asyncio.run(controller.sync_local_experiments()) == (0, 1)
    assert records(storage)[uid]['sync_status'] == 'Sync failed'
    assert controller.last_sync_error


def test_upload_confirmation_limits_which_records_are_sent():
    controller, storage = setup_controller()
    confirmed = save(storage, owner=1)
    after_dialog = save(storage, owner=1)
    controller.api_client.sync_experiment = AsyncMock(side_effect=acknowledgement)
    assert asyncio.run(controller.sync_local_experiments(experiment_uids=[confirmed], expected_user_id=1)) == (1, 0)
    assert records(storage)[after_dialog]['sync_status'] == 'Local only'


def test_account_change_invalidates_upload_confirmation():
    controller, storage = setup_controller()
    uid = save(storage, owner=1)
    controller.current_user['user_id'] = 2
    controller.api_client.sync_experiment = AsyncMock()
    assert asyncio.run(controller.sync_local_experiments(experiment_uids=[uid], expected_user_id=1)) == (0, 0)
    controller.api_client.sync_experiment.assert_not_called()


def test_network_failure_can_be_retried_without_changing_uuid():
    controller, storage = setup_controller()
    uid = save(storage, owner=1)
    controller.api_client.sync_experiment = AsyncMock(return_value=ApiResult(
        success=False, is_offline=True, error='Offline',
    ))
    assert asyncio.run(controller.sync_local_experiments()) == (0, 1)
    assert not controller._sync_in_progress
    assert records(storage)[uid]['sync_status'] == 'Sync failed'
    controller.is_online = True
    controller.api_client.sync_experiment = AsyncMock(side_effect=acknowledgement)
    assert asyncio.run(controller.sync_local_experiments()) == (1, 0)
    assert records(storage)[uid]['sync_status'] == 'Synced'


def test_parallel_upload_clicks_do_not_duplicate_requests():
    async def scenario():
        controller, storage = setup_controller()
        save(storage, owner=1)
        started, finish = asyncio.Event(), asyncio.Event()
        async def delayed(payload):
            started.set()
            await finish.wait()
            return acknowledgement(payload)
        controller.api_client.sync_experiment = AsyncMock(side_effect=delayed)
        first = asyncio.create_task(controller.sync_local_experiments())
        await started.wait()
        assert await controller.sync_local_experiments() == (0, 0)
        finish.set()
        assert await first == (1, 0)
        controller.api_client.sync_experiment.assert_awaited_once()
    asyncio.run(scenario())
