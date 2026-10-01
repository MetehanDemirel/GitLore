// The assistant: saved chats per project, streamed answers with clickable commit citations.
import { html, useEffect, useRef, useState } from "../../vendor/preact-htm.module.js";
import { api, streamAnswer, waitForJob } from "../api.js";
import { Icon } from "../icons.js";
import { t, number } from "../i18n.js";
import { renderMarkdown } from "../markdown.js";
import { useApp, ConfirmDialog, PromptDialog, Progress } from "../ui.js";

/** "About selected code in auth.py" or, for a whole commit, "About commit a1b2c3d". */
function focusLabel(f) {
  if (!f.text && f.commit) return t("assistant.focusCommit", { hash: f.commit.slice(0, 7) });
  return t("assistant.focus", { path: f.path || "…" });
}

export function Assistant() {
  const app = useApp();
  const pid = app.project?.id;
  const [chats, setChats] = useState([]);
  const [chatId, setChatId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [listOpen, setListOpen] = useState(false);
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(null);   // {stage, commits, text, error, seconds}
  const [dialog, setDialog] = useState(null);
  const abort = useRef(null);
  const busy = useRef(false);     // an answer is streaming: don't reload messages over it
  const scroller = useRef(null);
  const textarea = useRef(null);

  const loadChats = async (select) => {
    const list = await api.get(`/api/projects/${pid}/chats`);
    setChats(list);
    if (select !== undefined) setChatId(select);
    return list;
  };

  useEffect(() => {
    if (!pid) return;
    abort.current?.abort();
    setRunning(null); setMessages([]); setChatId(null);
    loadChats().then((list) => setChatId(list[0]?.id ?? null)).catch((e) => app.toast(e.message, true));
  }, [pid]);

  useEffect(() => {
    if (busy.current) return;
    if (!chatId) { setMessages([]); return; }
    api.get(`/api/chats/${chatId}/messages`).then(setMessages).catch((e) => app.toast(e.message, true));
  }, [chatId]);

  useEffect(() => { scroller.current?.scrollTo({ top: scroller.current.scrollHeight }); }, [messages, running?.text, running?.stage]);

  // Questions coming from the editor's right-click menu.
  useEffect(() => {
    const request = app.pendingAsk;
    if (!request) return;
    app.clearPendingAsk();
    const questions = { commit: "explain.commitQuestion", change: "explain.changeQuestion" };
    if (request.explain) send(t(questions[request.explain] || "menu.explainQuestion"), request.focus);
    else textarea.current?.focus();
  }, [app.pendingAsk]);

  const send = async (text, focus = app.focus) => {
    const question = (text ?? input).trim();
    if (!question || busy.current) return;
    busy.current = true;
    let id = chatId;
    if (!id) {
      try {
        id = (await api.post(`/api/projects/${pid}/chats`, {})).id;
      } catch (e) {
        busy.current = false;
        app.toast(e.message === "offline" ? t("common.offline") : e.message, true);
        return;
      }
      setChatId(id);
    }
    setInput("");
    app.setFocus(null);
    setMessages((m) => [...m, { role: "user", content: question, focus, id: `u${Date.now()}` }]);
    const state = { stage: "loading", commits: [], text: "", error: null, seconds: null };
    setRunning({ ...state });
    const controller = new AbortController();
    abort.current = controller;
    try {
      await streamAnswer(id, question, focus, (ev) => {
        if (ev.type === "status") state.stage = ev.stage;
        else if (ev.type === "commits") state.commits = ev.commits;
        else if (ev.type === "token") state.text += ev.text;
        else if (ev.type === "done") state.seconds = ev.seconds;
        else if (ev.type === "error") state.error = ev.message;
        setRunning({ ...state });
      }, controller.signal);
    } catch (e) {
      state.error = e.message === "offline" ? t("common.offline") : e.message;
    }
    abort.current = null;
    busy.current = false;
    setRunning(null);
    setMessages(await api.get(`/api/chats/${id}/messages`).catch(() => []));
    if (state.error) app.toast(state.error, true);
    loadChats();
  };

  const stop = () => abort.current?.abort();
  const newChat = () => { abort.current?.abort(); setChatId(null); setMessages([]); setListOpen(false); textarea.current?.focus(); };
  const current = chats.find((c) => c.id === chatId);

  const deleteChat = async () => {
    const id = chatId;
    setDialog(null);             // close first: the dialog reads the chat that is about to disappear
    abort.current?.abort();      // an answer still streaming into this chat
    try {
      await api.del(`/api/chats/${id}`);
    } catch (e) {
      app.toast(e.message, true);
    }
    const list = await loadChats().catch(() => []);
    setChatId(list[0]?.id ?? null);
  };

  const onAnswerClick = (e) => {
    const cite = e.target.closest("[data-hash]");
    if (cite) app.openCommit(cite.dataset.hash);
  };

  if (!app.open.assistant) return null;
  return html`<aside class="assistant" aria-label=${t("assistant.title")}>
    <div class="panel-head">
      <button class="btn" style="flex:1;min-width:0;justify-content:space-between" aria-expanded=${listOpen}
        onClick=${() => setListOpen(!listOpen)} title=${t("assistant.chats")}>
        <span style="overflow:hidden;text-overflow:ellipsis">${current ? current.title : t("assistant.newChat")}</span>
        <${Icon} name="chevron" />
      </button>
      <button class="icon-btn" aria-label=${t("assistant.newChat")} title=${t("assistant.newChat")} onClick=${newChat}><${Icon} name="plus" /></button>
      <button class="icon-btn" aria-label=${app.zen === "chat" ? t("panels.exitZen") : t("panels.focusChat")}
        title=${app.zen === "chat" ? t("panels.exitZen") : t("panels.focusChat")} aria-pressed=${app.zen === "chat"}
        onClick=${() => app.toggleZen("chat")}><${Icon} name="zen" /></button>
      ${current && html`
        <button class="icon-btn" aria-label=${t("assistant.renameChat")} title=${t("assistant.renameChat")}
          onClick=${() => setDialog("rename")}><${Icon} name="edit" /></button>
        <button class="icon-btn" aria-label=${t("assistant.deleteChat")} title=${t("assistant.deleteChat")}
          onClick=${() => setDialog("delete")}><${Icon} name="trash" /></button>`}
    </div>

    ${listOpen ? html`<div class="panel-body chat-list" role="listbox" aria-label=${t("assistant.chats")}>
        ${!chats.length && html`<p class="muted" style="padding:8px">${t("assistant.noChats")}</p>`}
        ${chats.map((c) => html`<button class="file" role="option" aria-selected=${c.id === chatId} aria-current=${c.id === chatId}
            style="padding:8px" onClick=${() => { setChatId(c.id); setListOpen(false); }}>
          <${Icon} name="chat" /><span class="grow" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${c.title}</span>
          <span class="muted">${c.message_count}</span></button>`)}
      </div>`
    : html`<div class="messages" ref=${scroller} onClick=${onAnswerClick} aria-live="polite">
        ${!messages.length && !running && html`<${EmptyChat} onPick=${(s) => send(s)} />`}
        ${messages.map((m) => html`<${Message} key=${m.id} message=${m} />`)}
        ${running && html`<${Running} state=${running} />`}
      </div>`}

    ${!app.model.downloaded && html`<${ModelNotice} />`}

    <form class="composer" onSubmit=${(e) => { e.preventDefault(); send(); }}>
      ${app.focus && html`<span class="focus-chip">
        <span>${focusLabel(app.focus)}</span>
        <button type="button" class="icon-btn" style="width:20px;height:20px" aria-label=${t("assistant.removeFocus")}
          onClick=${() => app.setFocus(null)}><${Icon} name="close" size=${12} /></button></span>`}
      <label class="sr-only" for="ask">${t("assistant.placeholder")}</label>
      <div class="row" style="align-items:flex-end">
        <textarea id="ask" ref=${textarea} class="textarea grow" rows="2" placeholder=${t("assistant.placeholder")}
          value=${input} onInput=${(e) => setInput(e.target.value)}
          onKeyDown=${(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}></textarea>
        ${running
          ? html`<button type="button" class="btn" onClick=${stop}><${Icon} name="stop" /> ${t("assistant.stop")}</button>`
          : html`<button class="btn primary" disabled=${!input.trim() || !app.model.downloaded}><${Icon} name="send" /> ${t("assistant.send")}</button>`}
      </div>
    </form>

    ${dialog === "rename" && html`<${PromptDialog} title=${t("assistant.renameChat")} label=${t("assistant.chatTitle")}
      value=${current.title} action=${t("common.save")} onClose=${() => setDialog(null)}
      onSubmit=${async (title) => { await api.patch(`/api/chats/${chatId}`, { title }); await loadChats(); }} />`}
    ${dialog === "delete" && current && html`<${ConfirmDialog} title=${t("confirm.deleteChat.title")}
      body=${t("confirm.deleteChat.body", { title: current.title })} action=${t("confirm.deleteChat.action")}
      onClose=${() => setDialog(null)} onConfirm=${deleteChat} />`}
  </aside>`;
}

function EmptyChat({ onPick }) {
  const app = useApp();
  return html`<div>
    <p class="muted">${t("assistant.empty")}</p>
    ${app.project?.is_demo && app.model.downloaded && html`<div class="suggestions">
      ${["assistant.suggest1", "assistant.suggest2", "assistant.suggest3"].map((k) =>
        html`<button type="button" onClick=${() => onPick(t(k))}>${t(k)}</button>`)}
    </div>`}
  </div>`;
}

function UsedCommits({ commits, seconds }) {
  const app = useApp();
  if (!commits?.length) return null;
  const label = seconds != null ? t("assistant.usedIn", { n: commits.length, s: number(seconds, 0) }) : t("assistant.used", { n: commits.length });
  return html`<details class="used"><summary><${Icon} name="history" size=${14} /> ${label}</summary>
    <ul>${commits.map((c) => html`<li key=${c.hash}><button type="button" onClick=${() => app.openCommit(c.hash)}
        title=${t("assistant.openCommit", { hash: c.short_hash })}>
      <span class="mono muted">${c.short_hash}</span> <span class="subj">${c.subject}</span> <span class="muted">${c.author}</span>
    </button></li>`)}</ul></details>`;
}

function Message({ message }) {
  if (message.role === "user") {
    return html`<div class="msg user">
      <div class="bubble">${message.content}</div>
      ${(message.focus?.text || message.focus?.commit) && html`<div class="focus-chip" title=${message.focus.text || ""}><span>${focusLabel(message.focus)}</span></div>`}
    </div>`;
  }
  return html`<div class="msg assistant-msg">
    <${UsedCommits} commits=${message.commits} seconds=${message.seconds} />
    ${message.content
      ? html`<div class="answer" dangerouslySetInnerHTML=${{ __html: renderMarkdown(message.content) }}></div>`
      : html`<p class="muted">${t("assistant.stopped")}</p>`}
  </div>`;
}

function Running({ state }) {
  const stageText = state.stage === "reading" ? t("assistant.stage.reading", { n: state.commits.length })
    : state.stage === "searching" ? t("assistant.stage.searching") : t("assistant.stage.loading");
  return html`<div class="msg assistant-msg">
    <${UsedCommits} commits=${state.commits} />
    ${!state.text && html`<div class="stage"><span class="spinner"></span><span>${stageText}</span></div>
      ${state.stage === "reading" && html`<p class="hint">${t("assistant.slowNote")}</p>`}`}
    ${state.text && html`<div class="answer caret" dangerouslySetInnerHTML=${{ __html: renderMarkdown(state.text) }}></div>`}
  </div>`;
}

function ModelNotice() {
  const app = useApp();
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);
  const download = async () => {
    setError(null);
    try {
      const { job: id } = await api.post("/api/model/download");
      await waitForJob(id, setJob);
      app.reload();
    } catch (e) { setError(e.message); setJob(null); }
  };
  const pct = job?.total ? (job.done / job.total) * 100 : 0;
  return html`<div class="notice">
    <p>${t("assistant.noModel")}</p>
    ${job ? html`<p class="hint">${t("assistant.downloading", { done: number(job.done / 1e9, 2), total: number(job.total / 1e9, 2) })}</p>
        <${Progress} value=${pct} />`
      : html`<button class="btn primary" onClick=${download}><${Icon} name="download" /> ${t("assistant.downloadModel")} (${number(app.model.size_gb, 1)} GB)</button>`}
    ${error && html`<p class="error-box" style="margin-top:8px">${error}</p>`}
  </div>`;
}
