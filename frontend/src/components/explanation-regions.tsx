"use client";

import type { ExplanationResult } from "@/lib/types";

/** SVG uses the same source geometry and contain/meet alignment as the images. */
export function RegionMarkers({ explanation, selected }: { explanation: ExplanationResult; selected: number | null }) {
  if (explanation.summary_basis !== 'gradcam_spatial_v1' || explanation.coordinate_system !== 'displayed_image') return null;
  const {width, height} = explanation;
  const radius = Math.min(width, height) * .045;
  return <svg className="region-marker-overlay" viewBox={`0 0 ${width} ${height}`}
    preserveAspectRatio="xMidYMid meet" aria-hidden="true" focusable="false">
    {(explanation.regions || []).map((region) => {
      const active = selected === region.id;
      const [left, top, right, bottom] = region.bounds;
      const x = region.marker[0] * width, y = region.marker[1] * height;
      // Keep each number inside its own coarse section so adjacent sections'
      // labels cannot overlap. The leader retains the actual contribution point.
      const labelX = Math.max(left * width + radius * 1.3, Math.min(right * width - radius * 1.3, x));
      const labelY = Math.max(top * height + radius * 1.3, Math.min(bottom * height - radius * 1.3, y));
      return <g key={region.id} data-region={region.id} data-selected={active ? 'true' : 'false'}>
        {active && <rect x={left * width} y={top * height} width={(right - left) * width} height={(bottom - top) * height}
          className="region-section-outline" vectorEffect="non-scaling-stroke" />}
        <line x1={x} y1={y} x2={labelX} y2={labelY} className="region-leader" vectorEffect="non-scaling-stroke" />
        <circle cx={x} cy={y} r={radius * .17} className="region-point" />
        <circle cx={labelX} cy={labelY} r={radius} className={`region-number-disc${active ? ' selected' : ''}`} vectorEffect="non-scaling-stroke" />
        <text x={labelX} y={labelY} textAnchor="middle" dominantBaseline="central" fontSize={radius * 1.15} className="region-number">{region.id}</text>
      </g>;
    })}
  </svg>;
}

export function RegionNarrative({ explanation, selected, onSelect }: {
  explanation: ExplanationResult; selected: number | null; onSelect: (id: number) => void;
}) {
  if (!explanation.summary || explanation.summary_basis !== 'gradcam_spatial_v1' || explanation.coordinate_system !== 'displayed_image') return null;
  const informative = explanation.status === 'available';
  const interpretation = !informative
    ? 'This explanation has no useful spatial pattern to show. The screening result is unchanged.'
    : explanation.target_class === 'PNEUMONIA'
      ? 'The highlighted areas contributed to the PNEUMONIA score. They do not confirm pneumonia in those areas.'
      : 'The highlighted areas contributed to the NORMAL score. They do not establish that the image is free of abnormalities.';
  return <section className="region-narrative" aria-label="Image contribution explanation">
    <p className="eyebrow">Image + explanation</p>
    <h3>What contributed to this result?</h3>
    <p className="region-interpretation">{interpretation}</p>
    {informative && explanation.distribution === 'broad' && <p className="region-distribution">Broad contribution pattern · contributions are spread across the displayed image</p>}
    <p className="region-summary">{explanation.summary}</p>
    {informative && !!explanation.regions?.length && <>
      <p className="field-help">Select a numbered note to highlight its image section.</p>
      <ol className="region-note-list">
        {explanation.regions.map((region) => <li key={region.id}>
          <button type="button" className="region-note" aria-pressed={selected === region.id}
            aria-label={`Highlight region ${region.id}: ${region.location}`} onClick={() => onSelect(region.id)}>
            <span className="region-note-number" aria-hidden="true">{region.id}</span>
            <span><strong>{region.title}</strong><span>{region.description}</span></span>
          </button>
        </li>)}
      </ol>
    </>}
    <details className="review-disclosure region-reading-guide">
      <summary>How to read this explanation</summary>
      <p>{informative
        ? 'Compare the Original view with the Heatmap; use the opacity slider and enlarged view to inspect the same image. Warmer colors show relatively higher contributions to this class score, not greater disease severity.'
        : 'Use the enlarged original X-ray for review. No heatmap or numbered regions are available for this explanation.'}</p>
      <p>Positions refer to the displayed image, not the patient&apos;s left or right. Numbers and the dashed outline are coarse image-section guides, not separate lesions or disease boundaries.</p>
      <p>This model does not name medical findings or explain a clinical diagnosis. Review the original X-ray and patient information with a qualified clinician. A high model score does not make the explanation more reliable.</p>
    </details>
  </section>;
}
