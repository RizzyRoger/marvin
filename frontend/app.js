const ICONS = {
  chat: "C",
  daily_planning: "P",
  web_search: "S",
  obsidian: "O",
  python_runner: "Y",
  voice_lock: "V",
};

const BOARD_DIRECTIONS = {
  "gpp-head": {
    title: "Hello, I'm Marvin.",
    body: "Press Start Voice and speak, or type a message below.",
    hint: "Configure Voice Lock in Settings → Voice Lock.",
    send: "Send",
    voiceIdle: "Start Voice",
    functions: "Functions used",
    placeholder: "Type a message…",
    ticker: "",
    hatch: "",
  },
  "chest-plate": {
    title: "Don't talk to me about life",
    body: "Hello. I am Marvin.",
    hint: "Start Voice if you must.",
    send: "Send",
    voiceIdle: "Start Voice",
    functions: "Functions used",
    placeholder: "Type a message…",
    ticker: "",
    hatch: "",
  },
  "life-ticker": {
    title: "Marvin",
    body: "Speak or transmit. I will compute a reply I already resent.",
    hint: "Configure Voice Lock in Settings if other people talk.",
    send: "Transmit",
    voiceIdle: "Start Voice",
    functions: "Functions used",
    placeholder: "Transmit…",
    ticker: "Don't talk to me about life",
    hatch: "Transmit",
  },
  "empty-planet": {
    title: "I think you ought to know I'm feeling very depressed.",
    body: "",
    hint: "",
    send: "Send",
    voiceIdle: "Voice",
    functions: "Functions used",
    placeholder: "…",
    ticker: "",
    hatch: "",
  },
};

const STATUS_LABELS = {
  idle: "Ready",
  listening: "Listening…",
  processing: "Processing…",
  speaking: "Speaking…",
  error: "Error",
};

let ws = null;
let modelsReady = false;
let voiceActive = false;
let voiceEnrolled = false;
let functions = [];
let activeFunction = "chat";
let usedFunctions = new Set();
let stickyTools = new Set();
let activeTools = new Set();
let enrollPhrases = [];
let enrollPending = 0;
let enrollRequired = 3;
let providerState = {
  providers: [],
  catalog: [],
  selected_provider: "local",
  selected_model: "qwen3-4b-instruct",
  network_available: true,
  last_cloud_provider: null,
  focusProvider: null,
};

const els = {
  functionsList: document.getElementById("functions-list"),
  chatMessages: document.getElementById("chat-messages"),
  messageInput: document.getElementById("message-input"),
  sendBtn: document.getElementById("send-btn"),
  voiceBtn: document.getElementById("voice-btn"),
  clearBtn: document.getElementById("clear-btn"),
  modelStatus: document.getElementById("model-status"),
  voiceLockPill: document.getElementById("voice-lock-pill"),
  activeLabel: document.getElementById("active-function-label"),
  voiceBadge: document.getElementById("voice-badge"),
  enrollPanel: document.getElementById("enroll-panel"),
  enrollInstructions: document.getElementById("enroll-instructions"),
  enrollPhrases: document.getElementById("enroll-phrases"),
  enrollProgress: document.getElementById("enroll-progress"),
  enrollRecordBtn: document.getElementById("enroll-record-btn"),
  enrollSaveBtn: document.getElementById("enroll-save-btn"),
  enrollResetBtn: document.getElementById("enroll-reset-btn"),
  enrollClearBtn: document.getElementById("enroll-clear-btn"),
};

function connectWebSocket() {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(`${protocol}//${location.host}/ws`);

  ws.onmessage = (event) => {
    const { event: type, data } = JSON.parse(event.data);
    handleEvent(type, data);
  };

  ws.onclose = () => setTimeout(connectWebSocket, 2000);
}

function handleEvent(type, data) {
  switch (type) {
    case "connected":
      functions = data.functions || [];
      activeFunction = data.active_function || "chat";
      usedFunctions = toolIdSet(data.functions_used);
      stickyTools = toolIdSet(data.sticky_tools || data.functions_used);
      activeTools = toolIdSet(data.active_tools);
      modelsReady = data.models_ready;
      voiceEnrolled = !!data.voice_enrolled;
      renderFunctions();
      updateUI();
      fetchHistory();
      refreshVoiceProfile();
      break;
    case "status":
      updateStatus(data.status, data.step, data);
      break;
    case "message":
      appendMessage(data);
      break;
    case "function_changed":
      activeFunction = data.function_id;
      updateUI();
      break;
    case "model_changed":
      providerState = { ...providerState, ...data };
      renderProviderCards();
      renderModelMenu();
      updateCloudVaultPrivacyWarning();
      break;
    case "history_cleared":
      usedFunctions = new Set();
      stickyTools = new Set();
      activeTools = new Set();
      renderFunctions();
      clearChatUI();
      break;
    case "voice_enroll":
      if (typeof data.pending === "number") enrollPending = data.pending;
      if (typeof data.required === "number") enrollRequired = data.required;
      if (typeof data.enrolled === "boolean") voiceEnrolled = data.enrolled;
      updateEnrollUI();
      updateUI();
      break;
  }
}

function toolIdSet(ids) {
  return new Set((ids || []).filter((id) => id && id !== "chat"));
}

function setsEqual(a, b) {
  if (a.size !== b.size) return false;
  for (const value of a) {
    if (!b.has(value)) return false;
  }
  return true;
}

function visibleToolIds() {
  return new Set([...usedFunctions, ...stickyTools, ...activeTools]);
}

function isFunctionActive(fnId) {
  return activeTools.has(fnId) || stickyTools.has(fnId) || usedFunctions.has(fnId);
}

function functionStateLabel(fnId) {
  if (activeTools.has(fnId)) return "Active";
  if (stickyTools.has(fnId) || usedFunctions.has(fnId)) return "Used";
  return "";
}

function applyToolActivity(data) {
  let changed = false;
  if (Array.isArray(data.functions_used)) {
    const next = toolIdSet(data.functions_used);
    if (!setsEqual(usedFunctions, next)) {
      usedFunctions = next;
      changed = true;
    }
  }
  if (Array.isArray(data.sticky_tools)) {
    const next = toolIdSet(data.sticky_tools);
    if (!setsEqual(stickyTools, next)) {
      stickyTools = next;
      changed = true;
    }
  } else if (Array.isArray(data.functions_used)) {
    const next = new Set(usedFunctions);
    if (!setsEqual(stickyTools, next)) {
      stickyTools = next;
      changed = true;
    }
  }
  if (Array.isArray(data.active_tools)) {
    const next = toolIdSet(data.active_tools);
    if (!setsEqual(activeTools, next)) {
      activeTools = next;
      changed = true;
    }
  }
  if (changed) renderFunctions();
}

function updateStatus(status, step, data = {}) {
  applyToolActivity(data);
  const pill = els.modelStatus;
  pill.className = "status-pill";
  if (data.rejected) {
    pill.classList.add("listening");
    pill.querySelector("span:last-child").textContent = "Ignored other voice";
  } else if (status === "idle" && step === undefined) {
    modelsReady = true;
    pill.classList.add("ready");
    pill.querySelector("span:last-child").textContent = "Ready";
  } else if (status === "processing" && step && String(step).startsWith("Loading")) {
    pill.querySelector("span:last-child").textContent = step;
  } else if (status === "idle") {
    pill.classList.add("ready");
    pill.querySelector("span:last-child").textContent = STATUS_LABELS.idle;
  } else {
    pill.classList.add(status);
    pill.querySelector("span:last-child").textContent = step || STATUS_LABELS[status] || status;
  }
  if (typeof data.voice_enrolled === "boolean") {
    voiceEnrolled = data.voice_enrolled;
  }
  updateUI();
}

function renderFunctions() {
  if (!els.functionsList) return;
  const visible = visibleToolIds();
  const rows = functions.filter((fn) => fn.id && fn.id !== "chat" && visible.has(fn.id));
  els.functionsList.innerHTML = "";
  rows.forEach((fn) => {
    const item = document.createElement("div");
    const stateLabel = functionStateLabel(fn.id);
    item.className = "function-item" + (isFunctionActive(fn.id) ? " active" : "");
    item.setAttribute(
      "aria-label",
      `${fn.label}: ${activeTools.has(fn.id) ? "tool active" : "used"}`
    );
    item.innerHTML = `
      <span class="fn-icon">${ICONS[fn.id] || "*"}</span>
      <div class="fn-copy">
        <div class="fn-label">${fn.label}</div>
        <div class="fn-desc">${fn.description}</div>
      </div>
      <span class="fn-state">${stateLabel}</span>
    `;
    els.functionsList.appendChild(item);
  });
}

function updateUI() {
  const fn = functions.find((f) => f.id === activeFunction);
  if (els.activeLabel) {
    els.activeLabel.textContent = fn ? fn.label : "Automatic routing";
  }
  els.voiceBtn.disabled = !modelsReady;
  els.sendBtn.disabled = !modelsReady;
  els.messageInput.disabled = !modelsReady;
  els.voiceBadge.textContent = voiceActive ? "Voice on" : "Voice off";
  els.voiceBadge.classList.toggle("active", voiceActive);
  els.voiceBtn.classList.toggle("listening", voiceActive);
  const idleVoice =
    (BOARD_DIRECTIONS[document.documentElement.dataset.direction] ||
      BOARD_DIRECTIONS["gpp-head"]).voiceIdle;
  els.voiceBtn.textContent = voiceActive ? "Stop Voice" : idleVoice;
  if (els.voiceLockPill) {
    els.voiceLockPill.textContent = voiceEnrolled ? "Voice lock: on" : "Voice lock: off";
    els.voiceLockPill.classList.toggle("on", voiceEnrolled);
  }

  const showEnroll = activeFunction === "voice_lock" && !!els.enrollPanel;
  const composer = document.querySelector(".composer");
  if (els.enrollPanel) els.enrollPanel.hidden = !showEnroll;
  if (els.chatMessages) els.chatMessages.hidden = showEnroll;
  if (composer) composer.style.display = showEnroll ? "none" : "flex";
  updateEnrollUI();
}

function updateEnrollUI() {
  els.enrollProgress.textContent = voiceEnrolled
    ? "Voice profile saved. Only your speech will go to Whisper."
    : `Samples: ${enrollPending} / ${enrollRequired}`;
  els.enrollSaveBtn.disabled = !modelsReady || enrollPending < enrollRequired;
  els.enrollRecordBtn.disabled = !modelsReady || voiceActive || voiceEnrolled;
  els.enrollResetBtn.disabled = !modelsReady || voiceEnrolled;
  els.enrollClearBtn.disabled = !modelsReady || !voiceEnrolled;

  els.enrollPhrases.innerHTML = "";
  enrollPhrases.forEach((phrase, i) => {
    const li = document.createElement("li");
    li.textContent = phrase;
    if (i < enrollPending) li.classList.add("done");
    if (i === enrollPending && !voiceEnrolled) li.classList.add("current");
    els.enrollPhrases.appendChild(li);
  });
}

async function refreshVoiceProfile() {
  try {
    const res = await fetch("/api/voice/profile");
    if (!res.ok) return;
    const data = await res.json();
    voiceEnrolled = !!data.enrolled;
    enrollPending = data.pending || 0;
    enrollRequired = data.required || 3;
    enrollPhrases = data.phrases || [];
    if (data.instructions) els.enrollInstructions.textContent = data.instructions;
    updateUI();
  } catch (_) {}
}

function appendMessage(msg) {
  const welcome = els.chatMessages.querySelector(".welcome");
  if (welcome) welcome.remove();

  const div = document.createElement("div");
  div.className = `message ${msg.role}`;
  div.textContent = msg.content;
  if (msg.timestamp) {
    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent = new Date(msg.timestamp).toLocaleTimeString();
    div.appendChild(meta);
  }
  els.chatMessages.appendChild(div);
  els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
}

function applyBoardDirection(direction) {
  const next = BOARD_DIRECTIONS[direction] ? direction : "gpp-head";
  const copy = BOARD_DIRECTIONS[next];
  if (next === "gpp-head") {
    delete document.documentElement.dataset.direction;
  } else {
    document.documentElement.dataset.direction = next;
  }
  localStorage.setItem("marvin-direction", next);

  const title = document.getElementById("welcome-title");
  const body = document.getElementById("welcome-body");
  const hint = document.getElementById("welcome-hint");
  if (title) title.textContent = copy.title;
  if (body) {
    body.textContent = copy.body;
    body.hidden = !copy.body;
  }
  if (hint) {
    hint.textContent = copy.hint;
    hint.hidden = !copy.hint;
  }

  const heading = document.getElementById("functions-heading");
  if (heading) heading.textContent = copy.functions;
  if (els.messageInput) els.messageInput.placeholder = copy.placeholder;
  if (els.sendBtn) els.sendBtn.textContent = copy.send;
  if (els.voiceBtn && !els.voiceBtn.classList.contains("listening")) {
    els.voiceBtn.textContent = copy.voiceIdle;
  }

  const ticker = document.getElementById("life-ticker");
  if (ticker) {
    ticker.textContent = copy.ticker;
    ticker.hidden = !copy.ticker;
  }
  const hatch = document.getElementById("composer-hatch");
  if (hatch) {
    hatch.textContent = copy.hatch;
    hatch.hidden = !copy.hatch;
  }

  document.querySelectorAll("[data-direction-value]").forEach((button) => {
    button.classList.toggle("active", button.dataset.directionValue === next);
  });
}

function clearChatUI() {
  const copy =
    BOARD_DIRECTIONS[document.documentElement.dataset.direction] ||
    BOARD_DIRECTIONS["gpp-head"];
  const body = copy.body ? `<p id="welcome-body">${copy.body}</p>` : `<p id="welcome-body" hidden></p>`;
  const hint = copy.hint
    ? `<p class="hint" id="welcome-hint">${copy.hint}</p>`
    : `<p class="hint" id="welcome-hint" hidden></p>`;
  els.chatMessages.innerHTML = `
    <div class="welcome">
      <h3 id="welcome-title">${copy.title}</h3>
      ${body}
      ${hint}
    </div>
  `;
}

async function fetchHistory() {
  const res = await fetch("/api/chat/history");
  const { messages } = await res.json();
  clearChatUI();
  if (messages.length) {
    els.chatMessages.innerHTML = "";
    messages.forEach(appendMessage);
  }
}

async function sendMessage() {
  const text = els.messageInput.value.trim();
  if (!text || !modelsReady) return;
  els.messageInput.value = "";

  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ event: "send_message", data: { text } }));
  } else {
    const res = await fetch("/api/chat/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (res.ok) {
      const { reply } = await res.json();
      appendMessage({ role: "assistant", content: reply });
    }
  }
}

async function toggleVoice() {
  if (!modelsReady) return;
  const endpoint = voiceActive ? "/api/voice/stop" : "/api/voice/start";
  const res = await fetch(endpoint, { method: "POST" });
  if (res.ok) {
    const data = await res.json();
    voiceActive = !!data.listening;
    updateUI();
  } else {
    voiceActive = false;
    updateUI();
  }
}

els.sendBtn.addEventListener("click", sendMessage);
els.messageInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendMessage();
});
els.voiceBtn.addEventListener("click", toggleVoice);
els.clearBtn?.addEventListener("click", async () => {
  await fetch("/api/chat/history", { method: "DELETE" });
  clearChatUI();
});

els.enrollRecordBtn.addEventListener("click", async () => {
  els.enrollRecordBtn.disabled = true;
  els.enrollRecordBtn.textContent = "Recording…";
  try {
    const res = await fetch("/api/voice/enroll/sample", { method: "POST" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      alert(data.detail || "Recording failed");
      return;
    }
    enrollPending = data.pending;
    enrollRequired = data.required;
    updateEnrollUI();
  } finally {
    els.enrollRecordBtn.textContent = "Record sample";
    updateEnrollUI();
  }
});

els.enrollSaveBtn.addEventListener("click", async () => {
  const res = await fetch("/api/voice/enroll/finish", { method: "POST" });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    alert(data.detail || "Could not save profile");
    return;
  }
  voiceEnrolled = true;
  enrollPending = 0;
  updateUI();
});

els.enrollResetBtn.addEventListener("click", async () => {
  await fetch("/api/voice/enroll/reset", { method: "POST" });
  enrollPending = 0;
  updateEnrollUI();
});

els.enrollClearBtn.addEventListener("click", async () => {
  await fetch("/api/voice/profile", { method: "DELETE" });
  voiceEnrolled = false;
  enrollPending = 0;
  updateUI();
});

connectWebSocket();

setInterval(async () => {
  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    const becameReady = data.models_ready && !modelsReady;
    modelsReady = !!data.models_ready;
    voiceActive = !!data.listening;
    voiceEnrolled = !!data.voice_enrolled;
    if (becameReady) {
      updateStatus("idle");
      refreshVoiceProfile();
    } else {
      updateUI();
    }
  } catch (_) {}
}, 3000);

/* --- Composer model picker + Settings AI Providers --- */
const providerEls = {
  modelBtn: document.getElementById("model-btn"),
  modelMenu: document.getElementById("model-menu"),
  providerCards: document.getElementById("provider-cards"),
  privacyCloudVaultWarning: document.getElementById("privacy-cloud-vault-warning"),
  vaultPathInput: document.getElementById("vault-path-input"),
};

function setModelMenuOpen(open) {
  if (!providerEls.modelMenu || !providerEls.modelBtn) return;
  providerEls.modelMenu.hidden = !open;
  providerEls.modelBtn.setAttribute("aria-expanded", String(open));
  if (open) renderModelMenu();
}

function updateCloudVaultPrivacyWarning() {
  if (!providerEls.privacyCloudVaultWarning) return;
  const cloud =
    providerState.selected_provider &&
    providerState.selected_provider !== "local" &&
    providerState.selected_provider !== "qwen";
  const vaultConfigured = !!(
    providerEls.vaultPathInput && providerEls.vaultPathInput.value.trim()
  );
  if (cloud && vaultConfigured) {
    providerEls.privacyCloudVaultWarning.style.fontWeight = "600";
    providerEls.privacyCloudVaultWarning.textContent =
      "Cloud model + Obsidian: note text used this turn can leave this machine to the provider. Prefer local Qwen for vault work, or clear the vault path when chatting with cloud models.";
  }
}

async function refreshProviders({ focusProvider = null } = {}) {
  try {
    const res = await fetch("/api/providers");
    if (!res.ok) return;
    const data = await res.json();
    providerState = { ...providerState, ...data };
    if (focusProvider) providerState.focusProvider = focusProvider;
    renderProviderCards();
    renderModelMenu();
    updateCloudVaultPrivacyWarning();
  } catch (_) {}
}

function renderProviderCards() {
  if (!providerEls.providerCards) return;
  providerEls.providerCards.innerHTML = "";
  (providerState.providers || []).forEach((provider) => {
    const card = document.createElement("div");
    card.className = "provider-card";
    card.dataset.providerId = provider.provider_id;
    const configured = !!provider.configured;
    card.innerHTML = `
      <h3>${provider.display_name}</h3>
      <span class="provider-status ${configured ? "configured" : ""}">
        ${configured ? "Configured" : "Not configured"}
      </span>
      <div class="provider-key-row">
        <input
          type="password"
          class="provider-key-input"
          placeholder="${configured ? "Enter a new key to replace" : "API key"}"
          autocomplete="off"
          spellcheck="false"
          aria-label="${provider.display_name} API key"
        />
        <button type="button" class="settings-action provider-reveal" aria-label="Show API key">Show</button>
      </div>
      <div class="provider-actions">
        <button type="button" class="settings-action provider-save">Save</button>
        <button type="button" class="settings-action provider-test">Test</button>
        <button type="button" class="settings-action danger provider-delete" ${
          configured ? "" : "disabled"
        }>Delete</button>
      </div>
      <p class="provider-error" hidden></p>
      <p class="provider-notice">${provider.privacy_notice || ""}</p>
    `;
    const input = card.querySelector(".provider-key-input");
    const reveal = card.querySelector(".provider-reveal");
    const errorEl = card.querySelector(".provider-error");
    reveal.addEventListener("click", () => {
      const showing = input.type === "text";
      input.type = showing ? "password" : "text";
      reveal.textContent = showing ? "Show" : "Hide";
    });
    card.querySelector(".provider-save").addEventListener("click", async () => {
      const apiKey = input.value.trim();
      if (!apiKey) {
        errorEl.hidden = false;
        errorEl.textContent = "Enter an API key to save.";
        return;
      }
      const res = await fetch(`/api/providers/${provider.provider_id}/key`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: apiKey }),
      });
      const data = await res.json().catch(() => ({}));
      input.value = "";
      input.type = "password";
      reveal.textContent = "Show";
      if (!res.ok) {
        errorEl.hidden = false;
        errorEl.textContent = data.detail || "Could not save key.";
        return;
      }
      errorEl.hidden = true;
      providerState = { ...providerState, ...data, focusProvider: null };
      renderProviderCards();
      renderModelMenu();
      if (data.validation && data.validation.ok === false) {
        errorEl.hidden = false;
        errorEl.style.color = "var(--danger)";
        errorEl.textContent =
          data.validation.error_message || "Key saved, but connection test failed.";
        return;
      }
      setSettingsOpen(false);
    });
    card.querySelector(".provider-test").addEventListener("click", async () => {
      const apiKey = input.value.trim() || null;
      const res = await fetch(`/api/providers/${provider.provider_id}/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: apiKey }),
      });
      const data = await res.json().catch(() => ({}));
      if (data.ok) {
        errorEl.hidden = false;
        errorEl.style.color = "var(--primary)";
        errorEl.textContent = "Connection OK.";
      } else {
        errorEl.hidden = false;
        errorEl.style.color = "var(--danger)";
        errorEl.textContent = data.error_message || "Connection failed.";
      }
    });
    card.querySelector(".provider-delete").addEventListener("click", async () => {
      if (!configured) return;
      if (!window.confirm(`Delete the ${provider.display_name} API key?`)) return;
      const res = await fetch(`/api/providers/${provider.provider_id}/key`, {
        method: "DELETE",
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        errorEl.hidden = false;
        errorEl.textContent = data.detail || "Could not delete key.";
        return;
      }
      providerState = { ...providerState, ...data };
      renderProviderCards();
      renderModelMenu();
    });
    providerEls.providerCards.appendChild(card);
    if (providerState.focusProvider === provider.provider_id) {
      input.focus();
    }
  });
}

function renderModelMenu() {
  if (!providerEls.modelMenu) return;
  const catalog = providerState.catalog || [];
  const selectedProvider = providerState.selected_provider;
  const selectedModel = providerState.selected_model;
  const offline = providerState.network_available === false;
  const lastCloud = providerState.last_cloud_provider;
  providerEls.modelMenu.innerHTML = "";
  catalog.forEach((group) => {
    const section = document.createElement("div");
    section.className = "model-menu-group";
    (group.models || []).forEach((model) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `model-menu-item${model.configured ? "" : " locked"}`;
      button.setAttribute("role", "menuitemradio");
      const selected =
        model.provider_id === selectedProvider && model.model_id === selectedModel;
      button.setAttribute("aria-checked", String(selected));
      let meta = "";
      if (!model.configured) {
        meta = "Needs API key";
      } else if (
        selected &&
        offline &&
        model.provider_id === "local" &&
        lastCloud
      ) {
        meta = "Offline";
      } else if (selected) {
        meta = "Selected";
      }
      button.innerHTML = `
        <span>${model.display_name}</span>
        <span class="model-menu-meta">${meta}</span>
      `;
      button.addEventListener("click", () => selectComposerModel(model));
      section.appendChild(button);
    });
    providerEls.modelMenu.appendChild(section);
  });
  const manage = document.createElement("button");
  manage.type = "button";
  manage.className = "model-menu-action";
  manage.setAttribute("role", "menuitem");
  manage.textContent = "Manage AI providers…";
  manage.addEventListener("click", () => {
    setModelMenuOpen(false);
    setSettingsOpen(true, { category: "providers" });
  });
  providerEls.modelMenu.appendChild(manage);
}

async function selectComposerModel(model) {
  const res = await fetch("/api/providers/select", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      provider_id: model.provider_id,
      model_id: model.model_id,
    }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) return;
  providerState = { ...providerState, ...data };
  setModelMenuOpen(false);
  if (data.needs_key) {
    setSettingsOpen(true, {
      category: "providers",
      focusProvider: data.focus_provider || model.provider_id,
    });
  } else {
    renderModelMenu();
  }
}

document.getElementById("model-btn")?.addEventListener("click", (event) => {
  event.stopPropagation();
  const menu = document.getElementById("model-menu");
  setModelMenuOpen(!!(menu && menu.hidden));
});

document.addEventListener("click", (event) => {
  const wrap = document.querySelector(".model-menu-wrap");
  if (!wrap || wrap.contains(event.target)) return;
  setModelMenuOpen(false);
});

/* --- Settings dialog + Skills (bundled Agent Skills) --- */
const settingsEls = {
  settingsBtn: document.getElementById("settings-btn"),
  settingsDialog: document.getElementById("settings-dialog"),
  settingsCloseBtn: document.getElementById("settings-close-btn"),
  settingsNavItems: document.querySelectorAll("[data-settings-category].settings-nav-item"),
  settingsPanels: document.querySelectorAll(".settings-panel"),
  skillsStatusLine: document.getElementById("skills-status-line"),
  skillsPathLine: document.getElementById("skills-path-line"),
  skillsRevealBtn: document.getElementById("skills-reveal-btn"),
  skillsRefreshBtn: document.getElementById("skills-refresh-btn"),
  formatSkillsList: document.getElementById("format-skills-list"),
  formatSkillsPhase2: document.getElementById("format-skills-phase2-hint"),
  providerCards: document.getElementById("provider-cards"),
};

let settingsCategory =
  localStorage.getItem("marvin-settings-category") || "general";

function setSettingsCategory(category, { focusProvider = null } = {}) {
  settingsCategory = category || "general";
  localStorage.setItem("marvin-settings-category", settingsCategory);
  settingsEls.settingsNavItems.forEach((button) => {
    const selected = button.dataset.settingsCategory === settingsCategory;
    button.setAttribute("aria-selected", String(selected));
  });
  settingsEls.settingsPanels.forEach((panel) => {
    panel.hidden = panel.dataset.settingsCategory !== settingsCategory;
  });
  if (settingsCategory === "skills") {
    refreshSkillsStatus();
  }
  if (settingsCategory === "providers") {
    refreshProviders({ focusProvider });
  }
}

function setSettingsOpen(open, { focusProvider = null, category = null } = {}) {
  if (!settingsEls.settingsDialog || !settingsEls.settingsBtn) return;
  settingsEls.settingsBtn.setAttribute("aria-expanded", String(open));
  settingsEls.settingsBtn.classList.toggle("active", open);
  if (open) {
    const nextCategory =
      category || (focusProvider ? "providers" : settingsCategory || "general");
    setSettingsCategory(nextCategory, { focusProvider });
    if (typeof settingsEls.settingsDialog.showModal === "function") {
      settingsEls.settingsDialog.showModal();
    }
    if (focusProvider) {
      requestAnimationFrame(() => {
        const input = providerEls.providerCards?.querySelector(
          `[data-provider-id="${focusProvider}"] .provider-key-input`
        );
        input?.focus();
      });
    }
  } else if (settingsEls.settingsDialog.open) {
    settingsEls.settingsDialog.close();
  }
}

function renderFormatSkills(formatSkills, phase2) {
  if (!settingsEls.formatSkillsList) return;
  settingsEls.formatSkillsList.innerHTML = "";
  (formatSkills || []).forEach((skill) => {
    const row = document.createElement("div");
    row.className = "format-skill-row";
    const label = document.createElement("label");
    label.className = "format-skill-toggle";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.checked = !!skill.enabled;
    input.dataset.skillId = skill.id;
    input.addEventListener("change", () => saveFormatSkillToggles());
    const text = document.createElement("span");
    const group = skill.group ? ` · ${skill.group}` : "";
    text.innerHTML = `<strong>${skill.name || skill.id}</strong>${group}<br /><span class="hint">${
      skill.description || ""
    }</span>`;
    label.appendChild(input);
    label.appendChild(text);
    row.appendChild(label);
    if (skill.group === "custom" || skill.custom) {
      const del = document.createElement("button");
      del.type = "button";
      del.className = "btn btn-ghost format-skill-delete";
      del.textContent = "Delete";
      del.addEventListener("click", async (event) => {
        event.preventDefault();
        try {
          await fetch(`/api/skills/custom/${encodeURIComponent(skill.id)}`, {
            method: "DELETE",
          });
        } catch (_) {}
        refreshSkillsStatus();
      });
      row.appendChild(del);
    }
    settingsEls.formatSkillsList.appendChild(row);
  });
  if (settingsEls.formatSkillsPhase2 && Array.isArray(phase2) && phase2.length) {
    settingsEls.formatSkillsPhase2.textContent = `Phase 2 (not available yet): ${phase2.join(
      ", "
    )}.`;
  }
}

async function refreshSkillsStatus() {
  try {
    const res = await fetch("/api/skills/status");
    if (!res.ok) return;
    const data = await res.json();
    if (settingsEls.skillsStatusLine) {
      settingsEls.skillsStatusLine.textContent = data.configured
        ? "Custom skill.md is active and loaded into Marvin’s prompt."
        : "Placeholder only — edit skill.md to activate custom instructions.";
    }
    if (settingsEls.skillsPathLine) {
      settingsEls.skillsPathLine.textContent = data.path || "";
    }
    renderFormatSkills(data.format_skills, data.phase2_skills);
  } catch (_) {}
}

async function saveFormatSkillToggles() {
  if (!settingsEls.formatSkillsList) return;
  const enabled = {};
  settingsEls.formatSkillsList
    .querySelectorAll("input[type=checkbox][data-skill-id]")
    .forEach((input) => {
      enabled[input.dataset.skillId] = !!input.checked;
    });
  try {
    const res = await fetch("/api/skills/format", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    });
    if (!res.ok) return;
    const data = await res.json();
    renderFormatSkills(data.format_skills, data.phase2_skills);
  } catch (_) {}
}

settingsEls.settingsBtn?.addEventListener("click", () => {
  const open = settingsEls.settingsDialog && !settingsEls.settingsDialog.open;
  setSettingsOpen(!!open);
});
settingsEls.settingsCloseBtn?.addEventListener("click", () => setSettingsOpen(false));
settingsEls.settingsDialog?.addEventListener("cancel", (e) => {
  e.preventDefault();
  setSettingsOpen(false);
});
settingsEls.settingsNavItems.forEach((button) => {
  button.addEventListener("click", () => {
    setSettingsCategory(button.dataset.settingsCategory);
  });
});
settingsEls.skillsRevealBtn?.addEventListener("click", async () => {
  try {
    await fetch("/api/skills/reveal", { method: "POST" });
  } catch (_) {}
});
settingsEls.skillsRefreshBtn?.addEventListener("click", () => refreshSkillsStatus());
setSettingsCategory(settingsCategory);
refreshProviders();
document.querySelectorAll("[data-direction-value]").forEach((button) => {
  button.addEventListener("click", () => applyBoardDirection(button.dataset.directionValue));
});
applyBoardDirection(localStorage.getItem("marvin-direction") || "gpp-head");
