'use client';

import React, { useState, useRef, useEffect } from 'react';
import Link from 'next/link';
import {
  UploadCloud,
  FileImage,
  X,
  AlertCircle,
  CheckCircle2,
  Shield,
  Sparkles,
  Info,
} from 'lucide-react';
import { useAuth } from '@/context/auth-context';
import { apiClient } from '@/lib/api-client';
import { ApiError, ScanMetadata } from '@/lib/types';
import { AuthenticatedLayout } from '@/components/layout/authenticated-layout';
import { formatBytes } from '@/lib/utils';

// Backend constraints
const MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024; // 20 MB
const ALLOWED_TYPES = ['image/png', 'image/jpeg', 'image/jpg'];
const PATIENT_ID_REGEX = /^[a-zA-Z0-9_\-]{3,64}$/;

export default function UploadPage() {
  const { token } = useAuth();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [patientId, setPatientId] = useState('');
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [uploadedScan, setUploadedScan] = useState<ScanMetadata | null>(null);

  // Clean up object URLs when preview changes or component unmounts
  useEffect(() => {
    return () => {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
      }
    };
  }, [previewUrl]);

  const handleFileSelection = (file: File) => {
    setErrorMessage(null);

    // 1. Format validation
    if (!ALLOWED_TYPES.includes(file.type.toLowerCase())) {
      setErrorMessage('Invalid file format. Supported formats are PNG and JPEG (.png, .jpg, .jpeg).');
      return;
    }

    // 2. Size validation
    if (file.size > MAX_FILE_SIZE_BYTES) {
      setErrorMessage(
        `File size (${formatBytes(file.size)}) exceeds the maximum allowed limit of ${formatBytes(
          MAX_FILE_SIZE_BYTES
        )}.`
      );
      return;
    }

    if (file.size === 0) {
      setErrorMessage('Uploaded image file is empty.');
      return;
    }

    // Clean up previous preview URL
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
    }

    const objectUrl = URL.createObjectURL(file);
    setSelectedFile(file);
    setPreviewUrl(objectUrl);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileSelection(e.dataTransfer.files[0]);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleRemoveFile = () => {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
    }
    setSelectedFile(null);
    setPreviewUrl(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    if (!selectedFile) {
      setErrorMessage('Please select a chest radiograph image to upload.');
      return;
    }

    const cleanPatientId = patientId.trim();
    if (!cleanPatientId) {
      setErrorMessage('Please enter a pseudonymous patient identifier.');
      return;
    }

    if (!PATIENT_ID_REGEX.test(cleanPatientId)) {
      setErrorMessage(
        'Invalid patient identifier format. Must be 3-64 characters using letters, digits, underscores, or hyphens (e.g. ANON-00941).'
      );
      return;
    }

    if (!token) {
      setErrorMessage('Your session has expired. Please sign in again.');
      return;
    }

    setIsUploading(true);
    try {
      const result = await apiClient.uploadScan(selectedFile, cleanPatientId, token);
      setUploadedScan(result);
      // Clean up preview URL immediately after successful upload
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setErrorMessage(err.detail);
      } else if (err instanceof Error) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage('Upload failed. Please check network and file validity.');
      }
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <AuthenticatedLayout>
      <div className="max-w-3xl mx-auto space-y-6">
        <div>
          <h1 className="text-xl md:text-2xl font-bold text-slate-900 tracking-tight">
            Upload Chest Radiograph
          </h1>
          <p className="text-xs md:text-sm text-slate-500 mt-1">
            Submit a frontal chest X-ray image for AES-256-GCM encryption and DenseNet121 AI screening.
          </p>
        </div>

        {/* Success Confirmation State */}
        {uploadedScan ? (
          <div className="bg-white rounded-xl border border-teal-200 p-6 md:p-8 shadow-xs space-y-6">
            <div className="flex items-center space-x-3 text-teal-800">
              <div className="h-10 w-10 rounded-full bg-teal-100 flex items-center justify-center text-teal-700 shrink-0">
                <CheckCircle2 className="h-6 w-6" />
              </div>
              <div>
                <h2 className="text-lg font-bold text-slate-900">Radiograph Successfully Encrypted & Saved</h2>
                <p className="text-xs text-slate-500">
                  Container verified with fresh 96-bit AES-GCM nonce and recorded in metadata database.
                </p>
              </div>
            </div>

            <div className="bg-slate-50 rounded-lg border border-slate-200 p-4 space-y-2.5 text-xs">
              <div className="flex justify-between items-center py-1 border-b border-slate-200/60">
                <span className="text-slate-500 font-medium">Scan Identifier (UUID):</span>
                <span className="font-mono font-semibold text-slate-900">{uploadedScan.scan_id}</span>
              </div>
              <div className="flex justify-between items-center py-1 border-b border-slate-200/60">
                <span className="text-slate-500 font-medium">Pseudonymous Patient ID:</span>
                <span className="font-mono font-semibold text-slate-900">{uploadedScan.patient_id}</span>
              </div>
              <div className="flex justify-between items-center py-1 border-b border-slate-200/60">
                <span className="text-slate-500 font-medium">Encrypted Payload Size:</span>
                <span className="text-slate-700 font-medium">{formatBytes(uploadedScan.file_size_bytes)}</span>
              </div>
              <div className="flex justify-between items-center py-1">
                <span className="text-slate-500 font-medium">Current Status:</span>
                <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold bg-amber-50 text-amber-700 border border-amber-200">
                  {uploadedScan.prediction_status}
                </span>
              </div>
            </div>

            <div className="flex flex-col sm:flex-row items-center gap-3 pt-2">
              <Link
                href={`/scans/${uploadedScan.scan_id}`}
                className="w-full sm:w-auto flex-1 inline-flex items-center justify-center space-x-2 px-5 py-2.5 bg-sky-600 hover:bg-sky-700 text-white text-xs font-semibold rounded-lg shadow-xs transition-colors"
              >
                <Sparkles className="h-4 w-4" />
                <span>Run AI Screening Now</span>
              </Link>
              <button
                type="button"
                onClick={() => {
                  setUploadedScan(null);
                  setSelectedFile(null);
                  setPreviewUrl(null);
                  setPatientId('');
                }}
                className="w-full sm:w-auto inline-flex items-center justify-center px-4 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-medium rounded-lg transition-colors"
              >
                Upload Another Radiograph
              </button>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="bg-white rounded-xl border border-slate-200 p-6 md:p-8 shadow-xs space-y-6">
            {errorMessage && (
              <div className="p-3.5 rounded-lg bg-rose-50 border border-rose-200 flex items-start space-x-2.5 text-rose-800 text-xs">
                <AlertCircle className="h-4 w-4 shrink-0 text-rose-600 mt-0.5" />
                <span>{errorMessage}</span>
              </div>
            )}

            {/* Patient Identifier Field */}
            <div>
              <label htmlFor="patient_id" className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                Pseudonymous Patient Identifier *
              </label>
              <input
                id="patient_id"
                type="text"
                required
                value={patientId}
                onChange={(e) => setPatientId(e.target.value)}
                placeholder="e.g. ANON-10492 or PT-2026-X01"
                className="block w-full px-3.5 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500 text-slate-900 placeholder-slate-400"
              />
              <p className="text-[11px] text-slate-400 mt-1 flex items-center space-x-1">
                <Info className="h-3 w-3 shrink-0" />
                <span>Strictly pseudonymous code. Never enter actual patient names, social security numbers, or DOB.</span>
              </p>
            </div>

            {/* Drag & Drop Upload Container */}
            <div>
              <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                Chest X-Ray Image File *
              </label>

              {!selectedFile ? (
                <div
                  onDrop={handleDrop}
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onClick={() => fileInputRef.current?.click()}
                  className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
                    isDragging
                      ? 'border-sky-500 bg-sky-50/50'
                      : 'border-slate-300 hover:border-slate-400 bg-slate-50/50'
                  }`}
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".png,.jpg,.jpeg,image/png,image/jpeg"
                    className="hidden"
                    onChange={(e) => {
                      if (e.target.files && e.target.files[0]) {
                        handleFileSelection(e.target.files[0]);
                      }
                    }}
                  />
                  <div className="h-12 w-12 rounded-full bg-sky-100 text-sky-600 mx-auto flex items-center justify-center mb-3">
                    <UploadCloud className="h-6 w-6" />
                  </div>
                  <p className="text-sm font-semibold text-slate-800">
                    Click to select or drag and drop a radiograph
                  </p>
                  <p className="text-xs text-slate-500 mt-1">
                    Accepts PNG or JPEG format (maximum file size {formatBytes(MAX_FILE_SIZE_BYTES)})
                  </p>
                </div>
              ) : (
                <div className="border border-slate-200 rounded-xl p-4 bg-slate-50 space-y-4">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center space-x-3">
                      <div className="h-10 w-10 rounded-lg bg-white border border-slate-200 flex items-center justify-center text-slate-600">
                        <FileImage className="h-5 w-5" />
                      </div>
                      <div>
                        <p className="text-xs font-semibold text-slate-900 truncate max-w-xs md:max-w-md">
                          {selectedFile.name}
                        </p>
                        <p className="text-[11px] text-slate-500">
                          {formatBytes(selectedFile.size)} • {selectedFile.type || 'image'}
                        </p>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={handleRemoveFile}
                      className="p-1 rounded-md text-slate-400 hover:text-rose-600 hover:bg-white transition-colors"
                      title="Remove image"
                    >
                      <X className="h-5 w-5" />
                    </button>
                  </div>

                  {/* Local Temporary Image Preview */}
                  {previewUrl && (
                    <div className="relative rounded-lg overflow-hidden border border-slate-200 bg-black/5 flex items-center justify-center max-h-72">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={previewUrl}
                        alt="Local radiograph preview"
                        className="max-h-72 object-contain rounded"
                      />
                    </div>
                  )}

                  <div className="flex justify-end">
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      className="text-xs text-sky-600 hover:text-sky-700 font-medium"
                    >
                      Choose a different file
                    </button>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".png,.jpg,.jpeg,image/png,image/jpeg"
                      className="hidden"
                      onChange={(e) => {
                        if (e.target.files && e.target.files[0]) {
                          handleFileSelection(e.target.files[0]);
                        }
                      }}
                    />
                  </div>
                </div>
              )}
            </div>

            {/* Cryptographic Pipeline Notice */}
            <div className="rounded-lg bg-sky-50/70 border border-sky-100 p-3.5 text-xs text-sky-800 flex items-start space-x-2.5">
              <Shield className="h-4 w-4 text-sky-600 shrink-0 mt-0.5" />
              <div className="space-y-0.5">
                <span className="font-semibold">AES-256-GCM Secure Ingestion:</span>
                <p className="text-[11px] text-sky-700 leading-relaxed">
                  Upon submission, the image binary is validated in-memory and encrypted via AES-256-GCM before writing to disk. Plaintext images are never stored in disk storage or persistent browser caches.
                </p>
              </div>
            </div>

            {/* Submit Action */}
            <div className="flex justify-end pt-2">
              <button
                type="submit"
                disabled={isUploading || !selectedFile}
                className="w-full sm:w-auto inline-flex items-center justify-center space-x-2 px-6 py-2.5 bg-sky-600 hover:bg-sky-700 text-white text-xs font-semibold rounded-lg shadow-xs transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isUploading ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent" />
                    <span>Encrypting & Storing...</span>
                  </>
                ) : (
                  <>
                    <UploadCloud className="h-4 w-4" />
                    <span>Upload & Encrypt Radiograph</span>
                  </>
                )}
              </button>
            </div>
          </form>
        )}
      </div>
    </AuthenticatedLayout>
  );
}
