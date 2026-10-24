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

import React, { createContext, useContext, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { apiClient } from '@/lib/api-client';
import { UserProfile, UserRole } from '@/lib/types';

interface AuthContextValue {
  token: string | null;
  user: UserProfile | null;
  role: UserRole | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<UserProfile | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const router = useRouter();

  const logout = useCallback(() => {
    // Clear all in-memory credentials immediately
    setToken(null);
    setUser(null);
    router.push('/login');
  }, [router]);

  const login = useCallback(
    async (username: string, password: string) => {
      setIsLoading(true);
      try {
        const tokenResp = await apiClient.login(username, password);
        const accessToken = tokenResp.access_token;
        
        // Immediately validate the token and load practitioner profile from GET /auth/me
        const profile = await apiClient.getMe(accessToken);
        
        setToken(accessToken);
        setUser(profile);
        router.push('/');
      } catch (err) {
        // Clear state on failed attempt
        setToken(null);
        setUser(null);
        throw err;
      } finally {
        setIsLoading(false);
      }
    },
    [router]
  );

  const refreshProfile = useCallback(async () => {
    if (!token) return;
    try {
      const profile = await apiClient.getMe(token);
      setUser(profile);
    } catch {
      logout();
    }
  }, [token, logout]);

  const value: AuthContextValue = {
    token,
    user,
    role: user?.role || null,
    isAuthenticated: !!token && !!user,
    isLoading,
    login,
    logout,
    refreshProfile,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
