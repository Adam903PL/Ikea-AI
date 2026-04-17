from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import openrouter_client


class FakeResponse:
    def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self) -> dict[str, object]:
        return self._payload


class FakeHttpxClient:
    requests: list[dict[str, object]] = []

    def __init__(self, *args, **kwargs) -> None:
        self.timeout = kwargs.get("timeout")

    def __enter__(self) -> "FakeHttpxClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def post(self, url: str, headers: dict[str, str], json: dict[str, object]) -> FakeResponse:
        self.__class__.requests.append({"url": url, "headers": headers, "json": json})
        return FakeResponse(
            {
                "id": "resp_123",
                "choices": [
                    {
                        "message": {
                            "content": '{"steps":[{"stepNumber":1,"title":"Start","description":"Opis","partIndices":[1],"contextPartIndices":[],"partRoles":{"1":"panel"}}]}'
                        }
                    }
                ],
            }
        )


class OpenRouterClientTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeHttpxClient.requests = []
        self.temp_dir = tempfile.TemporaryDirectory()
        self.preview_png = Path(self.temp_dir.name) / "preview.png"
        self.preview_png.write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO2sY4QAAAAASUVORK5CYII="))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_request_contains_structured_outputs_provider_flags_and_image(self) -> None:
        client = openrouter_client.OpenRouterClient(
            api_key="test-key",
            model="google/gemini-2.5-pro",
            fallback_model="anthropic/claude-sonnet-4.5",
            http_referer="https://example.com",
            app_title="IKEA Builder",
        )

        with patch.object(openrouter_client, "httpx") as httpx_module:
            httpx_module.Client = FakeHttpxClient
            payload, planner = client.generate_assembly_plan(
                system_prompt="sys",
                user_prompt="user",
                preview_png_path=self.preview_png,
            )

        request = FakeHttpxClient.requests[0]["json"]
        self.assertEqual(request["response_format"]["type"], "json_schema")
        self.assertTrue(request["response_format"]["json_schema"]["strict"])
        self.assertTrue(request["provider"]["require_parameters"])
        self.assertEqual(request["provider"]["data_collection"], "deny")
        self.assertTrue(request["provider"]["zdr"])
        self.assertEqual(request["messages"][1]["content"][1]["type"], "image_url")
        self.assertTrue(request["messages"][1]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,"))
        self.assertEqual(payload["steps"][0]["stepNumber"], 1)
        self.assertEqual(planner["model"], "google/gemini-2.5-pro")


if __name__ == "__main__":
    unittest.main()
