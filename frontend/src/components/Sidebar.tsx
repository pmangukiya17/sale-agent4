import { NavLink } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { useCompanies } from "../companies/CompanyContext";
import { CompanySwitcher } from "./CompanySwitcher";

const NAV_ITEMS = [
  { to: "/", label: "Pipeline" },
  { to: "/contacts", label: "Contacts" },
  { to: "/businesses", label: "My Businesses" },
  { to: "/workspace-settings", label: "Workspace Settings" },
  { to: "/settings", label: "Settings" },
];

export function Sidebar() {
  const { user, logout } = useAuth();
  // Delivery is the first company-scoped item in this Sidebar (everything
  // else above is global) - it needs the currently active business to
  // build its link. A single "Delivery" entry here (not three separate
  // Connections/Sending Profiles/Campaigns items) is a deliberate
  // long-term-scalability choice: future operational modules (Analytics,
  // Conversations, Automation, Inbox) each get one entry too, not three,
  // keeping the Sidebar from growing unbounded per milestone. The
  // Businesses card link (Businesses.tsx) covers jumping to a
  // non-active company's Delivery section.
  const { activeCompanyId } = useCompanies();

  return (
    <aside className="flex h-screen w-60 flex-col justify-between border-r border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900">
      <div>
        <div className="px-5 py-6">
          <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Sales Agent</h1>
          <p className="text-xs text-slate-500 dark:text-slate-400">Shiveshwar Textiles</p>
        </div>

        <div className="mb-4">
          <CompanySwitcher />
        </div>

        <nav className="flex flex-col gap-1 px-3">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                `rounded-md px-3 py-2 text-sm font-medium ${
                  isActive
                    ? "bg-slate-900 text-white"
                    : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
          {activeCompanyId ? (
            <NavLink
              to={`/businesses/${activeCompanyId}/delivery`}
              className={({ isActive }) =>
                `rounded-md px-3 py-2 text-sm font-medium ${
                  isActive
                    ? "bg-slate-900 text-white"
                    : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
                }`
              }
            >
              Delivery
            </NavLink>
          ) : (
            <span
              title="Select a business first"
              className="cursor-not-allowed rounded-md px-3 py-2 text-sm font-medium text-slate-300 dark:text-slate-600"
            >
              Delivery
            </span>
          )}
        </nav>
      </div>
      <div className="border-t border-slate-200 px-5 py-4 dark:border-slate-700">
        <p className="truncate text-sm text-slate-700 dark:text-slate-300">{user?.email}</p>
        <button
          onClick={logout}
          className="mt-2 text-xs font-medium text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
        >
          Sign out
        </button>
      </div>
    </aside>
  );
}
