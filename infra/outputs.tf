output "api_url" {
  description = "The API's public origin, which the site is built with."
  value       = "https://${azurerm_container_app.api.ingress[0].fqdn}"
}

data "azurerm_client_config" "current" {}

output "deploy_client_id" {
  description = "The client ID CI signs in to Azure with, as the deploy identity."
  value       = azurerm_user_assigned_identity.deploy.client_id
}

output "tenant_id" {
  description = "The Microsoft Entra tenant CI signs in to."
  value       = azurerm_user_assigned_identity.deploy.tenant_id
}

output "subscription_id" {
  description = "The subscription that holds the API app."
  value       = data.azurerm_client_config.current.subscription_id
}
