# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
# Applies the HYDRA Kubernetes manifests to an existing cluster (HYDRA CLUSTER profile).
terraform {
  required_providers {
    kubernetes = { source = "hashicorp/kubernetes", version = ">= 2.30" }
  }
}

variable "kubeconfig" {
  type    = string
  default = "~/.kube/config"
}

provider "kubernetes" {
  config_path = var.kubeconfig
}

locals {
  files = fileset("${path.module}/../kubernetes", "*.yaml")
  docs = flatten([
    for f in local.files : [
      for d in split("\n---\n", file("${path.module}/../kubernetes/${f}")) :
      yamldecode(d) if length(regexall("(?m)^[a-zA-Z]", d)) > 0
    ]
  ])
}

resource "kubernetes_manifest" "hydra" {
  for_each = { for d in local.docs : "${d.kind}/${try(d.metadata.namespace, "_")}/${d.metadata.name}" => d }
  manifest = each.value
}
