const storageKey = "chat-api-ui-state";

const state = {
  backendUrl: "",
  accessKey: "",
  providers: [],
  activeProvider: "",
  activeModel: "",
  sessions: [],
  activeSessionId: "",
  isSending: false,
};

const elements = {
  loginOverlay: document.querySelector("#loginOverlay"),
  loginForm: document.querySelector("#loginForm"),
  backendUrlInput: document.querySelector("#backendUrlInput"),
  accessKeyInput: document.querySelector("#accessKeyInput"),
  loginError: document.querySelector("#loginError"),
  providerSelect: document.querySelector("#providerSelect"),
  modelSelect: document.querySelector("#modelSelect"),
  composer: document.querySelector("#composer"),
  promptInput: document.querySelector("#promptInput"),
  sendButton: document.querySelector("#sendButton"),
  messages: document.querySelector("#messages"),
  sessionList: document.querySelector("#sessionList"),
  newChatButton: document.querySelector("#newChatButton"),
  logoutButton: document.querySelector("#logoutButton"),
  accountButton: document.querySelector("#accountButton"),
  connectionLabel: document.querySelector("#connectionLabel"),
  openSidebarButton: document.querySelector("#openSidebarButton"),
  closeSidebarButton: document.querySelector("#closeSidebarButton"),
  sidebar: document.querySelector(".sidebar"),
};

function loadSavedState() {
  const raw = localStorage.getItem(storageKey);
  if (!raw) return;

  try {
    const saved = JSON.parse(raw);
    state.backendUrl = saved.backendUrl || "";
    state.activeProvider = saved.activeProvider || "";
    state.activeModel = saved.activeModel || "";
    state.sessions = Array.isArray(saved.sessions) ? saved.sessions : [];
    state.activeSessionId = saved.activeSessionId || "";
  } catch {
    localStorage.removeItem(storageKey);
  }
}

function saveState() {
  localStorage.setItem(
    storageKey,
    JSON.stringify({
      backendUrl: state.backendUrl,
      activeProvider: state.activeProvider,
      activeModel: state.activeModel,
      sessions: state.sessions,
      activeSessionId: state.activeSessionId,
    }),
  );
}

function normalizeBackendUrl(url) {
  return url.trim().replace(/\/+$/, "");
}

function authHeaders(extra = {}) {
  return {
    ...extra,
    Authorization: `Bearer ${state.accessKey}`,
  };
}

async function fetchProviders() {
  const response = await fetch(`${state.backendUrl}/api/providers`, {
    headers: authHeaders(),
  });
  if (!response.ok) {
    throw new Error(await readableError(response));
  }
  const data = await response.json();
  state.providers = data.providers || [];
  if (!state.providers.length) {
    throw new Error("后端没有配置可用 API");
  }

  if (!state.providers.some((provider) => provider.id === state.activeProvider)) {
    state.activeProvider = state.providers[0].id;
  }
  const provider = currentProvider();
  if (!provider.models.includes(state.activeModel)) {
    state.activeModel = provider.default_model || provider.models[0];
  }
}

async function readableError(response) {
  try {
    const data = await response.json();
    return data.detail || response.statusText;
  } catch {
    return response.statusText || "请求失败";
  }
}

function currentProvider() {
  return state.providers.find((provider) => provider.id === state.activeProvider) || state.providers[0];
}

function createId() {
  if (crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function activeSession() {
  return state.sessions.find((session) => session.id === state.activeSessionId);
}

function createSession() {
  const session = {
    id: createId(),
    title: "新对话",
    messages: [],
    createdAt: Date.now(),
  };
  state.sessions.unshift(session);
  state.activeSessionId = session.id;
  saveState();
  render();
}

function ensureSession() {
  if (!state.sessions.length || !activeSession()) {
    createSession();
  }
}

function renderProviderOptions() {
  elements.providerSelect.innerHTML = "";
  elements.modelSelect.innerHTML = "";
  if (!state.providers.length) {
    return;
  }

  for (const provider of state.providers) {
    const option = document.createElement("option");
    option.value = provider.id;
    option.textContent = provider.name;
    option.selected = provider.id === state.activeProvider;
    elements.providerSelect.append(option);
  }

  renderModelOptions();
}

function renderModelOptions() {
  const provider = currentProvider();
  elements.modelSelect.innerHTML = "";
  for (const model of provider.models) {
    const option = document.createElement("option");
    option.value = model;
    option.textContent = model;
    option.selected = model === state.activeModel;
    elements.modelSelect.append(option);
  }
}

function renderSessions() {
  elements.sessionList.innerHTML = "";
  for (const session of state.sessions) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `session-item${session.id === state.activeSessionId ? " active" : ""}`;
    button.dataset.sessionId = session.id;

    const title = document.createElement("span");
    title.textContent = session.title;
    button.append(title);
    elements.sessionList.append(button);
  }
}

function renderMessages() {
  const session = activeSession();
  elements.messages.innerHTML = "";

  if (!session || session.messages.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.innerHTML = "<h2>有什么可以帮忙的？</h2>";
    elements.messages.append(empty);
    return;
  }

  for (const message of session.messages) {
    elements.messages.append(createMessageNode(message));
  }
  elements.messages.scrollTop = elements.messages.scrollHeight;
}

function createMessageNode(message) {
  const row = document.createElement("div");
  row.className = "message-row";

  const item = document.createElement("article");
  item.className = `message ${message.role}`;

  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  avatar.textContent = message.role === "user" ? "U" : "AI";

  const content = document.createElement("div");
  content.className = "message-content";
  if (message.pending) content.classList.add("typing");
  content.textContent = message.content;

  item.append(avatar, content);
  row.append(item);
  return row;
}

function renderConnection() {
  try {
    elements.connectionLabel.textContent = state.backendUrl ? new URL(state.backendUrl).host : "未连接";
  } catch {
    elements.connectionLabel.textContent = "未连接";
  }
}

function render() {
  renderProviderOptions();
  renderSessions();
  renderMessages();
  renderConnection();
  elements.sendButton.disabled = state.isSending;
}

function resizeTextarea() {
  elements.promptInput.style.height = "auto";
  elements.promptInput.style.height = `${Math.min(elements.promptInput.scrollHeight, 180)}px`;
}

async function handleLogin(event) {
  event.preventDefault();
  elements.loginError.textContent = "";
  state.backendUrl = normalizeBackendUrl(elements.backendUrlInput.value);
  state.accessKey = elements.accessKeyInput.value.trim();

  try {
    await fetchProviders();
    elements.loginOverlay.classList.add("hidden");
    elements.accessKeyInput.value = "";
    ensureSession();
    saveState();
    render();
  } catch (error) {
    elements.loginError.textContent = error.message || "连接失败";
  }
}

function logout() {
  state.backendUrl = "";
  state.accessKey = "";
  state.providers = [];
  state.activeProvider = "";
  state.activeModel = "";
  saveState();
  elements.backendUrlInput.value = "http://localhost:8000";
  elements.accessKeyInput.value = "";
  elements.loginOverlay.classList.remove("hidden");
  elements.connectionLabel.textContent = "未连接";
}

async function sendMessage(event) {
  event.preventDefault();
  const text = elements.promptInput.value.trim();
  if (!text || state.isSending) return;

  ensureSession();
  const session = activeSession();
  if (session.title === "新对话") {
    session.title = text.slice(0, 28);
  }

  session.messages.push({ role: "user", content: text });
  const assistantMessage = { role: "assistant", content: "", pending: true };
  session.messages.push(assistantMessage);
  elements.promptInput.value = "";
  resizeTextarea();
  state.isSending = true;
  saveState();
  render();

  try {
    await streamAssistantReply(session, assistantMessage);
  } catch (error) {
    assistantMessage.content = error.message || "请求失败";
  } finally {
    assistantMessage.pending = false;
    state.isSending = false;
    saveState();
    render();
  }
}

async function streamAssistantReply(session, assistantMessage) {
  const requestMessages = session.messages
    .filter((message) => !message.pending)
    .map(({ role, content }) => ({ role, content }));

  const response = await fetch(`${state.backendUrl}/api/chat/stream`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({
      provider: state.activeProvider,
      model: state.activeModel,
      messages: requestMessages,
    }),
  });

  if (!response.ok || !response.body) {
    throw new Error(await readableError(response));
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    buffer = consumeSseBuffer(buffer, assistantMessage);
    updateLastAssistantNode(assistantMessage);
  }

  buffer += decoder.decode();
  consumeSseBuffer(buffer, assistantMessage);
}

function consumeSseBuffer(buffer, assistantMessage) {
  const events = buffer.split(/\r?\n\r?\n/);
  const remainder = events.pop() || "";

  for (const eventText of events) {
    const dataLines = eventText
      .split(/\r?\n/)
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart());

    for (const data of dataLines) {
      if (!data || data === "[DONE]") continue;
      appendDelta(data, assistantMessage);
    }
  }

  return remainder;
}

function appendDelta(data, assistantMessage) {
  try {
    const parsed = JSON.parse(data);
    if (parsed.error) {
      assistantMessage.content += `请求失败：${parsed.error.message || JSON.stringify(parsed.error)}`;
      return;
    }
    if (parsed.detail) {
      assistantMessage.content += `请求失败：${parsed.detail}`;
      return;
    }
    const delta = parsed.choices?.[0]?.delta?.content || "";
    const fallback = parsed.choices?.[0]?.message?.content || "";
    assistantMessage.content += delta || fallback;
  } catch {
    if (data.startsWith("Upstream request failed") || data.startsWith("请求失败")) {
      assistantMessage.content += data;
    }
  }
}

function updateLastAssistantNode(assistantMessage) {
  const nodes = elements.messages.querySelectorAll(".message.assistant .message-content");
  const node = nodes[nodes.length - 1];
  if (!node) return;
  node.textContent = assistantMessage.content;
  elements.messages.scrollTop = elements.messages.scrollHeight;
}

elements.loginForm.addEventListener("submit", handleLogin);
elements.composer.addEventListener("submit", sendMessage);

elements.promptInput.addEventListener("input", resizeTextarea);
elements.promptInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    elements.composer.requestSubmit();
  }
});

elements.providerSelect.addEventListener("change", () => {
  state.activeProvider = elements.providerSelect.value;
  const provider = currentProvider();
  state.activeModel = provider.default_model || provider.models[0];
  saveState();
  render();
});

elements.modelSelect.addEventListener("change", () => {
  state.activeModel = elements.modelSelect.value;
  saveState();
});

elements.sessionList.addEventListener("click", (event) => {
  const button = event.target.closest(".session-item");
  if (!button) return;
  state.activeSessionId = button.dataset.sessionId;
  elements.sidebar.classList.remove("open");
  saveState();
  render();
});

elements.newChatButton.addEventListener("click", () => {
  createSession();
  elements.sidebar.classList.remove("open");
});

elements.logoutButton.addEventListener("click", logout);
elements.accountButton.addEventListener("click", () => {
  elements.loginOverlay.classList.remove("hidden");
});
elements.openSidebarButton.addEventListener("click", () => elements.sidebar.classList.add("open"));
elements.closeSidebarButton.addEventListener("click", () => elements.sidebar.classList.remove("open"));

async function init() {
  loadSavedState();
  elements.backendUrlInput.value = state.backendUrl || "http://localhost:8000";
  elements.accessKeyInput.value = "";
  renderConnection();
}

init();
