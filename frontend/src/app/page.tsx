"use client";

import Link from "next/link";
import {
  ArrowRight,
  UploadCloud,
  FolderOpen,
  Clock3,
  CircleCheck,
  Activity,
  FileImage,
  RefreshCw,
  ShieldCheck,
  ScanLine,
} from "lucide-react";
import { useAuth } from "@/context/auth-context";
import { AuthenticatedLayout } from "@/components/layout/authenticated-layout";
import {
  PageHeader,
  StatusBadge,
  ResultBadge,
  EmptyState,
  LoadingState,
  ErrorState,
  ScanLink,
  MobileScanCards,
} from "@/components/ui";
import { useScans } from "@/lib/use-scans";
import { formatDate } from "@/lib/utils";

export default function DashboardPage() {
  const { user, role, token } = useAuth();
  const { scans, loading, error, refresh } = useScans(token);
  const unavailable = !scans.length && (loading || Boolean(error));
  const pending = scans.filter(
    (scan) => scan.prediction_status === "PENDING",
  ).length;
  const screened = scans.filter(
    (scan) => scan.prediction_status === "PROCESSED",
  ).length;
  const normal = scans.filter(
    (scan) => scan.predicted_class === "NORMAL",
  ).length;
  const pneumonia = scans.filter(
    (scan) => scan.predicted_class === "PNEUMONIA",
  ).length;
  const latest = [...scans]
    .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
    .slice(0, 5);
  const institution = role !== "doctor";
  const stats = [
    {
      title: "Accessible radiographs",
      value: scans.length,
      foot: institution
        ? "Across your institution"
        : "Uploaded by your account",
      icon: FolderOpen,
    },
    {
      title: "Awaiting screening",
      value: pending,
      foot: "Ready for AI analysis",
      icon: Clock3,
    },
    {
      title: "Screenings completed",
      value: screened,
      foot: "Available for clinical review",
      icon: CircleCheck,
    },
    {
      title: "Pneumonia outputs",
      value: pneumonia,
      foot: "AI output · clinician review required",
      icon: Activity,
    },
  ];
  return (
    <AuthenticatedLayout>
      <div className="page-stack">
        <PageHeader
          eyebrow="Your daily workspace"
          title="Clinical overview"
          description={`Welcome back, ${user?.full_name || user?.username || "practitioner"}. Here is where your radiograph workflow stands.`}
          actions={
            <>
              <button
                className="button button-secondary"
                onClick={refresh}
                disabled={loading}
                aria-label="Refresh overview"
              >
                <RefreshCw size={14} className={loading ? "spin" : ""} />
                Refresh
              </button>
              <Link
                className="button button-primary"
                href={institution ? "/scans?status=PENDING" : "/upload"}
              >
                {institution ? (
                  <ScanLine size={16} />
                ) : (
                  <UploadCloud size={16} />
                )}
                {institution ? "Open screening queue" : "Upload radiograph"}
              </Link>
            </>
          }
        />
        {error && (
          <ErrorState
            message={error}
            onRetry={refresh}
            title="Could not update your workspace"
          />
        )}
        <div className="stat-grid">
          {stats.map(({ title, value, foot, icon: Icon }) => (
            <div className="panel stat-card" key={title}>
              <div className="flex items-center justify-between gap-2">
                <span className="stat-label">{title}</span>
                <span className="stat-icon">
                  <Icon size={16} />
                </span>
              </div>
              <div className="stat-number">
                {loading && !scans.length
                  ? "—"
                  : error && !scans.length
                    ? "—"
                    : value}
              </div>
              <p className="stat-foot">{foot}</p>
            </div>
          ))}
        </div>
        <div className="dashboard-columns">
          <div className="space-y-5 min-w-0">
            <section className="scope-banner">
              <div>
                <p
                  className="eyebrow"
                  style={{ color: "inherit", marginBottom: 7 }}
                >
                  {institution
                    ? "Institutional access"
                    : "Your clinical workspace"}
                </p>
                <h2>
                  {institution
                    ? "A shared view. A focused review."
                    : "From upload to insight, in one place."}
                </h2>
                <p>
                  {institution
                    ? "Review radiographs across the institution, starting with scans awaiting screening."
                    : "Upload a chest radiograph, run AI screening, and keep each result connected to its patient identifier."}
                </p>
                <Link
                  className="text-link mt-4"
                  href={institution ? "/scans?status=PENDING" : "/upload"}
                >
                  {institution
                    ? unavailable
                      ? "View pending scans"
                      : `Explore ${pending} pending scans`
                    : "Start a new upload"}
                  <ArrowRight size={14} />
                </Link>
              </div>
              <ScanLine size={70} strokeWidth={0.8} />
            </section>
            <section className="panel overflow-hidden">
              <div className="section-heading">
                <div>
                  <h2>Recent radiographs</h2>
                  <p>
                    {institution
                      ? "Latest scans across your institution"
                      : "Your most recent uploads and screening activity"}
                  </p>
                </div>
                <Link href="/scans" className="text-link">
                  View all
                  <ArrowRight size={14} />
                </Link>
              </div>
              {loading && !scans.length ? (
                <LoadingState label="Loading your radiographs..." />
              ) : !scans.length ? (
                <EmptyState
                  title={
                    error
                      ? "Radiographs unavailable"
                      : "Your first scan starts here"
                  }
                  description={
                    error
                      ? "Retry the connection to see your records."
                      : "Upload a radiograph to begin. Your screening activity will appear here."
                  }
                  action={
                    !error && (
                      <Link href="/upload" className="button button-primary">
                        <UploadCloud size={15} />
                        Upload first radiograph
                      </Link>
                    )
                  }
                />
              ) : (
                <>
                  <div className="table-scroll desktop-scan-table">
                    <table className="scan-table">
                      <caption className="sr-only">
                        Five most recent accessible radiographs
                      </caption>
                      <thead>
                        <tr>
                          <th scope="col">Patient / scan</th>
                          <th scope="col">Status</th>
                          <th scope="col">AI output</th>
                          <th scope="col">
                            <span className="sr-only">Review</span>
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {latest.map((scan) => (
                          <tr key={scan.scan_id}>
                            <td>
                              <div className="patient-cell">
                                <span className="patient-icon">
                                  <FileImage size={15} />
                                </span>
                                <div>
                                  <strong>{scan.patient_id}</strong>
                                  <small>{formatDate(scan.created_at)}</small>
                                </div>
                              </div>
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
                  <MobileScanCards scans={latest} />
                </>
              )}
            </section>
          </div>
          <aside className="dashboard-side">
            <section className="panel panel-padding">
              <p className="eyebrow">Screening activity</p>
              <h2>A snapshot of your scans</h2>
              <div className="metric-row">
                <span>Screenings completed</span>
                <strong>
                  {unavailable ? "—" : `${screened}/${scans.length}`}
                </strong>
              </div>
              <div
                className="progress-track"
                role="progressbar"
                aria-label="Scans screened"
                aria-valuenow={unavailable ? undefined : screened}
                aria-valuemin={0}
                aria-valuemax={Math.max(scans.length, 1)}
              >
                <span
                  style={{
                    width: `${scans.length ? (screened / scans.length) * 100 : 0}%`,
                  }}
                />
              </div>
              <div className="metric-row">
                <span className="muted">Normal outputs</span>
                <span>{unavailable ? "—" : normal}</span>
              </div>
              <div className="metric-row">
                <span className="muted">Pneumonia outputs</span>
                <span>{unavailable ? "—" : pneumonia}</span>
              </div>
              <div className="form-divider" />
              <p className="muted text-[11px]">
                Counts reflect AI screening outputs, not confirmed clinical
                diagnoses.
              </p>
            </section>
            <section className="panel panel-padding">
              <div className="flex items-center justify-between">
                <h2>A simple workflow</h2>
                <ShieldCheck size={17} className="accent" />
              </div>
              {[
                {
                  title: "Upload securely",
                  text: "Add a PNG or JPEG with a patient identifier.",
                },
                {
                  title: "Run AI screening",
                  text: "Generate a result for the selected scan.",
                },
                {
                  title: "Review in context",
                  text: "Correlate the output with clinical findings.",
                },
              ].map((step, index) => (
                <div className="workflow-step" key={step.title}>
                  <span className="step-number">{index + 1}</span>
                  <div>
                    <strong>{step.title}</strong>
                    <p>{step.text}</p>
                  </div>
                </div>
              ))}
            </section>
          </aside>
        </div>
      </div>
    </AuthenticatedLayout>
  );
}
