from __future__ import annotations

from urllib.parse import urlparse

from fan_translation.config import ProjectConfig


def build_llama_cpp_command(project: ProjectConfig) -> str:
    if project.provider != "llama.cpp":
        return "llama.cpp launch command is only available for the local llama.cpp provider."

    parsed = urlparse(project.resolved_api_base())
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8080
    context_size = max(512, project.llama_context_size)

    if project.gguf_path is not None:
        return (
            f'llama-server -m "{project.gguf_path}" '
            f"-c {context_size} --host {host} --port {port}"
        )

    hf_repo = project.hf_repo.strip() or "<set-hf-repo>"
    hf_file = project.hf_file.strip()
    if not hf_file:
        return (
            f'llama-server -hf "{hf_repo}" '
            f"-c {context_size} --host {host} --port {port}"
        )
    return (
        f'llama-server -hfr "{hf_repo}" -hff "{hf_file}" '
        f"-c {context_size} --host {host} --port {port}"
    )
