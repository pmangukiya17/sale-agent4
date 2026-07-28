import { Navigate, Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { DashboardLayout } from "./layouts/DashboardLayout";
import Login from "./pages/Login";
import Pipeline from "./pages/Pipeline";
import Contacts from "./pages/Contacts";
import Settings from "./pages/Settings";
import Businesses from "./pages/Businesses";
import CompanyProfileEditor from "./pages/CompanyProfileEditor";
import CompanyProducts from "./pages/CompanyProducts";
import CompanyICP from "./pages/CompanyICP";
import CompanyKnowledgeBase from "./pages/CompanyKnowledgeBase";
import WorkspaceSettingsPage from "./pages/WorkspaceSettingsPage";
import DiscoverySearches from "./pages/DiscoverySearches";
import DiscoveryExecutionPage from "./pages/DiscoveryExecutionPage";
import DiscoveryJobs from "./pages/DiscoveryJobs";
import Prospects from "./pages/Prospects";
import ResearchJobs from "./pages/ResearchJobs";
import ProspectResearch from "./pages/ProspectResearch";
import ResearchExecutionPage from "./pages/ResearchExecutionPage";
import PersonalizationJobs from "./pages/PersonalizationJobs";
import ProspectStrategy from "./pages/ProspectStrategy";
import PersonalizationExecutionPage from "./pages/PersonalizationExecutionPage";
import OutreachPlaybooks from "./pages/OutreachPlaybooks";
import ProspectOutreach from "./pages/ProspectOutreach";
import OutreachExecutionPage from "./pages/OutreachExecutionPage";
import BusinessEmailSignature from "./pages/BusinessEmailSignature";
import OAuthCallback from "./pages/OAuthCallback";
import DeliveryLayout from "./pages/delivery/DeliveryLayout";
import DeliveryConnections from "./pages/delivery/DeliveryConnections";
import DeliverySendingProfiles from "./pages/delivery/DeliverySendingProfiles";
import DeliveryCampaigns from "./pages/delivery/DeliveryCampaigns";
import DeliveryCampaignDetail from "./pages/delivery/DeliveryCampaignDetail";
import CommandCenter from "./pages/CommandCenter";
import AIWorkforce from "./pages/AIWorkforce";
import Analytics from "./pages/Analytics";
import Reports from "./pages/Reports";
import Conversations from "./pages/Conversations";
import MailboxBriefPage from "./pages/MailboxBriefPage";
import { AIGatewayLayout } from "./ai-gateway/AIGatewayLayout";
import AIGatewayOverview from "./pages/ai-gateway/AIGatewayOverview";
import AIGatewayProviders from "./pages/ai-gateway/AIGatewayProviders";
import AIGatewayProviderDetail from "./pages/ai-gateway/AIGatewayProviderDetail";
import AIGatewayRouting from "./pages/ai-gateway/AIGatewayRouting";
import AIGatewayActivity from "./pages/ai-gateway/AIGatewayActivity";
import AIGatewayUsage from "./pages/ai-gateway/AIGatewayUsage";
import AIGatewayApprovals from "./pages/ai-gateway/AIGatewayApprovals";
import AIGatewayHealth from "./pages/ai-gateway/AIGatewayHealth";
import AIGatewaySettings from "./pages/ai-gateway/AIGatewaySettings";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      {/* Top-level, unnested (not under /businesses/:companyId/...) - see
          OAuthCallback.tsx's docstring for why: the browser arrives here
          fresh from Google/Microsoft's redirect with only ?code&state,
          no route params. Still behind ProtectedRoute since the user is
          still logged in (the JWT survives the redirect); it just isn't
          wrapped in DashboardLayout/Sidebar since it's a transient
          full-screen handoff page, not a dashboard content area. */}
      <Route
        path="/oauth/callback"
        element={
          <ProtectedRoute>
            <OAuthCallback />
          </ProtectedRoute>
        }
      />
      {/* M8.3 review: "/" now sends users to the real Command Center
          instead of the legacy Pipeline page - Command Center is the
          intended landing experience per the Design Bible, and the legacy
          Company/stage list is no longer positioned as the app's default
          view. Pipeline.tsx itself is preserved, unmodified in behavior,
          just moved to its own explicitly transitional route below. */}
      <Route path="/" element={<Navigate to="/command-center" replace />} />
      <Route
        path="/crm/legacy-pipeline"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <Pipeline />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/contacts"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <Contacts />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/settings"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <Settings />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/businesses"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <Businesses />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/businesses/new"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <CompanyProfileEditor />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/businesses/:companyId"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <CompanyProfileEditor />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/businesses/:companyId/products"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <CompanyProducts />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/businesses/:companyId/icp"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <CompanyICP />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/businesses/:companyId/knowledge-base"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <CompanyKnowledgeBase />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/businesses/:companyId/branding/email-signature"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <BusinessEmailSignature />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/businesses/:companyId/discovery/searches"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <DiscoverySearches />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />
      {/* M8.8: Live AI Workflow Visualization - "Live Workflow Progress"
          step of Create Search -> Start Discovery -> Live Workflow
          Progress -> Results. A separate route from
          /discovery/searches itself (that config page is unchanged);
          reached only via DiscoverySearches.tsx's handleRun navigating
          here after POST .../run returns "queued". */}
      <Route
        path="/businesses/:companyId/discovery/searches/:searchId/run"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <DiscoveryExecutionPage />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/businesses/:companyId/discovery/jobs"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <DiscoveryJobs />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/businesses/:companyId/discovery/prospects"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <Prospects />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/businesses/:companyId/research/jobs"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <ResearchJobs />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/businesses/:companyId/prospects/:prospectId/research"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <ProspectResearch />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />
      {/* M8.13: Live AI Workflow Visualization for Research - reached
          only via ProspectResearch.tsx's runRequest navigating here
          after POST .../run returns "queued". */}
      <Route
        path="/businesses/:companyId/prospects/:prospectId/research/:requestId/run"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <ResearchExecutionPage />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/businesses/:companyId/personalization/jobs"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <PersonalizationJobs />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/businesses/:companyId/prospects/:prospectId/strategy"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <ProspectStrategy />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />
      {/* M8.14: Live AI Workflow Visualization for Personalization -
          reached only via ProspectStrategy.tsx's runRequest navigating
          here after POST .../run returns "queued". */}
      <Route
        path="/businesses/:companyId/prospects/:prospectId/strategy/:requestId/run"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <PersonalizationExecutionPage />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/businesses/:companyId/outreach/playbooks"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <OutreachPlaybooks />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/businesses/:companyId/prospects/:prospectId/contacts/:contactId/outreach"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <ProspectOutreach />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />
      {/* M8.15: Live AI Workflow Visualization for Outreach - reached
          only via ProspectOutreach.tsx's runRequest navigating here after
          POST .../run returns "queued". */}
      <Route
        path="/businesses/:companyId/prospects/:prospectId/contacts/:contactId/outreach/:requestId/run"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <OutreachExecutionPage />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />
      {/* M5: Outreach Delivery Engine. Tabbed shell (Campaigns / Sending
          Profiles / Connections) - a single top-level Sidebar entry per
          the explicit refinement, not three. Campaign detail is its own
          route below, outside the tab shell - same drill-down precedent
          as ProspectOutreach.tsx relative to Prospects.tsx. */}
      <Route
        path="/businesses/:companyId/delivery"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <DeliveryLayout />
            </DashboardLayout>
          </ProtectedRoute>
        }
      >
        <Route index element={<Navigate to="campaigns" replace />} />
        <Route path="campaigns" element={<DeliveryCampaigns />} />
        <Route path="sending-profiles" element={<DeliverySendingProfiles />} />
        <Route path="connections" element={<DeliveryConnections />} />
      </Route>
      <Route
        path="/businesses/:companyId/delivery/campaigns/:campaignId"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <DeliveryCampaignDetail />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/workspace-settings"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <WorkspaceSettingsPage />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />

      {/* M8.3: real Command Center dashboard. "/" is intentionally left
          untouched (still Pipeline.tsx) - "Command Center" was always its
          own nav destination (see navConfig.ts), so no repoint or route
          removal was needed; this is a pure content swap of what
          "/command-center" renders, everything else about this route is
          identical to M8.2 (same ProtectedRoute/DashboardLayout wrapping). */}
      <Route
        path="/command-center"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <CommandCenter />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />
      {/* M8.4: real AI Workforce roster + per-agent execution trace,
          backed by the new read-only ai_workforce backend API. */}
      <Route
        path="/ai-workforce"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <AIWorkforce />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />
      {/* Executive Daily Brief - UX follow-up requested right after the
          CEO's Track C5 approval: real Mailbox Brief backend (Track C5),
          redesigned dedicated page (see MailboxBriefPage.tsx's own
          docstring for the full section-by-section data-reuse mapping).
          The last ComingSoon placeholder route in the app is now real. */}
      <Route
        path="/mailbox-brief"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <MailboxBriefPage />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />
      {/* M6.5: real Conversations content - business-wide list + inline
          detail over the read-only GET /conversations endpoints, reusing
          the M6.1-M6.4 Conversation/EmailMessage/Reply Intelligence data
          already written by the sync/thread-builder/reply-classification
          workers. */}
      <Route
        path="/conversations"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <Conversations />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />
      {/* M8.9: real Analytics/Reports content - built entirely from
          already-existing endpoints (see Analytics.tsx/Reports.tsx's own
          docstrings for the exact scope boundary). */}
      <Route
        path="/analytics"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <Analytics />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/reports"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <Reports />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />
      {/* M8.1: AI Gateway UI Foundation. Workspace-scoped (not
          /businesses/:companyId/...) - same top-level precedent as
          /command-center and /ai-workforce, since routing/cost/approval
          infrastructure spans every business, not just the active one.
          AIGatewayLayout owns breadcrumb/title/subtitle/page-nav and
          renders <Outlet/>, matching DeliveryLayout's nested-route
          shape below it. Provider detail is a child route (not a
          sibling) so it still renders inside the same layout shell -
          pageMeta.ts's prefix-match fallback keeps "Providers"
          highlighted in the strip while on a provider's detail page. */}
      <Route
        path="/ai-gateway"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <AIGatewayLayout />
            </DashboardLayout>
          </ProtectedRoute>
        }
      >
        <Route index element={<AIGatewayOverview />} />
        <Route path="providers" element={<AIGatewayProviders />} />
        <Route path="providers/:providerKey" element={<AIGatewayProviderDetail />} />
        <Route path="routing" element={<AIGatewayRouting />} />
        <Route path="activity" element={<AIGatewayActivity />} />
        <Route path="usage" element={<AIGatewayUsage />} />
        <Route path="approvals" element={<AIGatewayApprovals />} />
        <Route path="health" element={<AIGatewayHealth />} />
        <Route path="settings" element={<AIGatewaySettings />} />
      </Route>
    </Routes>
  );
}
