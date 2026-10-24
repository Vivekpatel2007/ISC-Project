'use client';

import React, { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import {
  UploadCloud,
  FileText,
  Activity,
  Clock,
  CheckCircle2,
  AlertCircle,
  ArrowRight,
  RefreshCw,
  FileCheck2,
} from 'lucide-react';
import { useAuth } from '@/context/auth-context';
import { apiClient } from '@/lib/api-client';
import { ApiError, ScanMetadata } from '@/lib/types';
import { AuthenticatedLayout } from '@/components/layout/authenticated-layout';
import { formatDate } from '@/lib/utils';

export default function DashboardPage() {
  const { user, role, token } = useAuth();
  const [scans, setScans] = useState<ScanMetadata[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchScans = useCallback(
    async (showSpinner = true) => {
      if (!token) return;
      if (showSpinner) setIsLoading(true);
      setError(null);
      try {
        const data = await apiClient.listScans(token);
        setScans(data);
      } catch (err: unknown) {
        if (err instanceof ApiError) {
          setError(err.detail);
        } else if (err instanceof Error) {
          setError(err.message);
        } else {
          setError('Failed to fetch scans from backend.');
        }
      } finally {
        setIsLoading(false);
      }
    },
    [token]
  );

  useEffect(() => {
    let isSubscribed = true;
    if (!token) return;

    apiClient
      .listScans(token)
      .then((data) => {
        if (isSubscribed) {
          setScans(data);
          setIsLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (isSubscribed) {
          if (err instanceof ApiError) {
            setError(err.detail);
          } else if (err instanceof Error) {
            setError(err.message);
          } else {
            setError('Failed to fetch scans from backend.');
          }
          setIsLoading(false);
        }
      });

    return () => {
      isSubscribed = false;
    };
  }, [token]);

  // Real statistics computed solely from real API data
  const totalScans = scans.length;
  const pendingCount = scans.filter((s) => s.prediction_status === 'PENDING').length;
  const processedCount = scans.filter((s) => s.prediction_status === 'PROCESSED').length;
  const pneumoniaCount = scans.filter((s) => s.predicted_class === 'PNEUMONIA').length;
  const normalCount = scans.filter((s) => s.predicted_class === 'NORMAL').length;

  const recentScans = scans.slice(0, 5);

  return (
    <AuthenticatedLayout>
      <div className="space-y-6">
        {/* Welcome Banner */}
        <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-xs flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="text-xl md:text-2xl font-bold text-slate-900 tracking-tight">
                Welcome, {user?.full_name || user?.username}
              </h1>
              <span
                className={`text-xs font-semibold uppercase px-2 py-0.5 rounded ${
                  role === 'doctor'
                    ? 'bg-blue-100 text-blue-800'
                    : role === 'radiologist'
                    ? 'bg-teal-100 text-teal-800'
                    : 'bg-slate-100 text-slate-800'
                }`}
              >
                {role}
              </span>
            </div>
            <p className="text-xs md:text-sm text-slate-500 mt-1">
              {role === 'doctor'
                ? 'Your uploaded patient radiographs and screening statuses.'
                : 'Facility-wide diagnostic radiograph repository and DenseNet121 evaluation.'}
            </p>
          </div>

          <div className="flex items-center space-x-3">
            <button
              onClick={() => fetchScans(true)}
              disabled={isLoading}
              className="inline-flex items-center space-x-1.5 px-3 py-2 text-xs font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors"
              title="Refresh scan repository"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
              <span>Refresh</span>
            </button>
            <Link
              href="/upload"
              className="inline-flex items-center space-x-2 px-4 py-2 text-xs font-medium text-white bg-sky-600 hover:bg-sky-700 rounded-lg shadow-xs transition-colors"
            >
              <UploadCloud className="h-4 w-4" />
              <span>Upload New X-Ray</span>
            </Link>
          </div>
        </div>

        {/* Real Computed Metrics */}
        {error ? (
          <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 flex items-start justify-between">
            <div className="flex items-start space-x-3">
              <AlertCircle className="h-5 w-5 text-rose-600 shrink-0 mt-0.5" />
              <div>
                <h4 className="text-sm font-semibold">Backend Connection Issue</h4>
                <p className="text-xs text-rose-700 mt-0.5">{error}</p>
              </div>
            </div>
            <button
              onClick={() => fetchScans(true)}
              className="px-3 py-1.5 bg-white border border-rose-200 text-rose-700 text-xs font-medium rounded-lg hover:bg-rose-100/50"
            >
              Retry
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-slate-500 uppercase tracking-wider">
                  Total Accessible Scans
                </span>
                <div className="h-8 w-8 rounded-lg bg-sky-50 text-sky-600 flex items-center justify-center">
                  <FileText className="h-4 w-4" />
                </div>
              </div>
              <div className="mt-3">
                <span className="text-2xl font-bold text-slate-900">
                  {isLoading ? '...' : totalScans}
                </span>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  {role === 'doctor' ? 'Uploaded by you' : 'Total institutional scans'}
                </p>
              </div>
            </div>

            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-slate-500 uppercase tracking-wider">
                  Awaiting AI Analysis
                </span>
                <div className="h-8 w-8 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center">
                  <Clock className="h-4 w-4" />
                </div>
              </div>
              <div className="mt-3">
                <span className="text-2xl font-bold text-slate-900">
                  {isLoading ? '...' : pendingCount}
                </span>
                <p className="text-[11px] text-slate-400 mt-0.5">Prediction status PENDING</p>
              </div>
            </div>

            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-slate-500 uppercase tracking-wider">
                  Screened Scans
                </span>
                <div className="h-8 w-8 rounded-lg bg-teal-50 text-teal-600 flex items-center justify-center">
                  <CheckCircle2 className="h-4 w-4" />
                </div>
              </div>
              <div className="mt-3">
                <span className="text-2xl font-bold text-slate-900">
                  {isLoading ? '...' : processedCount}
                </span>
                <p className="text-[11px] text-slate-400 mt-0.5">DenseNet121 processed</p>
              </div>
            </div>

            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-slate-500 uppercase tracking-wider">
                  Normal / Pneumonia
                </span>
                <div className="h-8 w-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center">
                  <Activity className="h-4 w-4" />
                </div>
              </div>
              <div className="mt-3">
                <div className="flex items-baseline space-x-2">
                  <span className="text-2xl font-bold text-slate-900">
                    {isLoading ? '...' : `${normalCount} / ${pneumoniaCount}`}
                  </span>
                </div>
                <p className="text-[11px] text-slate-400 mt-0.5">Normal vs Pneumonia labeled</p>
              </div>
            </div>
          </div>
        )}

        {/* Recent Scans Section */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-xs overflow-hidden">
          <div className="p-5 border-b border-slate-100 flex items-center justify-between">
            <div>
              <h3 className="text-base font-semibold text-slate-900">Recent Radiographs</h3>
              <p className="text-xs text-slate-500 mt-0.5">
                Latest encrypted radiographs accessible under your {role} credentials.
              </p>
            </div>
            <Link
              href="/scans"
              className="inline-flex items-center space-x-1 text-xs font-medium text-sky-600 hover:text-sky-700"
            >
              <span>View All Scans</span>
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>

          {isLoading ? (
            <div className="p-12 text-center">
              <div className="animate-spin rounded-full h-8 w-8 border-2 border-sky-600 border-t-transparent mx-auto mb-3" />
              <p className="text-xs text-slate-500 font-medium">Loading scans from repository...</p>
            </div>
          ) : scans.length === 0 ? (
            <div className="p-12 text-center max-w-md mx-auto">
              <div className="h-12 w-12 rounded-full bg-slate-100 text-slate-400 mx-auto flex items-center justify-center mb-3">
                <FileCheck2 className="h-6 w-6" />
              </div>
              <h4 className="text-sm font-semibold text-slate-900">No radiographs uploaded yet</h4>
              <p className="text-xs text-slate-500 mt-1 mb-4">
                Begin by uploading a patient chest X-ray. It will be encrypted with AES-256-GCM before storage.
              </p>
              <Link
                href="/upload"
                className="inline-flex items-center space-x-1.5 px-4 py-2 bg-sky-600 hover:bg-sky-700 text-white text-xs font-medium rounded-lg transition-colors"
              >
                <UploadCloud className="h-4 w-4" />
                <span>Upload First Radiograph</span>
              </Link>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 text-slate-500 border-b border-slate-200 uppercase font-semibold">
                  <tr>
                    <th className="py-3 px-4">Patient Identifier</th>
                    <th className="py-3 px-4">Scan ID</th>
                    <th className="py-3 px-4">Uploaded At</th>
                    <th className="py-3 px-4">AI Status</th>
                    <th className="py-3 px-4">Screening Result</th>
                    <th className="py-3 px-4 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-slate-700">
                  {recentScans.map((scan) => (
                    <tr key={scan.scan_id} className="hover:bg-slate-50/70 transition-colors">
                      <td className="py-3 px-4 font-mono font-medium text-slate-900">
                        {scan.patient_id}
                      </td>
                      <td className="py-3 px-4 font-mono text-slate-500 truncate max-w-[140px]" title={scan.scan_id}>
                        {scan.scan_id}
                      </td>
                      <td className="py-3 px-4 text-slate-500">
                        {formatDate(scan.created_at)}
                      </td>
                      <td className="py-3 px-4">
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold ${
                            scan.prediction_status === 'PROCESSED'
                              ? 'bg-teal-50 text-teal-700 border border-teal-200'
                              : 'bg-amber-50 text-amber-700 border border-amber-200'
                          }`}
                        >
                          {scan.prediction_status}
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        {scan.predicted_class ? (
                          <span
                            className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-bold ${
                              scan.predicted_class === 'PNEUMONIA'
                                ? 'bg-rose-100 text-rose-800'
                                : 'bg-emerald-100 text-emerald-800'
                            }`}
                          >
                            {scan.predicted_class}
                            {scan.prediction_probability !== null && (
                              <span className="ml-1 text-[10px] font-normal opacity-75">
                                ({(scan.prediction_probability * 100).toFixed(1)}%)
                              </span>
                            )}
                          </span>
                        ) : (
                          <span className="text-slate-400 italic">Not evaluated</span>
                        )}
                      </td>
                      <td className="py-3 px-4 text-right">
                        <Link
                          href={`/scans/${scan.scan_id}`}
                          className="inline-flex items-center space-x-1 text-sky-600 hover:text-sky-800 font-semibold"
                        >
                          <span>Review</span>
                          <ArrowRight className="h-3 w-3" />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </AuthenticatedLayout>
  );
}
