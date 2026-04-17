const form = document.getElementById("translate-form");
const statusEl = document.getElementById("status");
const preview = document.getElementById("preview");
const extractionPreview = document.getElementById("extraction-preview");
const proofreadingPreview = document.getElementById("proofreading-preview");
const downloadMarkdown = document.getElementById("download-markdown");
const downloadJson = document.getElementById("download-json");
const launchCommand = document.getElementById("launch-command");
const translationTimer = document.getElementById("translation-timer");
const tokensPerSecond = document.getElementById("tokens-per-second");
const tokenCount = document.getElementById("token-count");

let latestMarkdown = "";
let latestJson = "";
let loadedProject = null;

const providerDefaults = {
  openai: {
    model: "gpt-4.1-mini",
    runtime: "openai",
    apiBase: "https://api.openai.com/v1",
    apiKeyEnv: "OPENAI_API_KEY",
    temperature: 0.2,
    chunkSize: 8,
    contextWindow: 2,
    requestTimeoutSeconds: 600,
    models: [
      { value: "gpt-5.2", label: "GPT-5.2" },
      { value: "gpt-5-mini", label: "GPT-5 mini" },
      { value: "gpt-5-nano", label: "GPT-5 nano" },
      { value: "gpt-4.1", label: "GPT-4.1" },
      { value: "gpt-4.1-mini", label: "GPT-4.1 mini" },
      { value: "__custom__", label: "Custom model..." },
    ],
  },
  gemini: {
    model: "gemini-3-flash-preview",
    runtime: "gemini",
    apiBase: "https://generativelanguage.googleapis.com/v1beta/openai",
    apiKeyEnv: "GEMINI_API_KEY",
    temperature: 0.2,
    chunkSize: 8,
    contextWindow: 2,
    requestTimeoutSeconds: 600,
    models: [
      { value: "gemini-2.5-flash", label: "Gemini 2.5 Flash" },
      { value: "gemini-2.5-flash-lite", label: "Gemini 2.5 Flash-Lite" },
      { value: "gemini-2.5-pro", label: "Gemini 2.5 Pro" },
      { value: "gemini-2.0-flash", label: "Gemini 2.0 Flash" },
      { value: "gemini-3-pro-preview", label: "Standard: Gemini 3 Pro" },
      { value: "gemini-3-flash-preview", label: "Standard: Gemini 3 Flash" },
      {
        value: "gemini-2.5-pro-reasoning",
        requestValue: "gemini-2.5-pro",
        label: "Reasoning: Gemini 2.5 Pro (Best for Logic)",
      },
      { value: "__custom__", label: "Custom model..." },
    ],
  },
  custom: {
    model: "",
    runtime: "openai-compatible",
    apiBase: "",
    apiKeyEnv: "",
    temperature: 0.2,
    chunkSize: 8,
    contextWindow: 2,
    requestTimeoutSeconds: 600,
    models: [],
  },
};

const fields = {
  provider: document.getElementById("provider"),
  modelSelect: document.getElementById("model-select"),
  model: document.getElementById("model"),
  runtime: document.getElementById("runtime"),
  apiBase: document.getElementById("api-base"),
  apiKey: document.getElementById("api-key"),
  ggufPath: document.getElementById("gguf-path"),
  hfRepo: document.getElementById("hf-repo"),
  hfFile: document.getElementById("hf-file"),
  sourceLanguage: document.getElementById("source-language"),
  targetLanguage: document.getElementById("target-language"),
  temperature: document.getElementById("temperature"),
  chunkSize: document.getElementById("chunk-size"),
  contextWindow: document.getElementById("context-window"),
  requestTimeoutSeconds: document.getElementById("request-timeout-seconds"),
  llamaContextSize: document.getElementById("llama-context-size"),
  style: document.getElementById("style"),
  glossaryText: document.getElementById("glossary-text"),
  notes: document.getElementById("notes"),
  sourceText: document.getElementById("source-text"),
};

boot();

async function boot() {
  try {
    const response = await fetch("/api/project");
    const data = await response.json();
    applyProjectDefaults(data.project);
    statusEl.textContent = "Project defaults loaded. Paste text and translate.";
  } catch (error) {
    statusEl.textContent = `Could not load project defaults: ${error.message}`;
  }
}

function applyProjectDefaults(project) {
  loadedProject = project;
  document.getElementById("project-model").textContent = project.model;
  fields.provider.value = project.provider;
  applyModelFieldState(project.provider, project.model);
  fields.runtime.value = project.runtime;
  fields.apiBase.value = project.api_base;
  fields.apiKey.value = project.api_key;
  fields.ggufPath.value = project.gguf_path;
  fields.hfRepo.value = project.hf_repo;
  fields.hfFile.value = project.hf_file;
  fields.sourceLanguage.value = project.source_language;
  fields.targetLanguage.value = project.target_language;
  fields.temperature.value = project.temperature;
  fields.chunkSize.value = project.chunk_size;
  fields.contextWindow.value = project.context_window;
  fields.requestTimeoutSeconds.value = project.request_timeout_seconds;
  fields.llamaContextSize.value = project.llama_context_size;
  fields.style.value = project.style;
  fields.glossaryText.value = project.glossary_text;
  fields.notes.value = project.notes;
  launchCommand.textContent = project.launch_command;
  updateProviderHints();
  syncProviderUi();
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const sourceText = fields.sourceText.value.trimEnd();
  if (!sourceText.trim()) {
    statusEl.textContent = "Paste some source text first.";
    return;
  }

  const model = getEffectiveModel();
  if (!model) {
    statusEl.textContent = "Choose a model or enter a custom model ID first.";
    return;
  }

  toggleBusy(true);
  statusEl.textContent = "Translating...";
  clearPreviews();
  translationTimer.textContent = "Running...";
  tokensPerSecond.textContent = "Running...";
  tokenCount.textContent = "Running...";

  try {
    const payload = {
      source_text: sourceText,
      provider: fields.provider.value,
      model,
      api_base: fields.apiBase.value,
      api_key: fields.apiKey.value,
      source_language: fields.sourceLanguage.value,
      target_language: fields.targetLanguage.value,
      temperature: Number(fields.temperature.value),
      chunk_size: Number(fields.chunkSize.value),
      context_window: Number(fields.contextWindow.value),
      request_timeout_seconds: Number(fields.requestTimeoutSeconds.value),
      style: fields.style.value,
      glossary_text: fields.glossaryText.value,
      notes: fields.notes.value,
    };

    const response = await fetch("/api/translate", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "Translation failed.");
    }

    latestMarkdown = data.markdown;
    latestJson = data.json_output;
    preview.textContent = latestMarkdown;
    renderExtractionPreview(data.extraction);
    renderProofreadingPreview(
      data.proofreading_preview ||
      data.proofreading_error ||
      "Proofreading preview unavailable.",
    );
    downloadMarkdown.disabled = false;
    downloadJson.disabled = false;
    const elapsedLabel = formatElapsedTime(data.elapsed_seconds);
    translationTimer.textContent = elapsedLabel;
    tokensPerSecond.textContent = formatTokensPerSecond(data.tokens_per_second);
    tokenCount.textContent = formatTokenCount(data.total_tokens);
    if (data.proofreading_error) {
      statusEl.textContent =
        `Translated ${data.entries.length} line(s) in ${elapsedLabel}. Proofreading preview failed: ${data.proofreading_error}`;
    } else {
      statusEl.textContent =
        `Translated and proofread ${data.entries.length} line(s) in ${elapsedLabel}.`;
    }
  } catch (error) {
    translationTimer.textContent = "No completed translation.";
    tokensPerSecond.textContent = "No completed translation.";
    tokenCount.textContent = "No completed translation.";
    statusEl.textContent = error.message;
  } finally {
    toggleBusy(false);
  }
});

for (const field of [
  fields.provider,
  fields.apiBase,
  fields.ggufPath,
  fields.hfRepo,
  fields.hfFile,
  fields.llamaContextSize,
]) {
  field.addEventListener("input", renderLaunchCommand);
}

fields.provider.addEventListener("change", () => {
  applyProviderDefaults();
  updateProviderHints();
  syncProviderUi();
  const providerLabel =
    fields.provider.options[fields.provider.selectedIndex]?.text || fields.provider.value;
  statusEl.textContent = `${providerLabel} defaults loaded. Add the API key and translate.`;
});

fields.modelSelect.addEventListener("change", () => {
  syncModelInputVisibility();
  syncModelBadge();
});

fields.model.addEventListener("input", () => {
  syncModelBadge();
});

downloadMarkdown.addEventListener("click", () => {
  saveBlob("translation-output.md", latestMarkdown, "text/markdown;charset=utf-8");
});

downloadJson.addEventListener("click", () => {
  saveBlob("translation-output.json", latestJson, "application/json;charset=utf-8");
});

function toggleBusy(isBusy) {
  document.getElementById("translate-button").disabled = isBusy;
}

function renderLaunchCommand() {
  if (fields.provider.value !== "llama.cpp") {
    launchCommand.textContent =
      "llama.cpp launch command is only available for the local llama.cpp provider.";
    return;
  }

  const baseUrl = fields.apiBase.value || "http://127.0.0.1:8080/v1";
  let host = "127.0.0.1";
  let port = "8080";

  try {
    const url = new URL(baseUrl, window.location.origin);
    host = url.hostname || host;
    port = url.port || port;
  } catch (error) {
    launchCommand.textContent = "Set a valid API base URL to render the llama-server command.";
    return;
  }

  const contextSize = Number(fields.llamaContextSize.value) || 8192;
  const ggufPath = fields.ggufPath.value.trim();

  if (ggufPath) {
    launchCommand.textContent =
      `llama-server -m "${ggufPath}" -c ${contextSize} --host ${host} --port ${port}`;
    return;
  }

  const repo = fields.hfRepo.value.trim() || "<set-hf-repo>";
  const file = fields.hfFile.value.trim() || "<choose-gguf-file>.gguf";
  launchCommand.textContent =
    `llama-server -hfr "${repo}" -hff "${file}" -c ${contextSize} --host ${host} --port ${port}`;
}

function applyProviderDefaults() {
  const provider = fields.provider.value;
  const defaults = getProviderDefaults(provider);
  applyModelFieldState(provider, defaults.model);
  fields.runtime.value = defaults.runtime;
  fields.apiBase.value = defaults.apiBase;
  fields.apiKey.value = "";
  fields.temperature.value = defaults.temperature;
  fields.chunkSize.value = defaults.chunkSize;
  fields.contextWindow.value = defaults.contextWindow;
  fields.requestTimeoutSeconds.value = defaults.requestTimeoutSeconds;
}

function getProviderDefaults(provider) {
  if (provider === "llama.cpp") {
    const projectIsLocal = loadedProject?.provider === "llama.cpp";
    return {
      model: projectIsLocal
        ? loadedProject.model
        : "Gemma4_E2B_Abliterated_Baked_HF_Ready",
      runtime: projectIsLocal ? loadedProject.runtime : "llama.cpp",
      apiBase: projectIsLocal
        ? loadedProject.api_base
        : "http://127.0.0.1:8080/v1",
      apiKeyEnv: projectIsLocal ? loadedProject.api_key_env : "",
      temperature: projectIsLocal ? loadedProject.temperature : 0.2,
      chunkSize: projectIsLocal ? loadedProject.chunk_size : 8,
      contextWindow: projectIsLocal ? loadedProject.context_window : 2,
      requestTimeoutSeconds: projectIsLocal
        ? loadedProject.request_timeout_seconds
        : 300,
      models: [],
    };
  }

  return providerDefaults[provider] || {
    model: fields.model.value,
    runtime: "openai-compatible",
    apiBase: fields.apiBase.value,
    apiKeyEnv: "",
    temperature: Number(fields.temperature.value) || 0.2,
    chunkSize: Number(fields.chunkSize.value) || 8,
    contextWindow: Number(fields.contextWindow.value) || 2,
    requestTimeoutSeconds: Number(fields.requestTimeoutSeconds.value) || 600,
    models: [],
  };
}

function updateProviderHints() {
  const provider = fields.provider.value;
  const defaults = getProviderDefaults(provider);
  fields.apiBase.placeholder =
    defaults.apiBase || "Enter the base URL for your OpenAI-compatible API.";
  if (defaults.apiKeyEnv) {
    fields.apiKey.placeholder =
      `Leave blank to use ${defaults.apiKeyEnv} on the server.`;
    return;
  }
  fields.apiKey.placeholder =
    "Leave blank to use the configured project default on the server.";
}

function syncProviderUi() {
  const isLocalProvider = fields.provider.value === "llama.cpp";
  const usesPresetModels = providerUsesModelDropdown(fields.provider.value);
  for (const field of [
    fields.ggufPath,
    fields.hfRepo,
    fields.hfFile,
    fields.llamaContextSize,
  ]) {
    field.disabled = !isLocalProvider;
  }
  fields.modelSelect.disabled = !usesPresetModels;
  syncModelInputVisibility();
  renderLaunchCommand();
}

function providerUsesModelDropdown(provider) {
  return provider === "openai" || provider === "gemini";
}

function applyModelFieldState(provider, modelValue) {
  const defaults = getProviderDefaults(provider);
  const supportsDropdown = providerUsesModelDropdown(provider);
  const options = defaults.models || [];

  fields.modelSelect.innerHTML = "";

  if (!supportsDropdown) {
    fields.modelSelect.hidden = true;
    fields.model.hidden = false;
    fields.model.value = modelValue || defaults.model || "";
    syncModelBadge();
    return;
  }

  for (const option of options) {
    const element = document.createElement("option");
    element.value = option.value;
    element.textContent = option.label;
    fields.modelSelect.appendChild(element);
  }

  const matchingOption = options.find(
    (option) => (option.requestValue || option.value) === modelValue,
  );
  if (matchingOption) {
    fields.modelSelect.value = matchingOption.value;
    fields.model.value = matchingOption.requestValue || matchingOption.value;
  } else {
    fields.modelSelect.value = "__custom__";
    fields.model.value = modelValue || defaults.model || "";
  }

  fields.modelSelect.hidden = false;
  syncModelInputVisibility();
  syncModelBadge();
}

function syncModelInputVisibility() {
  const provider = fields.provider.value;
  const supportsDropdown = providerUsesModelDropdown(provider);
  if (!supportsDropdown) {
    fields.model.hidden = false;
    fields.modelSelect.hidden = true;
    return;
  }

  fields.modelSelect.hidden = false;
  const isCustomModel = fields.modelSelect.value === "__custom__";
  fields.model.hidden = !isCustomModel;
  if (isCustomModel) {
    fields.model.placeholder = "Enter a custom model ID.";
    syncModelBadge();
    return;
  }
  const selectedOption = getSelectedModelOption();
  fields.model.value = selectedOption?.requestValue || fields.modelSelect.value;
  syncModelBadge();
}

function getEffectiveModel() {
  if (providerUsesModelDropdown(fields.provider.value)) {
    if (fields.modelSelect.value === "__custom__") {
      return fields.model.value.trim();
    }
    const selectedOption = getSelectedModelOption();
    return selectedOption?.requestValue || fields.modelSelect.value;
  }
  return fields.model.value.trim();
}

function getSelectedModelOption() {
  const provider = fields.provider.value;
  const defaults = getProviderDefaults(provider);
  return (defaults.models || []).find((option) => option.value === fields.modelSelect.value);
}

function syncModelBadge() {
  document.getElementById("project-model").textContent = getEffectiveModel() || "custom";
}

function clearPreviews() {
  latestMarkdown = "";
  latestJson = "";
  preview.textContent = "Generating fresh export preview...";
  extractionPreview.classList.remove("empty");
  extractionPreview.innerHTML =
    '<p class="proofreading-loading">Extracting characters, locations, and terms...</p>';
  proofreadingPreview.classList.remove("empty");
  proofreadingPreview.innerHTML =
    '<p class="proofreading-loading">Generating fresh proofreading preview...</p>';
  downloadMarkdown.disabled = true;
  downloadJson.disabled = true;
}

function renderProofreadingPreview(content) {
  const text = String(content || "").trim();
  proofreadingPreview.classList.remove("empty");

  if (!text) {
    proofreadingPreview.classList.add("empty");
    proofreadingPreview.innerHTML = "<p>No proofreading preview yet.</p>";
    return;
  }

  const parsed = parseProofreadingOutput(text);
  if (!parsed) {
    proofreadingPreview.innerHTML = `
      <pre class="proofreading-text">${escapeHtml(text)}</pre>
    `;
    return;
  }

  const tableHead = parsed.headers
    .map((header) => `<th>${escapeHtml(header)}</th>`)
    .join("");
  const tableRows = parsed.rows
    .map((row) => {
      const cells = row
        .map((cell) => `<td>${formatProofreadingCell(cell)}</td>`)
        .join("");
      return `<tr>${cells}</tr>`;
    })
    .join("");

  const correctedBlock = parsed.remainder.trim()
    ? `
      <section class="proofreading-corrected-block">
        <div class="proofreading-subhead">Full Corrected Version</div>
        <pre class="proofreading-text">${escapeHtml(parsed.remainder.trim())}</pre>
      </section>
    `
    : "";

  proofreadingPreview.innerHTML = `
    <div class="proofreading-table-wrap">
      <table class="proofreading-table">
        <thead>
          <tr>${tableHead}</tr>
        </thead>
        <tbody>
          ${tableRows}
        </tbody>
      </table>
    </div>
    ${correctedBlock}
  `;
}

function renderExtractionPreview(extraction) {
  extractionPreview.classList.remove("empty");
  if (!extraction) {
    extractionPreview.classList.add("empty");
    extractionPreview.innerHTML = "<p>No extraction preview yet.</p>";
    return;
  }

  extractionPreview.innerHTML = `
    ${renderExtractionSection("New Characters", extraction.new_characters)}
    ${renderExtractionSection("New Locations", extraction.new_locations)}
    ${renderExtractionSection("New Terms", extraction.new_terms)}
  `;
}

function renderExtractionSection(title, items) {
  const normalizedItems = Array.isArray(items) && items.length ? items : ["None"];
  const body =
    normalizedItems.length === 1 && normalizedItems[0] === "None"
      ? '<p class="extraction-empty">None</p>'
      : `
        <ul class="extraction-list">
          ${normalizedItems.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
        </ul>
      `;

  return `
    <section class="extraction-section">
      <div class="extraction-subhead">${escapeHtml(title)}</div>
      ${body}
    </section>
  `;
}

function parseProofreadingOutput(text) {
  const lines = text.split(/\r?\n/);
  if (lines.length < 2) {
    return null;
  }

  if (!looksLikeMarkdownTableRow(lines[0]) || !looksLikeMarkdownSeparator(lines[1])) {
    return null;
  }

  const tableLines = [lines[0]];
  let index = 2;
  for (; index < lines.length; index += 1) {
    const line = lines[index];
    if (!looksLikeMarkdownTableRow(line)) {
      break;
    }
    tableLines.push(line);
  }

  const headers = splitMarkdownTableRow(tableLines[0]);
  const rows = tableLines.slice(1).map(splitMarkdownTableRow);
  const remainder = lines.slice(index).join("\n");

  if (!headers.length || !rows.length) {
    return null;
  }

  return { headers, rows, remainder };
}

function looksLikeMarkdownTableRow(line) {
  const trimmed = line.trim();
  return trimmed.startsWith("|") && trimmed.endsWith("|");
}

function looksLikeMarkdownSeparator(line) {
  const trimmed = line.trim();
  return /^\|[\s:\-|]+\|$/.test(trimmed);
}

function splitMarkdownTableRow(line) {
  return line
    .trim()
    .slice(1, -1)
    .split("|")
    .map((cell) => cell.trim());
}

function formatProofreadingCell(text) {
  return escapeHtml(text).replaceAll("\n", "<br>");
}

function formatElapsedTime(elapsedSeconds) {
  const seconds = Number(elapsedSeconds);
  if (!Number.isFinite(seconds) || seconds < 0) {
    return "Unknown";
  }
  if (seconds < 1) {
    return `${Math.round(seconds * 1000)} ms`;
  }
  return `${seconds.toFixed(2)} s`;
}

function formatTokensPerSecond(value) {
  const rate = Number(value);
  if (!Number.isFinite(rate) || rate <= 0) {
    return "Unavailable";
  }
  return `${rate.toFixed(2)} tok/s`;
}

function formatTokenCount(value) {
  const total = Number(value);
  if (!Number.isFinite(total) || total <= 0) {
    return "Unavailable";
  }
  return `${Math.round(total)} tok`;
}

function saveBlob(filename, content, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
