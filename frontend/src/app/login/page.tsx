'use client';

import React, { useState } from 'react';
import {
  Activity,
  Lock,
  User,
  Eye,
  EyeOff,
  AlertCircle,
  ShieldCheck,
  Stethoscope,
  Info,
} from 'lucide-react';
import { useAuth } from '@/context/auth-context';
import { ApiError } from '@/lib/types';

export default function LoginPage() {
  const { login } = useAuth();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    // Validation
    const cleanUsername = username.trim();
    if (!cleanUsername) {
      setErrorMessage('Please enter your staff username.');
      return;
    }
    if (!password) {
      setErrorMessage('Please enter your account password.');
      return;
    }

    setIsLoading(true);
    try {
      await login(cleanUsername, password);
      // login() handles GET /auth/me and redirect to /
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setErrorMessage(err.detail);
      } else if (err instanceof Error) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage('Authentication failed. Please verify credentials.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleDemoFill = (demoUser: string, demoPass: string) => {
    setUsername(demoUser);
    setPassword(demoPass);
    setErrorMessage(null);
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
            <h3 className="text-base font-semibold text-slate-900">Practitioner Login</h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Enter your institutional credentials to authenticate your session.
            </p>
          </div>

          {errorMessage && (
            <div className="mb-5 p-3.5 rounded-lg bg-rose-50 border border-rose-200 flex items-start space-x-2.5 text-rose-800 text-xs">
              <AlertCircle className="h-4 w-4 shrink-0 text-rose-600 mt-0.5" />
              <span>{errorMessage}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label
                htmlFor="username"
                className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5"
              >
                Staff Username
              </label>
              <div className="relative rounded-md shadow-2xs">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                  <User className="h-4 w-4" />
                </div>
                <input
                  id="username"
                  name="username"
                  type="text"
                  autoComplete="username"
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="e.g. doctor1 or radiologist1"
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
                  name="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter your password"
                  className="block w-full pl-9 pr-10 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500 text-slate-900 placeholder-slate-400"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute inset-y-0 right-0 pr-3 flex items-center text-slate-400 hover:text-slate-600 focus:outline-none"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
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

          {/* Quick-Fill Helper for Evaluation */}
          <div className="mt-6 pt-5 border-t border-slate-100">
            <div className="flex items-center space-x-1 text-slate-500 text-xs mb-2.5">
              <Info className="h-3.5 w-3.5 text-slate-400" />
              <span>Demonstration Accounts (Pre-Seeded):</span>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => handleDemoFill('doctor1', 'DoctorPassword123!')}
                className="flex items-center justify-center space-x-1.5 px-2.5 py-1.5 text-xs font-medium text-blue-700 bg-blue-50/70 hover:bg-blue-100 border border-blue-200/80 rounded-md transition-colors"
              >
                <Stethoscope className="h-3 w-3" />
                <span>Doctor Staff</span>
              </button>
              <button
                type="button"
                onClick={() => handleDemoFill('radiologist1', 'RadioPassword123!')}
                className="flex items-center justify-center space-x-1.5 px-2.5 py-1.5 text-xs font-medium text-teal-700 bg-teal-50/70 hover:bg-teal-100 border border-teal-200/80 rounded-md transition-colors"
              >
                <ShieldCheck className="h-3 w-3" />
                <span>Radiologist Staff</span>
              </button>
            </div>
          </div>
        </div>

        {/* Security & In-Memory Session Notice */}
        <div className="mt-4 text-center space-y-1">
          <p className="text-[11px] text-slate-500">
            <strong>Security Notice:</strong> Sessions are managed in-memory with signed JWT tokens. Refreshing the browser terminates the session for clinical data safety.
          </p>
        </div>
      </div>
    </div>
  );
}
