"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowRight, KeyRound, Pencil, X } from "lucide-react";
import { AccountEditor } from "@/components/account-editor";
import type { UserProfile } from "@/lib/types";

export function AccountSettings({ user }: { user: UserProfile }) {
  const [mode, setMode] = useState<'profile' | 'password' | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (!mode) return;
    const modal = dialog.current;
    modal?.showModal();
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {modal?.close(); document.body.style.overflow = previous;};
  }, [mode]);
  return <section className="panel panel-padding" aria-labelledby="account-settings-heading">
    <p className="eyebrow">Your account</p><h2 id="account-settings-heading">Account settings</h2>
    <p className="muted text-sm mt-2 mb-5">Choose what you would like to update.</p>
    <div className="account-options">
      <button type="button" onClick={() => {setSaved(false); setMode('profile');}}><Pencil size={20} /><span><strong>Edit profile</strong><small>Display name and sign-in username</small></span><ArrowRight size={17} /></button>
      <button type="button" onClick={() => {setSaved(false); setMode('password');}}><KeyRound size={20} /><span><strong>Change password</strong><small>Confirm your current password first</small></span><ArrowRight size={17} /></button>
    </div>
    {saved && <p className="notice notice-info mt-4" role="status">Account saved. Use your updated details the next time you sign in.</p>}
    <dialog ref={dialog} className="account-dialog" aria-labelledby="account-dialog-heading"
      onCancel={(event) => {if (saving) event.preventDefault(); else setMode(null);}}
      onClose={() => {if (!saving) setMode(null);}}
      onClick={(event) => {if (!saving && event.target === event.currentTarget) setMode(null);}}>
      {mode && <div className="account-dialog-content">
        <div className="account-dialog-header"><div><p className="eyebrow">Account settings</p><h2 id="account-dialog-heading">{mode === 'profile' ? 'Edit profile' : 'Change password'}</h2></div>
          <button type="button" className="icon-button" aria-label="Close account editor" disabled={saving} onClick={() => setMode(null)}><X size={20} /></button>
        </div>
        <AccountEditor key={mode} user={user} mode={mode} onCancel={() => setMode(null)} onSavingChange={setSaving}
          onSaved={() => {setSaved(true); setMode(null);}} />
      </div>}
    </dialog>
  </section>;
}
