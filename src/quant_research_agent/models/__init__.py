"""Provider-agnostic model gateway."""

from .base import ChatResponse, Message, ModelClient, Role, ToolCall, Usage
from .cache import ResponseCache
from .echo import EchoModel
from .gateway import ModelGateway, build_model, estimate_cost
from .ollama import OllamaModel
from .openai_compat import AnthropicModel, OpenAICompatModel
from .tokens import estimate_messages_tokens, estimate_tokens

__all__ = [
    "AnthropicModel",
    "ChatResponse",
    "EchoModel",
    "Message",
    "ModelClient",
    "ModelGateway",
    "OllamaModel",
    "OpenAICompatModel",
    "ResponseCache",
    "Role",
    "ToolCall",
    "Usage",
    "build_model",
    "estimate_cost",
    "estimate_messages_tokens",
    "estimate_tokens",
]
