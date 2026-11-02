"""MFA Service: TOTP, Passkeys/WebAuthn, Device Trust, Security Events."""

import base64
import hashlib
import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import pyotp
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import (
    ACCESS,
    EMAIL_VERIFY,
    INVITE,
    PASSWORD_RESET,
    REFRESH,
    create_access_token,
    create_email_verification_token,
    create_invite_token,
    create_password_reset_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.core.timeutils import utcnow
from app.models.user import (
    User,
    Session,
    MFAMethod,
    TrustedDevice,
    SecurityAuditEvent,
    OrganizationSecurityPolicy,
    AccessReview,
    AccessReviewItem,
)
from app.models.organization import Organization
from app.models.role import UserRoleModel, RolePermission, Permission
from app.services.audit_service import audit_service
from app.services.email_service import email_service, hash_token
from app.services.event_service import event_service
from app.services.notification_service import notification_service

logger = logging.getLogger("vcos.mfa")

# Encryption key for TOTP secrets (derived from settings)
def _get_encryption_key() -> bytes:
    settings = get_settings()
    # Use a separate key derivation for MFA secrets
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"vcos-mfa-salt-v1",
        iterations=100000,
    )
    return kdf.derive(settings.SECRET_KEY.encode())


def _encrypt_secret(secret: str) -> str:
    """Encrypt a TOTP secret using AES-GCM."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key = _get_encryption_key()
    aesgcm = AESGCM(key)
    nonce = secrets.token_bytes(12)
    ciphertext = aesgcm.encrypt(nonce, secret.encode(), None)
    return base64.b64encode(nonce + ciphertext).decode()


def _decrypt_secret(encrypted: str) -> str:
    """Decrypt a TOTP secret."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key = _get_encryption_key()
    aesgcm = AESGCM(key)
    data = base64.b64decode(encrypted)
    nonce = data[:12]
    ciphertext = data[12:]
    return aesgcm.decrypt(nonce, ciphertext, None).decode()


class MFAService:
    """Service for managing MFA methods, passkeys, device trust, and security events."""

    # ------------------------------------------------------------------ TOTP

    async def setup_totp(
        self,
        db: AsyncSession,
        *,
        user: User,
        device_name: Optional[str] = None,
    ) -> dict[str, Any]:
        """Set up a new TOTP method for a user. Returns provisioning URI and secret."""
        # Check if user already has TOTP
        existing = await db.execute(
            select(MFAMethod).where(
                MFAMethod.user_id == user.id,
                MFAMethod.method_type == "totp",
            )
        )
        if existing.scalars().first():
            raise ValueError("TOTP already configured. Remove existing method first.")

        # Generate secret
        secret = pyotp.random_base32()
        encrypted = _encrypt_secret(secret)

        # Create MFA method
        mfa_method = MFAMethod(
            user_id=user.id,
            organization_id=user.organization_id,
            method_type="totp",
            secret_encrypted=encrypted,
            device_name=device_name or "Authenticator App",
            is_verified=False,
            is_primary=True,
        )
        db.add(mfa_method)
        await db.flush()

        # Generate provisioning URI
        totp = pyotp.TOTP(secret)
        provisioning_uri = totp.provisioning_uri(
            name=user.email,
            issuer_name="VCOS",
        )

        # Generate backup codes
        backup_codes = [secrets.token_hex(4).upper() for _ in range(10)]
        backup_hash = hashlib.sha256("\n".join(backup_codes).encode()).hexdigest()
        mfa_method.backup_codes_hash = backup_hash
        await db.flush()

        await self._log_security_event(
            db,
            user=user,
            event_type="mfa.totp.setup",
            event_category="auth",
            severity="info",
            outcome="success",
            details={"method_id": mfa_method.id, "device_name": device_name},
        )

        return {
            "method_id": mfa_method.id,
            "provisioning_uri": provisioning_uri,
            "secret": secret,  # Only returned once during setup
            "backup_codes": backup_codes,
        }

    async def verify_totp(
        self,
        db: AsyncSession,
        *,
        user: User,
        code: str,
        method_id: Optional[str] = None,
    ) -> bool:
        """Verify a TOTP code."""
        query = select(MFAMethod).where(
            MFAMethod.user_id == user.id,
            MFAMethod.method_type == "totp",
            MFAMethod.is_verified == True,
        )
        if method_id:
            query = query.where(MFAMethod.id == method_id)

        result = await db.execute(query)
        mfa_method = result.scalars().first()

        if not mfa_method or not mfa_method.secret_encrypted:
            return False

        try:
            secret = _decrypt_secret(mfa_method.secret_encrypted)
            totp = pyotp.TOTP(secret)
            valid = totp.verify(code, valid_window=1)

            if valid:
                mfa_method.last_used_at = utcnow()
                mfa_method.use_count += 1
                await db.flush()

                await self._log_security_event(
                    db,
                    user=user,
                    event_type="mfa.totp.verify",
                    event_category="auth",
                    severity="info",
                    outcome="success",
                    details={"method_id": mfa_method.id},
                )
            else:
                await self._log_security_event(
                    db,
                    user=user,
                    event_type="mfa.totp.verify",
                    event_category="auth",
                    severity="warning",
                    outcome="failure",
                    details={"method_id": mfa_method.id, "reason": "invalid_code"},
                )

            return valid
        except Exception as e:
            logger.error(f"TOTP verification error: {e}")
            return False

    async def verify_totp_setup(
        self,
        db: AsyncSession,
        *,
        user: User,
        code: str,
        method_id: str,
    ) -> bool:
        """Verify TOTP during initial setup."""
        mfa_method = await db.get(MFAMethod, method_id)
        if not mfa_method or mfa_method.user_id != user.id or mfa_method.method_type != "totp":
            return False

        if not mfa_method.secret_encrypted:
            return False

        try:
            secret = _decrypt_secret(mfa_method.secret_encrypted)
            totp = pyotp.TOTP(secret)
            valid = totp.verify(code, valid_window=1)

            if valid:
                mfa_method.is_verified = True
                mfa_method.verified_at = utcnow()
                user.mfa_enabled = True
                user.mfa_setup_at = utcnow()
                await db.flush()

                await self._log_security_event(
                    db,
                    user=user,
                    event_type="mfa.totp.enabled",
                    event_category="auth",
                    severity="info",
                    outcome="success",
                    details={"method_id": mfa_method.id},
                )
            else:
                await self._log_security_event(
                    db,
                    user=user,
                    event_type="mfa.totp.setup.verify",
                    event_category="auth",
                    severity="warning",
                    outcome="failure",
                    details={"method_id": mfa_method.id, "reason": "invalid_code"},
                )

            return valid
        except Exception as e:
            logger.error(f"TOTP setup verification error: {e}")
            return False

    # ------------------------------------------------------------------ Passkeys/WebAuthn

    async def start_passkey_registration(
        self,
        db: AsyncSession,
        *,
        user: User,
        device_name: Optional[str] = None,
    ) -> dict[str, Any]:
        """Start WebAuthn passkey registration. Returns creation options."""
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization

        # Generate challenge
        challenge = secrets.token_bytes(32)

        # Store challenge in session (in production, use Redis or session store)
        # For now, we'll return it to the client to send back

        rp_id = get_settings().WEBAUTHN_RP_ID or "localhost"
        rp_name = "VCOS"

        # User info
        user_handle = user.id.encode()
        user_name = user.email
        user_display_name = user.full_name or user.email

        # Relying party
        rp = {"id": rp_id, "name": rp_name}

        # User
        user_entity = {
            "id": base64.urlsafe_b64encode(user_handle).decode().rstrip("="),
            "name": user_name,
            "displayName": user_display_name,
        }

        # Credential creation options
        options = {
            "publicKey": {
                "rp": rp,
                "user": user_entity,
                "challenge": base64.urlsafe_b64encode(challenge).decode().rstrip("="),
                "pubKeyCredParams": [
                    {"type": "public-key", "alg": -7},  # ES256
                    {"type": "public-key", "alg": -257},  # RS256
                ],
                "timeout": 60000,
                "excludeCredentials": [],
                "authenticatorSelection": {
                    "authenticatorAttachment": "platform",
                    "residentKey": "preferred",
                    "requireResidentKey": True,
                    "userVerification": "preferred",
                },
                "attestation": "direct",
            }
        }

        # Store challenge temporarily (in production, use secure storage)
        # We'll hash it for storage
        challenge_hash = hashlib.sha256(challenge).hexdigest()

        return {
            "challenge": base64.urlsafe_b64encode(challenge).decode().rstrip("="),
            "challenge_hash": challenge_hash,
            "options": options,
        }

    async def complete_passkey_registration(
        self,
        db: AsyncSession,
        *,
        user: User,
        credential: dict,
        challenge_hash: str,
        device_name: Optional[str] = None,
    ) -> MFAMethod:
        """Complete WebAuthn passkey registration."""
        # Verify challenge (in production, retrieve from secure storage)
        # For now, we trust the client sent back the same challenge

        # Parse attestation object
        attestation_object = base64.urlsafe_b64decode(
            credential["response"]["attestationObject"] + "=="
        )
        client_data_json = base64.urlsafe_b64decode(
            credential["response"]["clientDataJSON"] + "=="
        )

        import json
        client_data = json.loads(client_data_json)

        # Verify challenge
        received_challenge_hash = hashlib.sha256(
            base64.urlsafe_b64decode(client_data["challenge"] + "==")
        ).hexdigest()

        if received_challenge_hash != challenge_hash:
            raise ValueError("Challenge mismatch")

        # Verify origin
        expected_origin = get_settings().WEBAUTHN_ORIGIN or "http://localhost:3000"
        if client_data["origin"] != expected_origin:
            raise ValueError("Origin mismatch")

        # Extract credential ID and public key
        credential_id = credential["id"]
        raw_id = credential["rawId"]

        # Parse attestation (simplified - in production use proper library)
        # Extract public key from attestation object
        # This is a simplified implementation

        # Create MFA method
        mfa_method = MFAMethod(
            user_id=user.id,
            organization_id=user.organization_id,
            method_type="passkey",
            credential_id=credential_id,
            public_key="stored_in_attestation",  # In production, extract actual public key
            device_name=device_name or "Passkey",
            device_type="platform",
            is_verified=True,
            verified_at=utcnow(),
            is_primary=True,
        )
        db.add(mfa_method)
        await db.flush()

        await self._log_security_event(
            db,
            user=user,
            event_type="mfa.passkey.registered",
            event_category="auth",
            severity="info",
            outcome="success",
            details={"method_id": mfa_method.id, "device_name": device_name},
        )

        return mfa_method

    async def start_passkey_authentication(
        self,
        db: AsyncSession,
        *,
        user: User,
    ) -> dict[str, Any]:
        """Start WebAuthn passkey authentication. Returns request options."""
        # Get user's passkeys
        result = await db.execute(
            select(MFAMethod).where(
                MFAMethod.user_id == user.id,
                MFAMethod.method_type == "passkey",
                MFAMethod.is_verified == True,
            )
        )
        passkeys = result.scalars().all()

        if not passkeys:
            raise ValueError("No passkeys registered")

        challenge = secrets.token_bytes(32)
        challenge_b64 = base64.urlsafe_b64encode(challenge).decode().rstrip("=")

        rp_id = get_settings().WEBAUTHN_RP_ID or "localhost"

        allow_credentials = [
            {
                "type": "public-key",
                "id": base64.urlsafe_b64decode(pk.credential_id + "=="),
                "transports": ["internal", "hybrid", "usb", "ble", "nfc"],
            }
            for pk in passkeys
        ]

        options = {
            "publicKey": {
                "challenge": challenge_b64,
                "timeout": 60000,
                "rpId": rp_id,
                "allowCredentials": allow_credentials,
                "userVerification": "preferred",
            }
        }

        challenge_hash = hashlib.sha256(challenge).hexdigest()

        return {
            "challenge": challenge_b64,
            "challenge_hash": challenge_hash,
            "options": options,
        }

    async def verify_passkey_authentication(
        self,
        db: AsyncSession,
        *,
        user: User,
        credential: dict,
        challenge_hash: str,
    ) -> bool:
        """Verify WebAuthn passkey authentication."""
        # Parse credential
        credential_id = credential["id"]
        authenticator_data = base64.urlsafe_b64decode(
            credential["response"]["authenticatorData"] + "=="
        )
        client_data_json = base64.urlsafe_b64decode(
            credential["response"]["clientDataJSON"] + "=="
        )
        signature = base64.urlsafe_b64decode(
            credential["response"]["signature"] + "=="
        )

        import json
        client_data = json.loads(client_data_json)

        # Verify challenge
        received_challenge_hash = hashlib.sha256(
            base64.urlsafe_b64decode(client_data["challenge"] + "==")
        ).hexdigest()

        if received_challenge_hash != challenge_hash:
            return False

        # Verify origin
        expected_origin = get_settings().WEBAUTHN_ORIGIN or "http://localhost:3000"
        if client_data["origin"] != expected_origin:
            return False

        # Find the passkey
        result = await db.execute(
            select(MFAMethod).where(
                MFAMethod.user_id == user.id,
                MFAMethod.method_type == "passkey",
                MFAMethod.credential_id == credential_id,
                MFAMethod.is_verified == True,
            )
        )
        mfa_method = result.scalars().first()

        if not mfa_method:
            return False

        # Verify signature (simplified - in production use proper library)
        # Extract public key and verify signature against authenticator data + client data hash
        # This is a simplified implementation

        mfa_method.last_used_at = utcnow()
        mfa_method.use_count += 1
        mfa_method.sign_count += 1
        await db.flush()

        await self._log_security_event(
            db,
            user=user,
            event_type="mfa.passkey.authenticated",
            event_category="auth",
            severity="info",
            outcome="success",
            details={"method_id": mfa_method.id},
        )

        return True

    # ------------------------------------------------------------------ Backup Codes

    async def generate_backup_codes(
        self,
        db: AsyncSession,
        *,
        user: User,
        method_id: str,
    ) -> list[str]:
        """Generate new backup codes for a TOTP method."""
        mfa_method = await db.get(MFAMethod, method_id)
        if not mfa_method or mfa_method.user_id != user.id or mfa_method.method_type != "totp":
            raise ValueError("Invalid MFA method")

        backup_codes = [secrets.token_hex(4).upper() for _ in range(10)]
        backup_hash = hashlib.sha256("\n".join(backup_codes).encode()).hexdigest()
        mfa_method.backup_codes_hash = backup_hash
        await db.flush()

        await self._log_security_event(
            db,
            user=user,
            event_type="mfa.backup_codes.generated",
            event_category="auth",
            severity="info",
            outcome="success",
            details={"method_id": method_id},
        )

        return backup_codes

    async def verify_backup_code(
        self,
        db: AsyncSession,
        *,
        user: User,
        code: str,
    ) -> bool:
        """Verify a backup code."""
        result = await db.execute(
            select(MFAMethod).where(
                MFAMethod.user_id == user.id,
                MFAMethod.method_type == "totp",
                MFAMethod.is_verified == True,
                MFAMethod.backup_codes_hash.isnot(None),
            )
        )
        mfa_method = result.scalars().first()

        if not mfa_method or not mfa_method.backup_codes_hash:
            return False

        # Check if code matches (hash comparison)
        code_hash = hashlib.sha256(code.upper().encode()).hexdigest()
        # In production, we'd need to check against individual hashed codes
        # For now, simplified check
        if code_hash == mfa_method.backup_codes_hash:
            # Mark code as used (in production, track individual codes)
            user.mfa_backup_codes_used += 1
            await db.flush()

            await self._log_security_event(
                db,
                user=user,
                event_type="mfa.backup_code.used",
                event_category="auth",
                severity="warning",
                outcome="success",
                details={"method_id": mfa_method.id, "codes_remaining": 10 - user.mfa_backup_codes_used},
            )
            return True

        return False

    # ------------------------------------------------------------------ Device Trust

    async def register_device(
        self,
        db: AsyncSession,
        *,
        user: User,
        device_fingerprint: str,
        device_name: str,
        device_type: str,
        browser: Optional[str] = None,
        os: Optional[str] = None,
        ip_address: Optional[str] = None,
        verification_method: str = "mfa",
        verified_by: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> TrustedDevice:
        """Register or update a trusted device."""
        # Check if device already exists
        result = await db.execute(
            select(TrustedDevice).where(
                TrustedDevice.user_id == user.id,
                TrustedDevice.device_fingerprint == device_fingerprint,
            )
        )
        device = result.scalars().first()

        settings = get_settings()
        trust_duration = timedelta(days=getattr(settings, "DEVICE_TRUST_DURATION_DAYS", 90))

        if device:
            # Update existing
            device.device_name = device_name
            device.device_type = device_type
            device.browser = browser
            device.os = os
            device.last_ip = ip_address
            device.last_seen_at = utcnow()
            device.last_session_id = session_id
            if not device.is_trusted and verification_method in ("mfa", "passkey", "admin"):
                device.is_trusted = True
                device.trusted_at = utcnow()
                device.trust_expires_at = utcnow() + trust_duration
                device.verification_method = verification_method
                device.verified_by = verified_by
                device.verified_at = utcnow()
        else:
            # Create new
            is_trusted = verification_method in ("mfa", "passkey", "admin")
            device = TrustedDevice(
                user_id=user.id,
                organization_id=user.organization_id,
                device_fingerprint=device_fingerprint,
                device_name=device_name,
                device_type=device_type,
                browser=browser,
                os=os,
                is_trusted=is_trusted,
                trusted_at=utcnow() if is_trusted else None,
                trust_expires_at=utcnow() + trust_duration if is_trusted else None,
                verification_method=verification_method,
                verified_by=verified_by,
                verified_at=utcnow() if is_trusted else None,
                last_ip=ip_address,
                last_seen_at=utcnow(),
                last_session_id=session_id,
            )
            db.add(device)
            await db.flush()

            # Check max trusted devices
            policy = await self.get_security_policy(db, user.organization_id)
            if policy and policy.max_trusted_devices:
                trusted_count = await db.execute(
                    select(func.count(TrustedDevice.id)).where(
                        TrustedDevice.user_id == user.id,
                        TrustedDevice.is_trusted == True,
                    )
                )
                if trusted_count.scalar() > policy.max_trusted_devices:
                    # Revoke oldest trusted device
                    oldest = await db.execute(
                        select(TrustedDevice).where(
                            TrustedDevice.user_id == user.id,
                            TrustedDevice.is_trusted == True,
                        ).order_by(TrustedDevice.trusted_at.asc())
                    )
                    oldest_device = oldest.scalars().first()
                    if oldest_device:
                        oldest_device.is_trusted = False
                        oldest_device.revoked_at = utcnow()
                        oldest_device.revoked_by = "system"
                        oldest_device.revocation_reason = "max_devices_exceeded"

        return device

    async def revoke_device(
        self,
        db: AsyncSession,
        *,
        user: User,
        device_id: str,
        revoked_by: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> bool:
        """Revoke a trusted device."""
        device = await db.get(TrustedDevice, device_id)
        if not device or device.user_id != user.id:
            return False

        device.is_trusted = False
        device.revoked_at = utcnow()
        device.revoked_by = revoked_by
        device.revocation_reason = reason

        # Also revoke any sessions associated with this device
        await db.execute(
            Session.__table__.update()
            .where(
                Session.user_id == user.id,
                Session.device_fingerprint == device.device_fingerprint,
                Session.revoked_at.is_(None),
            )
            .values(revoked_at=utcnow())
        )

        await self._log_security_event(
            db,
            user=user,
            organization_id=user.organization_id,
            event_type="device.revoked",
            event_category="access",
            severity="info",
            outcome="success",
            details={"device_id": device_id, "device_name": device.device_name, "reason": reason},
        )

        return True

    async def revoke_all_devices(
        self,
        db: AsyncSession,
        *,
        user: User,
        revoked_by: Optional[str] = None,
    ) -> int:
        """Revoke all trusted devices for a user."""
        result = await db.execute(
            select(TrustedDevice).where(
                TrustedDevice.user_id == user.id,
                TrustedDevice.is_trusted == True,
            )
        )
        devices = result.scalars().all()

        count = 0
        for device in devices:
            device.is_trusted = False
            device.revoked_at = utcnow()
            device.revoked_by = revoked_by
            device.revocation_reason = "revoke_all"
            count += 1

        # Revoke all sessions
        await db.execute(
            Session.__table__.update()
            .where(
                Session.user_id == user.id,
                Session.revoked_at.is_(None),
            )
            .values(revoked_at=utcnow())
        )

        await self._log_security_event(
            db,
            user=user,
            event_type="device.revoked_all",
            event_category="access",
            severity="warning",
            outcome="success",
            details={"count": count},
        )

        return count

    # ------------------------------------------------------------------ Session Security

    async def enforce_session_policy(
        self,
        db: AsyncSession,
        *,
        user: User,
        session: Session,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> dict[str, Any]:
        """Enforce organization session policies."""
        policy = await self.get_security_policy(db, user.organization_id)
        if not policy:
            return {"allowed": True}

        result = {"allowed": True, "requires_reauth": False, "reason": None}

        # Check idle timeout
        if session.last_activity_at:
            idle_minutes = (utcnow() - session.last_activity_at).total_seconds() / 60
            if idle_minutes > policy.session_idle_timeout_minutes:
                session.revoked_at = utcnow()
                result["allowed"] = False
                result["reason"] = "session_idle_timeout"
                await self._log_security_event(
                    db,
                    user=user,
                    event_type="session.revoked.idle",
                    event_category="access",
                    severity="info",
                    outcome="success",
                    details={"idle_minutes": idle_minutes, "limit": policy.session_idle_timeout_minutes},
                )
                return result

        # Check max duration
        session_age_hours = (utcnow() - session.created_at).total_seconds() / 3600
        if session_age_hours > policy.session_max_duration_hours:
            session.revoked_at = utcnow()
            result["allowed"] = False
            result["reason"] = "session_max_duration"
            await self._log_security_event(
                db,
                user=user,
                event_type="session.revoked.max_duration",
                event_category="access",
                severity="info",
                outcome="success",
                details={"session_age_hours": session_age_hours, "limit": policy.session_max_duration_hours},
            )
            return result

        # Check concurrent sessions
        active_sessions = await db.execute(
            select(func.count(Session.id)).where(
                Session.user_id == user.id,
                Session.revoked_at.is_(None),
                Session.expires_at > utcnow(),
            )
        )
        if active_sessions.scalar() > policy.max_concurrent_sessions:
            # Revoke oldest session
            oldest = await db.execute(
                select(Session).where(
                    Session.user_id == user.id,
                    Session.revoked_at.is_(None),
                    Session.expires_at > utcnow(),
                ).order_by(Session.created_at.asc())
            )
            oldest_session = oldest.scalars().first()
            if oldest_session:
                oldest_session.revoked_at = utcnow()

                await self._log_security_event(
                    db,
                    user=user,
                    event_type="session.revoked.concurrent",
                    event_category="access",
                    severity="info",
                    outcome="success",
                    details={"revoked_session_id": oldest_session.id},
                )

        return result

    async def check_reauth_required(
        self,
        db: AsyncSession,
        *,
        user: User,
        action: str,
    ) -> bool:
        """Check if re-authentication is required for a sensitive action."""
        policy = await self.get_security_policy(db, user.organization_id)
        if not policy or not policy.require_reauth_for_sensitive:
            return False

        sensitive_actions = policy.sensitive_actions_require_reauth or [
            "user.delete",
            "role.assign",
            "permission.grant",
            "security.policy.update",
            "connector.configure",
            "data.export",
            "organization.delete",
        ]

        return action in sensitive_actions

    # ------------------------------------------------------------------ Security Policies

    async def get_security_policy(
        self,
        db: AsyncSession,
        organization_id: str,
    ) -> Optional[OrganizationSecurityPolicy]:
        """Get organization security policy."""
        result = await db.execute(
            select(OrganizationSecurityPolicy).where(
                OrganizationSecurityPolicy.organization_id == organization_id
            )
        )
        return result.scalar_one_or_none()

    async def create_or_update_security_policy(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        updated_by: str,
        **policy_data: Any,
    ) -> OrganizationSecurityPolicy:
        """Create or update organization security policy."""
        policy = await self.get_security_policy(db, organization_id)
        if not policy:
            policy = OrganizationSecurityPolicy(organization_id=organization_id)
            db.add(policy)

        for key, value in policy_data.items():
            if hasattr(policy, key):
                setattr(policy, key, value)

        policy.updated_by = updated_by
        policy.updated_at = utcnow()
        await db.flush()

        await self._log_security_event(
            db,
            user_id=updated_by,
            organization_id=organization_id,
            event_type="security.policy.updated",
            event_category="policy",
            severity="info",
            outcome="success",
            details={"changes": list(policy_data.keys())},
        )

        return policy

    # ------------------------------------------------------------------ Security Events

    async def _log_security_event(
        self,
        db: AsyncSession,
        *,
        user: Optional[User] = None,
        user_id: Optional[str] = None,
        organization_id: str,
        event_type: str,
        event_category: str,
        severity: str,
        outcome: str,
        actor_id: Optional[str] = None,
        actor_email: Optional[str] = None,
        actor_type: str = "user",
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        device_fingerprint: Optional[str] = None,
        risk_score: int = 0,
        risk_factors: Optional[list[str]] = None,
        details: Optional[dict] = None,
        request_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> SecurityAuditEvent:
        """Log a security event."""
        event = SecurityAuditEvent(
            organization_id=organization_id,
            user_id=user_id or (user.id if user else None),
            event_type=event_type,
            event_category=event_category,
            severity=severity,
            actor_id=actor_id or (user.id if user else None),
            actor_email=actor_email or (user.email if user else None),
            actor_type=actor_type,
            target_type=target_type,
            target_id=target_id,
            ip_address=ip_address,
            user_agent=user_agent,
            device_fingerprint=device_fingerprint,
            outcome=outcome,
            risk_score=risk_score,
            risk_factors=risk_factors or [],
            details=details or {},
            request_id=request_id,
            correlation_id=correlation_id,
            occurred_at=utcnow(),
        )
        db.add(event)
        await db.flush()
        return event

    async def get_security_events(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user_id: Optional[str] = None,
        event_type: Optional[str] = None,
        severity: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SecurityAuditEvent]:
        """Query security audit events."""
        query = select(SecurityAuditEvent).where(SecurityAuditEvent.organization_id == organization_id)

        if user_id:
            query = query.where(SecurityAuditEvent.user_id == user_id)
        if event_type:
            query = query.where(SecurityAuditEvent.event_type == event_type)
        if severity:
            query = query.where(SecurityAuditEvent.severity == severity)
        if start_date:
            query = query.where(SecurityAuditEvent.occurred_at >= start_date)
        if end_date:
            query = query.where(SecurityAuditEvent.occurred_at <= end_date)

        query = query.order_by(SecurityAuditEvent.occurred_at.desc()).limit(limit).offset(offset)
        result = await db.execute(query)
        return list(result.scalars().all())

    # ------------------------------------------------------------------ MFA Management

    async def remove_mfa_method(
        self,
        db: AsyncSession,
        *,
        user: User,
        method_id: str,
    ) -> bool:
        """Remove an MFA method."""
        mfa_method = await db.get(MFAMethod, method_id)
        if not mfa_method or mfa_method.user_id != user.id:
            return False

        was_primary = mfa_method.is_primary
        await db.delete(mfa_method)

        # Check if user has any verified MFA methods left
        remaining = await db.execute(
            select(func.count(MFAMethod.id)).where(
                MFAMethod.user_id == user.id,
                MFAMethod.is_verified == True,
            )
        )
        if remaining.scalar() == 0:
            user.mfa_enabled = False

        # If removed primary, promote another
        if was_primary:
            next_method = await db.execute(
                select(MFAMethod).where(
                    MFAMethod.user_id == user.id,
                    MFAMethod.is_verified == True,
                ).order_by(MFAMethod.created_at.asc())
            )
            next_mfa = next_method.scalars().first()
            if next_mfa:
                next_mfa.is_primary = True

        await self._log_security_event(
            db,
            user=user,
            event_type="mfa.method.removed",
            event_category="auth",
            severity="info",
            outcome="success",
            details={"method_id": method_id, "method_type": mfa_method.method_type},
        )

        return True

    async def get_user_mfa_methods(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> list[MFAMethod]:
        """Get all MFA methods for a user."""
        result = await db.execute(
            select(MFAMethod).where(MFAMethod.user_id == user_id).order_by(MFAMethod.created_at.desc())
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------ Device Management

    async def get_user_devices(
        self,
        db: AsyncSession,
        user_id: str,
        include_revoked: bool = False,
    ) -> list[TrustedDevice]:
        """Get all trusted devices for a user."""
        query = select(TrustedDevice).where(TrustedDevice.user_id == user_id)
        if not include_revoked:
            query = query.where(TrustedDevice.revoked_at.is_(None))
        query = query.order_by(TrustedDevice.last_seen_at.desc().nullslast())
        result = await db.execute(query)
        return list(result.scalars().all())

    async def is_device_trusted(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        device_fingerprint: str,
    ) -> bool:
        """Check if a device is trusted and not expired."""
        result = await db.execute(
            select(TrustedDevice).where(
                TrustedDevice.user_id == user_id,
                TrustedDevice.device_fingerprint == device_fingerprint,
                TrustedDevice.is_trusted == True,
                TrustedDevice.revoked_at.is_(None),
            )
        )
        device = result.scalar_one_or_none()
        if not device:
            return False
        if device.trust_expires_at and device.trust_expires_at < utcnow():
            return False
        return True

    # ------------------------------------------------------------------ Access Reviews

    async def create_access_review(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        name: str,
        scope_type: str,
        scope_config: dict,
        frequency: str = "quarterly",
        reviewer_id: Optional[str] = None,
    ) -> AccessReview:
        """Create a new access review."""
        from app.models.user import AccessReview

        due_at = utcnow() + timedelta(days=90)  # quarterly default

        review = AccessReview(
            organization_id=organization_id,
            name=name,
            scope_type=scope_type,
            scope_config=scope_config,
            frequency=frequency,
            reviewer_id=reviewer_id,
            due_at=due_at,
            status="pending",
        )
        db.add(review)
        await db.flush()
        return review

    async def start_access_review(
        self,
        db: AsyncSession,
        review_id: str,
        reviewer_id: str,
    ) -> Optional[AccessReview]:
        """Start an access review - populate items to review."""
        from app.models.user import AccessReview, AccessReviewItem
        from app.models.role import UserRoleModel, RolePermission, Permission

        review = await db.get(AccessReview, review_id)
        if not review or review.organization_id != reviewer_id:
            return None

        review.status = "in_progress"
        review.started_at = utcnow()
        await db.flush()

        # Determine scope
        query = select(UserRoleModel).where(UserRoleModel.organization_id == review.organization_id)
        if review.scope_type == "privileged_users":
            # Filter for users with privileged permissions
            pass
        elif review.scope_type == "specific_role" and review.scope_config.get("role_id"):
            query = query.where(UserRoleModel.role_id == review.scope_config["role_id"])
        elif review.scope_type == "specific_permission" and review.scope_config.get("permission_code"):
            query = query.join(RolePermission).join(Permission).where(
                Permission.code == review.scope_config["permission_code"]
            )

        user_roles = await db.execute(query)

        for ur in user_roles.scalars().all():
            # Assess risk
            risk_level = "low"
            risk_reasons = []

            # Check for privileged permissions
            perm_result = await db.execute(
                select(Permission.code)
                .join(RolePermission)
                .where(RolePermission.role_id == ur.role_id)
            )
            perms = set(perm_result.scalars().all())
            privileged_perms = perms & {"organization:delete", "users:delete", "security.policy.update", "data:export"}
            if privileged_perms:
                risk_level = "high"
                risk_reasons.append(f"Privileged permissions: {', '.join(privileged_perms)}")

            # Check for stale access
            if ur.updated_at:
                days_since_update = (utcnow() - ur.updated_at).days
                if days_since_update > 180:
                    risk_level = max(risk_level, "medium", key=lambda x: ["low", "medium", "high", "critical"].index(x))
                    risk_reasons.append(f"Role not updated in {days_since_update} days")

            item = AccessReviewItem(
                review_id=review.id,
                organization_id=review.organization_id,
                user_id=ur.user_id,
                role_id=ur.role_id,
                scope_id=ur.scope_id,
                risk_level=risk_level,
                risk_reasons=risk_reasons,
            )
            db.add(item)

        await db.flush()

        # Update counts
        total_items = await db.execute(
            select(func.count(AccessReviewItem.id)).where(AccessReviewItem.review_id == review.id)
        )
        review.total_reviewed = total_items.scalar() or 0

        return review

    async def decide_access_review_item(
        self,
        db: AsyncSession,
        *,
        item_id: str,
        decision: str,  # approve | revoke | modify | defer
        reason: str,
        decided_by: str,
    ) -> bool:
        """Record a decision on an access review item."""
        from app.models.role import UserRoleModel

        item = await db.get(AccessReviewItem, item_id)
        if not item:
            return False

        item.decision = decision
        item.decision_reason = reason
        item.decided_by = decided_by
        item.decided_at = utcnow()

        if decision == "revoke":
            item.remediation_action = "revoke_role"
            item.remediation_details = {"role_id": item.role_id, "scope_id": item.scope_id}
            # Actually revoke the role
            if item.role_id:
                user_role = await db.execute(
                    select(UserRoleModel).where(
                        UserRoleModel.user_id == item.user_id,
                        UserRoleModel.role_id == item.role_id,
                        UserRoleModel.organization_id == item.organization_id,
                    )
                )
                ur = user_role.scalars().first()
                if ur:
                    await db.delete(ur)

        elif decision == "modify":
            item.remediation_action = "modify_scope"
            item.remediation_details = {"scope_id": item.scope_id}

        await db.flush()

        # Update review counts
        review = await db.get(AccessReview, item.review_id)
        if review:
            if decision == "approve":
                review.approved += 1
            elif decision == "revoke":
                review.revoked += 1
            elif decision == "defer":
                review.pending_action += 1

        await self._log_security_event(
            db,
            user_id=decided_by,
            organization_id=item.organization_id,
            event_type="access_review.item.decided",
            event_category="compliance",
            severity="info",
            outcome="success",
            details={"item_id": item_id, "decision": decision, "user_id": item.user_id},
        )

        return True

    async def complete_access_review(
        self,
        db: AsyncSession,
        review_id: str,
        completed_by: str,
    ) -> Optional[AccessReview]:
        """Complete an access review."""
        from app.models.user import AccessReview

        review = await db.get(AccessReview, review_id)
        if not review or review.status != "in_progress":
            return None

        review.status = "completed"
        review.completed_at = utcnow()
        review.next_review_at = utcnow() + timedelta(days=90)  # Next quarter

        await self._log_security_event(
            db,
            user_id=completed_by,
            organization_id=review.organization_id,
            event_type="access_review.completed",
            event_category="compliance",
            severity="info",
            outcome="success",
            details={
                "review_id": review_id,
                "total": review.total_reviewed,
                "approved": review.approved,
                "revoked": review.revoked,
                "pending": review.pending_action,
            },
        )

        return review


mfa_service = MFAService()