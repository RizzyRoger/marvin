const ICONS = {
  chat: "C",
  daily_planning: "P",
  web_search: "S",
  spotify: "M",
  obsidian: "O",
  timers: "T",
  ai_model: "A",
  voice_scrambler: "V",
  python_runner: "Y",
};

const VOICE_STATUS_LABELS = {
  not_configured: "Not configured",
  disabled: "Configured and disabled",
  enabled: "Enabled",
  needs_reenrollment: "Needs re-enrollment",
  error: "Profile error",
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
let voiceSettings = {
  voice_lock_enabled: false,
  voice_profile_status: "not_configured",
  strictness_mode: "strict",
  require_addressing: true,
  contextual_continuation_enabled: true,
  continuation_window_seconds: 60,
  limitation: "",
};
let functions = [];
let usedFunctions = new Set();
let stickyTools = new Set();
let activeTools = new Set();
let functionsFingerprint = "";
let enrollPhrases = [];
let enrollPending = 0;
let enrollRequired = 6;
let clientTimezone = "";
try {
  clientTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
} catch (_) {
  clientTimezone = "";
}

const els = {
  functionsList: document.getElementById("functions-list"),
  chatMessages: document.getElementById("chat-messages"),
  messageInput: document.getElementById("message-input"),
  sendBtn: document.getElementById("send-btn"),
  voiceBtn: document.getElementById("voice-btn"),
  settingsBtn: document.getElementById("settings-btn"),
  settingsCloseBtn: document.getElementById("settings-close-btn"),
  settingsDialog: document.getElementById("settings-dialog"),
  settingsNavItems: document.querySelectorAll("[data-settings-category]"),
  settingsPanels: document.querySelectorAll(".settings-panel"),
  settingsVoiceStatus: document.getElementById("settings-voice-status"),
  settingsClearBtn: document.getElementById("settings-clear-btn"),
  settingsClearStatus: document.getElementById("settings-clear-status"),
  themeOptions: document.querySelectorAll(".theme-option[data-theme-value]"),
  clearDialog: document.getElementById("clear-confirm-dialog"),
  clearCancelBtn: document.getElementById("clear-cancel-btn"),
  clearConfirmBtn: document.getElementById("clear-confirm-btn"),
  modelStatus: document.getElementById("model-status"),
  activeLabel: document.getElementById("active-function-label"),
  voiceBadge: document.getElementById("voice-badge"),
  voiceLockStatusLine: document.getElementById("voice-lock-status-line"),
  voiceLockMicrophone: document.getElementById("voice-lock-microphone"),
  voiceLockLimitation: document.getElementById("voice-lock-limitation"),
  voiceClearDialog: document.getElementById("voice-clear-confirm-dialog"),
  voiceClearCancelBtn: document.getElementById("voice-clear-cancel-btn"),
  voiceClearConfirmBtn: document.getElementById("voice-clear-confirm-btn"),
  enrollResetAllDialog: document.getElementById("enroll-reset-all-dialog"),
  enrollResetAllCancelBtn: document.getElementById("enroll-reset-all-cancel-btn"),
  enrollResetAllConfirmBtn: document.getElementById("enroll-reset-all-confirm-btn"),
  voiceLockEnabled: document.getElementById("voice-lock-enabled"),
  voiceLockStrictness: document.getElementById("voice-lock-strictness"),
  voiceLockRequireAddress: document.getElementById("voice-lock-require-address"),
  voiceLockContinuation: document.getElementById("voice-lock-continuation"),
  voiceLockWindow: document.getElementById("voice-lock-window"),
  enrollInstructions: document.getElementById("enroll-instructions"),
  enrollPhrases: document.getElementById("enroll-phrases"),
  enrollProgress: document.getElementById("enroll-progress"),
  enrollRecordBtn: document.getElementById("enroll-record-btn"),
  enrollSaveBtn: document.getElementById("enroll-save-btn"),
  enrollResetBtn: document.getElementById("enroll-reset-btn"),
  enrollClearBtn: document.getElementById("enroll-clear-btn"),
  voiceTestBtn: document.getElementById("voice-test-btn"),
  voiceTestResult: document.getElementById("voice-test-result"),
  providerCards: document.getElementById("provider-cards"),
  modelBtn: document.getElementById("model-btn"),
  modelMenu: document.getElementById("model-menu"),
  spotifyStatusLine: document.getElementById("spotify-status-line"),
  spotifyHint: document.getElementById("spotify-hint"),
  spotifyAccountLine: document.getElementById("spotify-account-line"),
  spotifyConnectBtn: document.getElementById("spotify-connect-btn"),
  spotifyDisconnectBtn: document.getElementById("spotify-disconnect-btn"),
  scramblerStatusLine: document.getElementById("scrambler-status-line"),
  scramblerHint: document.getElementById("scrambler-hint"),
  scramblerDeviceSelect: document.getElementById("scrambler-device-select"),
  scramblerStartBtn: document.getElementById("scrambler-start-btn"),
  scramblerStopBtn: document.getElementById("scrambler-stop-btn"),
  scramblerResetBtn: document.getElementById("scrambler-reset-btn"),
  scramblerClarity: document.getElementById("scrambler-clarity"),
  scramblerClarityLabel: document.getElementById("scrambler-clarity-label"),
  scramblerStrength: document.getElementById("scrambler-strength"),
  scramblerStrengthLabel: document.getElementById("scrambler-strength-label"),
  scramblerMasterGain: document.getElementById("scrambler-master-gain"),
  scramblerGainLabel: document.getElementById("scrambler-gain-label"),
  uiScaleSlider: document.getElementById("ui-scale-slider"),
  uiScaleLabel: document.getElementById("ui-scale-label"),
  vaultPathInput: document.getElementById("vault-path-input"),
  vaultPathStatus: document.getElementById("vault-path-status"),
  vaultPathSave: document.getElementById("vault-path-save"),
  vaultRequestAccess: document.getElementById("vault-request-access"),
  vaultSetupDialog: document.getElementById("vault-setup-dialog"),
  vaultSetupInput: document.getElementById("vault-setup-input"),
  vaultSetupStatus: document.getElementById("vault-setup-status"),
  vaultSetupSaveBtn: document.getElementById("vault-setup-save-btn"),
  vaultSetupSkipBtn: document.getElementById("vault-setup-skip-btn"),
  privacyCloudVaultWarning: document.getElementById("privacy-cloud-vault-warning"),
  speechNationality: document.getElementById("speech-nationality"),
  speechGender: document.getElementById("speech-gender"),
  speechMode: document.getElementById("speech-mode"),
  speechSettingsStatus: document.getElementById("speech-settings-status"),
  skillsStatusLine: document.getElementById("skills-status-line"),
  skillsPathLine: document.getElementById("skills-path-line"),
  skillsRevealBtn: document.getElementById("skills-reveal-btn"),
  skillsRefreshBtn: document.getElementById("skills-refresh-btn"),
};

let settingsCategory =
  localStorage.getItem("marvin-settings-category") || "general";
let settingsOpener = null;
let enrollSamples = [];
let enrollBusySampleId = null;
const SAMPLE_STATUS_LABELS = {
  not_recorded: "Not recorded",
  recording: "Recording",
  processing: "Processing",
  accepted: "Accepted",
  needs_retry: "Needs another attempt",
  failed: "Failed quality check",
};

let providerState = {
  providers: [],
  catalog: [],
  selected_provider: null,
  selected_model: null,
  pending_provider: null,
  pending_model: null,
  focusProvider: null,
};

function connectWebSocket() {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(`${protocol}//${location.host}/ws`);

  ws.onopen = () => {
    if (clientTimezone) {
      ws.send(
        JSON.stringify({
          event: "set_timezone",
          data: { timezone: clientTimezone },
        })
      );
    }
  };

  ws.onmessage = (event) => {
    const { event: type, data } = JSON.parse(event.data);
    handleEvent(type, data);
  };

  ws.onclose = () => setTimeout(connectWebSocket, 2000);
}

function handleEvent(type, data) {
  switch (type) {
    case "connected":
      functions = (data.functions || []).filter((fn) => fn.id !== "chat");
      usedFunctions = new Set(
        (data.functions_used || []).filter((id) => id && id !== "chat")
      );
      stickyTools = new Set(
        (data.sticky_tools || data.functions_used || []).filter(
          (id) => id && id !== "chat"
        )
      );
      activeTools = new Set(data.active_tools || []);
      modelsReady = data.models_ready;
      voiceEnrolled = !!data.voice_enrolled;
      renderFunctions();
      updateUI();
      if (modelsReady) updateStatus("idle");
      fetchHistory();
      refreshVoiceProfile();
      break;
    case "status":
      updateStatus(data.status, data.step, data);
      break;
    case "message":
      appendMessage(data);
      break;
    case "reminder": {
      const kind = data.kind || "reminder";
      const label = data.name || data.message || (kind === "timer" ? "Timer" : "Time’s up.");
      const content =
        kind === "timer" ? `Timer done: ${label}` : `Reminder: ${label}`;
      appendMessage({
        role: "assistant",
        content,
        function_id: kind === "timer" ? "timers" : "daily_planning",
        timestamp: new Date().toISOString(),
      });
      updateStatus("idle", kind === "timer" ? "Timer" : "Reminder");
      break;
    }
    case "function_changed":
      usedFunctions = new Set(
        data.function_id && data.function_id !== "chat" ? [data.function_id] : []
      );
      stickyTools = new Set(usedFunctions);
      renderFunctions();
      updateUI();
      break;
    case "model_changed":
      providerState = { ...providerState, ...data };
      renderProviderCards();
      renderModelMenu();
      updateCloudVaultPrivacyWarning();
      break;
    case "history_cleared":
      clearChatUI();
      break;
    case "history_updated":
      renderHistory(data.messages || []);
      break;
    case "voice_settings":
      applyVoiceSettings(data);
      updateUI();
      break;
    case "voice_enroll":
      if (typeof data.pending === "number") enrollPending = data.pending;
      if (typeof data.required === "number") enrollRequired = data.required;
      if (typeof data.enrolled === "boolean") voiceEnrolled = data.enrolled;
      applyVoiceSettings(data);
      updateEnrollUI();
      updateUI();
      break;
  }
}

function setsEqual(a, b) {
  if (a.size !== b.size) return false;
  for (const value of a) {
    if (!b.has(value)) return false;
  }
  return true;
}

function updateStatus(status, step, data = {}) {
  let activityChanged = false;
  if (Array.isArray(data.active_tools)) {
    const next = new Set(data.active_tools);
    if (!setsEqual(activeTools, next)) {
      activeTools = next;
      activityChanged = true;
    }
  }
  if (Array.isArray(data.functions_used)) {
    const next = new Set(
      data.functions_used.filter((id) => id && id !== "chat")
    );
    if (!setsEqual(usedFunctions, next)) {
      usedFunctions = next;
      activityChanged = true;
    }
  }
  if (Array.isArray(data.sticky_tools)) {
    const next = new Set(
      data.sticky_tools.filter((id) => id && id !== "chat")
    );
    if (!setsEqual(stickyTools, next)) {
      stickyTools = next;
      activityChanged = true;
    }
  } else if (Array.isArray(data.functions_used)) {
    // Prefer sticky_tools; fall back to functions_used for older payloads.
    stickyTools = new Set(usedFunctions);
  }
  if (activityChanged) {
    renderFunctions();
  }
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
  updateToolActivityStatus();
  updateUI();
}

function isFunctionActive(fnId) {
  if (activeTools.has(fnId)) {
    return true;
  }
  if (stickyTools.has(fnId)) {
    return true;
  }
  return usedFunctions.has(fnId);
}

function functionStateLabel(fnId) {
  if (activeTools.has(fnId)) {
    return "Active";
  }
  if (stickyTools.has(fnId) || usedFunctions.has(fnId)) {
    return "Used";
  }
  return "";
}

function updateToolActivityStatus() {
  let live = document.getElementById("tool-activity-live");
  if (!live) {
    live = document.createElement("div");
    live.id = "tool-activity-live";
    live.className = "visually-hidden";
    live.setAttribute("aria-live", "polite");
    live.setAttribute("aria-atomic", "true");
    document.body.appendChild(live);
  }
  const names = [...activeTools];
  const next = names.length
    ? `${names.map((name) => name.replace(/_/g, " ")).join(", ")} tool active`
    : "";
  if (live.textContent !== next) {
    live.textContent = next;
  }
}

function visibleToolIds() {
  return new Set(
    [...usedFunctions, ...stickyTools, ...activeTools].filter((id) => id && id !== "chat")
  );
}

function renderFunctions(force = false) {
  if (!els.functionsList) return;
  const visible = visibleToolIds();
  const rows = functions.filter((fn) => fn.id && visible.has(fn.id));
  const fingerprint = rows
    .map((fn) => `${fn.id}:${isFunctionActive(fn.id) ? 1 : 0}:${functionStateLabel(fn.id)}`)
    .join("|");
  if (!force && fingerprint === functionsFingerprint && els.functionsList.childElementCount === rows.length) {
    return;
  }
  functionsFingerprint = fingerprint;
  els.functionsList.innerHTML = "";
  rows.forEach((fn) => {
    const item = document.createElement("div");
    const isActive = isFunctionActive(fn.id);
    const stateLabel = functionStateLabel(fn.id);
    item.className = "function-item" + (isActive ? " active" : "");
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

function applyVoiceSettings(data) {
  if (!data || typeof data !== "object") return;
  voiceSettings = { ...voiceSettings, ...data };
  if (typeof data.enrolled === "boolean") voiceEnrolled = data.enrolled;
  if (typeof data.pending === "number") enrollPending = data.pending;
  if (typeof data.required === "number") enrollRequired = data.required;
  if (Array.isArray(data.phrases)) enrollPhrases = data.phrases;
  if (Array.isArray(data.samples)) enrollSamples = data.samples;
}

function voiceStatusLabel() {
  return (
    VOICE_STATUS_LABELS[voiceSettings.voice_profile_status] ||
    (voiceEnrolled
      ? voiceSettings.voice_lock_enabled
        ? "Enabled"
        : "Configured and disabled"
      : "Not configured")
  );
}

function updateUI() {
  if (els.activeLabel) els.activeLabel.textContent = "Automatic routing";
  if (els.voiceBtn) els.voiceBtn.disabled = !modelsReady;
  if (els.sendBtn) els.sendBtn.disabled = !modelsReady;
  if (els.messageInput) els.messageInput.disabled = !modelsReady;
  if (els.voiceBadge) {
    els.voiceBadge.textContent = voiceActive ? "Voice on" : "Voice off";
    els.voiceBadge.classList.toggle("active", voiceActive);
  }
  if (els.voiceBtn) {
    els.voiceBtn.classList.toggle("listening", voiceActive);
    const direction = document.documentElement.dataset.direction || "gpp-head";
    const idle =
      direction === "empty-planet" ? "Voice" : "Start Voice";
    els.voiceBtn.textContent = voiceActive ? "Stop Voice" : idle;
  }
  if (els.settingsVoiceStatus) {
    els.settingsVoiceStatus.textContent = voiceStatusLabel();
  }
  updateEnrollUI();
}

function resolvedThemePreference() {
  return localStorage.getItem("marvin-theme") || "system";
}

function applyThemePreference(preference) {
  const pref = preference || "system";
  if (pref === "system") {
    localStorage.setItem("marvin-theme", "system");
    document.documentElement.dataset.theme = matchMedia(
      "(prefers-color-scheme: dark)"
    ).matches
      ? "dark"
      : "light";
  } else {
    localStorage.setItem("marvin-theme", pref);
    document.documentElement.dataset.theme = pref;
  }
  updateThemeButton();
}

function resolvedUiScale() {
  const raw = Number(localStorage.getItem("marvin-ui-scale") || "100");
  if (!Number.isFinite(raw)) return 100;
  return Math.min(130, Math.max(90, raw));
}

function applyUiScale(percent) {
  const value = Math.min(130, Math.max(90, Number(percent) || 100));
  localStorage.setItem("marvin-ui-scale", String(value));
  document.documentElement.style.fontSize = `${(value / 100) * 16}px`;
  if (els.uiScaleSlider) els.uiScaleSlider.value = String(value);
  if (els.uiScaleLabel) els.uiScaleLabel.textContent = `${value}%`;
}

async function refreshSkillsStatus() {
  try {
    const res = await fetch("/api/skills/status");
    if (!res.ok) return;
    const data = await res.json();
    if (els.skillsStatusLine) {
      els.skillsStatusLine.textContent = data.configured
        ? "Custom skill.md is active and loaded into Marvin’s prompt."
        : "Placeholder only — edit skill.md to activate custom instructions.";
    }
    if (els.skillsPathLine) {
      els.skillsPathLine.textContent = data.path || "";
    }
  } catch (_) {}
}

async function refreshVaultStatus() {
  if (!els.vaultPathInput) return;
  try {
    const res = await fetch("/api/vault/status");
    if (!res.ok) return;
    const data = await res.json();
    if (!els.vaultPathInput.value) {
      els.vaultPathInput.value = data.path || "";
    }
    if (els.vaultPathStatus) {
      if (data.connected) {
        els.vaultPathStatus.textContent = "Vault connected.";
      } else if (data.needs_permission) {
        els.vaultPathStatus.textContent =
          data.hint ||
          "macOS is blocking Documents access. Click Request Documents access.";
      } else if (data.exists) {
        els.vaultPathStatus.textContent =
          data.hint || "Path exists but vault looks disconnected.";
      } else if (data.configured) {
        els.vaultPathStatus.textContent =
          data.hint || "Path missing — choose your Obsidian vault folder.";
      } else {
        els.vaultPathStatus.textContent =
          "Path missing — choose your Obsidian vault folder.";
      }
    }
    if (els.vaultRequestAccess) {
      els.vaultRequestAccess.hidden = !data.needs_permission;
    }
    if (data.needs_setup && data.bundle && els.vaultSetupDialog) {
      const skipped = sessionStorage.getItem("marvin-vault-setup-skipped") === "1";
      if (!skipped && !els.vaultSetupDialog.open) {
        if (els.vaultSetupInput && data.path) {
          els.vaultSetupInput.value = data.path;
        }
        els.vaultSetupDialog.showModal();
      }
    }
    updateCloudVaultPrivacyWarning();
  } catch (_) {}
}

async function requestVaultAccess() {
  try {
    const res = await fetch("/api/vault/request-access", { method: "POST" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      if (els.vaultPathStatus) {
        els.vaultPathStatus.textContent =
          data.detail || "Could not request Documents access.";
      }
      return;
    }
    if (els.vaultPathStatus) {
      els.vaultPathStatus.textContent = data.connected
        ? "Vault connected."
        : data.hint ||
          "If macOS prompted you, allow Documents access, then click Save vault path.";
    }
    if (els.vaultRequestAccess) {
      els.vaultRequestAccess.hidden = !data.needs_permission;
    }
    await refreshVaultStatus();
  } catch (_) {
    if (els.vaultPathStatus) {
      els.vaultPathStatus.textContent = "Could not request Documents access.";
    }
  }
}

async function refreshSpeechSettings() {
  if (!els.speechNationality) return;
  try {
    const res = await fetch("/api/speech/settings");
    if (!res.ok) return;
    const data = await res.json();
    if (els.speechNationality) els.speechNationality.value = data.nationality || "british";
    if (els.speechGender) els.speechGender.value = data.gender || "male";
    if (els.speechMode) els.speechMode.value = data.mode || "always_on";
    if (els.speechSettingsStatus) {
      els.speechSettingsStatus.textContent = data.voice_ready
        ? `Voice: ${data.voice_id}`
        : `Voice ${data.voice_id} not downloaded yet — run scripts/download_models.py`;
    }
  } catch (_) {}
}

async function saveSpeechSettings() {
  if (!els.speechNationality) return;
  try {
    const res = await fetch("/api/speech/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        nationality: els.speechNationality.value,
        gender: els.speechGender.value,
        mode: els.speechMode.value,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      if (els.speechSettingsStatus) {
        els.speechSettingsStatus.textContent =
          data.detail || "Could not save speech settings.";
      }
      return;
    }
    if (els.speechSettingsStatus) {
      els.speechSettingsStatus.textContent = data.voice_ready
        ? `Saved — speaking as ${data.voice_id}`
        : `Saved — download ${data.voice_id} via scripts/download_models.py`;
    }
  } catch (_) {
    if (els.speechSettingsStatus) {
      els.speechSettingsStatus.textContent = "Could not save speech settings.";
    }
  }
}

function updateCloudVaultPrivacyWarning() {
  if (!els.privacyCloudVaultWarning) return;
  const cloud =
    providerState.selected_provider &&
    providerState.selected_provider !== "local" &&
    providerState.selected_provider !== "qwen";
  const vaultConfigured = !!(els.vaultPathInput && els.vaultPathInput.value.trim());
  if (cloud && vaultConfigured) {
    els.privacyCloudVaultWarning.style.fontWeight = "600";
    els.privacyCloudVaultWarning.textContent =
      "Cloud model + Obsidian: note text used this turn can leave this machine to the provider. Prefer local Qwen for vault work, or clear the vault path when chatting with cloud models.";
  }
}

async function saveVaultPath() {
  if (!els.vaultPathInput) return;
  const path = els.vaultPathInput.value.trim();
  if (!path) {
    if (els.vaultPathStatus) {
      els.vaultPathStatus.textContent = "Enter a vault folder path.";
    }
    return;
  }
  try {
    const res = await fetch("/api/vault/path", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      if (els.vaultPathStatus) {
        els.vaultPathStatus.textContent =
          data.detail || "Could not save vault path.";
      }
      return;
    }
    els.vaultPathInput.value = data.path || path;
    if (els.vaultPathStatus) {
      els.vaultPathStatus.textContent = data.connected
        ? "Vault path saved and connected."
        : data.needs_permission
          ? data.hint ||
            "Saved, but macOS is blocking access — use Request Documents access."
          : "Vault path saved.";
    }
    if (els.vaultRequestAccess) {
      els.vaultRequestAccess.hidden = !data.needs_permission;
    }
    await refreshVaultStatus();
  } catch (_) {
    if (els.vaultPathStatus) {
      els.vaultPathStatus.textContent = "Could not save vault path.";
    }
  }
}

function sampleStatusLabel(status) {
  return SAMPLE_STATUS_LABELS[status] || status || "Not recorded";
}

function updateEnrollUI() {
  const status = voiceStatusLabel();
  els.voiceLockStatusLine.textContent = status;
  if (els.settingsVoiceStatus) els.settingsVoiceStatus.textContent = status;
  if (els.voiceLockMicrophone) {
    els.voiceLockMicrophone.textContent = `Microphone: ${
      voiceSettings.microphone_name || "Default input"
    }`;
  }
  els.voiceLockLimitation.textContent = voiceSettings.limitation || "";
  if (voiceSettings.instructions) {
    els.enrollInstructions.textContent = voiceSettings.instructions;
  }
  els.voiceLockEnabled.checked = !!voiceSettings.voice_lock_enabled;
  els.voiceLockEnabled.disabled = !voiceEnrolled;
  els.voiceLockStrictness.value = voiceSettings.strictness_mode || "strict";
  els.voiceLockRequireAddress.checked = voiceSettings.require_addressing !== false;
  els.voiceLockContinuation.checked =
    voiceSettings.contextual_continuation_enabled !== false;
  els.voiceLockWindow.value = voiceSettings.continuation_window_seconds || 60;

  els.enrollProgress.textContent = voiceEnrolled
    ? "Voice profile saved. Spoken turns require your voice and addressing rules."
    : `Samples: ${enrollPending} / ${enrollRequired}`;
  const recordingBusy = !!enrollBusySampleId;
  els.enrollSaveBtn.disabled =
    !modelsReady || enrollPending < enrollRequired || recordingBusy;
  els.enrollRecordBtn.disabled =
    !modelsReady || voiceActive || voiceEnrolled || recordingBusy;
  els.enrollResetBtn.disabled = !modelsReady || voiceEnrolled || recordingBusy;
  els.enrollClearBtn.disabled = !modelsReady || !voiceEnrolled;
  els.voiceTestBtn.disabled = !modelsReady || voiceActive || !voiceEnrolled;

  const samples =
    enrollSamples.length > 0
      ? enrollSamples
      : enrollPhrases.map((phrase, index) => ({
          sample_id: `legacy-${index}`,
          prompt_type:
            phrase === voiceSettings.natural_prompt ? "natural" : "phrase",
          prompt_text: phrase,
          status: index < enrollPending ? "accepted" : "not_recorded",
        }));

  els.enrollPhrases.innerHTML = "";
  let currentMarked = false;
  samples.forEach((sample) => {
    const card = document.createElement("div");
    const statusKey = sample.status || "not_recorded";
    const isNatural = sample.prompt_type === "natural";
    const isCurrent =
      !voiceEnrolled &&
      !currentMarked &&
      ["not_recorded", "needs_retry", "failed"].includes(statusKey);
    if (isCurrent) currentMarked = true;
    card.className = `enroll-sample${statusKey === "accepted" ? " accepted" : ""}${
      isCurrent ? " current" : ""
    }`;
    card.setAttribute("role", "listitem");
    card.dataset.sampleId = sample.sample_id;
    const label = isNatural ? "Natural speech sample" : "Enrollment phrase";
    const textClass = isNatural ? "enroll-sample-text natural" : "enroll-sample-text";
    card.innerHTML = `
      <div class="enroll-sample-top">
        <div>
          <span class="enroll-sample-label">${label}</span>
          <p class="${textClass}">${escapeHtml(sample.prompt_text || "")}</p>
        </div>
        <span class="enroll-sample-status">${sampleStatusLabel(statusKey)}</span>
      </div>
    `;
    if (isNatural) {
      const textEl = card.querySelector(".enroll-sample-text");
      textEl.setAttribute(
        "aria-label",
        "Natural speech exercise. Speak naturally for about ten seconds about your day. Do not read this instruction aloud; describe anything you did in your own words."
      );
    }
    if (!voiceEnrolled) {
      const actions = document.createElement("div");
      actions.className = "enroll-sample-actions";
      const recordBtn = document.createElement("button");
      recordBtn.type = "button";
      recordBtn.className = "settings-action";
      recordBtn.textContent =
        statusKey === "accepted" ? "Record again" : "Record";
      recordBtn.disabled = !modelsReady || voiceActive || recordingBusy;
      recordBtn.addEventListener("click", () =>
        recordEnrollmentSample(sample.sample_id)
      );
      actions.appendChild(recordBtn);
      if (statusKey === "accepted" || statusKey === "needs_retry") {
        const resetBtn = document.createElement("button");
        resetBtn.type = "button";
        resetBtn.className = "settings-action";
        resetBtn.textContent = "Reset";
        resetBtn.disabled = !modelsReady || recordingBusy;
        resetBtn.addEventListener("click", () =>
          resetEnrollmentSample(sample.sample_id)
        );
        actions.appendChild(resetBtn);
      }
      card.appendChild(actions);
    }
    if (sample.quality_message && statusKey !== "accepted") {
      const note = document.createElement("p");
      note.className = "hint";
      note.textContent = sample.quality_message;
      card.appendChild(note);
    }
    els.enrollPhrases.appendChild(card);
  });
}

function updateThemeButton() {
  const preference = resolvedThemePreference();
  els.themeOptions.forEach((button) => {
    const active = button.dataset.themeValue === preference;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
}

function setSettingsCategory(category, { focusProvider = null } = {}) {
  settingsCategory = category || "general";
  localStorage.setItem("marvin-settings-category", settingsCategory);
  els.settingsNavItems.forEach((button) => {
    if (!button.classList.contains("settings-nav-item")) return;
    const selected = button.dataset.settingsCategory === settingsCategory;
    button.setAttribute("aria-selected", String(selected));
  });
  els.settingsPanels.forEach((panel) => {
    panel.hidden = panel.dataset.settingsCategory !== settingsCategory;
  });
  if (settingsCategory === "providers") {
    refreshProviders({ focusProvider });
  }
  if (settingsCategory === "general") {
    refreshVaultStatus();
    refreshSpeechSettings();
  }
  if (settingsCategory === "voice") {
    refreshVoiceProfile();
  }
  if (settingsCategory === "spotify") {
    refreshSpotifyStatus();
  }
  if (settingsCategory === "scrambler") {
    refreshScramblerStatus();
  }
  if (settingsCategory === "skills") {
    refreshSkillsStatus();
  }
}

function setSettingsOpen(
  open,
  { focusProvider = null, category = null } = {}
) {
  els.settingsBtn.setAttribute("aria-expanded", String(open));
  els.settingsBtn.classList.toggle("active", open);
  if (open) {
    settingsOpener = document.activeElement;
    const nextCategory =
      category || (focusProvider ? "providers" : settingsCategory || "general");
    setSettingsCategory(nextCategory, { focusProvider });
    if (typeof els.settingsDialog.showModal === "function") {
      els.settingsDialog.showModal();
    }
    if (focusProvider) {
      requestAnimationFrame(() => {
        const input = els.providerCards?.querySelector(
          `[data-provider-id="${focusProvider}"] .provider-key-input`
        );
        input?.focus();
      });
    } else {
      els.settingsDialog
        .querySelector(`.settings-nav-item[data-settings-category="${nextCategory}"]`)
        ?.focus();
    }
  } else if (els.settingsDialog.open) {
    els.settingsDialog.close();
    settingsOpener?.focus?.();
    settingsOpener = null;
  }
}

function setModelMenuOpen(open) {
  if (!els.modelMenu || !els.modelBtn) return;
  els.modelMenu.hidden = !open;
  els.modelBtn.setAttribute("aria-expanded", String(open));
  if (open) renderModelMenu();
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

let spotifyState = {
  enabled: true,
  client_configured: false,
  connected: false,
  display_name: "",
  hint: "",
};

function renderSpotifyStatus() {
  if (!els.spotifyStatusLine) return;
  const connected = !!spotifyState.connected;
  const configured = !!spotifyState.client_configured;
  if (!configured) {
    els.spotifyStatusLine.textContent = "Not configured";
  } else if (connected) {
    const name = spotifyState.display_name
      ? `Connected as ${spotifyState.display_name}`
      : "Connected";
    els.spotifyStatusLine.textContent = name;
  } else {
    els.spotifyStatusLine.textContent = "Not connected";
  }
  if (els.spotifyHint) {
    els.spotifyHint.textContent =
      spotifyState.hint ||
      "Connect Spotify to control playback. Premium and an open Spotify app are required.";
  }
  if (els.spotifyAccountLine) {
    els.spotifyAccountLine.textContent = connected
      ? "OAuth tokens are stored in the system keychain"
      : "Tokens stay in the system keychain";
  }
  if (els.spotifyConnectBtn) {
    els.spotifyConnectBtn.disabled = !configured;
    els.spotifyConnectBtn.textContent = connected
      ? "Reconnect Spotify"
      : "Connect Spotify";
  }
  if (els.spotifyDisconnectBtn) {
    els.spotifyDisconnectBtn.disabled = !connected;
  }
}

async function refreshSpotifyStatus() {
  try {
    const res = await fetch("/api/spotify/status");
    if (!res.ok) return;
    spotifyState = { ...spotifyState, ...(await res.json()) };
    renderSpotifyStatus();
  } catch (_) {}
}

async function refreshScramblerStatus() {
  if (!els.scramblerStatusLine) return;
  try {
    const res = await fetch("/api/scrambler/status");
    if (!res.ok) return;
    const data = await res.json();
    const running = !!data.running;
    els.scramblerStatusLine.textContent = running
      ? `Running → ${data.output_device || "output"}`
      : "Stopped";
    if (els.scramblerHint && data.hint) {
      els.scramblerHint.textContent = data.hint;
    }
    if (els.scramblerDeviceSelect) {
      const devices = Array.isArray(data.devices) ? data.devices : [];
      const selected =
        data.output_device_index != null
          ? String(data.output_device_index)
          : els.scramblerDeviceSelect.value;
      els.scramblerDeviceSelect.innerHTML = devices
        .map((d) => {
          const kind =
            d.kind === "virtual"
              ? " — virtual cable"
              : d.kind === "speaker"
                ? " — speakers (avoid)"
                : "";
          return `<option value="${d.index}">${d.index}: ${d.name}${
            d.default ? " (default)" : ""
          }${kind}</option>`;
        })
        .join("");
      if (selected) els.scramblerDeviceSelect.value = selected;
    }
    const settings = data.settings || {};
    if (els.scramblerClarity) {
      const v = Math.round((settings.clarity_disguise ?? 0.65) * 100);
      els.scramblerClarity.value = String(v);
      if (els.scramblerClarityLabel) els.scramblerClarityLabel.textContent = `${v}%`;
    }
    if (els.scramblerStrength) {
      const v = Math.round((settings.enabled_strength ?? 1) * 100);
      els.scramblerStrength.value = String(v);
      if (els.scramblerStrengthLabel) els.scramblerStrengthLabel.textContent = `${v}%`;
    }
    if (els.scramblerMasterGain) {
      const v = Math.round((settings.master_gain ?? 1) * 100);
      els.scramblerMasterGain.value = String(v);
      if (els.scramblerGainLabel) els.scramblerGainLabel.textContent = `${v}%`;
    }
    if (els.scramblerStartBtn) els.scramblerStartBtn.disabled = running;
    if (els.scramblerStopBtn) els.scramblerStopBtn.disabled = !running;
  } catch (_) {}
}

async function saveScramblerSettings(patch) {
  try {
    await fetch("/api/scrambler/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch || {}),
    });
  } catch (_) {}
  refreshScramblerStatus();
}

async function connectSpotify() {
  try {
    if (els.spotifyHint) {
      els.spotifyHint.textContent = "Opening your browser for Spotify login…";
    }
    const res = await fetch("/api/spotify/authorize", { method: "POST" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      alert(data.detail || "Could not start Spotify login");
      await refreshSpotifyStatus();
      return;
    }
    // Desktop pywebview blocks window.open; the API opens the system browser.
    // Keep a browser fallback for running the UI outside the app shell.
    if (!data.opened_browser && data.authorize_url) {
      const popup = window.open(data.authorize_url, "_blank", "noopener,noreferrer");
      if (!popup && els.spotifyHint) {
        els.spotifyHint.textContent =
          "Could not open a browser automatically. Copy this URL from the log, or try again.";
      }
    } else if (els.spotifyHint) {
      els.spotifyHint.textContent =
        "Finish signing in in your browser, then return here. Status updates automatically.";
    }
    // Poll briefly so Settings updates after the browser callback completes.
    let attempts = 0;
    const timer = setInterval(async () => {
      attempts += 1;
      await refreshSpotifyStatus();
      if (spotifyState.connected || attempts >= 45) clearInterval(timer);
    }, 2000);
  } catch (_) {
    alert("Could not start Spotify login");
    await refreshSpotifyStatus();
  }
}

async function disconnectSpotify() {
  try {
    const res = await fetch("/api/spotify/connection", { method: "DELETE" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      alert(data.detail || "Could not disconnect Spotify");
      return;
    }
    spotifyState = { ...spotifyState, ...data };
    renderSpotifyStatus();
  } catch (_) {
    alert("Could not disconnect Spotify");
  }
}

function renderProviderCards() {
  if (!els.providerCards) return;
  els.providerCards.innerHTML = "";
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
    els.providerCards.appendChild(card);
    if (providerState.focusProvider === provider.provider_id) {
      input.focus();
    }
  });
}

function renderModelMenu() {
  if (!els.modelMenu) return;
  const catalog = providerState.catalog || [];
  const selectedProvider = providerState.selected_provider;
  const selectedModel = providerState.selected_model;
  const offline = providerState.network_available === false;
  const lastCloud = providerState.last_cloud_provider;
  els.modelMenu.innerHTML = "";
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
    els.modelMenu.appendChild(section);
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
  els.modelMenu.appendChild(manage);
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

async function recordEnrollmentSample(sampleId = null) {
  enrollBusySampleId = sampleId || "next";
  updateEnrollUI();
  if (els.enrollRecordBtn) {
    els.enrollRecordBtn.textContent = "Recording…";
  }
  try {
    const res = await fetch("/api/voice/enroll/sample", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sample_id: sampleId }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      alert(data.detail || "Recording failed");
      await refreshVoiceProfile();
      return;
    }
    applyVoiceSettings(data);
    enrollPending = data.pending ?? enrollPending;
    enrollRequired = data.required ?? enrollRequired;
  } finally {
    enrollBusySampleId = null;
    if (els.enrollRecordBtn) {
      els.enrollRecordBtn.textContent = "Record next sample";
    }
    updateEnrollUI();
  }
}

async function resetEnrollmentSample(sampleId) {
  const res = await fetch(
    `/api/voice/enroll/sample/${encodeURIComponent(sampleId)}`,
    { method: "DELETE" }
  );
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    alert(data.detail || "Could not reset that sample");
    return;
  }
  applyVoiceSettings(data);
  enrollPending = data.pending ?? enrollPending;
  updateEnrollUI();
}

async function refreshVoiceProfile() {
  try {
    const res = await fetch("/api/voice/settings");
    if (!res.ok) return;
    const data = await res.json();
    applyVoiceSettings(data);
    if (data.instructions) els.enrollInstructions.textContent = data.instructions;
    updateUI();
  } catch (_) {}
}

async function saveVoiceSettings(patch) {
  const res = await fetch("/api/voice/settings", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    alert(data.detail || "Could not save Voice Lock settings");
    await refreshVoiceProfile();
    return;
  }
  applyVoiceSettings(data);
  updateUI();
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderInlineMarkdown(value) {
  let html = escapeHtml(value);
  html = html.replace(
    /\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/gi,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>'
  );
  // Compact source chips such as [S1]
  html = html.replace(
    /\[(S\d+)\]/g,
    '<span class="source-chip" aria-label="Source $1">$1</span>'
  );
  // Autolink bare URLs (e.g. Sources footer) without making the whole message clickable.
  html = html.replace(
    /(^|[\s(])(https?:\/\/[^\s)<]+)(?=$|[\s).,!?:;])/gi,
    '$1<a href="$2" target="_blank" rel="noopener noreferrer">$2</a>'
  );
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/__([^_]+)__/g, "<strong>$1</strong>");
  html = html.replace(/(^|[\s(])\*([^*\n]+)\*(?=$|[\s).,!?:;])/g, "$1<em>$2</em>");
  html = html.replace(/(^|[\s(])_([^_\n]+)_(?=$|[\s).,!?:;])/g, "$1<em>$2</em>");
  return html;
}

function renderMarkdown(markdown) {
  const lines = String(markdown || "").replace(/\r\n?/g, "\n").split("\n");
  const output = [];
  let paragraph = [];
  let listType = null;
  let codeLines = null;
  let codeLanguage = "";

  const flushParagraph = () => {
    if (!paragraph.length) return;
    output.push(`<p>${paragraph.map(renderInlineMarkdown).join("<br>")}</p>`);
    paragraph = [];
  };
  const closeList = () => {
    if (!listType) return;
    output.push(`</${listType}>`);
    listType = null;
  };
  const openList = (type) => {
    if (listType === type) return;
    closeList();
    output.push(`<${type}>`);
    listType = type;
  };

  lines.forEach((line) => {
    const fence = line.match(/^\s*```([a-z0-9_+-]*)\s*$/i);
    if (fence) {
      flushParagraph();
      closeList();
      if (codeLines === null) {
        codeLines = [];
        codeLanguage = fence[1] || "";
      } else {
        const languageClass = codeLanguage
          ? ` class="language-${escapeHtml(codeLanguage)}"`
          : "";
        output.push(
          `<pre><code${languageClass}>${escapeHtml(codeLines.join("\n"))}</code></pre>`
        );
        codeLines = null;
        codeLanguage = "";
      }
      return;
    }
    if (codeLines !== null) {
      codeLines.push(line);
      return;
    }
    if (!line.trim()) {
      flushParagraph();
      closeList();
      return;
    }

    const heading = line.match(/^\s{0,3}(#{1,6})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      closeList();
      const level = heading[1].length;
      output.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
      return;
    }

    const unordered = line.match(/^\s*[-*+]\s+(.+)$/);
    if (unordered) {
      flushParagraph();
      openList("ul");
      output.push(`<li>${renderInlineMarkdown(unordered[1])}</li>`);
      return;
    }

    const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
    if (ordered) {
      flushParagraph();
      openList("ol");
      output.push(`<li>${renderInlineMarkdown(ordered[1])}</li>`);
      return;
    }

    const quote = line.match(/^\s*>\s?(.*)$/);
    if (quote) {
      flushParagraph();
      closeList();
      output.push(`<blockquote>${renderInlineMarkdown(quote[1])}</blockquote>`);
      return;
    }

    closeList();
    paragraph.push(line);
  });

  if (codeLines !== null) {
    output.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
  }
  flushParagraph();
  closeList();
  return output.join("");
}

async function copyText(text, button) {
  try {
    await navigator.clipboard.writeText(text);
  } catch (_) {
    const fallback = document.createElement("textarea");
    fallback.value = text;
    fallback.style.position = "fixed";
    fallback.style.opacity = "0";
    document.body.appendChild(fallback);
    fallback.select();
    document.execCommand("copy");
    fallback.remove();
  }
  button.textContent = "Copied";
  setTimeout(() => {
    button.textContent = "Copy";
  }, 1200);
}

function appendMessage(msg) {
  const welcome = els.chatMessages.querySelector(".welcome");
  if (welcome) welcome.remove();

  const div = document.createElement("div");
  const role = msg.role === "user" ? "user" : "assistant";
  const content = String(msg.content || "");
  const messageId = msg.id || "";
  div.className = `message ${role}`;
  if (messageId) div.dataset.messageId = messageId;

  const body = document.createElement("div");
  body.className = "message-content";
  body.innerHTML = renderMarkdown(content);
  div.appendChild(body);

  const meta = document.createElement("div");
  meta.className = "message-meta";
  const timestamp = document.createElement("span");
  timestamp.className = "timestamp";
  timestamp.textContent = msg.timestamp
    ? new Date(msg.timestamp).toLocaleTimeString()
    : "";
  meta.appendChild(timestamp);

  const actions = document.createElement("div");
  actions.className = "message-meta-actions";
  if (role === "assistant") {
    const copyButton = document.createElement("button");
    copyButton.type = "button";
    copyButton.className = "copy-btn";
    copyButton.textContent = "Copy";
    copyButton.title = "Copy response text";
    copyButton.setAttribute("aria-label", "Copy response text");
    copyButton.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      copyText(content, copyButton);
    });
    copyButton.addEventListener("mousedown", (event) => {
      event.preventDefault();
    });
    actions.appendChild(copyButton);
  }
  if (role === "user" && messageId) {
    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "delete-btn";
    deleteButton.textContent = "Delete";
    deleteButton.title = "Delete this prompt and response";
    deleteButton.setAttribute("aria-label", "Delete this prompt and response");
    deleteButton.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      deleteExchange(messageId);
    });
    deleteButton.addEventListener("mousedown", (event) => {
      event.preventDefault();
    });
    actions.appendChild(deleteButton);
  }
  if (actions.childElementCount) meta.appendChild(actions);
  div.appendChild(meta);

  els.chatMessages.appendChild(div);
  els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
}

async function deleteExchange(messageId) {
  if (!messageId) return;
  const res = await fetch(`/api/chat/history/${encodeURIComponent(messageId)}`, {
    method: "DELETE",
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    alert(data.detail || "Could not delete that exchange");
    return;
  }
  renderHistory(data.messages || []);
}

function renderHistory(messages) {
  clearChatUI();
  if (messages && messages.length) {
    els.chatMessages.innerHTML = "";
    messages.forEach(appendMessage);
  }
}

function clearChatUI() {
  els.chatMessages.innerHTML = `
    <div class="welcome">
      <h3>Hello, I'm Marvin.</h3>
      <p>Press <strong>Start Voice</strong> and speak, or type a message below.</p>
      <p class="hint">Configure Voice Lock in Settings → Voice Lock.</p>
    </div>
  `;
}

async function fetchHistory() {
  const res = await fetch("/api/chat/history");
  const { messages } = await res.json();
  renderHistory(messages);
}

async function sendMessage() {
  const text = els.messageInput.value.trim();
  if (!text || !modelsReady) return;
  els.messageInput.value = "";
  resizeComposer();

  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(
      JSON.stringify({
        event: "send_message",
        data: { text, timezone: clientTimezone },
      })
    );
  } else {
    const res = await fetch("/api/chat/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, timezone: clientTimezone }),
    });
    if (res.ok) {
      const { reply } = await res.json();
      if (reply) appendMessage({ role: "assistant", content: reply });
    }
  }
}

function resizeComposer() {
  els.messageInput.style.height = "auto";
  els.messageInput.style.height = `${Math.min(els.messageInput.scrollHeight, 128)}px`;
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
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});
els.messageInput.addEventListener("input", resizeComposer);
els.voiceBtn.addEventListener("click", toggleVoice);
els.modelBtn?.addEventListener("click", (event) => {
  event.stopPropagation();
  setModelMenuOpen(els.modelMenu.hidden);
});
els.settingsBtn.addEventListener("click", () => {
  setSettingsOpen(!els.settingsDialog.open);
});
els.settingsCloseBtn.addEventListener("click", () => setSettingsOpen(false));
els.settingsDialog.addEventListener("close", () => {
  els.settingsBtn.setAttribute("aria-expanded", "false");
  els.settingsBtn.classList.remove("active");
  if (settingsOpener) {
    settingsOpener.focus?.();
    settingsOpener = null;
  }
});
els.settingsDialog.addEventListener("click", (event) => {
  if (event.target === els.settingsDialog) setSettingsOpen(false);
});
els.settingsNavItems.forEach((button) => {
  if (!button.classList.contains("settings-nav-item")) return;
  button.addEventListener("click", () => {
    setSettingsCategory(button.dataset.settingsCategory);
  });
});
els.themeOptions.forEach((button) => {
  button.addEventListener("click", () => {
    applyThemePreference(button.dataset.themeValue);
  });
});
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  if (resolvedThemePreference() === "system") applyThemePreference("system");
});
els.voiceLockEnabled.addEventListener("change", () => {
  saveVoiceSettings({ voice_lock_enabled: els.voiceLockEnabled.checked });
});
els.voiceLockStrictness.addEventListener("change", () => {
  saveVoiceSettings({ strictness_mode: els.voiceLockStrictness.value });
});
els.voiceLockRequireAddress.addEventListener("change", () => {
  saveVoiceSettings({ require_addressing: els.voiceLockRequireAddress.checked });
});
els.voiceLockContinuation.addEventListener("change", () => {
  saveVoiceSettings({
    contextual_continuation_enabled: els.voiceLockContinuation.checked,
  });
});
els.voiceLockWindow.addEventListener("change", () => {
  const value = Number(els.voiceLockWindow.value);
  saveVoiceSettings({ continuation_window_seconds: value });
});
els.spotifyConnectBtn?.addEventListener("click", () => {
  connectSpotify();
});
els.spotifyDisconnectBtn?.addEventListener("click", () => {
  disconnectSpotify();
});
els.scramblerStartBtn?.addEventListener("click", async () => {
  const device = els.scramblerDeviceSelect?.value || "";
  try {
    await fetch("/api/scrambler/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ output_device: device }),
    });
  } catch (_) {}
  refreshScramblerStatus();
});
els.scramblerStopBtn?.addEventListener("click", async () => {
  try {
    await fetch("/api/scrambler/stop", { method: "POST" });
  } catch (_) {}
  refreshScramblerStatus();
});
els.scramblerResetBtn?.addEventListener("click", () => {
  saveScramblerSettings({ reset: true });
});
els.scramblerClarity?.addEventListener("input", () => {
  const v = Number(els.scramblerClarity.value);
  if (els.scramblerClarityLabel) els.scramblerClarityLabel.textContent = `${v}%`;
});
els.scramblerClarity?.addEventListener("change", () => {
  saveScramblerSettings({
    clarity_disguise: Number(els.scramblerClarity.value) / 100,
  });
});
els.scramblerStrength?.addEventListener("input", () => {
  const v = Number(els.scramblerStrength.value);
  if (els.scramblerStrengthLabel) els.scramblerStrengthLabel.textContent = `${v}%`;
});
els.scramblerStrength?.addEventListener("change", () => {
  saveScramblerSettings({
    enabled_strength: Number(els.scramblerStrength.value) / 100,
  });
});
els.scramblerMasterGain?.addEventListener("input", () => {
  const v = Number(els.scramblerMasterGain.value);
  if (els.scramblerGainLabel) els.scramblerGainLabel.textContent = `${v}%`;
});
els.scramblerMasterGain?.addEventListener("change", () => {
  saveScramblerSettings({
    master_gain: Number(els.scramblerMasterGain.value) / 100,
  });
});

els.speechNationality?.addEventListener("change", () => saveSpeechSettings());
els.speechGender?.addEventListener("change", () => saveSpeechSettings());
els.speechMode?.addEventListener("change", () => saveSpeechSettings());

els.uiScaleSlider?.addEventListener("input", () => {
  applyUiScale(els.uiScaleSlider.value);
});
els.skillsRevealBtn?.addEventListener("click", async () => {
  try {
    await fetch("/api/skills/reveal", { method: "POST" });
  } catch (_) {}
});
els.skillsRefreshBtn?.addEventListener("click", () => refreshSkillsStatus());
els.vaultPathSave?.addEventListener("click", () => saveVaultPath());
els.vaultRequestAccess?.addEventListener("click", () => requestVaultAccess());
els.vaultPathInput?.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    saveVaultPath();
  }
});
els.vaultSetupSaveBtn?.addEventListener("click", async () => {
  if (!els.vaultSetupInput) return;
  const path = els.vaultSetupInput.value.trim();
  if (!path) {
    if (els.vaultSetupStatus) {
      els.vaultSetupStatus.textContent = "Enter a vault folder path.";
    }
    return;
  }
  if (els.vaultPathInput) els.vaultPathInput.value = path;
  await saveVaultPath();
  if (els.vaultSetupDialog?.open) els.vaultSetupDialog.close();
});
els.vaultSetupSkipBtn?.addEventListener("click", () => {
  sessionStorage.setItem("marvin-vault-setup-skipped", "1");
  if (els.vaultSetupDialog?.open) els.vaultSetupDialog.close();
});

els.settingsClearBtn.addEventListener("click", () => {
  const hasMessages = !els.chatMessages.querySelector(".welcome");
  els.settingsClearBtn.disabled = !hasMessages;
  if (!hasMessages) return;
  els.clearDialog.showModal();
});
els.clearCancelBtn.addEventListener("click", () => els.clearDialog.close());
els.clearConfirmBtn.addEventListener("click", async () => {
  await fetch("/api/chat/history", { method: "DELETE" });
  clearChatUI();
  els.clearDialog.close();
});
els.clearDialog.addEventListener("click", (event) => {
  if (event.target === els.clearDialog) els.clearDialog.close();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    if (!els.modelMenu?.hidden) {
      setModelMenuOpen(false);
      event.preventDefault();
    }
  }
});
document.addEventListener("pointerdown", (event) => {
  if (
    els.modelMenu &&
    !els.modelMenu.hidden &&
    !els.modelMenu.contains(event.target) &&
    !els.modelBtn.contains(event.target)
  ) {
    setModelMenuOpen(false);
  }
});

els.enrollRecordBtn.addEventListener("click", () => recordEnrollmentSample());

els.enrollSaveBtn.addEventListener("click", async () => {
  const res = await fetch("/api/voice/enroll/finish", { method: "POST" });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    alert(data.detail || "Could not save profile");
    return;
  }
  applyVoiceSettings(data);
  enrollPending = 0;
  updateUI();
});

els.enrollResetBtn.addEventListener("click", () => {
  els.enrollResetAllDialog.showModal();
});
els.enrollResetAllCancelBtn.addEventListener("click", () =>
  els.enrollResetAllDialog.close()
);
els.enrollResetAllConfirmBtn.addEventListener("click", async () => {
  const res = await fetch("/api/voice/enroll/reset", { method: "POST" });
  const data = await res.json().catch(() => ({}));
  applyVoiceSettings(data);
  enrollPending = data.pending ?? 0;
  updateEnrollUI();
  els.enrollResetAllDialog.close();
});

els.enrollClearBtn.addEventListener("click", () => {
  els.voiceClearDialog.showModal();
});
els.voiceClearCancelBtn.addEventListener("click", () => els.voiceClearDialog.close());
els.voiceClearConfirmBtn.addEventListener("click", async () => {
  const res = await fetch("/api/voice/profile", { method: "DELETE" });
  const data = await res.json().catch(() => ({}));
  applyVoiceSettings({ enrolled: false, ...data });
  enrollPending = 0;
  updateUI();
  els.voiceClearDialog.close();
});
els.voiceClearDialog.addEventListener("click", (event) => {
  if (event.target === els.voiceClearDialog) els.voiceClearDialog.close();
});

els.voiceTestBtn.addEventListener("click", async () => {
  els.voiceTestBtn.disabled = true;
  els.voiceTestBtn.textContent = "Testing…";
  els.voiceTestResult.hidden = false;
  els.voiceTestResult.textContent = "Recording test sample…";
  try {
    const res = await fetch("/api/voice/test", { method: "POST" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      els.voiceTestResult.textContent = data.detail || "Test failed";
      return;
    }
    els.voiceTestResult.textContent = data.accepted
      ? `Accepted (score ${Number(data.score || 0).toFixed(3)})`
      : `Rejected (score ${Number(data.score || 0).toFixed(3)}; ${data.reason || "mismatch"})`;
  } finally {
    els.voiceTestBtn.textContent = "Test Voice Lock";
    updateEnrollUI();
  }
});

applyThemePreference(resolvedThemePreference());
applyUiScale(resolvedUiScale());
connectWebSocket();
updateThemeButton();
refreshProviders();
setSettingsCategory(settingsCategory);

setInterval(async () => {
  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    const becameReady = data.models_ready && !modelsReady;
    modelsReady = !!data.models_ready;
    voiceActive = !!data.listening;
    voiceEnrolled = !!data.voice_enrolled;
    let activityChanged = false;
    if (Array.isArray(data.active_tools)) {
      const next = new Set(data.active_tools);
      if (!setsEqual(activeTools, next)) {
        activeTools = next;
        activityChanged = true;
      }
    }
    if (Array.isArray(data.functions_used)) {
      const next = new Set(
        data.functions_used.filter((id) => id && id !== "chat")
      );
      if (!setsEqual(usedFunctions, next)) {
        usedFunctions = next;
        activityChanged = true;
      }
    }
    if (Array.isArray(data.sticky_tools)) {
      const next = new Set(
        data.sticky_tools.filter((id) => id && id !== "chat")
      );
      if (!setsEqual(stickyTools, next)) {
        stickyTools = next;
        activityChanged = true;
      }
    }
    if (activityChanged) {
      renderFunctions();
      updateToolActivityStatus();
    }
    if (becameReady) {
      updateStatus("idle");
      refreshVoiceProfile();
    } else {
      updateUI();
    }
  } catch (_) {}
}, 3000);

const BOARD_DIRECTIONS = {
  "gpp-head": { voiceIdle: "Start Voice" },
  "chest-plate": { voiceIdle: "Start Voice" },
  "life-ticker": { voiceIdle: "Start Voice" },
  "empty-planet": { voiceIdle: "Voice" },
};

function applyBoardDirection(direction) {
  const next = BOARD_DIRECTIONS[direction] ? direction : "gpp-head";
  if (next === "gpp-head") {
    delete document.documentElement.dataset.direction;
  } else {
    document.documentElement.dataset.direction = next;
  }
  localStorage.setItem("marvin-direction", next);
  document.querySelectorAll("[data-direction-value]").forEach((button) => {
    const active = button.dataset.directionValue === next;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  if (!voiceActive && els.voiceBtn) {
    const idle =
      (BOARD_DIRECTIONS[document.documentElement.dataset.direction] ||
        BOARD_DIRECTIONS["gpp-head"]).voiceIdle;
    els.voiceBtn.textContent = idle;
  }
}

document.querySelectorAll("[data-direction-value]").forEach((button) => {
  button.addEventListener("click", () => applyBoardDirection(button.dataset.directionValue));
});
applyBoardDirection(localStorage.getItem("marvin-direction") || "gpp-head");

