/**
 * Centralized Typed API Client for the FastAPI Healthcare Backend
 * ISC Project: AI-Based Pneumonia Detection with Secure Storage & Transmission
 */

import {
  ApiError,
  HealthStatus,
  PredictionResult,
  ReadinessStatus,
  ScanMetadata,
  TokenResponse,
  UserProfile,
} from './types';

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/+$/, '') || 'http://127.0.0.1:8000';

/**
 * Parse response error payload safely to extract user-friendly error details
 */
async function parseErrorResponse(response: Response): Promise<string> {
  try {
    const data = await response.json();
    if (data && typeof data.detail === 'string') {
      return data.detail;
    }
    if (data && Array.isArray(data.detail)) {
      // Pydantic validation error array
      return data.detail
        .map((err: unknown) =>
          typeof err === 'object' && err !== null && 'msg' in err
            ? String((err as { msg: unknown }).msg)
            : JSON.stringify(err)
        )
        .join(', ');
    }
    if (data && data.message) {
      return String(data.message);
    }
    return `Server returned HTTP ${response.status} (${response.statusText})`;
  } catch {
    return `Server returned HTTP ${response.status} (${response.statusText || 'Unknown Error'})`;
  }
}

/**
 * Generic fetch wrapper with standard header injection and error transformation
 */
async function request<T>(
  endpoint: string,
  options: RequestInit = {},
  token?: string | null
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  // If body is NOT FormData and not already Content-Type set, set JSON
  if (options.body && !(options.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  try {
    const res = await fetch(url, {
      ...options,
      headers,
    });

    if (!res.ok) {
      const errorDetail = await parseErrorResponse(res);
      throw new ApiError(res.status, errorDetail);
    }

    // Handle 204 or empty responses
    if (res.status === 204) {
      return {} as T;
    }

    return (await res.json()) as T;
  } catch (err: unknown) {
    if (err instanceof ApiError) {
      throw err;
    }
    // Network errors or fetch failures
    throw new ApiError(
      0,
      `Unable to connect to backend server at ${API_BASE_URL}. Please ensure the FastAPI server is running.`
    );
  }
}

export const apiClient = {
  /**
   * Health Check (Liveness)
   */
  async checkHealth(): Promise<HealthStatus> {
    return request<HealthStatus>('/health');
  },

  /**
   * Health Check (Readiness: DB + Encryption Storage + Model)
   */
  async checkReadiness(): Promise<ReadinessStatus> {
    return request<ReadinessStatus>('/health/ready');
  },

  /**
   * Authenticate practitioner credentials and receive JWT
   */
  async login(username: string, password: string): Promise<TokenResponse> {
    return request<TokenResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
  },

  /**
   * Retrieve current authenticated practitioner profile and assigned RBAC role
   */
  async getMe(token: string): Promise<UserProfile> {
    return request<UserProfile>('/auth/me', { method: 'GET' }, token);
  },

  /**
   * List scans accessible to current practitioner:
   * - Doctors see only scans uploaded by themselves
   * - Radiologists and Admins see all scans
   */
  async listScans(token: string): Promise<ScanMetadata[]> {
    return request<ScanMetadata[]>('/scans', { method: 'GET' }, token);
  },

  /**
   * Retrieve single scan metadata
   */
  async getScan(scanId: string, token: string): Promise<ScanMetadata> {
    return request<ScanMetadata>(`/scans/${encodeURIComponent(scanId)}`, { method: 'GET' }, token);
  },

  /**
   * Upload raw Chest X-Ray image and associate with pseudonymous patient ID
   * Note: FormData is passed directly without setting Content-Type so browser sets boundary.
   */
  async uploadScan(file: File, patientId: string, token: string): Promise<ScanMetadata> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('patient_id', patientId.trim());

    return request<ScanMetadata>(
      '/scans',
      {
        method: 'POST',
        body: formData,
      },
      token
    );
  },

  /**
   * In-memory decryption and DenseNet121 AI inference on encrypted radiograph
   */
  async predictScan(scanId: string, token: string): Promise<PredictionResult> {
    return request<PredictionResult>(
      `/scans/${encodeURIComponent(scanId)}/predict`,
      {
        method: 'POST',
      },
      token
    );
  },
};
