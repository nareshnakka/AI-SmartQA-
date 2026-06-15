/**
 * Extensible navigation config.
 * Add new features here — they appear in sidebar automatically.
 * Backend /api/v1/platform/navigation can override at runtime.
 */

export interface NavItem {
  id: string;
  label: string;
  href: string;
  icon: string;
  badge?: string;
}

export interface NavGroup {
  label: string;
  items: NavItem[];
}

export const NAVIGATION: NavGroup[] = [
  {
    label: "Overview",
    items: [
      { id: "dashboard", label: "Dashboard", href: "/", icon: "LayoutDashboard" },
      { id: "projects", label: "Projects", href: "/projects", icon: "FolderKanban" },
    ],
  },
  {
    label: "Quality Engineering",
    items: [
      { id: "quality-studio", label: "Quality Studio", href: "/quality-studio", icon: "Layers", badge: "Hub" },
      { id: "discovery", label: "Discovery", href: "/discovery", icon: "Radar" },
      { id: "studio", label: "Automation IDE", href: "/studio", icon: "Code2" },
      { id: "performance", label: "Performance", href: "/performance", icon: "Zap" },
      { id: "executions", label: "Executions", href: "/executions", icon: "PlayCircle" },
      { id: "pipelines", label: "Pipelines", href: "/pipelines", icon: "GitBranch" },
      { id: "reports", label: "Reports", href: "/reports", icon: "BarChart3" },
      { id: "agents", label: "Agents", href: "/agents", icon: "Workflow" },
    ],
  },
  {
    label: "Platform",
    items: [
      { id: "integrations", label: "Integrations", href: "/integrations", icon: "Blocks" },
      { id: "monitoring", label: "Monitoring", href: "/monitoring", icon: "Activity" },
      { id: "training", label: "Model Training", href: "/training", icon: "Database" },
      { id: "settings", label: "Settings", href: "/settings", icon: "Settings" },
    ],
  },
];

/** Register a new nav item at runtime (for plugins/custom modules) */
export function registerNavItem(groupLabel: string, item: NavItem): void {
  const group = NAVIGATION.find((g) => g.label === groupLabel);
  if (group && !group.items.find((i) => i.id === item.id)) {
    group.items.push(item);
  }
}
