# Extensibility Guide

QEOS is built for extension. Add features, integrations, and agents without modifying core platform code.

## Architecture

```
Frontend (Next.js)
  config/navigation.ts  →  add nav items
  app/your-feature/     →  add pages

Platform API
  /api/v1/platform/manifest     →  extension catalog
  /api/v1/platform/navigation   →  dynamic menus

Extension Registry (app/core/extensions.py)
  Points: integration | agent | feature | webhook | report

Plugin Loader (app/plugins/)
  Auto-discovers modules on startup
```

## Add a New Integration

1. Create `backend/app/plugins/integrations/your_provider.py`
2. Implement `BaseIntegration` and call `register_plugin()`
3. Register handler in `IntegrationManager`
4. Restart — appears in Integration Hub automatically

See `backend/app/plugins/integrations/_example.py` for template.

## Add a New Agent

1. Create agent in `backend/app/agents/`
2. Register in `backend/app/agents/registry.py`
3. Add descriptor in `backend/app/core/extensions.py`

## Add a New Frontend Feature

1. Add entry in `frontend/src/config/navigation.ts`
2. Add icon in `frontend/src/config/icons.ts`
3. Create page in `frontend/src/app/your-feature/page.tsx`

Use `AppShell`, `PageHeader`, and components from `@/components/ui`.

## API Reference

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/platform/manifest` | Full extension catalog |
| `GET /api/v1/platform/navigation` | Dynamic nav config |
| `POST /api/v1/platform/plugins/reload` | Hot-reload plugins |

## Design System

Components: `PageHeader`, `MetricCard`, `Badge`, `Tabs`, `EmptyState`, `StatusDot`

CSS: `ds-card`, `ds-btn-primary`, `ds-btn-secondary`, `ds-input`, `ds-table`
