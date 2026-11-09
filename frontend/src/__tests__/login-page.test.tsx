import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import LoginPage from '@/app/login/page';
import StaffLoginPage from '@/app/login/staff/page';
import RadiologistLoginPage from '@/app/login/radiologist/page';
import { AuthProvider, useAuth } from '@/context/auth-context';
import { apiClient } from '@/lib/api-client';
import { ApiError, type UserProfile } from '@/lib/types';
import { LOGIN_PORTAL_STORAGE_KEY } from '@/lib/login-portal';

const { mockReplace } = vi.hoisted(() => ({ mockReplace: vi.fn() }));
const router = { replace: mockReplace };
vi.mock('next/navigation', () => ({ useRouter: () => router }));

function SessionStatus() {
  const { isAuthenticated, logout } = useAuth();
  return <><output data-testid="session">{isAuthenticated ? 'signed-in' : 'signed-out'}</output><button onClick={logout}>Logout</button></>;
}

function enterCredentials(username = 'doctor1', password = 'DoctorPassword123!') {
  fireEvent.change(screen.getByLabelText(/username/i), { target: { value: username } });
  fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: password } });
}

function mockLogin(role: 'doctor' | 'radiologist' = 'doctor') {
  const username = role === 'doctor' ? 'doctor1' : 'radiologist1';
  vi.spyOn(apiClient, 'login').mockResolvedValueOnce({
    access_token: 'test-token', token_type: 'bearer', role, username, expires_in_minutes: 30,
  });
  vi.spyOn(apiClient, 'getMe').mockResolvedValueOnce({ user_id: `${role}-id`, username, role });
}

describe('Login portals', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    mockReplace.mockReset();
    localStorage.clear();
  });

  it.each(['staff', 'radiologist'] as const)('opens %s with blank fields and real portal navigation', (portal) => {
    render(<AuthProvider>{portal === 'staff' ? <StaffLoginPage /> : <RadiologistLoginPage />}</AuthProvider>);
    expect(screen.getByRole('heading', { name: portal === 'staff' ? 'Staff Login' : 'Radiologist Login' })).toBeInTheDocument();
    expect(screen.getByLabelText(/username/i)).toHaveValue('');
    expect(screen.getByLabelText(/^password$/i)).toHaveValue('');
    expect(screen.getByLabelText(/^password$/i)).toHaveAttribute('autocomplete', 'off');
    expect(screen.getByRole('link', { name: 'Staff', exact: true })).toHaveAttribute('href', '/login/staff');
    expect(screen.getByRole('link', { name: 'Radiologist', exact: true })).toHaveAttribute('href', '/login/radiologist');
    expect(screen.getByRole('link', { name: portal === 'staff' ? 'Staff' : 'Radiologist', exact: true })).toHaveAttribute('aria-current', 'page');
  });

  it('remembers only the radiologist portal across a fresh mount and resolves /login to it', () => {
    const { unmount } = render(<AuthProvider><RadiologistLoginPage /></AuthProvider>);
    enterCredentials('radiologist1', 'RadioPassword123!');
    expect(Object.keys(localStorage)).toEqual([LOGIN_PORTAL_STORAGE_KEY]);
    expect(localStorage.getItem(LOGIN_PORTAL_STORAGE_KEY)).toBe('radiologist');
    unmount();
    const freshPage = render(<AuthProvider><RadiologistLoginPage /></AuthProvider>);
    expect(screen.getByRole('heading', { name: 'Radiologist Login' })).toBeInTheDocument();
    expect(screen.getByLabelText(/username/i)).toHaveValue('');
    expect(screen.getByLabelText(/^password$/i)).toHaveValue('');
    freshPage.unmount();
    render(<LoginPage />);
    expect(mockReplace).toHaveBeenCalledWith('/login/radiologist');
  });

  it('clears entered credentials when switching between portals', () => {
    const { rerender } = render(<AuthProvider><RadiologistLoginPage /></AuthProvider>);
    enterCredentials('radiologist1', 'RadioPassword123!');
    rerender(<AuthProvider><StaffLoginPage /></AuthProvider>);
    expect(screen.getByLabelText(/username/i)).toHaveValue('');
    expect(screen.getByLabelText(/^password$/i)).toHaveValue('');
    expect(localStorage.getItem(LOGIN_PORTAL_STORAGE_KEY)).toBe('staff');
    rerender(<AuthProvider><RadiologistLoginPage /></AuthProvider>);
    expect(screen.getByLabelText(/username/i)).toHaveValue('');
    expect(screen.getByLabelText(/^password$/i)).toHaveValue('');
  });

  it.each(['pagehide', 'pageshow'])('clears credentials and visibility on browser %s', (eventName) => {
    render(<AuthProvider><RadiologistLoginPage /></AuthProvider>);
    enterCredentials('radiologist1', 'RadioPassword123!');
    fireEvent.click(screen.getByLabelText('Show password'));
    act(() => { window.dispatchEvent(new Event(eventName)); });
    expect(screen.getByLabelText(/username/i)).toHaveValue('');
    expect(screen.getByLabelText(/^password$/i)).toHaveValue('');
    expect(screen.getByLabelText(/^password$/i)).toHaveAttribute('type', 'password');
    expect(localStorage.getItem(LOGIN_PORTAL_STORAGE_KEY)).toBe('radiologist');
  });

  it('toggles password visibility', () => {
    render(<AuthProvider><StaffLoginPage /></AuthProvider>);
    fireEvent.click(screen.getByLabelText('Show password'));
    expect(screen.getByLabelText(/^password$/i)).toHaveAttribute('type', 'text');
    fireEvent.click(screen.getByLabelText('Hide password'));
    expect(screen.getByLabelText(/^password$/i)).toHaveAttribute('type', 'password');
  });

  it('validates a missing username', () => {
    render(<AuthProvider><StaffLoginPage /></AuthProvider>);
    fireEvent.submit(screen.getByRole('button', { name: /sign in to system/i }).closest('form')!);
    expect(screen.getByRole('alert')).toHaveTextContent('Please enter your staff username.');
  });

  it('clears the password after failed authentication and announces the error', async () => {
    vi.spyOn(apiClient, 'login').mockRejectedValueOnce(new ApiError(401, 'Incorrect username or password.'));
    render(<AuthProvider><RadiologistLoginPage /></AuthProvider>);
    enterCredentials('radiologist1', 'WrongPassword');
    fireEvent.click(screen.getByRole('button', { name: /sign in to system/i }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Incorrect username or password.'));
    expect(screen.getByLabelText(/^password$/i)).toHaveValue('');
    expect(screen.getByLabelText(/username/i)).toHaveValue('radiologist1');
  });

  it.each(['doctor', 'radiologist'] as const)('clears %s credentials on success and returns to the correct portal on logout', async (role) => {
    mockLogin(role);
    render(<AuthProvider>{role === 'doctor' ? <StaffLoginPage /> : <RadiologistLoginPage />}<SessionStatus /></AuthProvider>);
    enterCredentials(role === 'doctor' ? 'doctor1' : 'radiologist1', role === 'doctor' ? 'DoctorPassword123!' : 'RadioPassword123!');
    fireEvent.click(screen.getByLabelText('Show password'));
    fireEvent.click(screen.getByRole('button', { name: /sign in to system/i }));
    await waitFor(() => expect(screen.getByTestId('session')).toHaveTextContent('signed-in'));
    expect(screen.getByLabelText(/username/i)).toHaveValue('');
    expect(screen.getByLabelText(/^password$/i)).toHaveValue('');
    expect(screen.getByLabelText(/^password$/i)).toHaveAttribute('type', 'password');
    fireEvent.click(screen.getByText('Logout'));
    expect(mockReplace).toHaveBeenLastCalledWith(`/login/${role === 'doctor' ? 'staff' : 'radiologist'}`);
    expect(screen.getByTestId('session')).toHaveTextContent('signed-out');
    expect(screen.getByLabelText(/^password$/i)).toHaveValue('');
    expect(Object.keys(localStorage)).toEqual([LOGIN_PORTAL_STORAGE_KEY]);
  });

  it.each(['staff', 'radiologist'] as const)('rejects a backend account role that does not match the %s portal', async (portal) => {
    const oppositeRole = portal === 'staff' ? 'radiologist' : 'doctor';
    // Even a login response claiming the selected role cannot override /auth/me.
    vi.spyOn(apiClient, 'login').mockResolvedValueOnce({
      access_token: 'test-token', token_type: 'bearer', role: portal === 'staff' ? 'doctor' : 'radiologist',
      username: 'test-user', expires_in_minutes: 30,
    });
    vi.spyOn(apiClient, 'getMe').mockResolvedValueOnce({ user_id: 'test-id', username: 'test-user', role: oppositeRole });
    render(<AuthProvider>{portal === 'staff' ? <StaffLoginPage /> : <RadiologistLoginPage />}<SessionStatus /></AuthProvider>);
    enterCredentials('test-user', 'TestPassword123!');
    fireEvent.click(screen.getByRole('button', { name: /sign in to system/i }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(`This account belongs to ${portal === 'staff' ? 'Radiologist' : 'Staff'} Login.`));
    expect(screen.getByTestId('session')).toHaveTextContent('signed-out');
    expect(screen.getByLabelText(/^password$/i)).toHaveValue('');
    expect(mockReplace).not.toHaveBeenCalledWith('/');
  });

  it('prevents duplicate sign-ins and disables fields while a request is pending', async () => {
    let finishLogin!: () => void;
    vi.spyOn(apiClient, 'login').mockImplementationOnce(() => new Promise((resolve) => {
      finishLogin = () => resolve({ access_token: 'test-token', token_type: 'bearer', role: 'doctor', username: 'doctor1', expires_in_minutes: 30 });
    }));
    vi.spyOn(apiClient, 'getMe').mockResolvedValueOnce({ user_id: 'doctor-id', username: 'doctor1', role: 'doctor' });
    render(<AuthProvider><StaffLoginPage /></AuthProvider>);
    enterCredentials();
    const form = screen.getByRole('button', { name: /sign in to system/i }).closest('form')!;
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(apiClient.login).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText(/username/i)).toBeDisabled();
    expect(screen.getByLabelText(/^password$/i)).toBeDisabled();
    await act(async () => { finishLogin(); });
    expect(screen.getByLabelText(/username/i)).toBeEnabled();
  });

  it('rejects an unrecognized backend role without installing a session', async () => {
    vi.spyOn(apiClient, 'login').mockResolvedValueOnce({
      access_token: 'test-token', token_type: 'bearer', role: 'doctor', username: 'test-user', expires_in_minutes: 30,
    });
    vi.spyOn(apiClient, 'getMe').mockResolvedValueOnce({
      user_id: 'test-id', username: 'test-user', role: 'guest',
    } as unknown as UserProfile);
    render(<AuthProvider><StaffLoginPage /><SessionStatus /></AuthProvider>);
    enterCredentials('test-user', 'TestPassword123!');
    fireEvent.click(screen.getByRole('button', { name: /sign in to system/i }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('This account does not have access to PulmoScan.'));
    expect(screen.getByTestId('session')).toHaveTextContent('signed-out');
    expect(mockReplace).not.toHaveBeenCalledWith('/');
  });

  it('allows an administrator to use Staff Login', async () => {
    vi.spyOn(apiClient, 'login').mockResolvedValueOnce({
      access_token: 'admin-token', token_type: 'bearer', role: 'admin', username: 'administrator', expires_in_minutes: 30,
    });
    vi.spyOn(apiClient, 'getMe').mockResolvedValueOnce({
      user_id: 'admin-id', username: 'administrator', role: 'admin',
    });
    render(<AuthProvider><StaffLoginPage /><SessionStatus /></AuthProvider>);
    enterCredentials('administrator', 'TestPassword123!');
    fireEvent.click(screen.getByRole('button', { name: /sign in to system/i }));
    await waitFor(() => expect(screen.getByTestId('session')).toHaveTextContent('signed-in'));
    expect(mockReplace).toHaveBeenCalledWith('/');
  });

  it('cancels pending login when switching portals and ignores its late result', async () => {
    let finishLogin!: () => void;
    const login = vi.spyOn(apiClient, 'login').mockImplementationOnce(() => new Promise((resolve) => {
      finishLogin = () => resolve({ access_token: 'late-token', token_type: 'bearer', role: 'doctor', username: 'doctor1', expires_in_minutes: 30 });
    }));
    const getMe = vi.spyOn(apiClient, 'getMe');
    const { rerender } = render(<AuthProvider><StaffLoginPage /><SessionStatus /></AuthProvider>);
    enterCredentials();
    fireEvent.click(screen.getByRole('button', { name: /sign in to system/i }));
    const signal = login.mock.calls[0][2]!;
    rerender(<AuthProvider><RadiologistLoginPage /><SessionStatus /></AuthProvider>);
    expect(signal.aborted).toBe(true);
    enterCredentials('radiologist1', 'RadioPassword123!');
    await act(async () => { finishLogin(); });
    expect(screen.getByTestId('session')).toHaveTextContent('signed-out');
    expect(screen.getByLabelText(/username/i)).toHaveValue('radiologist1');
    expect(screen.getByLabelText(/^password$/i)).toHaveValue('RadioPassword123!');
    expect(getMe).not.toHaveBeenCalled();
    expect(mockReplace).not.toHaveBeenCalledWith('/');
  });
});
