# VCOS production AWS environment (Phase 16)
# One module per region: VPC + EKS + RDS multi-AZ + replicas + S3.

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {source = "hashicorp/aws", version = "~> 5.0"}
    helm = {source = "hashicorp/helm", version = "~> 2.0"}
    kubernetes = {source = "hashicorp/kubernetes", version = "~> 2.0"}
  }
  backend "s3" {
    bucket         = "vcos-terraform-state"
    key            = "production/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "vcos-terraform-locks"
    encrypt        = true
  }
}

provider "aws" {region = var.region}

# ---- Networking: VPC with 3 AZs, public + private subnets
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  tags                 = {Name = "vcos-${var.region}"}
}

resource "aws_subnet" "private" {
  count             = 3
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.${count.index + 10}.0/24"
  availability_zone = "${var.region}${element(["a", "b", "c"], count.index)}"
  tags              = {Name = "vcos-private-${count.index}"}
}

resource "aws_subnet" "public" {
  count             = 3
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.${count.index + 20}.0/24"
  availability_zone = "${var.region}${element(["a", "b", "c"], count.index)}"
  tags              = {Name = "vcos-public-${count.index}"}
}

# ---- Database: primary multi-AZ + 2 read replicas (Phase 16.5, 16.20)
resource "aws_db_instance" "primary" {
  identifier              = "vcos-primary"
  engine                  = "postgres"
  engine_version          = "16.3"
  instance_class          = "db.r6g.xlarge"
  allocated_storage       = 200
  storage_encrypted       = true
  backup_retention_period = 30               # PITR window (Phase 16.20)
  backup_window           = "02:00-03:00"
  maintenance_window      = "sun:04:00-sun:05:00"
  multi_az                = true
  db_subnet_group_name    = aws_db_subnet_group.main.name
  vpc_security_group_ids  = [aws_security_group.db.id]
  deletion_protection     = true
  tags                    = {Name = "vcos-primary"}
}

resource "aws_db_instance" "replica" {
  count                = 2
  identifier           = "vcos-replica-${count.index}"
  replicate_source_db  = aws_db_instance.primary.identifier
  instance_class       = "db.r6g.large"
  multi_az             = false
  deletion_protection  = true
  tags                 = {Name = "vcos-replica-${count.index}"}
}

resource "aws_db_subnet_group" "main" {
  name       = "vcos-main"
  subnet_ids = aws_subnet.private[*].id
}

# ---- Object storage (Phase 16.17): backup vault + media buckets
resource "aws_s3_bucket" "vcos_assets" {
  bucket        = "vcos-assets-${var.region}"
  force_destroy = false
}

resource "aws_s3_bucket" "vcos_backups" {
  bucket        = "vcos-backups-${var.region}"
  force_destroy = false
}

resource "aws_s3_bucket_versioning" "backups" {
  bucket = aws_s3_bucket.vcos_backups.id
  versioning_configuration {status = "Enabled"}
}

# ---- EKS control plane + managed node groups
resource "aws_eks_cluster" "vcos" {
  name     = "vcos-${var.region}"
  role_arn = aws_iam_role.eks_cluster.arn
  vpc_config {
    subnet_ids = aws_subnet.private[*].id
  }
}

resource "aws_eks_node_group" "workers" {
  cluster_name    = aws_eks_cluster.vcos.name
  node_group_name = "vcos-workers"
  node_role_arn   = aws_iam_role.eks_nodes.arn
  subnet_ids      = aws_subnet.private[*].id
  scaling_config {
    desired_size = 3
    max_size     = 20          # Phase 16.22 autoscaling ceiling
    min_size     = 3
  }
  instance_types = ["m6i.xlarge"]
}
