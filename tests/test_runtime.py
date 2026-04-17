import unittest
from pathlib import Path

from fan_translation.config import ProjectConfig
from fan_translation.runtime import build_llama_cpp_command


class RuntimeTests(unittest.TestCase):
    def test_llama_cpp_command_uses_hf_repo_when_no_local_file(self) -> None:
        project = ProjectConfig(
            hf_repo="mradermacher/Gemma4_E2B_Abliterated_Baked_HF_Ready-i1-GGUF",
            hf_file="chosen-quant.gguf",
        )
        command = build_llama_cpp_command(project)
        self.assertIn(
            '-hfr "mradermacher/Gemma4_E2B_Abliterated_Baked_HF_Ready-i1-GGUF"',
            command,
        )
        self.assertIn('-hff "chosen-quant.gguf"', command)

    def test_llama_cpp_command_prefers_local_file_when_present(self) -> None:
        project = ProjectConfig(gguf_path=Path("models/test.gguf"))
        command = build_llama_cpp_command(project)
        self.assertIn('-m "models\\test.gguf"', command)
        self.assertNotIn("-hfr", command)

    def test_llama_cpp_command_is_not_rendered_for_cloud_providers(self) -> None:
        project = ProjectConfig(provider="openai", api_base="https://api.openai.com/v1")
        command = build_llama_cpp_command(project)
        self.assertIn("only available for the local llama.cpp provider", command)
