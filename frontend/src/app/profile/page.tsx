'use client';

import React from 'react';
import {
  Shield,
  Stethoscope,
  FileCheck2,
  Lock,
  LogOut,
} from 'lucide-react';
import { useAuth } from '@/context/auth-context';
import { AuthenticatedLayout } from '@/components/layout/authenticated-layout';

export default function ProfilePage() {
  const { user, role, logout } = useAuth();

  return (
    <AuthenticatedLayout>
      <div className="max-w-3xl mx-auto space-y-6">
        <div>
          <h1 className="text-xl md:text-2xl font-bold text-slate-900 tracking-tight">
            Staff Credentials & Access
          </h1>
          <p className="text-xs md:text-sm text-slate-500 mt-1">
            Authenticated practitioner profile and cryptographically verified role permissions.
          </p>
        </div>

        {/* Profile Card */}
        <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-xs space-y-6">
          <div className="flex items-center space-x-4 pb-6 border-b border-slate-100">
            <div className="h-16 w-16 rounded-full bg-sky-100 text-sky-700 flex items-center justify-center font-bold text-2xl">
              {user?.full_name ? user.full_name[0] : user?.username?.[0]?.toUpperCase() || 'U'}
            </div>
            <div>
              <h2 className="text-lg font-bold text-slate-900">
                {user?.full_name || user?.username}
              </h2>
              <div className="flex items-center space-x-2 mt-1">
                <span
                  className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold uppercase ${
                    role === 'doctor'
                      ? 'bg-blue-100 text-blue-800'
                      : role === 'radiologist'
                      ? 'bg-teal-100 text-teal-800'
                      : 'bg-slate-100 text-slate-800'
                  }`}
                >
                  {role} Role
                </span>
                <span className="text-xs text-slate-400">•</span>
                <span className="text-xs text-slate-500 font-mono">@{user?.username}</span>
              </div>
            </div>
          </div>

          {/* Profile Fields from GET /auth/me */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
            <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-100 space-y-1">
              <span className="text-slate-400 font-medium uppercase text-[10px] tracking-wider">
                Internal User UUID
              </span>
              <p className="font-mono text-slate-800 break-all">{user?.user_id || 'N/A'}</p>
            </div>

            <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-100 space-y-1">
              <span className="text-slate-400 font-medium uppercase text-[10px] tracking-wider">
                Full Name / Title
              </span>
              <p className="font-semibold text-slate-800">{user?.full_name || 'Not provided'}</p>
            </div>

            <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-100 space-y-1">
              <span className="text-slate-400 font-medium uppercase text-[10px] tracking-wider">
                Staff Username
              </span>
              <p className="font-mono font-medium text-slate-800">{user?.username}</p>
            </div>

            <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-100 space-y-1">
              <span className="text-slate-400 font-medium uppercase text-[10px] tracking-wider">
                RBAC Access Level
              </span>
              <p className="font-semibold text-slate-800 capitalize">{role} Tier</p>
            </div>
          </div>

          {/* Role-Specific Capabilities */}
          <div className="pt-2">
            <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider mb-3">
              Role Authorization Capabilities (RBAC)
            </h3>
            <div className="space-y-2 text-xs">
              {role === 'doctor' ? (
                <>
                  <div className="p-3 rounded-lg bg-blue-50/70 border border-blue-100 flex items-start space-x-2 text-blue-900">
                    <FileCheck2 className="h-4 w-4 text-blue-700 shrink-0 mt-0.5" />
                    <div>
                      <span className="font-semibold">Upload & Encrypt Scans:</span>
                      <p className="text-blue-800 text-[11px] mt-0.5">
                        Authorized to upload patient chest radiographs with pseudonymous IDs.
                      </p>
                    </div>
                  </div>
                  <div className="p-3 rounded-lg bg-blue-50/70 border border-blue-100 flex items-start space-x-2 text-blue-900">
                    <Shield className="h-4 w-4 text-blue-700 shrink-0 mt-0.5" />
                    <div>
                      <span className="font-semibold">Owner-Restricted Scope:</span>
                      <p className="text-blue-800 text-[11px] mt-0.5">
                        Authorized to view and trigger DenseNet121 screening strictly on radiographs uploaded by your staff account.
                      </p>
                    </div>
                  </div>
                </>
              ) : role === 'radiologist' ? (
                <>
                  <div className="p-3 rounded-lg bg-teal-50/70 border border-teal-100 flex items-start space-x-2 text-teal-900">
                    <FileCheck2 className="h-4 w-4 text-teal-700 shrink-0 mt-0.5" />
                    <div>
                      <span className="font-semibold">Institutional Repository Review:</span>
                      <p className="text-teal-800 text-[11px] mt-0.5">
                        Diagnostic clearance to view all patient radiographs across the healthcare institution.
                      </p>
                    </div>
                  </div>
                  <div className="p-3 rounded-lg bg-teal-50/70 border border-teal-100 flex items-start space-x-2 text-teal-900">
                    <Stethoscope className="h-4 w-4 text-teal-700 shrink-0 mt-0.5" />
                    <div>
                      <span className="font-semibold">Diagnostic AI Inference:</span>
                      <p className="text-teal-800 text-[11px] mt-0.5">
                        Authorized to trigger DenseNet121 evaluation on any institutional scan.
                      </p>
                    </div>
                  </div>
                </>
              ) : (
                <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 text-slate-700">
                  Standard institutional access granted.
                </div>
              )}
            </div>
          </div>

          {/* Session Architecture Notice */}
          <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-600 space-y-2">
            <div className="flex items-center space-x-2 text-slate-900 font-semibold">
              <Lock className="h-4 w-4 text-sky-600" />
              <span>Session Security Architecture</span>
            </div>
            <p className="text-[11px] text-slate-500 leading-relaxed">
              Tokens are issued with 30-minute validity and reside strictly in volatile memory. Tokens are never persisted to localStorage or cookies. Reloading the page or closing the tab clears the session immediately.
            </p>
          </div>

          <div className="pt-2 flex justify-end">
            <button
              onClick={logout}
              className="inline-flex items-center space-x-2 px-4 py-2 bg-white hover:bg-rose-50 border border-rose-200 text-rose-700 text-xs font-semibold rounded-lg transition-colors"
            >
              <LogOut className="h-4 w-4" />
              <span>Sign Out of Session</span>
            </button>
          </div>
        </div>
      </div>
    </AuthenticatedLayout>
  );
}
