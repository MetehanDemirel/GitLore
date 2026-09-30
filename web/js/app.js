// GitLore web UI — the shell that wires views, state and the local API together.
import { html, render, useEffect, useMemo, useRef, useState } from "../vendor/preact-htm.module.js";
import { api, q, waitForJob } from "./api.js";
import { Icon } from "./icons.js";
import { loadLanguage, t, number, relativeTime } from "./i18n.js";
import { loadMonaco } from "./monaco.js";
import { AppCtx, ConfirmDialog, PromptDialog, Toasts, useApp, Dialog, Progress } from "./ui.js";
import { HistorySidebar, CommitEditor } from "./views/history.js";
import { ChangesSidebar, WorktreeEditor } from "./views/changes.js";
import { InsightsSidebar, InsightPage } from "./views/insights.js";
import { StorySidebar, StoryPage } from "./views/story.js";
import { SettingsPage } from "./views/settings.js";
import { Assistant } from "./views/assistant.js";

const store = {
  get: (k, d) => { try { return localStorage.getItem(k) ?? d; } catch { return d; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch {} },
};

export const THEMES = ["system", "light", "dark", "dim", "solarized-light", "solarized-dark", "sepia",
                       "contrast-light", "contrast-dark"];
export const DARK_THEMES = new Set(["dark", "dim", "solarized-dark", "contrast-dark"]);

function resolveTheme(setting) {
  if (setting === "system" || !THEMES.includes(setting)) {
    return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  return setting;
}

const ONLINE_REFRESH_MS = 5 * 60 * 1000;   // live mode: check GitHub for new commits every 5 minutes

function App({ initial }) {
  const [boot, setBoot] = useState(initial);
  const [view, setView] = useState(store.get("gitlore.view", "history"));   // history | changes | insights | story
  const [page, setPage] = useState(null);                                 // editor override: settings
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
  const [sidebarOpen, setSidebarOpen] = useState(store.get("gitlore.sidebar", "1") === "1");
  const [zen, setZen] = useState(null);                                   // null | "editor" | "chat"
  const [historyQuery, setHistoryQuery] = useState("");
  const [visits, setVisits] = useState({});                               // project id -> previous visit
  const [fetchJob, setFetchJob] = useState(null);
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
    document.documentElement.dataset.scheme = DARK_THEMES.has(theme) ? "dark" : "light";
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

  // "What changed since my last visit?": remember the previous visit, then record this one.
  useEffect(() => {
    if (!project || project.id in visits) return;
    api.post(`/api/projects/${project.id}/visit`, {})
      .then((r) => setVisits((v) => ({ ...v, [project.id]: r.previous })))
      .catch(() => {});
  }, [project?.id]);

  // Online projects stay live: fetch from GitHub now and then while the project is open.
  const fetchOnline = async (quiet = false) => {
    if (!project?.online || fetchJob) return;
    try {
      const { job } = await api.post(`/api/projects/${project.id}/fetch`, {});
      const done = await waitForJob(job, setFetchJob, 800);
      setFetchJob(null);
      const n = done.result?.new_commits || 0;
      if (n) { toast(t("online.newCommits", { n })); bump("history"); reload(); }
      else if (!quiet) toast(t("online.upToDate"));
    } catch (e) { setFetchJob(null); if (!quiet) toast(e.message, true); }
  };
  useEffect(() => {
    if (!project?.online) return;
    const timer = setInterval(() => fetchOnline(true), ONLINE_REFRESH_MS);
    return () => clearInterval(timer);
  }, [project?.id, project?.online]);

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

  // ------------------------------------------------------------------ panels, zen & shortcuts
  const toggleSidebar = (open = !sidebarOpen) => { setSidebarOpen(open); store.set("gitlore.sidebar", open ? "1" : "0"); };
  const toggleAssistant = (open = !assistantOpen) => { setAssistantOpen(open); store.set("gitlore.assistant", open ? "1" : "0"); };
  const toggleZen = (mode = "editor") => setZen((z) => (z === mode ? null : mode));
  useEffect(() => {
    let chord = false;
    const onKey = (e) => {
      const mod = e.ctrlKey || e.metaKey;
      if (chord) {
        chord = false;
        if (e.key.toLowerCase() === "z") { e.preventDefault(); toggleZen("editor"); }
        return;
      }
      if (mod && e.key.toLowerCase() === "k" && !e.shiftKey) { chord = true; return; }
      if (mod && e.altKey && e.key.toLowerCase() === "b") { e.preventDefault(); toggleAssistant(); return; }
      if (mod && !e.altKey && e.key.toLowerCase() === "b") { e.preventDefault(); toggleSidebar(); return; }
      if (e.key === "Escape" && zen && !document.querySelector(".backdrop, .monaco-menu")) setZen(null);
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [zen, sidebarOpen, assistantOpen]);

  // ------------------------------------------------------------------ actions
  const confirmLeaveEditor = () => !dirtyPath ? Promise.resolve(true) : new Promise((resolve) => setDialog({
    kind: "confirm", title: t("confirm.discard.title"), body: t("confirm.discard.body", { path: dirtyPath }),
    action: t("confirm.discard.action"), onConfirm: () => { setDirty(null); resolve(true); }, onCancel: () => resolve(false),
  }));

  const showView = (v) => {
    if (v === view && sidebarOpen && !page) { toggleSidebar(false); return; }  // like VS Code: click again to hide
    setView(v); store.set("gitlore.view", v); setPage(null); toggleSidebar(true);
    if (v === "insights" && selection?.kind !== "insight") setSelection({ kind: "insight", section: "overview" });
    if (v === "story" && selection?.kind !== "story") setSelection({ kind: "story", section: "history" });
  };

  const app = useMemo(() => ({
    version: boot.version, settings: boot.settings, languages: boot.languages, presets: boot.presets,
    model: boot.model, projects: boot.projects, project, selection, focus, pendingAsk, sideBySide, theme, monaco,
    editorJob, editorError, indexJobs, open: { assistant: assistantOpen }, zen, historyQuery,
    previousVisit: project ? visits[project.id] : null, fetchJob,
    historyVersion: versions.history, statusVersion: versions.status, commitVersion: versions.commit,
    toast, reload, setFocus, setDirty, setChangeCount, trackIndexJob, confirmLeaveEditor, setHistoryQuery,
    retryEditor: startEditor, toggleZen, toggleSidebar, toggleAssistant, fetchOnline,
    clearPendingAsk: () => setPendingAsk(null),
    setSideBySide: (v) => { setSideBySideState(v); store.set("gitlore.sideBySide", v ? "1" : "0"); },
    async select(sel) {
      if (!(await confirmLeaveEditor())) return;
      setPage(null);
      setSelection(sel);
    },
    async openProject(id) {
      if (!(await confirmLeaveEditor())) return;
      setProjectId(id); setSelection(null); setFocus(null); setPage(null); setHistoryQuery("");
      api.post("/api/settings", { last_project: id });
    },
    async openCommit(hash) {
      try {
        const detail = await api.get(`/api/projects/${project.id}/commits/${hash}`);
        if (!(await confirmLeaveEditor())) return;
        setView("history"); setPage(null); toggleSidebar(true);
        setSelection({ kind: "commit", hash: detail.hash, path: detail.files[0]?.path ?? null });
      } catch (e) { toast(e.message, true); }
    },
    searchHistory(query) {
      setHistoryQuery(query); setView("history"); setPage(null); toggleSidebar(true);
    },
    askAbout(f, explain) {
      setFocus(f);
      toggleAssistant(true);
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
    showAddOnline: () => setDialog({ kind: "online" }),
    bumpStatus: () => bump("status"),
    async refreshAfterCommit() {
      setVersions((v) => ({ history: v.history + 1, status: v.status + 1, commit: v.commit + 1 }));
      const { job } = await api.post(`/api/projects/${project.id}/index`, {});  // teach the assistant the new commit
      trackIndexJob(project.id, job);
    },
  }), [boot, project, selection, focus, pendingAsk, sideBySide, theme, monaco, editorJob, editorError, indexJobs,
       assistantOpen, versions, dirtyPath, zen, historyQuery, visits, fetchJob, sidebarOpen]);

  // ------------------------------------------------------------------ layout
  const activity = (name, label, onClick, pressed, badge) => html`<button aria-label=${label} title=${label}
      aria-current=${pressed === "page" ? "page" : undefined} aria-pressed=${pressed === true ? "true" : pressed === false ? "false" : undefined}
      onClick=${onClick}><${Icon} name=${name} size=${20} />${badge ? html`<span class="badge">${badge}</span>` : null}</button>`;

  const editor = page === "settings" ? html`<${SettingsPage} />`
    : selection?.kind === "commit" ? html`<${CommitEditor} key=${selection.hash} />`
    : selection?.kind === "worktree" ? html`<${WorktreeEditor} key=${selection.path} />`
    : selection?.kind === "insight" ? html`<${InsightPage} />`
    : selection?.kind === "story" ? html`<${StoryPage} />`
    : html`<${Welcome} />`;
  const sidebars = { history: HistorySidebar, changes: ChangesSidebar, insights: InsightsSidebar, story: StorySidebar };
  const Sidebar = sidebars[view] || HistorySidebar;
  const current = (v) => (view === v && sidebarOpen && page !== "settings" ? "page" : null);

  const indexJob = project && indexJobs[project.id];
  const shellClass = ["shell", assistantOpen ? "" : "no-assistant", sidebarOpen ? "" : "no-sidebar",
                      zen ? `zen zen-${zen}` : ""].filter(Boolean).join(" ");
  return html`<${AppCtx.Provider} value=${app}>
    <div class=${shellClass} ref=${shell}>
      <nav class="activity" aria-label="GitLore">
        ${activity("history", t("nav.history"), () => showView("history"), current("history"))}
        ${activity("changes", t("nav.changes"), () => showView("changes"), current("changes"), changeCount || null)}
        ${activity("chart", t("nav.insights"), () => showView("insights"), current("insights"))}
        ${activity("book", t("nav.story"), () => showView("story"), current("story"))}
        <span class="spacer"></span>
        ${activity("assistant", t("nav.assistant"), () => toggleAssistant(), assistantOpen)}
        ${activity("settings", t("nav.settings"), () => setPage(page === "settings" ? null : "settings"), page === "settings" ? "page" : null)}
      </nav>
      <${Sidebar} />
      <div class="resizer" role="separator" aria-orientation="vertical" onPointerDown=${startResize("side")}></div>
      <main class="editor-area">${editor}</main>
      <div class="resizer right" role="separator" aria-orientation="vertical" onPointerDown=${startResize("assist")}></div>
      <${Assistant} />
      <footer class="statusbar">
        <button class="item" onClick=${() => toggleSidebar()} aria-label=${t("panels.toggleSidebar")} title="${t("panels.toggleSidebar")} (Ctrl+B)">
          <${Icon} name="sidebar" size=${14} /></button>
        <span class="item"><${Icon} name=${project?.online ? "cloud" : "repo"} size=${14} />${project?.name}</span>
        ${project?.online && html`<button class="item" onClick=${() => fetchOnline(false)} disabled=${!!fetchJob}>
          <${Icon} name="refresh" size=${14} /> ${fetchJob ? t("online.updating") : t("online.update")}</button>`}
        ${indexJob && html`<span class="item">${t("status.indexing", { pct: indexJob.total ? Math.round((indexJob.done / indexJob.total) * 100) : 0 })}</span>`}
        ${editorJob && html`<span class="item">${t("status.editor", { pct: editorJob.total ? Math.round((editorJob.done / editorJob.total) * 100) : 0 })}</span>`}
        <span class="grow"></span>
        <button class="item" onClick=${() => toggleZen("editor")} aria-pressed=${!!zen} title="${t("panels.zen")} (Ctrl+K Z)">
          <${Icon} name="zen" size=${14} /> ${zen ? t("panels.exitZen") : t("panels.zen")}</button>
        <button class="item" onClick=${() => setPage("settings")}>${boot.model.downloaded ? t("status.modelReady") : t("status.modelMissing")}</button>
        <button class="item" onClick=${() => setPage("settings")}>${boot.languages[boot.settings.language]}</button>
        <button class="item" onClick=${() => setPage("settings")} aria-label=${t("settings.theme")}>${t("settings.theme." + boot.settings.theme)}</button>
        <span class="item">${boot.version}</span>
      </footer>
    </div>
    ${zen && html`<button class="zen-exit" onClick=${() => setZen(null)} title="Esc">${t("panels.exitZen")}</button>`}
    ${offline && html`<div class="backdrop"><div class="dialog" role="alertdialog"><p style="margin:0">${t("common.offline")}</p></div></div>`}
    ${dialog?.kind === "confirm" && html`<${ConfirmDialog} title=${dialog.title} body=${dialog.body} action=${dialog.action}
      onConfirm=${dialog.onConfirm} onClose=${() => { dialog.onCancel?.(); setDialog(null); }} />`}
    ${dialog?.kind === "add" && html`<${PromptDialog} title=${t("settings.addProject")} label=${t("settings.projectPath")}
      placeholder=${t("settings.projectPathPlaceholder")} action=${t("settings.addProject")} onClose=${() => setDialog(null)}
      onSubmit=${async (path) => { const p = await app.addProject(path); app.openProject(p.id); }} />`}
    ${dialog?.kind === "online" && html`<${AddOnlineDialog} onClose=${() => setDialog(null)} />`}
    <${Toasts} toasts=${toasts} />
  <//>`;
}

function AddOnlineDialog({ onClose }) {
  const app = useApp();
  const [url, setUrl] = useState("");
  const [depth, setDepth] = useState(1000);
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);
  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    try {
      const { job: id } = await api.post("/api/online/projects", { url, depth: Number(depth) });
      const done = await waitForJob(id, setJob, 700);
      await app.reload();
      onClose();
      app.openProject(done.result.project);
    } catch (err) { setError(err.message); setJob(null); }
  };
  const stage = job?.message;
  return html`<${Dialog} title=${t("online.addTitle")} onClose=${() => !job && onClose()}>
    <form onSubmit=${submit}>
      <p class="hint" style="margin-top:0">${t("online.addNote")}</p>
      <label class="field"><span>${t("online.url")}</span>
        <input class="input" value=${url} placeholder="github.com/microsoft/vscode" autocomplete="off" spellcheck="false"
          disabled=${!!job} onInput=${(e) => setUrl(e.target.value)} /></label>
      <label class="field"><span>${t("online.depth")}</span>
        <select class="select" value=${depth} disabled=${!!job} onChange=${(e) => setDepth(e.target.value)}>
          ${[200, 1000, 5000, 20000].map((n) => html`<option value=${n}>${t("online.depthN", { n: number(n) })}</option>`)}
        </select><p class="hint">${t("online.depthNote")}</p></label>
      ${job && html`<p class="hint">${stage === "indexing" ? t("online.indexing") : t("online.cloning")}
        ${job.total ? ` ${number(job.done)} / ${number(job.total)}` : ""}</p>
        <${Progress} value=${job.total ? (job.done / job.total) * 100 : 5} />`}
      ${error && html`<p class="error-box" role="alert" style="margin-top:10px">${error}</p>`}
      <div class="actions" style="margin-top:14px">
        <button type="button" class="btn" disabled=${!!job} onClick=${onClose}>${t("confirm.cancel")}</button>
        <button class="btn primary" disabled=${!url.trim() || !!job}><${Icon} name="cloud" /> ${t("online.add")}</button>
      </div>
    </form>
  <//>`;
}

function Welcome() {
  const app = useApp();
  const [since, setSince] = useState(null);
  useEffect(() => {
    setSince(null);
    if (!app.previousVisit || !app.project) return;
    api.get(`/api/projects/${app.project.id}/briefs/away${q({ since: app.previousVisit })}`)
      .then((d) => setSince(d.facts)).catch(() => {});
  }, [app.project?.id, app.previousVisit]);
  const openJwt = async () => {
    const hits = await api.get(`/api/projects/${app.project.id}/commits${q({ q: "JWT", limit: 5 })}`).catch(() => []);
    const target = hits.find((c) => c.subject.startsWith("Switch login")) || hits[0];
    if (target) app.openCommit(target.hash);
  };
  return html`<div class="welcome">
    <h1>${t("welcome.title")}</h1>
    <p>${app.project?.is_demo ? t("welcome.intro") : t("welcome.introOwn", { name: app.project?.name })}</p>
    ${since && since.count > 0 && html`<div class="card catch-up">
      <p><strong>${t("welcome.sinceVisit", { n: number(since.count), when: relativeTime(app.previousVisit) })}</strong></p>
      <button class="btn primary" onClick=${() => app.select({ kind: "story", section: "away" })}><${Icon} name="clock" /> ${t("welcome.catchUp")}</button>
    </div>`}
    <ol>
      <li>${t("welcome.step1")}</li>
      <li>${t("welcome.step2")}</li>
      <li>${t("welcome.step3")}</li>
      <li>${t("welcome.step4")}</li>
    </ol>
    <div class="row wrap">
      ${app.project?.is_demo && html`<button class="btn primary" onClick=${openJwt}><${Icon} name="history" /> ${t("welcome.tryCommit")}</button>`}
      <button class="btn" onClick=${() => app.select({ kind: "story", section: "onboarding" })}><${Icon} name="book" /> ${t("welcome.brief")}</button>
      <button class="btn" onClick=${app.showAddProject}><${Icon} name="plus" /> ${t("welcome.openRepo")}</button>
      <button class="btn" onClick=${app.showAddOnline}><${Icon} name="cloud" /> ${t("welcome.openGithub")}</button>
    </div>
    <p class="hint" style="margin-top:24px">${t("welcome.shortcuts")}</p>
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
