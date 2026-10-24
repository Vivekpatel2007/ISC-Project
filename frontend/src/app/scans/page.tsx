'use client';

import React, { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import {
  FileText,
  Search,
  RefreshCw,
  AlertCircle,
  ArrowRight,
  UploadCloud,
} from 'lucide-react';
import { useAuth } from '@/context/auth-context';
import { apiClient } from '@/lib/api-client';
import { ApiError, ScanMetadata } from '@/lib/types';
import { AuthenticatedLayout } from '@/components/layout/authenticated-layout';
import { formatBytes, formatDate } from '@/lib/utils';

export default function ScansHistoryPage() {
  const { role, token } = useAuth();
  const [scans, setScans] = useState<ScanMetadata[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'ALL' | 'PENDING' | 'PROCESSED'>('ALL');

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
          setError('Failed to retrieve scan records.');
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
            setError('Failed to retrieve scan records.');
          }
          setIsLoading(false);
        }
      });

    return () => {
      isSubscribed = false;
    };
  }, [token]);

  const filteredScans = scans.filter((scan) => {
    const matchesSearch =
      scan.patient_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      scan.scan_id.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus =
      statusFilter === 'ALL' || scan.prediction_status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  return (
    <AuthenticatedLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-xs flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-xl md:text-2xl font-bold text-slate-900 tracking-tight">
              Radiograph Repository
            </h1>
            <p className="text-xs md:text-sm text-slate-500 mt-1">
              {role === 'doctor'
                ? 'Authorized radiographs uploaded by your staff account.'
                : 'All institutional radiographs across all clinical departments.'}
            </p>
          </div>

          <div className="flex items-center space-x-3">
            <button
              onClick={() => fetchScans(true)}
              disabled={isLoading}
              className="inline-flex items-center space-x-1.5 px-3 py-2 text-xs font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
              <span>Refresh</span>
            </button>
            <Link
              href="/upload"
              className="inline-flex items-center space-x-2 px-4 py-2 text-xs font-medium text-white bg-sky-600 hover:bg-sky-700 rounded-lg shadow-xs transition-colors"
            >
              <UploadCloud className="h-4 w-4" />
              <span>Upload X-Ray</span>
            </Link>
          </div>
        </div>

        {/* Filter Bar */}
        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-xs flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3">
          <div className="relative flex-1">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
              <Search className="h-4 w-4" />
            </div>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by Patient ID (e.g. ANON-10492) or Scan UUID..."
              className="block w-full pl-9 pr-3 py-2 text-xs border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500 text-slate-900 placeholder-slate-400"
            />
          </div>

          <div className="flex items-center space-x-2">
            <span className="text-xs text-slate-500 font-medium">Status:</span>
            <div className="inline-flex rounded-lg border border-slate-200 p-0.5 bg-slate-50 text-xs">
              {(['ALL', 'PENDING', 'PROCESSED'] as const).map((status) => (
                <button
                  key={status}
                  onClick={() => setStatusFilter(status)}
                  className={`px-3 py-1.5 rounded-md font-medium transition-colors ${
                    statusFilter === status
                      ? 'bg-white text-slate-900 shadow-2xs font-semibold'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  {status}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Content */}
        {error ? (
          <div className="p-6 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 flex items-start justify-between">
            <div className="flex items-start space-x-3">
              <AlertCircle className="h-5 w-5 text-rose-600 shrink-0 mt-0.5" />
              <div>
                <h4 className="text-sm font-semibold">Failed to Retrieve Scans</h4>
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
        ) : isLoading ? (
          <div className="bg-white rounded-xl border border-slate-200 p-12 text-center shadow-xs">
            <div className="animate-spin rounded-full h-8 w-8 border-2 border-sky-600 border-t-transparent mx-auto mb-3" />
            <p className="text-xs text-slate-500 font-medium">Fetching authorized radiograph records...</p>
          </div>
        ) : filteredScans.length === 0 ? (
          <div className="bg-white rounded-xl border border-slate-200 p-12 text-center shadow-xs max-w-md mx-auto">
            <div className="h-12 w-12 rounded-full bg-slate-100 text-slate-400 mx-auto flex items-center justify-center mb-3">
              <FileText className="h-6 w-6" />
            </div>
            <h4 className="text-sm font-semibold text-slate-900">No matching scans found</h4>
            <p className="text-xs text-slate-500 mt-1 mb-4">
              {scans.length === 0
                ? 'No radiographs have been uploaded under your credentials yet.'
                : 'No scan records match the current filter criteria.'}
            </p>
            {scans.length === 0 && (
              <Link
                href="/upload"
                className="inline-flex items-center space-x-1.5 px-4 py-2 bg-sky-600 hover:bg-sky-700 text-white text-xs font-medium rounded-lg transition-colors"
              >
                <UploadCloud className="h-4 w-4" />
                <span>Upload First Scan</span>
              </Link>
            )}
          </div>
        ) : (
          <div className="space-y-4">
            {/* Desktop Table */}
            <div className="hidden md:block bg-white rounded-xl border border-slate-200 shadow-xs overflow-hidden">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 text-slate-500 border-b border-slate-200 uppercase font-semibold">
                  <tr>
                    <th className="py-3 px-4">Patient Identifier</th>
                    <th className="py-3 px-4">Scan UUID</th>
                    <th className="py-3 px-4">Created Date</th>
                    <th className="py-3 px-4">Encrypted Size</th>
                    <th className="py-3 px-4">Uploaded By</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4">Model Output</th>
                    <th className="py-3 px-4 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-slate-700">
                  {filteredScans.map((scan) => (
                    <tr key={scan.scan_id} className="hover:bg-slate-50/70 transition-colors">
                      <td className="py-3 px-4 font-mono font-medium text-slate-900">
                        {scan.patient_id}
                      </td>
                      <td className="py-3 px-4 font-mono text-slate-500 truncate max-w-[130px]" title={scan.scan_id}>
                        {scan.scan_id}
                      </td>
                      <td className="py-3 px-4 text-slate-500">
                        {formatDate(scan.created_at)}
                      </td>
                      <td className="py-3 px-4 text-slate-600">
                        {formatBytes(scan.file_size_bytes)}
                      </td>
                      <td className="py-3 px-4 font-mono text-slate-600">
                        {scan.uploaded_by}
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
                          <span className="text-slate-400 italic">Pending AI</span>
                        )}
                      </td>
                      <td className="py-3 px-4 text-right">
                        <Link
                          href={`/scans/${scan.scan_id}`}
                          className="inline-flex items-center space-x-1 text-sky-600 hover:text-sky-800 font-semibold"
                        >
                          <span>Details</span>
                          <ArrowRight className="h-3 w-3" />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Mobile Cards */}
            <div className="grid grid-cols-1 gap-3 md:hidden">
              {filteredScans.map((scan) => (
                <div key={scan.scan_id} className="bg-white rounded-xl border border-slate-200 p-4 shadow-xs space-y-3">
                  <div className="flex items-start justify-between">
                    <div>
                      <span className="text-[10px] uppercase font-semibold text-slate-400">Patient Identifier</span>
                      <p className="font-mono font-bold text-sm text-slate-900">{scan.patient_id}</p>
                    </div>
                    <span
                      className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold ${
                        scan.prediction_status === 'PROCESSED'
                          ? 'bg-teal-50 text-teal-700 border border-teal-200'
                          : 'bg-amber-50 text-amber-700 border border-amber-200'
                      }`}
                    >
                      {scan.prediction_status}
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-2 text-xs border-y border-slate-100 py-2">
                    <div>
                      <span className="text-slate-400 text-[10px]">Date</span>
                      <p className="text-slate-700 truncate">{formatDate(scan.created_at)}</p>
                    </div>
                    <div>
                      <span className="text-slate-400 text-[10px]">Encrypted Size</span>
                      <p className="text-slate-700">{formatBytes(scan.file_size_bytes)}</p>
                    </div>
                  </div>

                  <div className="flex items-center justify-between pt-1">
                    <div>
                      {scan.predicted_class ? (
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-bold ${
                            scan.predicted_class === 'PNEUMONIA'
                              ? 'bg-rose-100 text-rose-800'
                              : 'bg-emerald-100 text-emerald-800'
                          }`}
                        >
                          {scan.predicted_class}
                        </span>
                      ) : (
                        <span className="text-xs text-slate-400 italic">Not evaluated</span>
                      )}
                    </div>
                    <Link
                      href={`/scans/${scan.scan_id}`}
                      className="inline-flex items-center space-x-1 text-xs text-sky-600 font-semibold"
                    >
                      <span>Review Details</span>
                      <ArrowRight className="h-3 w-3" />
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </AuthenticatedLayout>
  );
}
