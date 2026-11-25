"""Pydantic output schema for the Synthesis Decision Agent.

Kept in sync with backend/app/models/schemas.py.
Used as response_format for MAF structured output.
"""

from typing import Literal

from pydantic import BaseModel, Field


class GateResults(BaseModel):
    gate_1_provider: Literal["PASS", "FAIL"] = "FAIL"
    gate_2_codes: Literal["PASS", "FAIL"] = "FAIL"
    gate_3_necessity: Literal["PASS", "FAIL"] = "FAIL"


class ConfidenceComponents(BaseModel):
    criteria_weight: float = 0.4
    criteria_score: float = 0.0

    extraction_weight: float = 0.3
    extraction_score: float = 0.0

    compliance_weight: float = 0.2
    compliance_score: float = 0.0

    policy_weight: float = 0.1
    policy_score: float = 0.0


class SynthesisAuditTrail(BaseModel):
    gates_evaluated: list[
        Literal[
            "gate_1_provider",
            "gate_2_codes",
            "gate_3_necessity",
        ]
    ] = Field(default_factory=list)

    gate_results: GateResults = Field(
        default_factory=GateResults
    )

    confidence_components: ConfidenceComponents = Field(
        default_factory=ConfidenceComponents
    )

    agents_consulted: list[
        Literal[
            "compliance",
            "clinical",
            "coverage",
        ]
    ] = Field(default_factory=list)


class SynthesisOutput(BaseModel):
    recommendation: Literal[
        "approve",
        "pend_for_review",
    ] = "pend_for_review"

    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )

    confidence_level: Literal[
        "HIGH",
        "MEDIUM",
        "LOW",
    ] = "LOW"

    summary: str = ""

    clinical_rationale: str = ""

    decision_gate: Literal[
        "gate_1_provider",
        "gate_2_codes",
        "gate_3_necessity",
        "approved",
    ] = "gate_3_necessity"

    coverage_criteria_met: list[str] = Field(default_factory=list)

    coverage_criteria_not_met: list[str] = Field(default_factory=list)

    missing_documentation: list[str] = Field(default_factory=list)

    policy_references: list[str] = Field(default_factory=list)

    criteria_summary: str = ""

    synthesis_audit_trail: SynthesisAuditTrail = Field(
        default_factory=SynthesisAuditTrail
    )

    disclaimer: str = ""