from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from fan_translation.config import GlossaryEntry, ProjectConfig

TRANSLATION_PROMPT_ENV = "FAN_TRANSLATION_SYSTEM_PROMPT"
TRANSLATION_PROMPT_FILE_ENV = "FAN_TRANSLATION_SYSTEM_PROMPT_FILE"
PROOFREADING_PROMPT_ENV = "FAN_TRANSLATION_PROOFREADING_PROMPT"
PROOFREADING_PROMPT_FILE_ENV = "FAN_TRANSLATION_PROOFREADING_PROMPT_FILE"

DEFAULT_TRANSLATION_SYSTEM_PROMPT = """You are an expert Japanese-to-English fan translation engine.

Before translating, scan the full excerpt and use the supplied canon list whenever it clearly matches the raw text.
Extract newly appearing characters, locations, and distinctive terms from the excerpt before translating.
If an entity is not covered by canon, resolve it conservatively from the excerpt itself without stopping for confirmation.

Translation rules:
- Preserve paragraph and line structure exactly.
- Keep each translation aligned to the provided line_number.
- Preserve address forms, honorifics, and explicit naming forms used in the raw.
- Prefer natural native English over literal translation-ese.
- Do not add attribution, explanation, or new information.
- Keep narration in literary past tense unless dialogue requires a different tense.

After the translation, report newly introduced characters, locations, and terms relative to the supplied canon list."""

DEFAULT_PROOFREADING_SYSTEM_PROMPT = """You are an expert English proofreader for fan translation prose.

Revise the provided English text into natural, publication-quality prose while preserving meaning, names, honorifics, paragraph boundaries, line breaks, symbols, and pacing.
Fix clunky translation-ese aggressively, but do not add information, attribution, or scene logic that is not present.
Keep tense and point of view consistent unless there is a clear error.

Output only:
1. A markdown table with columns Original Sentence | Why the Change is Needed | How to Change It
2. The Full Corrected Version

Do not add commentary outside the table and corrected text."""


@dataclass(slots=True)
class TranslationUnit:
    line_number: int
    source_text: str


def build_system_prompt(config: ProjectConfig) -> str:
    del config
    return (
        f"{_load_prompt_text(
            inline_env_name=TRANSLATION_PROMPT_ENV,
            file_env_name=TRANSLATION_PROMPT_FILE_ENV,
            fallback=DEFAULT_TRANSLATION_SYSTEM_PROMPT,
            label='translation system prompt',
        )}\n\n"
        "SYSTEM INTEGRATION OVERRIDE\n"
        "You are operating inside a translation app that requires machine-readable output.\n"
        "Follow the translation rules above, but return valid JSON only.\n"
        "Do not include markdown commentary, explanations, or prose outside the JSON object.\n"
        "Represent the translation body inside the translations array, keeping one entry per source line_number.\n"
        "Represent appended extraction sections in the new_characters, new_locations, and new_terms arrays.\n"
        "When a rule above conflicts with the JSON transport format, preserve the rule's intent inside the JSON fields.\n"
    )


def build_user_prompt(
    config: ProjectConfig,
    chunk: list[TranslationUnit],
    previous_context: list[TranslationUnit],
    glossary: list[GlossaryEntry],
    notes: str,
) -> str:
    canon_rows = [
        f"{entry.source} -> {entry.target}" + (f" ({entry.notes})" if entry.notes else "")
        for entry in glossary
    ]
    context_rows = [
        {"line_number": item.line_number, "source_text": item.source_text}
        for item in previous_context
    ]
    chunk_rows = [
        {"line_number": item.line_number, "source_text": item.source_text}
        for item in chunk
    ]

    instructions = {
        "task": (
            "Translate the excerpt into natural English using the extraction-first workflow, "
            "then report new characters, new locations, and new terms relative to the canon list."
        ),
        "source_language": config.source_language,
        "target_language": config.target_language,
        "style": config.style,
        "preserve_line_breaks": config.preserve_line_breaks,
        "rules": [
            "Keep each translation aligned to its line_number.",
            "Preserve paragraph and line structure exactly.",
            "Use the canon list when a clear match is present; otherwise resolve from the excerpt only.",
            "Preserve address form, honorifics, and kinship romanization when present.",
            "Keep dialogue natural but do not add attribution or explanation.",
            "Do not merge or split entries.",
            "Return JSON matching the requested schema only.",
        ],
        "output_schema": {
            "translations": [
                {
                    "line_number": 1,
                    "translation": "Translated line here",
                }
            ],
            "new_characters": ["<kanji>(<furigana>) / <EN name> (gender or note)"],
            "new_locations": ["Named location"],
            "new_terms": ["Distinctive term"],
        },
        "canon_list": canon_rows,
        "notes": notes,
        "previous_context": context_rows,
        "current_chunk": chunk_rows,
    }

    return json.dumps(instructions, ensure_ascii=False, indent=2)


def build_proofreading_system_prompt() -> str:
    return _load_prompt_text(
        inline_env_name=PROOFREADING_PROMPT_ENV,
        file_env_name=PROOFREADING_PROMPT_FILE_ENV,
        fallback=DEFAULT_PROOFREADING_SYSTEM_PROMPT,
        label="proofreading system prompt",
    )


def build_proofreading_user_prompt(text: str) -> str:
    return text.strip()


def _load_prompt_text(
    *,
    inline_env_name: str,
    file_env_name: str,
    fallback: str,
    label: str,
) -> str:
    inline_value = os.environ.get(inline_env_name, "").strip()
    if inline_value:
        return inline_value

    file_value = os.environ.get(file_env_name, "").strip()
    if not file_value:
        return fallback

    path = Path(file_value)
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(f"Unable to read {label} file: {path}") from exc

    if not text:
        raise RuntimeError(f"The configured {label} file is empty: {path}")

    return text
