"""Operational probes. Readiness never initializes services or attests model accuracy."""

import logging
from pathlib import Path
import sqlite3
from typing import Dict, Optional

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from src.api.config import API_VERSION
from src.api.dependencies import get_initialized_db, get_initialized_inference_engine, get_initialized_storage
from src.api.model_service import DenseNetInferenceEngine
from src.security.database import MetadataDB
from src.security.secure_storage import SecureImageStorage

router = APIRouter(prefix='/health', tags=['Health & Readiness'])
logger = logging.getLogger(__name__)


@router.get('', status_code=status.HTTP_200_OK)
def liveness() -> Dict[str, str]:
    return dict(status='healthy', service='pneumonia-detection-secure-api', version=API_VERSION)


@router.get('/ready')
def readiness(
    db: Optional[MetadataDB] = Depends(get_initialized_db),
    storage: Optional[SecureImageStorage] = Depends(get_initialized_storage),
    engine: Optional[DenseNetInferenceEngine] = Depends(get_initialized_inference_engine),
) -> JSONResponse:
    checks = dict(database=False, storage=False, model=False)
    components = dict(database='not_initialized', storage='not_initialized', model='not_initialized')
    model_info = None
    if db is not None:
        try:
            # Read-only URI mode prevents a probe from recreating a deleted database.
            connection = sqlite3.connect(Path(db.db_path).resolve().as_uri() + '?mode=ro', uri=True, timeout=1.)
            try:
                tables = {row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('scans','users')")}
                checks['database'] = tables == {'scans', 'users'}
            finally:
                connection.close()
        except Exception as error:
            logger.debug('Database readiness failed (%s).', type(error).__name__)
        components['database'] = 'ready' if checks['database'] else 'unavailable'
    if storage is not None:
        try:
            checks['storage'] = Path(storage.storage_dir).is_dir()
        except Exception as error:
            logger.debug('Storage readiness failed (%s).', type(error).__name__)
        components['storage'] = 'ready' if checks['storage'] else 'unavailable'
    if engine is not None:
        try:
            if engine.model is not None and Path(engine.checkpoint_path).is_file():
                model_info = engine.model_information()
                if not isinstance(model_info, dict) or not {'architecture', 'class_names', 'threshold', 'device'} <= set(model_info):
                    raise ValueError('Incomplete loaded-model metadata.')
                checks['model'] = True
        except Exception as error:
            model_info = None
            logger.debug('Model readiness failed (%s).', type(error).__name__)
        components['model'] = 'ready' if checks['model'] else 'unavailable'
    ready = all(checks.values())
    return JSONResponse(status_code=200 if ready else 503, content=dict(
        status='ready' if ready else 'unready', readiness_scope='operational_only',
        checks=checks, components=components, model=model_info,
        architecture=model_info['architecture'] if model_info else None,
        class_names=model_info['class_names'] if model_info else None,
        threshold=model_info['threshold'] if model_info else None,
        device=model_info['device'] if model_info else None))
