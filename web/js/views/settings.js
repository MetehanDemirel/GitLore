// Settings page (editor area): appearance, model, projects, indexing, about.
import { html, useState } from "../../vendor/preact-htm.module.js";
import { api, waitForJob } from "../api.js";
import { Icon } from "../icons.js";
import { t, number } from "../i18n.js";
import { useApp, ConfirmDialog, PromptDialog, Progress } from "../ui.js";

const COMMIT_COUNTS = [100, 200, 500, 1000, 2000, 5000];
const THEMES = ["system", "light", "dark", "dim", "solarized-light", "solarized-dark", "sepia", "contrast-light", "contrast-dark"];

export function SettingsPage() {
  const app = useApp();
  const s = app.settings;
  const [dialog, setDialog] = useState(null);
  const [modelJob, setModelJob] = useState(null);
  const [modelError, setModelError] = useState(null);
  const [custom, setCustom] = useState({ repo: s.custom_repo, file: s.custom_file });
  const [newPath, setNewPath] = useState("");
  const [addError, setAddError] = useState(null);

  const downloadModel = async () => {
    setModelError(null);
    try {
      const { job } = await api.post("/api/model/download");
      await waitForJob(job, setModelJob);
      app.reload();
    } catch (e) { setModelError(e.message); }
    setModelJob(null);
  };
  const addProject = async (e) => {
    e.preventDefault();
    setAddError(null);
    try {
      const project = await app.addProject(newPath);
      setNewPath("");
      app.openProject(project.id);
    } catch (err) { setAddError(err.message); }
  };
  const reindex = async (rebuild) => {
    const { job } = await api.post(`/api/projects/${app.project.id}/index`, { rebuild });
    app.trackIndexJob(app.project.id, job);
  };

  return html`<div class="settings" aria-labelledby="settings-title">
    <h1 id="settings-title" class="sr-only">${t("settings.title")}</h1>

    <section aria-labelledby="s-appearance">
      <h2 id="s-appearance">${t("settings.appearance")}</h2>
      <label class="field"><span>${t("settings.language")}</span>
        <select class="select" style="max-width:280px" value=${s.language} onChange=${(e) => app.setLanguage(e.target.value)}>
          ${Object.entries(app.languages).map(([code, name]) => html`<option value=${code}>${name}</option>`)}
        </select>
        <p class="hint">${t("settings.languageNote")}</p>
      </label>
      <div class="field"><span>${t("settings.theme")}</span>
        <div class="theme-grid" role="radiogroup" aria-label=${t("settings.theme")}>
          ${THEMES.map((k) => html`<button type="button" role="radio" aria-checked=${s.theme === k} class="theme-card"
              onClick=${() => app.setThemeSetting(k)}>
            <span class="theme-swatch" data-preview=${k === "system" ? "" : k} aria-hidden="true"><i></i><i></i><i></i></span>
            <span>${t("settings.theme." + k)}</span></button>`)}
        </div>
      </div>
    </section>

    <section aria-labelledby="s-model">
      <h2 id="s-model">${t("settings.model")}</h2>
      <div class="segmented" role="group" aria-label=${t("settings.modelSource")} style="margin-bottom:12px">
        <button aria-pressed=${s.model_source !== "server"} onClick=${() => app.updateSettings({ model_source: "builtin" })}>${t("settings.builtin")}</button>
        <button aria-pressed=${s.model_source === "server"} onClick=${() => app.updateSettings({ model_source: "server" })}>${t("settings.localServer")}</button>
      </div>
      ${s.model_source === "server" ? html`<${LocalServer} />` : html`
      <label class="field"><span class="sr-only">${t("settings.model")}</span>
        <select class="select" style="max-width:420px" value=${s.preset} onChange=${(e) => app.updateSettings({ preset: e.target.value })}>
          ${Object.entries(app.presets).map(([k, p]) => html`<option value=${k}>${p.label}</option>`)}
          <option value="custom">${t("settings.customModel")}</option>
        </select>
      </label>
      ${s.preset === "custom" && html`<div style="max-width:420px">
        <label class="field"><span>${t("settings.customRepo")}</span>
          <input class="input" value=${custom.repo} placeholder="owner/model-GGUF…" spellcheck="false" autocomplete="off"
            onInput=${(e) => setCustom({ ...custom, repo: e.target.value })} /></label>
        <label class="field"><span>${t("settings.customFile")}</span>
          <input class="input" value=${custom.file} placeholder="model-Q4_K_M.gguf…" spellcheck="false" autocomplete="off"
            onInput=${(e) => setCustom({ ...custom, file: e.target.value })} /></label>
        <p class="hint">${t("settings.customNote")}</p>
        <button class="btn" style="margin:8px 0 12px" onClick=${() => app.updateSettings({ custom_repo: custom.repo, custom_file: custom.file })}>
          ${t("settings.useCustom")}</button>
      </div>`}
      <p class=${app.model.downloaded ? "" : "muted"}>${app.model.downloaded
        ? t("settings.modelReady", { size: number(app.model.size_gb, 1) })
        : t("settings.modelMissing", { size: number(app.model.size_gb, 1) })}</p>
      ${modelJob && html`<div style="max-width:420px;margin-bottom:10px"><${Progress} value=${modelJob.total ? (modelJob.done / modelJob.total) * 100 : 0} /></div>`}
      ${modelError && html`<p class="error-box">${modelError}</p>`}
      ${app.model.downloaded
        ? html`<button class="btn danger" onClick=${() => setDialog("model")}><${Icon} name="trash" /> ${t("settings.removeModel")}</button>`
        : html`<button class="btn primary" disabled=${!!modelJob} onClick=${downloadModel}><${Icon} name="download" /> ${t("settings.downloadModel")}</button>`}`}
    </section>

    <section aria-labelledby="s-projects">
      <h2 id="s-projects">${t("settings.projects")}</h2>
      ${app.projects.map((p) => html`<div class="project-row" key=${p.id}>
        <${Icon} name="repo" />
        <div class="grow">
          <div class="row"><strong>${p.name}</strong>${p.is_demo && html`<span class="tag">${t("project.demo")}</span>`}</div>
          <div class="path mono" title=${p.path}>${p.path}</div>
        </div>
        <button class="btn" onClick=${() => setDialog({ rename: p })}>${t("settings.renameProject")}</button>
        ${!p.is_demo && html`<button class="btn danger" onClick=${() => setDialog({ remove: p })}>${t("settings.removeProject")}</button>`}
      </div>`)}
      <p class="hint">${t("settings.removeProjectNote")}</p>
      <form class="row" style="margin-top:12px;max-width:640px" onSubmit=${addProject}>
        <label class="sr-only" for="new-project">${t("settings.projectPath")}</label>
        <input id="new-project" class="input grow" value=${newPath} placeholder=${t("settings.projectPathPlaceholder")}
          spellcheck="false" autocomplete="off" onInput=${(e) => setNewPath(e.target.value)} />
        <button class="btn primary" disabled=${!newPath.trim()}><${Icon} name="plus" /> ${t("settings.addProject")}</button>
      </form>
      ${addError && html`<p class="error-box" style="margin-top:8px;max-width:640px" role="alert">${addError}</p>`}
    </section>

    ${app.project && html`<section aria-labelledby="s-index">
      <h2 id="s-index">${t("settings.indexing")}: ${app.project.name}</h2>
      <label class="field"><span>${t("settings.commitCount")}</span>
        <select class="select" style="max-width:160px" value=${s.commit_count}
          onChange=${(e) => app.updateSettings({ commit_count: Number(e.target.value) })}>
          ${COMMIT_COUNTS.map((n) => html`<option value=${n}>${number(n)}</option>`)}
        </select>
        <p class="hint">${t("settings.commitCountNote")}</p>
      </label>
      <div class="row">
        <button class="btn" onClick=${() => reindex(false)}><${Icon} name="refresh" /> ${t("settings.updateIndex")}</button>
        <button class="btn" onClick=${() => setDialog("rebuild")}>${t("settings.rebuildIndex")}</button>
        <span class="muted">${t("project.indexed", { n: number(app.project.indexed) })}</span>
      </div>
    </section>`}

    <section aria-labelledby="s-online">
      <h2 id="s-online">${t("settings.online")}</h2>
      <p class="muted">${t("settings.onlineNote")}</p>
      <button class="btn" onClick=${app.showAddOnline}><${Icon} name="cloud" /> ${t("online.addTitle")}</button>
      <p class="hint" style="margin-top:10px">${t("settings.onlineToken")}</p>
    </section>

    <section aria-labelledby="s-keys">
      <h2 id="s-keys">${t("settings.shortcuts")}</h2>
      <table class="table keys"><tbody>
        ${[["Ctrl+B", "panels.toggleSidebar"], ["Ctrl+Alt+B", "nav.assistant"], ["Ctrl+K Z", "panels.zen"], ["Esc", "panels.exitZen"],
           ["Ctrl+P", "changes.openFile"], ["Ctrl+S", "changes.save"], ["Ctrl+Enter", "changes.commit"]].map(([k, label]) =>
          html`<tr><td><kbd>${k}</kbd></td><td>${t(label)}</td></tr>`)}
      </tbody></table>
    </section>

    <section aria-labelledby="s-about">
      <h2 id="s-about">${t("settings.about")}</h2>
      <p>${t("settings.version", { version: app.version })}</p>
      <p class="muted">${t("settings.private")}</p>
    </section>

    ${dialog === "model" && html`<${ConfirmDialog} title=${t("confirm.removeModel.title")}
      body=${t("confirm.removeModel.body", { file: app.model.filename, size: number(app.model.size_gb, 1) })}
      action=${t("confirm.removeModel.action")} onClose=${() => setDialog(null)}
      onConfirm=${async () => { try { await api.del("/api/model"); } catch (e) { app.toast(e.message, true); } app.reload(); }} />`}
    ${dialog === "rebuild" && html`<${ConfirmDialog} title=${t("confirm.rebuild.title")}
      body=${t("confirm.rebuild.body", { n: number(app.project.indexed) })} action=${t("confirm.rebuild.action")}
      onClose=${() => setDialog(null)} onConfirm=${() => reindex(true)} />`}
    ${dialog?.remove && html`<${ConfirmDialog} title=${t("confirm.removeProject.title")}
      body=${t("confirm.removeProject.body", { name: dialog.remove.name })} action=${t("confirm.removeProject.action")}
      onClose=${() => setDialog(null)} onConfirm=${() => app.removeProject(dialog.remove.id)} />`}
    ${dialog?.rename && html`<${PromptDialog} title=${t("settings.renameProject")} label=${t("settings.renameProject")}
      value=${dialog.rename.name} action=${t("common.save")} onClose=${() => setDialog(null)}
      onSubmit=${async (name) => { await api.patch(`/api/projects/${dialog.rename.id}`, { name }); app.reload(); }} />`}
  </div>`;
}

/** A model served by another app on this computer (Ollama, LM Studio, llama.cpp server…). */
function LocalServer() {
  const app = useApp();
  const s = app.settings;
  const [url, setUrl] = useState(s.server_url);
  const [models, setModels] = useState(null);
  const [model, setModel] = useState(s.server_model);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const connect = async () => {
    setBusy(true); setError(null);
    try {
      const res = await api.get(`/api/model/server-models?url=${encodeURIComponent(url)}`);
      setUrl(res.url); setModels(res.models);
      if (!res.models.includes(model)) setModel(res.models[0] || "");
    } catch (e) { setError(e.message); setModels(null); }
    setBusy(false);
  };
  const save = () => app.updateSettings({ server_url: url, server_model: model });

  return html`<div style="max-width:420px">
    <p class="hint">${t("settings.localServerNote")}</p>
    <label class="field"><span>${t("settings.serverUrl")}</span>
      <div class="row" style="gap:6px">
        <input class="input grow" value=${url} placeholder="http://localhost:11434" spellcheck="false" autocomplete="off"
          onInput=${(e) => setUrl(e.target.value)} onKeyDown=${(e) => e.key === "Enter" && connect()} />
        <button class="btn" disabled=${busy} onClick=${connect}>${busy ? t("settings.connecting") : t("settings.connect")}</button>
      </div>
    </label>
    ${error && html`<p class="error-box">${error}</p>`}
    ${models && !models.length && html`<p class="muted">${t("settings.noServerModels")}</p>`}
    ${models && models.length > 0 && html`<label class="field"><span>${t("settings.serverModel")}</span>
      <select class="select" value=${model} onChange=${(e) => setModel(e.target.value)}>
        ${models.map((m) => html`<option value=${m}>${m}</option>`)}
      </select></label>
      <button class="btn primary" style="margin-top:8px" onClick=${save}>${t("settings.useServer")}</button>`}
    <p class=${s.server_model ? "" : "muted"} style="margin-top:10px">${s.server_model
      ? t("settings.serverInUse", { model: s.server_model, url: s.server_url })
      : t("settings.serverNotSet")}</p>
  </div>`;
}
