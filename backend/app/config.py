from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "QEOS"
    app_env: str = "development"
    secret_key: str = "change-me-in-production"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    database_url: str = "sqlite+aiosqlite:///./qeos.db"
    redis_url: str = "redis://localhost:6379/0"

    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    default_llm_provider: str = "qeos-native"
    default_llm_model: str = "qeos-intelligence-v1"
    # Copilot prefers openai > anthropic > ollama when API keys are set (see copilot/agent.py)

    # Optional: path to fine-tuned QEOS model (future)
    qeos_model_path: str = ""
    qeos_enable_neural: bool = False
    qeos_hybrid_auto: bool = True  # Auto-use Ollama when available in hybrid mode
    ollama_model: str = "llama3.2"

    # Training data collection from agent runs
    qeos_training_collect: bool = True
    qeos_training_data_dir: str = "training/data/collected"

    # Phase 5 — Playwright runners
    playwright_enabled: bool = True
    playwright_headless: bool = True
    playwright_timeout_ms: int = 30000
    playwright_test_timeout_ms: int = 300_000
    discovery_max_pages: int = 15
    discovery_max_steps: int = 80
    discovery_agent_enabled: bool = True
    execution_timeout_sec: int = 300
    execution_artifacts_dir: str = "execution_artifacts"
    execution_video_enabled: bool = True

    # Phase 5 — Auth (optional)
    qeos_auth_enabled: bool = False
    qeos_default_admin_email: str = "admin@qeos.local"
    qeos_default_admin_password: str = "admin"

    # SSO — OIDC (Azure AD, Okta, Google Workspace)
    qeos_sso_enabled: bool = False
    qeos_sso_issuer_url: str = ""
    qeos_sso_client_id: str = ""
    qeos_sso_client_secret: str = ""
    qeos_sso_redirect_uri: str = "http://localhost:8000/api/v1/auth/sso/callback"
    qeos_sso_scopes: str = "openid profile email"

    # Monitoring webhook secrets
    datadog_webhook_secret: str = ""
    sentry_webhook_secret: str = ""

    github_app_id: str = ""
    github_app_private_key: str = ""
    github_webhook_secret: str = ""
    github_client_id: str = ""
    github_client_secret: str = ""

    bitbucket_client_id: str = ""
    bitbucket_client_secret: str = ""
    bitbucket_webhook_secret: str = ""

    gitlab_client_id: str = ""
    gitlab_client_secret: str = ""
    gitlab_webhook_secret: str = ""

    jira_client_id: str = ""
    jira_client_secret: str = ""
    jira_webhook_secret: str = ""

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


settings = Settings()
