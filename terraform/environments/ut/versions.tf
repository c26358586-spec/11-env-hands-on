# Copyright 2026 Ranamicus Technology LLC. All rights reserved.

terraform {
  required_version = "= 1.14.1"

  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "= 4.5.0"
    }
  }
}
