# The collector's Azure resources: a scheduled Container Apps job writing to a
# PostgreSQL flexible server, and a manually started job that applies migrations.

terraform {
  required_version = "~> 1.17"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 5.14"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.9"
    }
  }

  # Created once by the commands in README.md. The state holds the database
  # passwords, so it lives in Azure rather than on one machine.
  backend "azurerm" {
    resource_group_name  = "rg-gridcast-tfstate"
    storage_account_name = "stgridcasttfstate"
    container_name       = "tfstate"
    key                  = "gridcast.tfstate"
  }
}

provider "azurerm" {
  features {}
  # The resource providers the jobs and the server need are registered once by
  # hand: a student subscription may refuse to register the others.
  resource_provider_registrations = "none"
}

locals {
  database_name = "gridcast"
  database_host = azurerm_postgresql_flexible_server.archive.fqdn
  # verify-full checks the server certificate against the image's system roots.
  tls_parameters = "sslmode=verify-full&sslrootcert=system"
  admin_url      = "postgresql://${azurerm_postgresql_flexible_server.archive.administrator_login}:${random_password.admin.result}@${local.database_host}:5432/${local.database_name}?${local.tls_parameters}"
  collector_url  = "postgresql://gridcast_collector:${random_password.collector.result}@${local.database_host}:5432/${local.database_name}?${local.tls_parameters}"
}

resource "azurerm_resource_group" "gridcast" {
  name     = "rg-gridcast"
  location = var.location
}

resource "azurerm_log_analytics_workspace" "gridcast" {
  name                = "log-gridcast"
  location            = azurerm_resource_group.gridcast.location
  resource_group_name = azurerm_resource_group.gridcast.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  # Caps the ingestion bill if a job starts logging in a loop.
  daily_quota_gb = 0.5
}

resource "azurerm_container_app_environment" "gridcast" {
  name                       = "cae-gridcast"
  location                   = azurerm_resource_group.gridcast.location
  resource_group_name        = azurerm_resource_group.gridcast.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.gridcast.id
}

# Server names are global DNS names, so a suffix keeps this one unique.
resource "random_string" "server_suffix" {
  length  = 6
  upper   = false
  special = false
}

# Letters and digits only, so the passwords need no escaping in connection URLs.
resource "random_password" "admin" {
  length  = 32
  special = false
}

resource "random_password" "collector" {
  length  = 32
  special = false
}

resource "azurerm_postgresql_flexible_server" "archive" {
  name                          = "psql-gridcast-${random_string.server_suffix.result}"
  location                      = azurerm_resource_group.gridcast.location
  resource_group_name           = azurerm_resource_group.gridcast.name
  version                       = "17"
  sku_name                      = "B_Standard_B1ms"
  storage_mb                    = 32768
  backup_retention_days         = 7
  administrator_login           = "gridcast_admin"
  administrator_password        = random_password.admin.result
  public_network_access_enabled = true

  lifecycle {
    # Azure picks the availability zone, and it cannot be changed afterwards.
    ignore_changes = [zone]
  }
}

resource "azurerm_postgresql_flexible_server_database" "archive" {
  name      = local.database_name
  server_id = azurerm_postgresql_flexible_server.archive.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

# The range 0.0.0.0 to 0.0.0.0 is Azure's notation for services inside Azure,
# which is where the jobs run. Nothing outside Azure can reach the server.
resource "azurerm_postgresql_flexible_server_firewall_rule" "azure_services" {
  name             = "allow-azure-services"
  server_id        = azurerm_postgresql_flexible_server.archive.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

resource "azurerm_container_app_job" "collect" {
  name                         = "caj-gridcast-collect"
  location                     = azurerm_resource_group.gridcast.location
  resource_group_name          = azurerm_resource_group.gridcast.name
  container_app_environment_id = azurerm_container_app_environment.gridcast.id
  # Three calls of at most 75 s each, retries included, fit inside this limit.
  replica_timeout_in_seconds = 240
  # A failed run is not repeated: the next scheduled run is 30 minutes away.
  replica_retry_limit = 0

  schedule_trigger_config {
    # UTC. Five minutes after each half hour, once NESO's update has landed.
    cron_expression          = "5,35 * * * *"
    parallelism              = 1
    replica_completion_count = 1
  }

  secret {
    name  = "database-url"
    value = local.collector_url
  }

  secret {
    name  = "healthcheck-url"
    value = var.healthcheck_url
  }

  template {
    container {
      name   = "collect"
      image  = var.collector_image
      cpu    = 0.25
      memory = "0.5Gi"

      env {
        name        = "GRIDCAST_DATABASE_URL"
        secret_name = "database-url"
      }

      env {
        name        = "GRIDCAST_HEALTHCHECK_URL"
        secret_name = "healthcheck-url"
      }
    }
  }
}

resource "azurerm_container_app_job" "migrate" {
  name                         = "caj-gridcast-migrate"
  location                     = azurerm_resource_group.gridcast.location
  resource_group_name          = azurerm_resource_group.gridcast.name
  container_app_environment_id = azurerm_container_app_environment.gridcast.id
  replica_timeout_in_seconds   = 120
  replica_retry_limit          = 0

  manual_trigger_config {
    parallelism              = 1
    replica_completion_count = 1
  }

  secret {
    name  = "admin-database-url"
    value = local.admin_url
  }

  secret {
    name  = "collector-password"
    value = random_password.collector.result
  }

  template {
    container {
      name    = "migrate"
      image   = var.collector_image
      command = ["gridcast-migrate"]
      cpu     = 0.25
      memory  = "0.5Gi"

      env {
        name        = "GRIDCAST_DATABASE_URL"
        secret_name = "admin-database-url"
      }

      env {
        name        = "GRIDCAST_COLLECTOR_PASSWORD"
        secret_name = "collector-password"
      }
    }
  }
}
