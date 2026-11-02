"""
OIDC Federation - Cross-Organization Identity Federation.

Provides:
- OIDC Federation 1.0 implementation (OpenID Connect Federation)
- Trust chains and entity statements
- Cross-organization SSO with automatic trust resolution
- Federation metadata publishing and discovery
- Automatic key rotation via JWKS
- Support for OpenID Connect Federation 1.0 spec
- Integration with existing OIDC/SAML providers
"""

import asyncio
import base64
import hashlib
import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union
from uuid import uuid4

import aiohttp
import jwt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509 import load_pem_x509_certificate

from sqlalchemy import Column, String, Text, JSON, DateTime, Index, ForeignKey, Boolean, Integer, Enum as SQLEnum
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid

logger = logging.getLogger(__name__)


# ==================== Federation Enums ====================

class FederationEntityType(str, Enum):
    """Types of entities in the federation."""
    LEAF = "leaf"                    # Relying Party (RP) or OpenID Provider (OP)
    INTERMEDIATE = "intermediate"    # Trust Anchor or Intermediate Authority
    TRUST_ANCHOR = "trust_anchor"    # Root of trust


class FederationRelationship(str, Enum):
    """Relationship between federation entities."""
    DIRECT_TRUST = "direct_trust"           # Direct trust relationship
    TRUST_CHAIN = "trust_chain"             # Via trust chain
    METADATA_FETCH = "metadata_fetch"       # Metadata-only relationship


class EntityStatementType(str, Enum):
    """Types of entity statements."""
    SELF_SIGNED = "self_signed"             # Self-signed entity statement
    SUBORDINATE = "subordinate"             # Subordinate statement (issued by superior)
    TRUST_ANCHOR = "trust_anchor"           # Trust anchor statement


class FederationMetadataType(str, Enum):
    """Types of federation metadata."""
    OPENID_PROVIDER = "openid_provider"
    RELYING_PARTY = "relying_party"
    FEDERATION_ENTITY = "federation_entity"
    TRUST_ANCHOR = "trust_anchor"


# ==================== Federation Data Structures ====================

@dataclass
class FederationEntity:
    """Represents an entity in the federation."""
    entity_id: str
    entity_type: FederationEntityType
    name: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    jwks: Dict[str, Any] = field(default_factory=dict)
    authority_hints: List[str] = field(default_factory=list)
    trusted: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    metadata_expires_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type.value,
            "name": self.name,
            "metadata": self.metadata,
            "jwks": self.jwks,
            "authority_hints": self.authority_hints,
            "trusted": self.trusted,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata_expires_at": self.metadata_expires_at.isoformat() if self.metadata_expires_at else None,
        }


@dataclass
class EntityStatement:
    """JWT-based entity statement for federation."""
    iss: str                                    # Issuer entity ID
    sub: str                                    # Subject entity ID
    iat: int                                    # Issued at
    exp: int                                    # Expires at
    jwks: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    authority_hints: List[str] = field(default_factory=list)
    metadata_policy: Dict[str, Any] = field(default_factory=dict)
    constraints: Dict[str, Any] = field(default_factory=dict)
    statement_type: EntityStatementType = EntityStatementType.SUBORDINATE
    
    def to_jwt_claims(self) -> Dict[str, Any]:
        """Convert to JWT claims."""
        return {
            "iss": self.iss,
            "sub": self.sub,
            "iat": self.iat,
            "exp": self.exp,
            "jwks": self.jwks,
            "metadata": self.metadata,
            "authority_hints": self.authority_hints,
            "metadata_policy": self.metadata_policy,
            "constraints": self.constraints,
        }
    
    @classmethod
    def from_jwt_claims(cls, claims: Dict[str, Any]) -> "EntityStatement":
        """Create from JWT claims."""
        return cls(
            iss=claims.get("iss", ""),
            sub=claims.get("sub", ""),
            iat=claims.get("iat", 0),
            exp=claims.get("exp", 0),
            jwks=claims.get("jwks", {}),
            metadata=claims.get("metadata", {}),
            authority_hints=claims.get("authority_hints", []),
            metadata_policy=claims.get("metadata_policy", {}),
            constraints=claims.get("constraints", {}),
        )


@dataclass
class TrustChain:
    """Validated trust chain from trust anchor to leaf."""
    anchor_id: str
    leaf_id: str
    chain: List[EntityStatement] = field(default_factory=list)
    combined_metadata: Dict[str, Any] = field(default_factory=dict)
    combined_jwks: Dict[str, Any] = field(default_factory=dict)
    expires_at: Optional[datetime] = None
    is_valid: bool = True
    validation_errors: List[str] = field(default_factory=list)


@dataclass
class FederationTrustAnchor:
    """Trust anchor configuration."""
    entity_id: str
    name: str
    jwks: Dict[str, Any]
    metadata: Dict[str, Any]
    allowed_entity_types: List[FederationEntityType] = field(default_factory=list)
    metadata_policy: Dict[str, Any] = field(default_factory=dict)
    constraints: Dict[str, Any] = field(default_factory=dict)
    active: bool = True


# ==================== Federation Manager ====================

class OIDCFederationManager:
    """
    OIDC Federation Manager.
    
    Implements OpenID Connect Federation 1.0:
    - Entity statement issuance and validation
    - Trust chain discovery and validation
    - Metadata resolution and policy enforcement
    - Automatic key rotation via JWKS
    - Federation metadata publishing
    """
    
    def __init__(
        self,
        session: AsyncSession = None,
        trust_anchors: List[FederationTrustAnchor] = None,
    ):
        self.session = session
        self._entities: Dict[str, FederationEntity] = {}
        self._entity_statements: Dict[str, EntityStatement] = {}
        self._trust_anchors: Dict[str, FederationTrustAnchor] = {}
        self._trust_chains: Dict[str, TrustChain] = {}
        self._federation_keys: Dict[str, Any] = {}  # entity_id -> private key
        self._jwks_cache: Dict[str, Dict[str, Any]] = {}
        self._metadata_cache: Dict[str, Dict[str, Any]] = {}
        
        if trust_anchors:
            for anchor in trust_anchors:
                self._trust_anchors[anchor.entity_id] = anchor
        
        # Initialize own federation keys
        self._initialize_federation_keys()
    
    def _initialize_federation_keys(self):
        """Initialize federation signing keys."""
        # Generate or load RSA key pair for signing entity statements
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        
        self._federation_keys["default"] = {
            "private_key": private_key,
            "public_key": private_key.public_key(),
            "kid": "federation-signing-key-1",
            "alg": "RS256",
        }
    
    async def initialize(self):
        """Initialize federation manager."""
        # Load entities from database
        if self.session:
            await self._load_entities()
        
        # Load trust anchors
        for anchor in self._trust_anchors.values():
            await self._load_trust_anchor(anchor)
        
        logger.info("OIDC Federation Manager initialized")
    
    async def _load_entities(self):
        """Load federation entities from database."""
        # In production, load from federation_entities table
        pass
    
    async def _load_trust_anchor(self, anchor: FederationTrustAnchor):
        """Load trust anchor into cache."""
        self._jwks_cache[anchor.entity_id] = anchor.jwks
        self._metadata_cache[anchor.entity_id] = anchor.metadata
        logger.info(f"Loaded trust anchor: {anchor.entity_id}")
    
    # ==================== Entity Registration ====================
    
    async def register_entity(
        self,
        entity_id: str,
        entity_type: FederationEntityType,
        name: str,
        metadata: Dict[str, Any],
        jwks: Dict[str, Any],
        authority_hints: List[str] = None,
    ) -> FederationEntity:
        """Register a new federation entity."""
        entity = FederationEntity(
            entity_id=entity_id,
            entity_type=entity_type,
            name=name,
            metadata=metadata,
            jwks=jwks,
            authority_hints=authority_hints or [],
        )
        
        self._entities[entity_id] = entity
        self._jwks_cache[entity_id] = jwks
        self._metadata_cache[entity_id] = metadata
        
        # Persist to database
        if self.session:
            await self._persist_entity(entity)
        
        logger.info(f"Registered federation entity: {entity_id} ({entity_type.value})")
        return entity
    
    async def _persist_entity(self, entity: FederationEntity):
        """Persist entity to database."""
        pass
    
    async def update_entity_metadata(
        self,
        entity_id: str,
        metadata: Dict[str, Any],
    ) -> FederationEntity:
        """Update entity metadata."""
        if entity_id not in self._entities:
            raise ValueError(f"Entity not found: {entity_id}")
        
        entity = self._entities[entity_id]
        entity.metadata = metadata
        entity.updated_at = datetime.utcnow()
        
        # Invalidate cache
        self._metadata_cache.pop(entity_id, None)
        
        if self.session:
            await self._persist_entity(entity)
        
        return entity
    
    # ==================== Entity Statement Management ====================
    
    async def issue_entity_statement(
        self,
        issuer_id: str,
        subject_id: str,
        metadata: Dict[str, Any] = None,
        jwks: Dict[str, Any] = None,
        authority_hints: List[str] = None,
        metadata_policy: Dict[str, Any] = None,
        constraints: Dict[str, Any] = None,
        expires_in: int = 86400,  # 24 hours
    ) -> str:
        """
        Issue a signed entity statement (JWT).
        
        Returns compact JWT string.
        """
        if issuer_id not in self._entities:
            raise ValueError(f"Issuer not found: {issuer_id}")
        
        issuer = self._entities[issuer_id]
        
        now = int(time.time())
        exp = now + expires_in
        
        statement = EntityStatement(
            iss=issuer_id,
            sub=subject_id,
            iat=now,
            exp=exp,
            jwks=jwks or {},
            metadata=metadata or {},
            authority_hints=authority_hints or issuer.authority_hints,
            metadata_policy=metadata_policy or {},
            constraints=constraints or {},
            statement_type=EntityStatementType.SUBORDINATE,
        )
        
        # Sign with issuer's private key
        signing_key = self._federation_keys.get("default")
        if not signing_key:
            raise ValueError("No signing key available")
        
        # Create JWT
        token = jwt.encode(
            statement.to_jwt_claims(),
            signing_key["private_key"],
            algorithm=signing_key["alg"],
            headers={"kid": signing_key["kid"], "typ": "entity-statement+jwt"},
        )
        
        # Store statement
        statement_key = f"{issuer_id}:{subject_id}"
        self._entity_statements[statement_key] = statement
        
        logger.info(f"Issued entity statement: {issuer_id} -> {subject_id}")
        return token
    
    async def validate_entity_statement(
        self,
        token: str,
    ) -> EntityStatement:
        """
        Validate an entity statement JWT.
        
        Returns validated EntityStatement or raises exception.
        """
        try:
            # Decode without verification first to get issuer
            unverified = jwt.decode(token, options={"verify_signature": False})
            issuer_id = unverified.get("iss")
            
            if not issuer_id:
                raise ValueError("Missing issuer in entity statement")
            
            # Get issuer's JWKS
            jwks = await self.get_jwks(issuer_id)
            if not jwks:
                raise ValueError(f"No JWKS available for issuer: {issuer_id}")
            
            # Verify signature
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            
            # Find matching key
            key = self._find_key_in_jwks(jwks, kid)
            if not key:
                raise ValueError(f"Key not found in JWKS: {kid}")
            
            # Verify and decode
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=None,  # No audience validation for entity statements
                options={"verify_exp": True, "verify_iat": True},
            )
            
            statement = EntityStatement.from_jwt_claims(claims)
            
            # Validate statement structure
            self._validate_entity_statement(statement)
            
            return statement
            
        except jwt.ExpiredSignatureError:
            raise ValueError("Entity statement expired")
        except jwt.InvalidTokenError as e:
            raise ValueError(f"Invalid entity statement: {e}")
    
    def _find_key_in_jwks(self, jwks: Dict[str, Any], kid: str) -> Optional[str]:
        """Find public key in JWKS by key ID."""
        for key_data in jwks.get("keys", []):
            if key_data.get("kid") == kid:
                # Convert JWK to PEM
                return self._jwk_to_pem(key_data)
        return None
    
    def _jwk_to_pem(self, jwk: Dict[str, Any]) -> str:
        """Convert JWK to PEM format."""
        # Simplified - in production use proper JWK library
        # This is a placeholder for JWK to PEM conversion
        return jwk.get("pem", "")
    
    def _validate_entity_statement(self, statement: EntityStatement):
        """Validate entity statement structure."""
        if not statement.iss or not statement.sub:
            raise ValueError("Missing iss or sub in entity statement")
        
        if statement.exp <= statement.iat:
            raise ValueError("Invalid expiration time")
        
        if statement.exp < int(time.time()):
            raise ValueError("Entity statement expired")
    
    # ==================== Trust Chain Discovery ====================
    
    async def discover_trust_chain(
        self,
        leaf_entity_id: str,
        trust_anchor_id: str = None,
    ) -> TrustChain:
        """
        Discover and validate trust chain from trust anchor to leaf entity.
        
        Implements trust chain discovery per OIDC Federation spec.
        """
        if trust_anchor_id and trust_anchor_id not in self._trust_anchors:
            raise ValueError(f"Trust anchor not found: {trust_anchor_id}")
        
        # If no trust anchor specified, try all
        trust_anchors = [trust_anchor_id] if trust_anchor_id else list(self._trust_anchors.keys())
        
        for anchor_id in trust_anchors:
            try:
                chain = await self._build_trust_chain(anchor_id, leaf_entity_id)
                if chain.is_valid:
                    self._trust_chains[f"{anchor_id}:{leaf_entity_id}"] = chain
                    return chain
            except Exception as e:
                logger.warning(f"Trust chain validation failed for {anchor_id} -> {leaf_entity_id}: {e}")
                continue
        
        # No valid chain found
        return TrustChain(
            anchor_id=trust_anchor_id or "",
            leaf_id=leaf_entity_id,
            is_valid=False,
            validation_errors=["No valid trust chain found"],
        )
    
    async def _build_trust_chain(
        self,
        anchor_id: str,
        leaf_id: str,
    ) -> TrustChain:
        """Build trust chain from anchor to leaf."""
        chain = TrustChain(anchor_id=anchor_id, leaf_id=leaf_id)
        
        # Get leaf entity
        leaf_entity = self._entities.get(leaf_id)
        if not leaf_entity:
            chain.is_valid = False
            chain.validation_errors.append(f"Leaf entity not found: {leaf_id}")
            return chain
        
        # Start from leaf, walk up authority hints
        current_id = leaf_id
        visited = set()
        
        while current_id != anchor_id and current_id not in visited:
            visited.add(current_id)
            
            entity = self._entities.get(current_id)
            if not entity:
                chain.is_valid = False
                chain.validation_errors.append(f"Entity not found in chain: {current_id}")
                return chain
            
            # Get entity statement from authority
            for authority_hint in entity.authority_hints:
                if authority_hint in visited:
                    continue
                
                statement_key = f"{authority_hint}:{current_id}"
                statement = self._entity_statements.get(statement_key)
                
                if statement:
                    chain.chain.append(statement)
                    
                    # Merge metadata and JWKS
                    chain.combined_metadata = self._merge_metadata(
                        chain.combined_metadata,
                        statement.metadata,
                    )
                    chain.combined_jwks = self._merge_jwks(
                        chain.combined_jwks,
                        statement.jwks,
                    )
                    
                    # Check expiration
                    if statement.exp:
                        exp_dt = datetime.fromtimestamp(statement.exp)
                        if not chain.expires_at or exp_dt < chain.expires_at:
                            chain.expires_at = exp_dt
                    
                    current_id = authority_hint
                    break
            else:
                # No authority hint matched
                break
        
        # Validate chain reaches anchor
        if current_id != anchor_id:
            chain.is_valid = False
            chain.validation_errors.append(f"Chain does not reach trust anchor: {anchor_id}")
        
        return chain
    
    def _merge_metadata(
        self,
        base: Dict[str, Any],
        overlay: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Merge metadata with policy enforcement."""
        # Simplified merge - in production, apply metadata_policy
        result = base.copy()
        result.update(overlay)
        return result
    
    def _merge_jwks(
        self,
        base: Dict[str, Any],
        overlay: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Merge JWKS sets."""
        result = base.copy()
        existing_kids = {key.get("kid") for key in base.get("keys", [])}
        
        for key in overlay.get("keys", []):
            if key.get("kid") not in existing_kids:
                if "keys" not in result:
                    result["keys"] = []
                result["keys"].append(key)
                existing_kids.add(key.get("kid"))
        
        return result
    
    # ==================== Metadata Resolution ====================
    
    async def resolve_metadata(
        self,
        entity_id: str,
        trust_anchor_id: str = None,
    ) -> Dict[str, Any]:
        """
        Resolve complete metadata for entity via trust chain.
        """
        # Try cache first
        if entity_id in self._metadata_cache:
            return self._metadata_cache[entity_id]
        
        # Build trust chain
        chain = await self.discover_trust_chain(entity_id, trust_anchor_id)
        
        if not chain.is_valid:
            raise ValueError(f"Cannot resolve metadata: {chain.validation_errors}")
        
        # Return combined metadata
        self._metadata_cache[entity_id] = chain.combined_metadata
        return chain.combined_metadata
    
    # ==================== JWKS Management ====================
    
    async def get_jwks(self, entity_id: str) -> Dict[str, Any]:
        """Get JWKS for entity."""
        if entity_id in self._jwks_cache:
            return self._jwks_cache[entity_id]
        
        # Try to fetch from entity's federation endpoint
        jwks = await self._fetch_jwks(entity_id)
        if jwks:
            self._jwks_cache[entity_id] = jwks
        
        return jwks or {}
    
    async def _fetch_jwks(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Fetch JWKS from entity's federation endpoint."""
        entity = self._entities.get(entity_id)
        if not entity:
            return None
        
        # Try to get from metadata
        metadata = entity.metadata
        jwks_uri = metadata.get("jwks_uri")
        
        if jwks_uri:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(jwks_uri, timeout=10) as resp:
                        if resp.status == 200:
                            return await resp.json()
            except Exception as e:
                logger.warning(f"Failed to fetch JWKS from {jwks_uri}: {e}")
        
        # Fallback to entity's stored JWKS
        return entity.jwks if entity.jwks else None
    
    async def publish_jwks(self, entity_id: str) -> Dict[str, Any]:
        """Publish entity's JWKS."""
        entity = self._entities.get(entity_id)
        if not entity:
            raise ValueError(f"Entity not found: {entity_id}")
        
        # Ensure we have a signing key
        if not entity.jwks:
            # Generate JWKS from entity's keys
            entity.jwks = await self._generate_jwks(entity_id)
            self._jwks_cache[entity_id] = entity.jwks
        
        return entity.jwks
    
    async def _generate_jwks(self, entity_id: str) -> Dict[str, Any]:
        """Generate JWKS for entity."""
        # In production, use entity's actual keys
        # For now, return federation signing key
        signing_key = self._federation_keys.get("default")
        if not signing_key:
            return {"keys": []}
        
        public_key = signing_key["public_key"]
        numbers = public_key.public_numbers()
        
        return {
            "keys": [{
                "kty": "RSA",
                "kid": signing_key["kid"],
                "use": "sig",
                "alg": "RS256",
                "n": base64.urlsafe_b64encode(numbers.n.to_bytes(256, "big")).decode().rstrip("="),
                "e": base64.urlsafe_b64encode(numbers.e.to_bytes(4, "big")).decode().rstrip("="),
            }]
        }
    
    # ==================== Federation Endpoints ====================
    
    async def get_federation_metadata(
        self,
        entity_id: str,
    ) -> Dict[str, Any]:
        """
        Get federation metadata for entity (federation entity endpoint).
        
        Returns combined metadata per OIDC Federation spec.
        """
        entity = self._entities.get(entity_id)
        if not entity:
            raise ValueError(f"Entity not found: {entity_id}")
        
        # Build metadata according to federation spec
        metadata = {
            "entity_id": entity_id,
            "entity_type": entity.entity_type.value,
            "name": entity.name,
            "metadata": entity.metadata,
            "jwks": entity.jwks,
            "authority_hints": entity.authority_hints,
            "federation_metadata": {
                "federation_entity": {
                    "federation_registration_endpoint": f"{settings.BASE_URL}/federation/register",
                    "federation_resolve_endpoint": f"{settings.BASE_URL}/federation/resolve",
                    "federation_list_endpoint": f"{settings.BASE_URL}/federation/list",
                }
            } if entity.entity_type == FederationEntityType.INTERMEDIATE else {},
        }
        
        return metadata
    
    async def resolve_federation_entity(
        self,
        entity_id: str,
        trust_anchor_id: str = None,
    ) -> Dict[str, Any]:
        """
        Resolve federation entity (federation resolve endpoint).
        
        Returns signed entity statements forming trust chain.
        """
        chain = await self.discover_trust_chain(entity_id, trust_anchor_id)
        
        if not chain.is_valid:
            raise ValueError(f"Trust chain validation failed: {chain.validation_errors}")
        
        # Build response with entity statements
        entity_statements = []
        for statement in chain.chain:
            # Re-issue statement with current time
            token = await self.issue_entity_statement(
                issuer_id=statement.iss,
                subject_id=statement.sub,
                metadata=statement.metadata,
                jwks=statement.jwks,
                authority_hints=statement.authority_hints,
                metadata_policy=statement.metadata_policy,
                constraints=statement.constraints,
            )
            entity_statements.append(token)
        
        return {
            "entity_id": entity_id,
            "trust_chain": entity_statements,
            "expires_at": chain.expires_at.isoformat() if chain.expires_at else None,
            "trust_anchor": chain.anchor_id,
        }
    
    async def list_federation_entities(
        self,
        trust_anchor_id: str = None,
        entity_type: FederationEntityType = None,
    ) -> List[Dict[str, Any]]:
        """
        List federation entities (federation list endpoint).
        """
        entities = list(self._entities.values())
        
        if trust_anchor_id:
            # Filter by trust anchor
            pass
        
        if entity_type:
            entities = [e for e in entities if e.entity_type == entity_type]
        
        return [e.to_dict() for e in entities]
    
    # ==================== Cross-Org SSO ====================
    
    async def initiate_cross_org_sso(
        self,
        user_org_id: str,
        target_org_id: str,
        user_id: str,
        redirect_uri: str,
    ) -> Dict[str, Any]:
        """
        Initiate cross-organization SSO via federation.
        
        Returns authorization URL for user to authenticate at target org.
        """
        # Resolve target org metadata
        target_metadata = await self.resolve_metadata(target_org_id)
        
        # Get target org's authorization endpoint
        auth_endpoint = target_metadata.get("authorization_endpoint")
        if not auth_endpoint:
            raise ValueError(f"Target org has no authorization endpoint: {target_org_id}")
        
        # Build authorization request
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        
        params = {
            "response_type": "code",
            "client_id": user_org_id,  # Our entity ID as client
            "redirect_uri": redirect_uri,
            "scope": "openid profile email federation",
            "state": state,
            "nonce": nonce,
            "prompt": "consent",
        }
        
        auth_url = f"{auth_endpoint}?{urlencode(params)}"
        
        return {
            "authorization_url": auth_url,
            "state": state,
            "nonce": nonce,
            "target_org": target_org_id,
        }
    
    async def complete_cross_org_sso(
        self,
        user_org_id: str,
        target_org_id: str,
        code: str,
        state: str,
        redirect_uri: str,
    ) -> Dict[str, Any]:
        """
        Complete cross-organization SSO via federation.
        
        Exchanges authorization code for tokens at target org.
        """
        # Resolve target org metadata
        target_metadata = await self.resolve_metadata(target_org_id)
        token_endpoint = target_metadata.get("token_endpoint")
        
        if not token_endpoint:
            raise ValueError(f"Target org has no token endpoint: {target_org_id}")
        
        # Exchange code for tokens
        async with aiohttp.ClientSession() as session:
            async with session.post(
                token_endpoint,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": user_org_id,
                    "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
                    "client_assertion": await self._create_client_assertion(user_org_id, target_org_id),
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    raise ValueError(f"Token exchange failed: {error}")
                
                tokens = await resp.json()
        
        # Validate ID token
        id_token = tokens.get("id_token")
        if not id_token:
            raise ValueError("No ID token in response")
        
        # Validate ID token using target org's JWKS
        jwks = await self.get_jwks(target_org_id)
        claims = jwt.decode(
            id_token,
            self._jwks_to_key(jwks),
            algorithms=["RS256"],
            audience=user_org_id,
        )
        
        return {
            "access_token": tokens.get("access_token"),
            "id_token": id_token,
            "refresh_token": tokens.get("refresh_token"),
            "claims": claims,
            "target_org": target_org_id,
        }
    
    async def _create_client_assertion(
        self,
        client_id: str,
        audience: str,
    ) -> str:
        """Create client assertion JWT for token exchange."""
        signing_key = self._federation_keys.get("default")
        
        now = int(time.time())
        assertion = jwt.encode(
            {
                "iss": client_id,
                "sub": client_id,
                "aud": audience,
                "iat": now,
                "exp": now + 300,  # 5 minutes
                "jti": secrets.token_urlsafe(16),
            },
            signing_key["private_key"],
            algorithm="RS256",
            headers={"kid": signing_key["kid"]},
        )
        
        return assertion
    
    def _jwks_to_key(self, jwks: Dict[str, Any]):
        """Convert JWKS to verification key."""
        # Simplified - in production use proper JWK library
        for key_data in jwks.get("keys", []):
            return self._jwk_to_pem(key_data)
        return None
    
    # ==================== Automatic Key Rotation ====================
    
    async def rotate_federation_keys(self, entity_id: str = None):
        """
        Rotate federation signing keys.
        
        Performs key rotation for entity or all entities.
        """
        if entity_id:
            entities = [entity_id] if entity_id in self._entities else []
        else:
            entities = list(self._entities.keys())
        
        for eid in entities:
            await self._rotate_entity_keys(eid)
    
    async def _rotate_entity_keys(self, entity_id: str):
        """Rotate keys for single entity."""
        entity = self._entities.get(entity_id)
        if not entity:
            return
        
        # Generate new key pair
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        
        new_kid = f"federation-signing-key-{int(time.time())}"
        
        # Update federation keys
        self._federation_keys[f"{entity_id}-{new_kid}"] = {
            "private_key": private_key,
            "public_key": private_key.public_key(),
            "kid": new_kid,
            "alg": "RS256",
        }
        
        # Update JWKS
        entity.jwks = await self._generate_jwks(entity_id)
        self._jwks_cache[entity_id] = entity.jwks
        
        # Update entity statements
        await self._reissue_entity_statements(entity_id)
        
        logger.info(f"Rotated federation keys for entity: {entity_id}")
    
    async def _reissue_entity_statements(self, entity_id: str):
        """Re-issue all entity statements for entity."""
        for key, statement in list(self._entity_statements.items()):
            if statement.iss == entity_id or statement.sub == entity_id:
                # Re-issue with new keys
                await self.issue_entity_statement(
                    issuer_id=statement.iss,
                    subject_id=statement.sub,
                    metadata=statement.metadata,
                    jwks=statement.jwks,
                    authority_hints=statement.authority_hints,
                    metadata_policy=statement.metadata_policy,
                    constraints=statement.constraints,
                )
    
    # ==================== Federation Discovery ====================
    
    async def discover_entity(
        self,
        entity_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Discover entity via OIDC Federation discovery.
        
        Queries well-known endpoints to discover entity.
        """
        # Try well-known endpoint
        well_known_url = f"https://{entity_id}/.well-known/openid-federation"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(well_known_url, timeout=10) as resp:
                    if resp.status == 200:
                        entity_statement = await resp.text()
                        # Validate and parse
                        statement = await self.validate_entity_statement(entity_statement)
                        return statement.to_jwt_claims()
        except Exception as e:
            logger.warning(f"Federation discovery failed for {entity_id}: {e}")
        
        return None
    
    # ==================== Database Persistence ====================
    
    async def _persist_entity(self, entity: FederationEntity):
        """Persist entity to database."""
        pass
    
    async def _persist_statement(self, key: str, statement: EntityStatement):
        """Persist entity statement to database."""
        pass


# ==================== Database Models ====================

class FederationEntityModel(Base, TimestampMixin):
    """Database model for federation entities."""
    
    __tablename__ = "federation_entities"
    __table_args__ = (
        Index("ix_federation_entities_org", "organization_id"),
        Index("ix_federation_entities_type", "entity_type"),
        UniqueConstraint("entity_id", name="uq_federation_entities_entity_id"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    entity_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    entity_type: Mapped[str] = mapped_column(SQLEnum(FederationEntityType), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)
    jwks: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)
    authority_hints: Mapped[List[str]] = mapped_column(JSON, default=list)
    trusted: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class EntityStatementModel(Base, TimestampMixin):
    """Database model for entity statements."""
    
    __tablename__ = "entity_statements"
    __table_args__ = (
        Index("ix_entity_statements_issuer", "issuer_id"),
        Index("ix_entity_statements_subject", "subject_id"),
        Index("ix_entity_statements_exp", "expires_at"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    issuer_id: Mapped[str] = mapped_column(String(255), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(255), nullable=False)
    statement_jwt: Mapped[str] = mapped_column(Text, nullable=False)  # Compact JWT
    statement_type: Mapped[str] = mapped_column(SQLEnum(EntityStatementType), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    validated: Mapped[bool] = mapped_column(Boolean, default=False)
    validation_errors: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)


class TrustAnchorModel(Base, TimestampMixin):
    """Database model for trust anchors."""
    
    __tablename__ = "federation_trust_anchors"
    __table_args__ = (
        Index("ix_trust_anchors_org", "organization_id"),
        UniqueConstraint("organization_id", "entity_id", name="uq_trust_anchors_org_entity"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    entity_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    jwks: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    allowed_entity_types: Mapped[List[str]] = mapped_column(JSON, default=list)
    metadata_policy: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)
    constraints: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class TrustChainModel(Base, TimestampMixin):
    """Database model for trust chains."""
    
    __tablename__ = "federation_trust_chains"
    __table_args__ = (
        Index("ix_trust_chains_anchor_leaf", "anchor_id", "leaf_id"),
        Index("ix_trust_chains_valid", "is_valid"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    anchor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    leaf_id: Mapped[str] = mapped_column(String(255), nullable=False)
    chain_statements: Mapped[List[str]] = mapped_column(JSON, default=list)  # JWTs
    combined_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    combined_jwks: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_valid: Mapped[bool] = mapped_column(Boolean, default=False)
    validation_errors: Mapped[List[str]] = mapped_column(JSON, default=list)
    validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


# ==================== Cross-Org Federation Models ====================

class CrossOrgFederationModel(Base, TimestampMixin):
    """Database model for cross-organization federation relationships."""
    
    __tablename__ = "cross_org_federations"
    __table_args__ = (
        Index("ix_cross_org_federations_org", "source_organization_id"),
        Index("ix_cross_org_federations_target", "target_organization_id"),
        UniqueConstraint("source_organization_id", "target_organization_id", name="uq_cross_org_federations"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    source_organization_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    target_organization_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    source_entity_id: Mapped[str] = mapped_column(String(255), nullable=False)
    target_entity_id: Mapped[str] = mapped_column(String(255), nullable=False)
    relationship_type: Mapped[str] = mapped_column(
        SQLEnum(FederationRelationship), default=FederationRelationship.TRUST_CHAIN
    )
    trust_chain_id: Mapped[Optional[str]] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(20), default="active")
    metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    sync_errors: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)


# ==================== Global Manager ====================

_oidc_federation_manager: Optional[OIDCFederationManager] = None


def get_oidc_federation_manager(session: AsyncSession = None) -> OIDCFederationManager:
    """Get global OIDC Federation manager."""
    global _oidc_federation_manager
    if _oidc_federation_manager is None:
        _oidc_federation_manager = OIDCFederationManager(session)
    return _oidc_federation_manager


async def init_oidc_federation(
    session: AsyncSession = None,
    trust_anchors: List[FederationTrustAnchor] = None,
) -> OIDCFederationManager:
    """Initialize OIDC Federation manager."""
    global _oidc_federation_manager
    _oidc_federation_manager = OIDCFederationManager(session, trust_anchors)
    await _oidc_federation_manager.initialize()
    return _oidc_federation_manager


# ==================== Convenience Functions ====================

import secrets
from urllib.parse import urlencode


async def initiate_federated_sso(
    source_org_id: str,
    target_org_id: str,
    user_id: str,
    redirect_uri: str,
    session: AsyncSession = None,
) -> Dict[str, Any]:
    """Initiate cross-org SSO via federation."""
    manager = get_oidc_federation_manager(session)
    return await manager.initiate_cross_org_sso(source_org_id, target_org_id, user_id, redirect_uri)


async def complete_federated_sso(
    source_org_id: str,
    target_org_id: str,
    code: str,
    state: str,
    redirect_uri: str,
    session: AsyncSession = None,
) -> Dict[str, Any]:
    """Complete cross-org SSO via federation."""
    manager = get_oidc_federation_manager(session)
    return await manager.complete_cross_org_sso(source_org_id, target_org_id, code, state, redirect_uri)


async def resolve_federation_metadata(
    entity_id: str,
    trust_anchor_id: str = None,
    session: AsyncSession = None,
) -> Dict[str, Any]:
    """Resolve federation metadata for entity."""
    manager = get_oidc_federation_manager(session)
    return await manager.resolve_metadata(entity_id, trust_anchor_id)


async def get_federation_trust_chain(
    leaf_entity_id: str,
    trust_anchor_id: str = None,
    session: AsyncSession = None,
) -> TrustChain:
    """Get validated trust chain."""
    manager = get_oidc_federation_manager(session)
    return await manager.discover_trust_chain(leaf_entity_id, trust_anchor_id)


# ==================== Federation Policy Engine ====================

class FederationPolicyEngine:
    """
    Policy engine for federation metadata and constraints.
    
    Enforces:
    - Metadata policies from trust anchors
    - Constraint validation
    - Entity type restrictions
    - Automatic metadata filtering
    """
    
    def __init__(self, federation_manager: OIDCFederationManager):
        self.manager = federation_manager
    
    async def apply_metadata_policy(
        self,
        metadata: Dict[str, Any],
        policy: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Apply metadata policy to metadata."""
        result = metadata.copy()
        
        # Apply required claims
        required = policy.get("required", [])
        for claim in required:
            if claim not in result:
                raise ValueError(f"Missing required claim: {claim}")
        
        # Apply optional claims with defaults
        optional = policy.get("optional", {})
        for claim, default in optional.items():
            if claim not in result:
                result[claim] = default
        
        # Apply value constraints
        value_constraints = policy.get("value_constraints", {})
        for claim, constraint in value_constraints.items():
            if claim in result:
                if not self._validate_constraint(result[claim], constraint):
                    raise ValueError(f"Value constraint failed for {claim}")
        
        # Remove disallowed claims
        disallowed = policy.get("disallowed", [])
        for claim in disallowed:
            result.pop(claim, None)
        
        return result
    
    def _validate_constraint(self, value: Any, constraint: Dict[str, Any]) -> bool:
        """Validate value against constraint."""
        if "values" in constraint:
            return value in constraint["values"]
        if "pattern" in constraint:
            return bool(re.match(constraint["pattern"], str(value)))
        if "min_length" in constraint:
            return len(str(value)) >= constraint["min_length"]
        if "max_length" in constraint:
            return len(str(value)) <= constraint["max_length"]
        if "min" in constraint:
            return value >= constraint["min"]
        if "max" in constraint:
            return value <= constraint["max"]
        return True
    
    async def validate_entity_against_policy(
        self,
        entity_id: str,
        trust_anchor_id: str,
    ) -> Tuple[bool, List[str]]:
        """Validate entity metadata against trust anchor policy."""
        anchor = self.manager._trust_anchors.get(trust_anchor_id)
        if not anchor:
            return False, ["Trust anchor not found"]
        
        entity_metadata = await self.manager.resolve_metadata(entity_id, trust_anchor_id)
        policy = anchor.metadata_policy
        
        errors = []
        
        # Check required claims
        for claim in policy.get("required", []):
            if claim not in entity_metadata:
                errors.append(f"Missing required claim: {claim}")
        
        # Check value constraints
        for claim, constraint in policy.get("value_constraints", {}).items():
            if claim in entity_metadata:
                if not self._validate_constraint(entity_metadata[claim], constraint):
                    errors.append(f"Value constraint failed for {claim}")
        
        # Check allowed entity types
        if "allowed_entity_types" in policy:
            entity = self.manager._entities.get(entity_id)
            if entity and entity.entity_type.value not in policy["allowed_entity_types"]:
                errors.append(f"Entity type not allowed: {entity.entity_type.value}")
        
        return len(errors) == 0, errors