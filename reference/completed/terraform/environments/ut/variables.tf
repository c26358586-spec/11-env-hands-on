# Copyright 2026 Ranamicus Technology LLC. All rights reserved.

variable "environment_face_id" {
  description = "Environment face identifier used for names, labels, inventory, and cleanup."
  type        = string
}

variable "target_image_name" {
  description = "Locally built Ubuntu 24.04 target image name."
  type        = string
}

variable "host_http_port" {
  description = "Host port mapped to target container port 80 for Nginx-proxied startup checks."
  type        = number
  default     = 18080
}

variable "test_run_id" {
  description = "PR CI Test run ID."
  type        = string
}

variable "issue_number" {
  description = "Linked GitHub Issue number."
  type        = string
}

variable "workflow_run_id" {
  description = "GitHub Actions workflow run ID."
  type        = string
}

variable "workflow_run_attempt" {
  description = "GitHub Actions workflow run attempt."
  type        = string
}

variable "repository" {
  description = "GitHub repository full name."
  type        = string
}
