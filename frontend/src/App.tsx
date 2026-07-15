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
