"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

interface Props {
  userName?: string;
  userOrg?: string;
  onLogout?: () => void;
}

export default function AdminSidebar({ userName = "Operator", userOrg = "Admin", onLogout }: Props) {
  const router = useRouter();
  const pathname = usePathname() ?? "";

  async function handleLogout() {
    await fetch("/api/auth/login", { method: "DELETE" });
    router.push("/login");
  }

  const initials = userName.split(" ").map((p) => p[0]).join("").slice(0, 2).toUpperCase();

  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M2 8h1.5" stroke="#f4f1ea" strokeWidth="1.4" strokeLinecap="round"/>
            <path d="M5 5v6" stroke="#f4f1ea" strokeWidth="1.4" strokeLinecap="round"/>
            <path d="M8 3v10" stroke="#f4f1ea" strokeWidth="1.4" strokeLinecap="round"/>
            <path d="M11 5v6" stroke="#f4f1ea" strokeWidth="1.4" strokeLinecap="round"/>
            <path d="M13.5 8H14" stroke="#f4f1ea" strokeWidth="1.4" strokeLinecap="round"/>
          </svg>
        </div>
        <div>
          <div className="brand-name">Resonant</div>
          <span className="brand-sub">Admin</span>
        </div>
      </div>

      <div className="nav-group">
        <div className="nav-label">Analytics</div>
        <Link href="/dashboard" className={`nav-item${pathname === "/dashboard" ? " active" : ""}`}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/>
            <rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>
          </svg>
          Dashboard
        </Link>
        <Link href="/dashboard/candidates" className={`nav-item${pathname.startsWith("/dashboard/candidates") ? " active" : ""}`}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="9" cy="8" r="3.5"/>
            <path d="M3 20c0-3 2.5-5 6-5s6 2 6 5"/>
            <circle cx="17" cy="9" r="2.5"/>
            <path d="M15 14c3 0 6 1.5 6 5"/>
          </svg>
          Candidates
        </Link>
      </div>

      <div className="nav-group">
        <div className="nav-label">Configuration</div>
        <Link href="/dashboard/skills" className={`nav-item${pathname.startsWith("/dashboard/skills") ? " active" : ""}`}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 3 2 8l10 5 10-5-10-5Z"/>
            <path d="M2 14l10 5 10-5"/>
          </svg>
          Skills library
        </Link>
        <Link href="/dashboard/config" className={`nav-item${pathname.startsWith("/dashboard/config") ? " active" : ""}`}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="3"/>
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z"/>
          </svg>
          Site config
        </Link>
        <button className="nav-item" onClick={onLogout ?? handleLogout}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
            <polyline points="16 17 21 12 16 7"/>
            <line x1="21" y1="12" x2="9" y2="12"/>
          </svg>
          Sign out
        </button>
      </div>

      <div className="sidebar-foot">
        <div className="user-chip">
          <div className="user-av">{initials}</div>
          <div className="user-meta">
            <b>{userName}</b>
            <span>{userOrg}</span>
          </div>
        </div>
      </div>
    </aside>
  );
}
