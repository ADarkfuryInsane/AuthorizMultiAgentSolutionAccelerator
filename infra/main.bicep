// ---------------------------------------------------------------------------
// Prior Auth MAF — Main Bicep Template
//
// Deploys resources into an EXISTING Resource Group.
//
// Deploys:
//   - Microsoft Foundry resource and project
//   - Azure OpenAI model deployment
//   - Container Registry
//   - Container Apps Environment
//   - Backend and frontend Container Apps
//   - Log Analytics
//   - Application Insights
//   - Role assignments
//
// NOTE:
//   The Resource Group is not created by this template.
// ---------------------------------------------------------------------------

targetScope = 'subscription'


// ── Parameters ──────────────────────────────────────────────────────────────

@minLength(1)
@maxLength(64)
@description('Name of the environment, for example dev, staging, or prod')
param environmentName string

@minLength(1)
@description('Primary location for deployed resources. The Resource Group metadata location does not need to match this location.')
@allowed([
  'eastus2'
  'swedencentral'
])
param location string

@description('Azure OpenAI deployment name used across all agent containers')
param azureOpenAIDeploymentName string = 'gpt-5.4-mini'

@description('Deployment SKU. DataZoneStandard is supported by this template only in East US 2.')
@allowed([
  'GlobalStandard'
  'DataZoneStandard'
])
param deploymentSkuName string = 'GlobalStandard'

@description('Whether container images have been built to ACR. Set automatically by the postprovision hook.')
param imagesBuilt string = ''

@minLength(1)
@description('Name of the existing Resource Group into which resources will be deployed')
param existingResourceGroupName string


// MCP server URLs are configured in each agent's agent.yaml:
//
//   MCP_ICD10_CODES
//   MCP_PUBMED
//   MCP_CLINICAL_TRIALS
//   MCP_NPI_REGISTRY
//   MCP_CMS_COVERAGE
//
// They are consumed by agents/<name>/main.py. The azd ai agent extension
// propagates these values into each agent container at deployment time.


// ── Variables ───────────────────────────────────────────────────────────────

var abbrs = loadJsonContent('./abbreviations.json')

var resourceToken = toLower(
  uniqueString(
    subscription().id,
    environmentName,
    location
  )
)

var tags = {
  'azd-env-name': environmentName
  'solution-accelerator': 'prior-auth-maf'
}


// ── Existing Resource Group ─────────────────────────────────────────────────
//
// This is a scope reference to an existing Resource Group. It does not create
// or modify the Resource Group itself.
//

var rg = resourceGroup(existingResourceGroupName)


// ── Container Registry ──────────────────────────────────────────────────────

module containerRegistry './modules/container-registry.bicep' = {
  name: 'container-registry'
  scope: rg

  params: {
    name: '${abbrs.containerRegistryRegistries}${resourceToken}'
    location: location
    tags: tags
  }
}


// ── Log Analytics + Application Insights ────────────────────────────────────

module monitoring './modules/monitoring.bicep' = {
  name: 'monitoring'
  scope: rg

  params: {
    logAnalyticsName: '${abbrs.operationalInsightsWorkspaces}${resourceToken}'
    appInsightsName: '${abbrs.insightsComponents}${resourceToken}'
    location: location
    tags: tags
  }
}


// ── Microsoft Foundry Resource + Project ────────────────────────────────────
//
// Foundry's App Insights project connection requires:
//
//   - The full Application Insights connection string
//   - The Application Insights resource ID
//
// The instrumentation key by itself is not accepted.
//

module aiFoundry './modules/ai-foundry.bicep' = {
  name: 'ai-foundry'
  scope: rg

  params: {
    name: '${abbrs.aiFoundry}${resourceToken}'
    location: location
    tags: tags

    appInsightsConnectionString: monitoring.outputs.appInsightsConnectionString
    appInsightsResourceId: monitoring.outputs.appInsightsResourceId

    deploymentName: azureOpenAIDeploymentName
    deploymentSkuName: deploymentSkuName
  }
}


// ── Container Apps Environment ──────────────────────────────────────────────

module containerAppsEnv './modules/container-apps-env.bicep' = {
  name: 'container-apps-env'
  scope: rg

  params: {
    name: '${abbrs.appManagedEnvironments}${resourceToken}'
    location: location
    tags: tags
    logAnalyticsWorkspaceId: monitoring.outputs.logAnalyticsWorkspaceId
  }
}


// ── Backend Container App ───────────────────────────────────────────────────

module backend './modules/container-app.bicep' = {
  name: 'backend'
  scope: rg

  params: {
    name: '${abbrs.appContainerApps}backend-${resourceToken}'
    location: location

    tags: union(
      tags,
      {
        'azd-service-name': 'backend'
      }
    )

    containerAppsEnvironmentId: containerAppsEnv.outputs.environmentId
    containerRegistryLoginServer: containerRegistry.outputs.loginServer

    imageName: 'backend'
    targetPort: 8000
    useAcrImage: imagesBuilt == 'true'

    cpu: '1'
    memory: '2Gi'

    // Backend currently keeps in-memory state. Keep it at one replica unless
    // review and notification state are moved to Cosmos DB, Redis, or another
    // shared state store.
    minReplicas: 1
    maxReplicas: 1

    env: [
      {
        name: 'AZURE_AI_PROJECT_ENDPOINT'
        value: aiFoundry.outputs.projectEndpoint
      }
      {
        name: 'HOSTED_AGENT_CLINICAL_NAME'
        value: 'clinical-reviewer-agent'
      }
      {
        name: 'HOSTED_AGENT_COVERAGE_NAME'
        value: 'coverage-assessment-agent'
      }
      {
        name: 'HOSTED_AGENT_COMPLIANCE_NAME'
        value: 'compliance-agent'
      }
      {
        name: 'HOSTED_AGENT_SYNTHESIS_NAME'
        value: 'synthesis-agent'
      }
      {
        name: 'HOSTED_AGENT_TIMEOUT_SECONDS'
        value: '180'
      }
      {
        name: 'APPLICATION_INSIGHTS_CONNECTION_STRING'
        value: monitoring.outputs.appInsightsConnectionString
      }
      {
        name: 'FRONTEND_ORIGIN'
        value: 'https://${abbrs.appContainerApps}frontend-${resourceToken}.${containerAppsEnv.outputs.defaultDomain}'
      }
    ]

    secrets: []

    healthCheckPath: '/health'
  }
}


// ── Frontend Container App ──────────────────────────────────────────────────

module frontend './modules/container-app.bicep' = {
  name: 'frontend'
  scope: rg

  params: {
    name: '${abbrs.appContainerApps}frontend-${resourceToken}'
    location: location

    tags: union(
      tags,
      {
        'azd-service-name': 'frontend'
      }
    )

    containerAppsEnvironmentId: containerAppsEnv.outputs.environmentId
    containerRegistryLoginServer: containerRegistry.outputs.loginServer

    imageName: 'frontend'
    targetPort: 80
    useAcrImage: imagesBuilt == 'true'

    minReplicas: 1

    env: [
      {
        name: 'BACKEND_URL'
        value: 'https://${abbrs.appContainerApps}backend-${resourceToken}.${containerAppsEnv.outputs.defaultDomain}'
      }
    ]

    secrets: []

    healthCheckPath: '/'
  }
}


// ── Role Assignments ────────────────────────────────────────────────────────
//
// Backend:
//   - Cognitive Services OpenAI User on Foundry
//
// Backend and frontend:
//   - AcrPull on ACR
//
// Foundry project and account identities:
//   - AcrPull on ACR
//
// Deployer:
//   - Foundry User and Foundry Project Manager via the postprovision hook
//

module roleAssignments './modules/role-assignments.bicep' = {
  name: 'role-assignments'
  scope: rg

  params: {
    foundryAccountName: aiFoundry.outputs.accountName

    backendPrincipalId: backend.outputs.principalId
    frontendPrincipalId: frontend.outputs.principalId

    containerRegistryName: containerRegistry.outputs.name

    foundryProjectPrincipalId: aiFoundry.outputs.projectPrincipalId
    foundryAccountPrincipalId: aiFoundry.outputs.accountPrincipalId
  }
}


// ── Outputs ─────────────────────────────────────────────────────────────────

output AZURE_RESOURCE_GROUP string = existingResourceGroupName

output AZURE_CONTAINER_REGISTRY_ENDPOINT string = containerRegistry.outputs.loginServer

output AI_FOUNDRY_ACCOUNT_NAME string = aiFoundry.outputs.accountName
output AI_FOUNDRY_PROJECT_NAME string = aiFoundry.outputs.projectName
output AI_FOUNDRY_ENDPOINT string = aiFoundry.outputs.endpoint
output AI_FOUNDRY_PROJECT_ENDPOINT string = aiFoundry.outputs.projectEndpoint
output AI_FOUNDRY_PORTAL_URL string = aiFoundry.outputs.portalUrl

// Required by the azd AI agent extension.
output AZURE_AI_PROJECT_ID string = aiFoundry.outputs.projectId
output AZURE_AI_PROJECT_ENDPOINT string = aiFoundry.outputs.projectEndpoint
output FOUNDRY_PROJECT_ENDPOINT string = aiFoundry.outputs.projectEndpoint

output BACKEND_CONTAINER_APP_NAME string = backend.outputs.name
output FRONTEND_CONTAINER_APP_NAME string = frontend.outputs.name

output AZURE_OPENAI_DEPLOYMENT_NAME string = azureOpenAIDeploymentName

output APPLICATION_INSIGHTS_CONNECTION_STRING string = monitoring.outputs.appInsightsConnectionString

output frontendUrl string = frontend.outputs.fqdn
output backendUrl string = backend.outputs.fqdn
