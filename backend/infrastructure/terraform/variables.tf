variable "region" {
  description = "AWS region (Phase 16 multi-region deployment)."
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment."
  type        = string
  default     = "production"
}

variable "api_image_tag" {
  description = "Container image tag for the API deployment."
  type        = string
  default     = "1.0.0"
}

variable "autoscaling_min" {
  description = "Minimum API replicas (matches autoscaling MIN_CAPACITY)."
  type        = number
  default     = 3
}

variable "autoscaling_max" {
  description = "Maximum API replicas (matches autoscaling MAX_CAPACITY)."
  type        = number
  default     = 20
}
