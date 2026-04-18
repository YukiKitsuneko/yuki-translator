from __future__ import annotations

import json
import re
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path

from fan_translation.client import ModelTranslationResponse
from fan_translation.config import GlossaryEntry
from fan_translation.client import OpenAICompatClient
from fan_translation.config import ProjectConfig
from fan_translation.prompts import (
    TranslationUnit,
    build_proofreading_system_prompt,
    build_proofreading_user_prompt,
    build_system_prompt,
    build_user_prompt,
)


@dataclass(slots=True)
class TranslationEntry:
    line_number: int
    source_text: str
    translation: str


@dataclass(slots=True)
class TranslationMetrics:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass(slots=True)
class ExtractionSummary:
    new_characters: list[str]
    new_locations: list[str]
    new_terms: list[str]


@dataclass(slots=True)
class TranslationRun:
    entries: list[TranslationEntry]
    metrics: TranslationMetrics
    extraction: ExtractionSummary


def translate_text(
    project: ProjectConfig,
    client: OpenAICompatClient,
    source_text: str,
    glossary: list[GlossaryEntry] | None = None,
    notes: str | None = None,
) -> list[TranslationEntry]:
    return translate_text_with_metrics(
        lines=source_text.splitlines(),
        project=project,
        client=client,
        glossary=glossary,
        notes=notes,
    ).entries


def translate_file(
    project: ProjectConfig,
    client: OpenAICompatClient,
    input_path: str | Path,
) -> list[TranslationEntry]:
    path = Path(input_path).resolve()
    lines = path.read_text(encoding="utf-8").splitlines()
    return translate_text_with_metrics(lines=lines, project=project, client=client).entries


def translate_text_with_metrics(
    lines: list[str],
    project: ProjectConfig,
    client: OpenAICompatClient,
    glossary: list[GlossaryEntry] | None = None,
    notes: str | None = None,
    ) -> TranslationRun:
    return _translate_lines(
        lines=lines,
        project=project,
        client=client,
        glossary=glossary,
        notes=notes,
    )


def entries_to_json(
    entries: list[TranslationEntry],
    extraction: ExtractionSummary | None = None,
) -> str:
    payload: dict[str, object] = {"entries": [asdict(entry) for entry in entries]}
    if extraction is not None:
        payload["new_characters"] = extraction.new_characters
        payload["new_locations"] = extraction.new_locations
        payload["new_terms"] = extraction.new_terms
    return json.dumps(payload, ensure_ascii=False, indent=2)


def entries_to_markdown(
    entries: list[TranslationEntry],
    extraction: ExtractionSummary | None = None,
) -> str:
    markdown_lines = ["# Translation Output", ""]
    for entry in entries:
        if not entry.source_text and not entry.translation:
            markdown_lines.append("")
            continue
        markdown_lines.append(f"## Line {entry.line_number}")
        markdown_lines.append(f"Source: {entry.source_text}")
        markdown_lines.append(f"Translation: {entry.translation}")
        markdown_lines.append("")
    if extraction is not None:
        markdown_lines.extend(_extraction_to_markdown_lines(extraction))
    return "\n".join(markdown_lines).rstrip() + "\n"


def entries_to_plain_text(entries: list[TranslationEntry]) -> str:
    return "\n".join(entry.translation for entry in entries)


def proofread_entries(
    project: ProjectConfig,
    client: OpenAICompatClient,
    entries: list[TranslationEntry],
) -> ModelTranslationResponse:
    proofreading_source = entries_to_plain_text(entries)
    if not proofreading_source.strip():
        return ModelTranslationResponse(content="")

    return client.complete_with_metadata(
        system_prompt=build_proofreading_system_prompt(),
        user_prompt=build_proofreading_user_prompt(proofreading_source),
        temperature=project.temperature,
        response_format=None,
    )


def accumulate_metrics(
    metrics: TranslationMetrics,
    response: ModelTranslationResponse,
) -> None:
    _accumulate_metrics(metrics, response)


def parse_glossary_text(raw_text: str) -> list[GlossaryEntry]:
    stripped = raw_text.strip()
    if not stripped:
        return []

    if stripped.startswith("["):
        parsed = json.loads(stripped)
        return [
            GlossaryEntry(
                source=item["source"],
                target=item["target"],
                notes=item.get("notes", ""),
            )
            for item in parsed
        ]

    entries: list[GlossaryEntry] = []
    for line in stripped.splitlines():
        row = line.strip()
        if not row or row.startswith("#"):
            continue
        parts = [part.strip() for part in row.split("|")]
        if len(parts) < 2:
            raise ValueError(
                "Glossary text must be JSON or pipe-delimited lines like 'source | target | notes'."
            )
        notes = parts[2] if len(parts) > 2 else ""
        entries.append(GlossaryEntry(source=parts[0], target=parts[1], notes=notes))
    return entries


def _translate_lines(
    lines: list[str],
    project: ProjectConfig,
    client: OpenAICompatClient,
    glossary: list[GlossaryEntry] | None = None,
    notes: str | None = None,
) -> TranslationRun:
    source_units = [
        TranslationUnit(line_number=index + 1, source_text=line)
        for index, line in enumerate(lines)
        if line.strip()
    ]
    glossary = glossary if glossary is not None else project.load_glossary()
    notes = notes if notes is not None else project.load_notes()
    system_prompt = build_system_prompt(project)

    translated_by_line: dict[int, str] = {}
    metrics = TranslationMetrics()
    extracted_characters: list[str] = []
    extracted_locations: list[str] = []
    extracted_terms: list[str] = []
    for chunk in _chunked(source_units, project.chunk_size):
        context = _context_for_chunk(source_units, chunk, project.context_window)
        user_prompt = build_user_prompt(project, chunk, context, glossary, notes)
        response = client.translate_with_metadata(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=project.temperature,
        )
        _accumulate_metrics(metrics, response)
        parsed = _parse_translation_response(response.content)
        for item in parsed["translations"]:
            translated_by_line[item["line_number"]] = item["translation"].strip()
        _extend_unique(extracted_characters, parsed["new_characters"])
        _extend_unique(extracted_locations, parsed["new_locations"])
        _extend_unique(extracted_terms, parsed["new_terms"])

    entries: list[TranslationEntry] = []
    for index, line in enumerate(lines, start=1):
        if not line.strip():
            entries.append(
                TranslationEntry(line_number=index, source_text="", translation="")
            )
            continue
        entries.append(
            TranslationEntry(
                line_number=index,
                source_text=line,
                translation=translated_by_line.get(index, ""),
            )
        )
    extraction = ExtractionSummary(
        new_characters=extracted_characters or ["None"],
        new_locations=extracted_locations or ["None"],
        new_terms=extracted_terms or ["None"],
    )
    return TranslationRun(entries=entries, metrics=metrics, extraction=extraction)


def write_output(
    entries: list[TranslationEntry],
    output_path: str | Path,
    output_format: str,
) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if output_format == "json":
        path.write_text(entries_to_json(entries), encoding="utf-8")
        return

    path.write_text(entries_to_markdown(entries), encoding="utf-8")


def _chunked(
    units: list[TranslationUnit], chunk_size: int
) -> list[list[TranslationUnit]]:
    return [units[index : index + chunk_size] for index in range(0, len(units), chunk_size)]


def _context_for_chunk(
    all_units: list[TranslationUnit],
    chunk: list[TranslationUnit],
    context_window: int,
) -> list[TranslationUnit]:
    if not chunk or context_window <= 0:
        return []
    first_line = chunk[0].line_number
    context = [
        item
        for item in all_units
        if item.line_number < first_line and item.line_number >= first_line - context_window
    ]
    return context


def _parse_translation_response(raw_json: str) -> dict[str, list]:
    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        translations = _extract_translations_from_malformed_json(raw_json)
        if translations is None:
            raise ValueError(f"Model did not return valid JSON: {raw_json}") from exc
        return {
            "translations": _clean_translations(translations),
            "new_characters": [],
            "new_locations": [],
            "new_terms": [],
        }

    translations = parsed.get("translations")
    if not isinstance(translations, list):
        raise ValueError(f"Missing 'translations' list in model output: {raw_json}")

    return {
        "translations": _clean_translations(translations),
        "new_characters": _clean_metadata_list(parsed.get("new_characters")),
        "new_locations": _clean_metadata_list(parsed.get("new_locations")),
        "new_terms": _clean_metadata_list(parsed.get("new_terms")),
    }


def _clean_translations(translations: list[object]) -> list[dict[str, str | int]]:
    cleaned: list[dict[str, str | int]] = []
    for item in translations:
        if not isinstance(item, dict):
            continue
        line_number = item.get("line_number")
        translation = item.get("translation")
        if isinstance(line_number, int) and isinstance(translation, str):
            cleaned.append(
                {"line_number": line_number, "translation": translation}
            )
    return cleaned


def _clean_metadata_list(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    cleaned: list[str] = []
    for item in values:
        if isinstance(item, str):
            text = item.strip()
            if text and text.lower() != "none":
                cleaned.append(text)
    return cleaned


def _extract_translations_from_malformed_json(raw_json: str) -> list[object] | None:
    marker = '"translations"'
    key_index = raw_json.find(marker)
    if key_index == -1:
        return None

    array_start = raw_json.find("[", key_index)
    if array_start == -1:
        return None

    array_end = _find_matching_bracket(raw_json, array_start)
    if array_end == -1:
        return _extract_completed_translation_objects(raw_json)

    array_text = raw_json[array_start : array_end + 1]
    try:
        parsed = json.loads(array_text)
    except json.JSONDecodeError:
        return _extract_completed_translation_objects(raw_json)

    if not isinstance(parsed, list):
        return _extract_completed_translation_objects(raw_json)
    return parsed


def _find_matching_bracket(raw_text: str, start_index: int) -> int:
    depth = 0
    in_string = False
    escape = False

    for index in range(start_index, len(raw_text)):
        char = raw_text[index]

        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue

        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return index

    return -1


def _extract_completed_translation_objects(raw_json: str) -> list[object] | None:
    pattern = re.compile(
        r'\{\s*"line_number"\s*:\s*(\d+)\s*,\s*"translation"\s*:\s*"((?:\\.|[^"\\])*)"\s*\}'
    )
    matches = pattern.findall(raw_json)
    if not matches:
        return None

    extracted: list[object] = []
    for line_number_text, translation_text in matches:
        try:
            translation = json.loads(f'"{translation_text}"')
        except json.JSONDecodeError:
            continue
        extracted.append(
            {
                "line_number": int(line_number_text),
                "translation": translation,
            }
        )

    if not extracted:
        return None
    return extracted


def _accumulate_metrics(
    metrics: TranslationMetrics,
    response: ModelTranslationResponse,
) -> None:
    if response.prompt_tokens is not None:
        metrics.prompt_tokens += response.prompt_tokens
    if response.completion_tokens is not None:
        metrics.completion_tokens += response.completion_tokens
    if response.total_tokens is not None:
        metrics.total_tokens += response.total_tokens


def _extend_unique(target: list[str], values: list[str]) -> None:
    for value in values:
        if value not in target:
            target.append(value)


def _extraction_to_markdown_lines(extraction: ExtractionSummary) -> list[str]:
    return [
        "## New Characters",
        *(_format_extraction_section(extraction.new_characters)),
        "",
        "## New Locations",
        *(_format_extraction_section(extraction.new_locations)),
        "",
        "## New Terms",
        *(_format_extraction_section(extraction.new_terms)),
        "",
    ]


def _format_extraction_section(items: list[str]) -> list[str]:
    if not items:
        return ["None"]
    if len(items) == 1 and items[0] == "None":
        return ["None"]
    return [f"- {item}" for item in items]
