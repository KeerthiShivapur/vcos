# Multi-Region Infrastructure - Variables

variable "cloudflare_api_token" {
  description = "Cloudflare API token for DNS and CDN management"
  type        = string
  sensitive   = true
}

variable "regions" {
  description = "Map of regions to deploy"
  type = map(object({
    name              = string
    provider_alias    = string
    k8s_version       = string
    vpc_cidr          = string
    instance_types    = map(string)
    node_group_sizes  = map(object({
      min_size     = number
      max_size     = number
      desired_size = number
    }))
    postgres_instance_class = string
    redis_node_type         = string
    s3_bucket_prefix        = string
    cloudfront_price_class  = string
  }))
  
  default = {
    "us-east-1" = {
      name              = "us-east-1"
      provider_alias    = "us_east_1"
      k8s_version       = "1.28"
      vpc_cidr          = "10.0.0.0/16"
      instance_types = {
        general   = "m6i.xlarge"
        compute   = "c6i.2xlarge"
        memory    = "r6i.xlarge"
      }
      node_group_sizes = {
        general = { min_size = 3, max_size = 50, desired_size = 6 }
        compute = { min_size = 2, max_size = 20, desired_size = 4 }
        memory  = { min_size = 1, max_size = 10, desired_size = 2 }
      }
      postgres_instance_class = "db.r6g.xlarge"
      redis_node_type         = "cache.r6g.xlarge"
      s3_bucket_prefix        = "vcos-us-east-1"
      cloudfront_price_class  = "PriceClass_All"
    }
    "eu-west-1" = {
      name              = "eu-west-1"
      provider_alias    = "eu_west_1"
      k8s_version       = "1.28"
      vpc_cidr          = "10.1.0.0/16"
      instance_types = {
        general   = "m6i.xlarge"
        compute   = "c6i.2xlarge"
        memory    = "r6i.xlarge"
      }
      node_group_sizes = {
        general = { min_size = 3, max_size = 30, desired_size = 4 }
        compute = { min_size = 2, max_size = 15, desired_size = 3 }
        memory  = { min_size = 1, max_size = 8, desired_size = 2 }
      }
      postgres_instance_class = "db.r6g.xlarge"
      redis_node_type         = "cache.r6g.xlarge"
      s3_bucket_prefix        = "vcos-eu-west-1"
      cloudfront_price_class  = "PriceClass_100"
    }
    "ap-southeast-1" = {
      name              = "ap-southeast-1"
      provider_alias    = "ap_southeast_1"
      k8s_version       = "1.28"
      vpc_cidr          = "10.2.0.0/16"
      instance_types = {
        general   = "m6i.xlarge"
        compute   = "c6i.2xlarge"
        memory    = "r6i.xlarge"
      }
      node_group_sizes = {
        general = { min_size = 2, max_size = 20, desired_size = 3 }
        compute = { min_size = 1, max_size = 10, desired_size = 2 }
        memory  = { min_size = 1, max_size = 6, desired_size = 1 }
      }
      postgres_instance_class = "db.r6g.large"
      redis_node_type         = "cache.r6g.large"
      s3_bucket_prefix        = "vcos-ap-southeast-1"
      cloudfront_price_class  = "PriceClass_200"
    }
  }
}

variable "livekit_api_key" {
  description = "LiveKit API key"
  type        = string
  sensitive   = true
}

variable "livekit_api_secret" {
  description = "LiveKit API secret"
  type        = string
  sensitive   = true
}

variable "turn_password" {
  description = "TURN server password"
  type        = string
  sensitive   = true
}

variable "turn_secret" {
  description = "TURN shared secret for ephemeral credentials"
  type        = string
  sensitive   = true
}

variable "postgres_password" {
  description = "PostgreSQL password"
  type        = string
  sensitive   = true
}

variable "redis_password" {
  description = "Redis password"
  type        = string
  sensitive   = true
}

variable "aws_access_key" {
  description = "AWS access key for S3"
  type        = string
  sensitive   = true
}

variable "aws_secret_key" {
  description = "AWS secret key for S3"
  type        = string
  sensitive   = true
}

variable "srt_passphrase" {
  description = "SRT passphrase for LiveKit ingress"
  type        = string
  sensitive   = true
}