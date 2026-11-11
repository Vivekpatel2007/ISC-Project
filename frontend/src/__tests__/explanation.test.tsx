import React from 'react';
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ScanDetailPage from '@/app/scans/[id]/page';
import { RadiographViewer, StoredRadiograph } from '@/components/radiograph-viewer';
import { apiClient } from '@/lib/api-client';
import { ApiError, type ExplanationResult, type PredictionResult, type ScanMetadata } from '@/lib/types';

vi.mock('next/navigation', () => ({useRouter: () => ({push: vi.fn(), replace: vi.fn()}), usePathname: () => '/scans/scan-123-abc'}));
vi.mock('@/context/auth-context', () => ({useAuth: () => ({token:'test-token', role:'doctor', isAuthenticated:true,
  user:{user_id:'doctor-a', username:'doctor_a', role:'doctor'}})}));

const scan: ScanMetadata = {scan_id:'scan-123-abc', patient_id:'PAT-001', file_size_bytes:1000, created_at:'2026-11-11T00:00:00Z',
  format_version:1, prediction_status:'PENDING', predicted_class:null, prediction_probability:null, uploaded_by:'doctor_a'};
const prediction: PredictionResult = {scan_id:scan.scan_id, patient_id:scan.patient_id, prediction:'PNEUMONIA', confidence:.9,
  pneumonia_probability:.9, normal_probability:.1, threshold_applied:.4, model_architecture:'densenet121', model_epoch:5,
  model_checkpoint_sha256:'a'.repeat(64), device:'cpu', disclaimer:'Clinical review is required.'};
const explanation: ExplanationResult = {scan_id:scan.scan_id, method:'Grad-CAM', target_class:'PNEUMONIA', target_layer:'features.denseblock4',
  target_score:'raw_class_logit', target_logit:2., pneumonia_probability:.9, model_checkpoint_sha256:'a'.repeat(64), image_sha256:'b'.repeat(64),
  device:'cpu', precision:'float32', preprocessing:'stretch', status:'available', heatmap_png_base64:'fixture', width:100, height:100,
  content_box:[0,0,224,224], limitation:'Relative model contribution, not a confirmed disease location.'};

const regionalExplanation: ExplanationResult = {...explanation, summary_basis:'gradcam_spatial_v1', coordinate_system:'displayed_image',
  distribution:'concentrated', summary:'Stronger positive contributions appear in the upper-left and lower-right displayed-image sections.',
  regions:[
    {id:1, location:'upper-left', title:'Upper-left image section', description:'The strongest compared section for the PNEUMONIA score.', bounds:[0,0,.33,.33], marker:[.1,.1]},
    {id:2, location:'lower-right', title:'Lower-right image section', description:'Another strong contribution to the PNEUMONIA score.', bounds:[.66,.66,1,1], marker:[.9,.9]},
  ]};

beforeEach(() => {
  vi.restoreAllMocks();
  URL.createObjectURL = vi.fn().mockReturnValue('blob:original');
  URL.revokeObjectURL = vi.fn();
  HTMLDialogElement.prototype.showModal = function () {this.setAttribute('open','');};
  HTMLDialogElement.prototype.close = function () {this.removeAttribute('open');};
  vi.spyOn(apiClient, 'getScan').mockResolvedValue(scan);
  vi.spyOn(apiClient, 'getScanImage').mockResolvedValue(new Blob(['original'], {type:'image/png'}));
  vi.spyOn(apiClient, 'predictScan').mockResolvedValue(prediction);
});

async function screenScan() {
  render(<ScanDetailPage params={{id:scan.scan_id}} />);
  expect(screen.queryByRole('button', {name:'Explain prediction'})).not.toBeInTheDocument();
  fireEvent.click(await screen.findByRole('button', {name:/Run AI Screening/i}));
  return screen.findByRole('button', {name:'Explain prediction'});
}

describe('Optional explanation workflow', () => {
  it('requests only on click, binds the model/class, and clears the map on a new screening', async () => {
    const explain = vi.spyOn(apiClient, 'explainScan').mockResolvedValue(explanation);
    const button = await screenScan();
    expect(explain).not.toHaveBeenCalled();
    fireEvent.click(button);
    await screen.findByRole('button', {name:'Explanation ready'});
    expect(explain).toHaveBeenCalledWith(scan.scan_id, 'PNEUMONIA', 'a'.repeat(64), 'test-token', expect.any(AbortSignal));
    expect(screen.getByRole('button', {name:'Heatmap'})).toHaveAttribute('aria-pressed','true');
    fireEvent.click(screen.getByRole('button', {name:/Re-run AI screening/i}));
    await screen.findByRole('button', {name:'Explain prediction'});
    expect(screen.queryByRole('button', {name:'Heatmap'})).not.toBeInTheDocument();
  });

  it('keeps the screening result when explanation fails and allows a retry', async () => {
    vi.spyOn(apiClient, 'explainScan').mockRejectedValueOnce(new ApiError(503,'Explanation unavailable')).mockResolvedValueOnce(explanation);
    fireEvent.click(await screenScan());
    expect(await screen.findByRole('alert')).toHaveTextContent('Explanation unavailable');
    expect(screen.getByRole('heading', {name:'PNEUMONIA'})).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name:'Explain prediction'}));
    await screen.findByRole('button', {name:'Explanation ready'});
  });

  it('rejects an explanation for a different checkpoint', async () => {
    vi.spyOn(apiClient, 'explainScan').mockResolvedValue({...explanation, model_checkpoint_sha256:'c'.repeat(64)});
    fireEvent.click(await screenScan());
    expect(await screen.findByRole('alert')).toHaveTextContent('identity did not match');
    expect(screen.queryByRole('button', {name:'Heatmap'})).not.toBeInTheDocument();
  });

  it('prevents duplicate requests and aborts pending requests when leaving', async () => {
    let finish!: (result: ExplanationResult) => void;
    const explain = vi.spyOn(apiClient, 'explainScan').mockImplementation(() => new Promise((resolve) => {finish=resolve;}));
    const view = render(<ScanDetailPage params={{id:scan.scan_id}} />);
    fireEvent.click(await screen.findByRole('button', {name:/Run AI Screening/i}));
    const button = await screen.findByRole('button', {name:'Explain prediction'});
    fireEvent.click(button); fireEvent.click(button);
    expect(explain).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', {name:/Re-run AI screening/i})).toBeDisabled();
    const signal = explain.mock.calls[0][4];
    view.unmount();
    expect(signal?.aborted).toBe(true);
    await act(async () => finish(explanation));
    expect(screen.queryByText('Grad-CAM for PNEUMONIA')).not.toBeInTheDocument();
  });
});

describe('Explanation image controls', () => {
  it('toggles the original, adjusts opacity, and zooms image/overlay together', () => {
    render(<RadiographViewer src="blob:original" label="X-ray" explanation={explanation} />);
    const overlay = document.querySelector('.heatmap-overlay');
    expect(overlay).toHaveStyle({opacity:'0.45'});
    fireEvent.change(screen.getByRole('slider', {name:'Heatmap opacity'}), {target:{value:'70'}});
    expect(overlay).toHaveStyle({opacity:'0.7'});
    fireEvent.click(screen.getByRole('button', {name:'Original'}));
    expect(document.querySelector('.heatmap-overlay')).toBeNull();
    fireEvent.click(screen.getByRole('button', {name:'Heatmap'}));
    fireEvent.click(screen.getByRole('button', {name:'Enlarge X-ray'}));
    const modal = screen.getByRole('dialog');
    fireEvent.click(within(modal).getByRole('button', {name:'Zoom in'}));
    const image = within(modal).getByAltText('X-ray, enlarged');
    expect(image.parentElement).toHaveStyle({width:'125%',height:'125%'});
    expect(image.parentElement?.querySelector('.heatmap-overlay')).toHaveStyle({opacity:'0.7'});
  });

  it('reports a non-informative map without displaying fake highlights', async () => {
    render(<StoredRadiograph scanId={scan.scan_id} patientId={scan.patient_id} token="test-token" explanation={{...explanation,status:'no_spatial_signal'}} />);
    expect(await screen.findByText(/No spatially informative/)).toBeInTheDocument();
    await screen.findByRole('button', {name:/Enlarge/});
    expect(screen.queryByRole('button', {name:'Heatmap'})).not.toBeInTheDocument();
    expect(document.querySelector('.heatmap-overlay')).toBeNull();
  });

  it('links numbered notes to image sections and restores the overlay when a note is selected', () => {
    render(<RadiographViewer src="blob:original" label="X-ray" explanation={regionalExplanation} />);
    const narrative = screen.getByRole('region', {name:'Image contribution explanation'});
    expect(narrative).toHaveTextContent('upper-left and lower-right');
    expect(narrative).toHaveTextContent("not the patient's left or right");
    const first = screen.getByRole('button', {name:'Highlight region 1: upper-left'});
    const second = screen.getByRole('button', {name:'Highlight region 2: lower-right'});
    expect(first).toHaveAttribute('aria-pressed','true');
    fireEvent.click(second);
    expect(second).toHaveAttribute('aria-pressed','true');
    const svg = document.querySelector('.region-marker-overlay');
    expect(svg).toHaveAttribute('viewBox','0 0 100 100');
    expect(svg).toHaveAttribute('preserveAspectRatio','xMidYMid meet');
    expect(svg?.querySelector('[data-region="2"]')).toHaveAttribute('data-selected','true');
    expect(svg?.querySelector('rect')).toHaveAttribute('x','66');
    fireEvent.click(screen.getByRole('button', {name:'Original'}));
    expect(document.querySelector('.region-marker-overlay')).toBeNull();
    fireEvent.click(second);
    expect(screen.getByRole('button', {name:'Heatmap'})).toHaveAttribute('aria-pressed','true');
    expect(document.querySelector('.region-marker-overlay')).not.toBeNull();
  });

  it('keeps numbered sections and their notes available inside the enlarged viewer', () => {
    render(<RadiographViewer src="blob:original" label="X-ray" explanation={regionalExplanation} />);
    fireEvent.click(screen.getByRole('button', {name:'Enlarge X-ray'}));
    const modal = screen.getByRole('dialog');
    fireEvent.click(within(modal).getByRole('button', {name:'Highlight region 2: lower-right'}));
    fireEvent.click(within(modal).getByRole('button', {name:'Zoom in'}));
    const image = within(modal).getByAltText('X-ray, enlarged');
    expect(image.parentElement).toHaveStyle({width:'125%'});
    const svg = image.parentElement?.querySelector('.region-marker-overlay');
    expect(svg?.querySelector('[data-region="2"]')).toHaveAttribute('data-selected','true');
    expect(within(modal).getByRole('region', {name:'Image contribution explanation'})).toHaveTextContent('strong contribution');
  });

  it('separates number labels when neighboring sections have adjacent contribution points', () => {
    const adjacent: ExplanationResult = {...regionalExplanation, regions:[
      {...regionalExplanation.regions![0], bounds:[0,.33,.33,.66], marker:[.2,.65]},
      {...regionalExplanation.regions![1], bounds:[0,.66,.33,1], marker:[.2,.67]},
    ]};
    render(<RadiographViewer src="blob:original" label="X-ray" explanation={adjacent} />);
    const numbers = document.querySelectorAll('.region-number-disc');
    const firstY = Number(numbers[0].getAttribute('cy')), secondY = Number(numbers[1].getAttribute('cy'));
    const radius = Number(numbers[0].getAttribute('r'));
    expect(secondY - firstY).toBeGreaterThan(2 * radius);
    // Leaders still originate at the actual high-contribution coordinates.
    expect(document.querySelectorAll('.region-leader')[0]).toHaveAttribute('y1','65');
    expect(document.querySelectorAll('.region-leader')[1]).toHaveAttribute('y1','67');
  });

  it('shows the region summary only when it is bound to the supported summary method', () => {
    const view = render(<RadiographViewer src="blob:original" label="X-ray" explanation={{...regionalExplanation, summary_basis:null}} />);
    expect(screen.queryByRole('region', {name:'Image contribution explanation'})).not.toBeInTheDocument();
    view.rerender(<RadiographViewer src="blob:original" label="X-ray" explanation={{...regionalExplanation,status:'no_spatial_signal',regions:[],distribution:'none',summary:'No spatially informative contribution pattern was found.'}} />);
    expect(screen.getByRole('region', {name:'Image contribution explanation'})).toHaveTextContent('No spatially informative');
    expect(document.querySelector('.region-marker-overlay')).toBeNull();
    expect(screen.queryByRole('button', {name:/Highlight region/})).not.toBeInTheDocument();
  });
});
