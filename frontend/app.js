const ICONS = {
  chat: "C",
  daily_planning: "P",
  web_search: "S",
  obsidian: "O",
  python_runner: "Y",
  voice_lock: "V",
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
let enrollPhrases = [];
let enrollPending = 0;
let enrollRequired = 3;

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
      renderFunctions();
      updateUI();
      break;
    case "history_cleared":
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

function updateStatus(status, step, data = {}) {
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
  els.functionsList.innerHTML = "";
  functions.forEach((fn) => {
    const btn = document.createElement("button");
    btn.className = "function-item" + (fn.id === activeFunction ? " active" : "");
    btn.disabled = !fn.enabled;
    btn.innerHTML = `
      <span class="fn-icon">${ICONS[fn.id] || "*"}</span>
      <div>
        <div class="fn-label">${fn.label}${!fn.enabled ? " (soon)" : ""}</div>
        <div class="fn-desc">${fn.description}</div>
      </div>
    `;
    btn.addEventListener("click", () => selectFunction(fn.id));
    els.functionsList.appendChild(btn);
  });
}

async function selectFunction(id) {
  const res = await fetch("/api/functions/select", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ function_id: id }),
  });
  if (res.ok) {
    activeFunction = id;
    renderFunctions();
    updateUI();
  }
}

function updateUI() {
  const fn = functions.find((f) => f.id === activeFunction);
  els.activeLabel.textContent = fn ? fn.label : "Chat";
  els.voiceBtn.disabled = !modelsReady;
  els.sendBtn.disabled = !modelsReady;
  els.messageInput.disabled = !modelsReady;
  els.voiceBadge.textContent = voiceActive ? "Voice on" : "Voice off";
  els.voiceBadge.classList.toggle("active", voiceActive);
  els.voiceBtn.classList.toggle("listening", voiceActive);
  els.voiceBtn.textContent = voiceActive ? "Stop Voice" : "Start Voice";
  els.voiceLockPill.textContent = voiceEnrolled ? "Voice lock: on" : "Voice lock: off";
  els.voiceLockPill.classList.toggle("on", voiceEnrolled);

  const showEnroll = activeFunction === "voice_lock";
  const composer = document.querySelector(".composer");
  els.enrollPanel.hidden = !showEnroll;
  els.chatMessages.hidden = showEnroll;
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

function clearChatUI() {
  els.chatMessages.innerHTML = `
    <div class="welcome">
      <h3>Hello, I'm Marvin.</h3>
      <p>Press <strong>Start Voice</strong> and speak, or type a message below.</p>
      <p class="hint">Open Voice Lock in the sidebar to teach Marvin your voice.</p>
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
els.clearBtn.addEventListener("click", async () => {
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
