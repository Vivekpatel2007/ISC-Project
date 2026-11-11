"use client";

import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import type { ReadinessStatus } from "@/lib/types";

export function ActiveModel() {
  const [status, setStatus] = useState<ReadinessStatus | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    let active = true;
    apiClient.checkReadiness().then((result) => {if (active) setStatus(result);}).catch(() => {if (active) setError(true);});
    return () => {active = false;};
  }, []);
  return <section className="panel panel-padding"><p className="eyebrow">Inference engine</p><h2>Active model</h2>
    {status?.model ? <><p className="mt-3"><strong>{status.model.architecture}</strong> · {status.model.device.toUpperCase()}</p>
      <p className="muted text-sm mt-2">{status.model.checkpoint_finalized === null ? 'Legacy checkpoint' : 'Finalized training artifact'} · epoch {status.model.epoch}</p>
      <p className="field-label mt-4">Checkpoint SHA-256</p><code className="model-fingerprint">{status.model.checkpoint_sha256}</code>
      <p className="field-help">Identifies the model loaded by the backend. Downloaded models become active only after a deliberate configuration change and restart. Scores are uncalibrated.</p></> : <p className="muted mt-3" role="status">{error ? 'Model status unavailable. Check that the backend is running and ready.' : 'Checking model status…'}</p>}
  </section>;
}
