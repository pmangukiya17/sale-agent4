import { useEffect, useState } from "react";
import { Bell } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { useCompanies } from "../companies/CompanyContext";
import { CommandPalette } from "./CommandPalette";
import { StatusIndicator, cn } from "../design-system";
import { useNotifications } from "../notifications/useNotifications";

/**
 * Top command strip — M8.2, Design Bible Section 3.
 *
 * Left to right: command palette trigger, then (right-aligned) the
 * "AI System" status pill, notification bell, date/time, and the
 * workspace+user identity cluster. That identity cluster is a
 * *persistent confirmation* of who/where you are, deliberately distinct
 * from the sidebar's own workspace SWITCHER (CompanySwitcher) - Design
 * Bible Section 0 item 8 covers why both are kept rather than one being
 * cut as a "duplicate."
 *
 * Honesty notes on what's real vs. not yet wired, stated plainly rather
 * than silently faked:
 * - Date/time is real (the browser's own clock, ticking).
 * - The "AI System" pill is currently a static "Idle" placeholder - there
 *   is no real Supervisor/Agent execution data reaching the frontend yet
 *   (that arrives with M8.3's dashboard and, eventually, real backend
 *   push/polling per Design Bible Section 13/14). Rendered as `idle`
 *   rather than invented as `active`, since claiming activity that isn't
 *   happening would be exactly the "decorative, not informational"
 *   motion the Design Bible argues against.
 * - The notification bell (M8.5) is now wired to the real Notification
 *   Center API (GET/POST /company-profiles/{id}/notifications - see
 *   ../notifications/useNotifications.ts). It still has a real, honest
 *   EMPTY state ("No notifications yet") when the Notification worker
 *   genuinely hasn't produced anything for this workspace, distinct from
 *   its loading/error states - never fabricated sample notifications.
 */
export function TopCommandStrip() {
  const { user } = useAuth();
  const { activeCompany } = useCompanies();
  const [now, setNow] = useState(() => new Date());
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const { notifications, unreadCount, isLoading, error, markRead, markAllRead } = useNotifications();

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(timer);
  }, []);

  return (
    <header className="flex h-16 items-center justify-between border-b border-border-hairline bg-surface-0 px-6">
      <CommandPalette />

      <div className="flex items-center gap-5">
        <StatusIndicator kind="idle" label="AI System — Idle" />

        <div className="relative">
          <button
            onClick={() => setNotificationsOpen((prev) => !prev)}
            className="relative flex h-9 w-9 items-center justify-center rounded-lg text-slate-400 hover:bg-surface-2 hover:text-slate-100"
            aria-label={unreadCount > 0 ? `Notifications (${unreadCount} unread)` : "Notifications"}
          >
            <Bell className="h-4 w-4" aria-hidden="true" />
            {unreadCount > 0 && (
              <span className="absolute right-1 top-1 flex h-2 w-2 rounded-full bg-accent-critical" aria-hidden="true" />
            )}
          </button>
          {notificationsOpen && (
            <div className="absolute right-0 z-20 mt-2 w-80 rounded-card border border-border-hairline-strong bg-surface-1/95 p-4 shadow-elevation-3 backdrop-blur-xl">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-slate-100">Notifications</p>
                {unreadCount > 0 && (
                  <button
                    onClick={markAllRead}
                    className="text-xs font-medium text-accent-primary hover:text-accent-primary/80"
                  >
                    Mark all read
                  </button>
                )}
              </div>

              {isLoading && <p className="mt-2 text-sm text-slate-500">Loading…</p>}

              {!isLoading && error && <p className="mt-2 text-sm text-accent-critical">{error}</p>}

              {!isLoading && !error && notifications.length === 0 && (
                <p className="mt-2 text-sm text-slate-500">
                  No notifications yet — this workspace's Notification worker hasn't produced any.
                </p>
              )}

              {!isLoading && !error && notifications.length > 0 && (
                <ul className="mt-2 max-h-80 space-y-1 overflow-y-auto">
                  {notifications.map((notification) => (
                    <li key={notification.id}>
                      <button
                        onClick={() => markRead(notification.id)}
                        className={cn(
                          "w-full rounded-lg px-2 py-2 text-left hover:bg-surface-2",
                          !notification.is_read && "bg-surface-2/60",
                        )}
                      >
                        <div className="flex items-start gap-2">
                          {!notification.is_read && (
                            <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent-primary" aria-hidden="true" />
                          )}
                          <div className={cn(!notification.is_read ? "flex-1" : "flex-1 pl-3.5")}>
                            <p className="text-sm font-medium text-slate-100">{notification.title}</p>
                            <p className="mt-0.5 text-xs text-slate-500">{notification.message}</p>
                          </div>
                        </div>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>

        <span className={cn("hidden text-sm text-slate-400 tabular-nums lg:inline")}>
          {now.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })} ·{" "}
          {now.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}
        </span>

        <div className="flex items-center gap-2 border-l border-border-hairline pl-4">
          <div className="text-right">
            <p className="text-sm font-medium leading-tight text-slate-100">{activeCompany?.name ?? "No workspace"}</p>
            <p className="text-xs leading-tight text-slate-500">{user?.role ?? "—"}</p>
          </div>
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-surface-2 text-xs font-semibold text-slate-200">
            {(user?.full_name ?? user?.email ?? "?").charAt(0).toUpperCase()}
          </div>
        </div>
      </div>
    </header>
  );
}
