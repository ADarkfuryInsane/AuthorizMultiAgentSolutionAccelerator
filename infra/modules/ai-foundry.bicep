// ---------------------------------------------------------------------------
// Microsoft Foundry — Resource + Project (new architecture)
//
// Creates:
//   - Microsoft Foundry resource
//   - Microsoft Foundry project
//   - Application Insights project connection
//   - Azure OpenAI model deployment
//   - Account capability host
//   - Project capability host
//
// Reference:
// https://learn.microsoft.com/en-us/azure/foundry/how-to/create-resource-template
// ---------------------------------------------------------------------------

@description('Base name for Foundry resources')
param name string

@description('Location for all resources')
param location string

@description('Tags for all resources')
param tags object = {}

@description('Full Application Insights connection string used to link this Foundry project to Application Insights')
@secure()
param appInsightsConnectionString string

@description('Application Insights resource ID — the target resource for the AppInsights connection')
param appInsightsResourceId string

@description('Name for the model deployment used in API calls, e.g. gpt-5.4-mini')
param deploymentName string = 'gpt-5.4-mini'

@description('Model version to deploy')
param modelVersion string = '2026-03-17'

@description('Deployment SKU: DataZoneStandard or GlobalStandard')
@allowed([
  'DataZoneStandard'
  'GlobalStandard'
])
param deploymentSkuName string = 'GlobalStandard'

@description('Capacity in thousands of tokens per minute. 100 = 100K TPM')
param deploymentCapacityK int = 100


// ── Microsoft Foundry Resource ──────────────────────────────────────────────

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-12-01' = {
  name: 'foundry-${name}'
  location: location
  tags: tags

  identity: {
    type: 'SystemAssigned'
  }

  sku: {
    name: 'S0'
  }

  kind: 'AIServices'

  properties: {
    allowProjectManagement: true
    customSubDomainName: 'foundry-${name}'
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}


// ── Microsoft Foundry Project ───────────────────────────────────────────────

resource foundryProject 'Microsoft.CognitiveServices/accounts/projects@2025-12-01' = {
  name: 'proj-${name}'
  parent: foundryAccount
  location: location
  tags: tags

  identity: {
    type: 'SystemAssigned'
  }

  properties: {}
}


// ── Application Insights Project Connection ─────────────────────────────────
//
// IMPORTANT:
//
// Current Foundry validation requires:
//
//   1. metadata.ResourceId containing the Application Insights resource ID
//   2. The FULL Application Insights connection string
//
// An instrumentation key by itself is no longer accepted for this
// project connection.
//
// Microsoft recommends connection strings for Application Insights;
// they include the InstrumentationKey plus endpoint configuration.
//

resource appInsightsConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-12-01' = {
  name: 'app-insights'
  parent: foundryProject

  properties: {
    category: 'AppInsights'

    target: appInsightsResourceId

    authType: 'ApiKey'

    credentials: {
      key: appInsightsConnectionString
    }

    metadata: {
      ResourceId: appInsightsResourceId
    }
  }
}


// ── Account Capability Host ─────────────────────────────────────────────────
//
// Required for Foundry Hosted Agents at the Foundry account level.
//

resource capabilityHost 'Microsoft.CognitiveServices/accounts/capabilityHosts@2025-12-01' = {
  name: 'accountcaphost'
  parent: foundryAccount

  properties: {
    capabilityHostKind: 'Agents'
  }
}


// ── Project Capability Host ─────────────────────────────────────────────────
//
// Project-level capability host.
//
// Do NOT put:
//
//   capabilityHostKind: 'Agents'
//
// in ProjectCapabilityHostProperties. Bicep does not permit that property
// for the project-level resource type.
//

resource projectCapabilityHost 'Microsoft.CognitiveServices/accounts/projects/capabilityHosts@2025-12-01' = {
  name: 'projectcaphost'
  parent: foundryProject

  properties: {}

  dependsOn: [
    capabilityHost
  ]
}


// ── gpt-5.4-mini Model Deployment ──────────────────────────────────────────
//
// GlobalStandard:
//   No data residency guarantee; broader regional availability.
//
// DataZoneStandard:
//   Geographic data-zone residency; available only where supported.
//
// Deployment SKU is selected by the azd environment.
//

resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-12-01' = {
  name: deploymentName
  parent: foundryAccount

  sku: {
    name: deploymentSkuName
    capacity: deploymentCapacityK
  }

  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-5.4-mini'
      version: modelVersion
    }

    versionUpgradeOption: 'OnceCurrentVersionExpired'
  }

  dependsOn: [
    capabilityHost
  ]
}


// ── Outputs ─────────────────────────────────────────────────────────────────

output accountName string = foundryAccount.name

output projectName string = foundryProject.name

// Full ARM resource ID required by the azd AI agent extension.
output projectId string = foundryProject.id

output endpoint string = foundryAccount.properties.endpoint

output portalUrl string = 'https://ai.azure.com/manage/project?wsid=${foundryProject.id}'

// Project endpoint consumed by backend/agents.
//
// Format:
// https://<foundry-resource>.services.ai.azure.com/api/projects/<project>
//
output projectEndpoint string = 'https://${foundryAccount.name}.services.ai.azure.com/api/projects/${foundryProject.name}'

// Project system-assigned managed identity.
// Requires AcrPull when Foundry needs to pull hosted-agent images.
output projectPrincipalId string = foundryProject.identity.principalId

// Foundry account managed identity.
output accountPrincipalId string = foundryAccount.identity.principalId
