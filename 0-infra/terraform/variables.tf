variable "vm_image" {
  description = "Tart VM base image"
  type        = string
  default     = "ghcr.io/cirruslabs/ubuntu:24.04"
}

variable "node_cpu_count" {
  description = "vCPU count per node (control-plane and worker share the same spec)"
  type        = number
  default     = 4
}

variable "node_memory_mb" {
  description = "Memory per node in MB"
  type        = number
  default     = 15360
}

variable "node_disk_gb" {
  description = "Disk size per node in GB"
  type        = number
  default     = 100
}
