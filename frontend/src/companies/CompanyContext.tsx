import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { apiClient } from "../api/client";
import { useAuth } from "../auth/AuthContext";

export interface CompanyProfile {
  id: string;
  name: string;
  logo_url: string | null;
  is_default: boolean;
  [key: string]: unknown;
}

interface CompanyContextValue {
  companies: CompanyProfile[];
  activeCompanyId: string | null;
  activeCompany: CompanyProfile | null;
  isLoading: boolean;
  setActiveCompanyId: (id: string) => void;
  refresh: () => Promise<void>;
}

const STORAGE_KEY = "sales_agent_active_company_id";

const CompanyContext = createContext<CompanyContextValue | undefined>(undefined);

export function CompanyProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [companies, setCompanies] = useState<CompanyProfile[]>([]);
  const [activeCompanyId, setActiveCompanyIdState] = useState<string | null>(
    () => localStorage.getItem(STORAGE_KEY)
  );
  const [isLoading, setIsLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!user) {
      setCompanies([]);
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    try {
      const { data } = await apiClient.get<CompanyProfile[]>("/company-profiles");
      setCompanies(data);

      // If nothing (or a stale/deleted id) is selected, fall back to the
      // default business, or the first one, so the UI always has something
      // sensible scoped rather than silently showing nothing.
      const stillExists = data.some((c) => c.id === activeCompanyId);
      if (!stillExists) {
        const fallback = data.find((c) => c.is_default) ?? data[0];
        if (fallback) {
          setActiveCompanyIdState(fallback.id);
          localStorage.setItem(STORAGE_KEY, fallback.id);
        } else {
          setActiveCompanyIdState(null);
          localStorage.removeItem(STORAGE_KEY);
        }
      }
    } finally {
      setIsLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  const setActiveCompanyId = (id: string) => {
    setActiveCompanyIdState(id);
    localStorage.setItem(STORAGE_KEY, id);
  };

  const activeCompany = companies.find((c) => c.id === activeCompanyId) ?? null;

  return (
    <CompanyContext.Provider
      value={{ companies, activeCompanyId, activeCompany, isLoading, setActiveCompanyId, refresh }}
    >
      {children}
    </CompanyContext.Provider>
  );
}

export function useCompanies(): CompanyContextValue {
  const ctx = useContext(CompanyContext);
  if (!ctx) {
    throw new Error("useCompanies must be used within a CompanyProvider");
  }
  return ctx;
}
