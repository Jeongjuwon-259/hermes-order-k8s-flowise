resource "tart_vm" "node_1" {
  name      = "node-1"
  image     = var.vm_image
  cpu_count = var.node_cpu_count
  memory    = var.node_memory_mb
  disk_size = var.node_disk_gb

  run = true
}

resource "tart_vm" "node_2" {
  name      = "node-2"
  image     = var.vm_image
  cpu_count = var.node_cpu_count
  memory    = var.node_memory_mb
  disk_size = var.node_disk_gb

  run = true
}
