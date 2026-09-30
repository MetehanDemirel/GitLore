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
  chart: "M3 13.5h10M4.5 11V8M8 11V4.5M11.5 11V6.5",
  people: "M6 7.5a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM2.5 12.5a3.5 3.5 0 0 1 7 0M11 7.5a1.6 1.6 0 1 0 0-3.2M12 12.5h1.5a3 3 0 0 0-2.5-3",
  flame: "M8 13.5a4 4 0 0 0 4-4c0-2.5-2-3.5-2.5-6-1.5 1-2 2.5-2 3.5-1-.5-1.5-1.5-1.5-2.5-1.5 1.5-2 3-2 5a4 4 0 0 0 4 4Z",
  tag: "M2.5 8.5v-6h6l5 5-6 6-5-5ZM5.5 5.5h.01",
  branch: "M5 2.5v8M5 10.5a1.8 1.8 0 1 0 0 3.6 1.8 1.8 0 0 0 0-3.6ZM11 5.5a1.8 1.8 0 1 0 0-3.6 1.8 1.8 0 0 0 0 3.6ZM11 5.5c0 3-6 2-6 5",
  cloud: "M4.5 12.5a3 3 0 0 1-.3-6A4 4 0 0 1 12 6a3.2 3.2 0 0 1-.3 6.5H4.5Z",
  sparkle: "M8 2v3M8 11v3M2 8h3M11 8h3M4 4l2 2M10 10l2 2M12 4l-2 2M6 10l-2 2",
  book: "M3 3h4a1.5 1.5 0 0 1 1 .5 1.5 1.5 0 0 1 1-.5h4v9.5H9a1 1 0 0 0-1 1 1 1 0 0 0-1-1H3V3ZM8 3.5v10",
  timeline: "M4 2.5v11M4 4.5h.01M4 8h.01M4 11.5h.01M6.5 4.5h6M6.5 8h4.5M6.5 11.5h6",
  clock: "M8 13.5a5.5 5.5 0 1 0 0-11 5.5 5.5 0 0 0 0 11ZM8 5v3.2l2 1.3",
  shield: "M8 2.5l4.5 1.5v4c0 3-2 4.8-4.5 5.5C5.5 12.8 3.5 11 3.5 8V4L8 2.5Z",
  layers: "M8 2.5l5.5 3L8 8.5l-5.5-3L8 2.5ZM2.5 8.5 8 11.5l5.5-3M2.5 11 8 14l5.5-3",
  undo: "M5 5.5H10a3 3 0 0 1 0 6H6M5 5.5 7.5 3M5 5.5 7.5 8",
  bolt: "M9 2 4 9h3.5L7 14l5-7H8.5L9 2Z",
  dot: "M8 9.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z",
  zen: "M3 3h4M3 3v4M13 3H9M13 3v4M3 13h4M3 13V9M13 13H9M13 13V9",
  panel: "M2.5 3h11v10h-11zM10 3v10",
  more: "M4 8h.01M8 8h.01M12 8h.01",
};

export function Icon({ name, size = 16 }) {
  return html`<svg width=${size} height=${size} viewBox="0 0 16 16" fill="none" stroke="currentColor"
    stroke-width="1.35" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
    <path d=${paths[name]} /></svg>`;
}
