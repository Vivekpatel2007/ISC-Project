"use client";

import { AlertTriangle, Info, LoaderCircle, ScanLine, Eye } from "lucide-react";
import { ErrorState, ResultBadge } from "@/components/ui";
import { formatModelScore } from "@/lib/utils";
import type { PredictionResult, ScanMetadata } from "@/lib/types";

export function ScreeningPanel({ scan, output, predicting, error, metadataWarning, onRun, onExplain, explaining = false, explanationReady = false, explanationError }: {
  scan: ScanMetadata;
  output: PredictionResult | null;
  predicting: boolean;
  error: string | null;
  metadataWarning: boolean;
  onRun: () => void;
  onExplain?: () => void;
  explaining?: boolean;
  explanationReady?: boolean;
  explanationError?: string | null;
}) {
  const saved = !output && !error && !predicting && scan.prediction_status === "PROCESSED";
  return (
    <section className="panel screening-panel" aria-labelledby="screening-heading" aria-busy={predicting}>
      <div className="screening-panel-header">
        <span className="screening-icon"><ScanLine size={23} /></span>
        <div><p className="eyebrow">AI-assisted review</p><h2 id="screening-heading">AI screening</h2></div>
      </div>
      <button className="button button-primary screening-run" disabled={predicting || explaining} onClick={onRun}>
        {predicting ? <LoaderCircle size={18} className="spin" /> : <ScanLine size={18} />}
        {predicting ? "Running AI screening..." : error ? "Retry AI screening" : output || saved ? "Re-run AI screening" : "Run AI Screening"}
      </button>
      {predicting && <div className="screening-progress" role="status"><strong>Screening in progress</strong><p>The model is processing this X-ray. Your result will appear here.</p></div>}
      {error && <div className="mt-5"><ErrorState title="Screening could not complete" message={error} /></div>}
      {metadataWarning && <div className="notice notice-warning mt-5" role="status"><Info size={18} className="shrink-0" /><p>Screening completed. The latest scan status could not be refreshed; your result remains available below.</p></div>}
      {!predicting && output && <div className="screening-output" aria-live="polite">
        <p className="eyebrow">DenseNet121 AI Screening Output</p>
        <h3 className={`screening-result ${output.prediction === "NORMAL" ? "accent" : ""}`}>{output.prediction}</h3>
        <p className="muted text-sm mt-2">{output.prediction === "PNEUMONIA" ? "The model selected the PNEUMONIA class. Review the original X-ray alongside this screening result." : "The model selected the NORMAL class. This screening result does not rule out abnormalities."}</p>
        <div className="screening-score"><span>Selected-class model score</span><strong>{formatModelScore(output.confidence)}</strong></div>
        <p className="score-explanation">Uncalibrated model score. This is not accuracy or the chance that a patient has pneumonia. Near 100% can reflect rounding or numerical saturation; high scores can still be wrong.</p>
        {[
          {label: "Pneumonia model score", value: output.pneumonia_probability, warning: true},
          {label: "Normal model score", value: output.normal_probability, warning: false},
        ].map(({label, value, warning}) => <div key={label} className={`probability-row${warning ? " warning" : ""}`}>
          <div className="metric-row"><span>{label}</span><strong>{formatModelScore(value)}</strong></div>
          <div className="progress-track" role="progressbar" aria-label={label} aria-valuenow={Number((value * 100).toFixed(2))} aria-valuetext={formatModelScore(value)} aria-valuemin={0} aria-valuemax={100}>
            <span style={{width: `${Math.min(100, Math.max(0, value * 100))}%`}} />
          </div>
        </div>)}
        {onExplain && <div className="explanation-action">
          <button type="button" className="button button-secondary w-full" disabled={explaining || explanationReady || !output.model_checkpoint_sha256} onClick={onExplain}>
            {explaining ? <LoaderCircle size={18} className="spin" /> : <Eye size={18} />}
            {explaining ? 'Generating explanation…' : explanationReady ? 'Explanation ready' : 'Explain prediction'}
          </button>
          <p className="field-help">{output.model_checkpoint_sha256 ? 'Optional Grad-CAM view of regions contributing to this class score. The screening result stays unchanged.' : 'Restart the backend and re-run screening to identify the model before requesting an explanation.'}</p>
          {explanationReady && <a href="#radiograph-image" className="text-link mt-3">View explanation on X-ray</a>}
          {explaining && <p role="status" className="muted text-sm mt-3">Generating the heatmap. It will appear over the X-ray.</p>}
          {explanationError && <p role="alert" className="notice notice-warning mt-3">{explanationError}</p>}
        </div>}
        <details className="review-disclosure"><summary>Model & screening details</summary><dl className="detail-grid mt-4">
          <div className="detail-item"><dt>Decision Threshold:</dt><dd>{output.threshold_applied}</dd></div>
          <div className="detail-item"><dt>Compute</dt><dd>{output.device.toUpperCase()}</dd></div>
          <div className="detail-item"><dt>Architecture / epoch</dt><dd>{output.model_architecture} / {output.model_epoch}</dd></div>
          {output.model_checkpoint_sha256 && <div className="detail-item"><dt>Loaded model SHA-256</dt><dd className="model-fingerprint">{output.model_checkpoint_sha256}</dd></div>}
        </dl></details>
      </div>}
      {saved && <div className="screening-output">
        <p className="eyebrow">Saved screening result</p><ResultBadge result={scan.predicted_class} />
        <p className="muted text-sm mt-3">This is the previously stored result. Re-run screening for a fresh score breakdown and the identity of the model used now.</p>
      </div>}
      {!output && !saved && !error && !predicting && <p className="muted text-sm mt-5">Ready to screen this radiograph. Run the model to see its class scores and screening output here.</p>}
      <div className="screening-disclaimer">
        <AlertTriangle size={18} className="shrink-0" />
        <div><strong>Mandatory Clinical Disclaimer</strong><p>{output?.disclaimer || "AI-assisted screening supports clinical review. It does not establish a diagnosis. A qualified clinician must interpret the result with the X-ray and patient history."}</p></div>
      </div>
    </section>
  );
}
