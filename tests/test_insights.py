"""Insights (no AI), narrative facts and online URL parsing."""

from __future__ import annotations

import pytest

from src import insights, narratives, online


@pytest.mark.parametrize("subject, files, primary", [
    ("fix: crash on empty list", ["a.py"], "bugfix"),
    ("feat(api): add export", ["a.py"], "feature"),
    ("chore(deps): bump requests", ["requirements.txt"], "dependencies"),
    ("Fix SQL injection in search", ["search.py"], "security"),
    ("Add tests for the token check", ["tests/test_auth.py"], "tests"),  # not security: only tests touched
    ("Update the install guide", ["docs/install.md"], "docs"),
    ("Speed up CSV export", ["export.py"], "performance"),
])
def test_categorize(subject, files, primary):
    assert insights.categorize(subject, files=files)["primary"] == primary


def test_large_and_breaking_changes():
    assert insights.categorize("feat!: new storage format", files=["a.py"])["breaking"]
    assert insights.categorize("Rewrite", files=["a.py"], lines=5000)["large"]
    assert not insights.categorize("Tweak", files=["a.py"], lines=3)["large"]


def test_parse_query():
    filters, words = insights.parse_query('author:"Ada L" type:fix path:auth since:2025-06 is:large login bug')
    assert filters == {"author": "Ada L", "type": "bugfix", "path": "auth", "since": "2025-06", "large": True}
    assert words == ["login", "bug"]


@pytest.fixture
def project(rb):
    rb.commit("Add login (#12)", {"auth.py": "def login(): pass\n"})
    rb.repo.create_tag("v1.0.0", message="First release")
    rb.commit("fix: login rejects valid users\n\nFollow-up to #12.", {"auth.py": "def login(): return True\n"})
    rb.commit("Add a dashboard", {"dash.py": "x = 1\n"})
    rb.commit('Revert "Add a dashboard"', {"dash.py": None})
    return rb


def test_search_and_overview(project):
    path = str(project.path)
    fixes = insights.search(path, "type:bugfix")["results"]
    assert [c["subject"] for c in fixes] == ["fix: login rejects valid users"]
    assert [c["subject"] for c in insights.search(path, "release:v1.0.0")["results"]] == ["Add login (#12)"]
    assert insights.search(path, "path:dash dashboard")["results"]
    ov = insights.overview(path)
    assert ov["commits"] == 4 and ov["contributors"] == 1


def test_related_follows_issue_numbers_and_reverts(project):
    path = str(project.path)
    by_subject = {c["subject"]: c["hash"] for c in insights.all_commits(path)}
    assert by_subject["fix: login rejects valid users"] in insights.related(path, [by_subject["Add login (#12)"]])
    assert by_subject['Revert "Add a dashboard"'] in insights.related(path, [by_subject["Add a dashboard"]])


def test_eras_split_by_release(project):
    eras = narratives.eras(str(project.path))
    assert [(e["key"], e["count"]) for e in eras] == [("v1.0.0", 1), ("unreleased", 3)]


def test_clean_citations_drops_made_up_hashes(project):
    real = insights.all_commits(str(project.path))[0]["hash"][:7]
    text = f"Login was fixed [{real}] and something else happened [a1b2c3d]."
    assert narratives.clean_citations(str(project.path), text) == f"Login was fixed [{real}] and something else happened."


@pytest.mark.parametrize("text", ["github.com/psf/requests", "https://github.com/psf/requests.git",
                                  "https://www.github.com/psf/requests/", "psf/requests"])
def test_parse_repo(text):
    assert online.parse_repo(text) == ("psf", "requests")


def test_parse_repo_rejects_other_hosts():
    with pytest.raises(online.OnlineError):
        online.parse_repo("gitlab.com/a/b")
