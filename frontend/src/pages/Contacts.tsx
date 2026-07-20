import { useEffect, useState } from "react";
import { apiClient } from "../api/client";
import { Table, PlaceholderNotice, type TableColumn } from "../design-system";

interface Contact {
  id: string;
  company_id: string;
  name: string | null;
  role: string | null;
  email: string | null;
  phone: string | null;
  created_at: string;
}

const COLUMNS: TableColumn<Contact>[] = [
  { key: "name", header: "Name", sortable: true, sortValue: (c) => c.name ?? "", render: (c) => <span className="font-medium text-slate-100">{c.name ?? "—"}</span> },
  { key: "role", header: "Role", sortable: true, sortValue: (c) => c.role ?? "", render: (c) => c.role ?? "—" },
  { key: "email", header: "Email", render: (c) => c.email ?? "—" },
  { key: "phone", header: "Phone", render: (c) => c.phone ?? "—" },
];

/**
 * Contacts — M8.7 Phase E1 (CRM zone). Migrated in place per Design Bible
 * Section 9.2: same data-fetching (a single GET /contacts, unchanged),
 * only the presentation layer moves onto the design system (Table,
 * PlaceholderNotice) instead of bespoke light-mode markup, per Section
 * 9.1 - this is one of the pages Section 9.1 names explicitly as "most at
 * risk of defaulting to a generic CRUD treatment."
 */
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
      <h1 className="mb-1 text-h1 font-semibold text-slate-100">Contacts</h1>
      <p className="mb-6 text-body text-slate-400">
        Purchasing contacts attached to companies in the CRM. Automated contact discovery is not wired up yet — this
        view proves the data path end to end, the same way the legacy Pipeline list does for companies.
      </p>

      {error && <p className="mb-4 text-sm text-status-danger">{error}</p>}

      {!isLoading && !error && contacts.length === 0 ? (
        <PlaceholderNotice kind="no-data" reason="No contacts yet. Automated contact resolution is a separate, future milestone." />
      ) : (
        <Table columns={COLUMNS} rows={contacts} rowKey={(c) => c.id} isLoading={isLoading} emptyMessage="No contacts yet." />
      )}
    </div>
  );
}
