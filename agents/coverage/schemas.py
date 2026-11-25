"""Pydantic output schema for the Coverage Assessment Agent.

Kept in sync with backend/app/models/schemas.py.
Used as the response_format for structured Hosted Agent output.
"""

from typing import Literal

from pydantic import BaseModel, Field


class AgentCheck(BaseModel):
    """A rule or validation check performed by the coverage agent."""

    rule: str = ""

    result: Literal[
        "pass",
        "fail",
        "warning",
        "info",
    ] = "info"

    detail: str = ""


class ToolResult(BaseModel):
    """Result of an MCP or other external tool invocation."""

    tool_name: str = ""

    status: Literal[
        "pass",
        "fail",
        "warning",
    ] = "warning"

    detail: str = ""


class ProviderVerification(BaseModel):
    """Provider information returned by NPI verification."""

    npi: str = ""
    name: str = ""
    specialty: str = ""

    status: Literal[
        "active",
        "inactive",
        "not_found",
        "unverified",
    ] = "unverified"

    detail: str = ""


class CoveragePolicy(BaseModel):
    """A Medicare coverage policy considered in the assessment."""

    policy_id: str = ""
    title: str = ""

    type: Literal[
        "LCD",
        "NCD",
        "UNKNOWN",
    ] = "UNKNOWN"

    relevant: bool = True


class CriterionAssessment(BaseModel):
    """Assessment of one policy or medical-necessity criterion."""

    criterion: str = ""

    status: Literal[
        "MET",
        "NOT_MET",
        "INSUFFICIENT",
    ] = "INSUFFICIENT"

    confidence: int = Field(
        default=0,
        ge=0,
        le=100,
    )

    evidence: list[str] = Field(
        default_factory=list
    )

    notes: str = ""

    source: str = ""

    # Maintained for compatibility with the current backend contract.
    # True only when status is MET.
    met: bool = False


class DocumentationGap(BaseModel):
    """Missing documentation identified during coverage assessment."""

    what: str = ""

    critical: bool = False

    request: str = ""


class CoverageResult(BaseModel):
    """Structured output returned by the Coverage Assessment Agent."""

    agent_name: str = "Coverage Agent"

    checks_performed: list[AgentCheck] = Field(
        default_factory=list
    )

    provider_verification: ProviderVerification | None = None

    coverage_policies: list[CoveragePolicy] = Field(
        default_factory=list
    )

    criteria_assessment: list[CriterionAssessment] = Field(
        default_factory=list
    )

    coverage_criteria_met: list[str] = Field(
        default_factory=list
    )

    coverage_criteria_not_met: list[str] = Field(
        default_factory=list
    )

    policy_references: list[str] = Field(
        default_factory=list
    )

    coverage_limitations: list[str] = Field(
        default_factory=list
    )

    documentation_gaps: list[DocumentationGap] = Field(
        default_factory=list
    )

    tool_results: list[ToolResult] = Field(
        default_factory=list
    )

    error: str | None = None