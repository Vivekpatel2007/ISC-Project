/**
 * Tests for In-Memory Authentication State Management
 * ISC Project: AI-Based Pneumonia Detection with Secure Storage & Transmission
 */

import React from 'react';
import { render, screen, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { AuthProvider, useAuth } from '@/context/auth-context';
import { apiClient } from '@/lib/api-client';

// Mock useRouter
const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
  }),
}));

function TestConsumer() {
  const { user, token, role, isAuthenticated, login, logout } = useAuth();
  return (
    <div>
      <span data-testid="auth-status">{isAuthenticated ? 'LOGGED_IN' : 'LOGGED_OUT'}</span>
      <span data-testid="username">{user?.username || 'NONE'}</span>
      <span data-testid="role">{role || 'NONE'}</span>
      <span data-testid="token">{token ? 'TOKEN_PRESENT' : 'NO_TOKEN'}</span>
      <button onClick={() => login('doctor1', 'DoctorPassword123!')}>Login</button>
      <button onClick={logout}>Logout</button>
    </div>
  );
}

describe('AuthContext', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    mockPush.mockReset();
  });

  it('initializes in an unauthenticated logged-out state with null token', () => {
    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );

    expect(screen.getByTestId('auth-status').textContent).toBe('LOGGED_OUT');
    expect(screen.getByTestId('username').textContent).toBe('NONE');
    expect(screen.getByTestId('token').textContent).toBe('NO_TOKEN');
  });

  it('updates in-memory credentials on successful login and redirects to /', async () => {
    vi.spyOn(apiClient, 'login').mockResolvedValueOnce({
      access_token: 'secret-token-123',
      token_type: 'bearer',
      role: 'doctor',
      username: 'doctor1',
      expires_in_minutes: 30,
    });

    vi.spyOn(apiClient, 'getMe').mockResolvedValueOnce({
      user_id: 'usr-doc-1',
      username: 'doctor1',
      role: 'doctor',
      full_name: 'Dr. Sarah Chen, MD',
    });

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );

    await act(async () => {
      screen.getByText('Login').click();
    });

    expect(screen.getByTestId('auth-status').textContent).toBe('LOGGED_IN');
    expect(screen.getByTestId('username').textContent).toBe('doctor1');
    expect(screen.getByTestId('role').textContent).toBe('doctor');
    expect(screen.getByTestId('token').textContent).toBe('TOKEN_PRESENT');
    expect(mockPush).toHaveBeenCalledWith('/');
  });

  it('clears all session state on logout and redirects to /login', async () => {
    vi.spyOn(apiClient, 'login').mockResolvedValueOnce({
      access_token: 'secret-token-123',
      token_type: 'bearer',
      role: 'doctor',
      username: 'doctor1',
      expires_in_minutes: 30,
    });

    vi.spyOn(apiClient, 'getMe').mockResolvedValueOnce({
      user_id: 'usr-doc-1',
      username: 'doctor1',
      role: 'doctor',
      full_name: 'Dr. Sarah Chen, MD',
    });

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );

    await act(async () => {
      screen.getByText('Login').click();
    });
    expect(screen.getByTestId('auth-status').textContent).toBe('LOGGED_IN');

    await act(async () => {
      screen.getByText('Logout').click();
    });

    expect(screen.getByTestId('auth-status').textContent).toBe('LOGGED_OUT');
    expect(screen.getByTestId('username').textContent).toBe('NONE');
    expect(screen.getByTestId('token').textContent).toBe('NO_TOKEN');
    expect(mockPush).toHaveBeenCalledWith('/login');
  });
});
