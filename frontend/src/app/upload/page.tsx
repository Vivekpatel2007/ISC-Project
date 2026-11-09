"use client";

/* eslint-disable @next/next/no-img-element -- Local upload previews use revocable blob URLs. */

import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type DragEvent,
} from "react";
import Link from "next/link";
import {
  UploadCloud,
  FileImage,
  X,
  ShieldCheck,
  Check,
  ArrowRight,
  CheckCircle2,
  Info,
  LoaderCircle,
} from "lucide-react";
import { useAuth } from "@/context/auth-context";
import { apiClient } from "@/lib/api-client";
import type { ScanMetadata } from "@/lib/types";
import { AuthenticatedLayout } from "@/components/layout/authenticated-layout";
import { PageHeader, ErrorState } from "@/components/ui";
import { formatBytes } from "@/lib/utils";

const MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024;
const ALLOWED_TYPES = ["image/png", "image/jpeg", "image/jpg"];
const PATIENT_ID_REGEX = /^[a-zA-Z0-9_\-]{3,64}$/;

export default function UploadPage() {
  const { token } = useAuth();
  const fileInput = useRef<HTMLInputElement>(null);
  const submitting = useRef(false);
  const operation = useRef(0);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<{ file: File; url: string } | null>(
    null,
  );
  const [patientId, setPatientId] = useState("");
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<ScanMetadata | null>(null);
  useEffect(() => {
    if (!file) return;
    const url = URL.createObjectURL(file);
    let active = true;
    queueMicrotask(() => {
      if (active) setPreview({ file, url });
    });
    return () => {
      active = false;
      URL.revokeObjectURL(url);
    };
  }, [file]);
  useEffect(
    () => () => {
      operation.current += 1;
      submitting.current = false;
      setUploading(false);
    },
    [],
  );
  const clearFile = () => {
    setFile(null);
    if (fileInput.current) fileInput.current.value = "";
  };
  const selectFile = (selected: File) => {
    if (submitting.current) return;
    setError(null);
    if (!ALLOWED_TYPES.includes(selected.type.toLowerCase())) {
      clearFile();
      setError(
        "Invalid file format. Supported formats are PNG and JPEG (.png, .jpg, .jpeg).",
      );
      return;
    }
    if (selected.size > MAX_FILE_SIZE_BYTES) {
      clearFile();
      setError(
        `File size (${formatBytes(selected.size)}) exceeds the maximum allowed limit of 20 MB.`,
      );
      return;
    }
    if (selected.size === 0) {
      clearFile();
      setError("This file is empty. Choose a valid radiograph.");
      return;
    }
    setFile(selected);
  };
  const drop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    if (submitting.current) return;
    if (event.dataTransfer.files.length !== 1) {
      clearFile();
      setError("Choose one radiograph at a time.");
      return;
    }
    selectFile(event.dataTransfer.files[0]);
  };
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (submitting.current) return;
    setError(null);
    if (!file) {
      setError("Please select a chest radiograph image to upload.");
      return;
    }
    const cleanId = patientId.trim();
    if (!PATIENT_ID_REGEX.test(cleanId)) {
      setError(
        "Invalid patient identifier format. Use 3–64 letters, digits, underscores, or hyphens.",
      );
      return;
    }
    if (!token) {
      setError("Your session is unavailable. Please sign in again.");
      return;
    }
    submitting.current = true;
    setUploading(true);
    const current = ++operation.current;
    try {
      const record = await apiClient.uploadScan(file, cleanId, token);
      if (current === operation.current) {
        setSaved(record);
        clearFile();
      }
    } catch (reason: unknown) {
      if (current === operation.current)
        setError(
          reason instanceof Error
            ? reason.message
            : "Upload failed. Please try again.",
        );
    } finally {
      if (current === operation.current) {
        submitting.current = false;
        setUploading(false);
      }
    }
  };
  return (
    <AuthenticatedLayout>
      <div className="page-stack">
        <PageHeader
          eyebrow="Start a new screening"
          title="Upload a radiograph"
          description="Add a chest X-ray, connect it to a patient identifier, and prepare it for AI screening."
        />
        {saved ? (
          <section
            className="panel panel-padding text-center"
            style={{ padding: "45px 25px" }}
            aria-live="polite"
          >
            <div className="success-mark">
              <CheckCircle2 size={30} strokeWidth={1.5} />
            </div>
            <p className="eyebrow">Upload complete</p>
            <h2 style={{ fontSize: 25 }}>Your radiograph is ready.</h2>
            <p className="muted text-sm mt-3">
              The scan was encrypted and saved. AI screening is the next step.
            </p>
            <dl
              className="detail-grid text-left mx-auto my-8"
              style={{ maxWidth: 440 }}
            >
              <div className="detail-item">
                <dt>Patient identifier</dt>
                <dd>{saved.patient_id}</dd>
              </div>
              <div className="detail-item">
                <dt>Scan identifier</dt>
                <dd className="font-mono">{saved.scan_id}</dd>
              </div>
            </dl>
            <div className="flex justify-center gap-3 flex-wrap">
              <Link
                className="button button-primary"
                href={`/scans/${encodeURIComponent(saved.scan_id)}`}
              >
                Continue to screening
                <ArrowRight size={15} />
              </Link>
              <button
                className="button button-secondary"
                onClick={() => {
                  setSaved(null);
                  setPatientId("");
                  setError(null);
                }}
              >
                Upload another
              </button>
            </div>
          </section>
        ) : (
          <div className="upload-columns">
            <form
              className="panel panel-padding"
              onSubmit={submit}
              noValidate
              aria-busy={uploading}
            >
              <div className="flex items-center gap-3 mb-6">
                <span className="step-number">01</span>
                <div>
                  <h2>Select your radiograph</h2>
                  <p className="muted text-[11px] mt-1">
                    Choose a clear, frontal chest X-ray.
                  </p>
                </div>
              </div>
              {error && (
                <div className="mb-5">
                  <ErrorState
                    message={error}
                    title="Please check your upload"
                  />
                </div>
              )}
              {file ? (
                <div className="upload-preview">
                  {preview?.file === file && (
                    <img src={preview.url} alt="Local radiograph preview" />
                  )}
                  <div className="file-metadata">
                    <div className="flex items-center gap-3 min-w-0">
                      <FileImage size={20} className="accent shrink-0" />
                      <div className="min-w-0">
                        <p>{file.name}</p>
                        <small>
                          {formatBytes(file.size)} · Ready to upload
                        </small>
                      </div>
                    </div>
                    <button
                      className="icon-button"
                      type="button"
                      disabled={uploading}
                      aria-label="Remove selected radiograph"
                      onClick={clearFile}
                    >
                      <X size={16} />
                    </button>
                  </div>
                </div>
              ) : (
                <label
                  className={`dropzone${dragging ? " dragging" : ""}`}
                  onDragOver={(event) => {
                    event.preventDefault();
                    if (!uploading) setDragging(true);
                  }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={drop}
                >
                  <span className="dropzone-icon">
                    <UploadCloud size={26} strokeWidth={1.5} />
                  </span>
                  <strong>Drop your radiograph here</strong>
                  <p>
                    or <span className="browse-label">browse files</span> to
                    choose an image
                  </p>
                  <p>PNG or JPEG · Up to 20 MB</p>
                  <input
                    ref={fileInput}
                    type="file"
                    accept="image/png,image/jpeg"
                    aria-label="Choose chest radiograph"
                    disabled={uploading}
                    onChange={(event) => {
                      const selected = event.target.files?.[0];
                      if (selected) selectFile(selected);
                    }}
                  />
                </label>
              )}
              <div className="form-divider" />
              <div className="flex items-center gap-3 mb-5">
                <span className="step-number">02</span>
                <h2>Connect to a patient</h2>
              </div>
              <label className="field-label" htmlFor="patient-id">
                Pseudonymous patient identifier
              </label>
              <input
                className="input"
                id="patient-id"
                autoComplete="off"
                spellCheck={false}
                placeholder="e.g. ANON-10492"
                value={patientId}
                disabled={uploading}
                maxLength={64}
                onChange={(event) => setPatientId(event.target.value)}
                aria-describedby="patient-help"
              />
              <p id="patient-help" className="field-help">
                Use a reference code, not a name or other personal information.
              </p>
              <div className="form-divider" />
              <div className="flex items-center justify-between gap-4 flex-wrap">
                <p className="muted text-[11px] flex items-center gap-2">
                  <ShieldCheck size={14} className="accent" />
                  Encrypted before storage
                </p>
                <button
                  className="button button-primary"
                  type="submit"
                  disabled={uploading}
                >
                  {uploading ? (
                    <>
                      <LoaderCircle size={16} className="spin" />
                      Uploading securely...
                    </>
                  ) : (
                    <>
                      <UploadCloud size={16} />
                      Upload & Encrypt Radiograph
                    </>
                  )}
                </button>
              </div>
            </form>
            <aside className="space-y-5">
              <section className="panel panel-padding">
                <p className="eyebrow">Before you upload</p>
                <h2>A good image matters.</h2>
                <ul className="checklist">
                  {[
                    {
                      title: "PNG or JPEG",
                      text: "One image at a time, up to 20 MB.",
                    },
                    {
                      title: "Clear chest radiograph",
                      text: "Use an upright, frontal image with the chest visible.",
                    },
                    {
                      title: "Image dimensions",
                      text: "Between 32 and 4,096 pixels on each side.",
                    },
                    {
                      title: "Patient reference only",
                      text: "Use a pseudonymous code to identify the scan.",
                    },
                  ].map((item) => (
                    <li key={item.title}>
                      <Check size={15} />
                      <div>
                        <strong>{item.title}</strong>
                        {item.text}
                      </div>
                    </li>
                  ))}
                </ul>
              </section>
              <div className="notice notice-info">
                <Info size={18} className="shrink-0" />
                <div>
                  <strong>What happens next?</strong>
                  <p>
                    After upload, open the scan and run screening. The AI output
                    is available for clinical review.
                  </p>
                </div>
              </div>
            </aside>
          </div>
        )}
      </div>
    </AuthenticatedLayout>
  );
}
