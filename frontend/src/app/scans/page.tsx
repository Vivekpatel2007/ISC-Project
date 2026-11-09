"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  Search,
  RefreshCw,
  UploadCloud,
  FileImage,
  ChevronLeft,
  ChevronRight,
  X,
} from "lucide-react";
import { useAuth } from "@/context/auth-context";
import { AuthenticatedLayout } from "@/components/layout/authenticated-layout";
import {
  PageHeader,
  StatusBadge,
  ResultBadge,
  EmptyState,
  ErrorState,
  LoadingState,
  ScanLink,
  MobileScanCards,
} from "@/components/ui";
import { useScans } from "@/lib/use-scans";
import { formatBytes, formatDate } from "@/lib/utils";

type StatusFilter = "ALL" | "PENDING" | "PROCESSED";
const PAGE_SIZE = 8;

function ScanRepository() {
  const { token, role } = useAuth();
  const { scans, loading, error, refresh } = useScans(token);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<StatusFilter>("ALL");
  const [sort, setSort] = useState("newest");
  const [page, setPage] = useState(1);
  const params = useSearchParams();
  const requestedStatus = params.get("status");
  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (active) {
        setStatus(
          requestedStatus === "PENDING" || requestedStatus === "PROCESSED"
            ? requestedStatus
            : "ALL",
        );
        setPage(1);
      }
    });
    return () => {
      active = false;
    };
  }, [requestedStatus]);
  const needle = query.trim().toLowerCase();
  const filtered = scans
    .filter(
      (scan) =>
        (status === "ALL" || scan.prediction_status === status) &&
        [scan.patient_id, scan.scan_id, scan.uploaded_by].some((value) =>
          value.toLowerCase().includes(needle),
        ),
    )
    .sort((a, b) =>
      sort === "patient"
        ? a.patient_id.localeCompare(b.patient_id)
        : sort === "oldest"
          ? Date.parse(a.created_at) - Date.parse(b.created_at)
          : Date.parse(b.created_at) - Date.parse(a.created_at),
    );
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, pages);
  const visible = filtered.slice(
    (currentPage - 1) * PAGE_SIZE,
    currentPage * PAGE_SIZE,
  );
  const reset = () => {
    setQuery("");
    setStatus("ALL");
    setPage(1);
  };
  return (
    <AuthenticatedLayout>
      <div className="page-stack">
        <PageHeader
          eyebrow={
            role === "doctor"
              ? "Your radiograph library"
              : "Institutional radiograph library"
          }
          title={role === "doctor" ? "My scans" : "Scan repository"}
          description={
            role === "doctor"
              ? "Every upload and screening result, organized for your review."
              : "Explore accessible radiographs across the institution and find scans ready for screening."
          }
          actions={
            <>
              <button
                className="button button-secondary"
                disabled={loading}
                onClick={refresh}
              >
                <RefreshCw size={14} className={loading ? "spin" : ""} />
                Refresh
              </button>
              <Link href="/upload" className="button button-primary">
                <UploadCloud size={15} />
                Upload radiograph
              </Link>
            </>
          }
        />
        {error && (
          <ErrorState
            message={error}
            title="Could not update scan records"
            onRetry={refresh}
          />
        )}
        <section className="panel overflow-hidden">
          <div className="filter-toolbar">
            <div className="field-icon search-field">
              <Search size={16} />
              <input
                className="input"
                aria-label="Search scans"
                placeholder="Search by patient ID, scan ID or uploader..."
                value={query}
                onChange={(event) => {
                  setQuery(event.target.value);
                  setPage(1);
                }}
              />
            </div>
            <div
              className="segmented-control"
              role="group"
              aria-label="Filter scans by status"
            >
              {(
                [
                  { value: "ALL", label: "All scans" },
                  { value: "PENDING", label: "Pending" },
                  { value: "PROCESSED", label: "Screened" },
                ] as const
              ).map((item) => (
                <button
                  key={item.value}
                  type="button"
                  aria-pressed={status === item.value}
                  onClick={() => {
                    setStatus(item.value);
                    setPage(1);
                  }}
                >
                  {item.label}
                </button>
              ))}
            </div>
            <label className="sr-only" htmlFor="scan-sort">
              Sort scans
            </label>
            <select
              id="scan-sort"
              value={sort}
              className="input"
              style={{ width: "auto" }}
              onChange={(event) => {
                setSort(event.target.value);
                setPage(1);
              }}
            >
              <option value="newest">Newest first</option>
              <option value="oldest">Oldest first</option>
              <option value="patient">Patient ID</option>
            </select>
          </div>
          <div className="filter-summary">
            <span aria-live="polite">
              {loading
                ? "Updating scans..."
                : `${filtered.length} ${filtered.length === 1 ? "scan" : "scans"}${status === "PENDING" ? " awaiting screening" : status === "PROCESSED" ? " screened" : " in your library"}`}
            </span>
            {(query || status !== "ALL") && (
              <button className="text-link" type="button" onClick={reset}>
                <X size={12} />
                Clear filters
              </button>
            )}
          </div>
          {loading && !scans.length ? (
            <LoadingState label="Fetching authorized radiograph records..." />
          ) : !filtered.length ? (
            <EmptyState
              title={
                error
                  ? "Scan records unavailable"
                  : scans.length
                    ? "No matching scans found"
                    : "No radiographs yet"
              }
              description={
                error
                  ? "Try refreshing your connection to view the repository."
                  : scans.length
                    ? "Try another patient identifier or clear your filters."
                    : "Your uploaded scans will appear here, ready for screening and review."
              }
              action={
                error ? undefined : scans.length ? (
                  <button className="button button-secondary" onClick={reset}>
                    Clear filters
                  </button>
                ) : (
                  <Link href="/upload" className="button button-primary">
                    <UploadCloud size={15} />
                    Upload first scan
                  </Link>
                )
              }
            />
          ) : (
            <>
              <div className="table-scroll desktop-scan-table">
                <table className="scan-table">
                  <caption className="sr-only">Accessible radiographs</caption>
                  <thead>
                    <tr>
                      <th scope="col">Patient / scan</th>
                      <th scope="col">Uploaded</th>
                      <th scope="col">File size</th>
                      <th scope="col">Status</th>
                      <th scope="col">AI output</th>
                      <th scope="col">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visible.map((scan) => (
                      <tr key={scan.scan_id}>
                        <td>
                          <div className="patient-cell">
                            <span className="patient-icon">
                              <FileImage size={16} />
                            </span>
                            <div>
                              <strong>{scan.patient_id}</strong>
                              <small title={scan.scan_id}>
                                {scan.scan_id.slice(0, 12)}…
                              </small>
                            </div>
                          </div>
                        </td>
                        <td>
                          <p>{formatDate(scan.created_at)}</p>
                          <p className="muted text-[10px] mt-1">
                            by {scan.uploaded_by}
                          </p>
                        </td>
                        <td className="muted">
                          {formatBytes(scan.file_size_bytes)}
                        </td>
                        <td>
                          <StatusBadge status={scan.prediction_status} />
                        </td>
                        <td>
                          <ResultBadge result={scan.predicted_class} />
                        </td>
                        <td>
                          <ScanLink id={scan.scan_id}>Review</ScanLink>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <MobileScanCards scans={visible} />
              <footer className="table-footer">
                <span>
                  Showing {(currentPage - 1) * PAGE_SIZE + 1}–
                  {Math.min(currentPage * PAGE_SIZE, filtered.length)} of{" "}
                  {filtered.length} scans
                </span>
                <div className="flex items-center gap-3">
                  <button
                    className="icon-button"
                    disabled={currentPage === 1}
                    onClick={() => setPage(currentPage - 1)}
                    aria-label="Previous page"
                  >
                    <ChevronLeft size={16} />
                  </button>
                  <span>
                    Page {currentPage} of {pages}
                  </span>
                  <button
                    className="icon-button"
                    disabled={currentPage === pages}
                    onClick={() => setPage(currentPage + 1)}
                    aria-label="Next page"
                  >
                    <ChevronRight size={16} />
                  </button>
                </div>
              </footer>
            </>
          )}
        </section>
      </div>
    </AuthenticatedLayout>
  );
}

export default function ScansHistoryPage() {
  return (
    <Suspense fallback={<LoadingState label="Opening your repository..." />}>
      <ScanRepository />
    </Suspense>
  );
}
