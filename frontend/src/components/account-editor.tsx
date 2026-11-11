"use client";

import { useRef, useState } from "react";
import { Save, Eye, EyeOff } from "lucide-react";
import { useAuth } from "@/context/auth-context";
import type { UserProfile } from "@/lib/types";

export function AccountEditor({ user }: { user: UserProfile }) {
  const { updateAccount } = useAuth();
  const [name, setName] = useState(user.full_name || user.username);
  const [username, setUsername] = useState(user.username);
  const [password, setPassword] = useState("");
  const [nextPassword, setNextPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [visible, setVisible] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const busy = useRef(false);
  return <section className="panel panel-padding">
    <p className="eyebrow">Account settings</p><h2>Edit your profile</h2>
    <p className="muted text-sm mt-2 mb-5">Update your display name, sign-in username, or password. Your account ID and role stay assigned by the system.</p>
    <form className="space-y-4" autoComplete="off" onSubmit={async (event) => {
      event.preventDefault();
      if (busy.current) return;
      setError(null); setSaved(false);
      if (nextPassword !== confirm) { setError('New passwords do not match.'); return; }
      if (nextPassword && new TextEncoder().encode(nextPassword).length > 72) { setError('Password must be at most 72 UTF-8 bytes.'); return; }
      busy.current = true; setSaving(true);
      try {
        await updateAccount({ full_name: name.trim(), username: username.trim(), current_password: password,
          ...(nextPassword ? {new_password: nextPassword} : {}) });
        setSaved(true);
      } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not save account.'); }
      finally { setPassword(''); setNextPassword(''); setConfirm(''); setVisible(false); busy.current = false; setSaving(false); }
    }}>
      <div className="field"><label htmlFor="profile-name">Display name</label><input id="profile-name" className="input" value={name} onChange={(e) => setName(e.target.value)} required maxLength={120} disabled={saving} /></div>
      <div className="field"><label htmlFor="profile-username">Sign-in username</label><input id="profile-username" className="input" value={username} onChange={(e) => setUsername(e.target.value)} required minLength={3} maxLength={32} pattern="[a-zA-Z0-9_.\-]{3,32}" autoCapitalize="none" spellCheck={false} disabled={saving} /><p className="field-help">Letters, numbers, dots, underscores, and hyphens. Scan ownership follows your account when renamed.</p></div>
      <div className="field"><label htmlFor="profile-current-password">Current password</label><div className="password-field"><input id="profile-current-password" className="input" type={visible ? 'text' : 'password'} value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="off" disabled={saving} /><button type="button" className="password-toggle" aria-label={visible ? 'Hide current password' : 'Show current password'} onClick={() => setVisible((v) => !v)}>{visible ? <EyeOff size={18} /> : <Eye size={18} />}</button></div></div>
      <div className="detail-grid">
        <div className="field"><label htmlFor="profile-new-password">New password (optional)</label><input id="profile-new-password" className="input" type="password" value={nextPassword} onChange={(e) => setNextPassword(e.target.value)} minLength={8} maxLength={72} autoComplete="new-password" disabled={saving} /></div>
        <div className="field"><label htmlFor="profile-confirm-password">Confirm new password</label><input id="profile-confirm-password" className="input" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required={!!nextPassword} autoComplete="new-password" disabled={saving} /></div>
      </div>
      <p className="field-help">Leave the new password empty to keep it. Saving invalidates your other signed-in sessions.</p>
      {error && <div className="notice notice-warning" role="alert">{error}</div>}
      {saved && <div className="notice notice-info" role="status">Account saved. Use your updated details the next time you sign in.</div>}
      <button type="submit" className="button button-primary" disabled={saving}><Save size={17} />{saving ? 'Saving…' : 'Save account changes'}</button>
    </form>
  </section>;
}
