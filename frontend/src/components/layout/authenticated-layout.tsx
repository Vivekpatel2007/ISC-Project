"use client";

import { useEffect, useRef, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Menu, X, ChevronRight, Search, Info } from "lucide-react";
import { useAuth } from "@/context/auth-context";
import { Sidebar } from "./sidebar";
import { getLoginPath } from "@/lib/login-portal";
import { ThemeToggle } from "@/components/theme-toggle";
import { LoadingState } from "@/components/ui";

export function AuthenticatedLayout({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading, user } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const drawer = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (!isLoading && !isAuthenticated) router.replace(getLoginPath());
  }, [isLoading, isAuthenticated, router]);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const desktop = window.matchMedia("(min-width: 768px)");
    const closeOnDesktop = () => {
      if (desktop.matches) drawer.current?.close();
    };
    desktop.addEventListener("change", closeOnDesktop);
    return () => desktop.removeEventListener("change", closeOnDesktop);
  }, []);
  const closeDrawer = () => drawer.current?.close();
  const section = pathname.startsWith("/scans/")
    ? "Scan details"
    : pathname === "/scans"
      ? "Scan repository"
      : pathname === "/upload"
        ? "Upload radiograph"
        : pathname === "/profile"
          ? "Profile & preferences"
          : pathname === "/patients" ? "Patients" : "Overview";
  if (isLoading) return <LoadingState label="Verifying your session..." />;
  if (!isAuthenticated)
    return (
      <div className="empty-state min-h-screen">
        <h1>Session Required</h1>
        <p>Sign in with your practitioner account to continue.</p>
        <button
          className="button button-primary"
          onClick={() => router.replace(getLoginPath())}
        >
          Go to Login
        </button>
      </div>
    );
  return (
    <div className="app-shell">
      <a className="skip-link" href="#workspace-content">
        Skip to content
      </a>
      <div className="desktop-sidebar">
        <Sidebar />
      </div>
      <dialog
        ref={drawer}
        className="drawer"
        aria-label="Navigation menu"
        onClick={(event) => {
          if (event.target === event.currentTarget) closeDrawer();
        }}
      >
        <button
          type="button"
          className="icon-button drawer-close"
          aria-label="Close navigation menu"
          onClick={closeDrawer}
        >
          <X size={18} />
        </button>
        <Sidebar onNavClick={closeDrawer} />
      </dialog>
      <div className="workspace-main">
        <header className="topbar">
          <div className="flex items-center gap-3">
            <button
              className="icon-button mobile-menu-button"
              type="button"
              aria-label="Open navigation menu"
              aria-haspopup="dialog"
              onClick={() => drawer.current?.showModal()}
            >
              <Menu size={18} />
            </button>
            <div className="breadcrumb">
              <span>Workspace</span>
              <ChevronRight size={12} />
              <strong>{section}</strong>
            </div>
          </div>
          <div className="topbar-actions">
            <Link href="/scans" className="topbar-search">
              <Search size={15} />
              Search scans
            </Link>
            <ThemeToggle />
            <Link href="/profile" className="avatar" aria-label="Your profile">
              {(user?.username || "P").slice(0, 2).toUpperCase()}
            </Link>
          </div>
        </header>
        <main
          id="workspace-content"
          tabIndex={-1}
          className="workspace-content"
        >
          {children}
        </main>
        <footer className="prototype-note">
          <Info size={14} className="shrink-0" />
          <p>
            <strong>Educational prototype.</strong> AI screening supports
            clinical review. A qualified clinician must interpret every result.
          </p>
        </footer>
      </div>
    </div>
  );
}
