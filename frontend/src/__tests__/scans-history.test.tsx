/**
 * Tests for ScansHistoryPage Component
 * ISC Project: AI-Based Pneumonia Detection with Secure Storage & Transmission
 */

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import ScansHistoryPage from '@/app/scans/page';
import { apiClient } from '@/lib/api-client';
import { ScanMetadata } from '@/lib/types';

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: vi.fn(),
  }),
  usePathname: () => '/scans',
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

const mockScans: ScanMetadata[] = [
  {
    scan_id: 'scan-aaa-111',
    patient_id: 'ANON-10001',
    file_size_bytes: 40960,
    format_version: 1,
    created_at: '2026-10-24T08:00:00Z',
    prediction_status: 'PENDING',
    predicted_class: null,
    prediction_probability: null,
    uploaded_by: 'doctor1',
  },
  {
    scan_id: 'scan-bbb-222',
    patient_id: 'ANON-20002',
    file_size_bytes: 51200,
    format_version: 1,
    created_at: '2026-10-24T08:15:00Z',
    prediction_status: 'PROCESSED',
    predicted_class: 'PNEUMONIA',
    prediction_probability: 0.9412,
    uploaded_by: 'doctor1',
  },
];

describe('ScansHistoryPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders scans retrieved from API in responsive list', async () => {
    vi.spyOn(apiClient, 'listScans').mockResolvedValueOnce(mockScans);

    render(<ScansHistoryPage />);

    await waitFor(() => {
      expect(screen.getAllByText('ANON-10001')[0]).toBeInTheDocument();
      expect(screen.getAllByText('ANON-20002')[0]).toBeInTheDocument();
      expect(screen.getAllByText('PENDING')[0]).toBeInTheDocument();
      expect(screen.getAllByText(/PNEUMONIA/i)[0]).toBeInTheDocument();
    });
  });

  it('filters scan records by pseudonymous patient ID', async () => {
    vi.spyOn(apiClient, 'listScans').mockResolvedValueOnce(mockScans);

    render(<ScansHistoryPage />);

    await waitFor(() => {
      expect(screen.getAllByText('ANON-10001')[0]).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText(/search by patient id/i);
    fireEvent.change(searchInput, { target: { value: '20002' } });

    expect(screen.queryByText('ANON-10001')).not.toBeInTheDocument();
    expect(screen.getAllByText('ANON-20002')[0]).toBeInTheDocument();
  });

  it('filters scan records by prediction status button', async () => {
    vi.spyOn(apiClient, 'listScans').mockResolvedValueOnce(mockScans);

    render(<ScansHistoryPage />);

    await waitFor(() => {
      expect(screen.getAllByText('ANON-10001')[0]).toBeInTheDocument();
    });

    // Click PROCESSED status filter button
    const processedFilterBtn = screen.getByRole('button', { name: /^PROCESSED$/i });
    fireEvent.click(processedFilterBtn);

    expect(screen.queryByText('ANON-10001')).not.toBeInTheDocument();
    expect(screen.getAllByText('ANON-20002')[0]).toBeInTheDocument();
  });

  it('renders useful empty state when no radiographs exist', async () => {
    vi.spyOn(apiClient, 'listScans').mockResolvedValueOnce([]);

    render(<ScansHistoryPage />);

    await waitFor(() => {
      expect(screen.getByText(/no matching scans found/i)).toBeInTheDocument();
      expect(screen.getByText(/upload first scan/i)).toBeInTheDocument();
    });
  });
});
