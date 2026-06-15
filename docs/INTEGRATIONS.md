# QEOS Integration Guide

## Source Control

| Provider | Auth Methods | Capabilities |
|----------|-------------|--------------|
| **GitHub** | OAuth, PAT, GitHub App | Repos, Actions dispatch, webhooks, PR triggers |
| **Bitbucket** | OAuth, App Password | Repos, Pipelines trigger, webhooks |
| **GitLab** | OAuth, Private Token | Repos, CI pipeline trigger, webhooks (cloud + self-hosted) |
| **Gitea / Forgejo** | OAuth, Access Token | Self-hosted repos, OAuth |
| **Azure DevOps** | PAT, OAuth | Repos, Pipelines trigger |

### Connecting GitHub

```bash
curl -X POST http://localhost:8000/api/v1/integrations/connect \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "github",
    "project_id": "00000000-0000-0000-0000-000000000001",
    "credentials": { "token": "ghp_..." },
    "config": {}
  }'
```

### Connecting Bitbucket

```bash
curl -X POST http://localhost:8000/api/v1/integrations/connect \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "bitbucket",
    "project_id": "00000000-0000-0000-0000-000000000001",
    "credentials": {
      "username": "your-user",
      "app_password": "your-app-password"
    }
  }'
```

### Self-Hosted GitLab / Gitea

Pass `base_url` in config:

```json
{
  "provider": "gitlab",
  "config": { "base_url": "https://gitlab.yourcompany.com" },
  "credentials": { "private_token": "glpat-..." }
}
```

## CI/CD

| Provider | Integration |
|----------|------------|
| Jenkins | Job trigger, status polling |
| GitHub Actions | Workflow dispatch via GitHub integration |
| GitLab CI | Pipeline trigger via GitLab integration |
| Azure Pipelines | Run trigger via Azure DevOps integration |

### Webhook Endpoints

Configure webhooks in your Git provider to point to:

```
POST /api/v1/integrations/webhooks/{provider}
```

Supported events:
- **Push** → sync test assets
- **Pull Request** → trigger regression pack
- **Pipeline/Workflow complete** → collect results

## Enterprise ALM

### Jira

Connect with domain, email, and API token:

```json
{
  "provider": "jira",
  "credentials": {
    "domain": "yourcompany.atlassian.net",
    "email": "user@company.com",
    "api_token": "..."
  }
}
```

Use JQL search to pull epics, stories, and acceptance criteria into the Requirements Agent.

## OAuth Flow

```
GET /api/v1/integrations/oauth/{provider}/authorize
  ?client_id=...&redirect_uri=...&state=...
```

Returns `{ "authorization_url": "..." }` for browser redirect.
