# Yuki Fan Translator

Beta `0.0.001`

![Version](https://img.shields.io/badge/version-0.0.001-2f6fed)
![Status](https://img.shields.io/badge/status-beta-f59e0b)
![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![Docker Compose](https://img.shields.io/badge/docker-compose-2496ED?logo=docker&logoColor=white)
![Providers](https://img.shields.io/badge/providers-llama.cpp%20%7C%20OpenAI%20%7C%20Gemini-7c3aed)

Yuki Fan Translator is a lightweight browser-based fan translation workspace for Japanese-to-English script translation. It is built for fast excerpt testing, glossary-aware translation passes, proofreading previews, and export-ready output without leaving the browser.

It supports:

- local `llama.cpp`
- OpenAI / ChatGPT-compatible APIs
- Gemini's OpenAI-compatible endpoint
- other OpenAI-compatible providers

## Getting Started In 60 Seconds

If you just want to get the full stack running as fast as possible:

```powershell
docker compose up --build -d
docker compose ps
docker compose logs -f llama
```

Then open:

- UI: `http://127.0.0.1:8000`
- llama.cpp: `http://127.0.0.1:8080`

What happens automatically:

1. the model prep service checks `./models`
2. if the GGUF file is missing, it downloads it
3. `llama.cpp` starts and loads the model
4. the UI starts after `llama` becomes healthy

## Feature Checklist

- [x] Browser UI for excerpt translation
- [x] Local `llama.cpp` support
- [x] OpenAI / ChatGPT API support
- [x] Gemini API support
- [x] Custom OpenAI-compatible endpoint support
- [x] Glossary-aware translation requests
- [x] Extraction preview for new characters, locations, and terms
- [x] Proofreading preview
- [x] Markdown export
- [x] JSON export
- [x] Docker Compose stack with model prep, `llama.cpp`, and UI
- [x] Runtime prompt injection through env vars or secret files

## Screenshot

UI preview section for GitHub:

<img width="1477" height="802" alt="image" src="https://github.com/user-attachments/assets/8c1ad2f7-c660-4a08-85f8-30fb90e851ab" />
<img width="1505" height="755" alt="image" src="https://github.com/user-attachments/assets/775ce69a-4772-4ba4-badd-f4b59a5f0eb0" />


## What It Does

- translates pasted script excerpts line by line
- preserves blank lines and structure for easier review
- injects glossary terms, style guidance, and notes into the translation request
- shows export, extraction, and proofreading previews in the UI
- exports Markdown or JSON
- supports Docker for running the UI and local `llama.cpp` stack together

## Current Stack

- app name: `Yuki Fan Translator`
- version: `0.0.001`
- version format: `<feature>.<bug>.<release>`
- default local model file: `Gemma4_E2B_Abliterated_Baked_HF_Ready.i1-Q5_K_M.gguf`

## Features

- browser UI for quick translation iteration
- glossary input in JSON or `source | target | notes` format
- extraction preview for newly detected characters, locations, and terms
- proofreading preview after translation
- cloud provider support for OpenAI and Gemini
- Docker Compose flow with:
  - model download step
  - `llama.cpp` service
  - UI service
- optional prompt injection through secret files or environment variables

## Project Layout

```text
config/
  glossary.example.json
  project.example.json
  project.gemini.example.json
  project.openai.example.json
  project.json
data/
  input/
src/
  fan_translation/
    cli.py
    client.py
    config.py
    pipeline.py
    prompts.py
    server.py
    web/
tests/
README.md
Dockerfile
compose.yaml
pyproject.toml
```

## Quick Start

### Local Python Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
Copy-Item config\project.example.json config\project.json
fantranslate ui --project config\project.json --host 127.0.0.1 --port 8000
```

Then open `http://127.0.0.1:8000`.

### One-Off Translation Command

```powershell
fantranslate translate --project config\project.json --input data\input\sample_script.txt --output output\sample_script.md
```

## Docker

Docker Compose is the main recommended container flow for this repo.

It starts three services:

- `yuki_translator_model_prep`
- `yuki_translator_llama`
- `yuki_translator_ui`

It also uses:

- Compose project name: `yuki_translator`
- UI image name: `fantralslator`

### Start The Full Stack

```powershell
docker compose up --build -d
```

### Stop The Stack

```powershell
docker compose down
```

### What Compose Does

1. `model_prep` checks whether the model file already exists in `./models`
2. if the file is missing or empty, it downloads it from Hugging Face
3. `llama` starts and loads the local file from `/models/...`
4. `ui` starts only after `llama` becomes healthy

### Ports

- `8000` for the browser UI
- `8080` for `llama.cpp`

### Model File Used By Docker

The stack uses this file:

- `models/Gemma4_E2B_Abliterated_Baked_HF_Ready.i1-Q5_K_M.gguf`

If it already exists and is non-empty, Docker will not re-download it.

### Useful Docker Commands

```powershell
docker compose ps
docker compose logs -f llama
docker compose logs llama --tail 200
docker compose logs -f app
```

## Local llama.cpp

If you do not want to use Docker Compose for the model server, you can run `llama-server` manually.

Official sources:

- GitHub: `https://github.com/ggml-org/llama.cpp`
- Releases: `https://github.com/ggml-org/llama.cpp/releases`

Model source:

- Hugging Face repo: `https://huggingface.co/mradermacher/Gemma4_E2B_Abliterated_Baked_HF_Ready-i1-GGUF`
- model file: `Gemma4_E2B_Abliterated_Baked_HF_Ready.i1-Q5_K_M.gguf`

Example local launch:

```powershell
llama-server -m "C:\models\Gemma4_E2B_Abliterated_Baked_HF_Ready.i1-Q5_K_M.gguf" -c 4096 --host 127.0.0.1 --port 8080
```

## GPU Offload

The Compose stack is GPU-offload aware for `llama.cpp`.

You can control it with a root `.env` file:

```text
LLAMA_GPU_LAYERS=20
LLAMA_CONTEXT_SIZE=4096
LLAMA_IMAGE=ghcr.io/ggml-org/llama.cpp:server
LLAMA_EXTRA_ARGS=
```

Notes:

- `LLAMA_GPU_LAYERS` maps to `-ngl`
- default is `0`, which is CPU-safe
- actual acceleration depends on a compatible GPU-enabled `llama.cpp` image and Docker runtime
- on unsupported Docker GPU setups, the stack can still run on CPU

## Provider Support

### Local llama.cpp

- provider: `llama.cpp`
- default API shape: OpenAI-compatible `/chat/completions`

### OpenAI

- provider: `openai`
- default base: `https://api.openai.com/v1`

Example:

```powershell
$env:OPENAI_API_KEY="your-openai-key"
fantranslate translate --project config\project.openai.example.json --input data\input\sample_script.txt --output output\sample_script-openai.md
```

### Gemini

- provider: `gemini`
- default base: `https://generativelanguage.googleapis.com/v1beta/openai`

Example:

```powershell
$env:GEMINI_API_KEY="your-gemini-key"
fantranslate translate --project config\project.gemini.example.json --input data\input\sample_script.txt --output output\sample_script-gemini.md
```

Important:

- do not append `?key=...` to the Gemini `api_base`
- provide credentials only once through the API key field or environment variable

### Custom OpenAI-Compatible Endpoints

You can also use:

- Ollama-compatible endpoints
- self-hosted proxies
- other OpenAI-style model gateways

## Prompt Privacy

If a prompt is committed into the repo, baked into the image, or sent to the browser, it is discoverable.

This repo supports runtime prompt injection instead.

Supported environment variables:

- `FAN_TRANSLATION_SYSTEM_PROMPT`
- `FAN_TRANSLATION_SYSTEM_PROMPT_FILE`
- `FAN_TRANSLATION_PROOFREADING_PROMPT`
- `FAN_TRANSLATION_PROOFREADING_PROMPT_FILE`

Recommended secret-file setup:

```text
FAN_TRANSLATION_SYSTEM_PROMPT_FILE=/run/secrets/translation_prompt.txt
FAN_TRANSLATION_PROOFREADING_PROMPT_FILE=/run/secrets/proofreading_prompt.txt
```

Then place the real prompt text in:

- `secrets/translation_prompt.txt`
- `secrets/proofreading_prompt.txt`

If no private prompt is injected, the app falls back to a generic built-in prompt.

## UI Overview

The browser UI includes:

- source text input
- provider switcher
- model selector
- API base and API key fields
- GGUF / HF repo / HF file settings
- translation tuning controls
- glossary and notes fields
- export preview
- extraction preview
- proofreading preview

## Output

### Markdown

Designed for human review and editing.

Example shape:

```markdown
# Translation Output

## Line 1
Source: ...
Translation: ...
```

### JSON

Designed for structured processing and reinsertion pipelines.

## Recommended Workflow

1. Paste an excerpt into the UI.
2. Choose your provider and model.
3. Add glossary terms and style notes.
4. Translate.
5. Review export, extraction, and proofreading previews.
6. Export Markdown or JSON.
7. Update glossary entries as your canon solidifies.

## Troubleshooting

### Docker UI Starts But Translation Fails

Check:

- `docker compose ps`
- `docker compose logs -f llama`

If `llama` is still loading the model, wait until it becomes healthy.

### Model Re-Downloads Unexpectedly

The downloader skips only when the target file already exists and is non-empty.

Expected file:

- `models/Gemma4_E2B_Abliterated_Baked_HF_Ready.i1-Q5_K_M.gguf`

### OpenAI Or Gemini Returns Auth Errors

Common causes:

- wrong API key
- Gemini `api_base` contains `?key=...`
- using an OAuth token instead of a Gemini API key
- provider mismatch between UI selection and endpoint

### Requests Feel Slow

For local models, try:

- lower `chunk_size`
- lower `context_window`
- smaller context size if appropriate
- GPU layer offload if supported

For cloud models, try:

- smaller chunks
- shorter context windows
- faster model variants

## Development

Run tests:

```powershell
$env:PYTHONPATH='src'
python -m unittest discover -s tests
```

Compile check:

```powershell
python -m compileall src tests
```

## License And Usage Note

This repository is a fan translation workflow tool. You are responsible for how you use it, what content you process, and whether your usage complies with the policies and rights associated with the underlying models and source material.
