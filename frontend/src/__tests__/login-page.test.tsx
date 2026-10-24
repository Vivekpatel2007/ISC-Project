/**
 * Tests for LoginPage Component
 * ISC Project: AI-Based Pneumonia Detection with Secure Storage & Transmission
 */

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import LoginPage from '@/app/login/page';
import { AuthProvider } from '@/context/auth-context';
import { apiClient } from '@/lib/api-client';
import { ApiError } from '@/lib/types';

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: vi.fn(),
  }),
}));

describe('LoginPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders login form elements and branding', () => {
    render(
      <AuthProvider>
        <LoginPage />
      </AuthProvider>
    );

    expect(screen.getByText('PulmoScan')).toBeInTheDocument();
    expect(screen.getByLabelText(/staff username/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^password$/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sign in to system/i })).toBeInTheDocument();
  });

  it('toggles password visibility when eye button is clicked', () => {
    render(
      <AuthProvider>
        <LoginPage />
      </AuthProvider>
    );

    const passwordInput = screen.getByLabelText(/^password$/i) as HTMLInputElement;
    expect(passwordInput.type).toBe('password');

    const toggleBtn = screen.getByLabelText(/show password/i);
    fireEvent.click(toggleBtn);
    expect(passwordInput.type).toBe('text');

    const hideBtn = screen.getByLabelText(/hide password/i);
    fireEvent.click(hideBtn);
    expect(passwordInput.type).toBe('password');
  });

  it('shows error message if username is empty on submit', async () => {
    render(
      <AuthProvider>
        <LoginPage />
      </AuthProvider>
    );

    const submitBtn = screen.getByRole('button', { name: /sign in to system/i });
    const form = submitBtn.closest('form');
    fireEvent.submit(form!);

    await waitFor(() => {
      expect(screen.getByText(/please enter your staff username/i)).toBeInTheDocument();
    });
  });

  it('populates fields when demo credentials button is clicked', () => {
    render(
      <AuthProvider>
        <LoginPage />
      </AuthProvider>
    );

    const doctorBtn = screen.getByRole('button', { name: /doctor staff/i });
    fireEvent.click(doctorBtn);

    const usernameInput = screen.getByLabelText(/staff username/i) as HTMLInputElement;
    const passwordInput = screen.getByLabelText(/^password$/i) as HTMLInputElement;

    expect(usernameInput.value).toBe('doctor1');
    expect(passwordInput.value).toBe('DoctorPassword123!');
  });

  it('displays API error alert when authentication fails', async () => {
    vi.spyOn(apiClient, 'login').mockRejectedValueOnce(
      new ApiError(401, 'Incorrect username or password.')
    );

    render(
      <AuthProvider>
        <LoginPage />
      </AuthProvider>
    );

    const usernameInput = screen.getByLabelText(/staff username/i);
    const passwordInput = screen.getByLabelText(/^password$/i);
    const submitBtn = screen.getByRole('button', { name: /sign in to system/i });

    fireEvent.change(usernameInput, { target: { value: 'doctor1' } });
    fireEvent.change(passwordInput, { target: { value: 'WrongPassword' } });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText('Incorrect username or password.')).toBeInTheDocument();
    });
  });
});
