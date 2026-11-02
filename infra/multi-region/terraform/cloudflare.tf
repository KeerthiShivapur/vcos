# Cloudflare DNS and CDN Configuration
# Global DNS management for multi-region VCOS deployment

# =============================================================================
# Cloudflare Zone
# =============================================================================

data "cloudflare_zone" "vcos" {
  name = "vcos.io"
}

# =============================================================================
# Global DNS Records
# =============================================================================

# Root domain - points to Global Accelerator / Cloudflare
resource "cloudflare_record" "root" {
  zone_id = data.cloudflare_zone.vcos.id
  name    = "@"
  type    = "CNAME"
  value   = "global-accelerator.vcos.io"
  ttl     = 300
  proxied = true
  
  comment = "Root domain -> Global Accelerator"
}

# API subdomain
resource "cloudflare_record" "api" {
  zone_id = data.cloudflare_zone.vcos.id
  name    = "api"
  type    = "CNAME"
  value   = "global-alb.vcos.io"
  ttl     = 300
  proxied = true
  
  comment = "API subdomain -> Global ALB"
}

# App subdomain
resource "cloudflare_record" "app" {
  zone_id = data.cloudflare_zone.vcos.id
  name    = "app"
  type    = "CNAME"
  value   = "global-alb.vcos.io"
  ttl     = 300
  proxied = true
  
  comment = "App subdomain -> Global ALB"
}

# WebSocket subdomain
resource "cloudflare_record" "ws" {
  zone_id = data.cloudflare_zone.vcos.id
  name    = "ws"
  type    = "CNAME"
  value   = "ws-global-alb.vcos.io"
  ttl     = 300
  proxied = true
  
  comment = "WebSocket subdomain -> Global WebSocket ALB"
}

# =============================================================================
# Region-specific TURN Servers (Geo-routing)
# =============================================================================

resource "cloudflare_record" "turn_us_east_1" {
  zone_id = data.cloudflare_zone.vcos.id
  name    = "turn-us-east-1"
  type    = "A"
  value   = module.turn_us_east_1.public_ip
  ttl     = 300
  proxied = false
  
  comment = "TURN server US East"
}

resource "cloudflare_record" "turn_eu_west_1" {
  zone_id = data.cloudflare_zone.vcos.id
  name    = "turn-eu-west-1"
  type    = "A"
  value   = module.turn_eu_west_1.public_ip
  ttl     = 300
  proxied = false
  
  comment = "TURN server EU West"
}

resource "cloudflare_record" "turn_ap_southeast_1" {
  zone_id = data.cloudflare_zone.vcos.id
  name    = "turn-ap-southeast-1"
  type    = "A"
  value   = module.turn_ap_southeast_1.public_ip
  ttl     = 300
  proxied = false
  
  comment = "TURN server AP Southeast"
}

# =============================================================================
# Region-specific LiveKit endpoints (Geo-routing)
# =============================================================================

resource "cloudflare_record" "livekit_us_east_1" {
  zone_id = data.cloudflare_zone.vcos.id
  name    = "livekit-us-east-1"
  type    = "CNAME"
  value   = module.livekit_us_east_1.endpoint
  ttl     = 300
  proxied = true
  
  comment = "LiveKit US East endpoint"
}

resource "cloudflare_record" "livekit_eu_west_1" {
  zone_id = data.cloudflare_zone.vcos.id
  name    = "livekit-eu-west-1"
  type    = "CNAME"
  value   = module.livekit_eu_west_1.endpoint
  ttl     = 300
  proxied = true
  
  comment = "LiveKit EU West endpoint"
}

resource "cloudflare_record" "livekit_ap_southeast_1" {
  zone_id = data.cloudflare_zone.vcos.id
  name    = "livekit-ap-southeast-1"
  type    = "CNAME"
  value   = module.livekit_ap_southeast_1.endpoint
  ttl     = 300
  proxied = true
  
  comment = "LiveKit AP Southeast endpoint"
}

# =============================================================================
# Global endpoint (Geo-routing)
# =============================================================================

resource "cloudflare_record" "livekit_global" {
  zone_id = data.cloudflare_zone.vcos.id
  name    = "livekit"
  type    = "CNAME"
  value   = "global-livekit.vcos.io"
  ttl     = 300
  proxied = true
  
  comment = "Global LiveKit endpoint (Geo-routing)"
}

# =============================================================================
# API subdomains per region
# =============================================================================

resource "cloudflare_record" "api_us_east_1" {
  zone_id = data.cloudflare_zone.vcos.id
  name    = "api-us-east-1"
  type    = "CNAME"
  value   = module.alb_us_east_1.dns_name
  ttl     = 300
  proxied = true
  
  comment = "API US East"
}

resource "cloudflare_record" "api_eu_west_1" {
  zone_id = data.cloudflare_zone.vcos.id
  name    = "api-eu-west-1"
  type    = "CNAME"
  value   = module.alb_eu_west_1.dns_name
  ttl     = 300
  proxied = true
  
  comment = "API EU West"
}

resource "cloudflare_record" "api_ap_southeast_1" {
  zone_id = data.cloudflare_zone.vcos.id
  name    = "api-ap-southeast-1"
  type    = "CNAME"
  value   = module.alb_ap_southeast_1.dns_name
  ttl     = 300
  proxied = true
  
  comment = "API AP Southeast"
}

# =============================================================================
# CDN
# =============================================================================

resource "cloudflare_record" "cdn" {
  zone_id = data.cloudflare_zone.vcos.id
  name    = "cdn"
  type    = "CNAME"
  value   = "cdn.vcos.io.cdn.cloudflare.net"
  ttl     = 300
  proxied = true
  
  comment = "CDN endpoint"
}

# =============================================================================
# Wildcard for custom domains
# =============================================================================

resource "cloudflare_record" "wildcard" {
  zone_id = data.cloudflare_zone.vcos.id
  name    = "*"
  type    = "CNAME"
  value   = "wildcard.vcos.io"
  ttl     = 300
  proxied = true
  
  comment = "Wildcard for custom domains"
}

# =============================================================================
# Health Checks (Cloudflare Load Balancer)
# =============================================================================

resource "cloudflare_load_balancer" "global" {
  name        = "vcos-global-lb"
  description = "Global load balancer for VCOS"
  enabled     = true
  ttl         = 30
  fallback_pool = cloudflare_load_balancer_pool.primary.id
  
  region_pools = {
    "WNAM" = cloudflare_load_balancer_pool.us_east_1.id
    "ENAM" = cloudflare_load_balancer_pool.us_east_1.id
    "WCAM" = cloudflare_load_balancer_pool.us_east_1.id
    "SCAM" = cloudflare_load_balancer_pool.us_east_1.id
    "NEUR" = cloudflare_load_balancer_pool.eu_west_1.id
    "EEUR" = cloudflare_load_balancer_pool.eu_west_1.id
    "SEAS" = cloudflare_load_balancer_pool.ap_southeast_1.id
    "OC"   = cloudflare_load_balancer_pool.ap_southeast_1.id
  }
  
  proxied = true
  
  steering_policy = "dynamic_latency"
  
  session_affinity = "cookie"
  session_affinity_ttl = 3600
  
  origin_steering_policy = "dynamic_latency"
  
  fallbacks = [
    cloudflare_load_balancer_pool.primary.id
  ]
}

# =============================================================================
# Load Balancer Pools (per region)
# =============================================================================

resource "cloudflare_load_balancer_pool" "primary" {
  name        = "vcos-primary-pool"
  description = "Primary pool (US East)"
  enabled     = true
  minimum_origins = 1
  
  check_regions = ["WNAM", "ENAM"]
  
  monitor = cloudflare_load_balancer_monitor.http.id
  
  origins = [
    {
      name     = "us-east-1-primary"
      address  = module.alb_us_east_1.dns_name
      weight   = 1.0
      enabled  = true
      header   = {
        Host = "api.vcos.io"
      }
    }
  ]
  
  notification_email = "ops@vcos.io"
  
  healthy_threshold = 2
  unhealthy_threshold = 3
}

resource "cloudflare_load_balancer_pool" "us_east_1" {
  name        = "vcos-us-east-1-pool"
  description = "US East pool"
  enabled     = true
  minimum_origins = 1
  
  check_regions = ["WNAM", "ENAM"]
  
  monitor = cloudflare_load_balancer_monitor.http.id
  
  origins = [
    {
      name     = "us-east-1"
      address  = module.alb_us_east_1.dns_name
      weight   = 1.0
      enabled  = true
      header   = {
        Host = "api.vcos.io"
      }
    }
  ]
  
  notification_email = "ops@vcos.io"
}

resource "cloudflare_load_balancer_pool" "eu_west_1" {
  name        = "vcos-eu-west-1-pool"
  description = "EU West pool"
  enabled     = true
  minimum_origins = 1
  
  check_regions = ["WEUR", "EEUR"]
  
  monitor = cloudflare_load_balancer_monitor.http.id
  
  origins = [
    {
      name     = "eu-west-1"
      address  = module.alb_eu_west_1.dns_name
      weight   = 1.0
      enabled  = true
      header   = {
        Host = "api.vcos.io"
      }
    }
  ]
  
  notification_email = "ops@vcos.io"
}

resource "cloudflare_load_balancer_pool" "ap_southeast_1" {
  name        = "vcos-ap-southeast-1-pool"
  description = "AP Southeast pool"
  enabled     = true
  minimum_origins = 1
  
  check_regions = ["SEAS", "OC"]
  
  monitor = cloudflare_load_balancer_monitor.http.id
  
  origins = [
    {
      name     = "ap-southeast-1"
      address  = module.alb_ap_southeast_1.dns_name
      weight   = 1.0
      enabled  = true
      header   = {
        Host = "api.vcos.io"
      }
    }
  ]
  
  notification_email = "ops@vcos.io"
}

# =============================================================================
# Load Balancer Monitor
# =============================================================================

resource "cloudflare_load_balancer_monitor" "http" {
  type          = "http"
  description   = "HTTP health check for load balancer pools"
  method        = "GET"
  path          = "/health"
  timeout       = 5
  interval      = 30
  retries       = 2
  follow_redirects = true
  allow_insecure = false
  expected_codes = "200"
  expected_body = "healthy"
  header = {
    Host = "api.vcos.io"
  }
  follow_redirects = true
  allow_insecure = false
}

# =============================================================================
# Cloudflare Page Rules
# =============================================================================

resource "cloudflare_page_rule" "api_cache" {
  zone_id = data.cloudflare_zone.vcos.id
  target  = "api.vcos.io/*"
  status  = "active"
  priority = 1
  
  actions {
    cache_level = "bypass"
  }
}

resource "cloudflare_page_rule" "static_assets" {
  zone_id = data.cloudflare_zone.vcos.id
  target  = "cdn.vcos.io/*"
  status  = "active"
  priority = 2
  
  actions {
    cache_level = "cache_everything"
    edge_cache_ttl = 31536000
    browser_cache_ttl = 86400
  }
}

resource "cloudflare_page_rule" "app_no_cache" {
  zone_id = data.cloudflare_zone.vcos.id
  target  = "app.vcos.io/*"
  status  = "active"
  priority = 3
  
  actions {
    cache_level = "bypass"
  }
}

resource "cloudflare_page_rule" "websocket_no_cache" {
  zone_id = data.cloudflare_zone.vcos.id
  target  = "ws.vcos.io/*"
  status  = "active"
  priority = 4
  
  actions {
    cache_level = "bypass"
  }
}

# =============================================================================
# Cloudflare Workers (Edge Functions)
# =============================================================================

resource "cloudflare_worker_script" "geo_routing" {
  name = "vcos-geo-routing"
  
  content = <<-EOT
    addEventListener('fetch', event => {
      event.respondWith(handleRequest(event.request))
    })
    
    async function handleRequest(request) {
      const url = new URL(request.url)
      const country = request.cf?.country || 'US'
      
      // Define region mapping
      const regionMap = {
        'US': 'us-east-1', 'CA': 'us-east-1', 'MX': 'us-east-1',
        'GB': 'eu-west-1', 'DE': 'eu-west-1', 'FR': 'eu-west-1',
        'SG': 'ap-southeast-1', 'JP': 'ap-southeast-1', 'AU': 'ap-southeast-1'
      }
      
      const region = regionMap[country] || 'us-east-1'
      const target = `https://api-${region}.vcos.io${url.pathname}${url.search}`
      
      return fetch(target, {
        method: request.method,
        headers: request.headers,
        body: request.body,
        redirect: 'follow'
      })
    }
  EOT
  
  module = true
}

resource "cloudflare_worker_route" "geo_routing" {
  zone_id = data.cloudflare_zone.vcos.id
  pattern = "api.vcos.io/*"
  script_name = cloudflare_worker_script.geo_routing.name
}

# =============================================================================
# Cloudflare WAF Rules
# =============================================================================

resource "cloudflare_filter" "rate_limit" {
  zone_id = data.cloudflare_zone.vcos.id
  expression = "(http.request.uri.path matches \"^/api/\" and http.request.method in {\"POST\" \"PUT\" \"DELETE\"})"
  description = "Rate limit API mutations"
}

resource "cloudflare_rate_limit" "api_mutations" {
  zone_id = data.cloudflare_zone.vcos.id
  threshold = 100
  period = 60
  action {
    mode = "simulate"
    timeout = 300
    response {
      content_type = "application/json"
      content = '{"error": "Rate limit exceeded"}'
    }
  }
  
  filter = {
    id = cloudflare_filter.rate_limit.id
  }
  
  match_request {
    request_method = ["POST", "PUT", "DELETE"]
    schemes = ["HTTPS"]
    url_pattern = "api.vcos.io/*"
  }
}

resource "cloudflare_filter" "login_protection" {
  zone_id = data.cloudflare_zone.vcos.id
  expression = "(http.request.uri.path matches \"^/api/auth/login\" and http.request.method == \"POST\")"
  description = "Login rate limit"
}

resource "cloudflare_rate_limit" "login" {
  zone_id = data.cloudflare_zone.vcos.id
  threshold = 5
  period = 300
  action {
    mode = "block"
    timeout = 900
    response {
      content_type = "application/json"
      content = '{"error": "Too many login attempts"}'
    }
  }
  
  filter = {
    id = cloudflare_filter.login_protection.id
  }
  
  match_request {
    request_method = ["POST"]
    schemes = ["HTTPS"]
    url_pattern = "*/api/auth/login"
  }
}

# =============================================================================
# Cloudflare Firewall Rules
# =============================================================================

resource "cloudflare_firewall_rule" "block_bad_bots" {
  zone_id = data.cloudflare_zone.vcos.id
  description = "Block known bad bots"
  action = "block"
  priority = 1
  paused = false
  
  filter {
    expression = "(http.user_agent contains \"sqlmap\" or http.user_agent contains \"nikto\" or http.user_agent contains \"nessus\")"
  }
}

resource "cloudflare_firewall_rule" "block_sql_injection" {
  zone_id = data.cloudflare_zone.vcos.id
  description = "Block SQL injection attempts"
  action = "block"
  priority = 2
  paused = false
  
  filter {
    expression = "(http.request.uri.query contains \"union select\" or http.request.uri.query contains \"drop table\" or http.request.body contains \"union select\" or http.request.body contains \"drop table\")"
  }
}

resource "cloudflare_firewall_rule" "block_xss" {
  zone_id = data.cloudflare_zone.vcos.id
  description = "Block XSS attempts"
  action = "block"
  priority = 3
  paused = false
  
  filter {
    expression = "(http.request.uri.query contains \"<script>\" or http.request.body contains \"<script>\" or http.request.uri.query contains \"javascript:\" or http.request.body contains \"javascript:\")"
  }
}

# =============================================================================
# Cloudflare Access Policies (Zero Trust)
# =============================================================================

resource "cloudflare_access_application" "admin" {
  zone_id = data.cloudflare_zone.vcos.id
  name = "VCOS Admin Panel"
  domain = "admin.vcos.io"
  type = "self_hosted"
  
  session_duration = "24h"
  auto_redirect_to_identity = true
  
  policies = [{
    name = "Admin access"
    decision = "allow"
    include = [{
      email = {
        domain = "vcos.io"
      }
    }]
  }]
}

resource "cloudflare_access_application" "api" {
  zone_id = data.cloudflare_zone.vcos.id
  name = "VCOS API"
  domain = "api.vcos.io"
  type = "self_hosted"
  
  session_duration = "1h"
  auto_redirect_to_identity = false
  
  policies = [{
    name = "Authenticated users"
    decision = "allow"
    include = [{
      email = {
        domain = "vcos.io"
      }
    }]
  }]
}

# =============================================================================
# Cloudflare Workers KV for Session Storage
# =============================================================================

resource "cloudflare_workers_kv_namespace" "sessions" {
  title = "vcos-sessions"
}

resource "cloudflare_workers_kv_namespace" "cache" {
  title = "vcos-cache"
}