import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useCompanies } from "../companies/CompanyContext";

/** Account/workspace-style switcher for the businesses the current user
 * owns - the selection drives which company's Products/ICP/Knowledge Base
 * every scoped page shows. Persisted in localStorage (see CompanyContext),
 * not server-side state. */
export function CompanySwitcher() {
  const { companies, activeCompany, setActiveCompanyId, isLoading } = useCompanies();
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();

  if (isLoading) {
    return <div className="px-3 py-2 text-xs text-slate-400">Loading businesses…</div>;
  }

  if (companies.length === 0) {
    return (
      <button
        onClick={() => navigate("/businesses/new")}
        className="w-full rounded-md border border-dashed border-slate-300 px-3 py-2 text-left text-xs font-medium text-slate-500 hover:border-slate-400 hover:text-slate-700 dark:border-slate-600 dark:text-slate-400"
      >
        + Add your business
      </button>
    );
  }

  return (
    <div className="relative px-3">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between rounded-md border border-slate-200 bg-white px-3 py-2 text-left text-sm font-medium text-slate-900 hover:border-slate-300 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
      >
        <span className="truncate">{activeCompany?.name ?? "Select business"}</span>
        <span className="text-slate-400">▾</span>
      </button>

      {open && (
        <div className="absolute left-3 right-3 z-10 mt-1 rounded-md border border-slate-200 bg-white py-1 shadow-lg dark:border-slate-700 dark:bg-slate-800">
          {companies.map((company) => (
            <button
              key={company.id}
              onClick={() => {
                setActiveCompanyId(company.id);
                setOpen(false);
              }}
              className={`block w-full truncate px-3 py-2 text-left text-sm ${
                company.id === activeCompany?.id
                  ? "bg-slate-100 font-medium text-slate-900 dark:bg-slate-700 dark:text-white"
                  : "text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-700"
              }`}
            >
              {company.name}
            </button>
          ))}
          <div className="my-1 border-t border-slate-100 dark:border-slate-700" />
          <button
            onClick={() => {
              setOpen(false);
              navigate("/businesses");
            }}
            className="block w-full px-3 py-2 text-left text-sm text-slate-500 hover:bg-slate-50 dark:text-slate-400 dark:hover:bg-slate-700"
          >
            Manage businesses
          </button>
        </div>
      )}
    </div>
  );
}
