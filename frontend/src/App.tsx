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
import DiscoveryJobs from "./pages/DiscoveryJobs";
import Prospects from "./pages/Prospects";
import ResearchJobs from "./pages/ResearchJobs";
import ProspectResearch from "./pages/ProspectResearch";
import PersonalizationJobs from "./pages/PersonalizationJobs";
import ProspectStrategy from "./pages/ProspectStrategy";
import OutreachPlaybooks from "./pages/OutreachPlaybooks";
import ProspectOutreach from "./pages/ProspectOutreach";
import BusinessEmailSignature from "./pages/BusinessEmailSignature";
import OAuthCallback from "./pages/OAuthCallback";
import DeliveryLayout from "./pages/delivery/DeliveryLayout";
import DeliveryConnections from "./pages/delivery/DeliveryConnections";
import DeliverySendingProfiles from "./pages/delivery/DeliverySendingProfiles";
import DeliveryCampaigns from "./pages/delivery/DeliveryCampaigns";
import DeliveryCampaignDetail from "./pages/delivery/DeliveryCampaignDetail";

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
      <Route
        path="/"
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
    </Routes>
  );
}
