import json
import unittest
from io import BytesIO
from unittest import mock

from fan_translation.config import ProjectConfig
from fan_translation.pipeline import (
    ExtractionSummary,
    TranslationEntry,
    TranslationMetrics,
    TranslationRun,
)
from fan_translation.server import TranslationWebApp


class TranslationServerTests(unittest.TestCase):
    def test_translate_can_skip_proofreading(self) -> None:
        app = TranslationWebApp(ProjectConfig(enable_proofreading=True))
        payload = json.dumps(
            {
                "source_text": "こんにちは",
                "enable_proofreading": False,
            }
        ).encode("utf-8")
        environ = {
            "CONTENT_LENGTH": str(len(payload)),
            "CONTENT_TYPE": "application/json",
            "wsgi.input": BytesIO(payload),
        }
        start_response_calls = []

        def start_response(status, headers):
            start_response_calls.append((status, headers))

        run = TranslationRun(
            entries=[
                TranslationEntry(
                    line_number=1,
                    source_text="こんにちは",
                    translation="Hello",
                )
            ],
            metrics=TranslationMetrics(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            extraction=ExtractionSummary(
                new_characters=["None"],
                new_locations=["None"],
                new_terms=["None"],
            ),
        )

        with mock.patch("fan_translation.server.build_model_client", return_value=mock.Mock()):
            with mock.patch("fan_translation.server.translate_text_with_metrics", return_value=run):
                with mock.patch("fan_translation.server.proofread_entries") as proofread_mock:
                    response_chunks = app._handle_translate(environ, start_response)

        self.assertEqual(start_response_calls[0][0], "200 OK")
        proofread_mock.assert_not_called()
        response = json.loads(b"".join(response_chunks).decode("utf-8"))
        self.assertFalse(response["enable_proofreading"])
        self.assertEqual(response["proofreading_preview"], "")
        self.assertEqual(response["proofreading_error"], "")


if __name__ == "__main__":
    unittest.main()
