import json
import os
from typing import Any

import httpx
from pydantic import ValidationError


class AIProviderError(Exception):
    def __init__(self, message: str, status_code: int = 503):
        super().__init__(message)
        self.status_code = status_code


def provider_configured() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY", "").strip())


def complete_json(system_prompt: str, user_data: dict[str, Any]) -> Any:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise AIProviderError("The GenAI provider is not configured.")

    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip()
    base_url = os.environ.get(
        "OPENAI_BASE_URL", "https://api.openai.com/v1"
    ).rstrip("/")
    if not model or not base_url.startswith(("https://", "http://")):
        raise AIProviderError("The GenAI provider configuration is invalid.")

    try:
        with httpx.Client(
            timeout=httpx.Timeout(20.0, connect=5.0),
            follow_redirects=False,
        ) as client:
            response = client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "temperature": 0.2,
                    "max_tokens": 1800,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": json.dumps(user_data, ensure_ascii=False),
                        },
                    ],
                },
            )
    except httpx.TimeoutException as error:
        raise AIProviderError("The GenAI provider request timed out.", 504) from error
    except httpx.RequestError as error:
        raise AIProviderError("The GenAI provider could not be reached.", 502) from error

    if response.status_code == 429:
        raise AIProviderError(
            "The GenAI provider rate limit was reached. Please retry shortly.", 429
        )
    if response.is_error:
        raise AIProviderError(
            f"The GenAI provider returned an error (HTTP {response.status_code}).",
            502,
        )
    if len(response.content) > 32_000:
        raise AIProviderError("The GenAI provider response exceeded the size limit.", 502)

    try:
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        if not isinstance(content, str) or len(content) > 24_000:
            raise ValueError("Invalid content")
        return json.loads(content)
    except (ValueError, KeyError, IndexError, TypeError) as error:
        raise AIProviderError(
            "The GenAI provider returned malformed JSON output.", 502
        ) from error


def validate_output(model: type, value: Any) -> Any:
    try:
        return model.model_validate(value)
    except ValidationError as error:
        raise AIProviderError(
            "The GenAI provider response did not match the required schema.", 502
        ) from error
