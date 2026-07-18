"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import clsx from "clsx";
import { ChevronRight, HelpCircle, LogOut } from "lucide-react";
import { NotificationBell } from "@/components/NotificationBell";
import { ReportBugButton } from "@/components/ReportBugButton";
import { useEffect, useState } from "react";
import { APP_TAGLINE, formatAppVersionLabel } from "@/config/version";
import { NAVIGATION } from "@/config/navigation";
import { getIcon } from "@/config/icons";
import { GlobalSearch } from "@/components/GlobalSearch";
import { BackendStatusBanner } from "@/components/BackendStatusBanner";
import { ActiveProjectSelector } from "@/components/ProjectSelector";
import { WorkspaceBar } from "@/components/workspace/WorkspaceBar";
import { useClientMounted } from "@/hooks/useClientMounted";
import { apiFetch, BACKEND_URL } from "@/lib/api";
import { clearSession, getStoredUser, type AuthUser } from "@/lib/auth";

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed inset-y-0 left-0 w-[240px] bg-sidebar flex flex-col z-30 border-r border-sidebar-border">
      <div className="h-14 flex items-center px-5 border-b border-sidebar-border">
        <Link href="/" className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-md bg-brand-700 flex items-center justify-center">
            <span className="text-white text-xs font-bold tracking-tight">Q</span>
          </div>
          <div>
            <span className="text-sm font-semibold text-white tracking-tight">QEOS</span>
            <span className="block text-[10px] text-gray-500 leading-tight mt-0.5">
              {APP_TAGLINE} ({formatAppVersionLabel()})
            </span>
          </div>
        </Link>
      </div>

      <nav className="flex-1 overflow-y-auto py-4 px-3">
        {NAVIGATION.map((group) => (
          <div key={group.label} className="mb-5">
            <p className="px-3 mb-1.5 text-[10px] font-semibold uppercase tracking-widest text-gray-500">
              {group.label}
            </p>
            <ul className="space-y-0.5">
              {group.items.map((item) => {
                const active = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
                const Icon = getIcon(item.icon);
                return (
                  <li key={item.id}>
                    <Link
                      href={item.href}
                      className={clsx(
                        "flex items-center gap-2.5 px-3 py-2 rounded-md text-[13px] font-medium transition-colors",
                        active
                          ? "bg-sidebar-active text-white"
                          : "text-gray-400 hover:text-gray-200 hover:bg-sidebar-hover"
                      )}
                    >
                      <Icon className="w-4 h-4 shrink-0 opacity-80" />
                      {item.label}
                      {item.badge && (
                        <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded bg-brand-700/30 text-blue-300">
                          {item.badge}
                        </span>
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <SidebarUser />
    </aside>
  );
}

function SidebarUser() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const router = useRouter();

  useEffect(() => {
    const stored = getStoredUser();
    if (stored) {
      setUser(stored);
      return;
    }
    apiFetch<{ enabled: boolean; user?: AuthUser }>("/api/v1/auth/status")
      .then((s) => { if (s.user) setUser(s.user); })
      .catch(() => {});
  }, []);

  const logout = () => {
    clearSession();
    router.push("/login");
  };

  const initials = (user?.name || user?.email || "U").charAt(0).toUpperCase();
  const displayName = user?.name || user?.email || "Development User";
  const role = user?.role?.replace(/_/g, " ") || "Platform Admin";

  return (
    <div className="p-4 border-t border-sidebar-border">
      <div className="flex items-center gap-2 px-2">
        <div className="w-7 h-7 rounded-full bg-gray-700 flex items-center justify-center text-xs font-medium text-gray-300">
          {initials}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-gray-300 truncate">{displayName}</p>
          <p className="text-[10px] text-gray-500 truncate capitalize">{role}</p>
        </div>
        <button
          onClick={logout}
          className="ds-btn-ghost p-1.5 text-gray-500 hover:text-gray-300"
          title="Sign out"
          suppressHydrationWarning
        >
          <LogOut className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}

export function TopBar({ title }: { title?: string }) {
  const pathname = usePathname();
  const showProject = pathname !== "/login" && !pathname.startsWith("/projects/");
  const mounted = useClientMounted();

  return (
    <header className="h-14 bg-[var(--surface-raised)] border-b border-[var(--border-default)] flex items-center justify-between px-6 sticky top-0 z-20">
      <div className="flex items-center gap-3 text-sm min-w-0">
        {title && (
          <div className="flex items-center gap-2 shrink-0">
            <span className="text-[var(--text-tertiary)]">QEOS</span>
            <ChevronRight className="w-3.5 h-3.5 text-gray-300" />
            <span className="font-medium text-[var(--text-primary)]">{title}</span>
          </div>
        )}
        {showProject && (
          <div className="flex items-center gap-2 min-w-0 flex-1">
            {title && <span className="text-gray-300">|</span>}
            {mounted ? (
              <>
                <ActiveProjectSelector className="ds-input py-1.5 text-sm w-52 max-w-[240px] shrink-0" />
                <WorkspaceBar />
              </>
            ) : (
              <div
                className="ds-input py-1.5 text-sm w-52 max-w-[240px] shrink-0 h-[34px] bg-[var(--surface-sunken)] animate-pulse rounded-md"
                aria-hidden
              />
            )}
          </div>
        )}
      </div>

      <div className="flex items-center gap-2">
        {mounted ? (
          <GlobalSearch />
        ) : (
          <div className="w-64 h-[34px] bg-[var(--surface-sunken)] animate-pulse rounded-md" aria-hidden />
        )}
        <a href={`${BACKEND_URL}/docs`} target="_blank" rel="noopener noreferrer" className="ds-btn-ghost p-2" title="API Docs">
          <HelpCircle className="w-4 h-4" />
        </a>
        <ReportBugButton />
        <NotificationBell />
      </div>
    </header>
  );
}

export function AppShell({ children, title }: { children: React.ReactNode; title?: string }) {
  return (
    <div className="min-h-screen">
      <Sidebar />
      <div className="pl-[240px]">
        <TopBar title={title} />
        <BackendStatusBanner />
        <main className="p-6 max-w-[1440px]">{children}</main>
      </div>
    </div>
  );
}
