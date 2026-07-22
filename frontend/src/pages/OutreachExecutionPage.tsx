import { Link, useParams } from "react-router-dom";
import { Breadcrumbs } from "../components/Breadcrumbs";
import { WorkflowExecutionView } from "../components/WorkflowExecutionView";
import { Button } from "../design-system";
import { useOutreachExecution } from "../outreach/useOutreachExecution";

/**
 * OutreachExecutionPage — M8.12, exact structural mirror of
 * PersonalizationExecutionPage.tsx (M8.11): the "Live Workflow Progress"
 * screen for Outreach, reached only after ProspectOutreach.tsx's
 * runRequest navigates here post-POST .../run. That page's own
 * request-creation/draft-review UI is otherwise unchanged.
 */
export default function OutreachExecutionPage() {
  const { companyId, prospectId, contactId, requestId } = useParams();
  const { isLoading, error, viewProps } = useOutreachExecution(companyId, requestId);

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Businesses", to: "/businesses" },
          { label: "Prospects", to: `/businesses/${companyId}/discovery/prospects` },
          { label: "Outreach", to: `/businesses/${companyId}/prospects/${prospectId}/contacts/${contactId}/outreach` },
          { label: "Live Progress" },
        ]}
      />

      <h1 className="mb-1 text-h1 font-semibold text-slate-100">Live Workflow Progress</h1>
      <p className="mb-6 text-body text-slate-400">
        Real-time AI Outreach generation - updates as the Workflow Engine actually runs it, no simulated progress.
      </p>

      {error && <p className="mb-4 text-sm text-status-danger">{error}</p>}

      {!isLoading && (
        <WorkflowExecutionView
          title="Outreach run"
          subtitle="AI Outreach"
          resultsAction={
            <Link to={`/businesses/${companyId}/prospects/${prospectId}/contacts/${contactId}/outreach`}>
              <Button size="sm">View Results</Button>
            </Link>
          }
          {...viewProps}
        />
      )}
    </div>
  );
}
