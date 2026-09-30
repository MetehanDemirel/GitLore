// GitLore web UI — the shell that wires views, state and the local API together.
import { html, render, useEffect, useMemo, useRef, useState } from "../vendor/preact-htm.module.js";
import { api, q, waitForJob } from "./api.js";
import { Icon } from "./icons.js";
import { loadLanguage, t, number } from "./i18n.js";
import { loadMonaco } from "./monaco.js";
import { AppCtx, ConfirmDialog, PromptDialog, Toasts, useApp } from "./ui.js";
import { HistorySidebar, CommitEditor } from "./views/history.js";
import { ChangesSidebar, WorktreeEditor } from "./views/changes.js";
import { SettingsPage } from "./views/settings.js";
import { Assistant } from "./views/assistant.js";

const store = {
  get: (k, d) => { try { return localStorage.getItem(k) ?? d; } catch { return d; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch {} },
};

function resolveTheme(setting) {
  return setting === "dark" || (setting === "system" && matchMedia("(prefers-color-scheme: dark)").matches) ? "dark" : "light";
}

function App({ initial }) {
  const [boot, setBoot] = useState(initial);
  const [view, setView] = useState("history");          // sidebar: history | changes
  const [page, setPage] = useState(null);               // editor override: settings
  const [projectId, setProjectId] = useState(() => {
    const last = initial.settings.last_project;
    return initial.projects.some((p) => p.id === last) ? last : initial.projects[0]?.id;
  });
  const [selection, setSelection] = useState(null);
  const [focus, setFocus] = useState(null);
  const [pendingAsk, setPendingAsk] = useState(null);
  const [sideBySide, setSideBySideState] = useState(store.get("gitlore.sideBySide", "1") === "1");
  const [theme, setTheme] = useState(resolveTheme(initial.settings.theme));
  const [monaco, setMonaco] = useState(null);
  const [editorJob, setEditorJob] = useState(null);
  const [editorError, setEditorError] = useState(null);
  const [toasts, setToasts] = useState([]);
  const [dialog, setDialog] = useState(null);
  const [dirtyPath, setDirty] = useState(null);
  const [changeCount, setChangeCount] = useState(0);
  const [versions, setVersions] = useState({ history: 0, status: 0, commit: 0 });
  const [indexJobs, setIndexJobs] = useState({});
  const [assistantOpen, setAssistantOpen] = useState(store.get("gitlore.assistant", "1") === "1");
  const [offline, setOffline] = useState(false);
  const shell = useRef(null);

  const project = boot.projects.find((p) => p.id === projectId) || boot.projects[0];
  const bump = (key) => setVersions((v) => ({ ...v, [key]: v[key] + 1 }));

  const toast = (text, error = false) => {
    const id = Math.random();
    setToasts((all) => [...all, { id, text, error }]);
    setTimeout(() => setToasts((all) => all.filter((x) => x.id !== id)), error ? 6000 : 2800);
  };
  const reload = async () => {
    try { setBoot(await api.get("/api/state")); } catch (e) { if (e.message === "offline") setOffline(true); }
  };

  // ------------------------------------------------------------------ theme
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    store.set("gitlore.theme", boot.settings.theme);
  }, [theme]);
  useEffect(() => {
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const update = () => setTheme(resolveTheme(boot.settings.theme));
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, [boot.settings.theme]);

  // ------------------------------------------------------------------ editor (Monaco)
  const startEditor = async () => {
    setEditorError(null);
    try {
      if (!boot.editor.ready) {
        const { job } = await api.post("/api/editor/download");
        if (job) await waitForJob(job, setEditorJob);
        setEditorJob(null);
      }
      setMonaco(await loadMonaco(boot.editor.path, boot.settings.language));
    } catch (e) { setEditorError(e.message); setEditorJob(null); }
  };
  useEffect(() => { startEditor(); }, []);

  // ------------------------------------------------------------------ background jobs & heartbeat
  const trackIndexJob = async (pid, jobId) => {
    try {
      await waitForJob(jobId, (job) => setIndexJobs((all) => ({ ...all, [pid]: job })), 600);
    } catch (e) { toast(e.message, true); }
    setIndexJobs((all) => { const { [pid]: _, ...rest } = all; return rest; });
    reload();
  };
  useEffect(() => {
    for (const p of boot.projects) if (p.index_job && !indexJobs[p.id]) trackIndexJob(p.id, p.index_job);
  }, [boot]);
  useEffect(() => {
    const beat = () => api.post("/api/heartbeat").then(() => setOffline(false)).catch(() => setOffline(true));
    beat();
    const timer = setInterval(beat, 10_000);
    return () => clearInterval(timer);
  }, []);

  // ------------------------------------------------------------------ panel resizing
  useEffect(() => {
    const el = shell.current;
    el.style.setProperty("--side-w", store.get("gitlore.sideW", "300") + "px");
    el.style.setProperty("--assist-w", store.get("gitlore.assistW", "380") + "px");
  }, []);
  const startResize = (which) => (e) => {
    e.preventDefault();
    const target = e.currentTarget;
    target.classList.add("dragging");
    const move = (ev) => {
      const w = which === "side" ? ev.clientX - 48 : window.innerWidth - ev.clientX;
      const clamped = Math.round(Math.max(200, Math.min(w, window.innerWidth * 0.45)));
      shell.current.style.setProperty(which === "side" ? "--side-w" : "--assist-w", clamped + "px");
      store.set(which === "side" ? "gitlore.sideW" : "gitlore.assistW", String(clamped));
    };
    const up = () => { target.classList.remove("dragging"); window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  // ------------------------------------------------------------------ actions
  const confirmLeaveEditor = () => !dirtyPath ? Promise.resolve(true) : new Promise((resolve) => setDialog({
    kind: "confirm", title: t("confirm.discard.title"), body: t("confirm.discard.body", { path: dirtyPath }),
    action: t("confirm.discard.action"), onConfirm: () => { setDirty(null); resolve(true); }, onCancel: () => resolve(false),
  }));

  const app = useMemo(() => ({
    version: boot.version, settings: boot.settings, languages: boot.languages, presets: boot.presets,
    model: boot.model, projects: boot.projects, project, selection, focus, pendingAsk, sideBySide, theme, monaco,
    editorJob, editorError, indexJobs, open: { assistant: assistantOpen },
    historyVersion: versions.history, statusVersion: versions.status, commitVersion: versions.commit,
    toast, reload, setFocus, setDirty, setChangeCount, trackIndexJob, confirmLeaveEditor,
    retryEditor: startEditor,
    clearPendingAsk: () => setPendingAsk(null),
    setSideBySide: (v) => { setSideBySideState(v); store.set("gitlore.sideBySide", v ? "1" : "0"); },
    async select(sel) {
      if (!(await confirmLeaveEditor())) return;
      setPage(null);
      setSelection(sel);
    },
    async openProject(id) {
      if (!(await confirmLeaveEditor())) return;
      setProjectId(id); setSelection(null); setFocus(null); setPage(null);
      api.post("/api/settings", { last_project: id });
    },
    async openCommit(hash) {
      try {
        const detail = await api.get(`/api/projects/${project.id}/commits/${hash}`);
        if (!(await confirmLeaveEditor())) return;
        setView("history"); setPage(null);
        setSelection({ kind: "commit", hash: detail.hash, path: detail.files[0]?.path ?? null });
      } catch (e) { toast(e.message, true); }
    },
    askAbout(f, explain) {
      setFocus(f);
      setAssistantOpen(true); store.set("gitlore.assistant", "1");
      setPendingAsk({ focus: f, explain });
    },
    async updateSettings(changes) {
      await api.post("/api/settings", changes).catch((e) => toast(e.message, true));
      await reload();
    },
    async setLanguage(lang) {
      await api.post("/api/settings", { language: lang });
      location.reload(); // Monaco's menus are loaded once per page, in one language
    },
    async setThemeSetting(value) {
      store.set("gitlore.theme", value);
      await api.post("/api/settings", { theme: value });
      await reload();
    },
    async addProject(path) {
      const created = await api.post("/api/projects", { path });
      await reload();
      if (created.index_job) trackIndexJob(created.id, created.index_job);
      return created;
    },
    async removeProject(id) {
      await api.del(`/api/projects/${id}`).catch((e) => toast(e.message, true));
      if (id === project.id) { setProjectId(boot.projects.find((p) => p.is_demo)?.id); setSelection(null); }
      await reload();
    },
    showAddProject: () => setDialog({ kind: "add" }),
    bumpStatus: () => bump("status"),
    async refreshAfterCommit() {
      setVersions((v) => ({ history: v.history + 1, status: v.status + 1, commit: v.commit + 1 }));
      const { job } = await api.post(`/api/projects/${project.id}/index`, {});  // teach the assistant the new commit
      trackIndexJob(project.id, job);
    },
  }), [boot, project, selection, focus, pendingAsk, sideBySide, theme, monaco, editorJob, editorError, indexJobs,
       assistantOpen, versions, dirtyPath]);

  // ------------------------------------------------------------------ layout
  const toggleAssistant = () => { const v = !assistantOpen; setAssistantOpen(v); store.set("gitlore.assistant", v ? "1" : "0"); };
  const activity = (name, label, onClick, pressed, badge) => html`<button aria-label=${label} title=${label}
      aria-current=${pressed === "page" ? "page" : undefined} aria-pressed=${pressed === true ? "true" : pressed === false ? "false" : undefined}
      onClick=${onClick}><${Icon} name=${name} size=${20} />${badge ? html`<span class="badge">${badge}</span>` : null}</button>`;

  const editor = page === "settings" ? html`<${SettingsPage} />`
    : selection?.kind === "commit" ? html`<${CommitEditor} key=${selection.hash} />`
    : selection?.kind === "worktree" ? html`<${WorktreeEditor} key=${selection.path} />`
    : html`<${Welcome} />`;

  const indexJob = project && indexJobs[project.id];
  return html`<${AppCtx.Provider} value=${app}>
    <div class=${"shell" + (assistantOpen ? "" : " no-assistant")} ref=${shell}>
      <nav class="activity" aria-label="GitLore">
        ${activity("history", t("nav.history"), () => { setView("history"); setPage(null); }, view === "history" && page !== "settings" ? "page" : null)}
        ${activity("changes", t("nav.changes"), () => { setView("changes"); setPage(null); }, view === "changes" && page !== "settings" ? "page" : null, changeCount || null)}
        <span class="spacer"></span>
        ${activity("assistant", t("nav.assistant"), toggleAssistant, assistantOpen)}
        ${activity("settings", t("nav.settings"), () => setPage(page === "settings" ? null : "settings"), page === "settings" ? "page" : null)}
      </nav>
      ${view === "history" ? html`<${HistorySidebar} />` : html`<${ChangesSidebar} />`}
      <div class="resizer" role="separator" aria-orientation="vertical" onPointerDown=${startResize("side")}></div>
      <main class="editor-area">${editor}</main>
      <div class="resizer right" role="separator" aria-orientation="vertical" onPointerDown=${startResize("assist")}></div>
      <${Assistant} />
      <footer class="statusbar">
        <span class="item"><${Icon} name="repo" size=${14} />${project?.name}</span>
        ${indexJob && html`<span class="item">${t("status.indexing", { pct: indexJob.total ? Math.round((indexJob.done / indexJob.total) * 100) : 0 })}</span>`}
        ${editorJob && html`<span class="item">${t("status.editor", { pct: editorJob.total ? Math.round((editorJob.done / editorJob.total) * 100) : 0 })}</span>`}
        <span class="grow"></span>
        <button class="item" onClick=${() => setPage("settings")}>${boot.model.downloaded ? t("status.modelReady") : t("status.modelMissing")}</button>
        <button class="item" onClick=${() => setPage("settings")}>${boot.languages[boot.settings.language]}</button>
        <button class="item" onClick=${() => app.setThemeSetting(theme === "dark" ? "light" : "dark")}
          aria-label=${t("settings.theme")}>${t("settings.theme." + boot.settings.theme)}</button>
        <span class="item">${boot.version}</span>
      </footer>
    </div>
    ${offline && html`<div class="backdrop"><div class="dialog" role="alertdialog"><p style="margin:0">${t("common.offline")}</p></div></div>`}
    ${dialog?.kind === "confirm" && html`<${ConfirmDialog} title=${dialog.title} body=${dialog.body} action=${dialog.action}
      onConfirm=${dialog.onConfirm} onClose=${() => { dialog.onCancel?.(); setDialog(null); }} />`}
    ${dialog?.kind === "add" && html`<${PromptDialog} title=${t("settings.addProject")} label=${t("settings.projectPath")}
      placeholder=${t("settings.projectPathPlaceholder")} action=${t("settings.addProject")} onClose=${() => setDialog(null)}
      onSubmit=${async (path) => { const p = await app.addProject(path); app.openProject(p.id); }} />`}
    <${Toasts} toasts=${toasts} />
  <//>`;
}

function Welcome() {
  const app = useApp();
  const openJwt = async () => {
    const hits = await api.get(`/api/projects/${app.project.id}/commits${q({ q: "JWT", limit: 5 })}`).catch(() => []);
    const target = hits.find((c) => c.subject.startsWith("Switch login")) || hits[0];
    if (target) app.openCommit(target.hash);
  };
  return html`<div class="welcome">
    <h1>${t("welcome.title")}</h1>
    <p>${t("welcome.intro")}</p>
    <ol>
      <li>${t("welcome.step1")}</li>
      <li>${t("welcome.step2")}</li>
      <li>${t("welcome.step3")}</li>
    </ol>
    <div class="row wrap">
      ${app.project?.is_demo && html`<button class="btn primary" onClick=${openJwt}><${Icon} name="history" /> ${t("welcome.tryCommit")}</button>`}
      <button class="btn" onClick=${app.showAddProject}><${Icon} name="plus" /> ${t("welcome.openRepo")}</button>
    </div>
  </div>`;
}

// ------------------------------------------------------------------ boot
async function start() {
  const root = document.getElementById("app");
  try {
    const initial = await api.get("/api/state");
    await loadLanguage(initial.settings.language);
    root.removeAttribute("aria-busy");
    root.textContent = "";
    render(html`<${App} initial=${initial} />`, root);
  } catch (e) {
    root.innerHTML = "";
    const p = document.createElement("p");
    p.className = "boot";
    p.textContent = "GitLore isn't running. Start it with start.bat (Windows) or start.sh (macOS / Linux).";
    root.appendChild(p);
  }
}
start();
