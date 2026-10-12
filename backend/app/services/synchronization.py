"""Validate and persist completed experiments atomically and idempotently."""

import csv
import hashlib
import io
import json
import logging
import math
from datetime import timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.experiment import (
    Dataset, Experiment, ExperimentPoint, ExperimentResult, PointPrediction,
    PredefinedSet, PredefinedSetPoint,
)
from app.models.user import AppUser
from app.schemas.experiment import CompletedExperiment, METHODS

LOGGER = logging.getLogger(__name__)


def _invalid(message: str):
    raise HTTPException(422, detail=message)


def _canonical(payload: CompletedExperiment, user_id: int) -> str:
    data = payload.model_dump(mode='json')
    data['user_id'] = user_id
    data['created_at'] = payload.created_at.astimezone(timezone.utc).isoformat()
    # Removed-point order is not meaningful; annotation order is meaningful.
    data['removed_indices'] = sorted(data['removed_indices'])
    data['metrics'] = sorted(data['metrics'], key=lambda metric: metric['Method'])
    return json.dumps(data, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _existing_result(existing: Experiment, owner: int, digest: bytes):
    if existing.annotator_id != owner:
        raise HTTPException(409, detail='Experiment UUID belongs to another account.')
    if existing.payload_sha256 is None or bytes(existing.payload_sha256) != digest:
        raise HTTPException(409, detail='Experiment UUID already exists with different content.')
    return {'status': 'already_synced', 'experiment_uid': str(existing.experiment_uid),
            'experiment_id': existing.experiment_id}


def _validate_dataset(db: Session, payload: CompletedExperiment) -> Dataset:
    dataset = db.scalar(select(Dataset).where(Dataset.name == payload.dataset_name))
    if dataset is None:
        raise HTTPException(404, detail='Dataset is not registered in the central database.')
    if not dataset.is_active:
        raise HTTPException(409, detail='Dataset is inactive.')
    cfg = payload.dataset_config
    if (
        cfg.incomplete_column != dataset.imputed_column
        or cfg.target_column != dataset.target_column
        or cfg.reference_columns != json.loads(dataset.reference_columns_json)
        or cfg.categorical_columns != json.loads(dataset.categorical_columns_json)
        or Decimal(str(cfg.precision)) != dataset.precision_value
    ):
        _invalid('Dataset configuration does not match the central dataset.')
    content = bytes(dataset.csv_file)
    if hashlib.sha256(content).digest() != bytes(dataset.csv_sha256):
        raise HTTPException(500, detail='Central dataset checksum validation failed.')
    try:
        rows = list(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))))
        if len(rows) != dataset.row_count:
            raise ValueError('Row count mismatch.')
        for index in payload.removed_indices:
            if index >= len(rows):
                _invalid('A point index is outside the dataset.')
            truth = float(rows[index][dataset.imputed_column])
            if not math.isfinite(truth) or not math.isclose(
                truth, payload.true_values[index], rel_tol=1e-12, abs_tol=1e-12
            ):
                _invalid('True values do not match the central dataset.')
    except (UnicodeError, KeyError, ValueError) as exc:
        raise HTTPException(500, detail='Central dataset cannot be read.') from exc
    if payload.source_type == 'PREDEFINED':
        predefined = db.get(PredefinedSet, payload.predefined_set_id)
        if (predefined is None or not predefined.is_active
                or predefined.dataset_id != dataset.dataset_id
                or predefined.na_fraction != Decimal(str(payload.na_fraction))):
            _invalid('Predefined set does not match the experiment.')
        points = db.scalars(select(PredefinedSetPoint).where(
            PredefinedSetPoint.predefined_set_id == predefined.predefined_set_id
        )).all()
        annotations = [point.row_index for point in sorted(
            (p for p in points if p.annotation_order is not None),
            key=lambda point: point.annotation_order,
        )]
        if ({point.row_index for point in points} != set(payload.removed_indices)
                or annotations != payload.annotation_indices):
            _invalid('Points or annotation order do not match the predefined set.')
    return dataset


def _validate_metrics(payload: CompletedExperiment):
    supplied = {metric.Method: metric for metric in payload.metrics}
    predictors = {'Annotator': payload.answers, **payload.algorithm_predictions}
    for name, values in predictors.items():
        errors = [values[i] - payload.true_values[i] for i in payload.annotation_indices]
        mae = sum(abs(error) / 15 for error in errors)
        rmse = math.hypot(*errors) / math.sqrt(15)
        if not math.isfinite(mae) or not math.isfinite(rmse):
            _invalid('Prediction errors are not finite.')
        metric = supplied[name]
        if (not math.isclose(metric.MAE, mae, rel_tol=1e-7, abs_tol=1e-9)
                or not math.isclose(metric.RMSE, rmse, rel_tol=1e-7, abs_tol=1e-9)):
            _invalid(f'Metrics do not match predictions for {name}.')


def synchronize(db: Session, payload: CompletedExperiment, user: AppUser):
    owner = user.user_id
    if payload.user_id is not None and payload.user_id != owner:
        raise HTTPException(403, detail='Cannot upload results for another account.')
    canonical = _canonical(payload, owner)
    digest = hashlib.sha256(canonical.encode('utf-8')).digest()
    existing = db.scalar(select(Experiment).where(Experiment.experiment_uid == payload.experiment_uid))
    if existing is not None:
        return _existing_result(existing, owner, digest), False
    dataset = _validate_dataset(db, payload)
    _validate_metrics(payload)
    experiment = Experiment(
        experiment_uid=payload.experiment_uid, annotator_id=owner,
        dataset_id=dataset.dataset_id, source_type=payload.source_type,
        seed=payload.seed, predefined_set_id=payload.predefined_set_id,
        na_fraction=Decimal(str(payload.na_fraction)), projection=payload.projection,
        completed_at=payload.created_at.astimezone(timezone.utc).replace(tzinfo=None),
        app_version=payload.app_version, payload_json=canonical, payload_sha256=digest,
    )
    try:
        db.add(experiment)
        db.flush()
        orders = {index: order for order, index in enumerate(payload.annotation_indices, start=1)}
        points = [ExperimentPoint(
            experiment_id=experiment.experiment_id, row_index=index,
            annotation_order=orders.get(index), true_value=payload.true_values[index],
        ) for index in sorted(payload.removed_indices)]
        db.add_all(points)
        db.flush()
        for point in points:
            index = point.row_index
            for method in METHODS:
                db.add(PointPrediction(
                    experiment_point_id=point.experiment_point_id, predictor_type='METHOD',
                    predictor_name=method, predicted_value=payload.algorithm_predictions[method][index],
                ))
            if index in orders:
                db.add(PointPrediction(
                    experiment_point_id=point.experiment_point_id, predictor_type='ANNOTATOR',
                    predictor_name='Annotator', predicted_value=payload.answers[index],
                ))
        for metric in payload.metrics:
            db.add(ExperimentResult(
                experiment_id=experiment.experiment_id,
                predictor_type='ANNOTATOR' if metric.Method == 'Annotator' else 'METHOD',
                predictor_name=metric.Method, mae=metric.MAE, rmse=metric.RMSE,
            ))
        db.flush()
        result = {'status': 'synced', 'experiment_uid': str(experiment.experiment_uid),
                  'experiment_id': experiment.experiment_id,
                  'points': len(points), 'predictions': len(points) * 6 + 15, 'metrics': 7}
        db.commit()
        return result, True
    except IntegrityError as exc:
        db.rollback()
        existing = db.scalar(select(Experiment).where(Experiment.experiment_uid == payload.experiment_uid))
        if existing is not None:
            return _existing_result(existing, owner, digest), False
        raise HTTPException(409, detail='Database constraint conflict; no experiment was saved.') from exc
    except SQLAlchemyError as exc:
        db.rollback()
        LOGGER.error('Experiment persistence failed', exc_info=True)
        raise HTTPException(500, detail='Experiment could not be saved; retry the upload.') from exc
