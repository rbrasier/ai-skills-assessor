"use client";

import { useRouter } from "next/navigation";

interface Props {
  userName?: string;
  userOrg?: string;
  onLogout?: () => void;
}

export default function AdminSidebar({ userName = "Operator", userOrg = "Admin", onLogout }: Props) {
  const router = useRouter();

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
        <button className="nav-item active">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/>
            <rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>
          </svg>
          Dashboard
        </button>
        <button className="nav-item">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="9" cy="8" r="3.5"/>
            <path d="M3 20c0-3 2.5-5 6-5s6 2 6 5"/>
            <circle cx="17" cy="9" r="2.5"/>
            <path d="M15 14c3 0 6 1.5 6 5"/>
          </svg>
          Candidates
        </button>
      </div>

      <div className="nav-group">
        <div className="nav-label">Configuration</div>
        <button className="nav-item">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 3 2 8l10 5 10-5-10-5Z"/>
            <path d="M2 14l10 5 10-5"/>
          </svg>
          Skills library
        </button>
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
