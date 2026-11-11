"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { UploadCloud, Pencil, Trash2 } from "lucide-react";
import { apiClient } from "@/lib/api-client";

export function PatientActions({ patientId, token, onRenamed, onDeleted }: {
  patientId: string; token: string; onRenamed: () => void; onDeleted: () => void;
}) {
  const router = useRouter();
  const file = useRef<HTMLInputElement>(null);
  const busy = useRef(false);
  const [mode, setMode] = useState<'rename' | 'delete' | null>(null);
  const [newId, setNewId] = useState(patientId);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function perform(action: () => Promise<void>) {
    if (busy.current) return;
    busy.current = true; setWorking(true); setError(null);
    try { await action(); setMode(null); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'The operation did not complete.'); }
    finally {busy.current = false; setWorking(false);}
  }
  return <div className="patient-actions">
    <div className="flex flex-wrap gap-2">
      <button type="button" className="button button-primary" disabled={working} onClick={() => file.current?.click()}><UploadCloud size={17} />Add follow-up X-ray</button>
      <button type="button" className="button button-secondary" disabled={working} onClick={() => {setMode('rename'); setNewId(patientId); setError(null);}}><Pencil size={16} />Edit patient ID</button>
      <button type="button" className="button button-danger" disabled={working} onClick={() => {setMode('delete'); setError(null);}}><Trash2 size={16} />Delete patient</button>
    </div>
    <input ref={file} className="sr-only" type="file" accept="image/png,image/jpeg" aria-label={`Follow-up X-ray for ${patientId}`} disabled={working} onChange={(event) => {
      const selected = event.target.files?.[0]; event.target.value = '';
      if (!selected) return;
      void perform(async () => {
        if (!['image/jpeg', 'image/png'].includes(selected.type) || selected.size === 0 || selected.size > 20 * 1024 * 1024) throw new Error('Choose a non-empty PNG or JPEG up to 20 MB.');
        const scan = await apiClient.uploadScan(selected, patientId, token);
        router.push(`/scans/${encodeURIComponent(scan.scan_id)}`);
      });
    }} />
    <p className="field-help mt-3">A follow-up keeps earlier images as history. Open the new scan and run AI screening to update the latest result.</p>
    {working && <p role="status" className="muted mt-3">Working…</p>}
    {error && <p className="notice notice-warning mt-3" role="alert">{error}</p>}
    {mode === 'rename' && <form className="space-y-3 mt-4" onSubmit={(event) => {
      event.preventDefault(); void perform(async () => {await apiClient.renamePatient(patientId, newId, token); onRenamed();});
    }}>
      <label className="field-label" htmlFor={`patient-id-${patientId}`}>New pseudonymous patient ID</label>
      <input id={`patient-id-${patientId}`} className="input" value={newId} onChange={(e) => setNewId(e.target.value)} required pattern="[a-zA-Z0-9_\-]{3,64}" minLength={3} maxLength={64} disabled={working} />
      <p className="field-help">Updates the ID on all this patient’s scans you can manage. Existing patient IDs cannot be merged.</p>
      <div className="flex gap-2"><button className="button button-primary" type="submit" disabled={working}>Save patient ID</button><button className="button button-secondary" type="button" disabled={working} onClick={() => setMode(null)}>Cancel</button></div>
    </form>}
    {mode === 'delete' && <div className="notice notice-warning mt-4" role="alert">
      <div><strong>Delete {patientId} and their stored X-rays?</strong><p>This permanently removes every scan you can manage for this ID, including encrypted images and AI results. Your original files and the training dataset remain on your device.</p>
        <div className="flex flex-wrap gap-2 mt-3"><button type="button" className="button button-danger" disabled={working} onClick={() => void perform(async () => {await apiClient.deletePatient(patientId, token); onDeleted();})}>Confirm patient deletion</button><button type="button" className="button button-secondary" disabled={working} onClick={() => setMode(null)}>Cancel</button></div>
      </div>
    </div>}
  </div>;
}
