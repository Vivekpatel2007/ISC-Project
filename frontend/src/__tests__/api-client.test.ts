/**
 * Unit & Mocked Integration Tests for PulmoScan API Client
 * ISC Project: AI-Based Pneumonia Detection with Secure Storage & Transmission
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiClient, API_BASE_URL } from '@/lib/api-client';

describe('apiClient', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('performs successful login and returns TokenResponse', async () => {
    const mockToken = {
      access_token: 'fake-jwt-token-123',
      token_type: 'bearer',
      role: 'doctor',
      username: 'doctor1',
      expires_in_minutes: 30,
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockToken,
    } as Response);

    const res = await apiClient.login('doctor1', 'DoctorPassword123!');
    expect(res.access_token).toBe('fake-jwt-token-123');
    expect(res.role).toBe('doctor');
    expect(fetch).toHaveBeenCalledWith(
      `${API_BASE_URL}/auth/login`,
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ username: 'doctor1', password: 'DoctorPassword123!' }),
      })
    );
  });

  it('handles 401 unauthorized login error with detail extraction', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      statusText: 'Unauthorized',
      json: async () => ({ detail: 'Incorrect username or password.' }),
    } as Response);

    await expect(apiClient.login('doctor1', 'WrongPassword!')).rejects.toThrow(
      'Incorrect username or password.'
    );
  });

  it('fetches practitioner profile with Authorization header', async () => {
    const mockProfile = {
      user_id: 'usr-123-abc',
      username: 'doctor1',
      role: 'doctor',
      full_name: 'Dr. Sarah Chen, MD',
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockProfile,
    } as Response);

    const profile = await apiClient.getMe('valid-token');
    expect(profile.username).toBe('doctor1');
    expect(profile.role).toBe('doctor');
    expect(fetch).toHaveBeenCalledWith(
      `${API_BASE_URL}/auth/me`,
      expect.objectContaining({
        method: 'GET',
        headers: expect.objectContaining({ Authorization: 'Bearer valid-token' }),
      })
    );
  });

  it('handles network disconnection gracefully', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('Failed to fetch'));

    await expect(apiClient.checkHealth()).rejects.toThrow(
      /Unable to connect to backend server/
    );
  });

  it('uploads scan with FormData without manual Content-Type override', async () => {
    const mockScan = {
      scan_id: 'scan-uuid-999',
      patient_id: 'ANON-10492',
      file_size_bytes: 4096,
      format_version: 1,
      created_at: '2026-10-24T08:00:00Z',
      prediction_status: 'PENDING',
      predicted_class: null,
      prediction_probability: null,
      uploaded_by: 'doctor1',
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => mockScan,
    } as Response);

    const file = new File(['fake-bytes'], 'chest.png', { type: 'image/png' });
    const result = await apiClient.uploadScan(file, 'ANON-10492', 'valid-token');

    expect(result.scan_id).toBe('scan-uuid-999');
    expect(result.patient_id).toBe('ANON-10492');

    const lastCall = vi.mocked(fetch).mock.calls[0];
    const headers = lastCall[1]?.headers as Record<string, string>;
    expect(headers['Authorization']).toBe('Bearer valid-token');
    // Crucial check: Content-Type must NOT be application/json or hardcoded multipart
    expect(headers['Content-Type']).toBeUndefined();
    expect(lastCall[1]?.body).toBeInstanceOf(FormData);
  });

  it('triggers DenseNet121 inference and returns clinical prediction response', async () => {
    const mockPrediction = {
      scan_id: 'scan-uuid-999',
      patient_id: 'ANON-10492',
      prediction: 'PNEUMONIA',
      confidence: 0.9412,
      pneumonia_probability: 0.9412,
      normal_probability: 0.0588,
      threshold_applied: 0.4,
      model_architecture: 'densenet121',
      model_epoch: 5,
      device: 'cuda',
      disclaimer: 'AI-assisted screening output for clinical decision support.',
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockPrediction,
    } as Response);

    const result = await apiClient.predictScan('scan-uuid-999', 'valid-token');
    expect(result.prediction).toBe('PNEUMONIA');
    expect(result.pneumonia_probability).toBeCloseTo(0.9412);
    expect(result.threshold_applied).toBe(0.4);
    expect(result.disclaimer).toContain('AI-assisted screening');
  });

  it('handles 409 ciphertext tampering detection during prediction', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      statusText: 'Conflict',
      json: async () => ({
        detail:
          'Security Error: Encrypted image failed authentication tag verification. Ciphertext has been corrupted or tampered with.',
      }),
    } as Response);

    await expect(apiClient.predictScan('tampered-scan', 'valid-token')).rejects.toThrow(
      /failed authentication tag verification/
    );
  });
});
