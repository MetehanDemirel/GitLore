// Monaco (VS Code's editor): loading, GitLore themes, and the diff view with "Ask GitLore" actions.
import { html, useEffect, useRef } from "../vendor/preact-htm.module.js";
import { t } from "./i18n.js";

let loading = null;

const addScript = (src) => new Promise((resolve, reject) => {
  const script = document.createElement("script");
  script.src = src;
  script.onload = resolve;
  script.onerror = () => reject(new Error("editor files missing"));
  document.head.appendChild(script);
});

/** Load Monaco once, with its menus in `lang` (tr, fr and de ship with Monaco). */
export function loadMonaco(basePath, lang) {
  if (loading) return loading;
  loading = (async () => {
    // Monaco's translations are plain scripts that set globals; they must run before the editor loads.
    if (lang !== "en") await addScript(`${basePath}/nls/lang/${lang}.js`).catch(() => {});
    await addScript(`${basePath}/loader.js`);
    window.require.config({ paths: { vs: basePath } });
    await new Promise((resolve, reject) => window.require(["vs/editor/editor.main"], resolve, reject));
    defineThemes(window.monaco);
    return window.monaco;
  })();
  return loading;
}

function defineThemes(monaco) {
  monaco.editor.defineTheme("gitlore-light", {
    base: "vs", inherit: true, rules: [],
    colors: {
      "editor.background": "#FFFFFF", "editorGutter.background": "#FFFFFF",
      "editor.lineHighlightBackground": "#F4F6F5", "editorLineNumber.foreground": "#9AA39F",
      "editor.selectionBackground": "#BFE3DC", "focusBorder": "#2A7A6F",
      "diffEditor.insertedTextBackground": "#1A7F3726", "diffEditor.removedTextBackground": "#CF222E26",
      "diffEditor.insertedLineBackground": "#1A7F3714", "diffEditor.removedLineBackground": "#CF222E14",
    },
  });
  monaco.editor.defineTheme("gitlore-dark", {
    base: "vs-dark", inherit: true, rules: [],
    colors: {
      "editor.background": "#1B2021", "editorGutter.background": "#1B2021",
      "editor.lineHighlightBackground": "#22282A", "editorLineNumber.foreground": "#5E6864",
      "editor.selectionBackground": "#2E5A53", "focusBorder": "#5CC2B2",
      "diffEditor.insertedTextBackground": "#3FB95033", "diffEditor.removedTextBackground": "#F8514933",
      "diffEditor.insertedLineBackground": "#3FB9501A", "diffEditor.removedLineBackground": "#F851491A",
    },
  });
}

export const monacoTheme = (theme) => (theme === "dark" ? "gitlore-dark" : "gitlore-light");

/**
 * Side-by-side (or inline) diff. Left = before, right = after.
 * editable: the right side can be edited (working tree); onChange/onSave are then used.
 * onAsk({text, side}, explain) is called from the right-click menu on a selection.
 */
export function DiffView({ monaco, original, modified, language, editable = false, sideBySide = true,
                           theme, collapseUnchanged = false, onAsk, onChange, onSave }) {
  const host = useRef(null);
  const editor = useRef(null);
  const handlers = useRef({});
  const content = useRef({});
  const changeSub = useRef(null);
  handlers.current = { onAsk, onChange, onSave };
  content.current = { original, modified, language };

  // Put the current before/after text into the editor (used on create and whenever the text changes).
  const applyModel = () => {
    const diff = editor.current;
    if (!diff) return;
    const old = diff.getModel();
    const { original: before, modified: after, language: lang } = content.current;
    if (old && old.original.getValue() === before && old.modified.getValue() === after &&
        old.modified.getLanguageId() === lang) return;  // unchanged: don't cancel a diff that is computing
    const model = { original: monaco.editor.createModel(before, lang), modified: monaco.editor.createModel(after, lang) };
    diff.setModel(model);
    changeSub.current?.dispose();
    changeSub.current = model.modified.onDidChangeContent(() => handlers.current.onChange?.(model.modified.getValue()));
    old?.original.dispose();
    old?.modified.dispose();
  };

  useEffect(() => {
    const diff = monaco.editor.createDiffEditor(host.current, {
      automaticLayout: true, readOnly: !editable, originalEditable: false, renderSideBySide: sideBySide,
      minimap: { enabled: false }, fontSize: 13, scrollBeyondLastLine: false, renderOverviewRuler: true,
      hideUnchangedRegions: { enabled: collapseUnchanged },
      useInlineViewWhenSpaceIsLimited: true, renderSideBySideInlineBreakpoint: 560,
      fontFamily: getComputedStyle(document.documentElement).getPropertyValue("--mono"),
    });
    editor.current = diff;
    const sides = [["original", diff.getOriginalEditor()], ["modified", diff.getModifiedEditor()]];
    for (const [side, ed] of sides) {
      const run = (explain) => () => {
        const selection = ed.getSelection();
        const text = selection && ed.getModel().getValueInRange(selection);
        if (text && text.trim()) handlers.current.onAsk?.({ text, side }, explain);
      };
      ed.addAction({ id: "gitlore.ask", label: t("menu.ask"), contextMenuGroupId: "navigation",
                     contextMenuOrder: 0, precondition: "editorHasSelection", run: run(false) });
      ed.addAction({ id: "gitlore.explain", label: t("menu.explain"), contextMenuGroupId: "navigation",
                     contextMenuOrder: 0.1, precondition: "editorHasSelection", run: run(true) });
    }
    diff.getModifiedEditor().addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => handlers.current.onSave?.());
    applyModel();
    return () => {
      const model = diff.getModel();
      changeSub.current?.dispose();
      diff.dispose();
      editor.current = null;
      model?.original.dispose();
      model?.modified.dispose();
    };
  }, [monaco, editable, collapseUnchanged]);

  useEffect(applyModel, [original, modified, language]);

  useEffect(() => { editor.current.updateOptions({ renderSideBySide: sideBySide }); }, [sideBySide]);
  useEffect(() => { monaco.editor.setTheme(monacoTheme(theme)); }, [theme]);

  return html`<div class="monaco-host" ref=${host}></div>`;
}
