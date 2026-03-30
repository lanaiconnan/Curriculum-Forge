"""本地 LLM 支持

支持 Ollama 和 LM Studio，提供离线模式。
基于 AgenticSeek 的本地化理念设计。
"""

import os
import sys
import json
import time
import socket
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum


class Provider(Enum):
    """LLM 提供商"""
    OLLAMA = "ollama"
    LM_STUDIO = "lm_studio"
    OPENAI = "openai"  # 兼容远程
    ANTHROPIC = "anthropic"  # 兼容远程


@dataclass
class LLMConfig:
    """LLM 配置"""
    provider: Provider = Provider.OLLAMA
    model: str = "llama3.2"
    base_url: str = "http://localhost"
    port: int = 11434
    api_key: Optional[str] = None
    timeout: int = 120
    max_retries: int = 3
    temperature: float = 0.7
    max_tokens: int = 4096
    
    @property
    def api_base(self) -> str:
        """API 基础 URL"""
        return f"{self.base_url}:{self.port}"
    
    @property
    def is_local(self) -> bool:
        """是否为本地模型"""
        return self.provider in [Provider.OLLAMA, Provider.LM_STUDIO]


@dataclass
class LLMResponse:
    """LLM 响应"""
    content: str
    model: str
    provider: Provider
    usage: Dict[str, int] = field(default_factory=dict)
    latency_ms: float = 0.0
    error: Optional[str] = None
    
    @property
    def success(self) -> bool:
        return self.error is None and bool(self.content)


@dataclass
class LLMMessage:
    """LLM 消息"""
    role: str  # system, user, assistant
    content: str


class BaseLLMProvider(ABC):
    """LLM 提供商基类"""
    
    def __init__(self, config: LLMConfig):
        self.config = config
    
    @abstractmethod
    def chat(self, messages: List[LLMMessage], **kwargs) -> LLMResponse:
        """发送聊天请求"""
        pass
    
    @abstractmethod
    def check_health(self) -> Tuple[bool, str]:
        """检查健康状态"""
        pass


class OllamaProvider(BaseLLMProvider):
    """Ollama 提供商"""
    
    API_CHAT = "/api/chat"
    API_GENERATE = "/api/generate"
    API_TAGS = "/api/tags"
    API_SHOW = "/api/show"
    
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self.base_url = config.api_base
    
    def chat(self, messages: List[LLMMessage], **kwargs) -> LLMResponse:
        """Ollama 聊天"""
        import urllib.request
        import urllib.error
        
        start_time = time.time()
        
        # 构建请求
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": m.role, "content": m.content}
                for m in messages
            ],
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", self.config.temperature),
                "num_predict": kwargs.get("max_tokens", self.config.max_tokens),
            }
        }
        
        url = f"{self.base_url}{self.API_CHAT}"
        
        for attempt in range(self.config.max_retries):
            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode('utf-8'),
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                
                with urllib.request.urlopen(req, timeout=self.config.timeout) as response:
                    result = json.loads(response.read().decode('utf-8'))
                    
                    latency = (time.time() - start_time) * 1000
                    
                    return LLMResponse(
                        content=result.get("message", {}).get("content", ""),
                        model=self.config.model,
                        provider=Provider.OLLAMA,
                        usage={
                            "prompt_tokens": result.get("prompt_eval_count", 0),
                            "completion_tokens": result.get("eval_count", 0),
                        },
                        latency_ms=latency,
                    )
                    
            except urllib.error.URLError as e:
                if attempt == self.config.max_retries - 1:
                    return LLMResponse(
                        content="",
                        model=self.config.model,
                        provider=Provider.OLLAMA,
                        error=f"Connection error: {e}",
                    )
                time.sleep(1)
            except Exception as e:
                return LLMResponse(
                    content="",
                    model=self.config.model,
                    provider=Provider.OLLAMA,
                    error=f"Error: {e}",
                )
        
        return LLMResponse(
            content="",
            model=self.config.model,
            provider=Provider.OLLAMA,
            error="Max retries exceeded",
        )
    
    def check_health(self) -> Tuple[bool, str]:
        """检查 Ollama 服务健康状态"""
        import urllib.request
        import urllib.error
        
        try:
            url = f"{self.base_url}{self.API_TAGS}"
            req = urllib.request.Request(url, method="GET")
            
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    models = json.loads(response.read().decode('utf-8'))
                    available = [m.get("name") for m in models.get("models", [])]
                    return True, f"Ollama running with {len(available)} models"
        
        except urllib.error.URLError:
            return False, "Ollama not running"
        except Exception as e:
            return False, f"Error: {e}"
        
        return False, "Unknown error"
    
    def list_models(self) -> List[str]:
        """列出可用模型"""
        import urllib.request
        
        try:
            url = f"{self.base_url}{self.API_TAGS}"
            req = urllib.request.Request(url, method="GET")
            
            with urllib.request.urlopen(req, timeout=5) as response:
                models = json.loads(response.read().decode('utf-8'))
                return [m.get("name") for m in models.get("models", [])]
        
        except Exception:
            return []


class LMStudioProvider(BaseLLMProvider):
    """LM Studio 提供商"""
    
    API_CHAT = "/v1/chat/completions"
    API_MODELS = "/v1/models"
    
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self.base_url = config.api_base
    
    def chat(self, messages: List[LLMMessage], **kwargs) -> LLMResponse:
        """LM Studio 聊天（OpenAI 兼容 API）"""
        import urllib.request
        import urllib.error
        
        start_time = time.time()
        
        # 构建请求（OpenAI 兼容格式）
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": m.role, "content": m.content}
                for m in messages
            ],
            "stream": False,
            "temperature": kwargs.get("temperature", self.config.temperature),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
        }
        
        url = f"{self.base_url}{self.API_CHAT}"
        
        # 添加 API Key（如果配置了）
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        
        for attempt in range(self.config.max_retries):
            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode('utf-8'),
                    headers=headers,
                    method="POST"
                )
                
                with urllib.request.urlopen(req, timeout=self.config.timeout) as response:
                    result = json.loads(response.read().decode('utf-8'))
                    
                    latency = (time.time() - start_time) * 1000
                    
                    choices = result.get("choices", [])
                    content = choices[0].get("message", {}).get("content", "") if choices else ""
                    
                    return LLMResponse(
                        content=content,
                        model=result.get("model", self.config.model),
                        provider=Provider.LM_STUDIO,
                        usage=result.get("usage", {}),
                        latency_ms=latency,
                    )
                    
            except urllib.error.URLError as e:
                if attempt == self.config.max_retries - 1:
                    return LLMResponse(
                        content="",
                        model=self.config.model,
                        provider=Provider.LM_STUDIO,
                        error=f"Connection error: {e}",
                    )
                time.sleep(1)
            except Exception as e:
                return LLMResponse(
                    content="",
                    model=self.config.model,
                    provider=Provider.LM_STUDIO,
                    error=f"Error: {e}",
                )
        
        return LLMResponse(
            content="",
            model=self.config.model,
            provider=Provider.LM_STUDIO,
            error="Max retries exceeded",
        )
    
    def check_health(self) -> Tuple[bool, str]:
        """检查 LM Studio 服务健康状态"""
        import urllib.request
        
        try:
            url = f"{self.base_url}{self.API_MODELS}"
            req = urllib.request.Request(url, method="GET")
            
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    models = json.loads(response.read().decode('utf-8'))
                    available = [m.get("id") for m in models.get("data", [])]
                    return True, f"LM Studio running with {len(available)} models"
        
        except urllib.error.URLError:
            return False, "LM Studio not running"
        except Exception as e:
            return False, f"Error: {e}"
        
        return False, "Unknown error"
    
    def list_models(self) -> List[str]:
        """列出可用模型"""
        import urllib.request
        
        try:
            url = f"{self.base_url}{self.API_MODELS}"
            req = urllib.request.Request(url, method="GET")
            
            with urllib.request.urlopen(req, timeout=5) as response:
                models = json.loads(response.read().decode('utf-8'))
                return [m.get("id") for m in models.get("data", [])]
        
        except Exception:
            return []


class LocalLLMManager:
    """
    本地 LLM 管理器
    
    功能：
    1. 自动检测可用的本地模型
    2. 提供统一的调用接口
    3. 支持 Ollama 和 LM Studio
    4. 离线模式支持
    """
    
    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig()
        self.provider: Optional[BaseLLMProvider] = None
        self.offline_mode = False
        self._init_provider()
    
    def _init_provider(self):
        """初始化提供商"""
        if self.config.provider == Provider.OLLAMA:
            self.provider = OllamaProvider(self.config)
        elif self.config.provider == Provider.LM_STUDIO:
            self.provider = LMStudioProvider(self.config)
        else:
            raise ValueError(f"Unsupported provider: {self.config.provider}")
    
    def chat(self, messages: List[LLMMessage], **kwargs) -> LLMResponse:
        """发送聊天请求"""
        if self.offline_mode:
            return LLMResponse(
                content="",
                model=self.config.model,
                provider=self.config.provider,
                error="Offline mode: LLM not available",
            )
        
        if not self.provider:
            return LLMResponse(
                content="",
                model=self.config.model,
                provider=self.config.provider,
                error="No provider initialized",
            )
        
        return self.provider.chat(messages, **kwargs)
    
    def check_health(self) -> Tuple[bool, str]:
        """检查健康状态"""
        if self.offline_mode:
            return True, "Offline mode"
        
        if not self.provider:
            return False, "No provider"
        
        return self.provider.check_health()
    
    def list_models(self) -> List[str]:
        """列出可用模型"""
        if self.offline_mode:
            return []
        
        if not self.provider:
            return []
        
        return self.provider.list_models()
    
    def enable_offline_mode(self):
        """启用离线模式"""
        self.offline_mode = True
        print("🔒 Offline mode enabled")
    
    def disable_offline_mode(self):
        """禁用离线模式"""
        self.offline_mode = False
        print("🌐 Online mode enabled")
    
    def auto_detect(self) -> Tuple[bool, str]:
        """
        自动检测可用的本地模型
        
        Returns:
            Tuple[bool, str]: (是否成功, 状态信息)
        """
        # 优先检查 Ollama
        ollama_config = LLMConfig(provider=Provider.OLLAMA, port=11434)
        ollama = OllamaProvider(ollama_config)
        healthy, msg = ollama.check_health()
        
        if healthy:
            self.config = ollama_config
            self.provider = ollama
            models = ollama.list_models()
            return True, f"Ollama detected: {len(models)} models available"
        
        # 检查 LM Studio
        lm_config = LLMConfig(provider=Provider.LM_STUDIO, port=1234)
        lm = LMStudioProvider(lm_config)
        healthy, msg = lm.check_health()
        
        if healthy:
            self.config = lm_config
            self.provider = lm
            models = lm.list_models()
            return True, f"LM Studio detected: {len(models)} models available"
        
        return False, "No local LLM detected. Run 'ollama serve' or start LM Studio."
    
    def get_status(self) -> Dict[str, Any]:
        """获取状态"""
        healthy, msg = self.check_health()
        models = self.list_models() if not self.offline_mode else []
        
        return {
            "provider": self.config.provider.value,
            "model": self.config.model,
            "is_local": self.config.is_local,
            "offline_mode": self.offline_mode,
            "healthy": healthy,
            "status": msg,
            "available_models": models,
        }
    
    def print_status(self):
        """打印状态"""
        status = self.get_status()
        
        print(f"\n🔒 Local LLM Status")
        print(f"   Provider: {status['provider']}")
        print(f"   Model: {status['model']}")
        print(f"   Local: {'Yes' if status['is_local'] else 'No'}")
        print(f"   Offline mode: {'Yes' if status['offline_mode'] else 'No'}")
        print(f"   Status: {status['status']}")
        
        if status['available_models']:
            print(f"\n   Available models ({len(status['available_models'])}):")
            for model in status['available_models'][:5]:
                print(f"      - {model}")
            if len(status['available_models']) > 5:
                print(f"      ... and {len(status['available_models']) - 5} more")


class OfflineSimulator:
    """
    离线模拟器
    
    当没有网络时，提供模拟响应以保持系统运行。
    """
    
    # 模拟的奖励分数
    SIMULATED_REWARDS = [0.65, 0.72, 0.68, 0.75, 0.70]
    _counter = 0
    
    @classmethod
    def get_simulated_reward(cls) -> float:
        """获取模拟奖励"""
        reward = cls.SIMULATED_REWARDS[cls._counter % len(cls.SIMULATED_REWARDS)]
        cls._counter += 1
        return reward
    
    @classmethod
    def reset_counter(cls):
        """重置计数器"""
        cls._counter = 0
    
    @classmethod
    def simulate_llm_response(cls, prompt: str) -> str:
        """模拟 LLM 响应"""
        # 基于提示词生成简单响应
        if "environment" in prompt.lower():
            return '{"name": "test_env", "difficulty": 0.5, "tasks": []}'
        elif "experiment" in prompt.lower():
            return '{"description": "test_exp", "implementation": "test_impl"}'
        elif "reward" in prompt.lower():
            reward = cls.get_simulated_reward()
            return f'{{"reward": {reward}, "confidence": 0.8}}'
        else:
            return '{"status": "simulated"}'


# 便捷函数
def create_local_llm(config: Optional[Dict[str, Any]] = None) -> LocalLLMManager:
    """创建本地 LLM 管理器"""
    if config:
        llm_config = LLMConfig(
            provider=Provider(config.get("provider", "ollama")),
            model=config.get("model", "llama3.2"),
            base_url=config.get("base_url", "http://localhost"),
            port=config.get("port", 11434),
            api_key=config.get("api_key"),
            timeout=config.get("timeout", 120),
        )
    else:
        llm_config = None
    
    return LocalLLMManager(llm_config)


def auto_detect_local_llm() -> Tuple[LocalLLMManager, bool, str]:
    """自动检测本地 LLM"""
    manager = LocalLLMManager()
    success, msg = manager.auto_detect()
    return manager, success, msg
