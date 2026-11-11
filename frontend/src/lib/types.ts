/**
 * TypeScript Data Models matching the FastAPI Backend Schemas
 * ISC Project: AI-Based Pneumonia Detection with Secure Storage & Transmission
 */

export type UserRole = 'doctor' | 'radiologist' | 'admin';

export interface UserProfile {
  user_id: string;
  username: string;
  role: UserRole;
  full_name?: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  role: UserRole;
  username: string;
  expires_in_minutes: number;
}

export interface AccountUpdate {
  full_name: string;
  username: string;
  current_password: string;
  new_password?: string;
}

export interface AccountUpdateResponse extends TokenResponse {
  user: UserProfile;
}

export interface ScanMetadata {
  scan_id: string;
  patient_id: string;
  file_size_bytes: number;
  format_version: number;
  created_at: string;
  prediction_status: 'PENDING' | 'PROCESSED' | string;
  predicted_class: 'NORMAL' | 'PNEUMONIA' | string | null;
  prediction_probability: number | null;
  uploaded_by: string;
}

export interface PredictionResult {
  scan_id: string;
  patient_id: string;
  prediction: 'NORMAL' | 'PNEUMONIA' | string;
  confidence: number;
  pneumonia_probability: number;
  normal_probability: number;
  threshold_applied: number;
  model_architecture: string;
  model_epoch: number;
  device: string;
  disclaimer: string;
  probabilities_calibrated?: boolean;
  model_checkpoint_sha256?: string | null;
  logit_margin?: number | null;
}

export interface HealthStatus {
  status: string;
}

export interface ReadinessStatus {
  status: string;
  components?: Record<string, string>;
  model?: {
    architecture: string;
    checkpoint_sha256: string;
    device: string;
    epoch: number;
    checkpoint_finalized: boolean | null;
    probabilities_calibrated: boolean;
  } | null;
}

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}
