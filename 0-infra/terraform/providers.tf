terraform {
  required_providers {
    tart = {
      source  = "cirruslabs/tart"
      version = "~> 1.0"
    }
  }
}

provider "tart" {}
