'use client';

import React, { useEffect, useState, useCallback, use, Suspense } from 'react';
import Link from 'next/link';
import {
  ShieldCheck,
  Sparkles,
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  Cpu,
  Clock,
  Layers,
  HardDrive,
  User,
} from 'lucide-react';
import { useAuth } from '@/context/auth-context';
import { apiClient } from '@/lib/api-client';
import { ApiError, PredictionResult, ScanMetadata } from '@/lib/types';
import { AuthenticatedLayout } from '@/components/layout/authenticated-layout';
import { formatBytes, formatDate } from '@/lib/utils';

function ScanDetailContent({
  params,
}: {
  params: Promise<{ id: string }> | { id: string };
}) {
  const resolvedParams =
    params && typeof (params as Promise<{ id: string }>).then === 'function'
      ? use(params as Promise<{ id: string }>)
      : (params as { id: string });
  const scanId = resolvedParams.id;
  const { token } = useAuth();

  const [scan, setScan] = useState<ScanMetadata | null>(null);
  const [prediction, setPrediction] = useState<PredictionResult | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isPredicting, setIsPredicting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [predictionError, setPredictionError] = useState<string | null>(null);

  const fetchScanDetail = useCallback(
    async (showSpinner = true) => {
      if (!token) return;
      if (showSpinner) setIsLoading(true);
      setErrorMessage(null);
      try {
        const data = await apiClient.getScan(scanId, token);
        setScan(data);
      } catch (err: unknown) {
        if (err instanceof ApiError) {
          if (err.status === 403) {
            setErrorMessage(
              'Access Denied (403): You are not authorized to view this radiograph. Doctors may only view their own uploads.'
            );
          } else if (err.status === 404) {
            setErrorMessage('Scan Not Found (404): No scan record matches the requested identifier.');
          } else {
            setErrorMessage(err.detail);
          }
        } else if (err instanceof Error) {
          setErrorMessage(err.message);
        } else {
          setErrorMessage('Failed to retrieve scan metadata.');
        }
      } finally {
        setIsLoading(false);
      }
    },
    [scanId, token]
  );

  useEffect(() => {
    let isSubscribed = true;
    if (!token) return;

    apiClient
      .getScan(scanId, token)
      .then((data) => {
        if (isSubscribed) {
          setScan(data);
          setIsLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (isSubscribed) {
          if (err instanceof ApiError) {
            if (err.status === 403) {
              setErrorMessage(
                'Access Denied (403): You are not authorized to view this radiograph. Doctors may only view their own uploads.'
              );
            } else if (err.status === 404) {
              setErrorMessage('Scan Not Found (404): No scan record matches the requested identifier.');
            } else {
              setErrorMessage(err.detail);
            }
          } else if (err instanceof Error) {
            setErrorMessage(err.message);
          } else {
            setErrorMessage('Failed to retrieve scan metadata.');
          }
          setIsLoading(false);
        }
      });

    return () => {
      isSubscribed = false;
    };
  }, [scanId, token]);

  const handleRunPrediction = async () => {
    if (!token) return;
    setIsPredicting(true);
    setPredictionError(null);
    try {
      const result = await apiClient.predictScan(scanId, token);
      setPrediction(result);
      // Refresh scan metadata to reflect PROCESSED status
      await fetchScanDetail(false);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          setPredictionError(
            'Integrity Tampering Error (409): The encrypted radiograph failed AES-GCM authentication tag verification. Ciphertext has been modified or corrupted on disk.'
          );
        } else if (err.status === 403) {
          setPredictionError('Forbidden (403): Insufficient permissions to trigger inference.');
        } else {
          setPredictionError(err.detail);
        }
      } else if (err instanceof Error) {
        setPredictionError(err.message);
      } else {
        setPredictionError('Model inference failed.');
      }
    } finally {
      setIsPredicting(false);
    }
  };

  return (
    <AuthenticatedLayout>
      <div className="max-w-4xl mx-auto space-y-6">
        {/* Back Link */}
        <div>
          <Link
            href="/scans"
            className="inline-flex items-center space-x-1.5 text-xs font-medium text-slate-500 hover:text-slate-800 transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
            <span>Back to Scan Repository</span>
          </Link>
        </div>

        {/* Loading State */}
        {isLoading ? (
          <div className="bg-white rounded-xl border border-slate-200 p-12 text-center shadow-xs">
            <div className="animate-spin rounded-full h-8 w-8 border-2 border-sky-600 border-t-transparent mx-auto mb-3" />
            <p className="text-xs text-slate-500 font-medium">Loading scan metadata from secure database...</p>
          </div>
        ) : errorMessage ? (
          /* Error State */
          <div className="bg-white rounded-xl border border-rose-200 p-8 shadow-xs text-center max-w-lg mx-auto space-y-4">
            <div className="h-12 w-12 rounded-full bg-rose-100 text-rose-600 mx-auto flex items-center justify-center">
              <AlertCircle className="h-6 w-6" />
            </div>
            <div>
              <h3 className="text-base font-bold text-slate-900">Unable to Access Scan</h3>
              <p className="text-xs text-slate-600 mt-1">{errorMessage}</p>
            </div>
            <div className="pt-2">
              <Link
                href="/scans"
                className="inline-flex items-center space-x-2 px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-800 text-xs font-medium rounded-lg transition-colors"
              >
                <span>Return to Scan History</span>
              </Link>
            </div>
          </div>
        ) : scan ? (
          <div className="space-y-6">
            {/* Metadata Card */}
            <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-xs">
              <div className="flex flex-col md:flex-row md:items-center justify-between pb-4 border-b border-slate-100 gap-3">
                <div>
                  <div className="flex items-center space-x-2.5">
                    <h1 className="text-lg font-bold text-slate-900 tracking-tight">
                      Radiograph Details
                    </h1>
                    <span
                      className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold ${
                        scan.prediction_status === 'PROCESSED'
                          ? 'bg-teal-50 text-teal-700 border border-teal-200'
                          : 'bg-amber-50 text-amber-700 border border-amber-200'
                      }`}
                    >
                      {scan.prediction_status}
                    </span>
                  </div>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Scan UUID: <span className="font-mono text-slate-700">{scan.scan_id}</span>
                  </p>
                </div>

                {/* AI Screening Action Button */}
                <div>
                  <button
                    onClick={handleRunPrediction}
                    disabled={isPredicting}
                    className="w-full sm:w-auto inline-flex items-center justify-center space-x-2 px-4 py-2.5 bg-sky-600 hover:bg-sky-700 text-white text-xs font-semibold rounded-lg shadow-xs transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isPredicting ? (
                      <>
                        <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent" />
                        <span>Running DenseNet121 Inference...</span>
                      </>
                    ) : (
                      <>
                        <Sparkles className="h-4 w-4" />
                        <span>
                          {prediction || scan.prediction_status === 'PROCESSED'
                            ? 'Re-Run AI Screening'
                            : 'Run AI Screening'}
                        </span>
                      </>
                    )}
                  </button>
                </div>
              </div>

              {/* Prediction Error Alert */}
              {predictionError && (
                <div className="mt-4 p-3.5 rounded-lg bg-rose-50 border border-rose-200 flex items-start space-x-2.5 text-rose-800 text-xs">
                  <AlertCircle className="h-4 w-4 shrink-0 text-rose-600 mt-0.5" />
                  <div>
                    <span className="font-semibold">Inference Aborted:</span>
                    <p className="mt-0.5 text-rose-700">{predictionError}</p>
                  </div>
                </div>
              )}

              {/* Authorized Metadata Grid */}
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 mt-5">
                <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-100">
                  <div className="flex items-center space-x-2 text-slate-500 mb-1">
                    <User className="h-3.5 w-3.5" />
                    <span className="text-[11px] uppercase font-semibold">Patient ID</span>
                  </div>
                  <p className="font-mono font-bold text-sm text-slate-900">{scan.patient_id}</p>
                </div>

                <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-100">
                  <div className="flex items-center space-x-2 text-slate-500 mb-1">
                    <Clock className="h-3.5 w-3.5" />
                    <span className="text-[11px] uppercase font-semibold">Uploaded Date</span>
                  </div>
                  <p className="font-medium text-xs text-slate-900">{formatDate(scan.created_at)}</p>
                </div>

                <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-100">
                  <div className="flex items-center space-x-2 text-slate-500 mb-1">
                    <HardDrive className="h-3.5 w-3.5" />
                    <span className="text-[11px] uppercase font-semibold">Encrypted Size</span>
                  </div>
                  <p className="font-medium text-xs text-slate-900">{formatBytes(scan.file_size_bytes)}</p>
                </div>

                <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-100">
                  <div className="flex items-center space-x-2 text-slate-500 mb-1">
                    <Layers className="h-3.5 w-3.5" />
                    <span className="text-[11px] uppercase font-semibold">Uploaded By</span>
                  </div>
                  <p className="font-mono font-medium text-xs text-slate-900">{scan.uploaded_by}</p>
                </div>
              </div>

              {/* Cryptographic Protection Explainer */}
              <div className="mt-5 p-3.5 rounded-lg bg-teal-50/70 border border-teal-200/60 text-xs text-teal-900 flex items-start space-x-2.5">
                <ShieldCheck className="h-4 w-4 text-teal-700 shrink-0 mt-0.5" />
                <div className="space-y-0.5">
                  <span className="font-semibold text-teal-950">In-Memory Decryption Architecture:</span>
                  <p className="text-[11px] text-teal-800 leading-relaxed">
                    This radiograph is stored on disk in the PX01 AES-256-GCM authenticated container. Plaintext scans are never persisted to disk or sent across unauthenticated browser sockets. During AI screening, the container is authenticated and decrypted strictly in volatile RAM.
                  </p>
                </div>
              </div>
            </div>

            {/* AI Screening Results Card */}
            {(prediction || scan.predicted_class) && (
              <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-xs space-y-5">
                <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                  <div className="flex items-center space-x-2">
                    <Cpu className="h-5 w-5 text-sky-600" />
                    <h2 className="text-base font-bold text-slate-900">DenseNet121 AI Screening Output</h2>
                  </div>
                  {prediction && (
                    <span className="text-xs font-mono text-slate-500">
                      Device: <span className="font-semibold uppercase text-slate-700">{prediction.device}</span>
                    </span>
                  )}
                </div>

                {/* Primary Classification Result Badge */}
                {(() => {
                  const label = prediction?.prediction || scan.predicted_class || 'UNKNOWN';
                  const isPneumonia = label === 'PNEUMONIA';
                  const pPneumonia = prediction?.pneumonia_probability ?? (isPneumonia ? scan.prediction_probability ?? 0 : 1 - (scan.prediction_probability ?? 0));
                  const pNormal = prediction?.normal_probability ?? (1 - pPneumonia);
                  const confidence = prediction?.confidence ?? scan.prediction_probability ?? 0;

                  return (
                    <div className="space-y-5">
                      <div
                        className={`p-5 rounded-xl border flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 ${
                          isPneumonia
                            ? 'bg-rose-50/80 border-rose-200 text-rose-900'
                            : 'bg-emerald-50/80 border-emerald-200 text-emerald-900'
                        }`}
                      >
                        <div>
                          <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                            Screening Indication
                          </span>
                          <div className="flex items-baseline space-x-2 mt-0.5">
                            <span
                              className={`text-2xl font-black tracking-tight ${
                                isPneumonia ? 'text-rose-700' : 'text-emerald-700'
                              }`}
                            >
                              {label}
                            </span>
                            <span className="text-xs font-medium text-slate-600">
                              (Confidence: {(confidence * 100).toFixed(1)}%)
                            </span>
                          </div>
                          <p className="text-xs text-slate-600 mt-1">
                            {isPneumonia
                              ? 'Model flagged features consistent with pulmonary consolidation or infiltrate.'
                              : 'Model flagged clear lung fields without prominent consolidation.'}
                          </p>
                        </div>

                        {prediction && (
                          <div className="text-left sm:text-right text-xs text-slate-600">
                            <div>
                              Decision Threshold: <span className="font-mono font-semibold">{prediction.threshold_applied}</span>
                            </div>
                            <div className="text-[11px] text-slate-400 mt-0.5">
                              Model: {prediction.model_architecture} (Epoch {prediction.model_epoch})
                            </div>
                          </div>
                        )}
                      </div>

                      {/* Probability Bars */}
                      <div className="space-y-3 bg-slate-50 rounded-xl p-4 border border-slate-200">
                        <h4 className="text-xs font-semibold text-slate-700 uppercase tracking-wider">
                          Model Probability Distribution
                        </h4>

                        {/* Pneumonia Bar */}
                        <div>
                          <div className="flex justify-between text-xs mb-1">
                            <span className="font-medium text-slate-700">Pneumonia Probability</span>
                            <span className="font-mono font-bold text-rose-700">
                              {(pPneumonia * 100).toFixed(2)}%
                            </span>
                          </div>
                          <div className="w-full h-3 bg-slate-200 rounded-full overflow-hidden">
                            <div
                              className="h-full bg-rose-500 rounded-full transition-all duration-500"
                              style={{ width: `${Math.min(100, Math.max(0, pPneumonia * 100))}%` }}
                            />
                          </div>
                        </div>

                        {/* Normal Bar */}
                        <div>
                          <div className="flex justify-between text-xs mb-1">
                            <span className="font-medium text-slate-700">Normal Probability</span>
                            <span className="font-mono font-bold text-emerald-700">
                              {(pNormal * 100).toFixed(2)}%
                            </span>
                          </div>
                          <div className="w-full h-3 bg-slate-200 rounded-full overflow-hidden">
                            <div
                              className="h-full bg-emerald-500 rounded-full transition-all duration-500"
                              style={{ width: `${Math.min(100, Math.max(0, pNormal * 100))}%` }}
                            />
                          </div>
                        </div>
                      </div>

                      {/* Clinical Disclaimer Box */}
                      <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 text-xs flex items-start space-x-3">
                        <AlertTriangle className="h-5 w-5 text-amber-600 shrink-0 mt-0.5" />
                        <div className="space-y-1">
                          <span className="font-bold">Mandatory Clinical Disclaimer:</span>
                          <p className="text-[11px] text-amber-800 leading-relaxed">
                            {prediction?.disclaimer ||
                              'AI-assisted screening output for clinical decision support. Not a standalone or definitive medical diagnosis. Clinical review and correlation by a qualified radiologist or physician is required.'}
                          </p>
                        </div>
                      </div>
                    </div>
                  );
                })()}
              </div>
            )}
          </div>
        ) : null}
      </div>
    </AuthenticatedLayout>
  );
}

export default function ScanDetailPage({
  params,
}: {
  params: Promise<{ id: string }> | { id: string };
}) {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center bg-slate-50">
          <div className="flex flex-col items-center space-y-3">
            <div className="animate-spin rounded-full h-8 w-8 border-2 border-sky-600 border-t-transparent" />
            <p className="text-xs text-slate-500 font-medium">Loading radiograph view...</p>
          </div>
        </div>
      }
    >
      <ScanDetailContent params={params} />
    </Suspense>
  );
}
