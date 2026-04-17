from __future__ import annotations

import json
import time
from dataclasses import asdict, replace
from importlib import resources
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server

from fan_translation.client import ModelResponseError, build_model_client
from fan_translation.config import ProjectConfig
from fan_translation.pipeline import (
    accumulate_metrics,
    entries_to_json,
    entries_to_markdown,
    parse_glossary_text,
    proofread_entries,
    translate_text_with_metrics,
)
from fan_translation.runtime import build_llama_cpp_command


def run_server(project: ProjectConfig, host: str, port: int) -> None:
    app = TranslationWebApp(project)
    with make_server(host, port, app) as httpd:
        print(f"Fan translation UI running at http://{host}:{port}")
        print("Press Ctrl+C to stop the server.")
        httpd.serve_forever()


class TranslationWebApp:
    def __init__(self, project: ProjectConfig) -> None:
        self.project = project

    def __call__(self, environ: dict, start_response) -> list[bytes]:
        method = environ.get("REQUEST_METHOD", "GET").upper()
        path = environ.get("PATH_INFO", "/")

        try:
            if method == "GET" and path == "/":
                return self._html_response(start_response, _read_asset("index.html"))
            if method == "GET" and path == "/static/styles.css":
                return self._text_response(
                    start_response,
                    _read_asset("styles.css"),
                    content_type="text/css; charset=utf-8",
                )
            if method == "GET" and path == "/static/app.js":
                return self._text_response(
                    start_response,
                    _read_asset("app.js"),
                    content_type="application/javascript; charset=utf-8",
                )
            if method == "GET" and path == "/api/project":
                return self._json_response(
                    start_response,
                    {
                        "project": {
                            "provider": self.project.provider,
                            "model": self.project.model,
                            "api_base": self.project.resolved_api_base(),
                            "api_key": self.project.api_key,
                            "api_key_env": self.project.api_key_env,
                            "runtime": self.project.runtime,
                            "gguf_path": str(self.project.gguf_path) if self.project.gguf_path else "",
                            "hf_repo": self.project.hf_repo,
                            "hf_file": self.project.hf_file,
                            "llama_context_size": self.project.llama_context_size,
                            "launch_command": build_llama_cpp_command(self.project),
                            "source_language": self.project.source_language,
                            "target_language": self.project.target_language,
                            "temperature": self.project.temperature,
                            "chunk_size": self.project.chunk_size,
                            "context_window": self.project.context_window,
                            "request_timeout_seconds": self.project.request_timeout_seconds,
                            "style": self.project.style,
                            "glossary_text": _serialize_glossary(self.project),
                            "notes": self.project.load_notes(),
                        }
                    },
                )
            if method == "POST" and path == "/api/translate":
                return self._handle_translate(environ, start_response)
        except (ValueError, json.JSONDecodeError, ModelResponseError) as exc:
            return self._json_response(
                start_response,
                {"error": str(exc)},
                status="400 Bad Request",
            )
        except Exception as exc:  # pragma: no cover
            return self._json_response(
                start_response,
                {"error": f"Unexpected server error: {exc}"},
                status="500 Internal Server Error",
            )

        return self._json_response(
            start_response,
            {"error": f"Route not found: {method} {path}"},
            status="404 Not Found",
        )

    def _handle_translate(self, environ: dict, start_response) -> list[bytes]:
        raw_body = _read_request_body(environ)
        payload = json.loads(raw_body or "{}")
        source_text = str(payload.get("source_text", ""))
        glossary_text = str(payload.get("glossary_text", ""))
        notes = str(payload.get("notes", ""))
        provider = _coalesce_text(payload.get("provider"), self.project.provider)
        api_base = _coalesce_text(payload.get("api_base"), self.project.api_base)
        api_key = _coalesce_text(payload.get("api_key"), self.project.api_key)

        effective_project = replace(
            self.project,
            provider=provider,
            model=str(payload.get("model", self.project.model)),
            api_base=api_base.rstrip("/"),
            api_key=api_key,
            source_language=str(
                payload.get("source_language", self.project.source_language)
            ),
            target_language=str(
                payload.get("target_language", self.project.target_language)
            ),
            style=str(payload.get("style", self.project.style)),
            temperature=float(payload.get("temperature", self.project.temperature)),
            chunk_size=max(1, int(payload.get("chunk_size", self.project.chunk_size))),
            context_window=max(
                0, int(payload.get("context_window", self.project.context_window))
            ),
            request_timeout_seconds=max(
                10,
                int(
                    payload.get(
                        "request_timeout_seconds",
                        self.project.request_timeout_seconds,
                    )
                ),
            ),
        )
        glossary = parse_glossary_text(glossary_text)
        client = build_model_client(effective_project)
        started_at = time.perf_counter()
        run = translate_text_with_metrics(
            project=effective_project,
            client=client,
            lines=source_text.splitlines(),
            glossary=glossary,
            notes=notes,
        )
        proofreading_preview = ""
        proofreading_error = ""
        try:
            proofreading_response = proofread_entries(
                project=effective_project,
                client=client,
                entries=run.entries,
            )
            proofreading_preview = proofreading_response.content
            accumulate_metrics(run.metrics, proofreading_response)
        except (ValueError, ModelResponseError) as exc:
            proofreading_error = str(exc)
        elapsed_seconds = time.perf_counter() - started_at
        tokens_per_second = None
        if elapsed_seconds > 0 and run.metrics.total_tokens > 0:
            tokens_per_second = round(run.metrics.total_tokens / elapsed_seconds, 2)
        return self._json_response(
            start_response,
            {
                "entries": [asdict(entry) for entry in run.entries],
                "markdown": entries_to_markdown(run.entries, run.extraction),
                "json_output": entries_to_json(run.entries, run.extraction),
                "extraction": {
                    "new_characters": run.extraction.new_characters,
                    "new_locations": run.extraction.new_locations,
                    "new_terms": run.extraction.new_terms,
                },
                "proofreading_preview": proofreading_preview,
                "proofreading_error": proofreading_error,
                "elapsed_seconds": round(elapsed_seconds, 3),
                "prompt_tokens": run.metrics.prompt_tokens,
                "completion_tokens": run.metrics.completion_tokens,
                "total_tokens": run.metrics.total_tokens,
                "tokens_per_second": tokens_per_second,
            },
        )

    def _html_response(self, start_response, body: str) -> list[bytes]:
        return self._text_response(
            start_response,
            body,
            content_type="text/html; charset=utf-8",
        )

    def _json_response(
        self,
        start_response,
        payload: dict,
        status: str = "200 OK",
    ) -> list[bytes]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
        ]
        start_response(status, headers)
        return [body]

    def _text_response(
        self,
        start_response,
        body: str,
        content_type: str,
        status: str = "200 OK",
    ) -> list[bytes]:
        encoded = body.encode("utf-8")
        headers = [
            ("Content-Type", content_type),
            ("Content-Length", str(len(encoded))),
        ]
        start_response(status, headers)
        return [encoded]


def _serialize_glossary(project: ProjectConfig) -> str:
    glossary = project.load_glossary()
    if not glossary:
        return ""
    return "\n".join(
        f"{entry.source} | {entry.target} | {entry.notes}".rstrip(" |")
        for entry in glossary
    )


def _read_asset(name: str) -> str:
    return resources.files("fan_translation.web").joinpath(name).read_text(
        encoding="utf-8"
    )


def _read_request_body(environ: dict) -> str:
    body_size = environ.get("CONTENT_LENGTH", "0")
    try:
        length = int(body_size)
    except ValueError:
        length = 0

    body = environ["wsgi.input"].read(length).decode("utf-8")
    content_type = environ.get("CONTENT_TYPE", "")
    if "application/x-www-form-urlencoded" in content_type:
        parsed = parse_qs(body)
        return json.dumps({key: values[-1] for key, values in parsed.items()})
    return body


def _coalesce_text(value: object, fallback: str) -> str:
    text = str(value or "").strip()
    if text:
        return text
    return fallback
