"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  UploadCloud,
  FolderOpen,
  UserRound,
  LogOut,
  ShieldCheck,
  ArrowUpRight,
} from "lucide-react";
import { useAuth } from "@/context/auth-context";
import { Brand } from "@/components/ui";

export function Sidebar({ onNavClick }: { onNavClick?: () => void }) {
  const pathname = usePathname();
  const { user, role, logout } = useAuth();
  const items = [
    { label: "Overview", href: "/", icon: LayoutDashboard },
    { label: "Patients", href: "/patients", icon: UserRound },
    { label: "Upload radiograph", href: "/upload", icon: UploadCloud },
    {
      label: role === "doctor" ? "My scans" : "Scan repository",
      href: "/scans",
      icon: FolderOpen,
    },
    { label: "Profile & preferences", href: "/profile", icon: UserRound },
  ];
  const initials = (user?.full_name || user?.username || "PS")
    .replace(/^Dr\.?\s*/i, "")
    .split(" ")
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
  return (
    <aside className="app-sidebar" aria-label="Workspace sidebar">
      <div className="sidebar-brand">
        <Brand />
      </div>
      <div className="workspace-label">
        <span />
        {role === "radiologist"
          ? "Radiology workspace"
          : role === "admin"
            ? "Administration workspace"
            : "Staff workspace"}
      </div>
      <nav className="sidebar-nav" aria-label="Main navigation">
        <p className="eyebrow">Workspace</p>
        {items.map(({ label, href, icon: Icon }) => {
          const active =
            href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              onClick={onNavClick}
              aria-current={active ? "page" : undefined}
              className={`nav-link${active ? " active" : ""}`}
            >
              <Icon size={18} strokeWidth={1.7} aria-hidden="true" />
              {label}
              {active && <span className="nav-indicator" />}
            </Link>
          );
        })}
      </nav>
      <div className="sidebar-footnote">
        <strong>
          <ShieldCheck size={15} className="accent" />
          Protected by design
        </strong>
        Radiographs are encrypted in storage and accessible by account
        permissions.
      </div>
      <div className="sidebar-account">
        <div className="flex items-center gap-3 mb-4">
          <span className="avatar">{initials}</span>
          <div className="min-w-0 flex-1">
            <p
              className="account-name"
              title={user?.full_name || user?.username}
            >
              {user?.full_name || user?.username}
            </p>
            <p className="account-role">
              {role === "doctor" ? "Clinical staff" : role}
            </p>
          </div>
          <Link
            href="/profile"
            onClick={onNavClick}
            className="muted"
            aria-label="View your profile"
          >
            <ArrowUpRight size={15} />
          </Link>
        </div>
        <button className="button button-secondary w-full" onClick={logout}>
          <LogOut size={14} />
          Sign Out
        </button>
      </div>
    </aside>
  );
}
