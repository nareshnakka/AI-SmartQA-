from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class TestingDomain(str, Enum):
    FUNCTIONAL = "functional"
    API = "api"
    PERFORMANCE = "performance"
    SECURITY = "security"
    ACCESSIBILITY = "accessibility"


class AgentType(str, Enum):
    REQUIREMENTS = "requirements"
    TEST_DESIGN = "test_design"
    AUTOMATION = "automation"
    PERFORMANCE = "performance"
    SELF_HEALING = "self_healing"
    DEFECT_INTELLIGENCE = "defect_intelligence"


class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class IntegrationProvider(str, Enum):
    GITHUB = "github"
    BITBUCKET = "bitbucket"
    GITLAB = "gitlab"
    GITEA = "gitea"
    FORGEJO = "forgejo"
    AZURE_DEVOPS = "azure_devops"
    JIRA = "jira"
    CONFLUENCE = "confluence"
    JENKINS = "jenkins"
    GITHUB_ACTIONS = "github_actions"
    GITLAB_CI = "gitlab_ci"
    AZURE_PIPELINES = "azure_pipelines"
    CIRCLECI = "circleci"
    BAMBOO = "bamboo"


class EnvironmentType(str, Enum):
    DEV = "dev"
    QA = "qa"
    SIT = "sit"
    UAT = "uat"
    STAGING = "staging"
    PERFORMANCE = "performance"
    PRE_PROD = "pre_prod"
    PROD = "prod"


class AutomationFramework(str, Enum):
    SELENIUM = "selenium"
    PLAYWRIGHT = "playwright"
    CYPRESS = "cypress"
    WEBDRIVERIO = "webdriverio"
    ROBOT_FRAMEWORK = "robot_framework"
    APPIUM = "appium"
    TESTCAFE = "testcafe"
    PUPPETEER = "puppeteer"


class PerformanceTool(str, Enum):
    JMETER = "jmeter"
    K6 = "k6"
    GATLING = "gatling"
    LOCUST = "locust"
    TAURUS = "taurus"


class UserRole(str, Enum):
    PLATFORM_ADMIN = "platform_admin"
    ENTERPRISE_ADMIN = "enterprise_admin"
    PROJECT_ADMIN = "project_admin"
    FUNCTIONAL_TESTER = "functional_tester"
    AUTOMATION_ENGINEER = "automation_engineer"
    PERFORMANCE_ENGINEER = "performance_engineer"
    SECURITY_ENGINEER = "security_engineer"
    BUSINESS_USER = "business_user"


# --- Request/Response Schemas ---


class HealthResponse(BaseModel):
    status: str
    version: str
    version_label: str = ""
    build: int = 1
    timestamp: datetime
    execution_executor: str = "asset_live_v2"
    playwright_python: bool = False
    playwright_browsers: bool = False
    playwright_hint: str | None = None
    runners_ready: dict | None = None


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None
    tenant_id: UUID | None = None


class ProjectResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    tenant_id: UUID | None
    created_at: datetime


class AgentRunRequest(BaseModel):
    agent_type: AgentType
    project_id: UUID
    input_data: dict[str, Any] = Field(default_factory=dict)
    llm_provider: str | None = None
    llm_model: str | None = None


class AgentRunResponse(BaseModel):
    id: UUID
    agent_type: AgentType
    status: AgentStatus
    project_id: UUID
    output: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class IntegrationConnectRequest(BaseModel):
    provider: IntegrationProvider
    project_id: UUID
    credentials: dict[str, Any]
    config: dict[str, Any] = Field(default_factory=dict)


class IntegrationResponse(BaseModel):
    id: UUID
    provider: IntegrationProvider
    project_id: UUID
    status: str
    config: dict[str, Any]
    created_at: datetime


class RequirementInput(BaseModel):
    source_type: str  # brd, frd, prd, user_story, jira, confluence
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class TestCaseOutput(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    title: str
    description: str
    steps: list[str]
    expected_results: list[str]
    priority: str = "medium"
    tags: list[str] = Field(default_factory=list)
    requirement_refs: list[str] = Field(default_factory=list)


class CoverageMatrix(BaseModel):
    total_requirements: int
    covered_requirements: int
    coverage_percentage: float
    gaps: list[str] = Field(default_factory=list)


class RequirementsAgentOutput(BaseModel):
    test_scenarios: list[str]
    test_cases: list[TestCaseOutput]
    risk_analysis: dict[str, Any]
    coverage_matrix: CoverageMatrix


class GitRepositoryInfo(BaseModel):
    provider: IntegrationProvider
    owner: str
    name: str
    default_branch: str
    url: str
    clone_url: str


class WebhookPayload(BaseModel):
    provider: IntegrationProvider
    event_type: str
    payload: dict[str, Any]
