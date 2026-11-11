"use client";

import {
  Sun,
  Moon,
  Monitor,
  ShieldCheck,
  UploadCloud,
  ScanLine,
  LogOut,
  LockKeyhole,
} from "lucide-react";
import { useAuth } from "@/context/auth-context";
import { useTheme } from "@/context/theme";
import { AuthenticatedLayout } from "@/components/layout/authenticated-layout";
import { PageHeader } from "@/components/ui";
import { AccountSettings } from "@/components/account-settings";
import { ActiveModel } from "@/components/active-model";

export default function ProfilePage() {
  const { user, role, logout } = useAuth();
  const { preference, setPreference } = useTheme();
  const institution = role !== "doctor";
  const initials = (user?.full_name || user?.username || "PS")
    .replace(/^Dr\.?\s*/i, "")
    .split(" ")
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
  return (
    <AuthenticatedLayout>
      <div className="page-stack">
        <PageHeader
          eyebrow="Make yourself at home"
          title="Profile & preferences"
          description="Your account, access scope, and a workspace that suits you."
        />
        <div className="profile-columns">
          <section className="panel">
            <div className="profile-cover" />
            <div className="panel-padding">
              <div className="avatar profile-avatar">{initials}</div>
              <div className="flex items-start justify-between gap-3 mt-4">
                <div>
                  <h2>{user?.full_name || user?.username}</h2>
                  <p className="muted text-xs mt-1">@{user?.username}</p>
                </div>
                <span className="badge badge-teal capitalize">
                  {role === "doctor" ? "Clinical staff" : role}
                </span>
              </div>
              <div className="form-divider" />
              <dl className="detail-grid">
                <div className="detail-item">
                  <dt>Account username</dt>
                  <dd>{user?.username}</dd>
                </div>
                <div className="detail-item">
                  <dt>Role</dt>
                  <dd className="capitalize">{role}</dd>
                </div>
                <div className="detail-item">
                  <dt>Record visibility</dt>
                  <dd>
                    {institution ? "Institutional scans" : "Your own uploads"}
                  </dd>
                </div>
                <div className="detail-item">
                  <dt>Account ID</dt>
                  <dd className="font-mono text-xs">{user?.user_id}</dd>
                </div>
              </dl>
              <div className="form-divider" />
              <details className="review-disclosure"><summary>Your access, explained</summary>
              <ul className="checklist">
                <li>
                  <UploadCloud size={17} />
                  <div>
                    <strong>Upload radiographs</strong>Securely add a PNG or
                    JPEG using a pseudonymous patient identifier.
                  </div>
                </li>
                <li>
                  <ShieldCheck size={17} />
                  <div>
                    <strong>
                      {institution
                        ? "Review institutional records"
                        : "Review your own records"}
                    </strong>
                    {institution
                      ? "Browse radiographs uploaded by practitioners across the institution."
                      : "View only radiographs uploaded by your account."}
                  </div>
                </li>
                <li>
                  <ScanLine size={17} />
                  <div>
                    <strong>Run AI screening</strong>
                    {institution
                      ? "Screen any radiograph you are authorized to access."
                      : "Screen your own uploads and review their AI outputs."}
                  </div>
                </li>
              </ul>
              </details>
            </div>
          </section>
          <aside className="space-y-5">
            {user && <AccountSettings key={user.user_id} user={user} />}
            <section className="panel panel-padding">
              <p className="eyebrow">Personalize your workspace</p>
              <h2>Appearance</h2>
              <p className="muted text-xs mt-2 mb-5">
                Choose a theme, or follow your device.
              </p>
              <div className="flex gap-2" role="group" aria-label="Appearance">
                {(
                  [
                    { value: "light", label: "Light", icon: Sun },
                    { value: "dark", label: "Dark", icon: Moon },
                    { value: "system", label: "System", icon: Monitor },
                  ] as const
                ).map(({ value, label, icon: Icon }) => (
                  <button
                    key={value}
                    type="button"
                    aria-pressed={preference === value}
                    className="appearance-option"
                    onClick={() => setPreference(value)}
                  >
                    <Icon size={19} />
                    {label}
                  </button>
                ))}
              </div>
              <p className="field-help mt-4">
                This preference is remembered on this browser.
              </p>
            </section>
            <ActiveModel />
            <section className="panel panel-padding">
              <LockKeyhole size={21} className="accent mb-4" />
              <h2>Your session</h2>
              <p className="muted text-xs mt-2 mb-5">
                Your session stays in this tab. Refreshing the page or closing
                the tab requires a new sign-in.
              </p>
              <button className="button button-danger w-full" onClick={logout}>
                <LogOut size={15} />
                Sign Out of Session
              </button>
            </section>
          </aside>
        </div>
      </div>
    </AuthenticatedLayout>
  );
}
