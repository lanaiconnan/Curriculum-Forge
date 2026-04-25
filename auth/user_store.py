"""
User Store Module for JWT Authentication

Manages user accounts with in-memory storage and optional JSON file persistence.
"""

import json
import os
import time
import secrets
import threading
import hashlib
from typing import Dict, Optional, List, Any
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class UserRecord:
    """User account record"""
    user_id: str
    username: str
    password_hash: str  # bcrypt hash
    email: Optional[str]
    full_name: Optional[str]
    roles: List[str]
    created_at: float
    updated_at: float
    last_login_at: Optional[float]
    enabled: bool
    failed_login_attempts: int
    locked_until: Optional[float]  # Account lock timestamp
    metadata: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserRecord':
        """Create from dictionary"""
        return cls(**data)


class UserStore:
    """
    Thread-safe user account storage
    
    Features:
    - In-memory storage with file persistence
    - Password hashing with bcrypt
    - Account lockout after failed attempts
    - User CRUD operations
    """
    
    # Password hashing
    try:
        from passlib.hash import bcrypt as passlib_bcrypt
        _HAS_PASSLIB = True
    except ImportError:
        _HAS_PASSLIB = False
        passlib_bcrypt = None
    
    def __init__(
        self,
        storage_path: Optional[str] = None,
        auto_save: bool = True,
        max_failed_attempts: int = 5,
        lockout_duration: int = 900  # 15 minutes
    ):
        """
        Initialize user store
        
        Args:
            storage_path: Path to JSON file for persistence (optional)
            auto_save: Auto-save to file on changes
            max_failed_attempts: Max failed login attempts before lockout
            lockout_duration: Lockout duration in seconds
        """
        self.storage_path = storage_path
        self.auto_save = auto_save
        self.max_failed_attempts = max_failed_attempts
        self.lockout_duration = lockout_duration
        
        self._users: Dict[str, UserRecord] = {}  # user_id -> UserRecord
        self._username_index: Dict[str, str] = {}  # username -> user_id
        self._lock = threading.RLock()
        
        # Load from file if exists
        if storage_path and os.path.exists(storage_path):
            self._load()
    
    def _hash_password(self, password: str) -> str:
        """Hash password using bcrypt"""
        if self._HAS_PASSLIB:
            return self.passlib_bcrypt.hash(password)
        else:
            # Fallback to SHA-256 (not as secure, use passlib in production)
            import warnings
            warnings.warn(
                "passlib not installed, using SHA-256 fallback. "
                "Install passlib[bcrypt] for secure password hashing."
            )
            return hashlib.sha256(password.encode()).hexdigest()
    
    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Verify password against hash"""
        if self._HAS_PASSLIB:
            try:
                return self.passlib_bcrypt.verify(password, password_hash)
            except Exception:
                return False
        else:
            # Fallback SHA-256 comparison
            return hashlib.sha256(password.encode()).hexdigest() == password_hash
    
    def _load(self) -> int:
        """Load users from JSON file"""
        if not self.storage_path:
            return 0
        
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
            
            with self._lock:
                self._users.clear()
                self._username_index.clear()
                
                for user_data in data.get("users", []):
                    user = UserRecord.from_dict(user_data)
                    self._users[user.user_id] = user
                    self._username_index[user.username] = user.user_id
            
            return len(self._users)
            
        except Exception as e:
            print(f"Error loading users from {self.storage_path}: {e}")
            return 0
    
    def _save(self) -> bool:
        """Save users to JSON file"""
        if not self.storage_path:
            return False
        
        try:
            # Create directory if needed
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            
            with self._lock:
                data = {
                    "version": 1,
                    "users": [user.to_dict() for user in self._users.values()]
                }
            
            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            return True
            
        except Exception as e:
            print(f"Error saving users to {self.storage_path}: {e}")
            return False
    
    def create_user(
        self,
        username: str,
        password: str,
        email: Optional[str] = None,
        full_name: Optional[str] = None,
        roles: Optional[List[str]] = None
    ) -> UserRecord:
        """
        Create new user
        
        Args:
            username: Unique username
            password: Plain text password
            email: User email (optional)
            full_name: Full name (optional)
            roles: User roles (default: ["user"])
            
        Returns:
            Created UserRecord
            
        Raises:
            ValueError: If username already exists
        """
        with self._lock:
            # Check if username exists
            if username in self._username_index:
                raise ValueError(f"Username '{username}' already exists")
            
            # Generate user ID
            user_id = f"user_{secrets.token_urlsafe(8)}"
            
            now = time.time()
            
            user = UserRecord(
                user_id=user_id,
                username=username,
                password_hash=self._hash_password(password),
                email=email,
                full_name=full_name,
                roles=roles or ["user"],
                created_at=now,
                updated_at=now,
                last_login_at=None,
                enabled=True,
                failed_login_attempts=0,
                locked_until=None,
                metadata={}
            )
            
            self._users[user_id] = user
            self._username_index[username] = user_id
            
            if self.auto_save:
                self._save()
            
            return user
    
    def get_user(self, user_id: str) -> Optional[UserRecord]:
        """Get user by ID"""
        with self._lock:
            return self._users.get(user_id)
    
    def get_user_by_username(self, username: str) -> Optional[UserRecord]:
        """Get user by username"""
        with self._lock:
            user_id = self._username_index.get(username)
            if user_id:
                return self._users.get(user_id)
            return None
    
    def update_user(
        self,
        user_id: str,
        email: Optional[str] = None,
        full_name: Optional[str] = None,
        roles: Optional[List[str]] = None,
        enabled: Optional[bool] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[UserRecord]:
        """
        Update user fields
        
        Returns:
            Updated UserRecord or None if not found
        """
        with self._lock:
            user = self._users.get(user_id)
            if not user:
                return None
            
            if email is not None:
                user.email = email
            if full_name is not None:
                user.full_name = full_name
            if roles is not None:
                user.roles = roles
            if enabled is not None:
                user.enabled = enabled
            if metadata is not None:
                user.metadata = metadata
            
            user.updated_at = time.time()
            
            if self.auto_save:
                self._save()
            
            return user
    
    def change_password(self, user_id: str, new_password: str) -> bool:
        """Change user password"""
        with self._lock:
            user = self._users.get(user_id)
            if not user:
                return False
            
            user.password_hash = self._hash_password(new_password)
            user.updated_at = time.time()
            
            # Reset failed attempts
            user.failed_login_attempts = 0
            user.locked_until = None
            
            if self.auto_save:
                self._save()
            
            return True
    
    def delete_user(self, user_id: str) -> bool:
        """Delete user"""
        with self._lock:
            user = self._users.get(user_id)
            if not user:
                return False
            
            del self._users[user_id]
            del self._username_index[user.username]
            
            if self.auto_save:
                self._save()
            
            return True
    
    def authenticate(self, username: str, password: str) -> Optional[UserRecord]:
        """
        Authenticate user with username/password
        
        Handles:
        - Password verification
        - Failed attempt tracking
        - Account lockout
        
        Returns:
            UserRecord if authenticated, None otherwise
        """
        with self._lock:
            user = self.get_user_by_username(username)
            
            if not user:
                return None
            
            # Check if account is locked
            if user.locked_until and time.time() < user.locked_until:
                return None
            
            # Check if account is enabled
            if not user.enabled:
                return None
            
            # Verify password
            if self._verify_password(password, user.password_hash):
                # Reset failed attempts on success
                user.failed_login_attempts = 0
                user.locked_until = None
                user.last_login_at = time.time()
                
                if self.auto_save:
                    self._save()
                
                return user
            else:
                # Track failed attempt
                user.failed_login_attempts += 1
                
                # Lock account if too many failures
                if user.failed_login_attempts >= self.max_failed_attempts:
                    user.locked_until = time.time() + self.lockout_duration
                
                if self.auto_save:
                    self._save()
                
                return None
    
    def unlock_user(self, user_id: str) -> bool:
        """Unlock user account"""
        with self._lock:
            user = self._users.get(user_id)
            if not user:
                return False
            
            user.failed_login_attempts = 0
            user.locked_until = None
            
            if self.auto_save:
                self._save()
            
            return True
    
    def list_users(
        self,
        enabled_only: bool = False,
        role: Optional[str] = None,
        limit: int = 100
    ) -> List[UserRecord]:
        """
        List users with optional filters
        
        Args:
            enabled_only: Only return enabled users
            role: Filter by role
            limit: Max results
            
        Returns:
            List of UserRecords
        """
        with self._lock:
            users = list(self._users.values())
            
            if enabled_only:
                users = [u for u in users if u.enabled]
            
            if role:
                users = [u for u in users if role in u.roles]
            
            return users[:limit]
    
    def count_users(self) -> int:
        """Count total users"""
        with self._lock:
            return len(self._users)
    
    def user_exists(self, username: str) -> bool:
        """Check if username exists"""
        with self._lock:
            return username in self._username_index


def create_default_admin_user(store: UserStore) -> Optional[UserRecord]:
    """
    Create default admin user if no users exist
    
    Username: admin
    Password: admin123 (CHANGE IN PRODUCTION)
    Roles: admin
    """
    if store.count_users() > 0:
        return None
    
    return store.create_user(
        username="admin",
        password="admin123",
        email="admin@localhost",
        full_name="Default Admin",
        roles=["admin", "user"]
    )
