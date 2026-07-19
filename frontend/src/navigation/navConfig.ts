import {
  Bot,
  Building2,
  ClipboardList,
  FileBarChart,
  FileSearch,
  GitBranch,
  LayoutDashboard,
  Mail,
  MailCheck,
  MessagesSquare,
  Package,
  Radar,
  Send,
  Settings as SettingsIcon,
  SlidersHorizontal,
  Users,
  type LucideIcon,
} from "lucide-react";

/**
 * Single source of truth for the product's navigation IA (M8 Design
 * Bible Section 2/3) - both Sidebar.tsx and CommandPalette.tsx read from
 * this SAME list, so the two never drift into showing different
 * destinations for the same product. Extending or reorganizing the nav
 * (adding a page in a later milestone) only ever means changing this one
 * file.
 *
 * See Sidebar.tsx's own docstring for the full reasoning behind each
 * route choice (existing routes preserved exactly, company-scoped items
 * follow the pre-existing Delivery-link conditional pattern, not-yet-
 * built pages route to ComingSoon).
 */
export interface NavItem {
  label: string;
  icon: LucideIcon;
  to: string;
  requiresCompany?: boolean;
  /** Small pill shown next to the label in both Sidebar and CommandPalette
   * (single source of truth - see both components' rendering). Used for
   * "Legacy" today (the M0 Company/Pipeline page, kept reachable but
   * explicitly marked as a transitional CRM view per the M8.3 review), not
   * a general-purpose annotation mechanism beyond that. */
  badge?: string;
}

export interface NavZone {
  label: string | null;
  items: NavItem[];
}

export function getNavZones(activeCompanyId: string | null): NavZone[] {
  return [
    {
      label: null,
      items: [{ label: "Command Center", icon: LayoutDashboard, to: "/command-center" }],
    },
    {
      label: "AI Workforce",
      items: [
        { label: "AI Agents", icon: Bot, to: "/ai-workforce" },
        {
          label: "Discovery",
          icon: Radar,
          to: activeCompanyId ? `/businesses/${activeCompanyId}/discovery/searches` : "#",
          requiresCompany: true,
        },
        {
          label: "Research",
          icon: FileSearch,
          to: activeCompanyId ? `/businesses/${activeCompanyId}/research/jobs` : "#",
          requiresCompany: true,
        },
        {
          label: "Outreach",
          icon: Send,
          to: activeCompanyId ? `/businesses/${activeCompanyId}/outreach/playbooks` : "#",
          requiresCompany: true,
        },
        { label: "Mailbox Brief", icon: Mail, to: "/mailbox-brief" },
        {
          label: "Delivery",
          icon: MailCheck,
          to: activeCompanyId ? `/businesses/${activeCompanyId}/delivery` : "#",
          requiresCompany: true,
        },
      ],
    },
    {
      label: "CRM",
      items: [
        { label: "Companies", icon: Building2, to: "/businesses" },
        { label: "Contacts", icon: Users, to: "/contacts" },
        { label: "Pipeline", icon: GitBranch, to: "/crm/legacy-pipeline", badge: "Legacy" },
        {
          label: "Products",
          icon: Package,
          to: activeCompanyId ? `/businesses/${activeCompanyId}/products` : "#",
          requiresCompany: true,
        },
      ],
    },
    {
      label: "Intelligence",
      items: [
        { label: "Conversations", icon: MessagesSquare, to: "/conversations" },
        { label: "Analytics", icon: FileBarChart, to: "/analytics" },
        { label: "Reports", icon: ClipboardList, to: "/reports" },
      ],
    },
  ];
}

export const SETTINGS_NAV_ITEMS: NavItem[] = [
  { label: "Workspace Settings", icon: SlidersHorizontal, to: "/workspace-settings" },
  { label: "Settings", icon: SettingsIcon, to: "/settings" },
];
