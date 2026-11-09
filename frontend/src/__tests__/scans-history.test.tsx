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
  useSearchParams: () => new URLSearchParams(),
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
      expect(screen.getAllByText('Pending')[0]).toBeInTheDocument();
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
    const processedFilterBtn = screen.getByRole('button', { name: /^Screened$/i });
    fireEvent.click(processedFilterBtn);

    expect(screen.queryByText('ANON-10001')).not.toBeInTheDocument();
    expect(screen.getAllByText('ANON-20002')[0]).toBeInTheDocument();
  });

  it('renders useful empty state when no radiographs exist', async () => {
    vi.spyOn(apiClient, 'listScans').mockResolvedValueOnce([]);

    render(<ScansHistoryPage />);

    await waitFor(() => {
      expect(screen.getByText(/no radiographs yet/i)).toBeInTheDocument();
      expect(screen.getByText(/upload first scan/i)).toBeInTheDocument();
    });
  });

  it('paginates the records and resets to the first page when searching', async () => {
    vi.spyOn(apiClient, 'listScans').mockResolvedValueOnce(Array.from({ length: 10 }, (_, index) => ({
      ...mockScans[0], scan_id: `scan-${index}`, patient_id: `ANON-${String(index).padStart(4, '0')}`,
    })));
    render(<ScansHistoryPage />);
    await waitFor(() => expect(screen.getByText('Page 1 of 2')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
    expect(screen.getByText('Page 2 of 2')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Search scans'), { target: { value: 'ANON-0000' } });
    expect(screen.getByText('Page 1 of 1')).toBeInTheDocument();
    expect(screen.getAllByText('ANON-0000')[0]).toBeInTheDocument();
  });

  it('shows a retryable error rather than an empty repository when loading fails', async () => {
    vi.spyOn(apiClient, 'listScans').mockRejectedValueOnce(new Error('Connection unavailable'));
    render(<ScansHistoryPage />);
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Connection unavailable'));
    expect(screen.queryByText('No radiographs yet')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });
});
