from __future__ import annotations

import argparse
from pathlib import Path

from fan_translation.client import ModelResponseError, build_model_client
from fan_translation.config import ProjectConfig
from fan_translation.pipeline import translate_file, write_output
from fan_translation.runtime import build_llama_cpp_command
from fan_translation.server import run_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fantranslate",
        description="Fan translation helper backed by a Gemma model endpoint.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    translate = subparsers.add_parser("translate", help="Translate one script file.")
    translate.add_argument("--project", required=True, help="Path to the project config JSON.")
    translate.add_argument("--input", required=True, help="Path to the source text file.")
    translate.add_argument("--output", required=True, help="Path to the translated output.")
    translate.add_argument(
        "--format",
        default="markdown",
        choices=("markdown", "json"),
        help="Output format.",
    )

    batch = subparsers.add_parser("batch", help="Translate every .txt file in a folder.")
    batch.add_argument("--project", required=True, help="Path to the project config JSON.")
    batch.add_argument("--input-dir", required=True, help="Folder containing source .txt files.")
    batch.add_argument("--output-dir", required=True, help="Folder where outputs will be written.")
    batch.add_argument(
        "--format",
        default="markdown",
        choices=("markdown", "json"),
        help="Output format.",
    )

    ui = subparsers.add_parser("ui", help="Launch the local browser UI.")
    ui.add_argument("--project", required=True, help="Path to the project config JSON.")
    ui.add_argument("--host", default="127.0.0.1", help="Host to bind the UI server.")
    ui.add_argument("--port", type=int, default=8000, help="Port to bind the UI server.")

    command = subparsers.add_parser(
        "llama-cpp-command",
        help="Print the llama-server command for the configured GGUF runtime.",
    )
    command.add_argument("--project", required=True, help="Path to the project config JSON.")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        project = ProjectConfig.load(args.project)

        if args.command == "ui":
            run_server(project=project, host=args.host, port=args.port)
            return 0

        if args.command == "llama-cpp-command":
            print(build_llama_cpp_command(project))
            return 0

        client = build_model_client(project)

        if args.command == "translate":
            entries = translate_file(project, client, args.input)
            write_output(entries, args.output, args.format)
            print(f"Wrote translation to {Path(args.output).resolve()}")
            return 0

        input_dir = Path(args.input_dir).resolve()
        output_dir = Path(args.output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        translated = 0
        suffix = ".json" if args.format == "json" else ".md"

        for source_file in sorted(input_dir.glob("*.txt")):
            target_file = output_dir / f"{source_file.stem}{suffix}"
            entries = translate_file(project, client, source_file)
            write_output(entries, target_file, args.format)
            translated += 1
            print(f"Translated {source_file.name} -> {target_file.name}")

        print(f"Finished batch translation for {translated} file(s).")
        return 0
    except (FileNotFoundError, ValueError, ModelResponseError) as exc:
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
