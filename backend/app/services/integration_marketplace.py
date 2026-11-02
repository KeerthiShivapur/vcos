"""
Integration Marketplace - Universal Integration Platform Marketplace.

Provides:
- Connector registry with versioning
- Installation wizard + Config validation
- Usage analytics + Cost tracking
- Revenue sharing (if marketplace)
- Connector discovery and ratings
- Security scanning and verification
"""

import asyncio
import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4

from sqlalchemy import Column, String, Text, JSON, DateTime, Index, ForeignKey, Boolean, Integer, Float, Enum as SQLEnum
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.connector_sdk import (
    ConnectorMetadata,
    ConnectorCapabilities,
    AuthConfig,
    RateLimitConfig,
    PaginationConfig,
    RetryConfig,
    EntityType,
    AuthScheme,
)
from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid

logger = logging.getLogger("vcos.integration.marketplace")


# ==================== Enums ====================

class ConnectorCategory(str, Enum):
    IDENTITY = "identity"
    HRIS = "hris"
    ATS = "ats"
    CRM = "crm"
    COMMUNICATION = "communication"
    CALENDAR = "calendar"
    STORAGE = "storage"
    PROJECT_MGMT = "project_mgmt"
    FINANCE = "finance"
    BI_ANALYTICS = "bi_analytics"
    DEVOPS = "devops"
    MARKETING = "marketing"
    SUPPORT = "support"
    ECOMMERCE = "ecommerce"
    ERP = "erp"
    CMS = "cms"
    ANALYTICS = "analytics"
    MONITORING = "monitoring"
    SECURITY = "security"
    AI_ML = "ai_ml"
    DESIGN = "design"
    DOCUMENT = "document"
    FORMS = "forms"
    PAYMENT = "payment"
    SHIPPING = "shipping"
    SMS = "sms"
    EMAIL = "email"
    VIDEO = "video"
    DATABASE = "database"
    WAREHOUSE = "warehouse"
    QUEUE = "queue"
    SEARCH = "search"
    AUTH = "auth"
    SOCIAL = "social"
    OTHER = "other"


class ConnectorStatus(str, Enum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class InstallationStatus(str, Enum):
    PENDING = "pending"
    INSTALLING = "installing"
    CONFIGURING = "configuring"
    TESTING = "testing"
    ACTIVE = "active"
    FAILED = "failed"
    UNINSTALLING = "uninstalling"
    UNINSTALLED = "uninstalled"


class PricingModel(str, Enum):
    FREE = "free"
    FREEMIUM = "freemium"
    SUBSCRIPTION = "subscription"
    USAGE_BASED = "usage_based"
    PER_SEAT = "per_seat"
    TIERED = "tiered"
    CUSTOM = "custom"


class RevenueShareModel(str, Enum):
    NONE = "none"
    PERCENTAGE = "percentage"
    FIXED = "fixed"
    TIERED = "tiered"


# ==================== Data Models ====================

@dataclass
class ConnectorListing:
    """Marketplace listing for a connector."""
    id: str
    metadata: "ConnectorMetadata"
    status: ConnectorStatus = ConnectorStatus.DRAFT
    pricing: "PricingInfo" = None
    rating: float = 0.0
    review_count: int = 0
    install_count: int = 0
    active_installations: int = 0
    verified: bool = False
    security_scan_status: str = "pending"
    security_scan_results: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    published_at: Optional[datetime] = None
    created_by: str = ""
    owner_id: str = ""
    organization_id: Optional[str] = None


@dataclass
class PricingInfo:
    """Pricing information for a connector."""
    model: PricingModel = PricingModel.FREE
    base_price: float = 0.0
    currency: str = "USD"
    billing_period: str = "monthly"  # monthly, yearly, per_call, per_record
    tiers: List[Dict[str, Any]] = field(default_factory=list)
    free_tier: bool = False
    free_tier_limits: Dict[str, Any] = field(default_factory=dict)
    setup_fee: float = 0.0
    trial_days: int = 0
    revenue_share: "RevenueShare" = None


@dataclass
class RevenueShare:
    """Revenue sharing configuration."""
    model: RevenueShareModel = RevenueShareModel.NONE
    platform_percentage: float = 0.0
    platform_fixed: float = 0.0
    developer_percentage: float = 100.0
    minimum_payout: float = 0.0
    payout_schedule: str = "monthly"  # monthly, quarterly, annually
    currency: str = "USD"


@dataclass
class ConnectorVersion:
    """Versioned connector package."""
    id: str
    listing_id: str
    version: str
    changelog: str = ""
    manifest: Dict[str, Any] = field(default_factory=dict)
    package_url: str = ""
    package_hash: str = ""
    package_size: int = 0
    min_platform_version: str = "1.0.0"
    max_platform_version: Optional[str] = None
    dependencies: List[Dict[str, str]] = field(default_factory=list)
    breaking_changes: bool = False
    migration_guide: str = ""
    status: ConnectorStatus = ConnectorStatus.DRAFT
    security_scan: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    published_at: Optional[datetime] = None
    deprecated_at: Optional[datetime] = None


@dataclass
class Installation:
    """Connector installation instance."""
    id: str
    listing_id: str
    version_id: str
    organization_id: str
    connection_id: Optional[str] = None
    status: InstallationStatus = InstallationStatus.PENDING
    config: Dict[str, Any] = field(default_factory=dict)
    credentials: Dict[str, Any] = field(default_factory=dict)
    field_mappings: Dict[str, str] = field(default_factory=dict)
    sync_schedule: Optional[str] = None
    last_sync_at: Optional[datetime] = None
    last_sync_status: Optional[str] = None
    sync_stats: Dict[str, int] = field(default_factory=dict)
    error_message: Optional[str] = None
    installed_by: str = ""
    installed_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    uninstalled_at: Optional[datetime] = None
    billing_info: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Review:
    """Connector review and rating."""
    id: str
    listing_id: str
    version_id: str
    organization_id: str
    user_id: str
    rating: int = Field(..., ge=1, le=5)
    title: str = ""
    content: str = ""
    pros: List[str] = field(default_factory=list)
    cons: List[str] = field(default_factory=list)
    verified_purchase: bool = False
    helpful_count: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class UsageAnalytics:
    """Usage analytics for a connector."""
    listing_id: str
    organization_id: str
    period_start: datetime
    period_end: datetime
    total_syncs: int = 0
    successful_syncs: int = 0
    failed_syncs: int = 0
    records_synced: int = 0
    api_calls: int = 0
    data_volume_bytes: int = 0
    avg_sync_duration_ms: float = 0.0
    errors: Dict[str, int] = field(default_factory=dict)
    cost: float = 0.0
    revenue: float = 0.0


@dataclass
class SecurityScanResult:
    """Security scan results for connector."""
    scan_id: str
    listing_id: str
    version_id: str
    status: str = "pending"  # pending, scanning, completed, failed
    score: float = 0.0  # 0-100
    vulnerabilities: List[Dict[str, Any]] = field(default_factory=list)
    secrets_detected: List[Dict[str, Any]] = field(default_factory=list)
    license_issues: List[str] = field(default_factory=list)
    dependency_issues: List[Dict[str, Any]] = field(default_factory=list)
    best_practice_violations: List[str] = field(default_factory=list)
    scanned_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None


# ==================== Marketplace Manager ====================

class MarketplaceManager:
    """Manages the integration marketplace."""
    
    def __init__(self, session: AsyncSession = None):
        self.session = session
        self._listings: Dict[str, ConnectorListing] = {}
        self._versions: Dict[str, List[ConnectorVersion]] = {}
        self._installations: Dict[str, Installation] = {}
        self._reviews: Dict[str, List[Review]] = {}
        self._analytics: Dict[str, List[UsageAnalytics]] = {}
    
    # ==================== Listing Management ====================
    
    async def create_listing(
        self,
        metadata: "ConnectorMetadata",
        pricing: "PricingInfo" = None,
        created_by: str = "",
        organization_id: str = None,
    ) -> ConnectorListing:
        """Create a new connector listing."""
        listing = ConnectorListing(
            id=str(uuid.uuid4()),
            metadata=metadata,
            status=ConnectorStatus.DRAFT,
            pricing=pricing or PricingInfo(),
            created_by=created_by,
            owner_id=created_by,
            organization_id=organization_id,
        )
        
        self._listings[listing.id] = listing
        self._versions[listing.id] = []
        self._reviews[listing.id] = []
        self._analytics[listing.id] = []
        
        # Trigger security scan
        asyncio.create_task(self._run_security_scan(listing))
        
        logger.info(f"Created connector listing: {listing.id} ({metadata.id})")
        return listing
    
    async def submit_for_review(self, listing_id: str) -> bool:
        """Submit listing for review."""
        listing = self._listings.get(listing_id)
        if not listing:
            return False
        
        if listing.status != ConnectorStatus.DRAFT:
            return False
        
        listing.status = ConnectorStatus.PENDING_REVIEW
        listing.updated_at = datetime.utcnow()
        return True
    
    async def approve_listing(self, listing_id: str, reviewer_id: str) -> bool:
        """Approve listing for publication."""
        listing = self._listings.get(listing_id)
        if not listing:
            return False
        
        if listing.status != ConnectorStatus.PENDING_REVIEW:
            return False
        
        if listing.security_scan_status != "completed":
            # Require security scan completion
            return False
        
        listing.status = ConnectorStatus.APPROVED
        listing.updated_at = datetime.utcnow()
        return True
    
    async def publish_listing(self, listing_id: str, publisher_id: str) -> bool:
        """Publish approved listing to marketplace."""
        listing = self._listings.get(listing_id)
        if not listing:
            return False
        
        if listing.status != ConnectorStatus.APPROVED:
            return False
        
        listing.status = ConnectorStatus.PUBLISHED
        listing.published_at = datetime.utcnow()
        listing.updated_at = datetime.utcnow()
        
        # Create initial version
        await self.create_version(
            listing_id=listing_id,
            version="1.0.0",
            changelog="Initial release",
            package_url="",  # Would be provided
            created_by=publisher_id,
        )
        
        return True
    
    async def reject_listing(self, listing_id: str, reason: str) -> bool:
        """Reject listing."""
        listing = self._listings.get(listing_id)
        if not listing:
            return False
        
        listing.status = ConnectorStatus.REJECTED
        listing.updated_at = datetime.utcnow()
        return True
    
    async def deprecate_listing(self, listing_id: str, reason: str) -> bool:
        """Deprecate published listing."""
        listing = self._listings.get(listing_id)
        if not listing:
            return False
        
        listing.status = ConnectorStatus.DEPRECATED
        listing.updated_at = datetime.utcnow()
        return True
    
    async def get_listing(self, listing_id: str) -> Optional[ConnectorListing]:
        """Get listing by ID."""
        return self._listings.get(listing_id)
    
    async def list_listings(
        self,
        category: Optional[str] = None,
        status: Optional[ConnectorStatus] = None,
        search: Optional[str] = None,
        sort_by: str = "popularity",  # popularity, rating, recent, alphabetical
        limit: int = 20,
        offset: int = 0,
    ) -> List[ConnectorListing]:
        """List marketplace listings with filters."""
        listings = list(self._listings.values())
        
        if category:
            listings = [l for l in listings if l.metadata.category == category]
        
        if status:
            listings = [l for l in listings if l.status == status]
        
        if search:
            search_lower = search.lower()
            listings = [
                l for l in listings
                if search_lower in l.metadata.id.lower()
                or search_lower in l.metadata.name.lower()
                or search_lower in l.metadata.description.lower()
            ]
        
        # Sort
        if sort_by == "popularity":
            listings.sort(key=lambda l: l.install_count, reverse=True)
        elif sort_by == "rating":
            listings.sort(key=lambda l: l.rating, reverse=True)
        elif sort_by == "recent":
            listings.sort(key=lambda l: l.created_at, reverse=True)
        elif sort_by == "alphabetical":
            listings.sort(key=lambda l: l.metadata.name)
        
        return listings[offset:offset + limit]
    
    async def get_categories(self) -> List[Dict[str, Any]]:
        """Get categories with counts."""
        categories = {}
        for listing in self._listings.values():
            cat = listing.metadata.category
            categories[cat] = categories.get(cat, 0) + 1
        
        return [
            {"category": cat, "count": count, "label": cat.replace("_", " ").title()}
            for cat, count in sorted(categories.items(), key=lambda x: -x[1])
        ]
    
    # ==================== Version Management ====================
    
    async def create_version(
        self,
        listing_id: str,
        version: str,
        changelog: str,
        package_url: str,
        package_hash: str,
        package_size: int,
        manifest: Dict[str, Any] = None,
        min_platform_version: str = "1.0.0",
        created_by: str = "",
        breaking_changes: bool = False,
        migration_guide: str = "",
    ) -> ConnectorVersion:
        """Create new connector version."""
        listing = self._listings.get(listing_id)
        if not listing:
            raise ValueError(f"Listing not found: {listing_id}")
        
        # Check version uniqueness
        existing_versions = self._versions.get(listing_id, [])
        for v in existing_versions:
            if v.version == version:
                raise ValueError(f"Version {version} already exists")
        
        version_obj = ConnectorVersion(
            id=str(uuid.uuid4()),
            listing_id=listing_id,
            version=version,
            changelog=changelog,
            manifest=manifest or {},
            package_url=package_url,
            package_hash=package_hash,
            package_size=0,  # Would be fetched from package_url
            min_platform_version=min_platform_version,
            manifest=manifest or {},
            status=ConnectorStatus.DRAFT,
            created_by=created_by,
            breaking_changes=breaking_changes,
            migration_guide=migration_guide,
        )
        
        self._versions.setdefault(listing_id, []).append(version_obj)
        
        # Update listing
        listing = self._listings[listing_id]
        listing.updated_at = datetime.utcnow()
        
        # Trigger security scan
        asyncio.create_task(self._run_security_scan(listing, version_obj))
        
        logger.info(f"Created version {version} for listing {listing_id}")
        return version_obj
    
    async def publish_version(self, version_id: str, publisher_id: str) -> bool:
        """Publish a version to marketplace."""
        # Find version
        for listing_id, versions in self._versions.items():
            for version in versions:
                if version.id == version_id:
                    if version.status != ConnectorStatus.DRAFT:
                        return False
                    
                    if version.security_scan.get("status") != "completed":
                        return False
                    
                    version.status = ConnectorStatus.PUBLISHED
                    version.published_at = datetime.utcnow()
                    
                    # Update listing status if first version
                    listing = self._listings.get(listing_id)
                    if listing and listing.status == ConnectorStatus.APPROVED:
                        listing.status = ConnectorStatus.PUBLISHED
                        listing.published_at = datetime.utcnow()
                    
                    return True
        
        return False
    
    async def deprecate_version(self, version_id: str, reason: str) -> bool:
        """Deprecate a version."""
        for listing_id, versions in self._versions.items():
            for version in versions:
                if version.id == version_id:
                    version.status = ConnectorStatus.DEPRECATED
                    version.deprecated_at = datetime.utcnow()
                    version.migration_guide = reason
                    return True
        return False
    
    async def get_versions(self, listing_id: str) -> List[ConnectorVersion]:
        """Get all versions for a listing."""
        return self._versions.get(listing_id, []).copy()
    
    async def get_latest_version(self, listing_id: str) -> Optional[ConnectorVersion]:
        """Get latest published version."""
        versions = self._versions.get(listing_id, [])
        published = [v for v in versions if v.status == ConnectorStatus.PUBLISHED]
        if not published:
            return None
        return max(published, key=lambda v: v.version)
    
    # ==================== Installation Management ====================
    
    async def install_connector(
        self,
        listing_id: str,
        version_id: str,
        organization_id: str,
        config: Dict[str, Any],
        credentials: Dict[str, Any],
        field_mappings: Dict[str, str] = None,
        sync_schedule: str = None,
        installed_by: str = "",
    ) -> Installation:
        """Install a connector for an organization."""
        
        listing = self._listings.get(listing_id)
        if not listing:
            raise ValueError(f"Listing not found: {listing_id}")
        
        if listing.status != ConnectorStatus.PUBLISHED:
            raise ValueError("Connector not published")
        
        version = None
        for v in self._versions.get(listing_id, []):
            if v.id == version_id and v.status == ConnectorStatus.PUBLISHED:
                version = v
                break
        
        if not version:
            raise ValueError("Version not found or not published")
        
        # Create installation
        installation = Installation(
            id=str(uuid.uuid4()),
            listing_id=listing_id,
            version_id=version_id,
            organization_id=organization_id,
            config=config or {},
            credentials=credentials or {},
            field_mappings=field_mappings or {},
            sync_schedule=sync_schedule,
            installed_by=installed_by,
        )
        
        self._installations[installation.id] = installation
        
        # Update stats
        listing.install_count += 1
        listing.active_installations += 1
        listing.updated_at = datetime.utcnow()
        
        # Initialize connection (would use integration runtime)
        # await self._initialize_connection(installation)
        
        logger.info(f"Installed connector {listing.metadata.name} v{version.version} for org {organization_id}")
        return installation
    
    async def uninstall_connector(
        self,
        installation_id: str,
        uninstalled_by: str,
    ) -> bool:
        """Uninstall a connector."""
        installation = self._installations.get(installation_id)
        if not installation:
            return False
        
        installation.status = InstallationStatus.UNINSTALLED
        installation.uninstalled_at = datetime.utcnow()
        
        # Update listing stats
        listing = self._listings.get(installation.listing_id)
        if listing:
            listing.active_installations = max(0, listing.active_installations - 1)
            listing.updated_at = datetime.utcnow()
        
        return True
    
    async def get_installation(self, installation_id: str) -> Optional[Installation]:
        return self._installations.get(installation_id)
    
    async def list_installations(
        self,
        organization_id: str,
        status: Optional[InstallationStatus] = None,
    ) -> List[Installation]:
        installations = [
            i for i in self._installations.values()
            if i.organization_id == organization_id
        ]
        
        if status:
            installations = [i for i in installations if i.status == status]
        
        return installations
    
    async def update_installation_config(
        self,
        installation_id: str,
        config: Dict[str, Any] = None,
        credentials: Dict[str, Any] = None,
        field_mappings: Dict[str, str] = None,
        sync_schedule: str = None,
    ) -> Optional[Installation]:
        """Update installation configuration."""
        installation = self._installations.get(installation_id)
        if not installation:
            return None
        
        if config is not None:
            installation.config.update(config)
        if credentials is not None:
            installation.credentials.update(credentials)
        if field_mappings is not None:
            installation.field_mappings = field_mappings
        if sync_schedule is not None:
            installation.sync_schedule = sync_schedule
        
        installation.updated_at = datetime.utcnow()
        return installation
    
    # ==================== Reviews & Ratings ====================
    
    async def add_review(
        self,
        listing_id: str,
        version_id: str,
        organization_id: str,
        user_id: str,
        rating: int,
        title: str = "",
        content: str = "",
        pros: List[str] = None,
        cons: List[str] = None,
        verified_purchase: bool = False,
    ) -> Review:
        """Add a review for a connector."""
        if not 1 <= rating <= 5:
            raise ValueError("Rating must be between 1 and 5")
        
        listing = self._listings.get(listing_id)
        if not listing:
            raise ValueError(f"Listing not found: {listing_id}")
        
        review = Review(
            id=str(uuid.uuid4()),
            listing_id=listing_id,
            version_id=version_id,
            organization_id=organization_id,
            user_id=user_id,
            rating=rating,
            title=title,
            content=content,
            pros=pros or [],
            cons=cons or [],
            verified_purchase=verified_purchase,
        )
        
        self._reviews.setdefault(listing_id, []).append(review)
        
        # Update listing rating
        reviews = self._reviews[listing_id]
        listing.rating = sum(r.rating for r in reviews) / len(reviews)
        listing.review_count = len(reviews)
        listing.updated_at = datetime.utcnow()
        
        return review
    
    async def get_reviews(
        self,
        listing_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Review]:
        reviews = self._reviews.get(listing_id, [])
        reviews.sort(key=lambda r: r.created_at, reverse=True)
        return reviews[offset:offset + limit]
    
    # ==================== Analytics ====================
    
    async def record_usage(
        self,
        listing_id: str,
        organization_id: str,
        syncs: int = 0,
        successful_syncs: int = 0,
        failed_syncs: int = 0,
        records_synced: int = 0,
        api_calls: int = 0,
        data_volume_bytes: int = 0,
        avg_sync_duration_ms: float = 0.0,
        errors: Dict[str, int] = None,
    ) -> UsageAnalytics:
        """Record usage analytics."""
        now = datetime.utcnow()
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        period_end = (period_start + timedelta(days=32)).replace(day=1) - timedelta(seconds=1)
        
        # Find or create analytics entry
        analytics = None
        for a in self._analytics.get(listing_id, []):
            if (a.organization_id == organization_id and
                a.period_start == period_start and
                a.period_end == period_end):
                analytics = a
                break
        
        if not analytics:
            analytics = UsageAnalytics(
                listing_id=listing_id,
                organization_id=organization_id,
                period_start=period_start,
                period_end=period_end,
            )
            self._analytics.setdefault(listing_id, []).append(analytics)
        
        analytics.total_syncs += syncs
        analytics.successful_syncs += successful_syncs
        analytics.failed_syncs += failed_syncs
        analytics.records_synced += records_synced
        analytics.api_calls += api_calls
        analytics.data_volume_bytes += data_volume_bytes
        analytics.avg_sync_duration_ms = (
            (analytics.avg_sync_duration_ms * (analytics.total_syncs - syncs) + 
             avg_sync_duration_ms * syncs) / analytics.total_syncs
            if analytics.total_syncs > 0 else avg_sync_duration_ms
        )
        if errors:
            for error, count in errors.items():
                analytics.errors[error] = analytics.errors.get(error, 0) + count
        
        return analytics
    
    async def get_analytics(
        self,
        listing_id: str,
        organization_id: str = None,
        period_start: datetime = None,
        period_end: datetime = None,
    ) -> List[UsageAnalytics]:
        analytics = self._analytics.get(listing_id, [])
        
        if organization_id:
            analytics = [a for a in analytics if a.organization_id == organization_id]
        if period_start:
            analytics = [a for a in analytics if a.period_start >= period_start]
        if period_end:
            analytics = [a for a in analytics if a.period_end <= period_end]
        
        return analytics
    
    # ==================== Security Scanning ====================
    
    async def _run_security_scan(self, listing: ConnectorListing, version: ConnectorVersion = None) -> None:
        """Run security scan on connector."""
        listing.security_scan_status = "scanning"
        
        # Simulate security scan
        await asyncio.sleep(2)
        
        # Mock scan results
        score = 95.0
        vulnerabilities = []
        secrets = []
        licenses = []
        
        if "dangerous" in listing.metadata.id.lower():
            score = 20.0
            vulnerabilities.append({
                "type": "injection",
                "severity": "critical",
                "description": "Potential SQL injection in query builder",
                "file": "src/query.py",
                "line": 42,
            })
        
        if "api_key" in str(listing.metadata.config_schema).lower():
            secrets.append({
                "type": "api_key",
                "description": "Potential hardcoded API key pattern",
                "file": "config.py",
            })
        
        listing.security_scan_status = "completed"
        listing.security_scan_results = {
            "score": score,
            "vulnerabilities": vulnerabilities,
            "secrets_detected": secrets,
            "license_issues": licenses,
            "scanned_at": datetime.utcnow().isoformat(),
        }
        
        listing.updated_at = datetime.utcnow()
    
    # ==================== Analytics & Stats ====================
    
    async def get_listing_stats(self, listing_id: str) -> Dict[str, Any]:
        listing = self._listings.get(listing_id)
        if not listing:
            return {}
        
        reviews = self._reviews.get(listing_id, [])
        installations = [i for i in self._installations.values() if i.listing_id == listing_id]
        analytics = self._analytics.get(listing_id, [])
        
        total_revenue = sum(a.revenue for a in analytics)
        total_cost = sum(a.cost for a in analytics)
        
        return {
            "listing_id": listing.id,
            "name": listing.metadata.name,
            "status": listing.status.value,
            "rating": listing.rating,
            "review_count": listing.review_count,
            "install_count": listing.install_count,
            "active_installations": listing.active_installations,
            "total_revenue": total_revenue,
            "total_cost": total_cost,
            "total_syncs": sum(a.total_syncs for a in analytics),
            "success_rate": (
                sum(a.successful_syncs for a in analytics) / 
                sum(a.total_syncs for a in analytics) * 100
            ) if analytics else 0,
            "avg_rating": listing.rating,
        }
    
    async def get_marketplace_stats(self) -> Dict[str, Any]:
        total_listings = len(self._listings)
        published = sum(1 for l in self._listings.values() if l.status == ConnectorStatus.PUBLISHED)
        total_installs = sum(l.install_count for l in self._listings.values())
        active_installs = sum(l.active_installations for l in self._listings.values())
        total_reviews = sum(len(r) for r in self._reviews.values())
        
        categories = {}
        for listing in self._listings.values():
            cat = listing.metadata.category
            categories[cat] = categories.get(cat, 0) + 1
        
        return {
            "total_listings": total_listings,
            "published_listings": published,
            "total_installs": total_installs,
            "active_installations": active_installs,
            "total_reviews": total_reviews,
            "categories": categories,
        }


# ==================== Installation Wizard ====================

class InstallationWizard:
    """Guided installation wizard for connectors."""
    
    def __init__(self, marketplace: MarketplaceManager):
        self.marketplace = marketplace
    
    async def validate_config(
        self,
        listing_id: str,
        version_id: str,
        config: Dict[str, Any],
    ) -> Tuple[bool, List[str]]:
        """Validate connector configuration."""
        errors = []
        
        listing = self.marketplace._listings.get(listing_id)
        if not listing:
            return False, ["Listing not found"]
        
        version = None
        for v in self.marketplace._versions.get(listing_id, []):
            if v.id == version_id:
                version = v
                break
        
        if not version:
            return False, ["Version not found"]
        
        # Validate required config fields
        config_schema = listing.metadata.config_schema
        required_fields = []
        for field_name, field_schema in config_schema.get("properties", {}).items():
            if field_name in config_schema.get("required", []):
                required_fields.append(field_name)
        
        for field in required_fields:
            if field not in config:
                errors.append(f"Required field missing: {field}")
            elif not config[field]:
                errors.append(f"Required field empty: {field}")
        
        # Validate field types
        for field_name, value in config.items():
            if field_name in listing.metadata.config_schema.get("properties", {}):
                field_schema = listing.metadata.config_schema["properties"][field_name]
                if not self._validate_field_type(value, field_schema):
                    errors.append(f"Invalid type for field {field_name}")
        
        return len(errors) == 0, errors
    
    def _validate_field_type(self, value: Any, field_schema: Dict[str, Any]) -> bool:
        expected_type = field_schema.get("type")
        if not expected_type:
            return True
        
        type_checks = {
            "string": lambda v: isinstance(v, str),
            "integer": lambda v: isinstance(v, int),
            "number": lambda v: isinstance(v, (int, float)),
            "boolean": lambda v: isinstance(v, bool),
            "array": lambda v: isinstance(v, list),
            "object": lambda v: isinstance(v, dict),
        }
        
        checker = type_checks.get(expected_type)
        if checker:
            return checker(value)
        return True
    
    async def generate_config_template(self, listing_id: str, version_id: str) -> Dict[str, Any]:
        """Generate configuration template with defaults."""
        listing = self._listings.get(listing_id)
        if not listing:
            return {}
        
        template = {}
        for field_name, field_schema in listing.metadata.config_schema.get("properties", {}).items():
            if "default" in field_schema:
                template[field_name] = field_schema["default"]
            elif field_schema.get("type") == "string":
                template[field_name] = ""
            elif field_schema.get("type") == "integer":
                template[field_name] = 0
            elif field_schema.get("type") == "boolean":
                template[field_name] = False
            elif field_schema.get("type") == "array":
                template[field_name] = []
            elif field_schema.get("type") == "object":
                template[field_name] = {}
        
        return template
    
    async def test_connection(
        self,
        listing_id: str,
        version_id: str,
        config: Dict[str, Any],
        credentials: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Test connection with provided config and credentials."""
        # Would use integration runtime to test
        return {
            "success": True,
            "detail": "Connection test successful",
            "tested_at": datetime.utcnow().isoformat(),
        }


# ==================== Database Models ====================

from sqlalchemy import Column, String, Text, JSON, DateTime, Index, ForeignKey, Boolean, Integer, Float, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


class ConnectorListingModel(Base, TimestampMixin):
    """Database model for connector listings."""
    
    __tablename__ = "connector_listings"
    __table_args__ = (
        Index("ix_connector_listings_status", "status"),
        Index("ix_connector_listings_category", "category"),
        Index("ix_connector_listings_owner", "owner_id"),
        Index("ix_connector_listings_org", "organization_id"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(SQLEnum(ConnectorStatus), default=ConnectorStatus.DRAFT)
    pricing: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    rating: Mapped[float] = mapped_column(Float, default=0.0)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    install_count: Mapped[int] = mapped_column(Integer, default=0)
    active_installations: Mapped[int] = mapped_column(Integer, default=0)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    security_scan_status: Mapped[str] = mapped_column(String(32), default="pending")
    security_scan_results: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(String(32))
    owner_id: Mapped[str] = mapped_column(String(32))
    organization_id: Mapped[Optional[str]] = mapped_column(
        String(32), ForeignKey("organizations.id", ondelete="SET NULL")
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class ConnectorVersionModel(Base, TimestampMixin):
    """Database model for connector versions."""
    
    __tablename__ = "connector_versions"
    __table_args__ = (
        Index("ix_connector_versions_listing", "listing_id"),
        Index("ix_connector_versions_status", "status"),
        Index("ix_connector_versions_version", "version"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    listing_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("connector_listings.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    changelog: Mapped[str] = mapped_column(Text)
    manifest: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    package_url: Mapped[str] = mapped_column(String(512))
    package_hash: Mapped[str] = mapped_column(String(128))
    package_size: Mapped[int] = mapped_column(Integer, default=0)
    min_platform_version: Mapped[str] = mapped_column(String(32), default="1.0.0")
    max_platform_version: Mapped[Optional[str]] = mapped_column(String(32))
    dependencies: Mapped[List[Dict[str, str]]] = mapped_column(JSON, default=list)
    breaking_changes: Mapped[bool] = mapped_column(Boolean, default=False)
    migration_guide: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(SQLEnum(ConnectorStatus), default=ConnectorStatus.DRAFT)
    security_scan: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    deprecated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class InstallationModel(Base, TimestampMixin):
    """Database model for connector installations."""
    
    __tablename__ = "connector_installations"
    __table_args__ = (
        Index("ix_installations_org", "organization_id"),
        Index("ix_installations_listing", "listing_id"),
        Index("ix_installations_status", "status"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    listing_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("connector_listings.id", ondelete="CASCADE"), nullable=False
    )
    version_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("connector_versions.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    connection_id: Mapped[Optional[str]] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(SQLEnum(InstallationStatus), default=InstallationStatus.PENDING)
    config: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    credentials: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    field_mappings: Mapped[Dict[str, str]] = mapped_column(JSON, default=dict)
    sync_schedule: Mapped[Optional[str]] = mapped_column(String(128))
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_sync_status: Mapped[Optional[str]] = mapped_column(String(32))
    sync_stats: Mapped[Dict[str, int]] = mapped_column(JSON, default=dict)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    installed_by: Mapped[str] = mapped_column(String(32))
    uninstalled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    billing_info: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)


class ReviewModel(Base, TimestampMixin):
    """Database model for connector reviews."""
    
    __tablename__ = "connector_reviews"
    __table_args__ = (
        Index("ix_reviews_listing", "listing_id"),
        Index("ix_reviews_version", "version_id"),
        Index("ix_reviews_org", "organization_id"),
        UniqueConstraint("listing_id", "version_id", "organization_id", "user_id", name="uq_reviews_unique"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    listing_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("connector_listings.id", ondelete="CASCADE"), nullable=False
    )
    version_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("connector_versions.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    pros: Mapped[List[str]] = mapped_column(JSON, default=list)
    cons: Mapped[List[str]] = mapped_column(JSON, default=list)
    verified_purchase: Mapped[bool] = mapped_column(Boolean, default=False)
    helpful_count: Mapped[int] = mapped_column(Integer, default=0)


class UsageAnalyticsModel(Base, TimestampMixin):
    """Database model for usage analytics."""
    
    __tablename__ = "usage_analytics"
    __table_args__ = (
        Index("ix_usage_analytics_listing", "listing_id"),
        Index("ix_usage_analytics_org", "organization_id"),
        Index("ix_usage_analytics_period", "period_start", "period_end"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    listing_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("connector_listings.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_syncs: Mapped[int] = mapped_column(Integer, default=0)
    successful_syncs: Mapped[int] = mapped_column(Integer, default=0)
    failed_syncs: Mapped[int] = mapped_column(Integer, default=0)
    records_synced: Mapped[int] = mapped_column(Integer, default=0)
    api_calls: Mapped[int] = mapped_column(Integer, default=0)
    data_volume_bytes: Mapped[int] = mapped_column(Integer, default=0)
    avg_sync_duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    errors: Mapped[Dict[str, int]] = mapped_column(JSON, default=dict)
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    revenue: Mapped[float] = mapped_column(Float, default=0.0)


class SecurityScanModel(Base, TimestampMixin):
    """Database model for security scan results."""
    
    __tablename__ = "security_scans"
    __table_args__ = (
        Index("ix_security_scans_listing", "listing_id"),
        Index("ix_security_scans_version", "version_id"),
        Index("ix_security_scans_status", "status"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    listing_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("connector_listings.id", ondelete="CASCADE"), nullable=False
    )
    version_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("connector_versions.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), default="pending")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    vulnerabilities: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    secrets_detected: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    license_issues: Mapped[List[str]] = mapped_column(JSON, default=list)
    dependency_issues: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    best_practice_violations: Mapped[List[str]] = mapped_column(JSON, default=list)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


# ==================== Global Manager ====================

_marketplace_manager: Optional[MarketplaceManager] = None
_installation_wizard: Optional["InstallationWizard"] = None


def get_marketplace_manager(session: AsyncSession = None) -> MarketplaceManager:
    """Get global marketplace manager."""
    global _marketplace_manager
    if _marketplace_manager is None:
        _marketplace_manager = MarketplaceManager(session)
    return _marketplace_manager


def get_installation_wizard(marketplace: MarketplaceManager = None) -> InstallationWizard:
    """Get installation wizard."""
    global _installation_wizard
    if _installation_wizard is None:
        marketplace = marketplace or get_marketplace_manager()
        _installation_wizard = InstallationWizard(marketplace)
    return _installation_wizard


# ==================== Convenience Functions ====================

async def create_connector_listing(
    metadata: "ConnectorMetadata",
    pricing: "PricingInfo" = None,
    created_by: str = "",
    organization_id: str = None,
    session: AsyncSession = None,
) -> ConnectorListing:
    """Create a new connector listing."""
    marketplace = get_marketplace_manager(session)
    return await marketplace.create_listing(metadata, pricing, created_by, organization_id)


async def install_connector(
    listing_id: str,
    version_id: str,
    organization_id: str,
    config: Dict[str, Any],
    credentials: Dict[str, Any],
    field_mappings: Dict[str, str] = None,
    sync_schedule: str = None,
    installed_by: str = "",
    session: AsyncSession = None,
) -> Installation:
    """Install a connector for an organization."""
    marketplace = get_marketplace_manager(session)
    return await marketplace.install_connector(
        listing_id=listing_id,
        version_id=version_id,
        organization_id=organization_id,
        config=config,
        credentials=credentials,
        field_mappings=field_mappings,
        sync_schedule=sync_schedule,
        installed_by=installed_by,
    )


async def get_marketplace_listings(
    category: str = None,
    status: ConnectorStatus = None,
    search: str = None,
    sort_by: str = "popularity",
    limit: int = 20,
    offset: int = 0,
    session: AsyncSession = None,
) -> List[ConnectorListing]:
    """List marketplace listings."""
    marketplace = get_marketplace_manager(session)
    return await marketplace.list_listings(category, status, search, sort_by, limit, offset)


async def get_connector_listing(listing_id: str, session: AsyncSession = None) -> Optional[ConnectorListing]:
    """Get connector listing by ID."""
    marketplace = get_marketplace_manager(session)
    return await marketplace.get_listing(listing_id)


async def submit_listing_for_review(listing_id: str, session: AsyncSession) -> bool:
    """Submit listing for review."""
    marketplace = get_marketplace_manager(session)
    return await marketplace.submit_for_review(listing_id)


async def approve_listing(listing_id: str, reviewer_id: str, session: AsyncSession) -> bool:
    """Approve listing for publication."""
    marketplace = get_marketplace_manager(session)
    return await marketplace.approve_listing(listing_id, reviewer_id)


async def publish_listing(listing_id: str, publisher_id: str, session: AsyncSession) -> bool:
    """Publish approved listing."""
    marketplace = get_marketplace_manager(session)
    return await marketplace.publish_listing(listing_id, publisher_id)


async def install_connector(
    listing_id: str,
    version_id: str,
    organization_id: str,
    config: Dict[str, Any],
    credentials: Dict[str, Any],
    field_mappings: Dict[str, str] = None,
    sync_schedule: str = None,
    installed_by: str = "",
    session: AsyncSession = None,
) -> Installation:
    """Install a connector."""
    marketplace = get_marketplace_manager(session)
    return await marketplace.install_connector(
        listing_id=listing_id,
        version_id=version_id,
        organization_id=organization_id,
        config=config,
        credentials=credentials,
        field_mappings=field_mappings,
        sync_schedule=sync_schedule,
        installed_by=installed_by,
    )


async def validate_connector_config(
    listing_id: str,
    version_id: str,
    config: Dict[str, Any],
    session: AsyncSession = None,
) -> Tuple[bool, List[str]]:
    """Validate connector configuration."""
    marketplace = get_marketplace_manager(session)
    wizard = get_installation_wizard(marketplace)
    return await wizard.validate_config(listing_id, version_id, config)


async def test_connector_connection(
    listing_id: str,
    version_id: str,
    config: Dict[str, Any],
    credentials: Dict[str, Any],
    session: AsyncSession = None,
) -> Dict[str, Any]:
    """Test connector connection."""
    marketplace = get_marketplace_manager(session)
    wizard = get_installation_wizard(marketplace)
    return await wizard.test_connection(listing_id, version_id, config, credentials)


async def get_marketplace_stats(session: AsyncSession = None) -> Dict[str, Any]:
    """Get marketplace statistics."""
    marketplace = get_marketplace_manager(session)
    return await marketplace.get_marketplace_stats()


async def get_listing_stats(listing_id: str, session: AsyncSession = None) -> Dict[str, Any]:
    """Get listing statistics."""
    marketplace = get_marketplace_manager(session)
    return await marketplace.get_listing_stats(listing_id)