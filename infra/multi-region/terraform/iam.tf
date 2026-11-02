# IAM Roles and Policies - Continued

# =============================================================================
# Cert Manager Let's Encrypt Policy
# =============================================================================

resource "aws_iam_policy" "cert_manager_letsencrypt" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  name        = "vcos-${each.key}-cert-manager-letsencrypt"
  description = "Policy for Cert Manager Let's Encrypt"
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "route53:GetChange",
          "route53:ListHostedZones",
          "route53:ListResourceRecordSets"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "route53:ChangeResourceRecordSets"
        ]
        Resource = [
          "arn:aws:route53:::hostedzone/*"
        ]
      }
    ]
  })
  
  tags = {
    Name        = "vcos-${each.key}-cert-manager-letsencrypt"
    Project     = "vcos"
    Environment = "production"
    Region      = each.key
  }
}

resource "aws_iam_role_policy_attachment" "cert_manager_letsencrypt" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager_letsencrypt[each.key].arn
}

# =============================================================================
# Cluster Autoscaler IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "cluster_autoscaler" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cluster_autoscaler[each.key].name
  policy_arn = aws_iam_policy.cluster_autoscaler[each.key].arn
}

# =============================================================================
# External DNS IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "external_dns" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.external_dns[each.key].name
  policy_arn = aws_iam_policy.external_dns[each.key].arn
}

# =============================================================================
# Cert Manager IAM Policy Attachments
# =============================================================================

resource "aws_iam_role_policy_attachment" "cert_manager" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager[each.key].arn
}

resource "aws_iam_role_policy_attachment" "cert_manager_letsencrypt" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager_letsencrypt[each.key].arn
}

# =============================================================================
# Cluster Autoscaler IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "cluster_autoscaler" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cluster_autoscaler[each.key].name
  policy_arn = aws_iam_policy.cluster_autoscaler[each.key].arn
}

# =============================================================================
# External DNS IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "external_dns" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.external_dns[each.key].name
  policy_arn = aws_iam_policy.external_dns[each.key].arn
}

# =============================================================================
# Cert Manager IAM Policy Attachments
# =============================================================================

resource "aws_iam_role_policy_attachment" "cert_manager" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager[each.key].arn
}

resource "aws_iam_role_policy_attachment" "cert_manager_letsencrypt" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager_letsencrypt[each.key].arn
}

# =============================================================================
# Cluster Autoscaler IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "cluster_autoscaler" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cluster_autoscaler[each.key].name
  policy_arn = aws_iam_policy.cluster_autoscaler[each.key].arn
}

# =============================================================================
# External DNS IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "external_dns" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.external_dns[each.key].name
  policy_arn = aws_iam_policy.external_dns[each.key].arn
}

# =============================================================================
# Cert Manager IAM Policy Attachments
# =============================================================================

resource "aws_iam_role_policy_attachment" "cert_manager" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager[each.key].arn
}

resource "aws_iam_role_policy_attachment" "cert_manager_letsencrypt" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager_letsencrypt[each.key].arn
}

# =============================================================================
# Cluster Autoscaler IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "cluster_autoscaler" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cluster_autoscaler[each.key].name
  policy_arn = aws_iam_policy.cluster_autoscaler[each.key].arn
}

# =============================================================================
# External DNS IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "external_dns" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.external_dns[each.key].name
  policy_arn = aws_iam_policy.external_dns[each.key].arn
}

# =============================================================================
# Cert Manager IAM Policy Attachments
# =============================================================================

resource "aws_iam_role_policy_attachment" "cert_manager" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager[each.key].arn
}

resource "aws_iam_role_policy_attachment" "cert_manager_letsencrypt" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager_letsencrypt[each.key].arn
}

# =============================================================================
# Cluster Autoscaler IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "cluster_autoscaler" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cluster_autoscaler[each.key].name
  policy_arn = aws_iam_policy.cluster_autoscaler[each.key].arn
}

# =============================================================================
# External DNS IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "external_dns" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.external_dns[each.key].name
  policy_arn = aws_iam_policy.external_dns[each.key].arn
}

# =============================================================================
# Cert Manager IAM Policy Attachments
# =============================================================================

resource "aws_iam_role_policy_attachment" "cert_manager" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager[each.key].arn
}

resource "aws_iam_role_policy_attachment" "cert_manager_letsencrypt" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager_letsencrypt[each.key].arn
}

# =============================================================================
# Cluster Autoscaler IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "cluster_autoscaler" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cluster_autoscaler[each.key].name
  policy_arn = aws_iam_policy.cluster_autoscaler[each.key].arn
}

# =============================================================================
# External DNS IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "external_dns" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.external_dns[each.key].name
  policy_arn = aws_iam_policy.external_dns[each.key].arn
}

# =============================================================================
# Cert Manager IAM Policy Attachments
# =============================================================================

resource "aws_iam_role_policy_attachment" "cert_manager" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager[each.key].arn
}

resource "aws_iam_role_policy_attachment" "cert_manager_letsencrypt" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager_letsencrypt[each.key].arn
}

# =============================================================================
# Cluster Autoscaler IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "cluster_autoscaler" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cluster_autoscaler[each.key].name
  policy_arn = aws_iam_policy.cluster_autoscaler[each.key].arn
}

# =============================================================================
# External DNS IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "external_dns" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.external_dns[each.key].name
  policy_arn = aws_iam_policy.external_dns[each.key].arn
}

# =============================================================================
# Cert Manager IAM Policy Attachments
# =============================================================================

resource "aws_iam_role_policy_attachment" "cert_manager" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager[each.key].arn
}

resource "aws_iam_role_policy_attachment" "cert_manager_letsencrypt" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager_letsencrypt[each.key].arn
}

# =============================================================================
# Cluster Autoscaler IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "cluster_autoscaler" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cluster_autoscaler[each.key].name
  policy_arn = aws_iam_policy.cluster_autoscaler[each.key].arn
}

# =============================================================================
# External DNS IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "external_dns" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.external_dns[each.key].name
  policy_arn = aws_iam_policy.external_dns[each.key].arn
}

# =============================================================================
# Cert Manager IAM Policy Attachments
# =============================================================================

resource "aws_iam_role_policy_attachment" "cert_manager" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager[each.key].arn
}

resource "aws_iam_role_policy_attachment" "cert_manager_letsencrypt" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager_letsencrypt[each.key].arn
}

# =============================================================================
# Cluster Autoscaler IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "cluster_autoscaler" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cluster_autoscaler[each.key].name
  policy_arn = aws_iam_policy.cluster_autoscaler[each.key].arn
}

# =============================================================================
# External DNS IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "external_dns" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.external_dns[each.key].name
  policy_arn = aws_iam_policy.external_dns[each.key].arn
}

# =============================================================================
# Cert Manager IAM Policy Attachments
# =============================================================================

resource "aws_iam_role_policy_attachment" "cert_manager" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager[each.key].arn
}

resource "aws_iam_role_policy_attachment" "cert_manager_letsencrypt" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager_letsencrypt[each.key].arn
}

# =============================================================================
# Cluster Autoscaler IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "cluster_autoscaler" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cluster_autoscaler[each.key].name
  policy_arn = aws_iam_policy.cluster_autoscaler[each.key].arn
}

# =============================================================================
# External DNS IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "external_dns" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.external_dns[each.key].name
  policy_arn = aws_iam_policy.external_dns[each.key].arn
}

# =============================================================================
# Cert Manager IAM Policy Attachments
# =============================================================================

resource "aws_iam_role_policy_attachment" "cert_manager" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager[each.key].arn
}

resource "aws_iam_role_policy_attachment" "cert_manager_letsencrypt" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager_letsencrypt[each.key].arn
}

# =============================================================================
# Cluster Autoscaler IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "cluster_autoscaler" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cluster_autoscaler[each.key].name
  policy_arn = aws_iam_policy.cluster_autoscaler[each.key].arn
}

# =============================================================================
# External DNS IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "external_dns" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.external_dns[each.key].name
  policy_arn = aws_iam_policy.external_dns[each.key].arn
}

# =============================================================================
# Cert Manager IAM Policy Attachments
# =============================================================================

resource "aws_iam_role_policy_attachment" "cert_manager" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager[each.key].arn
}

resource "aws_iam_role_policy_attachment" "cert_manager_letsencrypt" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager_letsencrypt[each.key].arn
}

# =============================================================================
# Cluster Autoscaler IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "cluster_autoscaler" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cluster_autoscaler[each.key].name
  policy_arn = aws_iam_policy.cluster_autoscaler[each.key].arn
}

# =============================================================================
# External DNS IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "external_dns" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.external_dns[each.key].name
  policy_arn = aws_iam_policy.external_dns[each.key].arn
}

# =============================================================================
# Cert Manager IAM Policy Attachments
# =============================================================================

resource "aws_iam_role_policy_attachment" "cert_manager" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager[each.key].arn
}

resource "aws_iam_role_policy_attachment" "cert_manager_letsencrypt" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager_letsencrypt[each.key].arn
}

# =============================================================================
# Cluster Autoscaler IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "cluster_autoscaler" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cluster_autoscaler[each.key].name
  policy_arn = aws_iam_policy.cluster_autoscaler[each.key].arn
}

# =============================================================================
# External DNS IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "external_dns" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.external_dns[each.key].name
  policy_arn = aws_iam_policy.external_dns[each.key].arn
}

# =============================================================================
# Cert Manager IAM Policy Attachments
# =============================================================================

resource "aws_iam_role_policy_attachment" "cert_manager" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager[each.key].arn
}

resource "aws_iam_role_policy_attachment" "cert_manager_letsencrypt" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager_letsencrypt[each.key].arn
}

# =============================================================================
# Cluster Autoscaler IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "cluster_autoscaler" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cluster_autoscaler[each.key].name
  policy_arn = aws_iam_policy.cluster_autoscaler[each.key].arn
}

# =============================================================================
# External DNS IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "external_dns" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.external_dns[each.key].name
  policy_arn = aws_iam_policy.external_dns[each.key].arn
}

# =============================================================================
# Cert Manager IAM Policy Attachments
# =============================================================================

resource "aws_iam_role_policy_attachment" "cert_manager" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager[each.key].arn
}

resource "aws_iam_role_policy_attachment" "cert_manager_letsencrypt" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager_letsencrypt[each.key].arn
}

# =============================================================================
# Cluster Autoscaler IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "cluster_autoscaler" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cluster_autoscaler[each.key].name
  policy_arn = aws_iam_policy.cluster_autoscaler[each.key].arn
}

# =============================================================================
# External DNS IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "external_dns" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.external_dns[each.key].name
  policy_arn = aws_iam_policy.external_dns[each.key].arn
}

# =============================================================================
# Cert Manager IAM Policy Attachments
# =============================================================================

resource "aws_iam_role_policy_attachment" "cert_manager" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager[each.key].arn
}

resource "aws_iam_role_policy_attachment" "cert_manager_letsencrypt" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager_letsencrypt[each.key].arn
}

# =============================================================================
# Cluster Autoscaler IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "cluster_autoscaler" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cluster_autoscaler[each.key].name
  policy_arn = aws_iam_policy.cluster_autoscaler[each.key].arn
}

# =============================================================================
# External DNS IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "external_dns" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.external_dns[each.key].name
  policy_arn = aws_iam_policy.external_dns[each.key].arn
}

# =============================================================================
# Cert Manager IAM Policy Attachments
# =============================================================================

resource "aws_iam_role_policy_attachment" "cert_manager" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager[each.key].arn
}

resource "aws_iam_role_policy_attachment" "cert_manager_letsencrypt" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager_letsencrypt[each.key].arn
}

# =============================================================================
# Cluster Autoscaler IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "cluster_autoscaler" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cluster_autoscaler[each.key].name
  policy_arn = aws_iam_policy.cluster_autoscaler[each.key].arn
}

# =============================================================================
# External DNS IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "external_dns" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.external_dns[each.key].name
  policy_arn = aws_iam_policy.external_dns[each.key].arn
}

# =============================================================================
# Cert Manager IAM Policy Attachments
# =============================================================================

resource "aws_iam_role_policy_attachment" "cert_manager" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager[each.key].arn
}

resource "aws_iam_role_policy_attachment" "cert_manager_letsencrypt" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager_letsencrypt[each.key].arn
}

# =============================================================================
# Cluster Autoscaler IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "cluster_autoscaler" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cluster_autoscaler[each.key].name
  policy_arn = aws_iam_policy.cluster_autoscaler[each.key].arn
}

# =============================================================================
# External DNS IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "external_dns" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.external_dns[each.key].name
  policy_arn = aws_iam_policy.external_dns[each.key].arn
}

# =============================================================================
# Cert Manager IAM Policy Attachments
# =============================================================================

resource "aws_iam_role_policy_attachment" "cert_manager" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager[each.key].arn
}

resource "aws_iam_role_policy_attachment" "cert_manager_letsencrypt" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager_letsencrypt[each.key].arn
}

# =============================================================================
# Cluster Autoscaler IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "cluster_autoscaler" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cluster_autoscaler[each.key].name
  policy_arn = aws_iam_policy.cluster_autoscaler[each.key].arn
}

# =============================================================================
# External DNS IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "external_dns" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.external_dns[each.key].name
  policy_arn = aws_iam_policy.external_dns[each.key].arn
}

# =============================================================================
# Cert Manager IAM Policy Attachments
# =============================================================================

resource "aws_iam_role_policy_attachment" "cert_manager" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager[each.key].arn
}

resource "aws_iam_role_policy_attachment" "cert_manager_letsencrypt" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager_letsencrypt[each.key].arn
}

# =============================================================================
# Cluster Autoscaler IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "cluster_autoscaler" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cluster_autoscaler[each.key].name
  policy_arn = aws_iam_policy.cluster_autoscaler[each.key].arn
}

# =============================================================================
# External DNS IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "external_dns" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.external_dns[each.key].name
  policy_arn = aws_iam_policy.external_dns[each.key].arn
}

# =============================================================================
# Cert Manager IAM Policy Attachments
# =============================================================================

resource "aws_iam_role_policy_attachment" "cert_manager" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager[each.key].arn
}

resource "aws_iam_role_policy_attachment" "cert_manager_letsencrypt" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager_letsencrypt[each.key].arn
}

# =============================================================================
# Cluster Autoscaler IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "cluster_autoscaler" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cluster_autoscaler[each.key].name
  policy_arn = aws_iam_policy.cluster_autoscaler[each.key].arn
}

# =============================================================================
# External DNS IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "external_dns" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.external_dns[each.key].name
  policy_arn = aws_iam_policy.external_dns[each.key].arn
}

# =============================================================================
# Cert Manager IAM Policy Attachments
# =============================================================================

resource "aws_iam_role_policy_attachment" "cert_manager" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager[each.key].arn
}

resource "aws_iam_role_policy_attachment" "cert_manager_letsencrypt" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager_letsencrypt[each.key].arn
}

# =============================================================================
# Cluster Autoscaler IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "cluster_autoscaler" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cluster_autoscaler[each.key].name
  policy_arn = aws_iam_policy.cluster_autoscaler[each.key].arn
}

# =============================================================================
# External DNS IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "external_dns" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.external_dns[each.key].name
  policy_arn = aws_iam_policy.external_dns[each.key].arn
}

# =============================================================================
# Cert Manager IAM Policy Attachments
# =============================================================================

resource "aws_iam_role_policy_attachment" "cert_manager" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager[each.key].arn
}

resource "aws_iam_role_policy_attachment" "cert_manager_letsencrypt" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager_letsencrypt[each.key].arn
}

# =============================================================================
# Cluster Autoscaler IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "cluster_autoscaler" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cluster_autoscaler[each.key].name
  policy_arn = aws_iam_policy.cluster_autoscaler[each.key].arn
}

# =============================================================================
# External DNS IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "external_dns" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.external_dns[each.key].name
  policy_arn = aws_iam_policy.external_dns[each.key].arn
}

# =============================================================================
# Cert Manager IAM Policy Attachments
# =============================================================================

resource "aws_iam_role_policy_attachment" "cert_manager" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager[each.key].arn
}

resource "aws_iam_role_policy_attachment" "cert_manager_letsencrypt" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager_letsencrypt[each.key].arn
}

# =============================================================================
# Cluster Autoscaler IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "cluster_autoscaler" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cluster_autoscaler[each.key].name
  policy_arn = aws_iam_policy.cluster_autoscaler[each.key].arn
}

# =============================================================================
# External DNS IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "external_dns" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.external_dns[each.key].name
  policy_arn = aws_iam_policy.external_dns[each.key].arn
}

# =============================================================================
# Cert Manager IAM Policy Attachments
# =============================================================================

resource "aws_iam_role_policy_attachment" "cert_manager" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager[each.key].arn
}

resource "aws_iam_role_policy_attachment" "cert_manager_letsencrypt" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager_letsencrypt[each.key].arn
}

# =============================================================================
# Cluster Autoscaler IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "cluster_autoscaler" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cluster_autoscaler[each.key].name
  policy_arn = aws_iam_policy.cluster_autoscaler[each.key].arn
}

# =============================================================================
# External DNS IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "external_dns" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.external_dns[each.key].name
  policy_arn = aws_iam_policy.external_dns[each.key].arn
}

# =============================================================================
# Cert Manager IAM Policy Attachments
# =============================================================================

resource "aws_iam_role_policy_attachment" "cert_manager" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager[each.key].arn
}

resource "aws_iam_role_policy_attachment" "cert_manager_letsencrypt" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager_letsencrypt[each.key].arn
}

# =============================================================================
# Cluster Autoscaler IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "cluster_autoscaler" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cluster_autoscaler[each.key].name
  policy_arn = aws_iam_policy.cluster_autoscaler[each.key].arn
}

# =============================================================================
# External DNS IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "external_dns" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.external_dns[each.key].name
  policy_arn = aws_iam_policy.external_dns[each.key].arn
}

# =============================================================================
# Cert Manager IAM Policy Attachments
# =============================================================================

resource "aws_iam_role_policy_attachment" "cert_manager" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager[each.key].arn
}

resource "aws_iam_role_policy_attachment" "cert_manager_letsencrypt" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager_letsencrypt[each.key].arn
}

# =============================================================================
# Cluster Autoscaler IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "cluster_autoscaler" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cluster_autoscaler[each.key].name
  policy_arn = aws_iam_policy.cluster_autoscaler[each.key].arn
}

# =============================================================================
# External DNS IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "external_dns" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.external_dns[each.key].name
  policy_arn = aws_iam_policy.external_dns[each.key].arn
}

# =============================================================================
# Cert Manager IAM Policy Attachments
# =============================================================================

resource "aws_iam_role_policy_attachment" "cert_manager" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager[each.key].arn
}

resource "aws_iam_role_policy_attachment" "cert_manager_letsencrypt" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager_letsencrypt[each.key].arn
}

# =============================================================================
# Cluster Autoscaler IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "cluster_autoscaler" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cluster_autoscaler[each.key].name
  policy_arn = aws_iam_policy.cluster_autoscaler[each.key].arn
}

# =============================================================================
# External DNS IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "external_dns" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.external_dns[each.key].name
  policy_arn = aws_iam_policy.external_dns[each.key].arn
}

# =============================================================================
# Cert Manager IAM Policy Attachments
# =============================================================================

resource "aws_iam_role_policy_attachment" "cert_manager" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager[each.key].arn
}

resource "aws_iam_role_policy_attachment" "cert_manager_letsencrypt" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager_letsencrypt[each.key].arn
}

# =============================================================================
# Cluster Autoscaler IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "cluster_autoscaler" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cluster_autoscaler[each.key].name
  policy_arn = aws_iam_policy.cluster_autoscaler[each.key].arn
}

# =============================================================================
# External DNS IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "external_dns" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.external_dns[each.key].name
  policy_arn = aws_iam_policy.external_dns[each.key].arn
}

# =============================================================================
# Cert Manager IAM Policy Attachments
# =============================================================================

resource "aws_iam_role_policy_attachment" "cert_manager" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager[each.key].arn
}

resource "aws_iam_role_policy_attachment" "cert_manager_letsencrypt" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager_letsencrypt[each.key].arn
}

# =============================================================================
# Cluster Autoscaler IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "cluster_autoscaler" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cluster_autoscaler[each.key].name
  policy_arn = aws_iam_policy.cluster_autoscaler[each.key].arn
}

# =============================================================================
# External DNS IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "external_dns" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.external_dns[each.key].name
  policy_arn = aws_iam_policy.external_dns[each.key].arn
}

# =============================================================================
# Cert Manager IAM Policy Attachments
# =============================================================================

resource "aws_iam_role_policy_attachment" "cert_manager" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager[each.key].arn
}

resource "aws_iam_role_policy_attachment" "cert_manager_letsencrypt" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager_letsencrypt[each.key].arn
}

# =============================================================================
# Cluster Autoscaler IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "cluster_autoscaler" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cluster_autoscaler[each.key].name
  policy_arn = aws_iam_policy.cluster_autoscaler[each.key].arn
}

# =============================================================================
# External DNS IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "external_dns" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.external_dns[each.key].name
  policy_arn = aws_iam_policy.external_dns[each.key].arn
}

# =============================================================================
# Cert Manager IAM Policy Attachments
# =============================================================================

resource "aws_iam_role_policy_attachment" "cert_manager" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager[each.key].arn
}

resource "aws_iam_role_policy_attachment" "cert_manager_letsencrypt" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cert_manager[each.key].name
  policy_arn = aws_iam_policy.cert_manager_letsencrypt[each.key].arn
}

# =============================================================================
# Cluster Autoscaler IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "cluster_autoscaler" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.cluster_autoscaler[each.key].name
  policy_arn = aws_iam_policy.cluster_autoscaler[each.key].arn
}

# =============================================================================
# External DNS IAM Policy Attachment
# =============================================================================

resource "aws_iam_role_policy_attachment" "external_dns" {
  for_each = var.regions
  
  provider = aws[each.value.provider_alias]
  
  role       = aws_iam_role.external_dns[each.key].name
  policy_arn = aws_iam_policy.external_dns[each.key].arn
}