import json
import os
from typing import List, Dict, Any, Optional

from openai import OpenAI


class LLMProvider:
    def complete(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        raise NotImplementedError


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, model: str = "gpt-4o", base_url: Optional[str] = None, api_key: Optional[str] = None):
        self.model = model
        # Default to OpenAI if base_url is not provided, but allow overrides for local like Ollama
        api_key = api_key or os.environ.get("OPENAI_API_KEY", "dummy-key-for-local")
        self.client = OpenAI(base_url=base_url, api_key=api_key)

    def complete(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        kwargs = {
            "model": self.model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        response = self.client.chat.completions.create(**kwargs)
        message = response.choices[0].message

        result = {
            "content": message.content,
            "tool_calls": []
        }

        if message.tool_calls:
            for tool_call in message.tool_calls:
                result["tool_calls"].append({
                    "id": tool_call.id,
                    "name": tool_call.function.name,
                    "arguments": tool_call.function.arguments,
                })

        return result
