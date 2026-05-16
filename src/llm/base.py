"""
Abstract LLM interface — all connectors implement this.
"""

from abc import ABC, abstractmethod
from typing import Optional


class LLMConnector(ABC):
    """Base class for LLM connectors."""
    
    name: str = "base"
    
    @abstractmethod
    async def call(
        self, 
        prompt: str, 
        history: list[dict], 
        system_prompt: Optional[str] = None,
        allowed_tool_names: Optional[list[str]] = None,
    ) -> str:
        """
        Call the LLM with a prompt.
        
        Args:
            prompt: User message
            history: Conversation history [{"role": "user"|"assistant", "content": "..."}]
            system_prompt: Optional system prompt override
            allowed_tool_names: Optional tool allow-list for connectors with tool support
            
        Returns:
            LLM response text
            
        Raises:
            RateLimitError: When rate limited
            LLMError: For other errors
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if this connector is available."""
        pass


class LLMError(Exception):
    """General LLM error."""
    pass


class RateLimitError(LLMError):
    """Rate limit exceeded."""
    pass
