import React from 'react';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import PatientsPage from '@/app/patients/page';
import { RadiographViewer, StoredRadiograph } from '@/components/radiograph-viewer';
import { PatientActions } from '@/components/patient-actions';
import { AccountEditor } from '@/components/account-editor';
import { AccountSettings } from '@/components/account-settings';
import { ActiveModel } from '@/components/active-model';
import { apiClient } from '@/lib/api-client';
import type { ScanMetadata } from '@/lib/types';
import { patientGroups } from '@/lib/patients';

const { push, updateAccount } = vi.hoisted(() => ({push: vi.fn(), updateAccount: vi.fn()}));
vi.mock('next/navigation', () => ({useRouter: () => ({push, replace: vi.fn()}), usePathname: () => '/patients'}));
vi.mock('@/context/auth-context', () => ({useAuth: () => ({token: 'test-token', role: 'doctor',
  isAuthenticated: true, user: {user_id: 'account-a', username: 'doctor_a', role: 'doctor'}, updateAccount})}));

function scan(id: string, date: string, result: string | null): ScanMetadata {
  return {scan_id: id, patient_id: 'PAT-001', created_at: date, prediction_status: result ? 'PROCESSED' : 'PENDING',
    predicted_class: result, prediction_probability: result === 'NORMAL' ? .1 : .9, file_size_bytes: 1000, format_version: 1, uploaded_by: 'doctor_a'};
}
const older = scan('older-scan', '2026-11-01T00:00:00Z', 'PNEUMONIA');
const recent = scan('latest-scan', '2026-11-11T00:00:00Z', 'NORMAL');

beforeEach(() => {
  vi.restoreAllMocks(); push.mockReset(); updateAccount.mockReset();
  URL.createObjectURL = vi.fn().mockReturnValue('blob:protected-image');
  URL.revokeObjectURL = vi.fn();
  HTMLDialogElement.prototype.showModal = function () {this.setAttribute('open', '');};
  HTMLDialogElement.prototype.close = function () {this.removeAttribute('open');};
});

describe('Patient follow-up', () => {
  it('uses the latest uploaded scan as current, even when an older scan was screened', () => {
    const pending = {...recent, predicted_class: null, prediction_status: 'PENDING'};
    expect(patientGroups([older, pending])[0].latest.prediction_status).toBe('PENDING');
    expect(patientGroups([recent, older])[0].history.map((item) => item.scan_id)).toEqual(['latest-scan', 'older-scan']);
  });

  it('shows a normal latest result while preserving a pneumonia result in history', async () => {
    vi.spyOn(apiClient, 'listScans').mockResolvedValue([older, recent]);
    render(<PatientsPage />);
    expect(await screen.findByRole('link', {name: 'Review latest X-ray'})).toHaveAttribute('href', '/scans/latest-scan');
    expect(within(screen.getByRole('group', {name:'Latest AI output for PAT-001'})).getByText('Normal')).toBeInTheDocument();
    fireEvent.click(screen.getByText('X-ray history (2)'));
    expect(screen.getByText('Pneumonia')).toBeInTheDocument();
  });

  it('requires explicit confirmation before deleting a patient', async () => {
    const remove = vi.spyOn(apiClient, 'deletePatient').mockResolvedValue({deleted_scans: 2});
    const deleted = vi.fn();
    render(<PatientActions patientId="PAT-001" token="test-token" onDeleted={deleted} onRenamed={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', {name: 'Delete patient'}));
    expect(remove).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', {name: 'Cancel'}));
    expect(remove).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', {name: 'Delete patient'}));
    fireEvent.click(screen.getByRole('button', {name: 'Confirm patient deletion'}));
    await waitFor(() => expect(deleted).toHaveBeenCalledOnce());
    expect(remove).toHaveBeenCalledWith('PAT-001', 'test-token');
  });

  it('uploads follow-up bytes under the same patient ID and opens the new scan', async () => {
    const upload = vi.spyOn(apiClient, 'uploadScan').mockResolvedValue(recent);
    render(<PatientActions patientId="PAT-001" token="test-token" onDeleted={vi.fn()} onRenamed={vi.fn()} />);
    const file = new File(['new-radiograph'], 'followup.png', {type: 'image/png'});
    fireEvent.change(screen.getByLabelText('Follow-up X-ray for PAT-001'), {target: {files: [file]}});
    await waitFor(() => expect(push).toHaveBeenCalledWith('/scans/latest-scan'));
    expect(upload).toHaveBeenCalledWith(file, 'PAT-001', 'test-token');
  });
});

describe('Protected radiograph viewer', () => {
  it('opens, zooms, resets, and closes the enlarged image', () => {
    render(<RadiographViewer src="blob:protected-image" label="Test radiograph" />);
    fireEvent.click(screen.getByRole('button', {name: 'Enlarge Test radiograph'}));
    const modal = screen.getByRole('dialog');
    expect(modal).toHaveAttribute('open');
    fireEvent.click(screen.getByRole('button', {name: 'Zoom in'}));
    expect(screen.getByAltText('Test radiograph, enlarged').parentElement).toHaveStyle({width: '125%'});
    fireEvent.click(screen.getByRole('button', {name: 'Fit image'}));
    expect(screen.getByAltText('Test radiograph, enlarged').parentElement).toHaveStyle({width: '100%'});
    fireEvent.click(screen.getByRole('button', {name: 'Close enlarged image'}));
    expect(modal).not.toHaveAttribute('open');
    expect(document.body.style.overflow).not.toBe('hidden');
  });

  it('revokes the image URL and aborts requests when leaving the scan', async () => {
    const get = vi.spyOn(apiClient, 'getScanImage').mockResolvedValue(new Blob(['image'], {type:'image/png'}));
    const view = render(<StoredRadiograph scanId="scan-a" patientId="PAT-001" token="test-token" />);
    expect(await screen.findByRole('button', {name: /Enlarge/})).toBeInTheDocument();
    const signal = get.mock.calls[0][2];
    view.unmount();
    expect(signal?.aborted).toBe(true);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:protected-image');
  });

  it('does not show an image that finishes loading after unmount', async () => {
    let resolve!: (value: Blob) => void;
    vi.spyOn(apiClient, 'getScanImage').mockImplementation(() => new Promise((done) => {resolve = done;}));
    const view = render(<StoredRadiograph scanId="scan-a" patientId="PAT-001" token="test-token" />);
    view.unmount();
    await act(async () => resolve(new Blob(['late image'])));
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  });
});

describe('Account editor', () => {
  it('rejects mismatched passwords and clears secrets after a successful save', async () => {
    updateAccount.mockResolvedValue(undefined);
    render(<AccountEditor mode="password" user={{user_id: 'account-a', username: 'doctor_a', role: 'doctor'}} />);
    fireEvent.change(screen.getByLabelText('Current password'), {target:{value:'OriginalPassword123!'}});
    fireEvent.change(screen.getByLabelText('New password'), {target:{value:'NewPassword123!'}});
    fireEvent.change(screen.getByLabelText('Confirm new password'), {target:{value:'DifferentPassword123!'}});
    fireEvent.click(screen.getByRole('button', {name:'Save account changes'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('do not match');
    expect(updateAccount).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('Confirm new password'), {target:{value:'NewPassword123!'}});
    fireEvent.click(screen.getByRole('button', {name:'Save account changes'}));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Account saved'));
    expect(screen.getByLabelText('Current password')).toHaveValue('');
    expect(screen.getByLabelText('New password')).toHaveValue('');
    expect(screen.getByLabelText('Confirm new password')).toHaveValue('');
  });
});

describe('Account settings disclosure', () => {
  const user = {user_id: 'account-a', username: 'doctor_a', full_name: 'Doctor A', role: 'doctor' as const};

  it('opens profile editing on request and discards changes on cancel', () => {
    render(<AccountSettings user={user} />);
    expect(screen.queryByLabelText('Current password')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: /Edit profile/}));
    expect(screen.getByRole('dialog', {name:'Edit profile'})).toHaveAttribute('open');
    expect(screen.queryByLabelText('New password')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Display name'), {target:{value:'Unsaved name'}});
    fireEvent.change(screen.getByLabelText('Current password'), {target:{value:'Secret123!'}});
    fireEvent.click(screen.getByRole('button', {name:'Cancel'}));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(updateAccount).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', {name: /Edit profile/}));
    expect(screen.getByLabelText('Display name')).toHaveValue('Doctor A');
    expect(screen.getByLabelText('Current password')).toHaveValue('');
  });

  it('opens a separate password form and closes it after saving', async () => {
    updateAccount.mockResolvedValue(undefined);
    render(<AccountSettings user={user} />);
    fireEvent.click(screen.getByRole('button', {name: /Change password/}));
    expect(screen.getByRole('dialog', {name:'Change password'})).toBeInTheDocument();
    expect(screen.queryByLabelText('Display name')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Current password'), {target:{value:'OriginalPassword123!'}});
    fireEvent.change(screen.getByLabelText('New password'), {target:{value:'NewPassword123!'}});
    fireEvent.change(screen.getByLabelText('Confirm new password'), {target:{value:'NewPassword123!'}});
    fireEvent.click(screen.getByRole('button', {name:'Save account changes'}));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Account saved'));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Current password')).not.toBeInTheDocument();
    expect(updateAccount).toHaveBeenCalledWith({full_name:'Doctor A', username:'doctor_a', current_password:'OriginalPassword123!', new_password:'NewPassword123!'});
  });

  it('does not leave a model-status request loading forever when metadata is absent', async () => {
    vi.spyOn(apiClient, 'checkReadiness').mockResolvedValue({status:'ready'});
    render(<ActiveModel />);
    fireEvent.click(screen.getByText('Active model'));
    expect(await screen.findByRole('status')).toHaveTextContent('did not provide model details');
  });
});

it('hides a previous patient image immediately when the scan changes', async () => {
  vi.spyOn(apiClient, 'getScanImage').mockResolvedValueOnce(new Blob(['first'], {type:'image/png'}))
    .mockImplementationOnce(() => new Promise(() => {}));
  const view = render(<StoredRadiograph scanId="scan-a" patientId="PAT-001" token="test-token" />);
  await screen.findByRole('button', {name:/Enlarge/});
  view.rerender(<StoredRadiograph scanId="scan-b" patientId="PAT-002" token="test-token" />);
  expect(screen.queryByRole('img')).not.toBeInTheDocument();
  expect(screen.getByRole('status')).toHaveTextContent('Loading protected image');
  expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:protected-image');
});
