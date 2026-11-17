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
    condition     = can(regex("^https://[^/]+/", var.healthcheck_url))
    error_message = "Expected an https URL with a host."
  }
}
