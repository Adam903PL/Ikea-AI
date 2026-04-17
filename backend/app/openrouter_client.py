from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

try:
    import httpx
except Exception as exc:  # pragma: no cover - depends on local runtime
    httpx = None
    HTTPX_IMPORT_ERROR = str(exc)
else:  # pragma: no cover - exercised in integration tests instead
    HTTPX_IMPORT_ERROR = None

from app.assembly_schema import build_openrouter_response_format

DEFAULT_OPENROUTER_MODEL = "google/gemini-2.5-pro"
DEFAULT_OPENROUTER_FALLBACK_MODEL = "anthropic/claude-sonnet-4.5"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterError(RuntimeError):
    pass


class OpenRouterClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        fallback_model: str | None = None,
        http_referer: str | None = None,
        app_title: str | None = None,
        timeout_seconds: float = 90.0,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.model = model or os.getenv("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL)
        self.fallback_model = fallback_model or os.getenv(
            "OPENROUTER_FALLBACK_MODEL",
            DEFAULT_OPENROUTER_FALLBACK_MODEL,
        )
        self.http_referer = http_referer or os.getenv("OPENROUTER_HTTP_REFERER")
        self.app_title = app_title or os.getenv("OPENROUTER_APP_TITLE")
        self.timeout_seconds = timeout_seconds

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def generate_assembly_plan(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        preview_png_path: Path | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if not self.api_key:
            raise OpenRouterError(
                "OPENROUTER_API_KEY is not configured. Falling back to the deterministic planner."
            )

        if httpx is None:
            raise OpenRouterError(
                "httpx is not installed in the backend environment. "
                f"Import error: {HTTPX_IMPORT_ERROR}"
            )

        attempts: list[str] = [self.model, self.model]

        if self.fallback_model and self.fallback_model != self.model:
            attempts.append(self.fallback_model)

        last_error: Exception | None = None

        for model_name in attempts:
            try:
                response_payload = self._request_completion(
                    model_name=model_name,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    preview_png_path=preview_png_path,
                )
                content = self._extract_message_content(response_payload)
                plan = json.loads(content)
                return (
                    plan,
                    {
                        "source": "ai",
                        "model": model_name,
                        "response_id": response_payload.get("id"),
                    },
                )
            except Exception as exc:
                last_error = exc

        if last_error is None:
            raise OpenRouterError("OpenRouter request failed without a specific error.")

        raise OpenRouterError(str(last_error)) from last_error

    def _request_completion(
        self,
        *,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
        preview_png_path: Path | None,
    ) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        if self.http_referer:
            headers["HTTP-Referer"] = self.http_referer

        if self.app_title:
            headers["X-Title"] = self.app_title

        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": self._build_user_content(user_prompt, preview_png_path)},
            ],
            "response_format": build_openrouter_response_format(),
            "provider": {
                "require_parameters": True,
                "data_collection": "deny",
                "zdr": True,
            },
            "stream": False,
            "temperature": 0.2,
        }

        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(OPENROUTER_URL, headers=headers, json=payload)

        if response.status_code >= 400:
            detail = self._read_error_detail(response)
            raise OpenRouterError(
                f"OpenRouter request failed for model {model_name}: {detail}"
            )

        return response.json()

    def _build_user_content(
        self,
        prompt: str,
        preview_png_path: Path | None,
    ) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]

        if preview_png_path and preview_png_path.is_file():
            encoded_image = base64.b64encode(preview_png_path.read_bytes()).decode("ascii")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{encoded_image}",
                    },
                }
            )

        return content

    def _extract_message_content(self, payload: dict[str, Any]) -> str:
        choices = payload.get("choices")

        if not choices:
            raise OpenRouterError("OpenRouter did not return any choices.")

        message = choices[0].get("message", {})
        content = message.get("content")

        if isinstance(content, str):
            return content

        if isinstance(content, list):
            text_fragments = [
                fragment.get("text", "")
                for fragment in content
                if isinstance(fragment, dict) and fragment.get("type") == "text"
            ]
            if text_fragments:
                return "".join(text_fragments)

        raise OpenRouterError("OpenRouter returned an unsupported message format.")

    def _read_error_detail(self, response: Any) -> str:
        try:
            payload = response.json()
        except Exception:
            return response.text

        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                return str(error.get("message") or error.get("code") or payload)
            return str(payload.get("detail") or payload)

        return str(payload)
