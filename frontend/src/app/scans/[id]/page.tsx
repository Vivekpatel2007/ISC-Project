"use client";

import { Suspense, use, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  ShieldCheck,
  FileImage,
} from "lucide-react";
import { useAuth } from "@/context/auth-context";
import { apiClient } from "@/lib/api-client";
import {
  ApiError,
  type PredictionResult,
  type ScanMetadata,
  type ExplanationResult,
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
import { ScreeningPanel } from "@/components/screening-panel";

function ScanDetailContent({ id }: { id: string }) {
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
  const [explanation, setExplanation] = useState<ExplanationResult | null>(null);
  const [explaining, setExplaining] = useState(false);
  const [explanationError, setExplanationError] = useState<string | null>(null);
  const explanationRequest = useRef<AbortController | null>(null);
  const explanationBusy = useRef(false);
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
      explanationBusy.current = false;
      explanationRequest.current?.abort();
      setPredicting(false);
      setExplaining(false);
    };
  }, [id, token, revision]);
  const scan =
    record?.id === id && record.revision === revision ? record.scan : null;
  const output = prediction?.scan_id === id ? prediction : null;
  const run = async () => {
    if (!token || busy.current || explanationBusy.current) return;
    busy.current = true;
    setPredicting(true);
    setPredictionError(null);
    setMetadataWarning(false);
    setExplanation(null);
    setExplanationError(null);
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
  const explain = async () => {
    if (!token || !output?.model_checkpoint_sha256 || busy.current || explanationBusy.current) return;
    explanationBusy.current = true;
    setExplaining(true);
    setExplanationError(null);
    const current = generation.current;
    const abort = new AbortController();
    explanationRequest.current = abort;
    try {
      const result = await apiClient.explainScan(id, output.prediction, output.model_checkpoint_sha256, token, abort.signal);
      if (generation.current !== current || abort.signal.aborted) return;
      if (result.scan_id !== id || result.target_class !== output.prediction || result.model_checkpoint_sha256 !== output.model_checkpoint_sha256) {
        throw new Error('Explanation identity did not match this screening result. Re-run screening before trying again.');
      }
      setExplanation(result);
    } catch (error) {
      if (generation.current === current && !abort.signal.aborted) setExplanationError(error instanceof Error ? error.message : 'Explanation could not be generated.');
    } finally {
      if (generation.current === current && !abort.signal.aborted) {
        explanationBusy.current = false;
        setExplaining(false);
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
              <div className="scan-review-grid">
                <div className="scan-review-screening">
                  <ScreeningPanel scan={scan} output={output} predicting={predicting}
                    error={predictionError} metadataWarning={metadataWarning} onRun={run}
                    onExplain={explain} explaining={explaining} explanationReady={!!explanation} explanationError={explanationError} />
                </div>
                <div className="scan-review-image" id="radiograph-image" tabIndex={-1}>
                  {token && <StoredRadiograph key={`${id}:${token}`} scanId={id} token={token} patientId={scan.patient_id} explanation={explanation} />}
                </div>
              </div>
              <section className="panel panel-padding" aria-label="Scan information and patient records">
                <details className="review-disclosure">
                  <summary><FileImage size={18} />Radiograph details</summary>
                  <dl className="detail-grid mt-5">
                    <div className="detail-item"><dt>Scan identifier</dt><dd className="font-mono">{scan.scan_id}</dd></div>
                    <div className="detail-item"><dt>Patient identifier</dt><dd>{scan.patient_id}</dd></div>
                    <div className="detail-item"><dt>Uploaded</dt><dd>{formatDate(scan.created_at)}</dd></div>
                    <div className="detail-item"><dt>Uploaded by</dt><dd>{scan.uploaded_by}</dd></div>
                    <div className="detail-item"><dt>Stored file size</dt><dd>{formatBytes(scan.file_size_bytes)}</dd></div>
                    <div className="detail-item"><dt>Storage protection</dt><dd>AES-256-GCM</dd></div>
                  </dl>
                </details>
                {token && <details className="review-disclosure patient-management">
                  <summary>Follow-up & patient records</summary>
                  <p className="muted text-sm mt-4 mb-4">For a new examination, add a follow-up X-ray. Earlier images and screening results stay in the patient history.</p>
                  <fieldset className="patient-action-fieldset" disabled={predicting || explaining}>
                    <legend className="sr-only">Patient record actions</legend>
                    <PatientActions key={scan.patient_id} patientId={scan.patient_id} token={token}
                      onRenamed={() => setRevision((v) => v + 1)} onDeleted={() => router.push('/patients')} />
                  </fieldset>
                </details>}
              </section>
              <p className="scan-storage-note"><ShieldCheck size={17} />The image is decrypted in memory after access and integrity checks.</p>
            </>
          )
        )}
      </div>
    </AuthenticatedLayout>
  );
}

function ResolvedScanDetail({ params }: { params: Promise<{ id: string }> | { id: string } }) {
  const { id } = typeof (params as Promise<{ id: string }>).then === "function"
    ? use(params as Promise<{ id: string }>) : params as { id: string };
  // A different scan gets fresh request state, errors, and screening output.
  return <ScanDetailContent key={id} id={id} />;
}

export default function ScanDetailPage({
  params,
}: {
  params: Promise<{ id: string }> | { id: string };
}) {
  return (
    <Suspense fallback={<LoadingState label="Opening scan..." />}>
      <ResolvedScanDetail params={params} />
    </Suspense>
  );
}
