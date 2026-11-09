'use client';

import React, { useState, useRef, useEffect } from 'react';
import Link from 'next/link';
import {
  Activity,
  Lock,
  User,
  Eye,
  EyeOff,
  AlertCircle,
  ShieldCheck,
  Stethoscope,
} from 'lucide-react';
import { useAuth } from '@/context/auth-context';
import { ApiError } from '@/lib/types';
import { getLoginPath, rememberLoginPortal, type LoginPortal } from '@/lib/login-portal';

export function LoginForm({ portal }: { portal: LoginPortal }) {
  const { login } = useAuth();
  const isRadiologist = portal === 'radiologist';
  const formRef = useRef<HTMLFormElement>(null);

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const submitting = useRef(false);
  const pendingLogin = useRef<AbortController | null>(null);

  useEffect(() => {
    rememberLoginPortal(portal);
    const clearCredentials = () => {
      pendingLogin.current?.abort();
      pendingLogin.current = null;
      formRef.current?.reset();
      setUsername('');
      setPassword('');
      setShowPassword(false);
      setErrorMessage(null);
      setIsLoading(false);
      submitting.current = false;
    };
    // Clear both retained Next.js routes and native back/forward page restores.
    window.addEventListener('pagehide', clearCredentials);
    window.addEventListener('pageshow', clearCredentials);
    return () => {
      clearCredentials();
      window.removeEventListener('pagehide', clearCredentials);
      window.removeEventListener('pageshow', clearCredentials);
    };
  }, [portal]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (submitting.current) return;
    setErrorMessage(null);

    // Validation
    const cleanUsername = username.trim();
    if (!cleanUsername) {
      setErrorMessage(`Please enter your ${isRadiologist ? 'radiologist' : 'staff'} username.`);
      return;
    }
    if (!password) {
      setErrorMessage('Please enter your account password.');
      return;
    }

    submitting.current = true;
    const controller = new AbortController();
    pendingLogin.current = controller;
    setIsLoading(true);
    setShowPassword(false);
    try {
      await login(cleanUsername, password, portal, controller.signal);
      if (controller.signal.aborted || pendingLogin.current !== controller) return;
      // Next.js can retain this route's state after navigation.
      setUsername('');
      setPassword('');
    } catch (err: unknown) {
      if (controller.signal.aborted || pendingLogin.current !== controller) return;
      setPassword('');
      if (err instanceof ApiError) {
        setErrorMessage(err.detail);
      } else if (err instanceof Error) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage('Authentication failed. Please verify credentials.');
      }
    } finally {
      if (pendingLogin.current === controller) {
        pendingLogin.current = null;
        submitting.current = false;
        setIsLoading(false);
      }
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        {/* Brand Icon & Heading */}
        <div className="flex justify-center mb-2">
          <div className="h-12 w-12 rounded-xl bg-sky-600 flex items-center justify-center text-white shadow-md shadow-sky-100">
            <Activity className="h-7 w-7 stroke-[2.2]" />
          </div>
        </div>
        <h2 className="text-center text-2xl font-bold tracking-tight text-slate-900">
          PulmoScan
        </h2>
        <p className="mt-1 text-center text-xs text-slate-500 font-medium">
          Chest Radiography AI Screening & Secure Repository
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md px-4">
        <div className="bg-white py-8 px-6 shadow-xs border border-slate-200 rounded-xl sm:px-10">
          <div className="mb-6">
            <h1 className="text-base font-semibold text-slate-900">
              {isRadiologist ? 'Radiologist Login' : 'Staff Login'}
            </h1>
            <p className="text-xs text-slate-500 mt-0.5">
              {isRadiologist
                ? 'Sign in to review and screen scans across the institution.'
                : 'Sign in to upload and screen radiographs assigned to your account.'}
            </p>
          </div>

          <nav aria-label="Login portal" className="grid grid-cols-2 gap-2 mb-6">
            {([
              { portal: 'staff', label: 'Staff', icon: Stethoscope },
              { portal: 'radiologist', label: 'Radiologist', icon: ShieldCheck },
            ] as const).map((item) => (
              <Link
                key={item.portal}
                href={getLoginPath(item.portal)}
                aria-current={portal === item.portal ? 'page' : undefined}
                className={`flex items-center justify-center gap-2 rounded-lg border px-3 py-2 text-xs font-semibold transition-colors ${
                  portal === item.portal
                    ? 'border-sky-600 bg-sky-50 text-sky-800'
                    : 'border-slate-200 text-slate-600 hover:bg-slate-50'
                }`}
              >
                <item.icon className="h-4 w-4" aria-hidden="true" />
                {item.label}
              </Link>
            ))}
          </nav>

          {errorMessage && (
            <div role="alert" id="login-error" className="mb-5 p-3.5 rounded-lg bg-rose-50 border border-rose-200 flex items-start space-x-2.5 text-rose-800 text-xs">
              <AlertCircle className="h-4 w-4 shrink-0 text-rose-600 mt-0.5" />
              <span>{errorMessage}</span>
            </div>
          )}

          <form ref={formRef} autoComplete="off" onSubmit={handleSubmit} aria-busy={isLoading} aria-describedby={errorMessage ? 'login-error' : undefined} className="space-y-4">
            <div>
              <label
                htmlFor="username"
                className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5"
              >
                {isRadiologist ? 'Radiologist Username' : 'Staff Username'}
              </label>
              <div className="relative rounded-md shadow-2xs">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                  <User className="h-4 w-4" />
                </div>
                <input
                  id="username"
                  name={`${portal}-username`}
                  type="text"
                  autoComplete="off"
                  disabled={isLoading}
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder={isRadiologist ? 'Enter your radiologist username' : 'Enter your staff username'}
                  className="block w-full pl-9 pr-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500 text-slate-900 placeholder-slate-400"
                />
              </div>
            </div>

            <div>
              <label
                htmlFor="password"
                className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5"
              >
                Password
              </label>
              <div className="relative rounded-md shadow-2xs">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                  <Lock className="h-4 w-4" />
                </div>
                <input
                  id="password"
                  name={`${portal}-password`}
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="off"
                  disabled={isLoading}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter your password"
                  className="block w-full pl-9 pr-10 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500 text-slate-900 placeholder-slate-400"
                />
                <button
                  type="button"
                  disabled={isLoading}
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute inset-y-0 right-0 pr-3 flex items-center text-slate-400 hover:text-slate-600 focus:outline-none"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  aria-pressed={showPassword}
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="w-full flex justify-center items-center py-2.5 px-4 border border-transparent rounded-lg shadow-xs text-sm font-medium text-white bg-sky-600 hover:bg-sky-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-sky-500 transition-colors disabled:opacity-60 disabled:cursor-not-allowed mt-2"
            >
              {isLoading ? (
                <div className="flex items-center space-x-2">
                  <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent" />
                  <span>Authenticating...</span>
                </div>
              ) : (
                <span>Sign In to System</span>
              )}
            </button>
          </form>

        </div>

        {/* Security & In-Memory Session Notice */}
        <div className="mt-4 text-center space-y-1">
          <p className="text-[11px] text-slate-500">
            Your preferred login portal is remembered. You will need to sign in again after refreshing or reopening the app.
          </p>
        </div>
      </div>
    </div>
  );
}
