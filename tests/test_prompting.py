import json
import os
import socket
import tempfile
import unittest
from urllib import error
from unittest import mock

from fan_translation.client import (
    ModelResponseError,
    ModelTranslationResponse,
    OpenAICompatClient,
    build_model_client,
)
from fan_translation.config import GlossaryEntry, ProjectConfig
from fan_translation.pipeline import (
    ExtractionSummary,
    TranslationEntry,
    TranslationMetrics,
    _parse_translation_response,
    entries_to_plain_text,
    entries_to_markdown,
    parse_glossary_text,
    proofread_entries,
    translate_text_with_metrics,
)
from fan_translation.prompts import (
    TranslationUnit,
    build_proofreading_system_prompt,
    build_system_prompt,
    build_user_prompt,
)
from fan_translation.runtime import build_llama_cpp_command


class PromptingTests(unittest.TestCase):
    def test_system_prompt_mentions_json(self) -> None:
        config = ProjectConfig()
        prompt = build_system_prompt(config)
        self.assertIn("valid JSON only", prompt)

    def test_system_prompt_can_load_from_secret_file(self) -> None:
        config = ProjectConfig()
        with tempfile.TemporaryDirectory() as temp_dir:
            prompt_path = os.path.join(temp_dir, "translation_prompt.txt")
            with open(prompt_path, "w", encoding="utf-8") as handle:
                handle.write("PRIVATE TRANSLATION PROMPT")

            with mock.patch.dict(
                os.environ,
                {"FAN_TRANSLATION_SYSTEM_PROMPT_FILE": prompt_path},
                clear=False,
            ):
                prompt = build_system_prompt(config)

        self.assertIn("PRIVATE TRANSLATION PROMPT", prompt)
        self.assertIn("valid JSON only", prompt)

    def test_proofreading_prompt_can_load_from_secret_env(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"FAN_TRANSLATION_PROOFREADING_PROMPT": "PRIVATE PROOFREADING PROMPT"},
            clear=False,
        ):
            prompt = build_proofreading_system_prompt()

        self.assertEqual(prompt, "PRIVATE PROOFREADING PROMPT")

    def test_llama_command_uses_hf_repo_when_hf_file_missing(self) -> None:
        project = ProjectConfig(
            provider="llama.cpp",
            api_base="http://127.0.0.1:8080/v1",
            hf_repo="ggml-org/gemma-3-1b-it-GGUF",
            hf_file="",
            gguf_path=None,
            llama_context_size=4096,
        )

        command = build_llama_cpp_command(project)

        self.assertIn('llama-server -hf "ggml-org/gemma-3-1b-it-GGUF"', command)
        self.assertNotIn("-hff", command)

    def test_user_prompt_is_valid_json(self) -> None:
        config = ProjectConfig()
        chunk = [TranslationUnit(line_number=1, source_text="こんにちは")]
        glossary = [GlossaryEntry(source="先輩", target="senpai", notes="Keep honorific.")]
        prompt = build_user_prompt(
            config=config,
            chunk=chunk,
            previous_context=[],
            glossary=glossary,
            notes="Keep the tone intimate.",
        )
        parsed = json.loads(prompt)
        self.assertEqual(parsed["current_chunk"][0]["line_number"], 1)
        self.assertIn("senpai", parsed["canon_list"][0])
        self.assertIn("new_characters", parsed["output_schema"])

    def test_pipe_delimited_glossary_is_supported(self) -> None:
        entries = parse_glossary_text("先輩 | senpai | Keep honorific")
        self.assertEqual(entries[0].source, "先輩")
        self.assertEqual(entries[0].target, "senpai")

    def test_markdown_export_contains_translation(self) -> None:
        output = entries_to_markdown(
            [
                TranslationEntry(
                    line_number=1,
                    source_text="こんにちは",
                    translation="Hello",
                )
            ]
        )
        self.assertIn("Translation: Hello", output)

    def test_markdown_export_appends_extraction_sections(self) -> None:
        output = entries_to_markdown(
            [
                TranslationEntry(
                    line_number=1,
                    source_text="ã“ã‚“ã«ã¡ã¯",
                    translation="Hello",
                )
            ],
            ExtractionSummary(
                new_characters=["å¤ªéƒŽ(ãŸã‚ã†) / Taro Yamada (male)"],
                new_locations=["Goblin Labyrinth"],
                new_terms=["Dungeon Core"],
            ),
        )
        self.assertIn("## New Characters", output)
        self.assertIn("Goblin Labyrinth", output)

    def test_plain_text_export_contains_only_translations(self) -> None:
        output = entries_to_plain_text(
            [
                TranslationEntry(line_number=1, source_text="a", translation="Hello"),
                TranslationEntry(line_number=2, source_text="", translation=""),
                TranslationEntry(line_number=3, source_text="b", translation="World"),
            ]
        )
        self.assertEqual(output, "Hello\n\nWorld")

    def test_timeout_becomes_model_response_error(self) -> None:
        client = OpenAICompatClient(
            provider="custom",
            api_base="http://localhost:11434/v1",
            api_key="ollama",
            model="gemma4",
            timeout_seconds=1,
        )

        with mock.patch(
            "fan_translation.client.request.urlopen",
            side_effect=error.URLError(socket.timeout("timed out")),
        ):
            with self.assertRaises(ModelResponseError) as exc_info:
                client.translate("system", "user", 0.2)

        self.assertIn("timed out", str(exc_info.exception))

    def test_translate_with_metadata_parses_usage(self) -> None:
        client = OpenAICompatClient(
            provider="custom",
            api_base="http://localhost:11434/v1",
            api_key="ollama",
            model="gemma4",
        )
        payload = {
            "choices": [
                {
                    "message": {
                        "content": "{\"translations\": [{\"line_number\": 1, \"translation\": \"Hello\"}]}"
                    }
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 6,
                "total_tokens": 16,
            },
        }

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(payload).encode("utf-8")

        with mock.patch(
            "fan_translation.client.request.urlopen",
            return_value=FakeResponse(),
        ):
            result = client.translate_with_metadata("system", "user", 0.2)

        self.assertEqual(result.prompt_tokens, 10)
        self.assertEqual(result.completion_tokens, 6)
        self.assertEqual(result.total_tokens, 16)

    def test_build_model_client_uses_openai_env_var(self) -> None:
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "secret-key"}, clear=False):
            project = ProjectConfig(
                provider="openai",
                model="gpt-4.1-mini",
                api_base="",
                api_key="",
                api_key_env="",
            )
            client = build_model_client(project)

        self.assertEqual(client.api_base, "https://api.openai.com/v1")
        self.assertEqual(client.api_key, "secret-key")

    def test_build_model_client_uses_gemini_env_var(self) -> None:
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "gemini-secret"}, clear=False):
            project = ProjectConfig(
                provider="gemini",
                model="gemini-2.5-flash",
                api_base="",
                api_key="",
                api_key_env="",
            )
            client = build_model_client(project)

        self.assertEqual(
            client.api_base,
            "https://generativelanguage.googleapis.com/v1beta/openai",
        )
        self.assertEqual(client.api_key, "gemini-secret")

    def test_gemini_api_base_rejects_embedded_key_query(self) -> None:
        project = ProjectConfig(
            provider="gemini",
            api_base="https://generativelanguage.googleapis.com/v1beta/openai?key=abc123",
            api_key="",
            api_key_env="GEMINI_API_KEY",
        )

        with self.assertRaises(ValueError) as exc_info:
            project.resolved_api_base()

        self.assertIn("must not include ?key=", str(exc_info.exception))

    def test_api_base_strips_chat_completions_suffix(self) -> None:
        project = ProjectConfig(
            provider="openai",
            api_base="https://api.openai.com/v1/chat/completions",
            api_key="secret",
        )

        self.assertEqual(project.resolved_api_base(), "https://api.openai.com/v1")

    def test_gemini_rejects_oauth_style_token(self) -> None:
        project = ProjectConfig(
            provider="gemini",
            api_base="https://generativelanguage.googleapis.com/v1beta/openai",
            api_key="AQ.some-access-token",
        )

        with self.assertRaises(ValueError) as exc_info:
            build_model_client(project)

        self.assertIn("looks like an OAuth or access token", str(exc_info.exception))

    def test_openai_insufficient_quota_error_is_human_friendly(self) -> None:
        client = OpenAICompatClient(
            provider="openai",
            api_base="https://api.openai.com/v1",
            api_key="sk-test",
            model="gpt-4.1-mini",
        )

        class FakeHttpError(error.HTTPError):
            def __init__(self):
                super().__init__(
                    url="https://api.openai.com/v1/chat/completions",
                    code=429,
                    msg="Too Many Requests",
                    hdrs=None,
                    fp=None,
                )

            def read(self):
                return (
                    b'{"error":{"message":"You exceeded your current quota, please check '
                    b'your plan and billing details.","type":"insufficient_quota",'
                    b'"param":null,"code":"insufficient_quota"}}'
                )

        with mock.patch(
            "fan_translation.client.request.urlopen",
            side_effect=FakeHttpError(),
        ):
            with self.assertRaises(ModelResponseError) as exc_info:
                client.translate("system", "user", 0.2)

        self.assertIn("OpenAI returned insufficient_quota", str(exc_info.exception))

    def test_gemini_requests_always_set_high_reasoning_effort(self) -> None:
        client = OpenAICompatClient(
            provider="gemini",
            api_base="https://generativelanguage.googleapis.com/v1beta/openai",
            api_key="gemini-key",
            model="gemini-3-flash-preview",
        )
        captured_payload = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b'{"choices":[{"message":{"content":"{}"}}],"usage":{}}'

        def fake_urlopen(req, timeout):
            del timeout
            captured_payload.update(json.loads(req.data.decode("utf-8")))
            return FakeResponse()

        with mock.patch("fan_translation.client.request.urlopen", side_effect=fake_urlopen):
            client.translate_with_metadata("system", "user", 0.2)

        self.assertEqual(captured_payload["reasoning_effort"], "high")

    def test_openai_gpt5_requests_set_high_reasoning_effort(self) -> None:
        client = OpenAICompatClient(
            provider="openai",
            api_base="https://api.openai.com/v1",
            api_key="sk-test",
            model="gpt-5.2",
        )
        captured_payload = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b'{"choices":[{"message":{"content":"{}"}}],"usage":{}}'

        def fake_urlopen(req, timeout):
            del timeout
            captured_payload.update(json.loads(req.data.decode("utf-8")))
            return FakeResponse()

        with mock.patch("fan_translation.client.request.urlopen", side_effect=fake_urlopen):
            client.translate_with_metadata("system", "user", 0.2)

        self.assertEqual(captured_payload["reasoning_effort"], "high")

    def test_openai_gpt41_requests_do_not_set_reasoning_effort(self) -> None:
        client = OpenAICompatClient(
            provider="openai",
            api_base="https://api.openai.com/v1",
            api_key="sk-test",
            model="gpt-4.1-mini",
        )
        captured_payload = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b'{"choices":[{"message":{"content":"{}"}}],"usage":{}}'

        def fake_urlopen(req, timeout):
            del timeout
            captured_payload.update(json.loads(req.data.decode("utf-8")))
            return FakeResponse()

        with mock.patch("fan_translation.client.request.urlopen", side_effect=fake_urlopen):
            client.translate_with_metadata("system", "user", 0.2)

        self.assertNotIn("reasoning_effort", captured_payload)

    def test_proofread_entries_uses_plain_text_completion(self) -> None:
        client = mock.Mock()
        client.complete_with_metadata.return_value = ModelTranslationResponse(
            content="Proofread output"
        )
        entries = [
            TranslationEntry(line_number=1, source_text="a", translation="Hello"),
            TranslationEntry(line_number=2, source_text="", translation=""),
            TranslationEntry(line_number=3, source_text="b", translation="World"),
        ]

        response = proofread_entries(ProjectConfig(), client, entries)

        self.assertEqual(response.content, "Proofread output")
        client.complete_with_metadata.assert_called_once()
        kwargs = client.complete_with_metadata.call_args.kwargs
        self.assertEqual(kwargs["user_prompt"], "Hello\n\nWorld")
        self.assertIsNone(kwargs["response_format"])

    def test_translation_metrics_can_be_accumulated(self) -> None:
        metrics = TranslationMetrics()
        first = ModelTranslationResponse(
            content="{}",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )
        second = ModelTranslationResponse(
            content="{}",
            prompt_tokens=8,
            completion_tokens=4,
            total_tokens=12,
        )

        metrics.prompt_tokens += first.prompt_tokens or 0
        metrics.completion_tokens += first.completion_tokens or 0
        metrics.total_tokens += first.total_tokens or 0
        metrics.prompt_tokens += second.prompt_tokens or 0
        metrics.completion_tokens += second.completion_tokens or 0
        metrics.total_tokens += second.total_tokens or 0

        self.assertEqual(metrics.prompt_tokens, 18)
        self.assertEqual(metrics.completion_tokens, 9)
        self.assertEqual(metrics.total_tokens, 27)

    def test_parser_recovers_translations_from_malformed_metadata(self) -> None:
        raw = (
            '{'
            '"translations": ['
            '{"line_number": 51, "translation": "Were you satisfied?"},'
            '{"line_number": 55, "translation": "He weakened."}'
            '],'
            '"new_characters": ['
            '{"broken": "value"'
        )

        parsed = _parse_translation_response(raw)

        self.assertEqual(len(parsed["translations"]), 2)
        self.assertEqual(parsed["translations"][0]["line_number"], 51)
        self.assertEqual(parsed["translations"][1]["translation"], "He weakened.")
        self.assertEqual(parsed["new_characters"], [])

    def test_parser_recovers_completed_items_from_truncated_array(self) -> None:
        raw = (
            '{ "translations": ['
            '{ "line_number": 1, "translation": "Chapter 226: Intersection" },'
            '{ "line_number": 3, "translation": "At night, in the mansion\'s private room." },'
            '{ "line_number": 5, "translation": "The air felt different from usual." },'
            '{ "line_number": 7, "translation": "'
        )

        parsed = _parse_translation_response(raw)

        self.assertEqual(len(parsed["translations"]), 3)
        self.assertEqual(parsed["translations"][0]["line_number"], 1)
        self.assertEqual(
            parsed["translations"][2]["translation"],
            "The air felt different from usual.",
        )

    def test_parser_keeps_extraction_metadata(self) -> None:
        raw = json.dumps(
            {
                "translations": [{"line_number": 1, "translation": "Hello"}],
                "new_characters": ["å¤ªéƒŽ(ãŸã‚ã†) / Taro Yamada (male)"],
                "new_locations": ["Goblin Labyrinth"],
                "new_terms": ["Dungeon Core"],
            }
        )

        parsed = _parse_translation_response(raw)

        self.assertEqual(parsed["translations"][0]["translation"], "Hello")
        self.assertEqual(
            parsed["new_characters"],
            ["å¤ªéƒŽ(ãŸã‚ã†) / Taro Yamada (male)"],
        )
        self.assertEqual(parsed["new_locations"], ["Goblin Labyrinth"])
        self.assertEqual(parsed["new_terms"], ["Dungeon Core"])


    def test_single_pass_translation_uses_one_translation_request(self) -> None:
        client = mock.Mock()
        client.translate_with_metadata.return_value = ModelTranslationResponse(
            content=json.dumps(
                {
                    "translations": [
                        {"line_number": 1, "translation": "One"},
                        {"line_number": 2, "translation": "Two"},
                        {"line_number": 3, "translation": "Three"},
                    ],
                    "new_characters": [],
                    "new_locations": [],
                    "new_terms": [],
                }
            )
        )
        project = ProjectConfig(chunk_size=1, single_pass_translation=True)

        run = translate_text_with_metrics(
            lines=["a", "b", "c"],
            project=project,
            client=client,
            glossary=[],
            notes="",
        )

        self.assertEqual(client.translate_with_metadata.call_count, 1)
        self.assertEqual(
            [entry.translation for entry in run.entries],
            ["One", "Two", "Three"],
        )

    def test_chunked_translation_uses_multiple_requests_when_single_pass_is_off(self) -> None:
        client = mock.Mock()
        client.translate_with_metadata.side_effect = [
            ModelTranslationResponse(
                content=json.dumps(
                    {
                        "translations": [{"line_number": 1, "translation": "One"}],
                        "new_characters": [],
                        "new_locations": [],
                        "new_terms": [],
                    }
                )
            ),
            ModelTranslationResponse(
                content=json.dumps(
                    {
                        "translations": [{"line_number": 2, "translation": "Two"}],
                        "new_characters": [],
                        "new_locations": [],
                        "new_terms": [],
                    }
                )
            ),
            ModelTranslationResponse(
                content=json.dumps(
                    {
                        "translations": [{"line_number": 3, "translation": "Three"}],
                        "new_characters": [],
                        "new_locations": [],
                        "new_terms": [],
                    }
                )
            ),
        ]
        project = ProjectConfig(chunk_size=1, single_pass_translation=False)

        run = translate_text_with_metrics(
            lines=["a", "b", "c"],
            project=project,
            client=client,
            glossary=[],
            notes="",
        )

        self.assertEqual(client.translate_with_metadata.call_count, 3)
        self.assertEqual(
            [entry.translation for entry in run.entries],
            ["One", "Two", "Three"],
        )


if __name__ == "__main__":
    unittest.main()
