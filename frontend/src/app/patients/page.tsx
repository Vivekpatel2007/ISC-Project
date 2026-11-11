"use client";

import { useState } from "react";
import Link from "next/link";
import { RefreshCw, UploadCloud, Search } from "lucide-react";
import { useAuth } from "@/context/auth-context";
import { AuthenticatedLayout } from "@/components/layout/authenticated-layout";
import { PageHeader, LoadingState, ErrorState, ResultBadge, StatusBadge } from "@/components/ui";
import { PatientActions } from "@/components/patient-actions";
import { useScans } from "@/lib/use-scans";
import { patientGroups } from "@/lib/patients";
import { formatDate } from "@/lib/utils";

export default function PatientsPage() {
  const { token } = useAuth();
  const { scans, loading, error, refresh } = useScans(token);
  const [query, setQuery] = useState('');
  const groups = patientGroups(scans).filter((patient) => patient.patientId.toLowerCase().includes(query.toLowerCase().trim()));
  return <AuthenticatedLayout><div className="page-stack">
    <PageHeader eyebrow="Patient follow-up" title="Patients" description="Review the latest X-ray, follow changes over time, and manage pseudonymous patient records."
      actions={<><button className="button button-secondary" onClick={refresh} disabled={loading}><RefreshCw size={16} />Refresh</button><Link href="/upload" className="button button-primary"><UploadCloud size={17} />Add patient / X-ray</Link></>} />
    <div className="notice notice-info"><p>The newest upload determines the current screening status. Its AI output is not a confirmed diagnosis. If it has not been screened, the status is pending; older results stay in the history.</p></div>
    <div className="field-icon"><Search size={18} /><input className="input" aria-label="Search patients" placeholder="Search patient ID…" value={query} onChange={(e) => setQuery(e.target.value)} /></div>
    {error && <ErrorState title="Could not refresh patients" message={error} onRetry={refresh} />}
    {loading ? <LoadingState label="Loading patient records…" /> : groups.length === 0 ? <section className="panel panel-padding"><h2>{query ? 'No matching patients' : 'No patient records yet'}</h2><p className="muted mt-2">Upload an X-ray with a pseudonymous patient ID to create a record.</p></section> : groups.map(({patientId, latest, history}) => <section className="panel panel-padding" key={patientId}>
      <div className="patient-heading"><div><p className="eyebrow">{history.length} {history.length === 1 ? 'X-ray' : 'X-rays'} on record</p><h2>{patientId}</h2><p className="muted text-sm mt-2">Latest upload: {formatDate(latest.created_at)}</p></div>
        <div role="group" aria-label={`Latest AI output for ${patientId}`}><p className="field-help mb-2">Latest AI output</p>{latest.prediction_status === 'PROCESSED' ? <ResultBadge result={latest.predicted_class} /> : <StatusBadge status={latest.prediction_status} />}</div>
      </div>
      <Link className="button button-secondary mt-4 mb-5" href={`/scans/${encodeURIComponent(latest.scan_id)}`}>{latest.prediction_status === 'PROCESSED' ? 'Review latest X-ray' : 'Open latest X-ray & screen'}</Link>
      {token && <PatientActions patientId={patientId} token={token} onRenamed={refresh} onDeleted={refresh} />}
      <details className="patient-history"><summary>X-ray history ({history.length})</summary><ul>{history.map((scan) => <li key={scan.scan_id}><Link href={`/scans/${encodeURIComponent(scan.scan_id)}`}>{formatDate(scan.created_at)} · {scan.scan_id.slice(0, 8)}</Link>{scan.prediction_status === 'PROCESSED' ? <ResultBadge result={scan.predicted_class} /> : <StatusBadge status={scan.prediction_status} />}</li>)}</ul></details>
    </section>)}
  </div></AuthenticatedLayout>;
}
