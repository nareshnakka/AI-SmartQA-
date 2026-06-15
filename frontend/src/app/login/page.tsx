"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { Loader2, Shield, LogIn } from "lucide-react";
import { apiFetch, BACKEND_URL } from "@/lib/api";
import { setSession } from "@/lib/auth";
import { getStoredProjectId, landingPath, setStoredProjectId } from "@/lib/active-project";

async function resolveLandingPath(): Promise<string> {
  let pid = getStoredProjectId();
  if (!pid) {
    try {
      const list = await apiFetch<{ id: string }[]>("/api/v1/projects");
      pid = list[0]?.id ?? null;
      if (pid) setStoredProjectId(pid);
    } catch {
      /* fall through to default landing */
    }
  }
  return landingPath(pid);
}

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("admin@qeos.local");
  const [password, setPassword] = useState("admin");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [ssoConfigured, setSsoConfigured] = useState(false);
  const [authEnabled, setAuthEnabled] = useState(false);

  useEffect(() => {
    const token = searchParams.get("token");
    if (token) {
      setSession(token, { id: "", email: "", role: "tester" });
      apiFetch<{ id: string; email: string; role: string; name: string }>("/api/v1/auth/me")
        .then((user) => {
          setSession(token, user);
          resolveLandingPath().then((path) => router.replace(path));
        })
        .catch(() => setError("SSO login failed"));
    }

    apiFetch<{ auth_enabled: boolean; sso_configured: boolean }>("/api/v1/auth/status")
      .then((s) => {
        setAuthEnabled(s.auth_enabled);
        setSsoConfigured(s.sso_configured);
        if (!s.auth_enabled) resolveLandingPath().then((path) => router.replace(path));
      })
      .catch(() => {});
  }, [searchParams, router]);

  const login = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await apiFetch<{
        access_token: string;
        user: { id: string; email: string; role: string; name?: string };
      }>("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      if (res.access_token) {
        setSession(res.access_token, res.user);
        const path = await resolveLandingPath();
        router.push(path);
      }
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--surface-sunken)] p-4">
      <div className="ds-card w-full max-w-md">
        <div className="ds-card-header">
          <div className="flex items-center gap-2">
            <Shield className="w-5 h-5 text-brand-700" />
            <h1 className="text-lg font-semibold">QEOS Sign In</h1>
          </div>
        </div>
        <form onSubmit={login} className="ds-card-body space-y-4 pt-0">
          {authEnabled && (
            <p className="text-xs text-[var(--text-tertiary)]">Authentication is enforced for this environment.</p>
          )}
          <div>
            <label className="block text-xs font-medium mb-1.5">Email</label>
            <input className="ds-input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1.5">Password</label>
            <input className="ds-input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </div>
          {error && <p className="text-xs text-red-600">{error}</p>}
          <button type="submit" disabled={loading} className="ds-btn-primary w-full">
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <LogIn className="w-4 h-4" />}
            Sign in
          </button>
          {ssoConfigured && (
            <a href={`${BACKEND_URL}/api/v1/auth/sso/login`} className="ds-btn-secondary w-full text-center block">
              Sign in with SSO
            </a>
          )}
        </form>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center"><Loader2 className="w-6 h-6 animate-spin" /></div>}>
      <LoginForm />
    </Suspense>
  );
}
