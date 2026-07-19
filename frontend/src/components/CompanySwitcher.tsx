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
    return <div className="px-3 py-2 text-xs text-slate-500">Loading businesses…</div>;
  }

  if (companies.length === 0) {
    return (
      <button
        onClick={() => navigate("/businesses/new")}
        className="mx-3 w-[calc(100%-1.5rem)] rounded-lg border border-dashed border-border-hairline-strong px-3 py-2 text-left text-xs font-medium text-slate-500 hover:border-accent-primary/50 hover:text-slate-300"
      >
        + Add your business
      </button>
    );
  }

  return (
    <div className="relative px-3">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between rounded-lg border border-border-hairline bg-surface-2 px-3 py-2 text-left text-sm font-medium text-slate-100 hover:border-border-hairline-strong"
      >
        <span className="truncate">{activeCompany?.name ?? "Select business"}</span>
        <span className="text-slate-500">▾</span>
      </button>

      {open && (
        <div className="absolute left-3 right-3 z-10 mt-1 rounded-lg border border-border-hairline-strong bg-surface-1 py-1 shadow-elevation-3">
          {companies.map((company) => (
            <button
              key={company.id}
              onClick={() => {
                setActiveCompanyId(company.id);
                setOpen(false);
              }}
              className={`block w-full truncate px-3 py-2 text-left text-sm ${
                company.id === activeCompany?.id ? "bg-surface-2 font-medium text-white" : "text-slate-300 hover:bg-surface-2"
              }`}
            >
              {company.name}
            </button>
          ))}
          <div className="my-1 border-t border-border-hairline" />
          <button
            onClick={() => {
              setOpen(false);
              navigate("/businesses");
            }}
            className="block w-full px-3 py-2 text-left text-sm text-slate-500 hover:bg-surface-2"
          >
            Manage businesses
          </button>
        </div>
      )}
    </div>
  );
}
