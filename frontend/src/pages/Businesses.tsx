import { Link } from "react-router-dom";
import { useCompanies } from "../companies/CompanyContext";
import { Card, Badge, PlaceholderNotice } from "../design-system";

const NAV_LINKS = (companyId: string) => [
  { to: `/businesses/${companyId}`, label: "Edit profile" },
  { to: `/businesses/${companyId}/products`, label: "Products" },
  { to: `/businesses/${companyId}/icp`, label: "ICP" },
  { to: `/businesses/${companyId}/knowledge-base`, label: "Knowledge Base" },
  { to: `/businesses/${companyId}/branding/email-signature`, label: "Email Signature" },
  { to: `/businesses/${companyId}/discovery/searches`, label: "Discovery Searches" },
  { to: `/businesses/${companyId}/discovery/jobs`, label: "Discovery Jobs" },
  { to: `/businesses/${companyId}/discovery/prospects`, label: "Prospects" },
  { to: `/businesses/${companyId}/research/jobs`, label: "Research Jobs" },
  { to: `/businesses/${companyId}/personalization/jobs`, label: "Personalization Jobs" },
  { to: `/businesses/${companyId}/outreach/playbooks`, label: "Outreach Playbooks" },
  { to: `/businesses/${companyId}/delivery`, label: "Delivery" },
];

/**
 * Businesses — M8.7 Phase E1 (CRM zone). Migrated in place per Design
 * Bible Section 9.2: identical data source (useCompanies context,
 * unchanged) and identical set of per-business nav links, only the
 * presentation moves from bespoke light/dark-variant Tailwind onto the
 * dark design-system primitives (Card, Badge, PlaceholderNotice) so this
 * page stops carrying its own one-off `dark:` classes per Section 10.1's
 * Design Debt Budget.
 */
export default function Businesses() {
  const { companies, isLoading, activeCompanyId, setActiveCompanyId } = useCompanies();

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="mb-1 text-h1 font-semibold text-slate-100">My Businesses</h1>
          <p className="text-body text-slate-400">
            Every business you configure here becomes something the AI can research buyers, products, and an Ideal
            Customer Profile for.
          </p>
        </div>
        <Link
          to="/businesses/new"
          className="rounded-lg bg-accent-primary px-4 py-2 text-sm font-medium text-white hover:brightness-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary focus-visible:ring-offset-2 focus-visible:ring-offset-surface-0"
        >
          + Add business
        </Link>
      </div>

      {!isLoading && companies.length === 0 && (
        <PlaceholderNotice kind="no-data" reason="No businesses yet.">
          <Link to="/businesses/new" className="mt-0.5 inline-block font-medium text-accent-primary underline">
            Add your first one
          </Link>
        </PlaceholderNotice>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {isLoading &&
          Array.from({ length: 3 }).map((_, i) => (
            <Card key={i} className="h-40 animate-pulse">
              {null}
            </Card>
          ))}

        {companies.map((company) => (
          <Card key={company.id}>
            <div className="mb-3 flex items-start justify-between">
              <h3 className="font-semibold text-slate-100">{company.name}</h3>
              {company.is_default && <Badge tone="neutral">Default</Badge>}
            </div>
            <div className="flex flex-wrap gap-2 text-sm">
              {NAV_LINKS(company.id).map((link) => (
                <Link
                  key={link.to}
                  to={link.to}
                  className="rounded-lg border border-border-hairline px-3 py-1.5 text-slate-200 hover:border-border-hairline-strong hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary"
                >
                  {link.label}
                </Link>
              ))}
            </div>
            {company.id !== activeCompanyId && (
              <button
                onClick={() => setActiveCompanyId(company.id)}
                className="mt-3 text-xs font-medium text-slate-400 underline hover:text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary"
              >
                Make active
              </button>
            )}
          </Card>
        ))}
      </div>
    </div>
  );
}
