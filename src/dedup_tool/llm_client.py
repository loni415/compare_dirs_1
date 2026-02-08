"""LLM client for semantic file comparison."""

import json
from abc import ABC, abstractmethod
from typing import Optional

import httpx
from loguru import logger

from .models import FileInfo


class LLMClientError(Exception):
    """Raised when LLM client fails."""
    pass


class LLMClient(ABC):
    """Abstract base class for LLM clients."""
    
    def __init__(self, base_url: str, model: Optional[str] = None):
        self.base_url = base_url
        self.model = model
        self.client = httpx.Client(timeout=60.0)
    
    @abstractmethod
    def compare_documents(
        self,
        file_a: FileInfo,
        file_b: FileInfo,
        text_a: str,
        text_b: str
    ) -> tuple[float, str]:
        """Compare two documents semantically.
        
        Returns:
            Tuple of (confidence_score, reasoning)
        """
        pass
    
    def close(self) -> None:
        """Close HTTP client."""
        self.client.close()


class LMStudioClient(LLMClient):
    """Client for LM Studio local API."""
    
    def __init__(self, base_url: str = "http://localhost:1234", model: Optional[str] = None):
        super().__init__(base_url, model)
        self.chat_url = f"{base_url}/v1/chat/completions"
    
    def compare_documents(
        self,
        file_a: FileInfo,
        file_b: FileInfo,
        text_a: str,
        text_b: str
    ) -> tuple[float, str]:
        """Compare documents using LM Studio."""
        prompt = self._build_prompt(file_a, file_b, text_a, text_b)
        
        payload = {
            "messages": [
                {
                    "role": "system",
                    "content": "You are a document comparison assistant. Analyze if two documents contain the same content and respond with valid JSON only."
                },
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 500,
        }
        
        if self.model:
            payload["model"] = self.model
        
        try:
            response = self.client.post(self.chat_url, json=payload)
            response.raise_for_status()
            data = response.json()
            
            content = data["choices"][0]["message"]["content"]
            return self._parse_response(content)
            
        except Exception as e:
            logger.error(f"LM Studio API error: {e}")
            raise LLMClientError(f"Failed to compare documents: {e}")
    
    def _build_prompt(
        self,
        file_a: FileInfo,
        file_b: FileInfo,
        text_a: str,
        text_b: str
    ) -> str:
        return f"""Compare these two documents and determine if they contain the same content:

FILE A: {file_a.path.name} (format: {file_a.format.value})
FILE B: {file_b.path.name} (format: {file_b.format.value})

CONTENT OF FILE A:
{text_a[:2000]}

CONTENT OF FILE B:
{text_b[:2000]}

Are these the same document? Consider:
1. Same topic/subject matter
2. Same structure and sections
3. Same key information (even if phrased differently)
4. One might be an export/conversion of the other

Respond with JSON only in this format:
{{"same_document": true/false, "confidence": 0.0-1.0, "reasoning": "brief explanation"}}
"""
    
    def _parse_response(self, content: str) -> tuple[float, str]:
        """Parse JSON response from LLM."""
        try:
            # Extract JSON if wrapped in markdown
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            data = json.loads(content.strip())
            confidence = float(data.get("confidence", 0.5))
            if data.get("same_document", False):
                confidence = max(confidence, 0.7)  # Boost if LLM says same
            reasoning = data.get("reasoning", "No reasoning provided")
            return confidence, reasoning
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM response: {content}")
            return 0.5, f"Parse error: {str(e)}"


class OllamaClient(LLMClient):
    """Client for Ollama local API."""
    
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama2"
    ):
        super().__init__(base_url, model)
        self.generate_url = f"{base_url}/api/generate"
    
    def compare_documents(
        self,
        file_a: FileInfo,
        file_b: FileInfo,
        text_a: str,
        text_b: str
    ) -> tuple[float, str]:
        """Compare documents using Ollama."""
        prompt = self._build_prompt(file_a, file_b, text_a, text_b)
        
        payload = {
            "model": self.model or "llama2",
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.1,
                "num_predict": 500,
            }
        }
        
        try:
            response = self.client.post(self.generate_url, json=payload)
            response.raise_for_status()
            data = response.json()
            
            content = data.get("response", "")
            return self._parse_response(content)
            
        except Exception as e:
            logger.error(f"Ollama API error: {e}")
            raise LLMClientError(f"Failed to compare documents: {e}")
    
    def _build_prompt(
        self,
        file_a: FileInfo,
        file_b: FileInfo,
        text_a: str,
        text_b: str
    ) -> str:
        return f"""Compare these two documents and determine if they contain the same content:

FILE A: {file_a.path.name} (format: {file_a.format.value})
FILE B: {file_b.path.name} (format: {file_b.format.value})

CONTENT OF FILE A:
{text_a[:2000]}

CONTENT OF FILE B:
{text_b[:2000]}

Are these the same document? Consider:
1. Same topic/subject matter
2. Same structure and sections
3. Same key information (even if phrased differently)
4. One might be an export/conversion of the other

Respond with JSON only:
{{"same_document": true/false, "confidence": 0.0-1.0, "reasoning": "brief explanation"}}
"""
    
    def _parse_response(self, content: str) -> tuple[float, str]:
        """Parse JSON response from LLM."""
        try:
            data = json.loads(content.strip())
            confidence = float(data.get("confidence", 0.5))
            if data.get("same_document", False):
                confidence = max(confidence, 0.7)
            reasoning = data.get("reasoning", "No reasoning provided")
            return confidence, reasoning
            
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse Ollama response: {content}")
            return 0.5, "Parse error"


class VLLMClient(LLMClient):
    """Client for vLLM OpenAI-compatible API."""
    
    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        model: Optional[str] = None
    ):
        super().__init__(base_url, model)
        self.chat_url = f"{base_url}/v1/chat/completions"
    
    def compare_documents(
        self,
        file_a: FileInfo,
        file_b: FileInfo,
        text_a: str,
        text_b: str
    ) -> tuple[float, str]:
        """Compare documents using vLLM."""
        prompt = self._build_prompt(file_a, file_b, text_a, text_b)
        
        payload = {
            "model": self.model or "default",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a document comparison assistant. Analyze if two documents contain the same content."
                },
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 500,
        }
        
        try:
            response = self.client.post(self.chat_url, json=payload)
            response.raise_for_status()
            data = response.json()
            
            content = data["choices"][0]["message"]["content"]
            return self._parse_response(content)
            
        except Exception as e:
            logger.error(f"vLLM API error: {e}")
            raise LLMClientError(f"Failed to compare documents: {e}")
    
    def _build_prompt(
        self,
        file_a: FileInfo,
        file_b: FileInfo,
        text_a: str,
        text_b: str
    ) -> str:
        return f"""Compare these two documents and determine if they contain the same content:

FILE A: {file_a.path.name} (format: {file_a.format.value})
FILE B: {file_b.path.name} (format: {file_b.format.value})

CONTENT OF FILE A:
{text_a[:2000]}

CONTENT OF FILE B:
{text_b[:2000]}

Are these the same document? Consider same topic, structure, and key information.

Respond with JSON only:
{{"same_document": true/false, "confidence": 0.0-1.0, "reasoning": "brief explanation"}}
"""
    
    def _parse_response(self, content: str) -> tuple[float, str]:
        """Parse JSON response from LLM."""
        try:
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            data = json.loads(content.strip())
            confidence = float(data.get("confidence", 0.5))
            if data.get("same_document", False):
                confidence = max(confidence, 0.7)
            reasoning = data.get("reasoning", "No reasoning provided")
            return confidence, reasoning
            
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse vLLM response: {content}")
            return 0.5, "Parse error"


def create_llm_client(
    provider: str,
    base_url: Optional[str] = None,
    model: Optional[str] = None
) -> LLMClient:
    """Factory function to create appropriate LLM client.
    
    Args:
        provider: One of 'lmstudio', 'ollama', 'vllm'
        base_url: Optional custom base URL
        model: Optional model name
        
    Returns:
        Configured LLM client
    """
    provider = provider.lower()
    
    if provider == "lmstudio":
        return LMStudioClient(base_url or "http://localhost:1234", model)
    elif provider == "ollama":
        return OllamaClient(base_url or "http://localhost:11434", model or "llama2")
    elif provider == "vllm":
        return VLLMClient(base_url or "http://localhost:8000", model)
    else:
        raise ValueError(f"Unknown provider: {provider}")
