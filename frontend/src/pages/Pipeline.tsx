import { useEffect, useState } from "react";
import { apiClient } from "../api/client";

interface Company {
  id: string;
  name: string;
  country: string | null;
  stage: string;
  icp_score: number | null;
  created_at: string;
}

export default function Pipeline() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiClient
      .get<Company[]>("/companies")
      .then((res) => setCompanies(res.data))
      .catch(() => setError("Could not load companies."))
      .finally(() => setIsLoading(false));
  }, []);

  return (
    <div>
      <h2 className="mb-1 text-2xl font-semibold text-slate-900">Pipeline</h2>
      <p className="mb-6 text-sm text-slate-500">
        Companies currently tracked in the CRM. Discovery, scoring, and outreach
        are not wired up yet — this view proves the data path end to end.
      </p>

      {isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}

      {!isLoading && !error && companies.length === 0 && (
        <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">
          No companies yet. Discovery lands here starting in Milestone 1.
        </div>
      )}

      {companies.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-100 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Country</th>
                <th className="px-4 py-3">Stage</th>
                <th className="px-4 py-3">ICP Score</th>
              </tr>
            </thead>
            <tbody>
              {companies.map((c) => (
                <tr key={c.id} className="border-t border-slate-100">
                  <td className="px-4 py-3 font-medium text-slate-900">{c.name}</td>
                  <td className="px-4 py-3 text-slate-600">{c.country ?? "—"}</td>
                  <td className="px-4 py-3 text-slate-600">{c.stage}</td>
                  <td className="px-4 py-3 text-slate-600">{c.icp_score ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
