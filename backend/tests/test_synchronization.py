"""Authenticated atomic uploads, content validation and UUID retries."""

import copy
import csv
import hashlib
import io
import json
import math
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError

from app.core.security import create_access_token
from app.models.user import AppUser
from app.models.experiment import Dataset, Experiment, ExperimentPoint, PointPrediction, ExperimentResult
from app.schemas.experiment import METHODS


@pytest.fixture()
def upload(sqlite_session):
    s = sqlite_session
    user = AppUser(email='sync@example.com', display_name='Sync test', password_hash='unused')
    other = AppUser(email='other@example.com', display_name='Other', password_hash='unused')
    s.add_all([user, other])
    s.flush()
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(['Id', 'value', 'reference'])
    for i in range(150):
        writer.writerow([i + 1, 4.0 + i / 10, 2.0])
    content = stream.getvalue().encode()
    dataset = Dataset(
        name='iris', csv_file_name='iris.csv', csv_file=content,
        csv_sha256=hashlib.sha256(content).digest(), row_count=150,
        imputed_column='value', target_column=None, reference_columns_json='["reference"]',
        categorical_columns_json='[]', precision_value=Decimal('0.1'), created_by=user.user_id,
    )
    s.add(dataset)
    s.commit()
    truth = {str(i): 4.0 + i / 10 for i in range(30)}
    predictions = {method: {key: value + 0.2 for key, value in truth.items()} for method in METHODS}
    answers = {str(i): truth[str(i)] + 0.1 for i in range(15)}
    metrics = []
    for name, values in {'Annotator': answers, **predictions}.items():
        errors = [values[str(i)] - truth[str(i)] for i in range(15)]
        metrics.append({'Method': name, 'MAE': sum(map(abs, errors)) / 15,
                        'RMSE': math.hypot(*errors) / math.sqrt(15)})
    payload = dict(
        payload_schema_version=2, experiment_uid=str(uuid4()),
        created_at=datetime.now(timezone.utc).isoformat(), dataset_name='iris',
        seed=42, na_fraction=0.2, projection='pca', user_id=user.user_id,
        app_version='1.1.0', answers=answers, annotation_indices=list(range(15)),
        removed_indices=list(range(30)), true_values=truth,
        algorithm_predictions=predictions, metrics=metrics,
        dataset_config=dict(incomplete_column='value', target_column=None,
                            reference_columns=['reference'], categorical_columns=[], precision=0.1,
                            number_of_clusters=3, knn_number_of_neighbors=5),
    )
    return payload, {'Authorization': 'Bearer ' + create_access_token(user.user_id, user.role_code)}, other.user_id


def count(session, model):
    return session.scalar(select(func.count()).select_from(model))


def test_complete_upload_and_retry_do_not_duplicate(client, sqlite_session, upload):
    payload, headers, _ = upload
    first = client.post('/api/v1/sync/experiment', json=payload, headers=headers)
    assert first.status_code == 201, first.text
    assert first.json()['predictions'] == 195
    assert count(sqlite_session, Experiment) == 1
    assert count(sqlite_session, ExperimentPoint) == 30
    assert count(sqlite_session, PointPrediction) == 195
    assert count(sqlite_session, ExperimentResult) == 7
    record = sqlite_session.scalar(select(Experiment))
    assert record.payload_sha256 and json.loads(record.payload_json)['payload_schema_version'] == 2
    assert record.synced_at is not None
    retry = client.post('/api/v1/sync/experiment', json=payload, headers=headers)
    assert retry.status_code == 200 and retry.json()['status'] == 'already_synced'
    assert count(sqlite_session, PointPrediction) == 195


def test_upload_requires_authentication(client, upload):
    payload, _, _ = upload
    assert client.post('/api/v1/sync/experiment', json=payload).status_code in (401, 403)


def test_owner_comes_from_authenticated_account(client, sqlite_session, upload):
    payload, headers, other = upload
    payload['user_id'] = other
    assert client.post('/api/v1/sync/experiment', json=payload, headers=headers).status_code == 403
    assert count(sqlite_session, Experiment) == 0


def test_uuid_with_changed_content_is_a_conflict(client, sqlite_session, upload):
    payload, headers, _ = upload
    assert client.post('/api/v1/sync/experiment', json=payload, headers=headers).status_code == 201
    payload['seed'] = 43
    assert client.post('/api/v1/sync/experiment', json=payload, headers=headers).status_code == 409
    assert count(sqlite_session, Experiment) == 1


def test_uuid_from_another_account_is_a_conflict(client, upload):
    payload, headers, other = upload
    assert client.post('/api/v1/sync/experiment', json=payload, headers=headers).status_code == 201
    payload['user_id'] = other
    headers = {'Authorization': 'Bearer ' + create_access_token(other, 'USER')}
    assert client.post('/api/v1/sync/experiment', json=payload, headers=headers).status_code == 409


@pytest.mark.parametrize('problem', [
    'legacy', 'missing_answer', 'missing_method', 'missing_prediction', 'duplicate_index',
    'truth', 'configuration', 'metrics', 'out_of_range', 'nonfinite', 'unknown_dataset',
])
def test_invalid_upload_creates_no_records(client, sqlite_session, upload, problem):
    payload, headers, _ = upload
    payload = copy.deepcopy(payload)
    if problem == 'legacy': payload['payload_schema_version'] = 1
    elif problem == 'missing_answer': payload['answers'].pop('0')
    elif problem == 'missing_method': payload['algorithm_predictions'].pop('Mean')
    elif problem == 'missing_prediction': payload['algorithm_predictions']['Mean'].pop('29')
    elif problem == 'duplicate_index': payload['removed_indices'].append(29)
    elif problem == 'truth': payload['true_values']['29'] = 99.0
    elif problem == 'configuration': payload['dataset_config']['incomplete_column'] = 'other'
    elif problem == 'metrics': payload['metrics'][0]['MAE'] = 99.0
    elif problem == 'nonfinite': payload['algorithm_predictions']['Mean']['29'] = 'NaN'
    elif problem == 'unknown_dataset': payload['dataset_name'] = 'unknown'
    elif problem == 'out_of_range':
        payload['removed_indices'][-1] = 150
        payload['true_values']['150'] = payload['true_values'].pop('29')
        for values in payload['algorithm_predictions'].values(): values['150'] = values.pop('29')
    response = client.post('/api/v1/sync/experiment', json=payload, headers=headers)
    assert response.status_code == (404 if problem == 'unknown_dataset' else 422), response.text
    for model in (Experiment, ExperimentPoint, PointPrediction, ExperimentResult):
        assert count(sqlite_session, model) == 0


def test_failure_after_point_inserts_rolls_back_everything(client, sqlite_session, sqlite_engine, upload):
    payload, headers, _ = upload
    seen_points = []
    def fail_predictions(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().startswith('INSERT INTO main.experiment_point'):
            seen_points.append(True)
        if 'INSERT INTO main.point_prediction' in statement:
            raise IntegrityError(statement, parameters, Exception('Injected constraint failure'))
    event.listen(sqlite_engine, 'before_cursor_execute', fail_predictions)
    try:
        response = client.post('/api/v1/sync/experiment', json=payload, headers=headers)
    finally:
        event.remove(sqlite_engine, 'before_cursor_execute', fail_predictions)
    assert seen_points
    assert response.status_code == 409
    for model in (Experiment, ExperimentPoint, PointPrediction, ExperimentResult):
        assert count(sqlite_session, model) == 0
    retry = client.post('/api/v1/sync/experiment', json=payload, headers=headers)
    assert retry.status_code == 201
