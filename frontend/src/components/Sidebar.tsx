import { NavLink } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

const NAV_ITEMS = [
  { to: "/", label: "Pipeline" },
  { to: "/contacts", label: "Contacts" },
  { to: "/settings", label: "Settings" },
];

export function Sidebar() {
  const { user, logout } = useAuth();

  return (
    <aside className="flex h-screen w-60 flex-col justify-between border-r border-slate-200 bg-white">
      <div>
        <div className="px-5 py-6">
          <h1 className="text-lg font-semibold text-slate-900">Sales Agent</h1>
          <p className="text-xs text-slate-500">Shiveshwar Textiles</p>
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
                    : "text-slate-600 hover:bg-slate-100"
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </div>
      <div className="border-t border-slate-200 px-5 py-4">
        <p className="truncate text-sm text-slate-700">{user?.email}</p>
        <button
          onClick={logout}
          className="mt-2 text-xs font-medium text-slate-500 hover:text-slate-800"
        >
          Sign out
        </button>
      </div>
    </aside>
  );
}
