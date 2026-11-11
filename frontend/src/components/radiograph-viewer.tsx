"use client";

import { useEffect, useRef, useState } from "react";
import { Expand, X, ZoomIn, ZoomOut, RotateCcw } from "lucide-react";
import { apiClient } from "@/lib/api-client";
import type { ExplanationResult } from "@/lib/types";

function OverlayControls({ enabled, opacity, onToggle, onOpacity }: {
  enabled: boolean; opacity: number; onToggle: (enabled: boolean) => void; onOpacity: (value: number) => void;
}) {
  return <div className="overlay-controls">
    <div className="segmented-control" role="group" aria-label="Radiograph display">
      <button type="button" aria-pressed={!enabled} onClick={() => onToggle(false)}>Original</button>
      <button type="button" aria-pressed={enabled} onClick={() => onToggle(true)}>Heatmap</button>
    </div>
    <label className="overlay-opacity">Heatmap opacity
      <input type="range" aria-label="Heatmap opacity" min="0" max="100" step="5" value={Math.round(opacity * 100)} disabled={!enabled}
        onChange={(event) => onOpacity(Number(event.target.value) / 100)} />
      <span>{Math.round(opacity * 100)}%</span>
    </label>
  </div>;
}

export function RadiographViewer({ src, label, explanation }: { src: string; label: string; explanation?: ExplanationResult | null }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [expanded, setExpanded] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [overlayChoice, setOverlayChoice] = useState<boolean | null>(null);
  const [opacity, setOpacity] = useState(.45);
  const available = explanation?.status === 'available';
  const overlayEnabled = available && (overlayChoice ?? true);
  const heatmap = available ? `data:image/png;base64,${explanation.heatmap_png_base64}` : undefined;
  const overlayControls = available && <OverlayControls enabled={overlayEnabled} opacity={opacity} onToggle={setOverlayChoice} onOpacity={setOpacity} />;
  useEffect(() => {
    if (!expanded) return;
    const modal = dialog.current;
    modal?.showModal();
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      modal?.close();
      document.body.style.overflow = previous;
    };
  }, [expanded]);

  return <>
    {overlayControls}
    <button type="button" className="radiograph-preview" aria-label={`Enlarge ${label}`}
      onClick={() => { setZoom(1); setExpanded(true); }}>
      {/* Authorized in-memory blob URL; do not proxy medical images through an optimizer. */}
      <span className="radiograph-stack">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={src} alt={label} />
        {/* eslint-disable-next-line @next/next/no-img-element */}
        {overlayEnabled && <img src={heatmap} alt="" aria-hidden="true" className="heatmap-overlay" style={{opacity}} />}
      </span>
      <span><Expand size={18} /> Click to enlarge</span>
    </button>
    <dialog ref={dialog} className="radiograph-dialog" aria-label={`${label} enlarged view`}
      onCancel={() => setExpanded(false)} onClose={() => setExpanded(false)}
      onClick={(event) => { if (event.target === event.currentTarget) setExpanded(false); }}>
      <div className="viewer-toolbar">
        <div><h2>{label}</h2><p>Original image · scroll to explore when zoomed</p></div>
        <button type="button" className="button button-secondary" aria-label="Close enlarged image" onClick={() => setExpanded(false)}><X size={20} /></button>
      </div>
      <div className="viewer-controls" role="group" aria-label="Image zoom">
        <button type="button" className="button button-secondary" aria-label="Zoom out" disabled={zoom <= 1} onClick={() => setZoom((v) => Math.max(1, v - .25))}><ZoomOut size={18} /></button>
        <output aria-live="polite">{Math.round(zoom * 100)}%</output>
        <button type="button" className="button button-secondary" aria-label="Zoom in" disabled={zoom >= 3} onClick={() => setZoom((v) => Math.min(3, v + .25))}><ZoomIn size={18} /></button>
        <button type="button" className="button button-ghost" onClick={() => setZoom(1)}><RotateCcw size={17} /> Fit image</button>
      </div>
      {expanded && overlayControls}
      <div className="viewer-viewport" tabIndex={0} aria-label="Scrollable radiograph">
        {expanded && <div className="viewer-image-stack" style={{width: `${zoom * 100}%`, height: `${zoom * 100}%`}}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={src} alt={`${label}, enlarged`} />
          {/* eslint-disable-next-line @next/next/no-img-element */}
          {overlayEnabled && <img src={heatmap} alt="" aria-hidden="true" className="heatmap-overlay" style={{opacity}} />}
        </div>}
      </div>
      <p className="viewer-caption">{explanation ? `Grad-CAM for ${explanation.target_class}. Relative model contribution, not a disease outline.` : 'Original radiograph without AI overlays.'} Press Escape to close.</p>
    </dialog>
  </>;
}

export function StoredRadiograph({ scanId, token, patientId, explanation }: { scanId: string; token: string; patientId: string; explanation?: ExplanationResult | null }) {
  const [image, setImage] = useState<{url?: string; error?: string; requestKey: string} | null>(null);
  const [revision, setRevision] = useState(0);
  const requestKey = `${scanId}:${token}:${revision}`;
  useEffect(() => {
    const abort = new AbortController();
    let url: string | undefined;
    apiClient.getScanImage(scanId, token, abort.signal).then((blob) => {
      if (abort.signal.aborted) return;
      url = URL.createObjectURL(blob);
      setImage({url, requestKey});
    }).catch((error: unknown) => {
      if (!abort.signal.aborted) setImage({error: error instanceof Error ? error.message : 'Image unavailable.', requestKey});
    });
    return () => { abort.abort(); if (url) URL.revokeObjectURL(url); };
  }, [scanId, token, requestKey]);
  const current = image?.requestKey === requestKey ? image : null;
  return <section className="panel overflow-hidden" aria-label="Stored radiograph">
    <div className="panel-padding"><h2>Chest radiograph</h2><p className="muted text-sm">Open the image for a larger view and zoom controls.</p></div>
    {current?.url ? <RadiographViewer src={current.url} label={`Radiograph for ${patientId}`} explanation={explanation} /> : current?.error ?
      <div className="panel-padding" role="alert"><p>{current.error}</p><button type="button" className="button button-secondary mt-4" onClick={() => setRevision((v) => v + 1)}>Retry image</button></div> :
      <p className="panel-padding muted" role="status">Loading protected image…</p>}
    {explanation && <div className="panel-padding explanation-caption">
      <h3>Grad-CAM for {explanation.target_class}</h3>
      {explanation.status === 'available' ? <div className="heatmap-legend"><span>Lower contribution</span><span className="heatmap-legend-gradient" /><span>Higher contribution</span></div> :
        <p className="notice notice-info mt-3" role="status">No spatially informative positive-contribution map was found for this class. The screening result is unchanged.</p>}
      <p className="muted text-sm mt-3">{explanation.limitation}</p>
      <details className="review-disclosure"><summary>Explanation details</summary><dl className="detail-grid mt-3">
        <div className="detail-item"><dt>Target</dt><dd>Raw {explanation.target_class} class score</dd></div>
        <div className="detail-item"><dt>Feature layer</dt><dd>{explanation.target_layer}</dd></div>
        <div className="detail-item"><dt>Device / precision</dt><dd>{explanation.device} / {explanation.precision}</dd></div>
        <div className="detail-item"><dt>Model SHA-256</dt><dd className="model-fingerprint">{explanation.model_checkpoint_sha256}</dd></div>
      </dl></details>
    </div>}
  </section>;
}
