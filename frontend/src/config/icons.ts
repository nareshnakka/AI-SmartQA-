import {
  LayoutDashboard,
  FolderKanban,
  Workflow,
  Code2,
  BarChart3,
  Blocks,
  Database,
  Settings,
  Zap,
  GitBranch,
  Radar,
  PlayCircle,
  Activity,
  Layers,
  type LucideIcon,
} from "lucide-react";

export const ICON_MAP: Record<string, LucideIcon> = {
  LayoutDashboard,
  FolderKanban,
  Workflow,
  Code2,
  BarChart3,
  Blocks,
  Database,
  Settings,
  Zap,
  GitBranch,
  Radar,
  PlayCircle,
  Activity,
  Layers,
};

export function getIcon(name: string): LucideIcon {
  return ICON_MAP[name] ?? LayoutDashboard;
}
