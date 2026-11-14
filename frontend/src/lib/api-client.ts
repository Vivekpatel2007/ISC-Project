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
  AccountUpdate,
  AccountUpdateResponse,
  ExplanationResult,
} from './types';

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/+$/, '') || 'http://127.0.0.1:8000';

const unauthorizedListeners = new Set<(token: string) => void>();

/** Only the session owning this request may react to a rejected bearer token. */
export function onUnauthorized(listener: (token: string) => void): () => void {
  unauthorizedListeners.add(listener);
  return () => { unauthorizedListeners.delete(listener); };
}

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
  token?: string | null,
  responseType: 'json' | 'blob' = 'json',
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
      cache: 'no-store',
    });

    if (!res.ok) {
      const errorDetail = await parseErrorResponse(res);
      if (res.status === 401 && token) {
        unauthorizedListeners.forEach((listener) => listener(token));
      }
      throw new ApiError(res.status, errorDetail);
    }

    // Handle 204 or empty responses
    if (res.status === 204) {
      return {} as T;
    }

    return (responseType === 'blob' ? await res.blob() : await res.json()) as T;
  } catch (err: unknown) {
    if (options.signal?.aborted || (err instanceof DOMException && err.name === 'AbortError')) {
      throw err;
    }
    if (err instanceof ApiError) {
      throw err;
    }
    if (err instanceof SyntaxError) {
      throw new ApiError(502, 'The backend returned an unreadable response. Please retry the request.');
    }
    // Network errors or fetch failures
    throw new ApiError(
      0,
      `Unable to connect to backend server at ${API_BASE_URL}. Please ensure the FastAPI server is running.`
    );
  }
}

export const apiClient = {
  async explainScan(scanId: string, targetClass: string, checkpoint: string, token: string, signal?: AbortSignal): Promise<ExplanationResult> {
    return request<ExplanationResult>(`/scans/${encodeURIComponent(scanId)}/explain`, {
      method: 'POST', cache: 'no-store', signal,
      body: JSON.stringify({target_class: targetClass, model_checkpoint_sha256: checkpoint}),
    }, token);
  },
  async renamePatient(patientId: string, newId: string, token: string): Promise<{patient_id: string; updated_scans: number}> {
    return request(`/patients/${encodeURIComponent(patientId)}`, {method: 'PUT', body: JSON.stringify({patient_id: newId})}, token);
  },
  async deletePatient(patientId: string, token: string): Promise<{deleted_scans: number}> {
    return request(`/patients/${encodeURIComponent(patientId)}`, {method: 'DELETE'}, token);
  },
  async updateAccount(change: AccountUpdate, token: string): Promise<AccountUpdateResponse> {
    return request<AccountUpdateResponse>('/auth/me', {method: 'PUT', body: JSON.stringify(change)}, token);
  },

  async getScanImage(scanId: string, token: string, signal?: AbortSignal): Promise<Blob> {
    return request<Blob>(`/scans/${encodeURIComponent(scanId)}/image`,
      {method: 'GET', cache: 'no-store', signal}, token, 'blob');
  },

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
  async login(username: string, password: string, signal?: AbortSignal): Promise<TokenResponse> {
    return request<TokenResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
      ...(signal ? { signal } : {}),
    });
  },

  /**
   * Retrieve current authenticated practitioner profile and assigned RBAC role
   */
  async getMe(token: string, signal?: AbortSignal): Promise<UserProfile> {
    return request<UserProfile>('/auth/me', { method: 'GET', ...(signal ? { signal } : {}) }, token);
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
