variable "collector_image" {
  description = "The image both jobs run: ghcr.io/protonicwave/gridcast-collector:<commit sha>."
  type        = string

  validation {
    condition     = can(regex("^ghcr\\.io/protonicwave/gridcast-collector:[0-9a-f]{40}$", var.collector_image))
    error_message = "Expected ghcr.io/protonicwave/gridcast-collector:<40-character commit sha>."
  }
}

variable "healthcheck_url" {
  description = "The healthchecks.io ping URL the collector calls once the regional forecast is stored."
  type        = string
  sensitive   = true

  validation {
    condition     = startswith(var.healthcheck_url, "https://")
    error_message = "Expected an https URL."
  }
}

variable "location" {
  description = "Azure region for every resource. Azure for Students allows few regions; Norway East offers both PostgreSQL B1ms and Container Apps jobs."
  type        = string
  default     = "norwayeast"
}
