"""Manage pseudonymous patient groups within the caller's existing scan permissions."""

from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException
from src.api.dependencies import get_db, get_storage, require_role
from src.api.routers.scans import PatientIdentifierUpdate
from src.security.database import MetadataDB, validate_patient_id
from src.security.exceptions import InvalidIdentifierError, StorageError
from src.security.secure_storage import SecureImageStorage

router = APIRouter(prefix='/patients', tags=['Patients'])


def accessible_patient_scans(patient_id, user, db):
    try:
        records = db.list_scans_for_patient(validate_patient_id(patient_id))
    except InvalidIdentifierError:
        raise HTTPException(status_code=422, detail='Invalid pseudonymous patient ID.') from None
    if user['role'] == 'doctor':
        records = [r for r in records if r['uploaded_by'] == user['username']]
    if not records:
        raise HTTPException(status_code=404, detail='No accessible records for this patient.')
    return records


@router.put('/{patient_id}')
def rename_patient(patient_id: str, change: PatientIdentifierUpdate,
                   user: Dict[str, Any] = Depends(require_role('doctor', 'radiologist', 'admin')),
                   db: MetadataDB = Depends(get_db)):
    accessible_patient_scans(patient_id, user, db)
    try:
        count = db.rename_patient(patient_id, change.patient_id,
                                  user['username'] if user['role'] == 'doctor' else None)
    except InvalidIdentifierError:
        raise HTTPException(status_code=422, detail='Invalid pseudonymous patient ID.') from None
    except StorageError as error:
        raise HTTPException(status_code=409, detail=str(error)) from None
    return dict(patient_id=change.patient_id.strip(), updated_scans=count)


@router.delete('/{patient_id}')
def delete_patient(patient_id: str,
                   user: Dict[str, Any] = Depends(require_role('doctor', 'radiologist', 'admin')),
                   db: MetadataDB = Depends(get_db), storage: SecureImageStorage = Depends(get_storage)):
    records = accessible_patient_scans(patient_id, user, db)
    deleted = 0
    try:
        for record in records:
            storage.delete_scan(record['scan_id'])
            deleted += 1
    except StorageError:
        raise HTTPException(status_code=503, detail=f'Deleted {deleted} scans; remaining records were retained. Refresh and retry deletion.') from None
    return dict(deleted_scans=deleted)
