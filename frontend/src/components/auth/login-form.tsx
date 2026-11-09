"use client";

import React, { useState, useRef, useEffect } from "react";
import Link from "next/link";
import {
  Activity,
  Lock,
  User,
  Eye,
  EyeOff,
  AlertCircle,
  ShieldCheck,
  Stethoscope,
  ArrowRight,
  Check,
} from "lucide-react";
import { useAuth } from "@/context/auth-context";
import { ApiError } from "@/lib/types";
import { Brand } from "@/components/ui";
import { ThemeToggle } from "@/components/theme-toggle";
import {
  getLoginPath,
  rememberLoginPortal,
  type LoginPortal,
} from "@/lib/login-portal";

export function LoginForm({ portal }: { portal: LoginPortal }) {
  const { login } = useAuth();
  const isRadiologist = portal === "radiologist";
  const formRef = useRef<HTMLFormElement>(null);

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const submitting = useRef(false);
  const pendingLogin = useRef<AbortController | null>(null);

  useEffect(() => {
    rememberLoginPortal(portal);
    const clearCredentials = () => {
      pendingLogin.current?.abort();
      pendingLogin.current = null;
      formRef.current?.reset();
      setUsername("");
      setPassword("");
      setShowPassword(false);
      setErrorMessage(null);
      setIsLoading(false);
      submitting.current = false;
    };
    // Clear both retained Next.js routes and native back/forward page restores.
    window.addEventListener("pagehide", clearCredentials);
    window.addEventListener("pageshow", clearCredentials);
    return () => {
      clearCredentials();
      window.removeEventListener("pagehide", clearCredentials);
      window.removeEventListener("pageshow", clearCredentials);
    };
  }, [portal]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (submitting.current) return;
    setErrorMessage(null);

    // Validation
    const cleanUsername = username.trim();
    if (!cleanUsername) {
      setErrorMessage(
        `Please enter your ${isRadiologist ? "radiologist" : "staff"} username.`,
      );
      return;
    }
    if (!password) {
      setErrorMessage("Please enter your account password.");
      return;
    }

    submitting.current = true;
    const controller = new AbortController();
    pendingLogin.current = controller;
    setIsLoading(true);
    setShowPassword(false);
    try {
      await login(cleanUsername, password, portal, controller.signal);
      if (controller.signal.aborted || pendingLogin.current !== controller)
        return;
      // Next.js can retain this route's state after navigation.
      setUsername("");
      setPassword("");
    } catch (err: unknown) {
      if (controller.signal.aborted || pendingLogin.current !== controller)
        return;
      setPassword("");
      if (err instanceof ApiError) {
        setErrorMessage(err.detail);
      } else if (err instanceof Error) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage("Authentication failed. Please verify credentials.");
      }
    } finally {
      if (pendingLogin.current === controller) {
        pendingLogin.current = null;
        submitting.current = false;
        setIsLoading(false);
      }
    }
  };

  return (
    <main className="login-shell">
      <section className="login-story" aria-label="About PulmoScan">
        <Brand />
        <svg
          viewBox="0 0 260 300"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.1"
          className="lung-illustration"
          aria-hidden="true"
        >
          <path d="M124 22v96m12-96v96M124 103c-22-18-31-58-48-45S16 142 23 219s85 53 91 18 10-106 10-134Zm12 0c22-18 31-58 48-45s60 84 53 161-85 53-91 18-10-106-10-134Z" />
          <path d="M124 110 74 159l-30 18m80-51-48 58-31 23m79-59-34 71-37 21m71-70-17 66M136 110l50 49 30 18m-80-51 48 58 31 23m-79-59 34 71 37 21m-71-70 17 66M75 82l-9 46m29-28-9 41m-36 52 29 7m-14 38 32-4m87-152 9 46m-29-28 9 41m36 52-29 7m14 38-32-4" />
          <path
            d="M9 45h28M9 45v28m242-28h-28m28 0v28M9 279h28m-28 0v-28m242 28h-28m28 0v-28"
            strokeWidth="2"
          />
        </svg>
        <div className="story-copy">
          <p className="eyebrow">A clearer perspective</p>
          <h2>
            Thoughtful technology.
            <br />
            <em>Confident clinical review.</em>
          </h2>
          <p>
            A focused workspace for chest radiograph screening, built around the
            people who care for patients.
          </p>
        </div>
        <div className="story-steps">
          <span>
            <b>01</b>Upload securely
          </span>
          <span>
            <b>02</b>Screen with AI
          </span>
          <span>
            <b>03</b>Review with care
          </span>
        </div>
        <p className="story-footer">
          <ShieldCheck size={14} />
          Encrypted radiograph storage. Account-based access.
        </p>
      </section>
      <section className="login-main" aria-label="Sign in">
        <div className="login-tools">
          <div className="login-mobile-brand">
            <Brand />
          </div>
          <p>
            <span className="status-dot accent" />
            Practitioner workspace
          </p>
          <ThemeToggle />
        </div>
        <div className="login-card">
          <p className="eyebrow">Welcome to PulmoScan</p>
          <h1>{isRadiologist ? "Radiologist Login" : "Staff Login"}</h1>
          <p className="page-description">
            {isRadiologist
              ? "Your institutional review workspace. Sign in to explore radiographs and run AI screening."
              : "Your clinical day, organized. Sign in to upload radiographs and follow your screening results."}
          </p>
          <nav aria-label="Login portal" className="portal-switch">
            {(
              [
                { portal: "staff", label: "Staff", icon: Stethoscope },
                { portal: "radiologist", label: "Radiologist", icon: Activity },
              ] as const
            ).map((item) => (
              <Link
                key={item.portal}
                href={getLoginPath(item.portal)}
                aria-current={portal === item.portal ? "page" : undefined}
              >
                <item.icon size={15} aria-hidden="true" />
                {item.label}
                {portal === item.portal && (
                  <Check size={13} aria-hidden="true" />
                )}
              </Link>
            ))}
          </nav>
          {errorMessage && (
            <div
              role="alert"
              id="login-error"
              className="notice notice-error mb-5"
            >
              <AlertCircle size={17} className="shrink-0" />
              <p>{errorMessage}</p>
            </div>
          )}
          <form
            ref={formRef}
            autoComplete="off"
            onSubmit={handleSubmit}
            aria-busy={isLoading}
            aria-describedby={errorMessage ? "login-error" : undefined}
            className="space-y-5"
          >
            <div>
              <label htmlFor="username" className="field-label">
                {isRadiologist ? "Radiologist Username" : "Staff Username"}
              </label>
              <div className="field-icon">
                <User size={16} />
                <input
                  id="username"
                  name={`${portal}-username`}
                  className="input"
                  type="text"
                  autoComplete="off"
                  autoCapitalize="none"
                  spellCheck={false}
                  disabled={isLoading}
                  required
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  placeholder={
                    isRadiologist
                      ? "Enter your radiologist username"
                      : "Enter your staff username"
                  }
                />
              </div>
            </div>
            <div>
              <label htmlFor="password" className="field-label">
                Password
              </label>
              <div className="field-icon password-field">
                <Lock size={16} />
                <input
                  id="password"
                  name={`${portal}-password`}
                  className="input"
                  type={showPassword ? "text" : "password"}
                  autoComplete="off"
                  disabled={isLoading}
                  required
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="Enter your password"
                />
                <button
                  type="button"
                  className="icon-button"
                  disabled={isLoading}
                  onClick={() => setShowPassword(!showPassword)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  aria-pressed={showPassword}
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>
            <button
              type="submit"
              disabled={isLoading}
              className="button button-primary w-full mt-2"
            >
              {isLoading ? (
                <>
                  <Activity size={16} className="spin" />
                  Authenticating...
                </>
              ) : (
                <>
                  Sign In to System
                  <ArrowRight size={16} />
                </>
              )}
            </button>
          </form>
          <div className="login-security">
            <ShieldCheck size={18} className="accent shrink-0 mt-1" />
            <p>
              Only your login portal and appearance preference are remembered.
              Refreshing or reopening the app requires a new sign-in.
            </p>
          </div>
        </div>
        <footer className="login-footer">
          <span>PulmoScan / Clinical decision support</span>
          <span>Educational prototype</span>
        </footer>
      </section>
    </main>
  );
}
