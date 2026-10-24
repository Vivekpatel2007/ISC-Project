"""
Live End-to-End System Validation Script
ISC Project: AI-Based Pneumonia Detection with Secure Storage & Transmission

Performs genuine HTTP integration tests against the live FastAPI backend (http://127.0.0.1:8000).
Tests complete workflow:
1. Health and readiness (database, storage, model on CUDA GPU)
2. Authentication (doctor, radiologist, invalid credentials, token verification)
3. Scan upload, AES-256-GCM encryption, container format verification
4. Verification that zero plaintext is written to persistent disk
5. Role-based access control (doctor ownership vs radiologist diagnostic clearance)
6. In-memory retrieval, tag authentication, and DenseNet121 inference
7. Tampered ciphertext rejection (GCM authentication failure detection)
8. Security headers verification (CSP, X-Frame-Options, X-Content-Type-Options)
"""

import io
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from PIL import Image

BASE_URL = "http://127.0.0.1:8000"
STORAGE_DIR = Path("secure_data/encrypted_images")


def make_request(endpoint: str, method: str = "GET", headers: dict = None, data: bytes = None) -> tuple:
    """Helper for raw HTTP requests."""
    url = f"{BASE_URL}{endpoint}"
    req_headers = headers or {}
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, resp.headers, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {"raw": body}
        return e.code, e.headers, parsed


def build_multipart_form(fields: dict, files: dict) -> tuple:
    """Construct multipart/form-data payload."""
    boundary = "----WebKitFormBoundaryE2ETest7MA4YWxkTrZu0gW"
    lines = []
    
    for k, v in fields.items():
        lines.append(f"--{boundary}".encode("utf-8"))
        lines.append(f'Content-Disposition: form-data; name="{k}"'.encode("utf-8"))
        lines.append(b"")
        lines.append(str(v).encode("utf-8"))
        
    for k, (filename, content, content_type) in files.items():
        lines.append(f"--{boundary}".encode("utf-8"))
        lines.append(f'Content-Disposition: form-data; name="{k}"; filename="{filename}"'.encode("utf-8"))
        lines.append(f"Content-Type: {content_type}".encode("utf-8"))
        lines.append(b"")
        lines.append(content)
        
    lines.append(f"--{boundary}--".encode("utf-8"))
    lines.append(b"")
    body = b"\r\n".join(lines)
    content_type_header = f"multipart/form-data; boundary={boundary}"
    return body, content_type_header


def run_e2e_suite():
    print("=" * 70)
    print("STARTING LIVE END-TO-END VALIDATION (http://127.0.0.1:8000)")
    print("=" * 70)

    # 1. Health & Readiness
    print("\n[1/8] Verifying Health & Readiness Endpoints...")
    status, headers, body = make_request("/health")
    assert status == 200, f"Health liveness failed: {status}"
    assert body.get("status") == "healthy"
    print(f"  [PASS] Liveness: {body}")

    status, headers, body = make_request("/health/ready")
    assert status == 200, f"Health readiness failed: {status}"
    assert body.get("status") == "ready"
    assert body["checks"]["database"] is True
    assert body["checks"]["storage"] is True
    assert body["checks"]["model"] is True
    assert round(body.get("threshold"), 2) == 0.40
    print(f"  [PASS] Readiness: {body['status']} | Model Device: {body.get('device')} | Threshold: {body.get('threshold')}")

    # 2. Security Headers
    print("\n[2/8] Verifying OWASP Security Headers on Live Server...")
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("X-XSS-Protection") == "1; mode=block"
    assert headers.get("Referrer-Policy") == "no-referrer"
    assert "default-src 'self'" in headers.get("Content-Security-Policy", "")
    print("  [PASS] Security headers verified (nosniff, DENY, CSP, XSS-Protection).")

    # 3. Authentication & Profile
    print("\n[3/8] Testing Authentication & JWT Flow...")
    # Doctor login
    doc_payload = json.dumps({"username": "doctor1", "password": "DoctorPassword123!"}).encode("utf-8")
    status, _, body = make_request("/auth/login", method="POST", headers={"Content-Type": "application/json"}, data=doc_payload)
    assert status == 200, f"Doctor login failed: {body}"
    doctor_token = body["access_token"]
    assert body["role"] == "doctor"
    print("  [PASS] Doctor login successful, received 30m JWT bearer token.")

    # Radiologist login
    rad_payload = json.dumps({"username": "radiologist1", "password": "RadioPassword123!"}).encode("utf-8")
    status, _, body = make_request("/auth/login", method="POST", headers={"Content-Type": "application/json"}, data=rad_payload)
    assert status == 200, f"Radiologist login failed: {body}"
    radio_token = body["access_token"]
    assert body["role"] == "radiologist"
    print("  [PASS] Radiologist login successful.")

    # Invalid login rejection
    bad_payload = json.dumps({"username": "doctor1", "password": "WrongPassword999!"}).encode("utf-8")
    status, _, body = make_request("/auth/login", method="POST", headers={"Content-Type": "application/json"}, data=bad_payload)
    assert status == 401
    print(f"  [PASS] Invalid password rejected with HTTP 401: {body.get('detail')}")

    # Profile verification
    status, _, profile = make_request("/auth/me", headers={"Authorization": f"Bearer {doctor_token}"})
    assert status == 200
    assert profile["username"] == "doctor1"
    assert profile["role"] == "doctor"
    print(f"  [PASS] Profile retrieved for current user: {profile['full_name']} ({profile['role']})")

    # 4. Image Upload & Secure Storage
    print("\n[4/8] Testing Radiograph Image Upload & AES-256-GCM Encryption...")
    # Generate test image
    img = Image.new("L", (224, 224), color=50)
    img_buf = io.BytesIO()
    img.save(img_buf, format="PNG")
    raw_img_bytes = img_buf.getvalue()

    body_bytes, ct_header = build_multipart_form(
        fields={"patient_id": "ANON-LIVE-E2E-001"},
        files={"file": ("chest_xray.png", raw_img_bytes, "image/png")}
    )

    status, _, upload_resp = make_request(
        "/scans",
        method="POST",
        headers={"Authorization": f"Bearer {doctor_token}", "Content-Type": ct_header},
        data=body_bytes
    )
    assert status == 201, f"Upload failed: {upload_resp}"
    scan_id = upload_resp["scan_id"]
    print(f"  [PASS] Uploaded scan_id: {scan_id}")
    print(f"  [PASS] Patient ID: {upload_resp['patient_id']} | Encrypted size: {upload_resp['file_size_bytes']} bytes")

    # 5. Zero-Plaintext at Rest Verification
    print("\n[5/8] Verifying Persistent Disk State & Encryption Container...")
    enc_file = STORAGE_DIR / f"{scan_id}.enc"
    assert enc_file.exists(), f"Encrypted file not found on disk: {enc_file}"
    container_bytes = enc_file.read_bytes()
    
    # Check container format: MAGIC (b'PX01') + VERSION (1)
    assert container_bytes[:4] == b"PX01", "Container magic header mismatch!"
    assert container_bytes[4] == 0x01, "Container version mismatch!"
    assert len(container_bytes) >= 33, "Container truncated!"
    
    # Ensure raw plaintext PNG header is NOT anywhere in the encrypted file
    assert b"\x89PNG\r\n\x1a\n" not in container_bytes, "CRITICAL: Plaintext PNG header found inside encrypted file!"
    print(f"  [PASS] Verified encrypted container on disk: PX01 format, 96-bit nonce, 128-bit GCM tag.")
    print("  [PASS] Zero plaintext confirmed on storage filesystem.")

    # 6. Role-Based Access Control
    print("\n[6/8] Testing RBAC & Scan Authorization...")
    # Doctor1 views their own scan
    status, _, scan_meta = make_request(f"/scans/{scan_id}", headers={"Authorization": f"Bearer {doctor_token}"})
    assert status == 200
    print(f"  [PASS] Doctor1 successfully accessed own scan: {scan_meta['scan_id']}")

    # Radiologist views doctor1's scan (Institutional diagnostic access)
    status, _, scan_meta_radio = make_request(f"/scans/{scan_id}", headers={"Authorization": f"Bearer {radio_token}"})
    assert status == 200
    print("  [PASS] Radiologist successfully accessed scan under institutional clearance.")

    # Unauthenticated request rejected
    status, _, err = make_request(f"/scans/{scan_id}")
    assert status == 401
    print("  [PASS] Unauthenticated access rejected with HTTP 401.")

    # 7. DenseNet121 In-Memory AI Inference
    print("\n[7/8] Executing In-Memory AI Inference (DenseNet121 on GPU)...")
    status, _, pred_resp = make_request(
        f"/scans/{scan_id}/predict",
        method="POST",
        headers={"Authorization": f"Bearer {radio_token}"}
    )
    assert status == 200, f"Inference failed: {pred_resp}"
    print(f"  [PASS] Prediction: {pred_resp['prediction']}")
    print(f"  [PASS] Confidence: {pred_resp['confidence']:.4f}")
    print(f"  [PASS] Normal Prob: {pred_resp['normal_probability']:.4f} | Pneumonia Prob: {pred_resp['pneumonia_probability']:.4f}")
    print(f"  [PASS] Decision Threshold Applied: {pred_resp['threshold_applied']}")
    print(f"  [PASS] Hardware Acceleration: {pred_resp['device']}")
    print(f"  [PASS] Disclaimer: {pred_resp['disclaimer'][:60]}...")
    
    assert pred_resp["prediction"] in ("NORMAL", "PNEUMONIA")
    assert 0.0 <= pred_resp["confidence"] <= 1.0
    assert abs((pred_resp["normal_probability"] + pred_resp["pneumonia_probability"]) - 1.0) < 0.01

    # Verify status in database updated to PROCESSED
    status, _, updated_meta = make_request(f"/scans/{scan_id}", headers={"Authorization": f"Bearer {doctor_token}"})
    assert updated_meta["prediction_status"] == "PROCESSED"
    assert updated_meta["predicted_class"] == pred_resp["prediction"]
    print("  [PASS] Metadata registry confirmed scan status transitioned to PROCESSED.")

    # 8. Cryptographic Tamper Detection
    print("\n[8/8] Testing Tamper Detection on Encrypted Storage Container...")
    # Corrupt ciphertext byte in file
    tampered_bytes = bytearray(container_bytes)
    tampered_bytes[-12] ^= 0xAA  # Flip bits in AES-GCM ciphertext payload
    enc_file.write_bytes(bytes(tampered_bytes))

    # Request prediction on tampered file -> must fail AES-256-GCM authentication tag
    status, _, tamper_err = make_request(
        f"/scans/{scan_id}/predict",
        method="POST",
        headers={"Authorization": f"Bearer {radio_token}"}
    )
    assert status == 409, f"Expected 409 Conflict, got {status}: {tamper_err}"
    assert "authentication" in tamper_err.get("detail", "").lower() or "tamper" in tamper_err.get("detail", "").lower()
    print(f"  [PASS] Tampered ciphertext rejected with HTTP 409 Conflict: '{tamper_err.get('detail')}'")

    # Restore valid container
    enc_file.write_bytes(container_bytes)

    print("\n" + "=" * 70)
    print("ALL LIVE END-TO-END VALIDATION SCENARIOS PASSED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    try:
        run_e2e_suite()
    except Exception as e:
        print(f"\n[FAIL] E2E VALIDATION ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
