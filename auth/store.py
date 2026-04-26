"""
API Key 存储

支持内存存储和文件持久化，生产环境应替换为数据库。
"""

import json
import secrets
import time
from dataclasses import dataclass, field, asdict
from auth.sanitizer import hash_api_key as _hash_api_key
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from threading import Lock
from datetime import datetime


@dataclass
class APIKeyRecord:
    """API Key 记录"""
    key_id: str                    # Key 唯一标识
    api_key: str                   # 实际的 API Key（哈希后存储）
    client_id: str                 # 客户端标识
    name: str                      # Key 名称
    scopes: List[str] = field(default_factory=lambda: ["read"])  # 权限范围
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None  # 过期时间（None 表示永不过期）
    last_used_at: Optional[float] = None
    enabled: bool = True
    rate_limit: int = 1000          # 每小时请求限制
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "APIKeyRecord":
        return cls(**data)

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    def is_valid(self) -> bool:
        return self.enabled and not self.is_expired()


class APIKeyStore:
    """
    API Key 存储

    线程安全的内存存储，支持可选的文件持久化。
    """

    def __init__(self, persist_file: Optional[str] = None):
        """
        初始化存储

        Args:
            persist_file: 持久化文件路径（None 表示仅内存存储）
        """
        self._keys: Dict[str, APIKeyRecord] = {}  # key_id -> record
        self._key_index: Dict[str, str] = {}      # api_key -> key_id
        self._lock = Lock()
        self._persist_file = persist_file

        if persist_file:
            self._load_from_file()

    def _load_from_file(self):
        """从文件加载"""
        if not self._persist_file:
            return

        path = Path(self._persist_file)
        if not path.exists():
            return

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            with self._lock:
                for item in data.get("keys", []):
                    record = APIKeyRecord.from_dict(item)
                    self._keys[record.key_id] = record
                    self._key_index[record.api_key] = record.key_id
        except Exception as e:
            print(f"[APIKeyStore] 加载失败: {e}")

    def _save_to_file(self):
        """保存到文件"""
        if not self._persist_file:
            return

        path = Path(self._persist_file)
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with self._lock:
                data = {
                    "keys": [r.to_dict() for r in self._keys.values()],
                    "updated_at": datetime.now().isoformat()
                }

            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[APIKeyStore] 保存失败: {e}")

    def generate_key(self) -> str:
        """生成新的 API Key"""
        # 使用 secrets 生成安全的随机 key
        # 格式: cf_live_<32位随机字符>
        random_part = secrets.token_urlsafe(24)
        return f"cf_live_{random_part}"

    def create_key(
        self,
        client_id: str,
        name: str,
        scopes: Optional[List[str]] = None,
        expires_at: Optional[float] = None,
        rate_limit: int = 1000,
        metadata: Optional[Dict] = None
    ) -> APIKeyRecord:
        """
        创建新的 API Key

        Args:
            client_id: 客户端标识
            name: Key 名称
            scopes: 权限范围
            expires_at: 过期时间戳
            rate_limit: 每小时请求限制
            metadata: 附加元数据

        Returns:
            APIKeyRecord
        """
        api_key = self.generate_key()
        key_id = f"key_{secrets.token_hex(8)}"

        api_key_hash = _hash_api_key(api_key)

        record = APIKeyRecord(
            key_id=key_id,
            api_key=api_key_hash,
            client_id=client_id,
            name=name,
            scopes=scopes or ["read"],
            expires_at=expires_at,
            rate_limit=rate_limit,
            metadata=metadata or {}
        )

        with self._lock:
            self._keys[key_id] = record
            self._key_index[api_key_hash] = key_id

        self._save_to_file()
        return record

    def get_by_key(self, api_key: str) -> Optional[APIKeyRecord]:
        """通过 API Key (哈希值) 获取记录"""
        with self._lock:
            key_id = self._key_index.get(api_key)
            if not key_id:
                return None
            return self._keys.get(key_id)

    def get_by_id(self, key_id: str) -> Optional[APIKeyRecord]:
        """通过 Key ID 获取记录"""
        with self._lock:
            return self._keys.get(key_id)

    def list_keys(
        self,
        client_id: Optional[str] = None,
        enabled_only: bool = True
    ) -> List[APIKeyRecord]:
        """
        列出所有 Key

        Args:
            client_id: 按客户端过滤（None 表示不过滤）
            enabled_only: 只返回有效的 Key

        Returns:
            Key 记录列表
        """
        with self._lock:
            records = list(self._keys.values())

        if client_id:
            records = [r for r in records if r.client_id == client_id]

        if enabled_only:
            records = [r for r in records if r.is_valid()]

        return records

    def update_key(
        self,
        key_id: str,
        **updates
    ) -> Optional[APIKeyRecord]:
        """
        更新 Key 属性

        可更新字段: name, scopes, enabled, rate_limit, expires_at, metadata
        """
        allowed_fields = {"name", "scopes", "enabled", "rate_limit", "expires_at", "metadata"}

        with self._lock:
            record = self._keys.get(key_id)
            if not record:
                return None

            for field, value in updates.items():
                if field in allowed_fields:
                    setattr(record, field, value)

        self._save_to_file()
        return record

    def delete_key(self, key_id: str) -> bool:
        """删除 Key"""
        with self._lock:
            record = self._keys.pop(key_id, None)
            if not record:
                return False

            self._key_index.pop(record.api_key, None)

        self._save_to_file()
        return True

    def record_usage(self, key_id: str):
        """记录使用时间"""
        with self._lock:
            record = self._keys.get(key_id)
            if record:
                record.last_used_at = time.time()

        # 不频繁保存，由调用方决定是否持久化

    def verify_key(self, api_key: str) -> Tuple[bool, Optional[APIKeyRecord]]:
        """
        验证 API Key

        Returns:
            (is_valid, record) 元组
        """
        api_key_hash = _hash_api_key(api_key)
        record = self.get_by_key(api_key_hash)

        if not record:
            return False, None

        if not record.is_valid():
            return False, record

        self.record_usage(record.key_id)
        return True, record

    def count_keys(self, client_id: Optional[str] = None) -> int:
        """统计 Key 数量"""
        with self._lock:
            if client_id:
                return sum(1 for r in self._keys.values() if r.client_id == client_id)
            return len(self._keys)
