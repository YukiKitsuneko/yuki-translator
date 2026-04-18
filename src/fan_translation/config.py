from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl
from urllib.parse import urlsplit
from urllib.parse import urlunsplit

DEFAULT_PROVIDER = "llama.cpp"
DEFAULT_API_BASE = "http://127.0.0.1:8080/v1"
OPENAI_API_BASE = "https://api.openai.com/v1"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/openai"


@dataclass(slots=True)
class GlossaryEntry:
    source: str
    target: str
    notes: str = ""


@dataclass(slots=True)
class ProjectConfig:
    provider: str = DEFAULT_PROVIDER
    model: str = "Gemma4_E2B_Abliterated_Baked_HF_Ready"
    api_base: str = DEFAULT_API_BASE
    api_key: str = "llama.cpp"
    api_key_env: str = ""
    runtime: str = "llama.cpp"
    gguf_path: Path | None = None
    hf_repo: str = "mradermacher/Gemma4_E2B_Abliterated_Baked_HF_Ready-i1-GGUF"
    hf_file: str = ""
    llama_context_size: int = 8192
    source_language: str = "Japanese"
    target_language: str = "English"
    temperature: float = 0.2
    chunk_size: int = 8
    context_window: int = 2
    single_pass_translation: bool = False
    enable_proofreading: bool = True
    style: str = "Natural fan translation with consistent terminology."
    preserve_line_breaks: bool = True
    glossary_path: Path | None = None
    notes_path: Path | None = None
    request_timeout_seconds: int = 300
    root_dir: Path = Path(".")

    @classmethod
    def load(cls, path: str | Path) -> "ProjectConfig":
        config_path = Path(path).resolve()
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        root_dir = config_path.parent
        glossary_path = _resolve_optional_path(root_dir, raw.get("glossary_path"))
        notes_path = _resolve_optional_path(root_dir, raw.get("notes_path"))
        gguf_path = _resolve_optional_path(root_dir, raw.get("gguf_path"))
        return cls(
            provider=_normalize_provider(raw.get("provider", DEFAULT_PROVIDER)),
            model=raw.get("model", "Gemma4_E2B_Abliterated_Baked_HF_Ready"),
            api_base=str(raw.get("api_base", DEFAULT_API_BASE)).rstrip("/"),
            api_key=raw.get("api_key", "llama.cpp"),
            api_key_env=str(raw.get("api_key_env", "")).strip(),
            runtime=raw.get("runtime", "llama.cpp"),
            gguf_path=gguf_path,
            hf_repo=raw.get(
                "hf_repo",
                "mradermacher/Gemma4_E2B_Abliterated_Baked_HF_Ready-i1-GGUF",
            ),
            hf_file=raw.get("hf_file", ""),
            llama_context_size=int(raw.get("llama_context_size", 8192)),
            source_language=raw.get("source_language", "Japanese"),
            target_language=raw.get("target_language", "English"),
            temperature=float(raw.get("temperature", 0.2)),
            chunk_size=int(raw.get("chunk_size", 8)),
            context_window=int(raw.get("context_window", 2)),
            single_pass_translation=bool(raw.get("single_pass_translation", False)),
            enable_proofreading=bool(raw.get("enable_proofreading", True)),
            style=raw.get(
                "style",
                "Natural fan translation with consistent terminology.",
            ),
            preserve_line_breaks=bool(raw.get("preserve_line_breaks", True)),
            glossary_path=glossary_path,
            notes_path=notes_path,
            request_timeout_seconds=int(raw.get("request_timeout_seconds", 300)),
            root_dir=root_dir,
        )

    def load_glossary(self) -> list[GlossaryEntry]:
        if self.glossary_path is None or not self.glossary_path.exists():
            return []
        raw = json.loads(self.glossary_path.read_text(encoding="utf-8"))
        entries: list[GlossaryEntry] = []
        for item in raw:
            entries.append(
                GlossaryEntry(
                    source=item["source"],
                    target=item["target"],
                    notes=item.get("notes", ""),
                )
            )
        return entries

    def load_notes(self) -> str:
        if self.notes_path is None or not self.notes_path.exists():
            return ""
        return self.notes_path.read_text(encoding="utf-8").strip()

    def resolved_api_base(self) -> str:
        configured = self.api_base.strip()
        if configured:
            return _normalize_api_base(self.provider, configured)
        return _normalize_api_base(
            self.provider, default_api_base_for_provider(self.provider)
        )

    def resolved_api_key(self) -> str:
        configured = self.api_key.strip()
        if configured:
            return _validate_api_key(self.provider, configured)

        env_name = self.api_key_env.strip() or default_api_key_env_for_provider(
            self.provider
        )
        if not env_name:
            return ""

        api_key = os.environ.get(env_name, "").strip()
        if api_key:
            return _validate_api_key(self.provider, api_key)

        raise ValueError(
            f"Missing API key for provider '{self.provider}'. "
            f"Set {env_name} or provide api_key in the project config."
        )


def _resolve_optional_path(root_dir: Path, value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = root_dir / path
    return path.resolve()


def _normalize_provider(value: object) -> str:
    provider = str(value or DEFAULT_PROVIDER).strip().lower()
    aliases = {
        "chatgpt": "openai",
        "google": "gemini",
        "local": "llama.cpp",
        "llamacpp": "llama.cpp",
        "openai_compatible": "custom",
    }
    return aliases.get(provider, provider or DEFAULT_PROVIDER)


def default_api_base_for_provider(provider: str) -> str:
    normalized = _normalize_provider(provider)
    if normalized == "openai":
        return OPENAI_API_BASE
    if normalized == "gemini":
        return GEMINI_API_BASE
    if normalized == "custom":
        return ""
    return DEFAULT_API_BASE


def default_api_key_env_for_provider(provider: str) -> str:
    normalized = _normalize_provider(provider)
    if normalized == "openai":
        return "OPENAI_API_KEY"
    if normalized == "gemini":
        return "GEMINI_API_KEY"
    return ""


def _normalize_api_base(provider: str, api_base: str) -> str:
    normalized_provider = _normalize_provider(provider)
    raw = api_base.strip()
    if not raw:
        return ""

    parsed = urlsplit(raw)
    query_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if parsed.query:
        if "key" in query_params or "api_key" in query_params:
            if normalized_provider == "gemini":
                raise ValueError(
                    "Gemini API base must not include ?key=... when using this app. "
                    "Set api_base to https://generativelanguage.googleapis.com/v1beta/openai "
                    "and provide the credential only once via api_key or GEMINI_API_KEY."
                )
            raise ValueError(
                "API base must not include embedded credentials like ?key=... . "
                "Provide credentials only once via api_key or an environment variable."
            )
        raise ValueError(
            "API base must not include query parameters. Use the provider root URL only."
        )

    if parsed.fragment:
        raise ValueError("API base must not include a URL fragment.")

    path = parsed.path.rstrip("/")
    if path.endswith("/chat/completions"):
        path = path[: -len("/chat/completions")]

    normalized = urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))
    return normalized.rstrip("/")


def _validate_api_key(provider: str, api_key: str) -> str:
    normalized_provider = _normalize_provider(provider)
    key = api_key.strip()
    if not key:
        return key

    if normalized_provider == "gemini":
        # Google AI Studio Gemini API keys are API keys, not OAuth/user access tokens.
        # Catch a few common token shapes so the UI can fail with a useful message.
        if key.startswith(("AQ.", "ya29.", "ya29", "eyJ")):
            raise ValueError(
                "The provided Gemini credential looks like an OAuth or access token, "
                "not a Gemini API key. Create an API key in Google AI Studio and use "
                "that value here instead."
            )
        if "." in key and not key.startswith("AIza"):
            raise ValueError(
                "The provided Gemini credential does not look like a Google AI Studio "
                "API key. Use a Gemini API key from Google AI Studio, or set it via "
                "GEMINI_API_KEY."
            )

    return key
