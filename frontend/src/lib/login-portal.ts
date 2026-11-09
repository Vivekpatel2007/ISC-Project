import type { UserRole } from './types';

export type LoginPortal = 'staff' | 'radiologist';

export const LOGIN_PORTAL_STORAGE_KEY = 'pulmoscan.login-portal';

export function getRememberedLoginPortal(): LoginPortal {
  try {
    return window.localStorage.getItem(LOGIN_PORTAL_STORAGE_KEY) === 'radiologist'
      ? 'radiologist'
      : 'staff';
  } catch {
    return 'staff';
  }
}

export function rememberLoginPortal(portal: LoginPortal): void {
  try {
    // This is a UI preference. Never store credentials, tokens, or account data here.
    window.localStorage.setItem(LOGIN_PORTAL_STORAGE_KEY, portal);
  } catch {
    // The explicit portal URL still works when browser storage is unavailable.
  }
}

export function portalForRole(role: UserRole): LoginPortal {
  return role === 'radiologist' ? 'radiologist' : 'staff';
}

export function getLoginPath(portal = getRememberedLoginPortal()): string {
  return `/login/${portal}`;
}
