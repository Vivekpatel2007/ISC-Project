/**
 * Tests for UploadPage Component
 * ISC Project: AI-Based Pneumonia Detection with Secure Storage & Transmission
 */

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import UploadPage from '@/app/upload/page';
import { AuthProvider } from '@/context/auth-context';

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: vi.fn(),
  }),
  usePathname: () => '/upload',
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
  AuthProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

// Provide mocked global URL.createObjectURL and revokeObjectURL
beforeEach(() => {
  global.URL.createObjectURL = vi.fn().mockReturnValue('blob:http://localhost:3000/mock-preview');
  global.URL.revokeObjectURL = vi.fn();
});

describe('UploadPage', () => {
  it('rejects invalid file format (e.g. text/plain)', async () => {
    render(
      <AuthProvider>
        <UploadPage />
      </AuthProvider>
    );

    const file = new File(['text content'], 'notes.txt', { type: 'text/plain' });
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;

    fireEvent.change(fileInput, { target: { files: [file] } });

    await waitFor(() => {
      expect(
        screen.getByText(/invalid file format\. supported formats are png and jpeg/i)
      ).toBeInTheDocument();
    });
  });

  it('rejects files larger than 20MB', async () => {
    render(
      <AuthProvider>
        <UploadPage />
      </AuthProvider>
    );

    // Create a mock large file
    const largeFile = new File([''], 'huge_xray.png', { type: 'image/png' });
    Object.defineProperty(largeFile, 'size', { value: 25 * 1024 * 1024 });

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(fileInput, { target: { files: [largeFile] } });

    await waitFor(() => {
      expect(screen.getByText(/exceeds the maximum allowed limit/i)).toBeInTheDocument();
    });
  });

  it('accepts valid PNG radiograph and creates temporary preview', async () => {
    render(
      <AuthProvider>
        <UploadPage />
      </AuthProvider>
    );

    const validFile = new File(['dummy bytes'], 'chest_xray.png', { type: 'image/png' });
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(fileInput, { target: { files: [validFile] } });

    await waitFor(() => {
      expect(screen.getByText('chest_xray.png')).toBeInTheDocument();
      expect(screen.getByAltText(/local radiograph preview/i)).toBeInTheDocument();
    });
  });

  it('validates pseudonymous patient ID format', async () => {
    render(
      <AuthProvider>
        <UploadPage />
      </AuthProvider>
    );

    const validFile = new File(['dummy bytes'], 'chest.png', { type: 'image/png' });
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(fileInput, { target: { files: [validFile] } });

    const patientInput = screen.getByLabelText(/pseudonymous patient identifier/i);
    // Invalid ID with special chars
    fireEvent.change(patientInput, { target: { value: 'BAD!ID#@' } });

    const submitBtn = screen.getByRole('button', { name: /upload & encrypt radiograph/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText(/invalid patient identifier format/i)).toBeInTheDocument();
    });
  });
});
