from datetime import datetime
from typing import Any
from uuid import UUID

from typing import Any

from pydantic import BaseModel, Field


# --- Project ---

class ProjectCreate(BaseModel):
    name: str
    description: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class ProjectResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime | None = None
    requirement_count: int = 0
    test_case_count: int = 0

    model_config = {"from_attributes": True}


class ProjectDetailResponse(ProjectResponse):
    coverage_percentage: float = 0.0


# --- Requirements ---

class RequirementCreate(BaseModel):
    title: str | None = None
    content: str
    source_type: str = "user_story"
    external_ref: str | None = None


class RequirementResponse(BaseModel):
    id: UUID
    project_id: UUID
    title: str
    content: str
    source_type: str
    external_ref: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Test Cases ---

class TestCaseResponse(BaseModel):
    id: UUID
    project_id: UUID
    module_id: UUID | None = None
    module_name: str | None = None
    environment_id: UUID | None = None
    environment_name: str | None = None
    case_code: str | None = None
    title: str
    description: str
    steps: list[str | dict[str, Any]]
    expected_results: list[str]
    priority: str
    tags: list[str]
    requirement_refs: list[str]
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TestCaseCreate(BaseModel):
    title: str | None = None
    description: str | None = None
    steps: list[str | dict[str, Any]] = Field(default_factory=list)
    expected_results: list[str] = Field(default_factory=list)
    priority: str = "medium"
    module_id: UUID | None = None
    module_name: str | None = None
    environment_id: UUID | None = None


class TestCaseUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    steps: list[str | dict[str, Any]] | None = None
    expected_results: list[str] | None = None
    priority: str | None = None
    status: str | None = None
    module_id: UUID | None = None
    environment_id: UUID | None = None


class TestCaseBulkAction(BaseModel):
    test_case_ids: list[UUID]
    action: str = Field(description="delete | disable | enable")


# --- Test Suites ---

class TestSuiteResponse(BaseModel):
    id: UUID
    project_id: UUID
    name: str
    suite_type: str
    test_case_ids: list[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Generation ---

class GenerateRequest(BaseModel):
    content: str
    source_type: str = "user_story"
    title: str | None = None
    run_test_design: bool = True


class GenerateResponse(BaseModel):
    requirement_id: str
    agent_run_id: str
    test_design_run_id: str | None = None
    test_scenarios: list[str]
    test_cases: list[dict[str, Any]]
    coverage_matrix: dict[str, Any]
    risk_analysis: dict[str, Any] | None = None
    test_design: dict[str, Any] | None = None


# --- Coverage ---

class CoverageResponse(BaseModel):
    total_requirements: int
    covered_requirements: int
    coverage_percentage: float
    gaps: list[str]
    risk_analysis: dict[str, Any] | None = None
    requirement_count: int = 0
    test_case_count: int = 0
    updated_at: str | None = None


# --- Agent Runs ---

class AgentRunResponse(BaseModel):
    id: UUID
    project_id: UUID
    agent_type: str
    status: str
    output_data: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}
