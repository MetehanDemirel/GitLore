// Renders its child only once Monaco is available; shows download/load progress until then.
import { html } from "../../vendor/preact-htm.module.js";
import { t } from "../i18n.js";
import { useApp, Progress } from "../ui.js";

export function EditorGate({ children }) {
  const app = useApp();
  if (app.monaco) return children(app.monaco);
  const job = app.editorJob;
  const pct = job && job.total ? (job.done / job.total) * 100 : 0;
  return html`<div class="placeholder"><div style="width:280px">
    <p>${job ? t("diff.downloadingEditor", { pct: Math.round(pct) }) : t("diff.loadingEditor")}</p>
    ${job && html`<${Progress} value=${pct} />`}
    ${app.editorError && html`<p class="error-box">${app.editorError}</p>
      <button class="btn" onClick=${app.retryEditor}>${t("common.retry")}</button>`}
  </div></div>`;
}
