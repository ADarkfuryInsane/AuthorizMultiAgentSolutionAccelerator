"""Coverage Assessment Hosted Agent.

Verifies provider NPI information, searches Medicare coverage policies,
maps clinical findings to policy criteria, and returns a structured
coverage evaluation.

Hosted using:
  - FoundryChatClient
  - Agent
  - MCPStreamableHTTPTool
  - SkillsProvider
  - ResponsesHostServer

Diagnostic state:
  - NPI Registry MCP: ENABLED
  - CMS Coverage MCP: DISABLED

This lets us verify the NPI MCP independently before enabling the
CMS Coverage MCP.
"""

import os
from pathlib import Path

import httpx
from agent_framework import Agent, MCPStreamableHTTPTool, SkillsProvider
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from schemas import CoverageResult


load_dotenv()


def configure_observability() -> None:
    """Enable Agent Framework tracing when App Insights is configured."""

    explicit_connection_string = (
        os.environ.get("OTEL_CONNECTION_STRING")
        or os.environ.get("APPLICATION_INSIGHTS_CONNECTION_STRING")
    )

    platform_connection_string = os.environ.get(
        "APPLICATIONINSIGHTS_CONNECTION_STRING",
        "",
    )

    # A valid Application Insights connection string contains
    # InstrumentationKey=...
    #
    # If Foundry injected a malformed value, replace it with the explicit
    # value passed through the Hosted Agent configuration.
    if "InstrumentationKey=" not in platform_connection_string:
        if explicit_connection_string:
            os.environ[
                "APPLICATIONINSIGHTS_CONNECTION_STRING"
            ] = explicit_connection_string
        else:
            os.environ.pop(
                "APPLICATIONINSIGHTS_CONNECTION_STRING",
                None,
            )

    if os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        from agent_framework.observability import enable_instrumentation

        # Prior-authorization content can contain PHI.
        # Do not capture prompts/completions in shared environments.
        enable_instrumentation(
            enable_sensitive_data=False,
        )


def create_npi_mcp_tools() -> list:
    """Configure only the NPI Registry MCP.

    CMS Coverage MCP is deliberately disabled while diagnosing MCP
    connectivity.
    """

    tools = []

    npi_url = os.environ.get("MCP_NPI_REGISTRY")

    if not npi_url:
        return tools

    mcp_http_client = httpx.AsyncClient(
        headers={
            "User-Agent": "prior-auth-maf/1.0",
        },
        timeout=httpx.Timeout(
            connect=15.0,
            read=60.0,
            write=30.0,
            pool=15.0,
        ),
        follow_redirects=True,
    )

    tools.append(
        MCPStreamableHTTPTool(
            name="npi-registry",
            description=(
                "Validate provider NPI numbers and retrieve provider "
                "information from the CMS NPPES registry. "
                "Use this tool only when a provider NPI is supplied."
            ),
            url=npi_url,
            http_client=mcp_http_client,
            load_prompts=False,
        )
    )

    return tools


def main() -> None:
    # -----------------------------------------------------------------------
    # Observability
    # -----------------------------------------------------------------------

    configure_observability()

    # -----------------------------------------------------------------------
    # Foundry runtime configuration
    # -----------------------------------------------------------------------

    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]

    # Prefer the model deployment variable injected by the Hosted Agent
    # runtime. Preserve the existing accelerator/local-development names
    # as fallbacks.
    model = os.environ.get(
        "AZURE_AI_MODEL_DEPLOYMENT_NAME",
        os.environ.get(
            "MODEL_DEPLOYMENT_NAME",
            os.environ.get(
                "AZURE_OPENAI_DEPLOYMENT_NAME",
                "gpt-5.4-mini",
            ),
        ),
    )

    # -----------------------------------------------------------------------
    # MCP tools
    # -----------------------------------------------------------------------

    # Diagnostic phase:
    #
    # Enable ONLY the NPI Registry MCP.
    #
    # Do not enable CMS Coverage until this tool has been independently
    # verified in the Foundry Playground.
    tools = create_npi_mcp_tools()

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

    # This credential path has already been proven in the working synthesis
    # agent and in coverage with MCP tools disabled.
    credential = DefaultAzureCredential()

    chat_client = FoundryChatClient(
        project_endpoint=project_endpoint,
        model=model,
        credential=credential,
    )

    # -----------------------------------------------------------------------
    # Coverage Assessment Agent
    # -----------------------------------------------------------------------

    agent = Agent(
        client=chat_client,
        name="coverage-assessment-agent",
        instructions=(
            "You are the Coverage Assessment Agent for prior authorization "
            "review. "

            "Use your coverage-assessment skill to evaluate provider "
            "identity, Medicare coverage requirements, medical necessity "
            "criteria, and documentation requirements. "

            "The NPI Registry MCP tool is currently available. "

            "When a provider NPI is supplied, use the npi-registry tool to "
            "verify the provider. "

            "Do not report a provider as verified unless the NPI Registry "
            "tool result supports that conclusion. "

            "If the NPI Registry tool fails or times out, do not invent a "
            "provider verification result. Record the lookup failure in "
            "tool_results and treat provider verification as insufficient. "

            "The CMS Coverage MCP tool is temporarily unavailable during "
            "diagnostic testing. Do not claim that you searched CMS coverage "
            "policies during this test. "

            "Do not invent NCD identifiers, LCD identifiers, policy titles, "
            "coverage requirements, provider details, clinical evidence, "
            "or policy references. "

            "For each applicable coverage criterion, return exactly one "
            "status: MET, NOT_MET, or INSUFFICIENT. "

            "Use INSUFFICIENT whenever the evidence needed to evaluate a "
            "criterion was not supplied or could not be verified. "

            "Do not interpret missing evidence as MET. "

            "Report missing documentation separately and identify whether "
            "each documentation gap is critical. "

            "Coverage policies handled by this application concern Medicare "
            "NCDs and LCDs. Commercial and Medicare Advantage requirements "
            "may differ. "

            "Your final response must conform to the CoverageResult schema."
        ),
        tools=tools,
        context_providers=[
            skills_provider,
        ],
        default_options={
            "response_format": CoverageResult,
            "store": False,
        },
    )

    # -----------------------------------------------------------------------
    # Foundry Hosted Agent HTTP server
    # -----------------------------------------------------------------------

    ResponsesHostServer(agent).run()


if __name__ == "__main__":
    main()