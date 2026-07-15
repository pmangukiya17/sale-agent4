import { Route, Routes } from "react-router-dom";
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

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
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
