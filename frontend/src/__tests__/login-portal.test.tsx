import React from 'react';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import LoginPage from '@/app/login/page';
import { AuthenticatedLayout } from '@/components/layout/authenticated-layout';
import { AuthProvider } from '@/context/auth-context';
import { getLoginPath, rememberLoginPortal, LOGIN_PORTAL_STORAGE_KEY } from '@/lib/login-portal';

const { mockReplace } = vi.hoisted(() => ({ mockReplace: vi.fn() }));
const router = { replace: mockReplace };
vi.mock('next/navigation', () => ({ useRouter: () => router, usePathname: () => '/' }));

describe('Login portal preference and protected routes', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    mockReplace.mockReset();
  });

  it('defaults to the staff portal on a first visit', () => {
    render(<LoginPage />);
    expect(mockReplace).toHaveBeenCalledWith('/login/staff');
  });

  it('ignores an invalid saved preference', () => {
    localStorage.setItem(LOGIN_PORTAL_STORAGE_KEY, 'https://example.com');
    expect(getLoginPath()).toBe('/login/staff');
  });

  it('keeps explicit login URLs working when storage is blocked', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('Storage disabled'); });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Storage disabled'); });
    expect(() => rememberLoginPortal('radiologist')).not.toThrow();
    expect(getLoginPath('radiologist')).toBe('/login/radiologist');
    expect(getLoginPath()).toBe('/login/staff');
  });

  it('redirects a refreshed protected page to the remembered radiologist portal without exposing its contents', () => {
    rememberLoginPortal('radiologist');
    render(<AuthProvider><AuthenticatedLayout><p>Private scans</p></AuthenticatedLayout></AuthProvider>);
    expect(screen.queryByText('Private scans')).not.toBeInTheDocument();
    expect(mockReplace).toHaveBeenCalledWith('/login/radiologist');
  });

  it('does not authenticate a new tab using a saved portal preference', () => {
    rememberLoginPortal('radiologist');
    render(<AuthProvider><AuthenticatedLayout><p>Private scans</p></AuthenticatedLayout></AuthProvider>);
    expect(screen.getByRole('heading', { name: 'Session Required' })).toBeInTheDocument();
    expect(screen.queryByText('Private scans')).not.toBeInTheDocument();
  });
});
