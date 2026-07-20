import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AuthProvider } from "./auth/AuthContext";
import { CompanyProvider } from "./companies/CompanyContext";
import { ToastProvider } from "./design-system";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <CompanyProvider>
          {/* M8.7 Phase D: mounted once at the app root, per Toast.tsx's
              own docstring - any component calls useToast(), none
              construct their own toast queue. */}
          <ToastProvider>
            <App />
          </ToastProvider>
        </CompanyProvider>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>
);
