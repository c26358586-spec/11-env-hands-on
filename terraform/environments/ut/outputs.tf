# Copyright 2026 Ranamicus Technology LLC. All rights reserved.

output "container_name" {
  description = "Target container name."
  value       = docker_container.target.name
}

output "network_name" {
  description = "UT Docker network name."
  value       = docker_network.ut.name
}

output "host_http_url" {
  description = "Runner-side URL for Nginx-proxied startup checks."
  value       = "http://127.0.0.1:${var.host_http_port}"
}

output "managed_label_filter" {
  description = "Docker CLI label filter for Lesson 5.4 cleanup and residue verification."
  value       = "label=test_run_id=${var.test_run_id}"
}

output "ansible_inventory" {
  description = "YAML inventory for Ansible Docker connection."
  value = yamlencode({
    all = {
      hosts = {
        ms1_target = {
          ansible_connection         = "community.docker.docker"
          ansible_host               = docker_container.target.name
          ansible_python_interpreter = "/usr/bin/python3"
          app_port                   = 8080
          nginx_port                 = 80
        }
      }
    }
  })
}
