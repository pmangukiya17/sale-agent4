import { useEffect, useState } from "react";
import { apiClient } from "../api/client";

interface Contact {
  id: string;
  company_id: string;
  name: string | null;
  role: string | null;
  email: string | null;
  phone: string | null;
  created_at: string;
}

export default function Contacts() {
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiClient
      .get<Contact[]>("/contacts")
      .then((res) => setContacts(res.data))
      .catch(() => setError("Could not load contacts."))
      .finally(() => setIsLoading(false));
  }, []);

  return (
    <div>
      <h2 className="mb-1 text-2xl font-semibold text-slate-900">Contacts</h2>
      <p className="mb-6 text-sm text-slate-500">
        Purchasing contacts attached to companies in the CRM. Automated
        contact discovery is not wired up yet — this view proves the data
        path end to end, the same way Pipeline does for companies.
      </p>

      {isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}

      {!isLoading && !error && contacts.length === 0 && (
        <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">
          No contacts yet. Automated contact resolution lands in Milestone 5.
        </div>
      )}

      {contacts.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-100 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Role</th>
                <th className="px-4 py-3">Email</th>
                <th className="px-4 py-3">Phone</th>
              </tr>
            </thead>
            <tbody>
              {contacts.map((c) => (
                <tr key={c.id} className="border-t border-slate-100">
                  <td className="px-4 py-3 font-medium text-slate-900">{c.name ?? "—"}</td>
                  <td className="px-4 py-3 text-slate-600">{c.role ?? "—"}</td>
                  <td className="px-4 py-3 text-slate-600">{c.email ?? "—"}</td>
                  <td className="px-4 py-3 text-slate-600">{c.phone ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
