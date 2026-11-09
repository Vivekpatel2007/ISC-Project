/**
 * Tests for In-Memory Authentication State Management
 * ISC Project: AI-Based Pneumonia Detection with Secure Storage & Transmission
 */

import React from 'react';
import { render, screen, act, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { AuthProvider, useAuth } from '@/context/auth-context';
import { apiClient } from '@/lib/api-client';

// Mock useRouter
const mockReplace = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({
    replace: mockReplace,
  }),
}));

function TestConsumer() {
  const { user, token, role, isAuthenticated, isLoading, login, logout, refreshProfile } = useAuth();
  return (
    <div>
      <span data-testid="auth-status">{isAuthenticated ? 'LOGGED_IN' : 'LOGGED_OUT'}</span>
      <span data-testid="username">{user?.username || 'NONE'}</span>
      <span data-testid="role">{role || 'NONE'}</span>
      <span data-testid="token">{token ? 'TOKEN_PRESENT' : 'NO_TOKEN'}</span>
      <span data-testid="loading">{String(isLoading)}</span>
      <input aria-label="Session notes" defaultValue="" />
      <button onClick={() => login('doctor1', 'DoctorPassword123!')}>Login</button>
      <button onClick={() => login('radiologist1', 'RadioPassword123!')}>Login radiologist</button>
      <button onClick={logout}>Logout</button>
      <button onClick={refreshProfile}>Refresh profile</button>
    </div>
  );
}

describe('AuthContext', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    mockReplace.mockReset();
    localStorage.clear();
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
    expect(mockReplace).toHaveBeenCalledWith('/');
  });

  it('clears all session state on logout and redirects to /login/staff', async () => {
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
    fireEvent.change(screen.getByLabelText('Session notes'), { target: { value: 'Previous account data' } });

    await act(async () => {
      screen.getByText('Logout').click();
    });

    expect(screen.getByTestId('auth-status').textContent).toBe('LOGGED_OUT');
    expect(screen.getByTestId('username').textContent).toBe('NONE');
    expect(screen.getByTestId('token').textContent).toBe('NO_TOKEN');
    expect(screen.getByLabelText('Session notes')).toHaveValue('');
    expect(mockReplace).toHaveBeenCalledWith('/login/staff');
  });

  it('ignores a login response that arrives after logout', async () => {
    let finishLogin!: () => void;
    vi.spyOn(apiClient, 'login').mockImplementationOnce(() => new Promise((resolve) => {
      finishLogin = () => resolve({
        access_token: 'late-token', token_type: 'bearer', role: 'doctor',
        username: 'doctor1', expires_in_minutes: 30,
      });
    }));
    const getMe = vi.spyOn(apiClient, 'getMe');
    render(<AuthProvider><TestConsumer /></AuthProvider>);
    fireEvent.click(screen.getByText('Login', { exact: true }));
    fireEvent.click(screen.getByText('Logout'));
    await act(async () => { finishLogin(); });

    expect(screen.getByTestId('auth-status')).toHaveTextContent('LOGGED_OUT');
    expect(screen.getByTestId('loading')).toHaveTextContent('false');
    expect(getMe).not.toHaveBeenCalled();
    expect(mockReplace).not.toHaveBeenCalledWith('/');
  });

  it('ignores a profile response from an unfinished login after logout', async () => {
    vi.spyOn(apiClient, 'login').mockResolvedValueOnce({
      access_token: 'doctor-token', token_type: 'bearer', role: 'doctor',
      username: 'doctor1', expires_in_minutes: 30,
    });
    let finishProfile!: () => void;
    vi.spyOn(apiClient, 'getMe').mockImplementationOnce(() => new Promise((resolve) => {
      finishProfile = () => resolve({ user_id: 'doctor-id', username: 'doctor1', role: 'doctor' });
    }));
    render(<AuthProvider><TestConsumer /></AuthProvider>);
    await act(async () => { screen.getByText('Login', { exact: true }).click(); });
    fireEvent.click(screen.getByText('Logout'));
    await act(async () => { finishProfile(); });

    expect(screen.getByTestId('auth-status')).toHaveTextContent('LOGGED_OUT');
    expect(screen.getByTestId('token')).toHaveTextContent('NO_TOKEN');
    expect(mockReplace).not.toHaveBeenCalledWith('/');
  });

  it.each(['resolve', 'reject'])('ignores a stale profile refresh that %ss after switching roles', async (outcome) => {
    vi.spyOn(apiClient, 'login')
      .mockResolvedValueOnce({
        access_token: 'doctor-token', token_type: 'bearer', role: 'doctor',
        username: 'doctor1', expires_in_minutes: 30,
      })
      .mockResolvedValueOnce({
        access_token: 'radio-token', token_type: 'bearer', role: 'radiologist',
        username: 'radiologist1', expires_in_minutes: 30,
      });
    let finishRefresh!: () => void;
    vi.spyOn(apiClient, 'getMe')
      .mockResolvedValueOnce({ user_id: 'doctor-id', username: 'doctor1', role: 'doctor' })
      .mockImplementationOnce(() => new Promise((resolve, reject) => {
        finishRefresh = () => outcome === 'resolve'
          ? resolve({ user_id: 'doctor-id', username: 'doctor1', role: 'doctor' })
          : reject(new Error('Expired old session'));
      }))
      .mockResolvedValueOnce({ user_id: 'radio-id', username: 'radiologist1', role: 'radiologist' });
    render(<AuthProvider><TestConsumer /></AuthProvider>);
    await act(async () => { screen.getByText('Login', { exact: true }).click(); });
    fireEvent.click(screen.getByText('Refresh profile'));
    fireEvent.click(screen.getByText('Logout'));
    await act(async () => { screen.getByText('Login radiologist').click(); });
    mockReplace.mockClear();
    await act(async () => { finishRefresh(); });

    expect(screen.getByTestId('auth-status')).toHaveTextContent('LOGGED_IN');
    expect(screen.getByTestId('username')).toHaveTextContent('radiologist1');
    expect(screen.getByTestId('role')).toHaveTextContent('radiologist');
    expect(mockReplace).not.toHaveBeenCalled();
  });
});
