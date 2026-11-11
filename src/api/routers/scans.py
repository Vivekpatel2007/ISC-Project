"""
Medical Scans & Inference Router
ISC Project: Secure Storage and Transmission of Medical Data

Endpoints:
- POST /scans: Upload a raw chest X-ray, encrypt with AES-256-GCM, and record metadata.
- GET  /scans: List accessible scan records based on authenticated role.
- GET  /scans/{scan_id}: View authorized scan metadata.
- POST /scans/{scan_id}/predict: In-memory retrieval, decryption, and DenseNet121 inference.

Security & Authorization Constraints:
1. Doctors can upload scans and view/predict only their own uploaded scans.
2. Radiologists have diagnostic clearance to view and run predictions on all patient scans.
3. Stored scans are encrypted and inference decryption stays in memory.
   Multipart uploads may spool to framework temporary files before this handler.
"""

import io
from typing import Any, Dict, List, Optional, Literal
from PIL import Image

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import Response
from pydantic import BaseModel, Field, ConfigDict

from src.api.config import (
    ALLOWED_IMAGE_FORMATS,
    ALLOWED_MIME_TYPES,
    MAX_IMAGE_SIZE_BYTES,
)
from src.api.dependencies import (
    get_current_user,
    get_db,
    get_inference_engine,
    get_storage,
    require_role,
)
from src.api.model_service import DenseNetInferenceEngine, InvalidImagePayloadError
from src.explainability import ExplanationMismatch
from src.api.rate_limiter import rate_limit_inference
from src.security.database import MetadataDB, validate_patient_id, validate_scan_id
from src.security.exceptions import (
    AuthenticationError,
    IntegrityVerificationError,
    InvalidIdentifierError,
    MaxFileSizeExceededError,
    ScanNotFoundError,
    StorageError,
)
from src.security.secure_storage import SecureImageStorage

router = APIRouter(prefix="/scans", tags=["Medical Scans"])


# =====================================================================
# Pydantic Schemas
# =====================================================================
class ScanMetadataResponse(BaseModel):
    scan_id: str
    patient_id: str
    file_size_bytes: int
    format_version: int
    created_at: str
    prediction_status: str
    predicted_class: Optional[str] = None
    prediction_probability: Optional[float] = None
    uploaded_by: str


class PredictionResponse(BaseModel):
    scan_id: str
    patient_id: str
    prediction: str
    confidence: float
    pneumonia_probability: float
    normal_probability: float
    threshold_applied: float
    model_architecture: str
    model_epoch: int
    model_checkpoint_sha256: Optional[str] = None
    device: str
    disclaimer: str
    logit_margin: Optional[float] = None
    log_probability_normal: Optional[float] = None
    log_probability_pneumonia: Optional[float] = None
    probabilities_calibrated: bool = False
    score_interpretation: str = 'uncalibrated_model_score'


class PatientIdentifierUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    patient_id: str = Field(..., min_length=3, max_length=64)


class ExplanationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    target_class: Literal['NORMAL', 'PNEUMONIA']
    model_checkpoint_sha256: str = Field(..., pattern=r'^[0-9a-f]{64}$')


class ExplanationRegion(BaseModel):
    id: int = Field(..., ge=1, le=3)
    location: str
    title: str
    description: str
    bounds: List[float] = Field(..., min_length=4, max_length=4)
    marker: List[float] = Field(..., min_length=2, max_length=2)


class ExplanationResponse(BaseModel):
    scan_id: str
    method: str
    target_layer: str
    target_class: str
    target_score: str
    target_logit: float
    pneumonia_probability: float
    model_checkpoint_sha256: str
    image_sha256: str
    device: str
    precision: str
    preprocessing: str
    status: Literal['available', 'no_spatial_signal']
    heatmap_png_base64: str
    content_box: List[int]
    width: int
    height: int
    limitation: str
    regions: List[ExplanationRegion] = Field(default_factory=list)
    summary: Optional[str] = None
    summary_basis: Optional[Literal['gradcam_spatial_v1']] = None
    coordinate_system: Optional[Literal['displayed_image']] = None
    distribution: Optional[Literal['none', 'concentrated', 'broad']] = None


# =====================================================================
# Authorization Helper
# =====================================================================
def verify_scan_access(scan_record: Dict[str, Any], current_user: Dict[str, Any]) -> None:
    """
    Enforce scan authorization:
    - Radiologists and Admins have institutional access to all scans.
    - Doctors are restricted to scans uploaded by themselves.
    """
    role = current_user.get("role", "")
    username = current_user.get("username", "")

    if role in ("radiologist", "admin"):
        return  # Authorized

    if role == "doctor":
        if scan_record.get("uploaded_by") == username:
            return  # Authorized owner
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You are not authorized to access scans uploaded by another practitioner."
        )

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Forbidden: Insufficient privileges to access patient scan records."
    )


# =====================================================================
# Endpoints
# =====================================================================
@router.post("", response_model=ScanMetadataResponse, status_code=status.HTTP_201_CREATED)
async def upload_scan(
    file: UploadFile = File(..., description="Chest X-Ray image file (PNG/JPEG)"),
    patient_id: str = Form(..., description="Pseudonymous patient identifier (e.g. ANON-10492)"),
    current_user: Dict[str, Any] = Depends(require_role("doctor", "radiologist", "admin")),
    storage: SecureImageStorage = Depends(get_storage),
    engine: DenseNetInferenceEngine = Depends(get_inference_engine)
) -> ScanMetadataResponse:
    """
    Upload and securely encrypt a patient chest X-ray image using AES-256-GCM.
    Enforces format validation, size restrictions, and patient ID pseudonyms.
    """
    # 1. Validate patient ID format
    try:
        clean_patient_id = validate_patient_id(patient_id)
    except InvalidIdentifierError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        ) from None

    # 2. Read bytes safely
    image_bytes = await file.read(MAX_IMAGE_SIZE_BYTES + 1)
    if len(image_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty."
        )

    if len(image_bytes) > MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Uploaded image exceeds the maximum limit ({MAX_IMAGE_SIZE_BYTES} bytes)."
        )

    # 3. Validate image content & format directly in memory
    try:
        engine.validate_and_decode_image(image_bytes)
    except InvalidImagePayloadError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Image validation failed: {str(e)}"
        ) from None

    # 4. Encrypt and store image
    try:
        record = storage.store_image(
            image_bytes=image_bytes,
            patient_id=clean_patient_id,
            uploaded_by=current_user["username"]
        )
        return ScanMetadataResponse(**record)
    except MaxFileSizeExceededError as e:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(e)) from None
    except StorageError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Secure storage error: {str(e)}") from None


@router.get("", response_model=List[ScanMetadataResponse])
def list_scans(
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: MetadataDB = Depends(get_db)
) -> List[ScanMetadataResponse]:
    """
    List scan records accessible to the authenticated user.
    Radiologists/Admins see all scans; Doctors see only scans they uploaded.
    """
    role = current_user.get("role", "")
    username = current_user.get("username", "")

    if role in ("radiologist", "admin"):
        scans = db.list_all_scans()
    elif role == "doctor":
        scans = db.list_scans_by_uploader(username)
    else:
        scans = []

    return [ScanMetadataResponse(**s) for s in scans]


@router.get("/{scan_id}", response_model=ScanMetadataResponse)
def get_scan(
    scan_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: MetadataDB = Depends(get_db)
) -> ScanMetadataResponse:
    """
    Retrieve metadata for an authorized scan.
    """
    try:
        clean_scan_id = validate_scan_id(scan_id)
        record = db.get_scan(clean_scan_id)
    except InvalidIdentifierError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid scan identifier format.") from None
    except ScanNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan record not found.") from None

    # Enforce RBAC access permissions
    verify_scan_access(record, current_user)
    return ScanMetadataResponse(**record)


@router.get('/{scan_id}/image')
def view_scan_image(scan_id: str,
                    current_user: Dict[str, Any] = Depends(get_current_user),
                    db: MetadataDB = Depends(get_db),
                    storage: SecureImageStorage = Depends(get_storage)) -> Response:
    # Authorize before reading or decrypting image bytes.
    record = get_scan(scan_id, current_user, db)
    try:
        raw, _ = storage.retrieve_image(record.scan_id)
        with Image.open(io.BytesIO(raw)) as image:
            media_type = {'PNG': 'image/png', 'JPEG': 'image/jpeg'}.get(image.format)
            image.verify()
        if media_type is None:
            raise ValueError('Unsupported image format')
    except (AuthenticationError, IntegrityVerificationError):
        raise HTTPException(status_code=409, detail='Stored image failed integrity verification.') from None
    except StorageError:
        raise HTTPException(status_code=503, detail='Stored image is unavailable.') from None
    except Exception:
        raise HTTPException(status_code=422, detail='Stored image cannot be displayed.') from None
    return Response(raw, media_type=media_type, headers={
        'Cache-Control': 'no-store, private', 'Pragma': 'no-cache',
        'Content-Disposition': 'inline', 'X-Content-Type-Options': 'nosniff'})


@router.post('/{scan_id}/explain', response_model=ExplanationResponse)
def explain_scan(scan_id: str, request: ExplanationRequest, response: Response,
                 user: Dict[str, Any] = Depends(require_role('doctor', 'radiologist', 'admin')),
                 db: MetadataDB = Depends(get_db), storage: SecureImageStorage = Depends(get_storage),
                 engine: DenseNetInferenceEngine = Depends(get_inference_engine),
                 _rate_limit: None = Depends(rate_limit_inference)) -> ExplanationResponse:
    record = get_scan(scan_id, user, db)  # Authorize before decrypting or computing.
    try:
        raw, _ = storage.retrieve_image(record.scan_id)
        result = engine.explain(raw, request.target_class, request.model_checkpoint_sha256)
    except (AuthenticationError, IntegrityVerificationError):
        raise HTTPException(status_code=409, detail='Stored image failed integrity verification.') from None
    except ExplanationMismatch as error:
        raise HTTPException(status_code=409, detail=str(error)) from None
    except InvalidImagePayloadError:
        raise HTTPException(status_code=422, detail='The stored image cannot be explained.') from None
    except StorageError:
        raise HTTPException(status_code=503, detail='Stored image is unavailable.') from None
    except Exception:
        raise HTTPException(status_code=503, detail='Explanation could not be generated. Screening results are unchanged.') from None
    response.headers['Cache-Control'] = 'no-store, private'
    response.headers['Pragma'] = 'no-cache'
    return ExplanationResponse(scan_id=record.scan_id, **result)


@router.post("/{scan_id}/predict", response_model=PredictionResponse)
def predict_scan(
    scan_id: str,
    current_user: Dict[str, Any] = Depends(require_role("doctor", "radiologist", "admin")),
    storage: SecureImageStorage = Depends(get_storage),
    engine: DenseNetInferenceEngine = Depends(get_inference_engine),
    db: MetadataDB = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_inference)
) -> PredictionResponse:
    """
    Retrieve an authorized encrypted scan, decrypt it in memory, and run DenseNet121 inference.
    Plaintext images are NEVER written to disk.
    Updates the database with the prediction result.
    """
    try:
        clean_scan_id = validate_scan_id(scan_id)
        record = db.get_scan(clean_scan_id)
    except InvalidIdentifierError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid scan identifier format.") from None
    except ScanNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan record not found.") from None

    # Check authorization
    verify_scan_access(record, current_user)

    # In-memory retrieval and authenticated decryption
    try:
        decrypted_bytes, _ = storage.retrieve_image(clean_scan_id)
    except AuthenticationError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Security Error: Encrypted image failed authentication tag verification. Ciphertext has been corrupted or tampered with."
        ) from None
    except IntegrityVerificationError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Security Error: Recovered image failed SHA-256 integrity verification."
        ) from None
    except StorageError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from None

    # Run in-memory DenseNet121 inference
    try:
        pred_result = engine.predict(decrypted_bytes)
    except InvalidImagePayloadError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Image decoding error: {str(e)}") from None
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Model inference failed: {type(e).__name__}") from None

    # Update database record with prediction outcome
    db.update_prediction(
        scan_id=clean_scan_id,
        predicted_class=pred_result["prediction"],
        probability=pred_result["pneumonia_probability"],
        status="PROCESSED"
    )

    return PredictionResponse(
        scan_id=clean_scan_id,
        patient_id=record["patient_id"],
        prediction=pred_result["prediction"],
        confidence=pred_result["confidence"],
        pneumonia_probability=pred_result["pneumonia_probability"],
        normal_probability=pred_result["normal_probability"],
        threshold_applied=pred_result["threshold_applied"],
        model_architecture=pred_result["model_architecture"],
        model_epoch=pred_result["model_epoch"],
        model_checkpoint_sha256=pred_result.get("model_checkpoint_sha256"),
        device=pred_result["device"],
        disclaimer=pred_result["disclaimer"],
        logit_margin=pred_result.get("logit_margin"),
        log_probability_normal=pred_result.get("log_probability_normal"),
        log_probability_pneumonia=pred_result.get("log_probability_pneumonia"),
        probabilities_calibrated=pred_result.get("probabilities_calibrated", False),
        score_interpretation=pred_result.get("score_interpretation", "uncalibrated_model_score")
    )
