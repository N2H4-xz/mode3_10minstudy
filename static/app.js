const state = {
  session: null,
  user: null,
  testMode: "learned",
  sending: false,
};

const els = {
  sidebar: document.getElementById("sidebar"),
  openSidebar: document.getElementById("openSidebar"),
  closeSidebar: document.getElementById("closeSidebar"),
  userInput: document.getElementById("userInput"),
  switchUserBtn: document.getElementById("switchUserBtn"),
  currentUserLabel: document.getElementById("currentUserLabel"),
  userProfileInfo: document.getElementById("userProfileInfo"),
  styleNameInput: document.getElementById("styleNameInput"),
  styleFileInput: document.getElementById("styleFileInput"),
  styleImportText: document.getElementById("styleImportText"),
  importStyleBtn: document.getElementById("importStyleBtn"),
  loadUserJsonBtn: document.getElementById("loadUserJsonBtn"),
  userJsonPath: document.getElementById("userJsonPath"),
  userJsonText: document.getElementById("userJsonText"),
  stageStatus: document.getElementById("stageStatus"),
  stagePills: document.getElementById("stagePills"),
  emptyState: document.getElementById("emptyState"),
  testModeBar: document.getElementById("testModeBar"),
  manualTestModeBtn: document.getElementById("manualTestModeBtn"),
  learnedTestModeBtn: document.getElementById("learnedTestModeBtn"),
  collectionIdentityPanel: document.getElementById("collectionIdentityPanel"),
  collectionIdentity: document.getElementById("collectionIdentity"),
  chatPanel: document.getElementById("chatPanel"),
  profilePanel: document.getElementById("profilePanel"),
  profileGrid: document.getElementById("profileGrid"),
  manualFormPanel: document.getElementById("manualFormPanel"),
  scorePanel: document.getElementById("scorePanel"),
  composerWrap: document.getElementById("composerWrap"),
  messageInput: document.getElementById("messageInput"),
  guidanceRow: document.getElementById("guidanceRow"),
  switchTopicBtn: document.getElementById("switchTopicBtn"),
  continueTopicBtn: document.getElementById("continueTopicBtn"),
  sendBtn: document.getElementById("sendBtn"),
  manualSaveBtn: document.getElementById("manualSaveBtn"),
  submitScoreBtn: document.getElementById("submitScoreBtn"),
  manualDialogueBox: document.getElementById("manualDialogueBox"),
  learnedDialogueBox: document.getElementById("learnedDialogueBox"),
  savedPaths: document.getElementById("savedPaths"),
};

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function api(path, payload = null) {
  const options = payload
    ? {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }
    : {};
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || `请求失败：${response.status}`);
  }
  return data;
}

function currentStage() {
  return state.session?.stage || "idle";
}

function closeSidebarOnMobile() {
  if (window.matchMedia("(max-width: 860px)").matches) {
    els.sidebar.classList.remove("open");
  }
}

function stageLabel(stage) {
  return {
    idle: "未开始",
    collect: "语料采集",
    manual_style: "设定风格",
    learned_style: "多轮对话测试",
    score: "评分",
    done: "已完成",
  }[stage] || stage;
}

function setBusy(isBusy, label = "") {
  state.sending = isBusy;
  els.sendBtn.disabled = isBusy;
  els.importStyleBtn.disabled = isBusy;
  els.loadUserJsonBtn.disabled = isBusy;
  els.switchTopicBtn.disabled = isBusy || currentStage() !== "collect";
  els.continueTopicBtn.disabled = isBusy || currentStage() !== "collect";
  els.manualSaveBtn.disabled = isBusy || currentStage() !== "manual_style";
  renderTestModeControls();
  if (label) {
    els.stageStatus.textContent = label;
  } else {
    renderStage();
  }
}

function activeProfile(user) {
  return user?.profiles?.find((profile) => profile.active) || null;
}

function renderUser() {
  const user = state.user;
  const userId = user?.user_id || els.userInput.value.trim() || localStorage.getItem("stylelab_user") || "local_user";
  if (user) {
    els.userInput.value = user.user_id;
  }
  els.currentUserLabel.textContent = user?.user_id || userId;
  const profile = activeProfile(user);
  if (!user) {
    els.userProfileInfo.textContent = "未载入用户";
  } else if (profile) {
    const total = profile.raw_stats?.total_chars || 0;
    els.userProfileInfo.textContent = `当前用户：${user.user_id}；已载入风格：${profile.name}（${total} 字语料）`;
  } else {
    els.userProfileInfo.textContent = `当前用户：${user.user_id}；还没有导入或学习完成的风格`;
  }
}

function setManualForm(form = {}) {
  document.getElementById("identity").value = form.identity || "";
  document.getElementById("languageStyle").value = form.language_style || "";
  document.getElementById("constraints").value = form.constraints || "";
}

function currentCollectionIdentity() {
  return (state.session?.collection_identity || state.user?.collection_identity || "").trim();
}

function renderCollectionIdentity() {
  if (document.activeElement === els.collectionIdentity) return;
  els.collectionIdentity.value = currentCollectionIdentity();
}

function renderManualForm() {
  if (currentStage() !== "manual_style") return;
  setManualForm(state.session?.manual_style_form || state.user?.manual_style_form || {});
}

function renderTestModeControls() {
  const isManual = state.testMode === "manual";
  const disabled = state.sending || currentStage() !== "learned_style";
  els.manualTestModeBtn.classList.toggle("active", isManual);
  els.learnedTestModeBtn.classList.toggle("active", !isManual);
  els.manualTestModeBtn.disabled = disabled;
  els.learnedTestModeBtn.disabled = disabled;
}

function setTestMode(mode) {
  if (state.sending) return;
  state.testMode = mode === "manual" ? "manual" : "learned";
  renderAll();
}

function renderStage() {
  const stage = currentStage();
  els.stageStatus.textContent = stageLabel(stage);
  document.querySelectorAll(".pill").forEach((pill) => {
    pill.classList.toggle("active", pill.dataset.stage === stage || (stage === "done" && pill.dataset.stage === "score"));
  });
  document.querySelectorAll(".mode-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.stage === stage || (stage === "done" && item.dataset.stage === "score"));
  });
  els.emptyState.classList.toggle("hidden", Boolean(state.session));
  els.chatPanel.classList.toggle("hidden", !["collect", "learned_style"].includes(stage));
  const testTurnsStarted = Boolean(
    state.session?.learned_style_dialogue?.length || state.session?.manual_style_dialogue?.length
  );
  const showProfilePanel = Boolean(state.session?.style_profile)
    && stage !== "manual_style"
    && !(stage === "learned_style" && testTurnsStarted);
  els.profilePanel.classList.toggle("hidden", !showProfilePanel);
  els.testModeBar.classList.toggle("hidden", stage !== "learned_style");
  els.collectionIdentityPanel.classList.toggle("hidden", stage !== "collect");
  els.manualFormPanel.classList.toggle("hidden", stage !== "manual_style");
  els.scorePanel.classList.toggle("hidden", !["score", "done"].includes(stage));
  els.composerWrap.classList.toggle("hidden", !["collect", "learned_style"].includes(stage));
  els.messageInput.disabled = !["collect", "learned_style"].includes(stage);
  els.guidanceRow.classList.toggle("hidden", stage !== "collect");
  els.messageInput.placeholder = stage === "collect"
    ? "输入你的回答，开始采集说话风格"
    : state.testMode === "manual"
      ? "输入消息，和第一种 LLM 多轮对话"
      : "输入消息，和第二种 LLM 多轮对话";
  els.sendBtn.disabled = !["collect", "learned_style"].includes(stage);
  els.switchTopicBtn.disabled = stage !== "collect";
  els.continueTopicBtn.disabled = stage !== "collect";
  els.manualSaveBtn.disabled = stage !== "manual_style";
  renderTestModeControls();
}

function renderChat() {
  const session = state.session;
  els.chatPanel.innerHTML = "";
  if (!session) return;
  if (currentStage() === "learned_style") {
    const dialogue = state.testMode === "manual"
      ? (session.manual_style_dialogue || [])
      : (session.learned_style_dialogue || []);
    const label = state.testMode === "manual" ? "第一种对话" : "第二种对话";
    const turns = Math.floor(dialogue.length / 2);
    els.chatPanel.insertAdjacentHTML(
      "beforeend",
      `<div class="system-chip">${label} · 已完成 ${turns} 轮；两种测试模式上下文互不共享</div>`
    );
    dialogue.forEach((item) => {
      els.chatPanel.insertAdjacentHTML(
        "beforeend",
        `<div class="message-row ${item.role}"><div class="bubble">${escapeHtml(item.content)}</div></div>`
      );
    });
    return;
  }
  const totalChars = session.collected_user_messages.reduce((sum, item) => sum + item.length, 0);
  const turns = session.collected_user_messages.length;
  els.chatPanel.insertAdjacentHTML(
    "beforeend",
    `<div class="system-chip">已收集 ${totalChars} 字 / 目标 400 字 · ${turns} 轮</div>`
  );
  session.collection_dialogue.forEach((item) => {
    els.chatPanel.insertAdjacentHTML(
      "beforeend",
      `<div class="message-row ${item.role}"><div class="bubble">${escapeHtml(item.content)}</div></div>`
    );
  });
}

function renderProfile() {
  const profile = state.session?.style_profile;
  if (!profile) return;
  els.profileGrid.innerHTML = "";
  Object.values(profile.characteristics).forEach((item) => {
    els.profileGrid.insertAdjacentHTML(
      "beforeend",
      `<article class="profile-item"><h3>${escapeHtml(item.label)} · ${escapeHtml(item.confidence)}</h3><p>${escapeHtml(item.value)}</p></article>`
    );
  });
}

function renderDialogueBox(box, dialogue) {
  box.innerHTML = "";
  dialogue.forEach((item) => {
    const role = item.role === "user" ? "用户" : "LLM";
    box.insertAdjacentHTML(
      "beforeend",
      `<div class="dialogue-line"><strong>${role}：</strong>${escapeHtml(item.content)}</div>`
    );
  });
}

function renderScore() {
  if (!state.session) return;
  const manualDialogue = state.session.manual_style_dialogue || [];
  const learnedDialogue = state.session.learned_style_dialogue || [];
  renderDialogueBox(els.manualDialogueBox, manualDialogue);
  renderDialogueBox(els.learnedDialogueBox, learnedDialogue);
  document.getElementById("manualScore").disabled = !manualDialogue.length;
  document.getElementById("learnedScore").disabled = !learnedDialogue.length;
}

function renderAll() {
  renderUser();
  renderStage();
  renderCollectionIdentity();
  renderChat();
  renderProfile();
  renderManualForm();
  renderScore();
}

async function switchUser() {
  if (state.sending) return;
  const userId = els.userInput.value.trim();
  if (!userId) {
    alert("请输入用户名称。");
    return;
  }
  setBusy(true, "正在切换用户...");
  try {
    const data = await api("/api/user/switch", { user_id: userId });
    state.user = data.user;
    state.session = null;
    localStorage.setItem("stylelab_user", data.user.user_id);
    els.savedPaths.textContent = "";
    els.userJsonPath.textContent = "";
    els.userJsonText.value = "";
    renderAll();
    closeSidebarOnMobile();
  } catch (err) {
    alert(err.message);
  } finally {
    setBusy(false);
  }
}

async function readImportedProfileText() {
  const file = els.styleFileInput.files?.[0];
  if (file) {
    return file.text();
  }
  return els.styleImportText.value.trim();
}

async function importStyleProfile() {
  const userId = (state.user?.user_id || els.userInput.value || "local_user").trim();
  const rawText = await readImportedProfileText();
  if (!rawText) {
    alert("请选择 JSON 文件，或粘贴 style_profile JSON。");
    return;
  }
  let profile;
  try {
    profile = JSON.parse(rawText);
  } catch (err) {
    alert("导入内容不是合法 JSON。");
    return;
  }
  setBusy(true, "正在导入风格画像...");
  try {
    const data = await api("/api/user/import-style", {
      user_id: userId,
      profile_name: els.styleNameInput.value.trim() || "导入风格",
      profile,
      session_id: state.session?.user_id === userId ? state.session.session_id : null,
    });
    state.user = data.user;
    if (data.session) {
      state.session = data.session;
    }
    localStorage.setItem("stylelab_user", data.user.user_id);
    els.styleImportText.value = "";
    els.styleFileInput.value = "";
    renderAll();
    closeSidebarOnMobile();
  } catch (err) {
    alert(err.message);
  } finally {
    setBusy(false);
  }
}

async function loadUserJson() {
  const userId = (state.user?.user_id || els.userInput.value || "local_user").trim();
  if (!userId) {
    alert("请输入用户名称。");
    return;
  }
  setBusy(true, "正在读取当前用户 JSON...");
  try {
    const data = await api("/api/user/raw", { user_id: userId });
    els.userJsonPath.textContent = data.path || "";
    els.userJsonText.value = JSON.stringify(data.user_json, null, 2);
  } catch (err) {
    alert(err.message);
  } finally {
    setBusy(false);
  }
}

async function newSession(forceCollect = false) {
  setBusy(true, "正在创建实验...");
  try {
    const userId = state.user?.user_id || localStorage.getItem("stylelab_user") || "local_user";
    const data = await api("/api/session/new", { user_id: userId, force_collect: forceCollect });
    state.session = data.session;
    if (data.user) {
      state.user = data.user;
      localStorage.setItem("stylelab_user", data.user.user_id);
    }
    els.messageInput.value = "";
    els.savedPaths.textContent = "";
    renderAll();
  } catch (err) {
    alert(err.message);
  } finally {
    setBusy(false);
  }
}

async function openMode(targetStage) {
  if (state.sending) return;
  if (targetStage === "collect") {
    await newSession(true);
    closeSidebarOnMobile();
    return;
  }

  if (!state.session) {
    await newSession(false);
  }

  if (targetStage === "manual_style") {
    state.session.stage = "manual_style";
    renderAll();
    closeSidebarOnMobile();
    return;
  }

  if (targetStage === "learned_style") {
    if (!state.session.style_profile) {
      alert("请先在当前用户下导入或采集学习好的语言风格。");
      return;
    }
    state.testMode = "learned";
    state.session.stage = "learned_style";
    renderAll();
    closeSidebarOnMobile();
    return;
  }

  if (targetStage === "score") {
    if (state.session.learned_style_dialogue?.length || state.session.manual_style_dialogue?.length) {
      state.session.stage = "score";
      renderAll();
      closeSidebarOnMobile();
      return;
    }
    alert("请先完成至少一轮测试对话。");
  }
}

async function sendCollectionMessage() {
  if (!state.session || currentStage() !== "collect" || state.sending) return;
  const message = els.messageInput.value.trim();
  if (!message) return;
  setBusy(true, "正在处理语料...");
  try {
    const data = await api("/api/collect/respond", {
      session_id: state.session.session_id,
      message,
      collection_identity: els.collectionIdentity.value.trim(),
    });
    state.session = data.session;
    if (data.user) {
      state.user = data.user;
    }
    els.messageInput.value = "";
    renderAll();
  } catch (err) {
    alert(err.message);
  } finally {
    setBusy(false);
  }
}

async function sendGuidance(action) {
  if (!state.session || currentStage() !== "collect" || state.sending) return;
  setBusy(true, action === "switch_topic" ? "正在换个话题..." : "正在继续当前话题...");
  try {
    const data = await api("/api/collect/guidance", {
      session_id: state.session.session_id,
      action,
    });
    state.session = data.session;
    if (data.user) {
      state.user = data.user;
    }
    renderAll();
  } catch (err) {
    alert(err.message);
  } finally {
    setBusy(false);
  }
}

async function saveCollectionIdentity() {
  if (!state.session || state.sending) return;
  const identity = els.collectionIdentity.value.trim();
  if (identity === (state.session.collection_identity || "")) return;
  try {
    const data = await api("/api/collect/identity", {
      session_id: state.session.session_id,
      collection_identity: identity,
    });
    state.session = data.session;
    if (data.user) {
      state.user = data.user;
    }
    renderAll();
  } catch (err) {
    alert(err.message);
  }
}

function collectForm() {
  return {
    identity: document.getElementById("identity").value.trim(),
    school_status: "",
    situation: "",
    goal: "",
    language_style: document.getElementById("languageStyle").value.trim(),
    constraints: document.getElementById("constraints").value.trim(),
    opening: "",
  };
}

async function saveManualStyle() {
  if (!state.session || currentStage() !== "manual_style") return;
  setBusy(true, "正在保存设定风格...");
  try {
    const data = await api("/api/manual-style/save", {
      session_id: state.session.session_id,
      form: collectForm(),
    });
    state.session = data.session;
    if (data.user) {
      state.user = data.user;
      localStorage.setItem("stylelab_user", data.user.user_id);
    }
    state.testMode = "manual";
    els.messageInput.value = "";
    renderAll();
  } catch (err) {
    alert(err.message);
  } finally {
    setBusy(false);
  }
}

async function sendManualStyleMessage() {
  if (!state.session || currentStage() !== "learned_style") return;
  const message = els.messageInput.value.trim();
  if (!message) {
    alert("请输入要发送的消息。");
    return;
  }
  setBusy(true, "正在生成第一种回复...");
  try {
    const manualData = await api("/api/dialogue/manual-style", {
      session_id: state.session.session_id,
      message,
      form: state.session.manual_style_form || state.user?.manual_style_form || collectForm(),
    });
    state.session = manualData.session;
    els.messageInput.value = "";
    renderAll();
  } catch (err) {
    alert(err.message);
  } finally {
    setBusy(false);
  }
}

async function sendLearnedStyleMessage() {
  if (!state.session || currentStage() !== "learned_style") return;
  const message = els.messageInput.value.trim();
  if (!message) {
    alert("请输入要发送的消息。");
    return;
  }
  setBusy(true, "正在生成第二种回复...");
  try {
    const learnedData = await api("/api/dialogue/learned-style", {
      session_id: state.session.session_id,
      message,
    });
    state.session = learnedData.session;
    els.messageInput.value = "";
    renderAll();
  } catch (err) {
    alert(err.message);
  } finally {
    setBusy(false);
  }
}

async function submitScore() {
  if (!state.session) return;
  setBusy(true, "正在保存评分...");
  try {
    const payload = {
      session_id: state.session.session_id,
    };
    if (state.session.manual_style_dialogue?.length) {
      payload.manual_style_score_0_to_10 = Number(document.getElementById("manualScore").value);
    }
    if (state.session.learned_style_dialogue?.length) {
      payload.learned_style_score_0_to_10 = Number(document.getElementById("learnedScore").value);
    }
    const data = await api("/api/score", payload);
    state.session = data.session;
    els.savedPaths.innerHTML = `已保存：<br>${escapeHtml(data.saved.markdown_path)}<br>${escapeHtml(data.saved.json_path)}`;
    renderAll();
  } catch (err) {
    alert(err.message);
  } finally {
    setBusy(false);
  }
}

els.switchUserBtn.addEventListener("click", switchUser);
els.userInput.addEventListener("blur", () => {
  const userId = els.userInput.value.trim();
  if (userId && userId !== state.user?.user_id) {
    switchUser();
  }
});
els.userInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    switchUser();
  }
});
els.importStyleBtn.addEventListener("click", importStyleProfile);
els.loadUserJsonBtn.addEventListener("click", loadUserJson);
els.collectionIdentity.addEventListener("blur", saveCollectionIdentity);
function handleComposerSend() {
  if (currentStage() === "collect") {
    sendCollectionMessage();
  } else if (currentStage() === "learned_style") {
    if (state.testMode === "manual") {
      sendManualStyleMessage();
    } else {
      sendLearnedStyleMessage();
    }
  }
}

els.sendBtn.addEventListener("click", handleComposerSend);
els.manualTestModeBtn.addEventListener("click", () => setTestMode("manual"));
els.learnedTestModeBtn.addEventListener("click", () => setTestMode("learned"));
els.switchTopicBtn.addEventListener("click", () => sendGuidance("switch_topic"));
els.continueTopicBtn.addEventListener("click", () => sendGuidance("continue_topic"));
els.messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    handleComposerSend();
  }
});
els.manualSaveBtn.addEventListener("click", saveManualStyle);
els.submitScoreBtn.addEventListener("click", submitScore);
els.openSidebar.addEventListener("click", () => els.sidebar.classList.add("open"));
els.closeSidebar.addEventListener("click", () => els.sidebar.classList.remove("open"));
document.querySelectorAll(".mode-item").forEach((item) => {
  item.addEventListener("click", () => openMode(item.dataset.stage));
});

els.userInput.value = localStorage.getItem("stylelab_user") || "local_user";
switchUser();
