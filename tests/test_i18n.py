"""Translations match English's with the same {placeholders}; every key used in the UI exists."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src import config

WEB = Path(__file__).resolve().parent.parent / "web"
EN = json.loads((WEB / "i18n" / "en.json").read_text(encoding="utf-8"))
PLACEHOLDER = re.compile(r"\{(\w+)\}")


@pytest.mark.parametrize("lang", [code for code in config.LANGUAGES if code != "en"])
def test_translations_are_consistent(lang):
    """Missing strings fall back to English (translations are catching up); present ones must be sound."""
    path = WEB / "i18n" / f"{lang}.json"
    if not path.exists():
        pytest.skip(f"{lang}: UI not translated yet, English is shown")
    strings = json.loads(path.read_text(encoding="utf-8"))
    assert set(strings) <= set(EN), f"{lang}: unknown keys {sorted(set(strings) - set(EN))}"
    for key, text in strings.items():
        assert set(PLACEHOLDER.findall(text)) == set(PLACEHOLDER.findall(EN[key])), f"{lang}: {key}"
        assert text.strip(), f"{lang}: {key} is empty"


def test_every_key_used_in_the_ui_exists():
    used = set()
    for js in (p for p in (WEB / "js").rglob("*.js") if p.name != "i18n.js"):  # i18n.js documents t("key")
        used |= set(re.findall(r"\bt\(\"([a-zA-Z0-9_.]+)\"", js.read_text(encoding="utf-8")))
    # keys built dynamically in the code
    used -= {k for k in used if k.endswith(".")}
    assert used - set(EN) == set()
    for prefix, names in [("settings.theme.", config.THEMES), ("diff.", ["added", "deleted", "modified", "renamed"])]:
        for name in names:
            assert prefix + name in EN
