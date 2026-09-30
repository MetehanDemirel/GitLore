"""Every UI language has every string, with the same {placeholders}; every key used in the UI exists."""

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
def test_translation_is_complete(lang):
    strings = json.loads((WEB / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
    assert set(strings) == set(EN), f"{lang}: missing {sorted(set(EN) - set(strings))}, extra {sorted(set(strings) - set(EN))}"
    for key, english in EN.items():
        assert set(PLACEHOLDER.findall(strings[key])) == set(PLACEHOLDER.findall(english)), f"{lang}: {key}"
        assert strings[key].strip(), f"{lang}: {key} is empty"


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
