output "api_url" {
  description = "The API's public origin, which the site is built with."
  value       = "https://${azurerm_container_app.api.ingress[0].fqdn}"
}
