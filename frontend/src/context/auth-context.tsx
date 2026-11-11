'use client';

/**
 * Authentication Context & State Management
 * ISC Project: AI-Based Pneumonia Detection with Secure Storage & Transmission
 * 
 * Security Architecture:
 * 1. Tokens reside strictly in volatile JavaScript memory (React state).
 * 2. Neither access tokens nor passwords are ever committed to localStorage, sessionStorage, or cookies.
 * 3. Page refreshes clear the in-memory session intentionally for zero-persistence security.
 * 4. All authorization checks are enforced by the backend on every API request.
 */

import React, { createContext, useContext, useState, useCallback, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { apiClient } from '@/lib/api-client';
import { ApiError, UserProfile, UserRole, AccountUpdate } from '@/lib/types';
import { getLoginPath, portalForRole, rememberLoginPortal, type LoginPortal } from '@/lib/login-portal';

interface AuthContextValue {
  token: string | null;
  user: UserProfile | null;
  role: UserRole | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (username: string, password: string, portal?: LoginPortal, signal?: AbortSignal) => Promise<void>;
  logout: () => void;
  refreshProfile: () => Promise<void>;
  updateAccount: (change: AccountUpdate) => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<UserProfile | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [sessionVersion, setSessionVersion] = useState(0);
  const authAttempt = useRef(0);
  const currentToken = useRef<string | null>(null);
  const router = useRouter();

  const logout = useCallback(() => {
    const loginPath = user ? getLoginPath(portalForRole(user.role)) : getLoginPath();
    if (user) rememberLoginPortal(portalForRole(user.role));
    // Invalidate pending requests and unmount cached pages containing session data.
    authAttempt.current += 1;
    currentToken.current = null;
    setToken(null);
    setUser(null);
    setIsLoading(false);
    setSessionVersion((version) => version + 1);
    router.replace(loginPath);
  }, [router, user]);

  const login = useCallback(
    async (username: string, password: string, portal?: LoginPortal, signal?: AbortSignal) => {
      const attempt = ++authAttempt.current;
      setIsLoading(true);
      try {
        const tokenResp = await apiClient.login(username, password, signal);
        if (attempt !== authAttempt.current || signal?.aborted) return;
        const accessToken = tokenResp.access_token;
        
        // Immediately validate the token and load practitioner profile from GET /auth/me
        const profile = await apiClient.getMe(accessToken, signal);
        if (attempt !== authAttempt.current || signal?.aborted) return;

        if (!['doctor', 'radiologist', 'admin'].includes(profile.role)) {
          throw new ApiError(403, 'This account does not have access to PulmoScan. Contact your administrator.');
        }
        // Portal selection is a preference; only the backend profile determines access.
        const accountPortal = portalForRole(profile.role);
        if (portal && portal !== accountPortal) {
          throw new ApiError(403, `This account belongs to ${accountPortal === 'radiologist' ? 'Radiologist' : 'Staff'} Login. Please switch to that portal.`);
        }
        
        rememberLoginPortal(accountPortal);
        currentToken.current = accessToken;
        setToken(accessToken);
        setUser(profile);
        router.replace('/');
      } catch (err) {
        if (attempt !== authAttempt.current || signal?.aborted) return;
        // Clear state on failed attempt
        currentToken.current = null;
        setToken(null);
        setUser(null);
        throw err;
      } finally {
        if (attempt === authAttempt.current) setIsLoading(false);
      }
    },
    [router]
  );

  const refreshProfile = useCallback(async () => {
    if (!token) return;
    const attempt = authAttempt.current;
    try {
      const profile = await apiClient.getMe(token);
      if (attempt === authAttempt.current && currentToken.current === token) setUser(profile);
    } catch {
      if (attempt === authAttempt.current && currentToken.current === token) logout();
    }
  }, [token, logout]);

  const updateAccount = useCallback(async (change: AccountUpdate) => {
    if (!token) throw new ApiError(401, 'Sign in to update your account.');
    const attempt = authAttempt.current;
    const updated = await apiClient.updateAccount(change, token);
    if (attempt !== authAttempt.current || currentToken.current !== token) return;
    authAttempt.current += 1;
    currentToken.current = updated.access_token;
    setToken(updated.access_token);
    setUser(updated.user);
  }, [token]);

  const value: AuthContextValue = {
    token,
    user,
    role: user?.role || null,
    isAuthenticated: !!token && !!user,
    isLoading,
    login,
    logout,
    refreshProfile,
    updateAccount,
  };

  return (
    <AuthContext.Provider value={value}>
      <React.Fragment key={sessionVersion}>{children}</React.Fragment>
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
