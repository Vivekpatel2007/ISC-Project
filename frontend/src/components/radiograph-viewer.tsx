"use client";

import { useEffect, useRef, useState } from "react";
import { Expand, X, ZoomIn, ZoomOut, RotateCcw } from "lucide-react";
import { apiClient } from "@/lib/api-client";

export function RadiographViewer({ src, label }: { src: string; label: string }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [expanded, setExpanded] = useState(false);
  const [zoom, setZoom] = useState(1);
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
    <button type="button" className="radiograph-preview" aria-label={`Enlarge ${label}`}
      onClick={() => { setZoom(1); setExpanded(true); }}>
      {/* Authorized in-memory blob URL; do not proxy medical images through an optimizer. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={src} alt={label} />
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
      <div className="viewer-viewport" tabIndex={0} aria-label="Scrollable radiograph">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        {expanded && <img src={src} alt={`${label}, enlarged`} style={{width: `${zoom * 100}%`, height: `${zoom * 100}%`}} />}
      </div>
      <p className="viewer-caption">Viewing aid only. The image has no AI overlays or annotations. Press Escape to close.</p>
    </dialog>
  </>;
}

export function StoredRadiograph({ scanId, token, patientId }: { scanId: string; token: string; patientId: string }) {
  const [image, setImage] = useState<{url?: string; error?: string; revision: number} | null>(null);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const abort = new AbortController();
    let url: string | undefined;
    apiClient.getScanImage(scanId, token, abort.signal).then((blob) => {
      if (abort.signal.aborted) return;
      url = URL.createObjectURL(blob);
      setImage({url, revision});
    }).catch((error: unknown) => {
      if (!abort.signal.aborted) setImage({error: error instanceof Error ? error.message : 'Image unavailable.', revision});
    });
    return () => { abort.abort(); if (url) URL.revokeObjectURL(url); };
  }, [scanId, token, revision]);
  const current = image?.revision === revision ? image : null;
  return <section className="panel overflow-hidden" aria-label="Stored radiograph">
    <div className="panel-padding"><h2>Chest radiograph</h2><p className="muted text-sm">Open the image for a larger view and zoom controls.</p></div>
    {current?.url ? <RadiographViewer src={current.url} label={`Radiograph for ${patientId}`} /> : current?.error ?
      <div className="panel-padding" role="alert"><p>{current.error}</p><button type="button" className="button button-secondary mt-4" onClick={() => setRevision((v) => v + 1)}>Retry image</button></div> :
      <p className="panel-padding muted" role="status">Loading protected image…</p>}
  </section>;
}
