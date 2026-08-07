# Copyright 2026 Ranamicus Technology LLC. All rights reserved.

locals {
  resource_prefix = "ut-${replace(lower(var.environment_face_id), "_", "-")}"
  common_labels = {
    environment_pattern_id = "UT"
    environment_face_id    = var.environment_face_id
    test_run_id            = var.test_run_id
    issue_number           = var.issue_number
    workflow_run_id        = var.workflow_run_id
    workflow_run_attempt   = var.workflow_run_attempt
    repository             = var.repository
    managed_by             = "github-actions-pr-ci"
  }
}

resource "docker_network" "ut" {
  name = "${local.resource_prefix}-net"

  dynamic "labels" {
    for_each = local.common_labels
    content {
      label = labels.key
      value = labels.value
    }
  }
}

resource "docker_container" "target" {
  name     = "${local.resource_prefix}-target"
  image    = var.target_image_name
  command  = ["sleep", "infinity"]
  must_run = true

  networks_advanced {
    name = docker_network.ut.name
  }

  ports {
    internal = 80
    external = var.host_http_port
  }

  dynamic "labels" {
    for_each = local.common_labels
    content {
      label = labels.key
      value = labels.value
    }
  }
}
