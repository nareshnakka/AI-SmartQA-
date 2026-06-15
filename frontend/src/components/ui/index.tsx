import clsx from "clsx";

interface PageHeaderProps {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  breadcrumbs?: { label: string; href?: string }[];
}

export function PageHeader({ title, subtitle, actions, breadcrumbs }: PageHeaderProps) {
  return (
    <div className="mb-6">
      {breadcrumbs && breadcrumbs.length > 0 && (
        <nav className="flex items-center gap-1.5 text-xs text-[var(--text-tertiary)] mb-2">
          {breadcrumbs.map((crumb, i) => (
            <span key={i} className="flex items-center gap-1.5">
              {i > 0 && <span className="text-gray-300">/</span>}
              <span className={i === breadcrumbs.length - 1 ? "text-[var(--text-secondary)]" : ""}>
                {crumb.label}
              </span>
            </span>
          ))}
        </nav>
      )}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="ds-page-title">{title}</h1>
          {subtitle && <p className="ds-page-subtitle">{subtitle}</p>}
        </div>
        {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
      </div>
    </div>
  );
}

interface MetricCardProps {
  label: string;
  value: string | number;
  change?: string;
  changeType?: "positive" | "negative" | "neutral";
  icon?: React.ReactNode;
}

export function MetricCard({ label, value, change, changeType = "neutral", icon }: MetricCardProps) {
  const changeColors = {
    positive: "text-emerald-600",
    negative: "text-red-600",
    neutral: "text-[var(--text-tertiary)]",
  };

  return (
    <div className="ds-card p-5">
      <div className="flex items-start justify-between">
        <div className="space-y-1">
          <p className="ds-metric-label">{label}</p>
          <p className="ds-metric-value">{value}</p>
          {change && (
            <p className={clsx("text-xs font-medium", changeColors[changeType])}>{change}</p>
          )}
        </div>
        {icon && (
          <div className="p-2 rounded-md bg-[var(--surface-sunken)] text-[var(--text-tertiary)]">
            {icon}
          </div>
        )}
      </div>
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
      <div className="p-3 rounded-lg bg-[var(--surface-sunken)] text-[var(--text-tertiary)] mb-4">
        {icon}
      </div>
      <h3 className="text-sm font-semibold text-[var(--text-primary)]">{title}</h3>
      <p className="text-sm text-[var(--text-secondary)] mt-1 max-w-sm">{description}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function StatusDot({ status }: { status: "online" | "offline" | "degraded" }) {
  const colors = {
    online: "bg-emerald-500",
    offline: "bg-gray-400",
    degraded: "bg-amber-500",
  };
  return (
    <span className="relative flex h-2 w-2">
      {status === "online" && (
        <span className={clsx("animate-ping absolute inline-flex h-full w-full rounded-full opacity-40", colors[status])} />
      )}
      <span className={clsx("relative inline-flex rounded-full h-2 w-2", colors[status])} />
    </span>
  );
}

export function Badge({
  children,
  variant = "neutral",
}: {
  children: React.ReactNode;
  variant?: "success" | "warning" | "error" | "info" | "neutral";
}) {
  const classes = {
    success: "ds-badge-success",
    warning: "ds-badge-warning",
    error: "ds-badge-error",
    info: "ds-badge-info",
    neutral: "ds-badge-neutral",
  };
  return <span className={classes[variant]}>{children}</span>;
}

export function Tabs({
  tabs,
  active,
  onChange,
}: {
  tabs: { id: string; label: string; count?: number }[];
  active: string;
  onChange: (id: string) => void;
}) {
  return (
    <div className="flex gap-1 border-b border-[var(--border-default)]">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          className={clsx(
            "px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors",
            active === tab.id
              ? "border-brand-700 text-brand-700"
              : "border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
          )}
        >
          {tab.label}
          {tab.count !== undefined && (
            <span className="ml-1.5 text-xs text-[var(--text-tertiary)]">({tab.count})</span>
          )}
        </button>
      ))}
    </div>
  );
}
