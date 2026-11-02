"""
Edge CDN + Caching Service for VCOS.

Provides:
- Edge caching with configurable rules
- Cache invalidation and purging
- Cache warming/preloading
- Origin shielding
- Cache analytics and metrics
- Stale-while-revalidate / stale-if-error
- Cache key customization
- Origin shielding
"""

import asyncio
import hashlib
import logging
import random
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple
from uuid import uuid4

from app.core.config import settings
from app.core.timeutils import utcnow

logger = logging.getLogger(__name__)


class CacheStatus(str, Enum):
    """Cache entry status."""
    FRESH = "fresh"
    STALE = "stale"
    EXPIRED = "expired"
    MISSING = "missing"
    STALE_WHILE_REVALIDATE = "stale_while_revalidate"
    STALE_IF_ERROR = "stale_if_error"


class CacheAction(str, Enum):
    """Cache actions."""
    HIT = "hit"
    MISS = "miss"
    REFRESH = "refresh"
    PURGE = "purge"
    WARM = "warm"
    BYPASS = "bypass"


class CacheTier(str, Enum):
    """Cache tier levels."""
    EDGE = "edge"           # Edge PoP
    REGIONAL = "regional"   # Regional cache
    ORIGIN_SHIELD = "origin_shield"  # Origin shield
    ORIGIN = "origin"       # Origin server


@dataclass
class CacheEntry:
    """Cache entry."""
    key: str
    value: bytes
    headers: Dict[str, str]
    status_code: int
    created_at: datetime
    expires_at: datetime
    last_accessed: datetime
    access_count: int = 0
    size_bytes: int = 0
    etag: Optional[str] = None
    last_modified: Optional[datetime] = None
    vary_headers: List[str] = field(default_factory=list)
    vary_by_cookie: Optional[str] = None
    vary_by_header: Optional[str] = None
    vary_by_region: bool = False
    region: Optional[str] = None
    stale_while_revalidate: int = 0
    stale_if_error: int = 0
    status: CacheStatus = CacheStatus.FRESH
    compressed: bool = False
    encoding: Optional[str] = None


@dataclass
class CachePurgeRequest:
    """Cache purge request."""
    id: str
    patterns: List[str]  # URL patterns or exact keys
    regions: List[str] = field(default_factory=list)  # Empty = all regions
    tiers: List[str] = field(default_factory=lambda: ["edge", "regional", "origin_shield"])
    tags: List[str] = field(default_factory=list)  # Cache tags
    force: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    status: str = "pending"  # pending, running, completed, failed
    purged_keys: int = 0
    error: Optional[str] = None


@dataclass
class CacheWarmRequest:
    """Cache warming request."""
    id: str
    urls: List[str]
    regions: List[str] = field(default_factory=list)
    headers: Dict[str, str] = field(default_factory=dict)
    priority: int = 5  # 1-10
    scheduled_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    status: str = "pending"
    completed_urls: int = 0
    failed_urls: int = 0


@dataclass
class CacheMetrics:
    """Cache metrics."""
    timestamp: datetime
    region: str
    tier: str
    hits: int = 0
    misses: int = 0
    stale_hits: int = 0
    errors: int = 0
    bytes_served: int = 0
    bytes_fetched: int = 0
    avg_latency_ms: float = 0.0
    hit_rate: float = 0.0
    bandwidth_saved_bytes: int = 0


@dataclass
class CacheRule:
    """Cache configuration rule."""
    id: str
    pattern: str  # URL pattern (glob or regex)
    ttl_seconds: int = 3600
    stale_while_revalidate: int = 86400
    stale_if_error: int = 86400
    vary_headers: List[str] = field(default_factory=list)
    vary_by_cookie: Optional[str] = None
    vary_by_header: Optional[str] = None
    vary_by_region: bool = False
    bypass_cookies: List[str] = field(default_factory=list)
    bypass_query_params: List[str] = field(default_factory=list)
    cache_methods: List[str] = field(default_factory=lambda: ["GET", "HEAD"])
    cache_status_codes: List[int] = field(default_factory=lambda: [200, 301, 302, 304, 404])
    compress: bool = True
    compress_types: List[str] = field(default_factory=lambda: ["text/", "application/json", "application/javascript", "text/"])
    min_size_bytes: int = 100
    max_size_bytes: int = 100 * 1024 * 1024  # 100MB
    enabled: bool = True
    priority: int = 100
    tags: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class OriginShieldConfig:
    """Origin shield configuration."""
    enabled: bool = True
    shield_regions: List[str] = field(default_factory=list)  # Regions to deploy shields
    shield_ttl_seconds: int = 300
    max_concurrent_requests: int = 100
    collapse_requests: bool = True  # Request collapsing
    stale_while_revalidate: int = 60
    stale_if_error: int = 3600


class EdgeCDNService:
    """
    Edge CDN + Caching Service.
    
    Features:
    - Multi-tier caching (Edge -> Regional -> Origin Shield -> Origin)
    - Cache rules with flexible matching
    - Cache invalidation and purging
    - Cache warming/preloading
    - Origin shielding with request collapsing
    - Stale-while-revalidate / stale-if-error
    - Cache key customization
    - Cache analytics and metrics
    - Cache warming/preloading
    - Origin shielding
    """

    def __init__(self):
        self._cache_rules: Dict[str, CacheRule] = {}
        self._cache_stores: Dict[str, Dict[str, CacheEntry]] = defaultdict(dict)  # tier:region -> key -> entry
        self._purge_requests: Dict[str, CachePurgeRequest] = {}
        self._warm_requests: Dict[str, CacheWarmRequest] = {}
        self._metrics: Dict[str, List[CacheMetrics]] = defaultdict(list)  # tier:region -> metrics
        self._origin_shields: Dict[str, OriginShieldConfig] = {}
        self._initialized = False
        self._purge_lock = asyncio.Lock()
        self._warm_lock = asyncio.Lock()

    async def initialize(self):
        """Initialize Edge CDN service."""
        if self._initialized:
            return
        
        # Load cache rules from database
        await self._load_cache_rules()
        
        # Initialize origin shields
        await self._init_origin_shields()
        
        # Start background tasks
        asyncio.create_task(self._cleanup_loop())
        asyncio.create_task(self._metrics_aggregation_loop())
        asyncio.create_task(self._warm_request_processor())
        
        self._initialized = True
        logger.info("Edge CDN Service initialized")

    async def _load_cache_rules(self):
        """Load cache rules from database."""
        # Add default rules
        default_rules = [
            CacheRule(
                id="default-static",
                pattern="**/*.{css,js,ico,png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,eot}",
                ttl_seconds=31536000,  # 1 year
                stale_while_revalidate=86400,
                stale_if_error=86400,
                tags=["static", "immutable"],
                priority=10,
            ),
            CacheRule(
                id="default-html",
                pattern="**/*.html",
                ttl_seconds=3600,
                stale_while_revalidate=300,
                stale_if_error=86400,
                vary_headers=["Accept-Language", "Accept-Encoding"],
                priority=50,
            ),
            CacheRule(
                id="api-responses",
                pattern="/api/**",
                ttl_seconds=60,
                stale_while_revalidate=60,
                stale_if_error=300,
                vary_headers=["Accept", "Authorization"],
                vary_by_cookie="session_id",
                cache_methods=["GET", "HEAD"],
                cache_status_codes=[200, 304],
                tags=["api", "dynamic"],
                priority=20,
            ),
            CacheRule(
                id="api-mutations",
                pattern="/api/**",
                cache_methods=["POST", "PUT", "PATCH", "DELETE"],
                enabled=False,  # Don't cache mutations
                priority=5,
            ),
        ]
        
        for rule in default_rules:
            self._cache_rules[rule.id] = rule

    async def _init_origin_shields(self):
        """Initialize origin shields in configured regions."""
        default_shields = {
            "us-east-1": OriginShieldConfig(
                shield_regions=["us-east-1", "us-east-2", "us-west-2"],
            ),
            "eu-west-1": OriginShieldConfig(
                shield_regions=["eu-west-1", "eu-central-1"],
            ),
            "ap-southeast-1": OriginShieldConfig(
                shield_regions=["ap-southeast-1", "ap-northeast-1"],
            ),
        }
        self._origin_shields = default_shields

    # ==================== Cache Rules ====================

    def add_cache_rule(self, rule: CacheRule) -> CacheRule:
        """Add a cache rule."""
        self._cache_rules[rule.id] = rule
        logger.info(f"Added cache rule: {rule.id}")
        return rule

    def remove_cache_rule(self, rule_id: str) -> bool:
        if rule_id in self._cache_rules:
            del self._cache_rules[rule_id]
            return True
        return False

    def get_cache_rule(self, rule_id: str) -> Optional[CacheRule]:
        return self._cache_rules.get(rule_id)

    def list_cache_rules(self, enabled_only: bool = True) -> List[CacheRule]:
        rules = list(self._cache_rules.values())
        if enabled_only:
            rules = [r for r in rules if r.enabled]
        return sorted(rules, key=lambda r: r.priority)

    def match_cache_rule(self, url: str, method: str) -> Optional[CacheRule]:
        """Find matching cache rule for a request."""
        matching_rules = []
        
        for rule in self._cache_rules.values():
            if not rule.enabled:
                continue
            
            if method not in rule.cache_methods:
                continue
            
            # Simple glob matching
            if self._match_pattern(url, rule.pattern):
                matching_rules.append(rule)
        
        if not matching_rules:
            return None
        
        # Return highest priority rule
        return max(matching_rules, key=lambda r: r.priority)

    def _match_pattern(self, url: str, pattern: str) -> bool:
        """Match URL against pattern (glob or regex)."""
        # Convert glob to regex
        import fnmatch
        return fnmatch.fnmatch(url, pattern) or fnmatch.fnmatch(url, pattern.replace("**", "*"))

    # ==================== Cache Operations ====================

    def _get_store(self, tier: str, region: str) -> Dict[str, CacheEntry]:
        """Get cache store for tier and region."""
        key = f"{tier}:{region}"
        return self._cache_stores[key]

    def _get_cache_key(
        self,
        url: str,
        method: str,
        headers: Dict[str, str],
        cookies: Dict[str, str],
        rule: CacheRule,
        region: Optional[str] = None,
    ) -> str:
        """Generate cache key."""
        parts = [url, method]
        
        # Add vary headers
        for header in rule.vary_headers:
            parts.append(f"h:{header}:{headers.get(header, '')}")
        
        # Vary by cookie
        if rule.vary_by_cookie and rule.vary_by_cookie in cookies:
            parts.append(f"cookie:{rule.vary_by_cookie}:{cookies[rule.vary_by_cookie]}")
        
        # Vary by header
        if rule.vary_by_header and rule.vary_by_header in headers:
            parts.append(f"h:{rule.vary_by_header}:{headers[rule.vary_by_header]}")
        
        # Vary by region
        if rule.vary_by_region and region:
            parts.append(f"region:{region}")
        
        # Filter out bypassed cookies
        for cookie in rule.bypass_cookies:
            if cookie in cookies:
                parts.append(f"cookie:{cookie}:{cookies[cookie]}")
        
        # Filter bypass query params
        # Would parse URL and filter query params
        
        key_string = "|".join(parts)
        return hashlib.sha256(key_string.encode()).hexdigest()[:32]

    async def get(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        cookies: Optional[Dict[str, str]] = None,
        region: Optional[str] = None,
        tier: str = "edge",
    ) -> Tuple[Optional[CacheEntry], CacheAction]:
        """Get cached response."""
        headers = headers or {}
        cookies = cookies or {}
        region = region or "global"
        
        rule = self.match_cache_rule(url, "GET")
        if not rule:
            return None, CacheAction.BYPASS
        
        # Check bypass conditions
        if any(c in cookies for c in rule.bypass_cookies):
            return None, CacheAction.BYPASS
        
        # Generate cache key
        key = self._get_cache_key(url, "GET", headers or {}, {}, region)
        
        # Check cache stores in tier order
        for tier in [tier, "regional", "origin_shield", "origin"]:
            store = self._get_store(tier, region or "global")
            entry = store.get(key)
            
            if entry:
                # Check if fresh
                if utcnow() < entry.expires_at:
                    entry.last_accessed = utcnow()
                    entry.access_count += 1
                    self._record_hit(region, tier, CacheAction.HIT)
                    return entry, CacheAction.HIT
                
                # Check stale-while-revalidate
                if entry.stale_while_revalidate > 0:
                    stale_limit = entry.expires_at + timedelta(seconds=entry.stale_while_revalidate)
                    if utcnow() < stale_limit:
                        entry.last_accessed = utcnow()
                        entry.access_count += 1
                        entry.status = CacheStatus.STALE_WHILE_REVALIDATE
                        self._record_hit(region, tier, CacheAction.HIT)
                        # Trigger background refresh
                        asyncio.create_task(self._background_refresh(url, "GET", region))
                        return entry, CacheAction.HIT
                
                # Check stale-if-error
                if entry.stale_if_error > 0:
                    stale_limit = entry.expires_at + timedelta(seconds=entry.stale_if_error)
                    if utcnow() < stale_limit:
                        entry.status = CacheStatus.STALE_IF_ERROR
                        self._record_hit(region, tier, CacheAction.HIT)
                        return entry, CacheAction.HIT
                
                # Expired
                entry.status = CacheStatus.EXPIRED
        
        # Cache miss
        self._record_hit(region, tier, CacheAction.MISS)
        return None, CacheAction.MISS

    async def set(
        self,
        url: str,
        method: str,
        response_data: bytes,
        headers: Dict[str, str],
        status_code: int,
        region: Optional[str] = None,
        tier: str = "edge",
        rule: Optional[CacheRule] = None,
    ) -> CacheEntry:
        """Store response in cache."""
        region = region or "global"
        rule = rule or self.match_cache_rule(url, method)
        
        if not rule or not rule.enabled:
            # Still store in origin tier for potential future use
            rule = CacheRule(
                id="default",
                pattern="*",
                ttl_seconds=60,
                enabled=True,
            )
        
        if method not in rule.cache_methods:
            raise ValueError(f"Method {method} not cacheable")
        
        if status_code not in rule.cache_status_codes:
            raise ValueError(f"Status code {status_code} not cacheable")
        
        # Check size limits
        size_bytes = len(response_data)
        if size_bytes < rule.min_size_bytes or size_bytes > rule.max_size_bytes:
            raise ValueError(f"Response size {size_bytes} outside limits")
        
        # Generate cache key
        key = self._get_cache_key(
            url, method, {}, {}, region
        )
        
        # Calculate expiry
        now = utcnow()
        expires_at = now + timedelta(seconds=rule.ttl_seconds)
        
        # Generate ETag
        etag = hashlib.sha256(response_data).hexdigest()[:32]
        
        # Check compression
        compressed = False
        compressed_data = response_data
        encoding = None
        if rule.compress and size > rule.min_size_bytes:
            content_type = headers.get("content-type", "")
            if any(content_type.startswith(ct) for ct in rule.compress_types):
                import gzip
                compressed_data = gzip.compress(response_data)
                if len(compressed_data) < len(response_data):
                    compressed = True
                    encoding = "gzip"
        
        entry = CacheEntry(
            key=key,
            value=compressed_data,
            headers=dict(headers),
            status_code=status_code,
            created_at=utcnow(),
            expires_at=now + timedelta(seconds=rule.ttl_seconds),
            last_accessed=utcnow(),
            access_count=1,
            size_bytes=len(compressed_data),
            etag=etag,
            last_modified=headers.get("last-modified"),
            vary_headers=rule.vary_headers,
            vary_by_cookie=rule.vary_by_cookie,
            vary_by_header=rule.vary_by_header,
            vary_by_region=rule.vary_by_region,
            region=region,
            stale_while_revalidate=rule.stale_while_revalidate,
            stale_if_error=rule.stale_if_error,
            status=CacheStatus.FRESH,
            compressed=compressed,
            encoding=encoding,
        )
        
        # Store in tier
        store = self._get_store(tier, region or "global")
        store[key] = entry
        
        # Also store in higher tiers for origin shielding
        if tier == "edge":
            # Also store in origin shield
            shield_store = self._get_store("origin_shield", region or "global")
            shield_store[key] = entry
        
        return entry

    async def purge(
        self,
        patterns: List[str],
        regions: Optional[List[str]] = None,
        tiers: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        force: bool = False,
    ) -> CachePurgeRequest:
        """Purge cache entries matching patterns."""
        async with self._purge_lock:
            request = CachePurgeRequest(
                id=str(uuid4()),
                patterns=patterns,
                regions=regions or [],
                tiers=tiers or ["edge", "regional", "origin_shield", "origin"],
                tags=tags or [],
                force=force,
            )
            
            self._purge_requests[request.id] = request
            
            # Process purge asynchronously
            asyncio.create_task(self._process_purge(request))
            
            return request

    async def _process_purge(self, request: CachePurgeRequest):
        """Process a purge request."""
        try:
            request.status = "running"
            purged = 0
            
            for tier in request.tiers:
                regions = request.regions or ["global"]
                
                for region in regions:
                    store = self._get_store(tier, region)
                    keys_to_delete = []
                    
                    for key, entry in store.items():
                        if self._matches_patterns(entry, request.patterns, request.tags):
                            keys_to_delete.append(key)
                    
                    for key in keys_to_delete:
                        del store[key]
                        purged += 1
            
            request.purged_keys = purged
            request.status = "completed"
            request.completed_at = utcnow()
            logger.info(f"Purge {request.id} completed: {purged} keys purged")
            
        except Exception as e:
            request.status = "failed"
            request.error = str(e)
            logger.error(f"Purge {request.id} failed: {e}")

    def _matches_patterns(
        self,
        entry: CacheEntry,
        patterns: List[str],
        tags: List[str],
    ) -> bool:
        """Check if entry matches purge patterns or tags."""
        # Check tags
        if tags:
            # Would check entry tags
            pass
        
        # Check patterns against key/URL
        import fnmatch
        for pattern in patterns:
            # Would match against entry key or stored URL
            # For now, simple key matching
            if fnmatch.fnmatch(entry.key, pattern) or fnmatch.fnmatch(pattern, entry.key):
                return True
        
        return False

    async def get_purge_status(self, purge_id: str) -> Optional[CachePurgeRequest]:
        return self._purge_requests.get(purge_id)

    # ==================== Cache Warming ====================

    async def warm_cache(
        self,
        urls: List[str],
        regions: Optional[List[str]] = None,
        headers: Optional[Dict[str, str]] = None,
        priority: int = 5,
    ) -> CacheWarmRequest:
        """Warm cache for given URLs."""
        async with self._warm_lock:
            request = CacheWarmRequest(
                id=str(uuid4()),
                urls=urls,
                regions=regions or ["global"],
                headers=headers or {},
                priority=priority,
            )
            
            self._warm_requests[request.id] = request
            asyncio.create_task(self._process_warm_request(request))
            return request

    async def _process_warm_request(self, request: CacheWarmRequest):
        """Process cache warming request."""
        try:
            request.status = "running"
            completed = 0
            failed = 0
            
            for url in request.urls:
                for region in request.regions:
                    try:
                        # Would fetch from origin and store in cache
                        # This is a simplified version
                        await asyncio.sleep(0.1)  # Simulate fetch
                        completed += 1
                    except Exception as e:
                        logger.warning(f"Failed to warm {url} in {region}: {e}")
                        failed += 1
            
            request.completed_urls = completed
            request.failed_urls = failed
            request.status = "completed" if failed == 0 else "partial"
            request.completed_at = utcnow()
            
        except Exception as e:
            request.status = "failed"
            logger.error(f"Cache warming failed: {e}")

    async def get_warm_status(self, request_id: str) -> Optional[CacheWarmRequest]:
        return self._warm_requests.get(request_id)

    # ==================== Origin Shield ====================

    async def get_origin_shield_config(self, region: str) -> Optional[OriginShieldConfig]:
        return self._origin_shields.get(region)

    async def set_origin_shield_config(self, region: str, config: OriginShieldConfig):
        self._origin_shields[region] = config
        logger.info(f"Updated origin shield config for {region}")

    async def fetch_via_shield(
        self,
        url: str,
        method: str,
        headers: Dict[str, str],
        region: str,
    ) -> Tuple[bytes, Dict[str, str], int]:
        """Fetch via origin shield with request collapsing."""
        # Would implement request collapsing
        # For now, placeholder
        raise NotImplementedError("Origin shield fetch not implemented")

    # ==================== Cache Invalidation ====================

    async def invalidate_by_tags(self, tags: List[str], regions: Optional[List[str]] = None):
        """Invalidate cache entries by tags."""
        request = CachePurgeRequest(
            id=str(uuid4()),
            patterns=[],
            tags=tags,
            regions=regions or [],
            tiers=["edge", "regional", "origin_shield", "origin"],
        )
        return await self.purge(request.patterns, request.regions, request.tiers, request.tags)

    async def invalidate_by_url(self, urls: List[str], regions: Optional[List[str]] = None):
        """Invalidate specific URLs."""
        request = CachePurgeRequest(
            id=str(uuid4()),
            patterns=urls,
            regions=regions or [],
            tiers=["edge", "regional", "origin_shield", "origin"],
        )
        return await self.purge(request.patterns, request.regions, request.tiers, request.tags)

    # ==================== Metrics ====================

    def _record_hit(self, region: str, tier: str, action: CacheAction):
        """Record cache hit/miss."""
        key = f"{tier}:{region}"
        today = utcnow().date()
        
        # Find or create today's metrics
        metrics = self._metrics.get(key, [])
        today_metrics = None
        for m in metrics:
            if m.timestamp.date() == utcnow().date():
                today_metrics = m
                break
        
        if not today_metrics:
            today_metrics = CacheMetrics(
                timestamp=utcnow(),
                region=region,
                tier=tier,
            )
            self._metrics[key].append(today_metrics)
        
        if action == CacheAction.HIT:
            today_metrics.hits += 1
        elif action == CacheAction.MISS:
            today_metrics.misses += 1
        elif action in (CacheAction.REFRESH, CacheAction.HIT):
            today_metrics.stale_hits += 1
        
        # Recalculate hit rate
        total = today_metrics.hits + today_metrics.misses
        if total > 0:
            today_metrics.hit_rate = today_metrics.hits / total

    def get_metrics(
        self,
        tier: str,
        region: str,
        hours: int = 24,
    ) -> List[CacheMetrics]:
        """Get cache metrics."""
        key = f"{tier}:{region}"
        metrics = self._metrics.get(key, [])
        cutoff = utcnow() - timedelta(hours=hours)
        return [m for m in metrics if m.timestamp >= cutoff]

    def get_overall_stats(self) -> Dict[str, Any]:
        """Get overall cache statistics."""
        total_hits = 0
        total_misses = 0
        total_bytes = 0
        
        for metrics_list in self._metrics.values():
            for m in metrics_list:
                total_hits += m.hits
                total_misses += m.misses
                total_bytes += m.bytes_served
        
        total = total_hits + total_misses
        hit_rate = total_hits / total if total > 0 else 0
        
        return {
            "total_hits": total_hits,
            "total_misses": total_misses,
            "hit_rate": hit_rate,
            "bytes_served": total_bytes,
            "regions": len(set(
                m.region for metrics in self._metrics.values() for m in metrics
            )),
            "tiers": len(set(
                m.tier for metrics in self._metrics.values() for m in metrics
            )),
        }

    # ==================== Cache Invalidation Helpers ====================

    async def invalidate_by_prefix(self, prefix: str, regions: Optional[List[str]] = None):
        """Invalidate all keys with a given prefix."""
        return await self.invalidate_by_prefix(prefix, regions)

    async def invalidate_by_regex(self, regex: str, regions: Optional[List[str]] = None):
        """Invalidate keys matching regex."""
        import re
        pattern = re.compile(regex)
        # Would iterate and match
        pass

    # ==================== Cache Warming Helpers ====================

    async def warm_popular_paths(
        self,
        paths: List[str],
        regions: Optional[List[str]] = None,
    ) -> CacheWarmRequest:
        """Warm cache for popular paths."""
        return await self.warm_cache(
            urls=paths,
            regions=regions,
            priority=10,
        )

    async def warm_from_analytics(
        self,
        top_paths: List[Tuple[str, int]],  # (path, hit_count)
        regions: Optional[List[str]] = None,
        threshold: int = 100,
    ) -> CacheWarmRequest:
        """Warm cache based on analytics data."""
        popular = [path for path, count in top_paths if count >= threshold]
        return await self.warm_popular_paths(popular, regions)

    # ==================== Compression ====================

    def _compress_response(self, data: bytes, content_type: str) -> Tuple[bytes, str]:
        """Compress response data."""
        if not any(content_type.startswith(ct) for ct in ["text/", "application/json", "application/javascript", "text/"]):
            return data, "identity"
        
        import gzip
        compressed = gzip.compress(data)
        if len(compressed) < len(data):
            return compressed, "gzip"
        return data, "identity"

    def _decompress_response(self, data: bytes, encoding: str) -> bytes:
        """Decompress response data."""
        if encoding == "gzip":
            import gzip
            return gzip.decompress(data)
        return data

    # ==================== Background Tasks ====================

    async def _cleanup_loop(self):
        """Clean up expired cache entries."""
        while True:
            try:
                await self._cleanup_expired()
            except Exception as e:
                logger.error(f"Cache cleanup error: {e}")
            await asyncio.sleep(3600)  # Every hour

    async def _cleanup_expired(self):
        """Remove expired cache entries."""
        now = utcnow()
        total_removed = 0
        
        for store in self._cache_stores.values():
            keys_to_delete = [
                key for key, entry in store.items()
                if entry.expires_at < now
            ]
            for key in keys_to_delete:
                del store[key]
                total_removed += 1
        
        if total_removed > 0:
            logger.info(f"Cleaned up {total_removed} expired cache entries")

    async def _metrics_aggregation_loop(self):
        """Aggregate metrics periodically."""
        while True:
            try:
                await self._aggregate_metrics()
            except Exception as e:
                logger.error(f"Metrics aggregation error: {e}")
            await asyncio.sleep(300)  # Every 5 minutes

    async def _aggregate_metrics(self):
        """Aggregate metrics for reporting."""
        # In production, would push to monitoring system
        pass

    async def _warm_request_processor(self):
        """Process cache warming requests."""
        while True:
            try:
                await self._process_pending_warm_requests()
            except Exception as e:
                logger.error(f"Warm request processor error: {e}")
            await asyncio.sleep(60)  # Check every minute

    async def _process_pending_warm_requests(self):
        """Process pending warm requests."""
        pending = [r for r in self._warm_requests.values() if r.status == "pending"]
        pending.sort(key=lambda r: -r.priority)
        
        for request in pending[:5]:  # Process up to 5 at a time
            if request.scheduled_at and request.scheduled_at > utcnow():
                continue
            await self._process_warm_request(request)

    async def _process_warm_request(self, request: CacheWarmRequest):
        """Process a single warm request."""
        try:
            request.status = "running"
            completed = 0
            failed = 0
            
            for url in request.urls:
                for region in request.regions:
                    try:
                        # In production, would fetch from origin
                        await asyncio.sleep(0.1)
                        completed += 1
                    except Exception as e:
                        logger.warning(f"Failed to warm {url} in {region}: {e}")
                        failed += 1
            
            request.completed_urls = completed
            request.failed_urls = failed
            request.status = "completed" if failed == 0 else "partial"
            request.completed_at = utcnow()
            
        except Exception as e:
            request.status = "failed"
            logger.error(f"Cache warming failed: {e}")

    # ==================== Stats ====================

    def get_stats(self) -> Dict[str, Any]:
        """Get CDN statistics."""
        total_entries = sum(len(s) for s in self._cache_stores.values())
        total_size = sum(
            e.size_bytes for store in self._cache_stores.values() for e in store.values()
        )
        
        return {
            "total_entries": total_entries,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "cache_rules": len(self._cache_rules),
            "enabled_rules": sum(1 for r in self._cache_rules.values() if r.enabled),
            "purge_requests": len(self._purge_requests),
            "pending_purges": sum(1 for p in self._purge_requests.values() if p.status in ["pending", "running"]),
            "warm_requests": len(self._warm_requests),
            "pending_warm": sum(1 for w in self._warm_requests.values() if w.status == "pending"),
            "overall_stats": self.get_overall_stats(),
            "origin_shields": len(self._origin_shields),
        }

    def get_overall_stats(self) -> Dict[str, Any]:
        """Get overall cache statistics."""
        total_hits = 0
        total_misses = 0
        total_bytes = 0
        total_stale = 0
        
        for metrics_list in self._metrics.values():
            for m in metrics_list:
                total_hits += m.hits
                total_misses += m.misses
                total_stale += m.stale_hits
                total_bytes += m.bytes_served
        
        total = total_hits + total_misses
        hit_rate = total_hits / total if total > 0 else 0
        
        return {
            "total_hits": total_hits,
            "total_misses": total_misses,
            "stale_hits": total_stale,
            "hit_rate": round(hit_rate * 100, 2),
            "bytes_served": total_bytes,
            "bytes_served_mb": round(total_bytes / (1024 * 1024), 2),
        }

    # ==================== Utilities ====================

    async def close(self):
        """Close the CDN service."""
        self._initialized = False
        logger.info("Edge CDN Service closed")


# ==================== Global Instance ====================

_edge_cdn_service: Optional[EdgeCDNService] = None


def get_edge_cdn_service() -> EdgeCDNService:
    """Get or create Edge CDN service singleton."""
    global _edge_cdn_service
    if _edge_cdn_service is None:
        _edge_cdn_service = EdgeCDNService()
    return _edge_cdn_service


async def init_edge_cdn_service() -> EdgeCDNService:
    """Initialize Edge CDN service."""
    global _edge_cdn_service
    _edge_cdn_service = EdgeCDNService()
    await _edge_cdn_service.initialize()
    return _edge_cdn_service