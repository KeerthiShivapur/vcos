# Security Resources - Security Groups, IAM, KMS

# =============================================================================
# KMS Keys (per region)
# =============================================================================

resource "aws_kms_key" "eks_secrets" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  description             = "EKS secrets encryption for vcos-${each.key}"
  deletion_window_in_days = 30
  key_usage               = "ENCRYPT_DECRYPT"
  customer_master_key_spec = "SYMMETRIC_DEFAULT"
  deletion_window_in_days = 10
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "Allow administration of the key"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action = [
          "kms:*"
        ]
        Resource = "*"
      },
      {
        Sid    = "Allow EKS to use the key"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/eks-cluster-role"
        }
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:DescribeKey"
        ]
        Resource = "*"
      }
    ]
  }
  
  tags = {
    Name        = "vcos-${each.key}-eks-secrets"
    Project     = "vcos"
    Environment = "production"
    Region      = each.key
    ManagedBy   = "terraform"
  }
}

resource "aws_kms_key" "rds" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  description             = "RDS encryption for vcos-${each.key}"
  deletion_window_in_days = 30
  key_usage               = "ENCRYPT_DECRYPT"
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "Allow administration of the key"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action = ["kms:*"]
        Resource = "*"
      },
      {
        Sid    = "Allow RDS to use the key"
        Effect = "Allow"
        Principal = {
          Service = "rds.amazonaws.com"
        }
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:DescribeKey"
        ]
        Resource = "*"
      }
    ]
  })
  
  tags = {
    Name        = "vcos-${each.key}-rds"
    Project     = "vcos"
    Environment = "production"
    Region      = each.key
    ManagedBy   = "terraform"
  }
}

resource "aws_kms_key" "s3_replication" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  description             = "S3 replication encryption for vcos-${each.key}"
  deletion_window_in_days = 30
  key_usage               = "ENCRYPT_DECRYPT"
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "Allow administration of the key"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action = ["kms:*"]
        Resource = "*"
      },
      {
        Sid    = "Allow S3 to use the key"
        Effect = "Allow"
        Principal = {
          Service = "s3.amazonaws.com"
        }
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:DescribeKey"
        ]
        Resource = "*"
      }
    ]
  })
  
  tags = {
    Name        = "vcos-${each.key}-s3-replication"
    Project     = "vcos"
    Environment = "production"
    Region      = each.key
    ManagedBy   = "terraform"
  }
}

resource "aws_kms_alias" "eks_secrets" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  name          = "alias/vcos-${each.key}-eks-secrets"
  target_key_id = aws_kms_key.eks_secrets[each.key].id
}

resource "aws_kms_alias" "rds" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  name          = "alias/vcos-${each.key}-rds"
  target_key_id = aws_kms_key.rds[each.key].id
}

resource "aws_kms_alias" "s3_replication" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  name          = "alias/vcos-${each.key}-s3-replication"
  target_key_id = aws_kms_key.s3_replication[each.key].id
}

# =============================================================================
# Security Groups
# =============================================================================

resource "aws_security_group" "eks_cluster" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  name        = "vcos-${each.key}-eks-cluster"
  description = "Security group for EKS cluster control plane"
  vpc_id      = module.vpc[each.key].vpc_id
  
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Kubernetes API"
  }
  
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  tags = {
    Name        = "vcos-${each.key}-eks-cluster"
    Project     = "vcos"
    Environment = "production"
    Region      = each.key
  }
}

resource "aws_security_group" "eks_node" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  name        = "vcos-${each.key}-eks-node"
  description = "Security group for EKS worker nodes"
  vpc_id      = module.vpc[each.key].vpc_id
  
  # Allow all traffic within the VPC for node-to-node communication
  ingress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    self        = true
    description = "Node to node communication"
  }
  
  # Allow pods to communicate with each other
  ingress {
    from_port   = 1025
    to_port     = 65535
    protocol    = "tcp"
    self        = true
    description = "Pod communication"
  }
  
  # Allow LiveKit UDP ports
  ingress {
    from_port   = 50000
    to_port     = 60000
    protocol    = "udp"
    self        = true
    description = "LiveKit RTC UDP"
  }
  
  # Allow metrics
  ingress {
    from_port   = 9090
    to_port     = 9090
    protocol    = "tcp"
    cidr_blocks = [module.vpc[each.key].vpc_cidr_block]
    description = "Prometheus metrics"
  }
  
  # Allow health checks
  ingress {
    from_port   = 7880
    to_port     = 7880
    protocol    = "tcp"
    cidr_blocks = [module.vpc[each.key].vpc_cidr_block]
    description = "LiveKit health"
  }
  
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  tags = {
    Name        = "vcos-${each.key}-eks-node"
    Project     = "vcos"
    Environment = "production"
    Region      = each.key
  }
}

resource "aws_security_group" "rds" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  name        = "vcos-${each.key}-rds"
  description = "Security group for RDS PostgreSQL"
  vpc_id      = module.vpc[each.key].vpc_id
  
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.eks_node[each.key].id]
    description     = "PostgreSQL from EKS nodes"
  }
  
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  tags = {
    Name        = "vcos-${each.key}-rds"
    Project     = "vcos"
    Environment = "production"
    Region      = each.key
  }
}

resource "aws_security_group" "elasticache" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  name        = "vcos-${each.key}-elasticache"
  description = "Security group for ElastiCache Redis"
  vpc_id      = module.vpc[each.key].vpc_id
  
  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.eks_node[each.key].id]
    description     = "Redis from EKS nodes"
  }
  
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  tags = {
    Name        = "vcos-${each.key}-elasticache"
    Project     = "vcos"
    Environment = "production"
    Region      = each.key
  }
}

resource "aws_security_group" "alb_controller" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  name        = "vcos-${each.key}-alb-controller"
  description = "Security group for AWS Load Balancer Controller"
  vpc_id      = module.vpc[each.key].vpc_id
  
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTPS"
  }
  
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTP"
  }
  
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  tags = {
    Name        = "vcos-${each.key}-alb-controller"
    Project     = "vcos"
    Environment = "production"
    Region      = each.key
  }
}

resource "aws_security_group" "vpc_endpoint" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  name        = "vcos-${each.key}-vpc-endpoint"
  description = "Security group for VPC endpoints"
  vpc_id      = module.vpc[each.key].vpc_id
  
  ingress {
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [aws_security_group.eks_node[each.key].id]
    description     = "HTTPS for VPC endpoints"
  }
  
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  tags = {
    Name        = "vcos-${each.key}-vpc-endpoint"
    Project     = "vcos"
    Environment = "production"
    Region      = each.key
  }
}

# =============================================================================
# IAM Roles and Policies
# =============================================================================

resource "aws_iam_role" "eks_cluster" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  name = "vcos-${each.key}-eks-cluster-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "eks.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  }
  
  managed_policy_arns = [
    "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy",
    "arn:aws:iam::aws:policy/AmazonEKSVPCResourceController"
  ]
  
  tags = {
    Name        = "vcos-${each.key}-eks-cluster-role"
    Project     = "vcos"
    Environment = "production"
    Region      = each.key
  }
}

resource "aws_iam_role" "eks_node" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  name = "vcos-${each.key}-eks-node-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  }
  
  managed_policy_arns = [
    "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy",
    "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy",
    "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
    "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
  ]
  
  inline_policy = {
    name = "vcos-node-policy"
    policy = jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Effect = "Allow"
          Action = [
            "s3:GetObject",
            "s3:PutObject",
            "s3:DeleteObject",
            "s3:ListBucket"
          ]
          Resource = [
            "arn:aws:s3:::vcos-${each.key}-*",
            "arn:aws:s3:::vcos-${each.key}-*/*"
          ]
        },
        {
          Effect = "Allow"
          Action = [
            "kms:Encrypt",
            "kms:Decrypt",
            "kms:ReEncrypt*",
            "kms:GenerateDataKey*",
            "kms:DescribeKey"
          ]
          Resource = [
            aws_kms_key.eks_secrets[each.key].arn,
            aws_kms_key.s3_replication[each.key].arn
          ]
        },
        {
          Effect = "Allow"
          Action = [
            "secretsmanager:GetSecretValue",
            "secretsmanager:DescribeSecret"
          ]
          Resource = [
            "arn:aws:secretsmanager:${aws[each.value.provider_alias].region}:${data.aws_caller_identity.current.account_id}:secret:vcos/*"
          ]
        }
      ]
    })
  
  tags = {
    Name        = "vcos-${each.key}-eks-node-role"
    Project     = "vcos"
    Environment = "production"
    Region      = each.key
  }
}

resource "aws_iam_instance_profile" "eks_node" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  name = "vcos-${each.key}-eks-node-profile"
  role = aws_iam_role.eks_node[each.key].name
}

resource "aws_iam_role" "alb_controller" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  name = "vcos-${each.key}-alb-controller-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/${data.aws_eks_cluster[each.key].oidc_provider_arn}"
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${replace(data.aws_eks_cluster[each.key].oidc_provider_arn, "arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/", "")}:sub" = "system:serviceaccount:kube-system:aws-load-balancer-controller"
        }
      }
    }]
  })
  
  inline_policy = {
    name = "alb-controller-policy"
    policy = jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Effect = "Allow"
          Action = [
            "iam:CreateServiceLinkedRole",
            "ec2:DescribeAccountAttributes",
            "ec2:DescribeAddresses",
            "ec2:DescribeAvailabilityZones",
            "ec2:DescribeInternetGateways",
            "ec2:DescribeVpcs",
            "ec2:DescribeSubnets",
            "ec2:DescribeSecurityGroups",
            "ec2:DescribeInstances",
            "ec2:DescribeNetworkInterfaces",
            "ec2:DescribeTags",
            "ec2:GetCoipPoolUsage",
            "ec2:DescribeCoipPools",
            "elasticloadbalancing:DescribeLoadBalancers",
            "elasticloadbalancing:DescribeLoadBalancerAttributes",
            "elasticloadbalancing:DescribeListeners",
            "elasticloadbalancing:DescribeListenerCertificates",
            "elasticloadbalancing:DescribeSSLPolicies",
            "elasticloadbalancing:DescribeRules",
            "elasticloadbalancing:DescribeTargetGroups",
            "elasticloadbalancing:DescribeTargetGroupAttributes",
            "elasticloadbalancing:DescribeTargetHealth",
            "elasticloadbalancing:DescribeTags"
          ]
          Resource = "*"
        },
        {
          Effect = "Allow"
          Action = [
            "cognito-idp:DescribeUserPoolClient",
            "acm:ListCertificates",
            "acm:DescribeCertificate",
            "iam:ListServerCertificates",
            "iam:GetServerCertificate",
            "waf-regional:GetWebACL",
            "waf-regional:GetWebACLForResource",
            "waf-regional:AssociateWebACL",
            "waf-regional:DisassociateWebACL",
            "wafv2:GetWebACL",
            "wafv2:GetWebACLForResource",
            "wafv2:AssociateWebACL",
            "wafv2:DisassociateWebACL",
            "shield:GetSubscriptionState",
            "shield:DescribeProtection",
            "shield:CreateProtection",
            "shield:DeleteProtection"
          ]
          Resource = "*"
        },
        {
          Effect = "Allow"
          Action = [
            "ec2:AuthorizeSecurityGroupIngress",
            "ec2:RevokeSecurityGroupIngress",
            "ec2:CreateSecurityGroup",
            "ec2:DeleteSecurityGroup",
            "ec2:ModifyInstanceAttribute",
            "ec2:CreateNetworkInterface",
            "ec2:DescribeNetworkInterfaces",
            "ec2:DeleteNetworkInterface",
            "ec2:ModifyNetworkInterfaceAttribute",
            "ec2:CreateNetworkInterfacePermission",
            "ec2:DescribeNetworkInterfacePermissions"
          ]
          Resource = "*"
        }
      ]
    })
  
  tags = {
    Name        = "vcos-${each.key}-alb-controller-role"
    Project     = "vcos"
    Environment = "production"
    Region      = each.key
  }
}

resource "aws_iam_role" "alb_controller_irsa" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  name = "vcos-${each.key}-alb-controller-irsa"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = data.aws_eks_cluster[each.key].oidc_provider_arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${replace(data.aws_eks_cluster[each.key].oidc_provider_arn, "arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/", "")}:sub" = "system:serviceaccount:kube-system:aws-load-balancer-controller"
        }
      }
    }]
  })
  
  tags = {
    Name        = "vcos-${each.key}-alb-controller-irsa"
    Project     = "vcos"
    Environment = "production"
    Region      = each.key
  }
}

# IAM Role for S3 Replication
resource "aws_iam_role" "s3_replication" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  name = "vcos-${each.key}-s3-replication-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "s3.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
  
  inline_policy = {
    name = "s3-replication-policy"
    policy = jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Effect = "Allow"
          Action = [
            "s3:GetReplicationConfiguration",
            "s3:ListBucket"
          ]
          Resource = [
            "arn:aws:s3:::vcos-${each.value.s3_bucket_prefix}-recordings",
            "arn:aws:s3:::vcos-${each.value.s3_bucket_prefix}-assets",
            "arn:aws:s3:::vcos-${each.value.s3_bucket_prefix}-backups"
          ]
        },
        {
          Effect = "Allow"
          Action = [
            "s3:GetObjectVersion",
            "s3:GetObjectVersionTagging",
            "s3:GetObjectVersionAcl",
            "s3:GetObjectVersionTorrent"
          ]
          Resource = [
            "arn:aws:s3:::vcos-${each.value.s3_bucket_prefix}-recordings/*",
            "arn:aws:s3:::vcos-${each.value.s3_bucket_prefix}-assets/*",
            "arn:aws:s3:::vcos-${each.value.s3_bucket_prefix}-backups/*"
          ]
        },
        {
          Effect = "Allow"
          Action = [
            "s3:ReplicateObject",
            "s3:ReplicateDelete",
            "s3:ReplicateTags",
            "s3:ObjectOwnerOverrideToBucketOwner"
          ]
          Resource = [
            "arn:aws:s3:::vcos-recordings-eu-west-1/*",
            "arn:aws:s3:::vcos-recordings-ap-southeast-1/*",
            "arn:aws:s3:::vcos-assets-eu-west-1/*",
            "arn:aws:s3:::vcos-assets-ap-southeast-1/*"
          ]
        }
      ]
    })
  
  tags = {
    Name        = "vcos-${each.key}-s3-replication-role"
    Project     = "vcos"
    Environment = "production"
    Region      = each.key
  }
}

# IAM Role for ALB Controller
resource "aws_iam_role_policy_attachment" "alb_controller" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.alb_controller[each.key].name
  policy_arn = "arn:aws:iam::aws:policy/ElasticLoadBalancingFullAccess"
}

resource "aws_iam_role_policy_attachment" "alb_controller_irsa" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.alb_controller_irsa[each.key].name
  policy_arn = aws_iam_policy.alb_controller[each.key].arn
}

resource "aws_iam_policy" "alb_controller" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  name        = "vcos-${each.key}-alb-controller-policy"
  description = "Policy for AWS Load Balancer Controller"
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "iam:CreateServiceLinkedRole",
          "ec2:DescribeAccountAttributes",
          "ec2:DescribeAddresses",
          "ec2:DescribeAvailabilityZones",
          "ec2:DescribeInternetGateways",
          "ec2:DescribeVpcs",
          "ec2:DescribeSubnets",
          "ec2:DescribeSecurityGroups",
          "ec2:DescribeInstances",
          "ec2:DescribeNetworkInterfaces",
          "ec2:DescribeTags",
          "ec2:GetCoipPoolUsage",
          "ec2:DescribeCoipPools",
          "elasticloadbalancing:DescribeLoadBalancers",
          "elasticloadbalancing:DescribeLoadBalancerAttributes",
          "elasticloadbalancing:DescribeListeners",
          "elasticloadbalancing:DescribeListenerCertificates",
          "elasticloadbalancing:DescribeSSLPolicies",
          "elasticloadbalancing:DescribeRules",
          "elasticloadbalancing:DescribeTargetGroups",
          "elasticloadbalancing:DescribeTargetGroupAttributes",
          "elasticloadbalancing:DescribeTargetHealth",
          "elasticloadbalancing:DescribeTags"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "cognito-idp:DescribeUserPoolClient",
          "acm:ListCertificates",
          "acm:DescribeCertificate",
          "iam:ListServerCertificates",
          "iam:GetServerCertificate",
          "waf-regional:GetWebACL",
          "waf-regional:GetWebACLForResource",
          "waf-regional:AssociateWebACL",
          "waf-regional:DisassociateWebACL",
          "wafv2:GetWebACL",
          "wafv2:GetWebACLForResource",
          "wafv2:AssociateWebACL",
          "wafv2:DisassociateWebACL",
          "shield:GetSubscriptionState",
          "shield:DescribeProtection",
          "shield:CreateProtection",
          "shield:DeleteProtection"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ec2:AuthorizeSecurityGroupIngress",
          "ec2:RevokeSecurityGroupIngress",
          "ec2:CreateSecurityGroup",
          "ec2:DeleteSecurityGroup",
          "ec2:ModifyInstanceAttribute",
          "ec2:CreateNetworkInterface",
          "ec2:DescribeNetworkInterfaces",
          "ec2:DeleteNetworkInterface",
          "ec2:ModifyNetworkInterfaceAttribute",
          "ec2:CreateNetworkInterfacePermission",
          "ec2:DescribeNetworkInterfacePermissions"
        ]
        Resource = "*"
      }
    ]
  })
  
  tags = {
    Name        = "vcos-${each.key}-alb-controller-policy"
    Project     = "vcos"
    Environment = "production"
    Region      = each.key
  }
}