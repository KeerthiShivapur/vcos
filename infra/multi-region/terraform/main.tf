# Multi-Region Infrastructure - Main Terraform Configuration
# Deploys VCOS infrastructure across multiple AWS regions

# =============================================================================
# VPC and Networking (per region)
# =============================================================================

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"
  
  for_each = var.regions
  
  providers = {
    aws = aws[each.value.provider_alias]
  }
  
  name                       = "vcos-${each.key}"
  cidr_block                 = each.value.vpc_cidr
  enable_dns_hostnames       = true
  enable_dns_support         = true
  enable_classiclink         = false
  enable_classiclink_dns_support = false
  
  # Subnets
  public_subnets             = [for i, az in data.aws_availability_zones[each.key].names : cidrsubnet(each.value.vpc_cidr, 4, i)]
  private_subnets            = [for i, az in data.aws_availability_zones[each.key].names : cidrsubnet(each.value.vpc_cidr, 4, i + 10)]
  database_subnets           = [for i, az in data.aws_availability_zones[each.key].names : cidrsubnet(each.value.vpc_cidr, 4, i + 20)]
  
  # NAT Gateway
  enable_nat_gateway         = true
  single_nat_gateway         = false
  one_nat_gateway_per_az     = true
  enable_dns_hostnames       = true
  
  # VPC Endpoints
  vpc_endpoints = {
    s3 = {
      service             = "com.amazonaws.${aws.region}.s3"
      vpc_endpoint_type   = "Gateway"
      route_table_ids     = module.vpc[each.key].private_route_table_ids
    }
    dynamodb = {
      service             = "com.amazonaws.${aws.region}.dynamodb"
      vpc_endpoint_type   = "Gateway"
      route_table_ids     = module.vpc[each.key].private_route_table_ids
    }
    ecr_api = {
      service             = "com.amazonaws.${aws.region}.ecr.api"
      vpc_endpoint_type   = "Interface"
      private_dns_enabled = true
      subnet_ids          = module.vpc[each.key].private_subnets
      security_group_ids  = [aws_security_group.vpc_endpoint[each.key].id]
    }
    ecr_dkr = {
      service             = "com.amazonaws.${aws.region}.ecr.dkr"
      vpc_endpoint_type   = "Interface"
      private_dns_enabled = true
      subnet_ids          = module.vpc[each.key].private_subnets
      security_group_ids  = [aws_security_group.vpc_endpoint[each.key].id]
    }
    logs = {
      service             = "com.amazonaws.${aws.region}.logs"
      vpc_endpoint_type   = "Interface"
      private_dns_enabled = true
      subnet_ids          = module.vpc[each.key].private_subnets
      security_group_ids  = [aws_security_group.vpc_endpoint[each.key].id]
    }
    monitoring = {
      service             = "com.amazonaws.${aws.region}.monitoring"
      vpc_endpoint_type   = "Interface"
      private_dns_enabled = true
      subnet_ids          = module.vpc[each.key].private_subnets
      security_group_ids  = [aws_security_group.vpc_endpoint[each.key].id]
    }
    ecs = {
      service             = "com.amazonaws.${aws.region}.ecs"
      vpc_endpoint_type   = "Interface"
      private_dns_enabled = true
      subnet_ids          = module.vpc[each.key].private_subnets
      security_group_ids  = [aws_security_group.vpc_endpoint[each.key].id]
    }
    ecs_agent = {
      service             = "com.amazonaws.${aws.region}.ecs-agent"
      vpc_endpoint_type   = "Interface"
      private_dns_enabled = true
      subnet_ids          = module.vpc[each.key].private_subnets
      security_group_ids  = [aws_security_group.vpc_endpoint[each.key].id]
    }
    elasticloadbalancing = {
      service             = "com.amazonaws.${aws.region}.elasticloadbalancing"
      vpc_endpoint_type   = "Interface"
      private_dns_enabled = true
      subnet_ids          = module.vpc[each.key].private_subnets
      security_group_ids  = [aws_security_group.vpc_endpoint[each.key].id]
    }
    cloudwatch = {
      service             = "com.amazonaws.${aws.region}.cloudwatch"
      vpc_endpoint_type   = "Interface"
      private_dns_enabled = true
      subnet_ids          = module.vpc[each.key].private_subnets
      security_group_ids  = [aws_security_group.vpc_endpoint[each.key].id]
    }
    autoscaling = {
      service             = "com.amazonaws.${aws.region}.autoscaling"
      vpc_endpoint_type   = "Interface"
      private_dns_enabled = true
      subnet_ids          = module.vpc[each.key].private_subnets
      security_group_ids  = [aws_security_group.vpc_endpoint[each.key].id]
    }
    cloudformation = {
      service             = "com.amazonaws.${aws.region}.cloudformation"
      vpc_endpoint_type   = "Interface"
      private_dns_enabled = true
      subnet_ids          = module.vpc[each.key].private_subnets
      security_group_ids  = [aws_security_group.vpc_endpoint[each.key].id]
    }
    secretsmanager = {
      service             = "com.amazonaws.${aws.region}.secretsmanager"
      vpc_endpoint_type   = "Interface"
      private_dns_enabled = true
      subnet_ids          = module.vpc[each.key].private_subnets
      security_group_ids  = [aws_security_group.vpc_endpoint[each.key].id]
    }
    kms = {
      service             = "com.amazonaws.${aws.region}.kms"
      vpc_endpoint_type   = "Interface"
      private_dns_enabled = true
      subnet_ids          = module.vpc[each.key].private_subnets
      security_group_ids  = [aws_security_group.vpc_endpoint[each.key].id]
    }
    sns = {
      service             = "com.amazonaws.${aws.region}.sns"
      vpc_endpoint_type   = "Interface"
      private_dns_enabled = true
      subnet_ids          = module.vpc[each.key].private_subnets
      security_group_ids  = [aws_security_group.vpc_endpoint[each.key].id]
    }
    sqs = {
      service             = "com.amazonaws.${aws.region}.sqs"
      vpc_endpoint_type   = "Interface"
      private_dns_enabled = true
      subnet_ids          = module.vpc[each.key].private_subnets
      security_group_ids  = [aws_security_group.vpc_endpoint[each.key].id]
    }
  }
  
  tags = {
    Name        = "vcos-${each.key}"
    Project     = "vcos"
    Environment = "production"
    Region      = each.key
    ManagedBy   = "terraform"
  }
}

# =============================================================================
# EKS Clusters (per region)
# =============================================================================

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 19.0"
  
  for_each = var.regions
  
  providers = {
    aws = aws[each.value.provider_alias]
    kubernetes = kubernetes[each.value.provider_alias]
    helm = helm[each.value.provider_alias]
  }
  
  cluster_name    = "vcos-${each.key}"
  cluster_version = each.value.k8s_version
  
  vpc_id                         = module.vpc[each.key].vpc_id
  subnet_ids                     = module.vpc[each.key].private_subnets
  cluster_endpoint_public_access = true
  cluster_endpoint_private_access = true
  
  # Cluster security group
  cluster_security_group_ids = [aws_security_group.eks_cluster[each.key].id]
  
  # Encryption
  enable_irsa = true
  
  # Cluster encryption
  cluster_encryption_config = [{
    provider_key_arn = aws_kms_key.eks_secrets[each.key].arn
    resources        = ["secrets"]
  }]
  
  # Logging
  cluster_log_retention_period = 30
  cluster_log_types = ["api", "audit", "authenticator", "controllerManager", "scheduler"]
  
  # Node groups
  eks_managed_node_groups = {
    general = {
      name           = "general"
      instance_types = [each.value.instance_types.general]
      capacity_type  = "ON_DEMAND"
      
      scaling_config = {
        min_size     = each.value.node_group_sizes.general.min_size
        max_size     = each.value.node_group_sizes.general.max_size
        desired_size = each.value.node_group_sizes.general.desired_size
      }
      
      instance_profile = aws_iam_instance_profile.eks_node[each.key].name
      
      labels = {
        "node-type" = "general"
        "region"    = each.key
      }
      
      taints = [{
        key    = "dedicated"
        value  = "general"
        effect = "NO_SCHEDULE"
      }]
      
      labels = {
        "node-type" = "general"
      }
      
      update_config = {
        max_unavailable_percentage = 25
      }
    }
    
    compute = {
      name           = "compute"
      instance_types = [each.value.instance_types.compute]
      capacity_type  = "ON_DEMAND"
      
      scaling_config = {
        min_size     = each.value.node_group_sizes.compute.min_size
        max_size     = each.value.node_group_sizes.compute.max_size
        desired_size = each.value.node_group_sizes.compute.desired_size
      }
      
      instance_profile = aws_iam_instance_profile.eks_node[each.key].name
      
      labels = {
        "node-type" = "compute"
        "region"    = each.key
      }
      
      taints = [{
        key    = "dedicated"
        value  = "compute"
        effect = "NO_SCHEDULE"
      }]
      
      update_config = {
        max_unavailable_percentage = 25
      }
    }
    
    memory = {
      name           = "memory"
      instance_types = [each.value.instance_types.memory]
      capacity_type  = "ON_DEMAND"
      
      scaling_config = {
        min_size     = each.value.node_group_sizes.memory.min_size
        max_size     = each.value.node_group_sizes.memory.max_size
        desired_size = each.value.node_group_sizes.memory.desired_size
      }
      
      instance_profile = aws_iam_instance_profile.eks_node[each.key].name
      
      labels = {
        "node-type" = "memory"
        "region"    = each.key
      }
      
      taints = [{
        key    = "dedicated"
        value  = "memory"
        effect = "NO_SCHEDULE"
      }]
      
      update_config = {
        max_unavailable_percentage = 25
      }
    }
  }
  
  # Add-ons
  enable_irsa = true
  
  cluster_addons = {
    vpc-cni = {
      most_recent = true
      configuration_values = {
        env = {
          AWS_VPC_K8S_CNI_EXTERNALSNAT = "true"
          AWS_VPC_K8S_CNI_CUSTOM_NETWORK_CFG = "true"
        }
      }
    }
    coredns = {
      most_recent = true
      configuration_values = {
        replicaCount = 2
      }
    }
    kube-proxy = {
      most_recent = true
    }
    aws-ebs-csi-driver = {
      most_recent = true
    }
    aws-efs-csi-driver = {
      most_recent = true
    }
    cert-manager = {
      most_recent = true
      configuration_values = {
        installCRDs = true
        extraArgs = [
          "--dns01-recursive-nameservers-only",
          "--dns01-recursive-nameservers=8.8.8.8:53,1.1.1.1:53"
        ]
      }
    }
    external-dns = {
      most_recent = true
      configuration_values = {
        provider = "aws"
        sources = ["service", "ingress"]
        domainFilters = ["vcos.io"]
        policy = "upsert-only"
      }
    }
    aws-load-balancer-controller = {
      most_recent = true
      configuration_values = {
        clusterName = "vcos-${each.key}"
        region = data.aws_eks_cluster[each.key].region
        vpcId = module.vpc[each.key].vpc_id
        serviceAccount = {
          create = true
          name = "aws-load-balancer-controller"
          annotations = {
            "eks.amazonaws.com/role-arn" = aws_iam_role.alb_controller[each.key].arn
          }
        }
      }
    }
    metrics-server = {
      most_recent = true
      configuration_values = {
        args = [
          "--kubelet-insecure-tls",
          "--kubelet-preferred-address-types=InternalIP,ExternalIP,Hostname"
        ]
      }
    }
    cluster-autoscaler = {
      most_recent = true
      configuration_values = {
        autoDiscovery = {
          clusterName = "vcos-${each.key}"
        }
        awsRegion = data.aws_eks_cluster[each.key].region
        scaleDownUtilizationThreshold = 0.5
        scaleDownDelayAfterAdd = "10m"
        scaleDownDelayAfterDelete = "10m"
        scaleDownDelayAfterFailure = "3m"
        scaleDownUnneededTime = "10m"
        scaleDownUnreadyTime = "20m"
      }
    }
  }
  
  tags = {
    Name        = "vcos-${each.key}"
    Project     = "vcos"
    Environment = "production"
    Region      = each.key
    ManagedBy   = "terraform"
  }
}

# =============================================================================
# RDS PostgreSQL (per region)
# =============================================================================

module "rds" {
  source  = "terraform-aws-modules/rds/aws"
  version = "~> 6.0"
  
  for_each = var.regions
  
  providers = {
    aws = aws[each.value.provider_alias]
  }
  
  identifier = "vcos-${each.key}"
  
  engine               = "postgres"
  engine_version       = "15.4"
  instance_class       = each.value.postgres_instance_class
  
  allocated_storage     = 500
  max_allocated_storage = 1000
  storage_encrypted     = true
  storage_type          = "gp3"
  iops                  = 10000
  
  db_name  = "vcos"
  username = "vcos"
  password = var.postgres_password
  port     = 5432
  
  vpc_id            = module.vpc[each.key].vpc_id
  db_subnet_group_name = module.vpc[each.key].database_subnet_group_name
  vpc_security_group_ids = [aws_security_group.rds[each.key].id]
  
  # Multi-AZ
  multi_az               = true
  availability_zone      = data.aws_availability_zones[each.key].names[0]
  
  # Backup
  backup_retention_period = 30
  backup_window          = "03:00-04:00"
  maintenance_window     = "sun:04:00-sun:05:00"
  copy_tags_to_snapshot  = true
  
  # Monitoring
  monitoring_interval = 60
  performance_insights_enabled = true
  performance_insights_retention_period = 7
  
  # Encryption
  storage_encrypted = true
  kms_key_id = aws_kms_key.rds[each.key].arn
  
  # Deletion protection
  deletion_protection = true
  
  # Parameter group
  parameter_group_name = aws_db_parameter_group.postgres[each.key].name
  
  tags = {
    Name        = "vcos-${each.key}-postgres"
    Project     = "vcos"
    Environment = "production"
    Region      = each.key
    ManagedBy   = "terraform"
  }
}

# =============================================================================
# ElastiCache Redis (per region)
# =============================================================================

module "elasticache" {
  source  = "terraform-aws-modules/elasticache/aws"
  version = "~> 2.0"
  
  for_each = var.regions
  
  providers = {
    aws = aws[each.value.provider_alias]
  }
  
  cluster_id = "vcos-${each.key}"
  
  engine               = "redis"
  engine_version       = "7.1"
  node_type            = each.value.redis_node_type
  num_cache_nodes      = 3
  parameter_group_name = aws_elasticache_parameter_group.redis[each.key].name
  
  port                 = 6379
  automatic_failover_enabled = true
  multi_az_enabled     = true
  
  # Security
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  auth_token_enabled         = true
  auth_token                 = var.redis_password
  
  # Network
  subnet_group_name = aws_elasticache_subnet_group.redis[each.key].name
  security_group_ids = [aws_security_group.elasticache[each.key].id]
  
  # Backup
  snapshot_retention_limit = 7
  snapshot_window          = "03:00-04:00"
  maintenance_window       = "sun:05:00-sun:07:00"
  
  # Logging
  log_delivery_config = {
    destination_type = "cloudwatch-logs"
    log_type         = "slow-log"
    destination_details = {
      cloudwatch_logs = {
        log_group = "/aws/elasticache/vcos-${each.key}/redis"
      }
    }
  }
  
  tags = {
    Name        = "vcos-${each.key}-redis"
    Project     = "vcos"
    Environment = "production"
    Region      = each.key
    ManagedBy   = "terraform"
  }
}

# =============================================================================
# S3 Buckets (per region)
# =============================================================================

resource "aws_s3_bucket" "recordings" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  bucket = "${each.value.s3_bucket_prefix}-recordings"
  
  versioning {
    enabled = true
  }
  
  server_side_encryption_configuration {
    rule {
      apply_server_side_encryption_by_default {
        sse_algorithm = "AES256"
      }
    }
  }
  
  versioning {
    enabled = true
  }
  
  lifecycle_rule {
    enabled = true
    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }
    transition {
      days          = 90
      storage_class = "GLACIER"
    }
    transition {
      days          = 365
      storage_class = "DEEP_ARCHIVE"
    }
  }
  
  replication_configuration {
    role = aws_iam_role.s3_replication[each.key].arn
    
    rule {
      id     = "replicate-to-other-regions"
      status = "Enabled"
      priority = 1
      
      destination {
        bucket        = "arn:aws:s3:::vcos-${lookup(var.regions, "eu-west-1", {s3_bucket_prefix = "vcos-eu-west-1"}).s3_bucket_prefix}-recordings"
        storage_class = "STANDARD_IA"
        account_id    = data.aws_caller_identity.current.account_id
      }
      
      destination {
        bucket        = "arn:aws:s3:::vcos-recordings-ap-southeast-1"
        storage_class = "STANDARD_IA"
        account_id    = data.aws_caller_identity.current.account_id
      }
    }
  }
  
  tags = {
    Name        = "${each.value.s3_bucket_prefix}-recordings"
    Project     = "vcos"
    Environment = "production"
    Region      = each.key
    ManagedBy   = "terraform"
  }
}

resource "aws_s3_bucket" "assets" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  bucket = "${each.value.s3_bucket_prefix}-assets"
  
  versioning {
    enabled = true
  }
  
  server_side_encryption_configuration {
    rule {
      apply_server_side_encryption_by_default {
        sse_algorithm = "AES256"
      }
    }
  }
  
  lifecycle_rule {
    enabled = true
    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }
    transition {
      days          = 365
      storage_class = "GLACIER"
    }
  }
  
  replication_configuration {
    role = aws_iam_role.s3_replication[each.key].arn
    
    rule {
      id     = "replicate-assets"
      status = "Enabled"
      priority = 1
      
      destination {
        bucket        = "arn:aws:s3:::vcos-assets-eu-west-1"
        storage_class = "STANDARD_IA"
        account_id    = data.aws_caller_identity.current.account_id
      }
      
      destination {
        bucket        = "arn:aws:s3:::vcos-assets-ap-southeast-1"
        storage_class = "STANDARD_IA"
        account_id    = data.aws_caller_identity.current.account_id
      }
    }
  }
  
  tags = {
    Name        = "${each.value.s3_bucket_prefix}-assets"
    Project     = "vcos"
    Environment = "production"
    Region      = each.key
    ManagedBy   = "terraform"
  }
}

resource "aws_s3_bucket" "backups" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  bucket = "${each.value.s3_bucket_prefix}-backups"
  
  versioning {
    enabled = true
  }
  
  server_side_encryption_configuration {
    rule {
      apply_server_side_encryption_by_default {
        sse_algorithm = "AES256"
      }
    }
  }
  
  lifecycle_rule {
    enabled = true
    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }
    transition {
      days          = 90
      storage_class = "GLACIER"
    }
    expiration {
      days = 2555 # 7 years
    }
  }
  
  tags = {
    Name        = "${each.value.s3_bucket_prefix}-backups"
    Project     = "vcos"
    Environment = "production"
    Region      = each.key
    ManagedBy   = "terraform"
  }
}