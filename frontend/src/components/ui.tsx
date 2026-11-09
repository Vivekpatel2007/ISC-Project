import Link from "next/link";
import {
  Activity,
  ArrowRight,
  AlertCircle,
  FileImage,
  LoaderCircle,
} from "lucide-react";
import type { ReactNode } from "react";
import type { ScanMetadata } from "@/lib/types";
import { formatBytes, formatDate } from "@/lib/utils";

export function Brand() {
  return (
    <div className="brand">
      <span className="brand-mark">
        <Activity size={24} strokeWidth={2.1} aria-hidden="true" />
      </span>
      <span>
        <strong>
          PulmoScan<span className="brand-dot">.</span>
        </strong>
        <small>CLARITY IN EVERY SCAN</small>
      </span>
    </div>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string;
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p className="page-description">{description}</p>
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const done = status === "PROCESSED";
  return (
    <span className={`badge ${done ? "badge-teal" : "badge-amber"}`}>
      <span className="status-dot" />
      {done ? "Screened" : status === "PENDING" ? "Pending" : status}
    </span>
  );
}

export function ResultBadge({ result }: { result: string | null }) {
  if (!result) return <span className="muted text-xs">Not screened</span>;
  return (
    <span
      className={`badge ${result === "NORMAL" ? "badge-teal" : "badge-rose"}`}
    >
      {result === "NORMAL"
        ? "Normal"
        : result === "PNEUMONIA"
          ? "Pneumonia"
          : result}
    </span>
  );
}

export function LoadingState({
  label = "Loading your workspace...",
}: {
  label?: string;
}) {
  return (
    <div className="empty-state" role="status">
      <LoaderCircle className="spin accent" size={28} />
      <p>{label}</p>
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
  title = "Something needs attention",
}: {
  message: string;
  onRetry?: () => void;
  title?: string;
}) {
  return (
    <div className="notice notice-error" role="alert">
      <AlertCircle size={20} className="shrink-0" />
      <div className="min-w-0 flex-1">
        <strong>{title}</strong>
        <p>{message}</p>
      </div>
      {onRetry && (
        <button
          type="button"
          className="button button-small button-secondary"
          onClick={onRetry}
        >
          Try again
        </button>
      )}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <span className="empty-icon">
        <FileImage size={27} strokeWidth={1.5} />
      </span>
      <div>
        <h3>{title}</h3>
        <p>{description}</p>
      </div>
      {action}
    </div>
  );
}

export function ScanLink({
  id,
  children = "Review scan",
}: {
  id: string;
  children?: ReactNode;
}) {
  return (
    <Link className="text-link" href={`/scans/${encodeURIComponent(id)}`}>
      {children}
      <ArrowRight size={15} aria-hidden="true" />
    </Link>
  );
}

export function MobileScanCards({ scans }: { scans: ScanMetadata[] }) {
  return (
    <div className="mobile-scan-list">
      {scans.map((scan) => (
        <article key={scan.scan_id} className="mobile-scan">
          <div className="flex items-center justify-between gap-3">
            <strong className="text-sm">{scan.patient_id}</strong>
            <StatusBadge status={scan.prediction_status} />
          </div>
          <p className="muted text-[11px] mt-2">
            {formatDate(scan.created_at)} · {formatBytes(scan.file_size_bytes)}
          </p>
          <div className="flex items-center justify-between mt-4">
            <ResultBadge result={scan.predicted_class} />
            <ScanLink id={scan.scan_id}>Review</ScanLink>
          </div>
        </article>
      ))}
    </div>
  );
}
