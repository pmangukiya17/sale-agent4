import { Link } from "react-router-dom";
import { useCompanies } from "../companies/CompanyContext";

export default function Businesses() {
  const { companies, isLoading, activeCompanyId, setActiveCompanyId } = useCompanies();

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h2 className="mb-1 text-2xl font-semibold text-slate-900 dark:text-slate-100">
            My Businesses
          </h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Every business you configure here becomes something the AI can research
            buyers, products, and an Ideal Customer Profile for.
          </p>
        </div>
        <Link
          to="/businesses/new"
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 dark:bg-indigo-600 dark:hover:bg-indigo-500"
        >
          + Add business
        </Link>
      </div>

      {isLoading && <p className="text-sm text-slate-500">Loading…</p>}

      {!isLoading && companies.length === 0 && (
        <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900">
          No businesses yet.{" "}
          <Link to="/businesses/new" className="font-medium text-slate-900 underline dark:text-slate-100">
            Add your first one
          </Link>
          .
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {companies.map((company) => (
          <div
            key={company.id}
            className="rounded-lg border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-900"
          >
            <div className="mb-3 flex items-start justify-between">
              <h3 className="font-semibold text-slate-900 dark:text-slate-100">{company.name}</h3>
              {company.is_default && (
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600 dark:bg-slate-700 dark:text-slate-300">
                  Default
                </span>
              )}
            </div>
            <div className="flex flex-wrap gap-2 text-sm">
              <Link
                to={`/businesses/${company.id}`}
                className="rounded-md border border-slate-200 px-3 py-1.5 text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
              >
                Edit profile
              </Link>
              <Link
                to={`/businesses/${company.id}/products`}
                className="rounded-md border border-slate-200 px-3 py-1.5 text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
              >
                Products
              </Link>
              <Link
                to={`/businesses/${company.id}/icp`}
                className="rounded-md border border-slate-200 px-3 py-1.5 text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
              >
                ICP
              </Link>
              <Link
                to={`/businesses/${company.id}/knowledge-base`}
                className="rounded-md border border-slate-200 px-3 py-1.5 text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
              >
                Knowledge Base
              </Link>
              <Link
                to={`/businesses/${company.id}/discovery/searches`}
                className="rounded-md border border-slate-200 px-3 py-1.5 text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
              >
                Discovery Searches
              </Link>
              <Link
                to={`/businesses/${company.id}/discovery/jobs`}
                className="rounded-md border border-slate-200 px-3 py-1.5 text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
              >
                Discovery Jobs
              </Link>
              <Link
                to={`/businesses/${company.id}/discovery/prospects`}
                className="rounded-md border border-slate-200 px-3 py-1.5 text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
              >
                Prospects
              </Link>
            </div>
            {company.id !== activeCompanyId && (
              <button
                onClick={() => setActiveCompanyId(company.id)}
                className="mt-3 text-xs font-medium text-slate-500 underline hover:text-slate-800 dark:text-slate-400"
              >
                Make active
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
