/**
 * Tests for ScanDetailPage & AI Screening Component
 * ISC Project: AI-Based Pneumonia Detection with Secure Storage & Transmission
 */

import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import ScanDetailPage from '@/app/scans/[id]/page';
import { apiClient } from '@/lib/api-client';
import { ApiError, PredictionResult, ScanMetadata } from '@/lib/types';

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: vi.fn(),
  }),
  usePathname: () => '/scans/scan-123',
}));

vi.mock('@/context/auth-context', () => ({
  useAuth: () => ({
    token: 'mock-valid-token',
    user: { user_id: 'usr-1', username: 'doctor1', role: 'doctor', full_name: 'Dr. Sarah Chen' },
    role: 'doctor',
    isAuthenticated: true,
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
    refreshProfile: vi.fn(),
  }),
}));

const mockScanRecord: ScanMetadata = {
  scan_id: 'scan-123-abc',
  patient_id: 'ANON-99999',
  file_size_bytes: 65536,
  format_version: 1,
  created_at: '2026-10-24T09:00:00Z',
  prediction_status: 'PENDING',
  predicted_class: null,
  prediction_probability: null,
  uploaded_by: 'doctor1',
};

const mockPredictionResult: PredictionResult = {
  scan_id: 'scan-123-abc',
  patient_id: 'ANON-99999',
  prediction: 'PNEUMONIA',
  confidence: 0.954,
  pneumonia_probability: 0.954,
  normal_probability: 0.046,
  threshold_applied: 0.4,
  model_architecture: 'densenet121',
  model_epoch: 5,
  device: 'cuda',
  disclaimer:
    'AI-assisted screening output for clinical decision support. Not a standalone or definitive medical diagnosis.',
};

describe('ScanDetailPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(apiClient, 'getScan').mockResolvedValue(mockScanRecord);
  });

  it('renders authorized metadata from GET /scans/{scan_id}', async () => {
    const mockParams = { id: 'scan-123-abc' };
    render(<ScanDetailPage params={mockParams} />);

    await waitFor(
      () => {
        expect(screen.getAllByText('ANON-99999')[0]).toBeInTheDocument();
        expect(screen.getAllByText(/scan-123-abc/i)[0]).toBeInTheDocument();
        expect(screen.getByText('64 KB')).toBeInTheDocument();
        expect(screen.getAllByText(/AES-256-GCM/i)[0]).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /run ai screening/i })).toBeInTheDocument();
      },
      { timeout: 3000 }
    );
  });

  it('triggers DenseNet121 inference on button click and displays prediction card', async () => {
    vi.spyOn(apiClient, 'predictScan').mockResolvedValueOnce(mockPredictionResult);

    const mockParams = { id: 'scan-123-abc' };
    render(<ScanDetailPage params={mockParams} />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /run ai screening/i })).toBeInTheDocument();
    });

    const predictBtn = screen.getByRole('button', { name: /run ai screening/i });
    await act(async () => {
      fireEvent.click(predictBtn);
    });

    await waitFor(
      () => {
        expect(screen.getByText(/DenseNet121 AI Screening Output/i)).toBeInTheDocument();
        expect(screen.getByText(/^PNEUMONIA$/)).toBeInTheDocument();
        expect(screen.getByText(/95.40%/i)).toBeInTheDocument();
        expect(screen.getByText(/Mandatory Clinical Disclaimer/i)).toBeInTheDocument();
        expect(screen.getByText(/Decision Threshold:/i)).toBeInTheDocument();
        expect(screen.getByText('0.4')).toBeInTheDocument();
      },
      { timeout: 3000 }
    );
  });

  it('displays tampering conflict error if ciphertext fails GCM authentication (409)', async () => {
    vi.spyOn(apiClient, 'predictScan').mockRejectedValueOnce(
      new ApiError(
        409,
        'Security Error: Encrypted image failed authentication tag verification. Ciphertext has been corrupted or tampered with.'
      )
    );

    const mockParams = { id: 'scan-123-abc' };
    render(<ScanDetailPage params={mockParams} />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /run ai screening/i })).toBeInTheDocument();
    });

    const predictBtn = screen.getByRole('button', { name: /run ai screening/i });
    await act(async () => {
      fireEvent.click(predictBtn);
    });

    await waitFor(
      () => {
        expect(screen.getByText(/Integrity Tampering Error \(409\)/i)).toBeInTheDocument();
        expect(
          screen.getByText(/failed AES-GCM authentication tag verification/i)
        ).toBeInTheDocument();
      },
      { timeout: 3000 }
    );
  });

  it('keeps a successful result visible when the subsequent metadata refresh fails', async () => {
    vi.spyOn(apiClient, 'getScan').mockResolvedValueOnce(mockScanRecord).mockRejectedValueOnce(new Error('Status refresh unavailable'));
    vi.spyOn(apiClient, 'predictScan').mockResolvedValueOnce(mockPredictionResult);
    render(<ScanDetailPage params={{ id: 'scan-123-abc' }} />);
    fireEvent.click(await screen.findByRole('button', { name: /run ai screening/i }));
    await waitFor(() => expect(screen.getByText('95.40%')).toBeInTheDocument());
    expect(screen.getByText(/Screening completed. The latest scan status could not be refreshed/i)).toBeInTheDocument();
    expect(screen.queryByText('Screening could not complete')).not.toBeInTheDocument();
  });

  it('removes the previous result if a rerun detects corrupted ciphertext', async () => {
    vi.spyOn(apiClient, 'predictScan').mockResolvedValueOnce(mockPredictionResult).mockRejectedValueOnce(new ApiError(409, 'Corrupted ciphertext'));
    render(<ScanDetailPage params={{ id: 'scan-123-abc' }} />);
    fireEvent.click(await screen.findByRole('button', { name: /run ai screening/i }));
    await screen.findByText('95.40%');
    fireEvent.click(screen.getByRole('button', { name: /re-run ai screening/i }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Integrity Tampering Error'));
    expect(screen.queryByText('95.40%')).not.toBeInTheDocument();
  });

  it("shows loading feedback and removes the old error while retrying scan details", async () => {
    let finishLoading!: () => void;
    vi.spyOn(apiClient, "getScan")
      .mockRejectedValueOnce(new Error("Connection unavailable"))
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            finishLoading = () => resolve(mockScanRecord);
          }),
      );
    render(<ScanDetailPage params={{ id: "scan-123-abc" }} />);
    fireEvent.click(await screen.findByRole("button", { name: "Try again" }));
    expect(screen.getByRole("status")).toHaveTextContent(
      "Loading scan details...",
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    await act(async () => {
      finishLoading();
    });
    expect(
      screen.getByRole("heading", { name: "ANON-99999" }),
    ).toBeInTheDocument();
  });
});
