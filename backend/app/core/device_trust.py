"""
Device Trust & Risk Scoring Service for VCOS.

Provides:
- Device fingerprinting and trust scoring
- Geo/IP risk scoring with IP intelligence
- Device trust levels and policies
- Risk-based authentication challenges
- Device registration and management
"""

import asyncio
import hashlib
import json
import logging
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import uuid4

import aiohttp
import geoip2.database
import geoip2.errors
import redis.asyncio as redis
import user_agents

from app.core.config import settings
from app.core.timeutils import utcnow

logger = logging.getLogger(__name__)


class DeviceTrustLevel(str, Enum):
    """Device trust levels."""
    UNKNOWN = "unknown"       # New/unseen device
    UNTRUSTED = "untrusted"   # Failed verification
    LOW = "low"               # Basic verification only
    MEDIUM = "medium"         # Some verification (password + known device)
    HIGH = "high"             # Strong verification (MFA + known device + low risk)
    TRUSTED = "trusted"       # Fully verified (passkeys, hardware keys, long history)


class RiskLevel(str, Enum):
    """Risk levels for authentication attempts."""
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ChallengeType(str, Enum):
    """Types of authentication challenges."""
    PASSWORD = "password"
    MFA_TOTP = "mfa_totp"
    MFA_PASSKEY = "mfa_passkey"
    MFA_PUSH = "mfa_push"
    MFA_SMS = "mfa_sms"
    MFA_EMAIL = "mfa_email"
    DEVICE_VERIFICATION = "device_verification"
    CAPTCHA = "captcha"
    STEP_UP = "step_up"
    BLOCK = "block"


@dataclass
class DeviceFingerprint:
    """Device fingerprint components."""
    # Browser/Client
    user_agent: str
    accept_language: str
    accept_encoding: str
    
    # Network (required fields first)
    ip: str = ""
    ip_version: int = 4
    
    # Browser/Client optional
    screen_resolution: Optional[str] = None
    timezone: Optional[str] = None
    platform: Optional[str] = None
    
    # Canvas/FP
    canvas_fingerprint: Optional[str] = None
    webgl_fingerprint: Optional[str] = None
    audio_fingerprint: Optional[str] = None
    font_list: Optional[str] = None
    
    # Hardware (from client)
    cpu_cores: Optional[int] = None
    device_memory: Optional[int] = None
    hardware_concurrency: Optional[int] = None
    device_pixel_ratio: Optional[float] = None
    
    # Derived
    fingerprint_hash: str = ""
    confidence: float = 0.0
    
    def compute_hash(self) -> str:
        """Compute stable fingerprint hash."""
        components = [
            self.user_agent,
            self.accept_language,
            self.accept_encoding,
            self.screen_resolution or "",
            self.timezone or "",
            self.platform or "",
            self.canvas_fingerprint or "",
            self.webgl_fingerprint or "",
            self.audio_fingerprint or "",
            self.font_list or "",
            str(self.cpu_cores or 0),
            str(self.device_memory or 0),
            str(self.hardware_concurrency or 0),
            str(self.device_pixel_ratio or 0),
        ]
        canonical = "|".join(components)
        return hashlib.sha256(canonical.encode()).hexdigest()[:32]


@dataclass
class IPIntelligence:
    """IP address intelligence data."""
    ip: str
    version: int  # 4 or 6
    
    # Location
    country: Optional[str] = None
    country_code: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    timezone: Optional[str] = None
    
    # Network
    asn: Optional[int] = None
    asn_name: Optional[str] = None
    isp: Optional[str] = None
    organization: Optional[str] = None
    
    # Risk indicators
    is_proxy: bool = False
    is_vpn: bool = False
    is_tor: bool = False
    is_hosting: bool = False
    is_anonymous: bool = False
    is_bot: bool = False
    is_abuser: bool = False
    threat_level: str = "none"  # none, low, medium, high, critical
    
    # Reputation
    reputation_score: float = 100.0  # 0-100, higher = better
    abuse_score: int = 0
    
    # Metadata
    last_seen: Optional[datetime] = None
    last_updated: datetime = field(default_factory=datetime.utcnow)
    source: str = "unknown"  # ipapi, ipinfo, maxmind, internal


@dataclass
class DeviceRegistration:
    """Registered device record."""
    id: str
    user_id: str
    organization_id: str
    
    # Fingerprint
    fingerprint_hash: str
    device_name: str
    device_type: str  # desktop, mobile, tablet, unknown
    platform: str  # windows, macos, linux, ios, android, unknown
    browser: str
    browser_version: str
    
    # Trust
    trust_level: DeviceTrustLevel = DeviceTrustLevel.UNKNOWN
    trust_score: float = 0.0  # 0-100
    
    # Verification
    is_verified: bool = False
    verified_at: Optional[datetime] = None
    verified_by: Optional[str] = None
    verification_method: Optional[str] = None
    
    # Activity
    first_seen: datetime = field(default_factory=datetime.utcnow)
    last_seen: datetime = field(default_factory=datetime.utcnow)
    last_ip: str = ""
    login_count: int = 0
    
    # Security
    is_blocked: bool = False
    blocked_reason: Optional[str] = None
    blocked_at: Optional[datetime] = None
    blocked_by: Optional[str] = None
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class RiskAssessment:
    """Risk assessment for an authentication attempt."""
    request_id: str
    user_id: str
    organization_id: str
    timestamp: datetime
    
    # Risk factors
    risk_score: float = 0.0  # 0-100
    risk_level: RiskLevel = RiskLevel.NONE
    risk_factors: List[Dict[str, Any]] = field(default_factory=list)
    
    # Factors
    ip_risk: float = 0.0
    device_risk: float = 0.0
    behavioral_risk: float = 0.0
    geo_risk: float = 0.0
    velocity_risk: float = 0.0
    
    # Decision
    required_challenges: List[str] = field(default_factory=list)
    recommended_challenge: Optional[str] = None
    allow: bool = True
    block_reason: Optional[str] = None
    
    # Metadata
    ip_intelligence: Optional[Dict] = None
    device_info: Optional[Dict] = None
    geo_data: Optional[Dict] = None
    assessed_at: datetime = field(default_factory=datetime.utcnow)


class DeviceTrustService:
    """
    Device Trust & Risk Scoring Service.
    
    Features:
    - Device fingerprinting and trust scoring
    - Geo/IP risk scoring with IP intelligence
    - Device trust levels and policies
    - Risk-based authentication challenges
    - Device registration and management
    - Integration with WebAuthn/FIDO2
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/3",
        geoip_db_path: Optional[str] = None,
        ipintel_providers: List[str] = None,
    ):
        self.redis_url = redis_url
        self.geoip_db_path = geoip_db_path or getattr(settings, 'GEOIP_DB_PATH', '/usr/share/GeoIP/GeoLite2-City.mmdb')
        self.ipintel_providers = ipintel_providers or ['ipapi', 'ipinfo']
        
        self._redis: Optional[redis.Redis] = None
        self._geoip_reader: Optional[geoip2.database.Reader] = None
        self._http_session: Optional[aiohttp.ClientSession] = None
        self._fingerprint_cache: Dict[str, DeviceFingerprint] = {}
        self._ip_intel_cache: Dict[str, IPIntelligence] = {}
        self._device_cache: Dict[str, DeviceRegistration] = {}
        
        self._initialized = False
        
        # Trust scoring weights
        self.weights = {
            'ip_risk': 0.25,
            'device_risk': 0.30,
            'behavioral_risk': 0.25,
            'geo_risk': 0.15,
            'velocity_risk': 0.10,
        }
        
        # Trust thresholds
        self.trust_thresholds = {
            DeviceTrustLevel.TRUSTED: 90,
            DeviceTrustLevel.HIGH: 75,
            DeviceTrustLevel.MEDIUM: 50,
            DeviceTrustLevel.LOW: 25,
            DeviceTrustLevel.UNTRUSTED: 0,
        }
        
        # Risk thresholds
        self.risk_thresholds = {
            RiskLevel.CRITICAL: 90,
            RiskLevel.HIGH: 70,
            RiskLevel.MEDIUM: 40,
            RiskLevel.LOW: 20,
            RiskLevel.NONE: 0,
        }

    async def initialize(self):
        """Initialize the device trust service."""
        if self._initialized:
            return
        
        # Redis connection
        if self.redis_url:
            try:
                self._redis = redis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    max_connections=20,
                )
                await self._redis.ping()
            except Exception as e:
                logger.warning(f"Redis not available for DeviceTrustService: {e}")
                self._redis = None
        else:
            logger.info("DeviceTrustService initialized without Redis")
        
        # GeoIP database
        try:
            self._geoip_reader = geoip2.database.Reader(self.geoip_db_path)
            logger.info("GeoIP database loaded")
        except Exception as e:
            logger.warning(f"Could not load GeoIP database: {e}")
        
        # HTTP session for IP intelligence APIs
        self._http_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=5),
            connector=aiohttp.TCPConnector(limit=20),
        )
        
        # Load device cache
        await self._load_device_cache()
        
        logger.info("Device Trust Service initialized")
        self._initialized = True

    async def close(self):
        """Close connections."""
        if self._redis:
            await self._redis.close()
        if self._http_session:
            await self._http_session.close()
        if self._geoip_reader:
            self._geoip_reader.close()

    # ==================== Device Fingerprinting ====================

    async def register_device(
        self,
        user_id: str,
        organization_id: str,
        fingerprint_data: Dict[str, Any],
        device_name: Optional[str] = None,
        device_name_hint: Optional[str] = None,
    ) -> DeviceRegistration:
        """Register a new device for a user."""
        # Parse fingerprint
        fingerprint = self._parse_fingerprint(fingerprint_data)
        fingerprint_hash = fingerprint.compute_hash()
        
        # Check if already registered
        existing = await self.get_device_by_fingerprint(fingerprint_hash, user_id)
        if existing:
            # Update existing
            return await self.update_device_seen(existing.id, fingerprint)
        
        # Parse user agent
        ua = user_agents.parse(fingerprint.user_agent)
        
        # Determine device type
        device_type = self._classify_device(ua)
        
        # Create registration
        device = DeviceRegistration(
            id=str(uuid4()),
            user_id=user_id,
            organization_id=organization_id,
            fingerprint_hash=fingerprint.fingerprint_hash,
            device_name=fingerprint_data.get('device_name') or device_name or f"{ua.browser.family} on {ua.os.family}",
            device_type=self._classify_device(user_agents.parse(fingerprint.user_agent)),
            platform=ua.os.family.lower(),
            browser=ua.browser.family,
            browser_version=ua.browser.version_string,
        )
        
        # Compute initial trust score
        device.trust_score = await self._calculate_initial_trust_score(
            fingerprint, 
            await self._get_ip_intelligence(""),  # Would need actual IP
        )
        device.trust_level = self._calculate_trust_level(device.trust_score)
        
        # Store
        await self._save_device_registration(fingerprint)
        
        # Update user's device list
        await self._add_device_to_user(user_id, device.id)
        
        logger.info(f"Registered new device for user {user_id}: {fingerprint.fingerprint_hash[:16]}")
        return device

    async def get_device_by_fingerprint(
        self,
        fingerprint_hash: str,
        user_id: str,
    ) -> Optional[DeviceRegistration]:
        """Get device by fingerprint hash."""
        # Check cache
        cache_key = f"device:fingerprint:{fingerprint_hash}:{user_id}"
        cached = await self._redis.get(f"vcos:device:{cache_key}")
        if cached:
            return DeviceRegistration(**json.loads(cached))
        
        # Check Redis
        device_data = await self._redis.hgetall(f"vcos:device:fp:{fingerprint_hash}:{user_id}")
        if device_data:
            device = DeviceRegistration(**device_data)
            return device
        
        return None

    async def get_user_devices(self, user_id: str) -> List[DeviceRegistration]:
        """Get all devices for a user."""
        device_ids = await self._redis.smembers(f"vcos:user:devices:{user_id}")
        devices = []
        for device_id in device_ids:
            device_data = await self._redis.hgetall(f"vcos:device:{device_id}")
            if device_data:
                devices.append(DeviceRegistration(**device_data))
        return sorted(devices, key=lambda d: d.last_seen, reverse=True)

    async def update_device_seen(
        self,
        device_id: str,
        fingerprint: Optional[DeviceFingerprint] = None,
    ) -> bool:
        """Update device last seen timestamp."""
        device = await self.get_device(device_id)
        if not device:
            return False
        
        device.last_seen = datetime.utcnow()
        device.login_count += 1
        device.updated_at = datetime.utcnow()
        
        if fingerprint:
            device.fingerprint_hash = fingerprint.fingerprint_hash
        
        await self._save_device_registration(device)
        return True

    # ==================== Risk Assessment ====================

    async def assess_risk(
        self,
        user_id: str,
        organization_id: str,
        ip: str,
        fingerprint: Optional[DeviceFingerprint] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> RiskAssessment:
        """Perform comprehensive risk assessment."""
        request_id = str(uuid.uuid4())
        context = context or {}
        
        assessment = RiskAssessment(
            request_id=str(uuid.uuid4()),
            user_id=user_id,
            organization_id=organization_id,
            timestamp=utcnow(),
        )
        
        # Get IP intelligence
        ip_intel = await self.get_ip_intelligence(ip)
        assessment.ip_intelligence = ip_intel.__dict__ if ip_intel else None
        
        # Calculate risk factors
        assessment.ip_risk = await self._calculate_ip_risk(ip_intel)
        assessment.device_risk = await self._calculate_device_risk(
            fingerprint, 
            user_id,
        )
        assessment.geo_risk = await self._calculate_geo_risk(ip_intel, context)
        assessment.velocity_risk = await self._calculate_velocity_risk(user_id)
        assessment.behavioral_risk = await self._calculate_behavioral_risk(
            user_id, 
            context,
        )
        
        # Calculate overall risk score
        assessment.risk_score = (
            assessment.ip_risk * self.weights['ip_risk'] +
            assessment.device_risk * self.weights['device_risk'] +
            assessment.behavioral_risk * self.weights['behavioral_risk'] +
            assessment.geo_risk * self.weights['geo_risk'] +
            assessment.velocity_risk * self.weights['velocity_risk']
        )
        
        assessment.risk_level = self._calculate_risk_level(assessment.risk_score)
        
        # Determine required challenges
        assessment.required_challenges = self._determine_challenges(
            assessment.risk_level,
            context,
        )
        
        assessment.recommended_challenge = self._recommend_challenge(
            assessment.risk_level,
            context,
        )
        
        # Determine allow/block
        assessment.allow = assessment.risk_level != RiskLevel.CRITICAL
        if not assessment.allow:
            assessment.block_reason = "Risk level exceeds threshold"
        
        assessment.assessed_at = utcnow()
        return assessment

    def _calculate_risk_level(self, score: float) -> RiskLevel:
        if score >= self.risk_thresholds[RiskLevel.CRITICAL]:
            return RiskLevel.CRITICAL
        elif score >= self.risk_thresholds[RiskLevel.HIGH]:
            return RiskLevel.HIGH
        elif score >= self.risk_thresholds[RiskLevel.MEDIUM]:
            return RiskLevel.MEDIUM
        elif score >= self.risk_thresholds[RiskLevel.LOW]:
            return RiskLevel.LOW
        return RiskLevel.NONE

    # ==================== IP Intelligence ====================

    async def get_ip_intelligence(self, ip: str) -> IPIntelligence:
        """Get IP intelligence data."""
        # Check cache
        cache_key = f"ipintel:{ip}"
        cached = await self._redis.get(f"vcos:ipintel:{ip}")
        if cached:
            return IPIntelligence(**json.loads(cached))
        
        # Check local cache
        if ip in self._ip_intel_cache:
            intel = self._ip_intel_cache[ip]
            if (utcnow() - intel.last_updated).total_seconds() < 3600:  # 1 hour cache
                return intel
        
        # Fetch from providers
        intel = await self._fetch_ip_intelligence(ip)
        
        # Cache result
        self._ip_intel_cache[ip] = intel
        await self._redis.setex(
            f"vcos:ipintel:{ip}",
            3600,  # 1 hour
            json.dumps(intel.__dict__, default=str)
        )
        
        return intel

    async def _fetch_ip_intelligence(self, ip: str) -> IPIntelligence:
        """Fetch IP intelligence from multiple providers."""
        intel = IPIntelligence(ip=ip)
        
        # Try GeoIP database first
        if self._geoip_reader:
            try:
                response = self._geoip_reader.city(ip)
                intel.country = response.country.name
                intel.country_code = response.country.iso_code
                intel.region = response.subdivisions.most_specific.name
                intel.city = response.city.name
                intel.latitude = response.location.latitude
                intel.longitude = response.location.longitude
                intel.timezone = response.location.time_zone
            except geoip2.errors.AddressNotFoundError:
                pass
            except Exception as e:
                logger.warning(f"GeoIP lookup failed: {e}")
        
        # Try external APIs
        for provider in self.ipintel_providers:
            try:
                data = await self._fetch_from_provider(ip, provider)
                if data:
                    self._merge_ip_intel(intel, data, provider)
                    break  # Use first successful provider
            except Exception as e:
                logger.warning(f"IP intel provider {provider} failed: {e}")
        
        # Determine threat level
        intel.threat_level = self._assess_threat_level(intel)
        intel.reputation_score = self._calculate_reputation(intel)
        
        return intel

    async def _fetch_from_provider(self, ip: str, provider: str) -> Optional[Dict]:
        """Fetch IP intelligence from a specific provider."""
        urls = {
            'ipapi': f'http://ip-api.com/json/{ip}?fields=status,message,continent,continentCode,country,countryCode,region,regionName,city,district,zip,lat,lon,timezone,offset,currency,isp,org,as,asname,reverse,mobile,proxy,hosting,query',
            'ipinfo': f'https://ipinfo.io/{ip}/json',
        }
        
        url = urls.get(provider)
        if not url:
            return None
        
        try:
            async with self._http_session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            logger.warning(f"Failed to fetch from {provider}: {e}")
        return None

    def _merge_ip_intel(self, intel: IPIntelligence, data: Dict, provider: str):
        """Merge IP intelligence data from provider."""
        intel.source = provider
        intel.last_updated = datetime.utcnow()
        
        if provider == 'ipapi':
            intel.country = data.get('country')
            intel.country_code = data.get('countryCode')
            intel.region = data.get('regionName')
            intel.city = data.get('city')
            intel.latitude = data.get('lat')
            intel.longitude = data.get('lon')
            intel.timezone = data.get('timezone')
            intel.isp = data.get('isp')
            intel.organization = data.get('org')
            intel.asn = data.get('as')
            intel.asn_name = data.get('asname')
            intel.is_proxy = data.get('proxy', False)
            intel.is_hosting = data.get('hosting', False)
            intel.is_anonymous = data.get('proxy', False) or data.get('hosting', False)
        elif provider == 'ipinfo':
            intel.country = data.get('country')
            intel.region = data.get('region')
            intel.city = data.get('city')
            intel.latitude = data.get('loc', '').split(',')[0] if data.get('loc') else None
            intel.longitude = data.get('loc', '').split(',')[1] if data.get('loc') else None
            intel.org = data.get('org')
            intel.is_vpn = data.get('vpn', False)
            intel.is_proxy = data.get('proxy', False)
            intel.is_tor = data.get('tor', False)
            intel.is_hosting = data.get('hosting', False)

    def _assess_threat_level(self, intel: IPIntelligence) -> str:
        """Assess threat level from IP intelligence."""
        risk_score = 0
        
        if intel.is_proxy or intel.is_vpn or intel.is_tor:
            risk_score += 40
        if intel.is_hosting:
            risk_score += 30
        if intel.is_anonymous:
            risk_score += 30
        if intel.is_bot:
            risk_score += 20
        if intel.is_abuser:
            risk_score += 50
        if intel.threat_level == 'high':
            risk_score += 40
        elif intel.threat_level == 'medium':
            risk_score += 20
        
        if risk_score >= 70:
            return 'critical'
        elif risk_score >= 50:
            return 'high'
        elif risk_score >= 25:
            return 'medium'
        elif risk_score >= 10:
            return 'low'
        return 'none'

    def _calculate_reputation(self, intel: IPIntelligence) -> float:
        """Calculate reputation score (0-100)."""
        score = 100.0
        
        if intel.is_proxy: score -= 20
        if intel.is_vpn: score -= 15
        if intel.is_tor: score -= 30
        if intel.is_hosting: score -= 15
        if intel.is_anonymous: score -= 20
        if intel.is_bot: score -= 25
        if intel.is_abuser: score -= 40
        if intel.threat_level == 'high': score -= 30
        elif intel.threat_level == 'medium': score -= 15
        elif intel.threat_level == 'low': score -= 5
        
        return max(0.0, min(100.0, score))

    # ==================== Risk Calculation ====================

    async def _calculate_ip_risk(self, intel: IPIntelligence) -> float:
        """Calculate risk from IP intelligence."""
        if not intel:
            return 50.0  # Unknown = medium risk
        
        risk = 0.0
        
        # Threat level
        threat_scores = {
            'critical': 100,
            'high': 80,
            'medium': 50,
            'low': 20,
            'none': 0,
        }
        risk += threat_scores.get(intel.threat_level, 0)
        
        # Reputation
        risk += (100 - intel.reputation_score) * 0.5
        
        # Specific flags
        if intel.is_tor: risk += 30
        if intel.is_proxy: risk += 20
        if intel.is_vpn: risk += 15
        if intel.is_hosting: risk += 15
        if intel.is_tor: risk += 30
        
        return min(100.0, risk)

    async def _calculate_device_risk(
        self,
        fingerprint: Optional[DeviceFingerprint],
        user_id: str,
    ) -> float:
        """Calculate device risk."""
        if not fingerprint:
            return 70.0  # Unknown device = high risk
        
        risk = 0.0
        
        # Check if device is registered
        device = await self.get_device_by_fingerprint(fingerprint.fingerprint_hash)
        if not device:
            risk += 40  # Unknown device
        elif not device.is_verified:
            risk += 20
        elif device.trust_level == DeviceTrustLevel.UNTRUSTED:
            risk += 50
        elif device.trust_level == DeviceTrustLevel.UNKNOWN:
            risk += 30
        elif device.trust_level == DeviceTrustLevel.LOW:
            risk += 15
        elif device.trust_level == DeviceTrustLevel.MEDIUM:
            risk += 5
        elif device.trust_level in [DeviceTrustLevel.HIGH, DeviceTrustLevel.TRUSTED]:
            risk -= 10  # Trusted devices lower risk
        
        # Fingerprint stability
        if fingerprint.confidence < 0.5:
            risk += 15
        
        return min(100.0, max(0.0, risk))

    async def _calculate_geo_risk(
        self,
        intel: Optional[IPIntelligence],
        context: Dict[str, Any],
    ) -> float:
        """Calculate geographic risk."""
        if not intel:
            return 50.0
        
        risk = 0.0
        
        # High-risk countries
        high_risk_countries = {'CN', 'RU', 'KP', 'IR', 'SY', 'CU', 'IR'}
        if intel.country_code in high_risk_countries:
            return 90.0
        
        # Check for impossible travel
        # Would check against user's last known location
        # Simplified for now
        
        return 0.0

    async def _calculate_velocity_risk(self, user_id: str) -> float:
        """Calculate velocity-based risk (impossible travel, too many requests)."""
        # Check login frequency
        # Check for impossible travel
        # Simplified
        return 0.0

    async def _calculate_behavioral_risk(
        self,
        user_id: str,
        context: Dict[str, Any],
    ) -> float:
        """Calculate behavioral risk."""
        # Would analyze typing patterns, mouse movements, etc.
        # Simplified for now
        return 0.0

    def _determine_challenges(
        self,
        risk_level: RiskLevel,
        context: Dict[str, Any],
    ) -> List[str]:
        """Determine required authentication challenges based on risk."""
        challenges = []
        
        if risk_level == RiskLevel.NONE:
            challenges.append(ChallengeType.PASSWORD)
        elif risk_level == RiskLevel.LOW:
            challenges.extend([ChallengeType.PASSWORD, ChallengeType.MFA_TOTP])
        elif risk_level == RiskLevel.MEDIUM:
            challenges.extend([ChallengeType.PASSWORD, ChallengeType.MFA_TOTP, ChallengeType.MFA_PUSH])
        elif risk_level == RiskLevel.HIGH:
            challenges.extend([
                ChallengeType.PASSWORD, 
                ChallengeType.MFA_PASSKEY, 
                ChallengeType.MFA_PUSH,
                ChallengeType.DEVICE_VERIFICATION
            ])
        elif risk_level == RiskLevel.CRITICAL:
            challenges.append(ChallengeType.BLOCK)
        
        return challenges

    def _recommend_challenge(
        self,
        risk_level: RiskLevel,
        context: Dict[str, Any],
    ) -> str:
        """Recommend the best challenge for the risk level."""
        if risk_level == RiskLevel.CRITICAL:
            return ChallengeType.BLOCK
        elif risk_level == RiskLevel.HIGH:
            return ChallengeType.MFA_PASSKEY  # Strongest MFA
        elif risk_level == RiskLevel.MEDIUM:
            return ChallengeType.MFA_PUSH
        elif risk_level == RiskLevel.LOW:
            return ChallengeType.MFA_TOTP
        return ChallengeType.PASSWORD

    # ==================== Device Management ====================

    def _parse_fingerprint(self, data: Dict[str, Any]) -> DeviceFingerprint:
        """Parse fingerprint data from request."""
        fp = DeviceFingerprint(
            user_agent=data.get('user_agent', ''),
            accept_language=data.get('accept_language', ''),
            accept_encoding=data.get('accept_encoding', ''),
            screen_resolution=data.get('screen_resolution'),
            timezone=data.get('timezone'),
            platform=data.get('platform'),
            canvas_fingerprint=data.get('canvas_fingerprint'),
            webgl_fingerprint=data.get('webgl_fingerprint'),
            audio_fingerprint=data.get('audio_fingerprint'),
            font_list=data.get('font_list'),
            cpu_cores=data.get('cpu_cores'),
            device_memory=data.get('device_memory'),
            hardware_concurrency=data.get('hardware_concurrency'),
            device_pixel_ratio=data.get('device_pixel_ratio'),
            ip=data.get('ip', ''),
        )
        return fp

    def _classify_device(self, ua: user_agents.parsers.UserAgent) -> str:
        """Classify device type from user agent."""
        if ua.is_mobile:
            return "mobile"
        elif ua.is_tablet:
            return "tablet"
        elif ua.is_pc:
            return "desktop"
        elif ua.is_bot:
            return "bot"
        return "unknown"

    async def _calculate_initial_trust_score(
        self,
        fingerprint: DeviceFingerprint,
        ip_intel: IPIntelligence,
    ) -> float:
        """Calculate initial trust score for a new device."""
        score = 50.0  # Neutral
        
        # Fingerprint quality
        if fingerprint.confidence > 0.8:
            score += 10
        elif fingerprint.confidence < 0.3:
            score -= 20
        
        # IP reputation
        if hasattr(ip_intel, 'reputation_score'):
            score += (ip_intel.reputation_score - 50) * 0.3
        
        return max(0.0, min(100.0, score))

    def _calculate_trust_level(self, score: float) -> DeviceTrustLevel:
        for level in [DeviceTrustLevel.TRUSTED, DeviceTrustLevel.HIGH, 
                      DeviceTrustLevel.MEDIUM, DeviceTrustLevel.LOW, DeviceTrustLevel.UNTRUSTED]:
            if score >= self.trust_thresholds[level]:
                return level
        return DeviceTrustLevel.UNTRUSTED

    # ==================== Storage ====================

    async def _save_device_registration(self, device: DeviceRegistration):
        """Save device registration to Redis."""
        key = f"vcos:device:{device.id}"
        data = device.__dict__.copy()
        # Convert datetime to ISO string
        for key, value in data.items():
            if isinstance(value, datetime):
                data[key] = value.isoformat()
            elif isinstance(value, DeviceTrustLevel):
                data[key] = value.value
        
        await self._redis.hset(f"vcos:device:{device.id}", mapping=data)
        await self._redis.sadd(f"vcos:user:devices:{device.user_id}", device.id)
        
        # Cache fingerprint
        fp_key = f"device:fingerprint:{device.fingerprint_hash}:{device.user_id}"
        await self._redis.setex(
            f"vcos:device:fp:{device.fingerprint_hash}:{device.user_id}",
            86400 * 30,  # 30 days
            json.dumps({
                "device_id": device.id,
                "fingerprint_hash": device.fingerprint_hash,
            })
        )

    async def _load_device_cache(self):
        """Load device cache from Redis."""
        # Implementation would scan Redis for devices
        pass

    async def _add_device_to_user(self, user_id: str, device_id: str):
        await self._redis.sadd(f"vcos:user:devices:{user_id}", device_id)

    async def get_device(self, device_id: str) -> Optional[DeviceRegistration]:
        """Get device by ID."""
        data = await self._redis.hgetall(f"vcos:device:{device_id}")
        if not data:
            return None
        return DeviceRegistration(**data)

    async def get_device_by_fingerprint(
        self,
        fingerprint_hash: str,
        user_id: str,
    ) -> Optional[DeviceRegistration]:
        """Get device by fingerprint hash and user."""
        fp_key = f"vcos:device:fp:{fingerprint_hash}:{user_id}"
        device_id = await self._redis.get(fp_key)
        if device_id:
            return await self.get_device(device_id)
        return None


# ==================== Risk Assessment Helpers ====================

def calculate_risk_score(
    ip_risk: float,
    device_risk: float,
    behavioral_risk: float,
    geo_risk: float,
    velocity_risk: float,
    weights: Dict[str, float] = None,
) -> float:
    """Calculate composite risk score."""
    weights = weights or {
        'ip_risk': 0.25,
        'device_risk': 0.30,
        'behavioral_risk': 0.25,
        'geo_risk': 0.15,
        'velocity_risk': 0.10,
    }
    
    return (
        ip_risk * weights['ip_risk'] +
        device_risk * weights['device_risk'] +
        behavioral_risk * weights['behavioral_risk'] +
        geo_risk * weights['geo_risk'] +
        velocity_risk * weights['velocity_risk']
    )


def get_risk_level(score: float, thresholds: Dict[str, float] = None) -> RiskLevel:
    """Get risk level from score."""
    thresholds = thresholds or {
        RiskLevel.CRITICAL: 90,
        RiskLevel.HIGH: 70,
        RiskLevel.MEDIUM: 40,
        RiskLevel.LOW: 20,
        RiskLevel.NONE: 0,
    }
    
    for level in [RiskLevel.CRITICAL, RiskLevel.HIGH, RiskLevel.MEDIUM, RiskLevel.LOW, RiskLevel.NONE]:
        if score >= thresholds.get(level, 0):
            return level
    return RiskLevel.NONE


def get_required_challenges(risk_level: RiskLevel) -> List[ChallengeType]:
    """Get required challenges for risk level."""
    challenges = []
    
    if risk_level == RiskLevel.NONE:
        challenges.append(ChallengeType.PASSWORD)
    elif risk_level == RiskLevel.LOW:
        challenges.extend([ChallengeType.PASSWORD, ChallengeType.MFA_TOTP])
    elif risk_level == RiskLevel.MEDIUM:
        challenges.extend([ChallengeType.PASSWORD, ChallengeType.MFA_TOTP, ChallengeType.MFA_PUSH])
    elif risk_level == RiskLevel.HIGH:
        challenges.extend([
            ChallengeType.PASSWORD, 
            ChallengeType.MFA_PASSKEY, 
            ChallengeType.MFA_PUSH,
            ChallengeType.DEVICE_VERIFICATION
        ])
    elif risk_level == RiskLevel.CRITICAL:
        challenges.append(ChallengeType.BLOCK)
    
    return challenges


def recommend_challenge(risk_level: RiskLevel) -> str:
    """Recommend the best challenge for risk level."""
    if risk_level == RiskLevel.CRITICAL:
        return ChallengeType.BLOCK
    elif risk_level == RiskLevel.HIGH:
        return ChallengeType.MFA_PASSKEY
    elif risk_level == RiskLevel.MEDIUM:
        return ChallengeType.MFA_PUSH
    elif risk_level == RiskLevel.LOW:
        return ChallengeType.MFA_TOTP
    return ChallengeType.PASSWORD


# ==================== Global Instance ====================

_device_trust_service: Optional[DeviceTrustService] = None


def get_device_trust_service() -> DeviceTrustService:
    """Get or create device trust service singleton."""
    global _device_trust_service
    if _device_trust_service is None:
        _device_trust_service = DeviceTrustService()
    return _device_trust_service


async def init_device_trust_service() -> DeviceTrustService:
    """Initialize device trust service."""
    global _device_trust_service
    _device_trust_service = DeviceTrustService()
    await _device_trust_service.initialize()
    return _device_trust_service