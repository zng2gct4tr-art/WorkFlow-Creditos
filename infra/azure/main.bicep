targetScope = 'resourceGroup'

@description('Short unique prefix using lowercase letters and digits.')
@minLength(3)
@maxLength(16)
param prefix string
param location string = resourceGroup().location
@secure()
param postgresAdministratorPassword string
param postgresAdministratorLogin string = 'workflowadmin'

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${prefix}-logs'
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: '${prefix}docs'
  location: location
  sku: { name: 'Standard_ZRS' }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    publicNetworkAccess: 'Disabled'
    encryption: {
      keySource: 'Microsoft.Storage'
      services: { blob: { enabled: true, keyType: 'Account' } }
    }
  }
}
resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
  properties: {
    deleteRetentionPolicy: { enabled: true, days: 30 }
    containerDeleteRetentionPolicy: { enabled: true, days: 30 }
    isVersioningEnabled: true
  }
}
resource documents 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'credit-documents'
  properties: { publicAccess: 'None' }
}
resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: '${prefix}-vault'
  location: location
  properties: {
    tenantId: tenant().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enablePurgeProtection: true
    softDeleteRetentionInDays: 90
    publicNetworkAccess: 'Disabled'
    accessPolicies: []
  }
}
resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: '${prefix}-postgres'
  location: location
  sku: { name: 'Standard_D2s_v3', tier: 'GeneralPurpose' }
  properties: {
    version: '16'
    administratorLogin: postgresAdministratorLogin
    administratorLoginPassword: postgresAdministratorPassword
    storage: { storageSizeGB: 32 }
    backup: { backupRetentionDays: 14, geoRedundantBackup: 'Disabled' }
    network: { publicNetworkAccess: 'Disabled' }
    highAvailability: { mode: 'Disabled' }
  }
}
resource database 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: postgres
  name: 'workflow'
  properties: { charset: 'UTF8', collation: 'en_US.utf8' }
}
resource redis 'Microsoft.Cache/redis@2024-11-01' = {
  name: '${prefix}-redis'
  location: location
  properties: {
    sku: { name: 'Standard', family: 'C', capacity: 1 }
    enableNonSslPort: false
    minimumTlsVersion: '1.2'
    publicNetworkAccess: 'Disabled'
  }
}
resource apps 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${prefix}-apps'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
    workloadProfiles: [{ name: 'Consumption', workloadProfileType: 'Consumption' }]
  }
}
output blobAccountUrl string = storage.properties.primaryEndpoints.blob
output vaultUri string = vault.properties.vaultUri
output postgresHost string = postgres.properties.fullyQualifiedDomainName
output redisHost string = redis.properties.hostName
output containerEnvironmentId string = apps.id
