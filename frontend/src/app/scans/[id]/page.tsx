"use client";

import { Suspense, use, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  ScanLine,
  ShieldCheck,
  Info,
  LoaderCircle,
  FileImage,
  AlertTriangle,
} from "lucide-react";
import { useAuth } from "@/context/auth-context";
import { apiClient } from "@/lib/api-client";
import {
  ApiError,
  type PredictionResult,
  type ScanMetadata,
} from "@/lib/types";
import { AuthenticatedLayout } from "@/components/layout/authenticated-layout";
import {
  PageHeader,
  StatusBadge,
  LoadingState,
  ErrorState,
} from "@/components/ui";
import { formatDate, formatBytes } from "@/lib/utils";
import { StoredRadiograph } from "@/components/radiograph-viewer";
import { PatientActions } from "@/components/patient-actions";

function ScanDetailContent({
  params,
}: {
  params: Promise<{ id: string }> | { id: string };
}) {
  const { id } =
    typeof (params as Promise<{ id: string }>).then === "function"
      ? use(params as Promise<{ id: string }>)
      : (params as { id: string });
  const { token } = useAuth();
  const router = useRouter();
  const [record, setRecord] = useState<{
    id: string;
    revision: number;
    scan: ScanMetadata | null;
    error: string | null;
  } | null>(null);
  const [revision, setRevision] = useState(0);
  const [prediction, setPrediction] = useState<PredictionResult | null>(null);
  const [predicting, setPredicting] = useState(false);
  const [predictionError, setPredictionError] = useState<string | null>(null);
  const [metadataWarning, setMetadataWarning] = useState(false);
  const busy = useRef(false);
  const generation = useRef(0);
  useEffect(() => {
    if (!token) return;
    let active = true;
    apiClient
      .getScan(id, token)
      .then((scan) => {
        if (active) setRecord({ id, revision, scan, error: null });
      })
      .catch((error: unknown) => {
        const message =
          error instanceof ApiError && error.status === 403
            ? "You do not have permission to view this scan. Choose a scan available to your account."
            : error instanceof ApiError && error.status === 404
              ? "This scan could not be found. Return to the repository to choose another."
              : error instanceof Error
                ? error.message
                : "Could not load this scan.";
        if (active) setRecord({ id, revision, scan: null, error: message });
      });
    return () => {
      active = false;
      generation.current += 1;
      busy.current = false;
      setPredicting(false);
    };
  }, [id, token, revision]);
  const scan =
    record?.id === id && record.revision === revision ? record.scan : null;
  const output = prediction?.scan_id === id ? prediction : null;
  const run = async () => {
    if (!token || busy.current) return;
    busy.current = true;
    setPredicting(true);
    setPredictionError(null);
    setMetadataWarning(false);
    const current = generation.current;
    try {
      const result = await apiClient.predictScan(id, token);
      if (generation.current !== current) return;
      setPrediction(result);
      // The screening can succeed even if the following metadata refresh fails.
      try {
        const updated = await apiClient.getScan(id, token);
        if (generation.current === current)
          setRecord({ id, revision, scan: updated, error: null });
      } catch {
        if (generation.current === current) setMetadataWarning(true);
      }
    } catch (error: unknown) {
      if (generation.current !== current) return;
      setPrediction(null);
      setPredictionError(
        error instanceof ApiError && error.status === 409
          ? "Integrity Tampering Error (409): This scan failed AES-GCM authentication tag verification. The encrypted file may be corrupted or modified. Do not use it for screening."
          : error instanceof Error
            ? error.message
            : "Screening did not complete. Please try again.",
      );
    } finally {
      if (generation.current === current) {
        busy.current = false;
        setPredicting(false);
      }
    }
  };
  return (
    <AuthenticatedLayout>
      <div className="page-stack">
        <Link href="/scans" className="text-link">
          <ArrowLeft size={15} />
          Back to scan repository
        </Link>
        {!record || record.id !== id || record.revision !== revision ? (
          <div className="panel">
            <LoadingState label="Loading scan details..." />
          </div>
        ) : record.error ? (
          <ErrorState
            title="Unable to access scan"
            message={record.error}
            onRetry={() => setRevision((value) => value + 1)}
          />
        ) : (
          scan && (
            <>
              <PageHeader
                eyebrow="Radiograph review"
                title={scan.patient_id}
                description="Scan details and AI screening, ready for your clinical review."
                actions={<StatusBadge status={scan.prediction_status} />}
              />
              <div className="upload-columns">
                <div className="space-y-5">
                  {token && <StoredRadiograph key={`${id}:${token}`} scanId={id} token={token} patientId={scan.patient_id} />}
                  <section className="panel panel-padding">
                    <div className="flex items-center gap-3 mb-6">
                      <span
                        className="empty-icon"
                        style={{ width: 42, height: 46, borderRadius: 9 }}
                      >
                        <FileImage size={20} />
                      </span>
                      <div>
                        <h2>Radiograph details</h2>
                        <p className="muted text-sm">
                          Stored securely · AES-256-GCM
                        </p>
                      </div>
                    </div>
                    <dl className="detail-grid">
                      <div className="detail-item">
                        <dt>Scan identifier</dt>
                        <dd className="font-mono">{scan.scan_id}</dd>
                      </div>
                      <div className="detail-item">
                        <dt>Patient identifier</dt>
                        <dd>{scan.patient_id}</dd>
                      </div>
                      <div className="detail-item">
                        <dt>Uploaded</dt>
                        <dd>{formatDate(scan.created_at)}</dd>
                      </div>
                      <div className="detail-item">
                        <dt>Uploaded by</dt>
                        <dd>{scan.uploaded_by}</dd>
                      </div>
                      <div className="detail-item">
                        <dt>Stored file size</dt>
                        <dd>{formatBytes(scan.file_size_bytes)}</dd>
                      </div>
                      <div className="detail-item">
                        <dt>Screening status</dt>
                        <dd>
                          {scan.prediction_status === "PROCESSED"
                            ? "Screened"
                            : "Awaiting screening"}
                        </dd>
                      </div>
                    </dl>
                    {token && <div className="form-divider" />}
                    {token && <PatientActions key={scan.patient_id} patientId={scan.patient_id} token={token}
                      onRenamed={() => setRevision((v) => v + 1)} onDeleted={() => router.push('/patients')} />}
                  </section>
                  {predictionError && (
                    <ErrorState
                      title="Screening could not complete"
                      message={predictionError}
                    />
                  )}
                  {metadataWarning && (
                    <div className="notice notice-warning" role="status">
                      <Info size={18} className="shrink-0" />
                      <p>
                        Screening completed. The latest scan status could not be
                        refreshed; your result remains available below.
                      </p>
                    </div>
                  )}
                  {output ? (
                    <section className="panel panel-padding" aria-live="polite">
                      <div className="screening-hero">
                        <span
                          className={`empty-icon ${output.prediction === "NORMAL" ? "accent" : ""}`}
                        >
                          <ScanLine size={28} />
                        </span>
                        <div>
                          <p className="eyebrow" style={{ marginBottom: 5 }}>
                            DenseNet121 AI Screening Output
                          </p>
                          <h2 className="screening-result">
                            {output.prediction}
                          </h2>
                          <p className="muted text-xs mt-1">
                            {output.prediction === "PNEUMONIA"
                              ? "Pneumonia pattern indicated. Clinical review is required."
                              : "Normal pattern indicated. Correlate with clinical findings."}
                          </p>
                        </div>
                      </div>
                      <div className="flex justify-between items-end gap-4 mt-6">
                        <div>
                          <p className="muted text-sm">
                            Model score for the selected class
                          </p>
                          <p className="score-number mt-1">
                            {(output.confidence * 100).toFixed(2)}%
                          </p>
                        </div>
                        <span className="badge badge-neutral">
                          AI screening score
                        </span>
                      </div>
                      <p className="muted text-sm mt-4">This score is uncalibrated. It is not the model’s accuracy or the chance that a patient has pneumonia.</p>
                      {[
                        {
                          label: "Pneumonia probability",
                          value: output.pneumonia_probability,
                          warning: true,
                        },
                        {
                          label: "Normal probability",
                          value: output.normal_probability,
                          warning: false,
                        },
                      ].map(({ label, value, warning }) => (
                        <div
                          key={label}
                          className={`probability-row${warning ? " warning" : ""}`}
                        >
                          <div className="metric-row">
                            <span>{label}</span>
                            <strong>{(value * 100).toFixed(1)}%</strong>
                          </div>
                          <div
                            className="progress-track"
                            role="progressbar"
                            aria-label={label}
                            aria-valuenow={Number((value * 100).toFixed(1))}
                            aria-valuemin={0}
                            aria-valuemax={100}
                          >
                            <span
                              style={{
                                width: `${Math.min(100, Math.max(0, value * 100))}%`,
                              }}
                            />
                          </div>
                        </div>
                      ))}
                      <div className="flex flex-wrap gap-4 muted text-sm mt-6">
                        <span>
                          Decision Threshold:{" "}
                          <strong>{output.threshold_applied}</strong>
                        </span>
                        <span>Compute: {output.device.toUpperCase()}</span>
                        {output.model_checkpoint_sha256 && <span title={output.model_checkpoint_sha256}>Model ID: <code>{output.model_checkpoint_sha256.slice(0, 12)}</code></span>}
                      </div>
                      <div className="notice notice-warning mt-6">
                        <AlertTriangle size={17} className="shrink-0" />
                        <div>
                          <strong>Mandatory Clinical Disclaimer</strong>
                          <p>{output.disclaimer}</p>
                        </div>
                      </div>
                    </section>
                  ) : (
                    <section className="panel">
                      <div className="empty-state">
                        <span className="empty-icon">
                          <ScanLine size={27} />
                        </span>
                        <div>
                          <h2>
                            {scan.prediction_status === "PROCESSED"
                              ? "This scan has been screened."
                              : "Ready for a closer look."}
                          </h2>
                          <p>
                            {scan.prediction_status === "PROCESSED"
                              ? `Previous AI output: ${scan.predicted_class || "unavailable"}. Run screening again to view the full probability breakdown.`
                              : "Run AI screening to see class probabilities and the model output for this radiograph."}
                          </p>
                        </div>
                        <button
                          className="button button-primary"
                          disabled={predicting}
                          onClick={run}
                        >
                          {predicting ? (
                            <LoaderCircle size={16} className="spin" />
                          ) : (
                            <ScanLine size={16} />
                          )}
                          {predicting
                            ? "Running AI screening..."
                            : "Run AI Screening"}
                        </button>
                      </div>
                    </section>
                  )}
                </div>
                <aside className="space-y-5">
                  <section className="panel panel-padding">
                    <p className="eyebrow">AI-assisted review</p>
                    <h2>Screen. Then correlate.</h2>
                    <p className="muted text-xs mt-3 mb-5">
                      Screening helps identify image patterns. It does not
                      establish a medical diagnosis.
                    </p>
                    {output && (
                      <button
                        className="button button-primary w-full mb-5"
                        disabled={predicting}
                        onClick={run}
                      >
                        {predicting ? (
                          <LoaderCircle size={15} className="spin" />
                        ) : (
                          <ScanLine size={15} />
                        )}
                        {predicting
                          ? "Running AI screening..."
                          : "Re-run AI screening"}
                      </button>
                    )}
                    <div className="form-divider" />
                    <p className="muted text-sm">
                      Review results with the radiograph, patient history, and
                      other clinical findings.
                    </p>
                  </section>
                  <div className="notice notice-info">
                    <ShieldCheck size={18} className="shrink-0" />
                    <div>
                      <strong>Protected at every step</strong>
                      <p>
                        The stored file is decrypted in memory for screening.
                        Its integrity is checked before analysis.
                      </p>
                    </div>
                  </div>
                </aside>
              </div>
            </>
          )
        )}
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
    <Suspense fallback={<LoadingState label="Opening scan..." />}>
      <ScanDetailContent params={params} />
    </Suspense>
  );
}
