"""
JWT Authentication Module for Curriculum-Forge

Provides JWT token generation, validation, and refresh functionality
for user authentication and Web UI session management.

Dependencies:
    pip install pyjwt passlib[bcrypt]

Usage:
    from auth.jwt import JWTAuth, JWTConfig
    
    jwt_auth = JWTAuth(JWTConfig(secret_key="your-secret"))
    token = jwt_auth.create_token(user_id="user123", username="alice")
    payload = jwt_auth.verify_token(token)
"""

import jwt
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Any, List
from datetime import datetime, timedelta


@dataclass
class JWTConfig:
    """JWT configuration settings"""
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    issuer: str = "curriculum-forge"
    audience: str = "forge-users"


@dataclass
class TokenPair:
    """Access and refresh token pair"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 900  # 15 minutes in seconds


@dataclass
class UserPayload:
    """Decoded JWT user payload"""
    user_id: str
    username: str
    roles: List[str]
    email: Optional[str] = None
    iat: float = 0
    exp: float = 0
    
    def is_expired(self) -> bool:
        """Check if token is expired"""
        return time.time() > self.exp
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "roles": self.roles,
            "email": self.email,
            "iat": self.iat,
            "exp": self.exp
        }


class JWTAuth:
    """
    JWT Authentication handler
    
    Handles token creation, verification, and refresh
    """
    
    def __init__(self, config: JWTConfig):
        self.config = config
        self._blacklist: Dict[str, float] = {}  # token_id -> expiry
    
    def create_access_token(
        self,
        user_id: str,
        username: str,
        roles: List[str] = None,
        email: Optional[str] = None,
        additional_claims: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create access token
        
        Args:
            user_id: Unique user identifier
            username: Username
            roles: User roles (default: ["user"])
            email: User email (optional)
            additional_claims: Extra claims to include
            
        Returns:
            JWT access token string
        """
        if roles is None:
            roles = ["user"]
        
        now = time.time()
        exp = now + (self.config.access_token_expire_minutes * 60)
        
        payload = {
            "sub": user_id,
            "username": username,
            "roles": roles,
            "iat": now,
            "exp": exp,
            "iss": self.config.issuer,
            "aud": self.config.audience,
            "type": "access"
        }
        
        if email:
            payload["email"] = email
        
        if additional_claims:
            payload.update(additional_claims)
        
        return jwt.encode(
            payload,
            self.config.secret_key,
            algorithm=self.config.algorithm
        )
    
    def create_refresh_token(
        self,
        user_id: str,
        username: str
    ) -> str:
        """
        Create refresh token
        
        Args:
            user_id: Unique user identifier
            username: Username
            
        Returns:
            JWT refresh token string
        """
        now = time.time()
        exp = now + (self.config.refresh_token_expire_days * 86400)
        
        payload = {
            "sub": user_id,
            "username": username,
            "iat": now,
            "exp": exp,
            "iss": self.config.issuer,
            "aud": self.config.audience,
            "type": "refresh"
        }
        
        return jwt.encode(
            payload,
            self.config.secret_key,
            algorithm=self.config.algorithm
        )
    
    def create_token_pair(
        self,
        user_id: str,
        username: str,
        roles: List[str] = None,
        email: Optional[str] = None
    ) -> TokenPair:
        """
        Create access and refresh token pair
        
        Args:
            user_id: Unique user identifier
            username: Username
            roles: User roles
            email: User email
            
        Returns:
            TokenPair with both tokens
        """
        access_token = self.create_access_token(
            user_id=user_id,
            username=username,
            roles=roles,
            email=email
        )
        
        refresh_token = self.create_refresh_token(
            user_id=user_id,
            username=username
        )
        
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self.config.access_token_expire_minutes * 60
        )
    
    def verify_token(self, token: str, expected_type: str = "access") -> Optional[UserPayload]:
        """
        Verify and decode JWT token
        
        Args:
            token: JWT token string
            expected_type: Expected token type ("access" or "refresh")
            
        Returns:
            UserPayload if valid, None if invalid/expired
        """
        try:
            # Check blacklist
            if token in self._blacklist:
                if time.time() < self._blacklist[token]:
                    return None  # Blacklisted
                else:
                    del self._blacklist[token]  # Clean up expired entry
            
            payload = jwt.decode(
                token,
                self.config.secret_key,
                algorithms=[self.config.algorithm],
                issuer=self.config.issuer,
                audience=self.config.audience,
                options={"require": ["sub", "exp", "iat"]}
            )
            
            # Check token type
            if payload.get("type") != expected_type:
                return None
            
            return UserPayload(
                user_id=payload["sub"],
                username=payload["username"],
                roles=payload.get("roles", ["user"]),
                email=payload.get("email"),
                iat=payload["iat"],
                exp=payload["exp"]
            )
            
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None
        except Exception:
            return None
    
    def refresh_access_token(self, refresh_token: str) -> Optional[TokenPair]:
        """
        Create new token pair from refresh token
        
        Args:
            refresh_token: Valid refresh token
            
        Returns:
            New TokenPair if refresh token is valid, None otherwise
        """
        payload = self.verify_token(refresh_token, expected_type="refresh")
        
        if not payload:
            return None
        
        # Invalidate old refresh token (one-time use)
        self._blacklist[refresh_token] = payload.exp
        
        # Create new token pair
        return self.create_token_pair(
            user_id=payload.user_id,
            username=payload.username,
            roles=payload.roles,
            email=payload.email
        )
    
    def invalidate_token(self, token: str) -> bool:
        """
        Blacklist a token (logout)
        
        Args:
            token: JWT token to invalidate
            
        Returns:
            True if token was valid and blacklisted
        """
        payload = self.verify_token(token, expected_type="access")
        if not payload:
            payload = self.verify_token(token, expected_type="refresh")
        
        if payload:
            self._blacklist[token] = payload.exp
            return True
        
        return False
    
    def cleanup_blacklist(self) -> int:
        """
        Remove expired entries from blacklist
        
        Returns:
            Number of entries removed
        """
        now = time.time()
        expired = [k for k, v in self._blacklist.items() if v < now]
        
        for key in expired:
            del self._blacklist[key]
        
        return len(expired)
    
    def get_token_remaining_time(self, token: str) -> int:
        """
        Get remaining validity time in seconds
        
        Args:
            token: JWT token
            
        Returns:
            Remaining seconds, 0 if invalid/expired
        """
        payload = self.verify_token(token)
        if not payload:
            return 0
        
        remaining = payload.exp - time.time()
        return max(0, int(remaining))


# Token extraction utilities

def extract_bearer_token(authorization_header: str) -> Optional[str]:
    """
    Extract Bearer token from Authorization header
    
    Args:
        authorization_header: Value of Authorization header
        
    Returns:
        Token string or None if invalid format
    """
    if not authorization_header:
        return None
    
    parts = authorization_header.split()
    if len(parts) != 2:
        return None
    
    if parts[0].lower() != "bearer":
        return None
    
    return parts[1]


def create_jwt_auth_from_env() -> JWTAuth:
    """
    Create JWTAuth instance from environment variables
    
    Required:
        CF_JWT_SECRET_KEY: Secret key for signing tokens
        
    Optional:
        CF_JWT_ACCESS_EXPIRE_MINUTES: Access token lifetime (default: 15)
        CF_JWT_REFRESH_EXPIRE_DAYS: Refresh token lifetime (default: 7)
        CF_JWT_ISSUER: Token issuer (default: curriculum-forge)
        CF_JWT_AUDIENCE: Token audience (default: forge-users)
    
    Returns:
        Configured JWTAuth instance
    """
    import os
    
    secret_key = os.getenv("CF_JWT_SECRET_KEY", "dev-secret-key-change-in-production")
    
    config = JWTConfig(
        secret_key=secret_key,
        access_token_expire_minutes=int(os.getenv("CF_JWT_ACCESS_EXPIRE_MINUTES", "15")),
        refresh_token_expire_days=int(os.getenv("CF_JWT_REFRESH_EXPIRE_DAYS", "7")),
        issuer=os.getenv("CF_JWT_ISSUER", "curriculum-forge"),
        audience=os.getenv("CF_JWT_AUDIENCE", "forge-users")
    )
    
    return JWTAuth(config)
