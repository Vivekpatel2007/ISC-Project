"""
Secure Metadata Database Module (SQLite)
ISC Project: Secure Storage and Transmission of Medical Data

Privacy & Security Design:
1. Minimality: Stores strictly minimal metadata (pseudonymous IDs, hashes, timestamps).
2. Zero Key Storage: Cryptographic keys are NEVER written to the database.
3. Zero Patient PII: Names, DOB, addresses, and medical charts are excluded.
4. Injection Protection: 100% parameterized SQL queries; string interpolation is forbidden.
5. Path Traversal Defense: scan_id is strictly validated against safe patterns.
6. Reliability & Resource Safety: Explicit connection closing ensures no file locks linger on Windows.
"""

import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Union

from src.security.exceptions import (
    InvalidIdentifierError,
    ScanNotFoundError,
    StorageError,
)

# Strict regex patterns for identifiers to prevent SQL injection and path traversal
SCAN_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]{8,64}$")
PATIENT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]{3,64}$")


def validate_scan_id(scan_id: str) -> str:
    """Validate that scan_id is safe and contains no path traversal sequences or special characters."""
    if not isinstance(scan_id, str):
        raise InvalidIdentifierError("Scan ID must be a string.")
    cleaned = scan_id.strip()
    if not SCAN_ID_PATTERN.match(cleaned) or ".." in cleaned or "/" in cleaned or "\\" in cleaned:
        raise InvalidIdentifierError(f"Invalid scan ID format: '{scan_id}'. Path traversal sequences are strictly forbidden.")
    return cleaned


def validate_patient_id(patient_id: str) -> str:
    """Validate that patient_id conforms to pseudonymous identifier rules."""
    if not isinstance(patient_id, str):
        raise InvalidIdentifierError("Patient ID must be a string.")
    cleaned = patient_id.strip()
    if not PATIENT_ID_PATTERN.match(cleaned):
        raise InvalidIdentifierError(
            f"Invalid patient identifier: '{patient_id}'. Must be a pseudonymous code (e.g. 'ANON-10492')."
        )
    return cleaned


class MetadataDB:
    def __init__(self, db_path: Union[str, Path]):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        """
        Context manager that yields a connection within a transaction and guarantees
        the connection is closed on exit, preventing file locks on Windows.
        """
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Create the metadata schema and performance indexes."""
        with self._connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scans (
                    scan_id TEXT PRIMARY KEY,
                    patient_id TEXT NOT NULL,
                    encrypted_filename TEXT NOT NULL UNIQUE,
                    original_sha256 TEXT NOT NULL,
                    file_size_bytes INTEGER NOT NULL,
                    format_version INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    prediction_status TEXT NOT NULL DEFAULT 'PENDING',
                    predicted_class TEXT,
                    prediction_probability REAL
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_scans_patient_id ON scans(patient_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_scans_created_at ON scans(created_at);")

    def insert_scan(
        self,
        scan_id: str,
        patient_id: str,
        encrypted_filename: str,
        original_sha256: str,
        file_size_bytes: int,
        format_version: int = 1
    ) -> Dict[str, Any]:
        """
        Record metadata for a newly encrypted medical scan.
        """
        s_id = validate_scan_id(scan_id)
        p_id = validate_patient_id(patient_id)
        created_at = datetime.now(timezone.utc).isoformat()

        try:
            with self._connection() as conn:
                conn.execute("""
                    INSERT INTO scans (
                        scan_id, patient_id, encrypted_filename, original_sha256,
                        file_size_bytes, format_version, created_at, prediction_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING');
                """, (s_id, p_id, encrypted_filename, original_sha256, file_size_bytes, format_version, created_at))
        except sqlite3.IntegrityError as e:
            raise StorageError(f"Failed to record scan metadata: scan_id or filename collision. ({e})") from None
        except Exception as e:
            raise StorageError(f"Database error during scan insertion: {type(e).__name__}") from None

        return self.get_scan(s_id)

    def get_scan(self, scan_id: str) -> Dict[str, Any]:
        """
        Retrieve a scan record by its unique scan_id.
        """
        s_id = validate_scan_id(scan_id)
        try:
            with self._connection() as conn:
                cursor = conn.execute("SELECT * FROM scans WHERE scan_id = ?;", (s_id,))
                row = cursor.fetchone()
                if row is None:
                    raise ScanNotFoundError(f"Scan record '{s_id}' not found.")
                return dict(row)
        except ScanNotFoundError:
            raise
        except Exception as e:
            raise StorageError(f"Database query error: {type(e).__name__}") from None

    def list_scans_for_patient(self, patient_id: str) -> List[Dict[str, Any]]:
        """
        List all scan records for a given pseudonymous patient ID.
        """
        p_id = validate_patient_id(patient_id)
        with self._connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM scans WHERE patient_id = ? ORDER BY created_at DESC;",
                (p_id,)
            )
            return [dict(r) for r in cursor.fetchall()]

    def update_prediction(
        self,
        scan_id: str,
        predicted_class: str,
        probability: float,
        status: str = "PROCESSED"
    ) -> None:
        """
        Update the diagnosis prediction result for a scan.
        """
        s_id = validate_scan_id(scan_id)
        with self._connection() as conn:
            cursor = conn.execute("""
                UPDATE scans
                SET predicted_class = ?, prediction_probability = ?, prediction_status = ?
                WHERE scan_id = ?;
            """, (predicted_class, float(probability), status, s_id))
            if cursor.rowcount == 0:
                raise ScanNotFoundError(f"Scan record '{s_id}' not found.")

    def delete_scan(self, scan_id: str) -> None:
        """
        Delete a scan record from the database.
        """
        s_id = validate_scan_id(scan_id)
        with self._connection() as conn:
            conn.execute("DELETE FROM scans WHERE scan_id = ?;", (s_id,))
