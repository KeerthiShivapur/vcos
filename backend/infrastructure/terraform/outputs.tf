output "region" {
  description = "Deployed region (Phase 16.3 topology)."
  value       = var.region
}

output "eks_cluster_endpoint" {
  value = aws_eks_cluster.vcos.endpoint
}

output "database_primary_address" {
  value = aws_db_instance.primary.address
}

output "database_replica_addresses" {
  value = aws_db_instance.replica[*].address
}

output "backup_bucket" {
  value = aws_s3_bucket.vcos_backups.id
}

output "assets_bucket" {
  value = aws_s3_bucket.vcos_assets.id
}
