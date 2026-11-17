output "resource_group" {
  value = azurerm_resource_group.gridcast.name
}

output "database_host" {
  value = local.database_host
}

output "collect_job" {
  value = azurerm_container_app_job.collect.name
}

output "migrate_job" {
  value = azurerm_container_app_job.migrate.name
}
