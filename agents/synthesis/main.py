"""Synthesis Decision Hosted Agent.

Synthesizes outputs from Compliance, Clinical, and Coverage agents into
a final APPROVE or PEND recommendation using gate-based evaluation,
weighted confidence scoring, and a structured audit trail.

Hosted using:
  - FoundryChatClient
  - Agent
  - SkillsProvider
  - ResponsesHostServer

Structured output is enforced through SynthesisOutput.
"""

import os
from pathlib import Path

from agent_framework import Agent, SkillsProvider
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from schemas import SynthesisOutput


# Load local .env when running locally.
# Hosted Agent environment variables remain available through os.environ.
load_dotenv()


def configure_observability() -> None:
    """Configure Agent Framework tracing when App Insights is available.

    The Foundry Hosted Agent platform may provide
    APPLICATIONINSIGHTS_CONNECTION_STRING.

    This solution also explicitly passes OTEL_CONNECTION_STRING through
    agent.yaml. If the platform-provided value is missing or malformed,
    use the explicit connection string instead.
    """

    explicit_connection_string = (
        os.environ.get("OTEL_CONNECTION_STRING")
        or os.environ.get("APPLICATION_INSIGHTS_CONNECTION_STRING")
    )

    platform_connection_string = os.environ.get(
        "APPLICATIONINSIGHTS_CONNECTION_STRING",
        "",
    )

    # A valid Application Insights connection string should contain
    # InstrumentationKey=...
    #
    # If the platform-injected value is absent or malformed, fall back to
    # the explicit value supplied by agent.yaml.
    if "InstrumentationKey=" not in platform_connection_string:
        if explicit_connection_string:
            os.environ[
                "APPLICATIONINSIGHTS_CONNECTION_STRING"
            ] = explicit_connection_string
        else:
            # Avoid handing an invalid value to the tracing stack.
            os.environ.pop(
                "APPLICATIONINSIGHTS_CONNECTION_STRING",
                None,
            )

    connection_string = os.environ.get(
        "APPLICATIONINSIGHTS_CONNECTION_STRING"
    )

    if connection_string:
        from agent_framework.observability import enable_instrumentation

        # Sensitive-data collection is deliberately disabled because
        # prior-authorization prompts may contain PHI.
        enable_instrumentation(
            enable_sensitive_data=False,
        )


def main() -> None:
    # -----------------------------------------------------------------------
    # Observability
    # -----------------------------------------------------------------------

    configure_observability()

    # -----------------------------------------------------------------------
    # Foundry runtime configuration
    # -----------------------------------------------------------------------

    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]

    # Prefer the model variable supplied by the Hosted Agent runtime.
    # Retain MODEL_DEPLOYMENT_NAME and gpt-5.4-mini as fallbacks for
    # compatibility with the existing accelerator configuration.
    model = os.environ.get(
        "AZURE_AI_MODEL_DEPLOYMENT_NAME",
        os.environ.get(
            "MODEL_DEPLOYMENT_NAME",
            "gpt-5.4-mini",
        ),
    )

    # -----------------------------------------------------------------------
    # Skills
    # -----------------------------------------------------------------------

    skills_path = Path(__file__).parent / "skills"

    skills_provider = SkillsProvider.from_paths(
        str(skills_path),
        disable_load_skill_approval=True,
        disable_read_skill_resource_approval=True,
    )

    # -----------------------------------------------------------------------
    # Authentication + Foundry model client
    # -----------------------------------------------------------------------

    # Keep DefaultAzureCredential because this is the credential path already
    # proven to work inside this Hosted Agent.
    credential = DefaultAzureCredential()

    chat_client = FoundryChatClient(
        project_endpoint=project_endpoint,
        model=model,
        credential=credential,
    )

    # -----------------------------------------------------------------------
    # Synthesis Agent
    # -----------------------------------------------------------------------

    agent = Agent(
        client=chat_client,
        name="synthesis-agent",
        instructions=(
            "You are the Synthesis Agent for prior authorization review. "

            "Use your synthesis-decision skill to evaluate the outputs from "
            "the Compliance, Clinical Reviewer, and Coverage agents. "

            "Evaluate the case through the strict three-gate pipeline: "

            "Gate 1: Provider verification. "
            "Determine whether the provider information is valid and whether "
            "any provider-related deficiency blocks approval. "

            "Gate 2: Code validation. "
            "Evaluate the Clinical Reviewer output for diagnosis, procedure, "
            "ICD-10, CPT, and other coding issues. "

            "Gate 3: Medical necessity and coverage. "
            "Evaluate the Coverage and Compliance outputs for applicable "
            "coverage criteria, medical necessity requirements, documentation "
            "requirements, and policy compliance. "

            "Produce exactly one final recommendation: APPROVE or PEND. "

            "Include weighted confidence scoring, clinical rationale, "
            "coverage criteria that were met or not met, missing documentation, "
            "policy references when available, and a complete synthesis "
            "audit trail. "

            "Do not invent policy references, clinical evidence, provider "
            "verification results, or coverage criteria that were not supplied "
            "by the upstream agents. "

            "If required evidence is missing or an approval gate cannot be "
            "established from the supplied information, prefer PEND rather "
            "than assuming that the requirement passed. "

            "Your final response must conform to the SynthesisOutput schema."
        ),
        tools=[],
        context_providers=[
            skills_provider,
        ],
        default_options={
            "response_format": SynthesisOutput,
            "store": False,
        },
    )

    # -----------------------------------------------------------------------
    # Hosted Agent HTTP server
    # -----------------------------------------------------------------------

    ResponsesHostServer(agent).run()


if __name__ == "__main__":
    main()