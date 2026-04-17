from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from urllib import error, request

from fan_translation.config import ProjectConfig


class ModelResponseError(RuntimeError):
    """Raised when the model response cannot be interpreted."""


@dataclass(slots=True)
class ModelTranslationResponse:
    content: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(slots=True)
class OpenAICompatClient:
    provider: str
    api_base: str
    api_key: str
    model: str
    timeout_seconds: int = 120

    def translate(self, system_prompt: str, user_prompt: str, temperature: float) -> str:
        return self.translate_with_metadata(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
        ).content

    def translate_with_metadata(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
    ) -> ModelTranslationResponse:
        return self.complete_with_metadata(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            response_format={"type": "json_object"},
        )

    def complete_with_metadata(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        response_format: dict | None = None,
    ) -> ModelTranslationResponse:
        payload = {
            "model": self.model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        reasoning_effort = _default_reasoning_effort(self.provider, self.model)
        if reasoning_effort:
            payload["reasoning_effort"] = reasoning_effort
        if response_format is not None:
            payload["response_format"] = response_format
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url=f"{self.api_base}/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except socket.timeout as exc:
            raise ModelResponseError(
                "Model request timed out. Increase request_timeout_seconds, reduce "
                "chunk_size, or verify the selected model endpoint is healthy."
            ) from exc
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ModelResponseError(
                _format_http_error_message(self.api_base, exc.code, detail)
            ) from exc
        except error.URLError as exc:
            if isinstance(exc.reason, socket.timeout):
                raise ModelResponseError(
                    "Model request timed out. Increase request_timeout_seconds, reduce "
                    "chunk_size, or verify the selected model endpoint is healthy."
                ) from exc
            raise ModelResponseError(
                f"Could not reach model endpoint at {self.api_base}: {exc.reason}"
            ) from exc

        try:
            parsed = json.loads(raw)
            usage = parsed.get("usage", {})
            return ModelTranslationResponse(
                content=parsed["choices"][0]["message"]["content"],
                prompt_tokens=_coerce_optional_int(usage.get("prompt_tokens")),
                completion_tokens=_coerce_optional_int(usage.get("completion_tokens")),
                total_tokens=_coerce_optional_int(usage.get("total_tokens")),
            )
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ModelResponseError(
                f"Unexpected model response payload: {raw[:500]}"
            ) from exc


def _coerce_optional_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    return None


def _default_reasoning_effort(provider: str, model: str) -> str | None:
    normalized_provider = provider.strip().lower()
    normalized_model = model.strip().lower()

    if normalized_provider == "gemini":
        return "high"

    if normalized_provider == "openai" and normalized_model.startswith("gpt-5"):
        return "high"

    return None


def _format_http_error_message(api_base: str, status_code: int, detail: str) -> str:
    parsed_detail = _try_parse_json(detail)
    error_payload = _extract_error_object(parsed_detail)
    error_code = str(error_payload.get("code", "")).strip()
    error_message = str(error_payload.get("message", "")).strip()

    if status_code == 429 and error_code == "insufficient_quota":
        if "api.openai.com" in api_base:
            return (
                "OpenAI returned insufficient_quota. This usually means the API "
                "project has no available credits, billing is not enabled, or the "
                "monthly spend limit has been reached. Check OpenAI billing and usage, "
                "or switch to Gemini / llama.cpp in the UI."
            )
        return (
            "The selected provider reported insufficient quota. This is usually an "
            "account or billing limit, not a bad prompt. Check the provider's billing "
            "and usage limits, or switch models/providers."
        )

    if status_code == 429 and error_message:
        return f"Model endpoint rate limited the request: {error_message}"

    if status_code == 503 and error_message:
        return f"Model endpoint is temporarily unavailable: {error_message}"

    return f"Model endpoint returned HTTP {status_code}: {detail}"


def _try_parse_json(raw_text: str) -> object | None:
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        return None


def _extract_error_object(payload: object) -> dict:
    if isinstance(payload, dict):
        error_value = payload.get("error")
        if isinstance(error_value, dict):
            return error_value
    if isinstance(payload, list) and payload:
        first = payload[0]
        if isinstance(first, dict):
            error_value = first.get("error")
            if isinstance(error_value, dict):
                return error_value
    return {}


def build_model_client(project: ProjectConfig) -> OpenAICompatClient:
    return OpenAICompatClient(
        provider=project.provider,
        api_base=project.resolved_api_base(),
        api_key=project.resolved_api_key(),
        model=project.model,
        timeout_seconds=project.request_timeout_seconds,
    )
