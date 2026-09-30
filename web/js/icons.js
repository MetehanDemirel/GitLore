// Small stroke icons (16px). Decorative: callers give buttons a text label or aria-label.
import { html } from "../vendor/preact-htm.module.js";

const paths = {
  history: "M3 8a5 5 0 1 0 1.5-3.5M3 2.5V5h2.5M8 5v3l2 1.5",
  changes: "M5 3v6.5M5 3a1.5 1.5 0 1 0 0 .01M5 13a1.5 1.5 0 1 0 0-.01M11 13a1.5 1.5 0 1 0 0-.01M11 11.5V9a2 2 0 0 0-2-2H5",
  settings: "M8 10a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM13 8l1.3-1-1-1.8-1.6.5a4.6 4.6 0 0 0-1.2-.7L10.2 3H7.8l-.3 1.9c-.4.2-.8.4-1.2.7l-1.6-.5-1 1.8L3 8l-1.3 1 1 1.8 1.6-.5c.4.3.8.5 1.2.7l.3 1.9h2.4l.3-1.9c.4-.2.8-.4 1.2-.7l1.6.5 1-1.8L13 8Z",
  assistant: "M3 3.5h10v7H8l-3 2.5v-2.5H3v-7ZM6 7h.01M8 7h.01M10 7h.01",
  plus: "M8 3v10M3 8h10",
  send: "M3 8h9M8.5 4.5 12 8l-3.5 3.5",
  stop: "M5 5h6v6H5z",
  trash: "M3.5 4.5h9M6.5 4.5V3h3v1.5M5 4.5l.5 8.5h5l.5-8.5",
  edit: "M10.5 3.5l2 2L6 12H4v-2l6.5-6.5Z",
  close: "M4 4l8 8M12 4l-8 8",
  chevron: "M5 6l3 3 3-3",
  search: "M7 11.5a4.5 4.5 0 1 0 0-9 4.5 4.5 0 0 0 0 9ZM10.3 10.3 13.5 13.5",
  file: "M4 2.5h5l3 3v8H4v-11ZM9 2.5v3h3",
  save: "M3.5 3h7l2 2v8h-9V3ZM5.5 3v3h4V3M5.5 13v-3.5h5V13",
  chat: "M3 4h10v6.5H7.5L5 12.5v-2H3V4Z",
  repo: "M2.5 4.5a1 1 0 0 1 1-1h3l1.5 1.5h4.5a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1h-9a1 1 0 0 1-1-1v-7.5Z",
  check: "M3.5 8.5 6.5 11.5 12.5 4.5",
  refresh: "M12.5 5.5A5 5 0 1 0 13 9M12.5 2.5v3h-3",
  sidebar: "M2.5 3h11v10h-11zM6 3v10",
  download: "M8 2.5v8M4.5 7 8 10.5 11.5 7M3 13.5h10",
};

export function Icon({ name, size = 16 }) {
  return html`<svg width=${size} height=${size} viewBox="0 0 16 16" fill="none" stroke="currentColor"
    stroke-width="1.35" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
    <path d=${paths[name]} /></svg>`;
}
