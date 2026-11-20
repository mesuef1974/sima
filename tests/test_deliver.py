"""اختبارات التسليم: ترقيع tokens.css وspa.html وmanifest، وخطة الكتابة، وتدفق البطاقة عبر هدف وهمي."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import pytest

from sima.domain import brief_from_dict
from sima.services.deliver import apply_plan, deliver, manifest_with_prefix, patch_spa_html, patch_tokens_css, plan_delivery
from sima.services.workspace import open_workspace

from .test_domain_ledger_workspace import BRIEF

TOKENS = """:root {
  --color-brand: #7a1c3e;
  /* الشعار ثابت في الوضعين: هو العلامة، لا يتبع السمة */
  --color-mark-tile: #7a1c3e;
  --color-mark-ink: #ffffff;
  --color-mark-dot: #d9a441;
  --color-focus: #c58a1c;
}

@media screen and (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --color-brand: #e48aa8;
  }
}
"""

SPA = """<head>
  <link rel="icon" type="image/svg+xml" href="{% static 'favicon.svg' %}">
  <title>x</title>
</head>
"""


def test_patch_tokens_replaces_mark_vars_and_flips_dark_ink():
    out = patch_tokens_css(TOKENS, "#7A1C3E", "#D9A441")
    assert "--color-mark-tile" not in out and "--color-mark-dot" not in out
    root, dark = out.split("@media")
    assert "--color-mark-ink: #7a1c3e;" in root and "--color-mark-accent: #d9a441;" in root
    assert "--color-mark-ink: #ffffff;" in dark
    assert "الشعار ثابت في الوضعين" not in out
    assert patch_tokens_css(out, "#7A1C3E", "#D9A441") == out  # idempotent


def test_patch_tokens_appends_block_when_no_mark_vars():
    out = patch_tokens_css(":root {\n  --x: 1;\n}\n", "#111111", "#222222")
    assert "--color-mark-ink: #111111;" in out and "--color-mark-accent: #222222;" in out


def test_patch_spa_adds_links_once():
    out = patch_spa_html(SPA)
    assert 'rel="manifest"' in out and 'rel="apple-touch-icon"' in out and out.index('rel="icon"') < out.index('rel="manifest"')
    assert patch_spa_html(out) == out


def test_manifest_prefix():
    m = json.dumps({"icons": [{"src": "/icon-192.png"}, {"src": "/static/x.png"}]})
    data = json.loads(manifest_with_prefix(m, "/static/"))
    assert [i["src"] for i in data["icons"]] == ["/static/icon-192.png", "/static/x.png"]


def _package(tmp_path: Path) -> Path:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "BrandMark.vue").write_text('<template><svg fill="var(--color-mark-accent, #d9a441)"/></template>', encoding="utf-8")
    (pkg / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (pkg / "favicon.ico").write_bytes(b"\x00\x00\x01\x00")
    (pkg / "site.webmanifest").write_text(json.dumps({"icons": [{"src": "/icon-192.png"}]}), encoding="utf-8")
    (pkg / "x-mark.svg").write_text("<svg/>", encoding="utf-8")
    (pkg / "USAGE.md").write_text("# قواعد", encoding="utf-8")
    (pkg / "preview.html").write_text("<html/>", encoding="utf-8")
    (pkg / "concept.json").write_text(json.dumps({"id": "w1"}), encoding="utf-8")
    return pkg


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "frontend" / "src" / "styles").mkdir(parents=True)
    (repo / "templates").mkdir()
    (repo / "frontend" / "src" / "styles" / "tokens.css").write_text(TOKENS, encoding="utf-8")
    (repo / "templates" / "spa.html").write_text(SPA, encoding="utf-8")
    return repo


def test_plan_and_apply(tmp_path):
    b = brief_from_dict(BRIEF)
    plan = plan_delivery(b, _package(tmp_path), _repo(tmp_path), 1, "w1")
    paths = set(plan.paths)
    assert {"frontend/src/components/BrandMark.vue", "frontend/public/favicon.svg", "frontend/public/favicon.ico",
            "frontend/public/site.webmanifest", "frontend/src/styles/tokens.css", "templates/spa.html",
            f"brand/{b.project}/x-mark.svg", f"brand/{b.project}/USAGE.md"} <= paths
    assert not any(p.endswith(("preview.html", "concept.json")) for p in paths)
    wt = tmp_path / "wt"
    apply_plan(plan, wt)
    apply_plan(plan, wt)
    assert "/static/icon-192.png" in (wt / "frontend/public/site.webmanifest").read_text(encoding="utf-8")
    assert "--color-mark-accent" in (wt / "frontend/src/styles/tokens.css").read_text(encoding="utf-8")
    # ط4 «مسك» v10: حزمة بُنيت بلا قاعدة الليل تُسلَّم بها في الموضعين، وتعليق الرمز يُكتب عند التسليم
    from sima.services.export import NIGHT_FAVICON
    for rel in ("frontend/public/favicon.svg", f"brand/{b.project}/favicon.svg"):
        assert NIGHT_FAVICON in (wt / rel).read_text(encoding="utf-8"), rel
    (tmp_path / "old").mkdir()
    pkg = _package(tmp_path / "old")
    (pkg / "BrandMark.vue").write_text('<script setup lang="ts">\n// شعار: جملة الشعار الكامل وDESIGN\nconst a = 1;\n</script>\n',
                                       encoding="utf-8")
    mark = next(w for w in plan_delivery(b, pkg, _repo(tmp_path / "old"), 1, "w1").writes
                if w.path == "frontend/src/components/BrandMark.vue").content.decode("utf-8")
    assert "DESIGN" not in mark and "مُولَّد بأداة سِمة (المفهوم w1)" in mark and "const a = 1;" in mark


def test_mirrors_copy_planned_files_and_drop_stale_ones(tmp_path):
    """بند mirrors («مسك» v10): نسخ الواجهة تطابق أصلها في الخطة بعد تحويله، ومجلد النسخ لا يبقى فيه ما ليس في أصله."""
    import pytest

    b = brief_from_dict(BRIEF)
    pkg, repo = _package(tmp_path), _repo(tmp_path)
    (pkg / "x-mark.svg").write_text('<svg viewBox="0 0 100.00000 100.00000"><path d="M0 0Z"/></svg>', encoding="utf-8")
    old = repo / "frontend/src/static/brand/marks"
    old.mkdir(parents=True)
    (old / "gone.svg").write_text("<svg/>", encoding="utf-8")
    mirrors = {"frontend/src/static/brand/mark.svg": f"brand/{b.project}/x-mark.svg",
               "frontend/src/static/brand/marks/": f"brand/{b.project}"}
    plan = plan_delivery(b, pkg, repo, 1, "w1", mirrors=mirrors)
    content = {w.path: w.content for w in plan.writes}
    copy = content["frontend/src/static/brand/mark.svg"]
    assert copy == content[f"brand/{b.project}/x-mark.svg"] and b'viewBox="0 0 100 100"' in copy
    assert content["frontend/src/static/brand/marks/x-mark.svg"] == copy
    assert "frontend/src/static/brand/marks/gone.svg" in plan.deletes
    with pytest.raises(RuntimeError, match="mirrors"):
        plan_delivery(b, pkg, repo, 1, "w1", mirrors={"a.svg": "brand/none.svg"})


class FakeTarget:
    """origin: ما في origin/main (يُنسخ إلى الـworktree كما يفعل git worktree add)؛ fail_commit: يتعثّر الإيداع مرة."""

    def __init__(self, root: Path, origin: Path | None = None, fail_commit: bool = False):
        self.root, self.origin, self.fail_commit = root, origin or root, fail_commit
        self.calls: list[str] = []
        self.body = ""

    def base_files(self):
        from sima.services.deliver import DirFiles

        return DirFiles(self.origin)

    def new_card(self, title, body, success):
        self.calls.append("new")
        assert "سِمة" in title and "BrandMark" in body and success
        self.body = body
        return "20260101-abc123"

    def make_worktree(self, card_id):
        self.calls.append("worktree")
        wt = self.root / ".worktrees" / card_id
        if not wt.exists():
            shutil.copytree(self.origin, wt, ignore=shutil.ignore_patterns(".worktrees"))
        return wt, f"card/{card_id}"

    def commit(self, worktree, paths, message):
        self.calls.append("commit")
        if self.fail_commit:
            self.fail_commit = False
            raise RuntimeError("تعثّر الإيداع")
        self.committed = tuple(paths)
        self.gone = tuple(p for p in paths if not (worktree / p).is_file())  # ما حذفته الخطة يُودَع حذفًا
        return "deadbeefcafe"

    def ready(self, card_id):
        self.calls.append("ready")


def test_deliver_flow_is_idempotent(tmp_path):
    b = brief_from_dict(BRIEF)
    ws = open_workspace(tmp_path / "out", b)
    repo = _repo(tmp_path)
    pkg = _package(tmp_path)
    ws.package_dir.mkdir()
    for p in pkg.iterdir():
        (ws.package_dir / p.name).write_bytes(p.read_bytes())
    ws.mark_done("package")
    target = FakeTarget(repo)
    rc = deliver(ws, b, target, repo)
    assert rc.card_id == "20260101-abc123" and rc.branch == "card/20260101-abc123" and rc.head == "deadbeefcafe"
    assert target.calls == ["new", "worktree", "commit", "ready"]
    rc2 = deliver(ws, b, target, repo)
    assert rc2 == rc and target.calls == ["new", "worktree", "commit", "ready"]


def _delivery_setup(tmp_path):
    b = brief_from_dict(BRIEF)
    ws = open_workspace(tmp_path / "out", b)
    repo = _repo(tmp_path)
    ws.package_dir.mkdir()
    for p in _package(tmp_path).iterdir():
        (ws.package_dir / p.name).write_bytes(p.read_bytes())
    ws.mark_done("package")
    return b, ws, repo


def test_delivery_patches_origin_files_not_local_edits(tmp_path):
    b, ws, repo = _delivery_setup(tmp_path)
    origin = tmp_path / "origin"
    shutil.copytree(repo, origin)
    tokens = "frontend/src/styles/tokens.css"
    (origin / tokens).write_text(TOKENS + "/* UPSTREAM */", encoding="utf-8")
    (repo / tokens).write_text(TOKENS + "/* LOCAL-UNCOMMITTED */", encoding="utf-8")
    rc = deliver(ws, b, FakeTarget(repo, origin), repo)
    css = (Path(rc.worktree) / tokens).read_text(encoding="utf-8")
    assert "UPSTREAM" in css and "LOCAL-UNCOMMITTED" not in css and "--color-mark-accent" in css


def test_failed_delivery_resumes_the_same_card(tmp_path):
    b, ws, repo = _delivery_setup(tmp_path)
    target = FakeTarget(repo, fail_commit=True)
    with pytest.raises(RuntimeError):
        deliver(ws, b, target, repo)
    rc = deliver(ws, b, target, repo)
    assert target.calls.count("new") == 1 and rc.card_id == "20260101-abc123" and target.calls[-1] == "ready"


def test_plan_carries_full_identity_without_json_and_approved_palette(tmp_path):
    b = brief_from_dict(BRIEF)
    pkg = _package(tmp_path)
    ident = pkg / "identity"
    (ident / "tokens").mkdir(parents=True)
    (ident / "tokens" / "tokens.css").write_text(":root{}", encoding="utf-8")
    (ident / "tokens" / "tokens.json").write_text("{}", encoding="utf-8")
    (ident / "checks.json").write_text("{}", encoding="utf-8")
    (ident / "brand-book.pdf").write_bytes(b"%PDF")
    plan = plan_delivery(b, pkg, _repo(tmp_path), 2, "w1", palette=("#842447", "#E3AB3C"))
    paths = set(plan.paths)
    assert {f"brand/{b.project}/identity/tokens/tokens.css", f"brand/{b.project}/identity/brand-book.pdf"} <= paths
    assert not any(p.endswith(".json") for p in paths)
    css = next(w.content for w in plan.writes if w.path == "frontend/src/styles/tokens.css").decode("utf-8")
    assert "--color-mark-ink: #842447;" in css and "--color-mark-accent: #e3ab3c;" in css
    assert any("الهوية الكاملة" in n for n in plan.notes)


def test_in_place_delivery_closes_the_track_without_a_card(tmp_path, monkeypatch):
    """مشروع هو مستودع سِمة نفسه: نقطة git تسجَّل تسليمًا ودمجًا، مرة واحدة، ولا تُخلط ببطاقة."""
    from sima.adapters import auto_deliver
    from sima.services.board import sima_state
    from sima.services.deliver import deliver_in_place
    from sima.services.timeline import flow, timeline

    b, ws, repo = _delivery_setup(tmp_path)
    for stage in flow(False)[:-2]:
        ws.mark_done(stage, {})
    (ws.root / "run.json").write_text(json.dumps({"project": b.project, "closed": True, "brief_source": "briefs/x.yaml"}), encoding="utf-8")
    t = timeline(ws.root)
    assert t["progress"]["current"] == "deliver" and t["now"]["who"] == "owner"
    done = deliver_in_place(ws, b, "6f90530aa11bb22cc33")
    assert done == {"in_place": True, "commit": "6f90530aa11bb22cc33"}
    assert deliver_in_place(ws, b, "ffffffff") == done  # مرة لكل إصدار: النقطة الأولى تبقى
    t = timeline(ws.root)
    assert t["progress"]["current"] is None and t["progress"]["done"] == t["progress"]["total"]
    assert t["now"]["who"] == "script" and any("مستودع سِمة نفسه (النقطة 6f90530a)" in e["text"] for e in t["events"])
    [row] = sima_state(tmp_path / "out")
    assert row["deliver"]["in_place"] == "6f90530a" and all(s["status"] == "done" for s in row["steps"])
    with pytest.raises(RuntimeError, match="في مكانه"):
        deliver(ws, b, FakeTarget(repo), repo)

    b2, ws2, repo2 = _delivery_setup(tmp_path / "carded")
    deliver(ws2, b2, FakeTarget(repo2), repo2)
    with pytest.raises(RuntimeError, match="سابقًا في البطاقة"):
        deliver_in_place(ws2, b2, "abc")
    fresh = open_workspace(tmp_path / "none", b)
    with pytest.raises(RuntimeError, match="لا حزمة"):
        deliver_in_place(fresh, b, "abc")

    f = tmp_path / "t.yaml"
    f.write_text(f"{b.project}:\n  in_place: true\n", encoding="utf-8")
    monkeypatch.setattr(auto_deliver, "targets", lambda: auto_deliver.yaml.safe_load(f.read_text(encoding="utf-8")))
    assert "--in-place" in auto_deliver.deliver_if_configured(ws.root) and "briefs/x.yaml" in auto_deliver.deliver_if_configured(ws.root)
    assert auto_deliver.resolve_commit("HEAD") and auto_deliver.resolve_commit("no-such-ref-zz") == ""


def test_manual_delivery_records_the_project_merge_commit(tmp_path, monkeypatch, capsys):
    """تسليم يدوي بقرار المالك («مرصد»): نقطة الدمج في مستودع المشروع تُسجَّل تسليمًا ودمجًا، مرة واحدة، ولا تُخلط ببطاقة
    ولا بتسليم في المكان؛ الأمر يرفض مرجعًا غائبًا عن المستودع ولا يكتب فيه شيئًا."""
    import subprocess

    from sima import cli
    from sima.services.board import sima_state
    from sima.services.deliver import deliver_in_place, deliver_manual
    from sima.services.timeline import flow, timeline

    b, ws, repo = _delivery_setup(tmp_path)
    for stage in flow(False)[:-2]:
        ws.mark_done(stage, {})
    (ws.root / "run.json").write_text(json.dumps({"project": b.project, "closed": True, "brief_source": "briefs/x.yaml"}), encoding="utf-8")
    done = deliver_manual(ws, b, repo, "03bafcda441d7943")
    assert done == {"manual": True, "repo": str(repo), "commit": "03bafcda441d7943"}
    assert deliver_manual(ws, b, repo, "ffffffff") == done  # مرة لكل إصدار
    t = timeline(ws.root)
    assert t["progress"]["current"] is None and t["progress"]["done"] == t["progress"]["total"]
    assert any("يدويًّا" in e["text"] and "03bafcda" in e["text"] and repo.name in e["text"] for e in t["events"])
    [row] = sima_state(tmp_path / "out")
    assert row["deliver"]["manual"] == "03bafcda" and row["deliver"]["repo"] == repo.name and not row["deliver"]["in_place"]
    assert all(s["status"] == "done" for s in row["steps"])
    with pytest.raises(RuntimeError, match="يدويًّا"):
        deliver(ws, b, FakeTarget(repo), repo)
    with pytest.raises(RuntimeError, match="بنوع آخر"):
        deliver_in_place(ws, b, "abc")
    b2, ws2, repo2 = _delivery_setup(tmp_path / "carded")
    deliver(ws2, b2, FakeTarget(repo2), repo2)
    with pytest.raises(RuntimeError, match="سابقًا في البطاقة"):
        deliver_manual(ws2, b2, repo2, "abc")

    b3, ws3, repo3 = _delivery_setup(tmp_path / "cli")
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
    subprocess.run(["git", "init", "-q"], cwd=repo3, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo3, check=True)
    subprocess.run([*git, "commit", "-qm", "x"], cwd=repo3, check=True)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo3, capture_output=True, text=True, check=True).stdout.strip()
    monkeypatch.setattr(cli, "load_brief", lambda _p: b3)
    monkeypatch.setattr(cli, "_version", lambda _b: ws3)
    args = argparse.Namespace(brief="briefs/x.yaml", repo=None, manual="HEAD", in_place=None, redeliver=False, static_prefix="/static/")
    assert cli.cmd_deliver(args) == 2 and "--repo" in capsys.readouterr().err
    args.repo, args.manual = str(repo3), "no-such-ref-zz"
    assert cli.cmd_deliver(args) == 2 and not ws3.done("deliver")
    args.manual = "HEAD"
    assert cli.cmd_deliver(args) == 0 and ws3.read_marker("deliver")["commit"] == head
    assert subprocess.run(["git", "status", "--porcelain"], cwd=repo3, capture_output=True, text=True, check=True).stdout == ""


def test_auto_delivery_targets_and_unconfigured_project(tmp_path):
    from sima.adapters.auto_deliver import deliver_if_configured, targets

    f = tmp_path / "t.yaml"
    f.write_text("math_papers:\n  repo: C:/x\n", encoding="utf-8")
    assert targets(f)["math_papers"]["repo"] == "C:/x" and targets(tmp_path / "none.yaml") == {}
    root = tmp_path / "other" / "v1"
    root.mkdir(parents=True)
    (root / "run.json").write_text(json.dumps({"project": "zzz_unlisted", "brief_source": "briefs/x.yaml"}), encoding="utf-8")
    assert "لا مستودع تسليم" in deliver_if_configured(root)


def test_frozen_brief_round_trips_with_the_same_hash(tmp_path):
    import dataclasses

    from sima.domain.brief import load_frozen_brief

    b = brief_from_dict({**BRIEF, "palette": {**BRIEF.get("palette", {}), "extra": {"brand_strong": "#5E1430"}}})
    (tmp_path / "brief.json").write_text(json.dumps(dataclasses.asdict(b), ensure_ascii=False), encoding="utf-8")
    frozen = load_frozen_brief(tmp_path)
    assert frozen.hash() == b.hash() and frozen.palette.extra == (("brand_strong", "#5E1430"),)


def test_commit_outputs_commits_only_the_version_and_is_idempotent(tmp_path):
    import subprocess

    from sima.adapters.auto_deliver import commit_outputs

    def git(*a):
        return subprocess.run(["git", *a], cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", check=True).stdout

    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    (tmp_path / "other.txt").write_text("عمل غير مودَع", encoding="utf-8")
    v = tmp_path / "out" / "p" / "v1"
    v.mkdir(parents=True)
    (v / "run.json").write_text(json.dumps({"project": "p", "version": 1}), encoding="utf-8")
    assert "أُودعت" in commit_outputs(v, tmp_path)
    assert git("show", "--name-only", "--format=").split() == ["out/p/v1/run.json"]
    assert "other.txt" in git("status", "--porcelain")  # لم يُمسّ عمل آخر
    assert commit_outputs(v, tmp_path) == ""  # لا جديد، لا نقطة


TOKENS_BOTH_DARK = """:root {
  --color-brand: #842447;
  --color-grid: rgb(132 36 71 / 5%);
  --color-mark-ink: #842447;
  --color-mark-accent: #e3ab3c;
  --color-level-r: #842447;
}
@media screen and (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --color-brand: #d58298;
    --color-mark-ink: #ffffff;
  }
}
@media screen {
  :root[data-theme="dark"] {
    --color-brand: #d58298;
    --color-mark-ink: #ffffff;
  }
}
"""

PRINT = """@page { @bottom-right { border-top: 0.9pt solid #842447; } }
@media print {
  :root {
    --color-brand: #842447;
    --color-mark-ink: #842447;
    --color-mark-accent: #e3ab3c;
  }
}
"""


def test_patch_tokens_keeps_the_ink_in_every_dark_block_in_place():
    """ملاحظة جلسة «أوراق» على v4: الحبر الأبيض كُتب في الكتلة التلقائية وحُذف من اليدوية فبقي الشعار عنابيًّا في الليلي اليدوي."""
    from sima.services.deliver import patch_print_css

    out = patch_tokens_css(TOKENS_BOTH_DARK, "#7A1C3E", "#D9A441")
    light, auto, manual = out.split("@media")
    assert "--color-mark-ink: #7a1c3e;\n  --color-mark-accent: #d9a441;" in light
    for dark in (auto, manual):
        assert dark.count("--color-mark-ink: #ffffff;") == 1 and "--color-mark-accent" not in dark
        assert dark.index("--color-brand") < dark.index("--color-mark-ink")  # في موضعه لا في رأس الكتلة
    assert patch_tokens_css(out, "#7A1C3E", "#D9A441") == out
    manual_only = patch_tokens_css(':root {\n  --color-mark-ink: #111111;\n}\n:root[data-theme="dark"] {\n  --x: 1;\n}\n', "#111111", "#222222")
    assert manual_only.split('[data-theme="dark"]')[1].count("--color-mark-ink: #ffffff;") == 1

    paper = patch_print_css(PRINT, "#7A1C3E", "#D9A441")
    assert "--color-mark-ink: #7a1c3e;" in paper and "--color-mark-accent: #d9a441;" in paper and "--color-brand: #842447;" in paper
    assert patch_print_css(paper, "#7A1C3E", "#D9A441") == paper


def test_replace_color_covers_hex_case_and_rgb_triples():
    from sima.services.deliver import light_brand, replace_color

    text = "a: #842447; b: #842447AA; c: rgb(132 36 71 / 5%); d: rgba(132, 36, 71, 0.5); e: rgb(132 36 710);"
    assert replace_color(text.upper().replace("RGB", "rgb"), "#842447", "#7A1C3E").startswith("A: #7a1c3e;")
    out = replace_color(text, "#842447", "#7A1C3E")
    assert "rgb(122 28 62 / 5%)" in out and "rgba(122, 28, 62, 0.5)" in out and "rgb(132 36 710)" in out
    assert light_brand(TOKENS_BOTH_DARK) == "#842447" and light_brand(":root{}") == ""


def _styled_repo(tmp_path: Path) -> Path:
    repo = _repo(tmp_path)
    styles = repo / "frontend" / "src" / "styles"
    (styles / "tokens.css").write_text(TOKENS_BOTH_DARK, encoding="utf-8")
    (styles / "print.css").write_text(PRINT, encoding="utf-8")
    (styles / "print.test.ts").write_text('expect(print).toContain("solid #842447");', encoding="utf-8")
    (styles / "logo.png").write_bytes(b"\x89PNG\xff\xfe")
    (repo / "templates" / "spa.html").write_text(SPA.replace("<title>", '<meta name="theme-color" content="#842447">\n  <title>'), encoding="utf-8")
    return repo


def test_print_css_follows_the_mark_and_brand_unifies_only_when_the_owner_asked(tmp_path):
    b = brief_from_dict(BRIEF)
    pkg, repo = _package(tmp_path), _styled_repo(tmp_path)
    palette = ("#7A1C3E", "#D9A441")

    plain = {w.path: w.content.decode("utf-8") for w in plan_delivery(b, pkg, repo, 4, "a1", palette=palette).writes
             if w.path.endswith((".css", ".ts", ".html"))}
    assert "--color-mark-ink: #7a1c3e;" in plain["frontend/src/styles/print.css"]
    assert "--color-brand: #842447;" in plain["frontend/src/styles/tokens.css"] and "frontend/src/styles/print.test.ts" not in plain

    plan = plan_delivery(b, pkg, repo, 4, "a1", palette=palette, unify_brand=True)
    got = {w.path: w.content.decode("utf-8") for w in plan.writes if w.path.endswith((".css", ".ts", ".html"))}
    tokens = got["frontend/src/styles/tokens.css"]
    assert "--color-brand: #7a1c3e;" in tokens and "--color-level-r: #7a1c3e;" in tokens and "rgb(122 28 62 / 5%)" in tokens
    assert tokens.count("--color-brand: #d58298;") == 2  # القيم الليلية لا تُمسّ
    assert "#842447" not in "".join(got.values())
    assert "solid #7a1c3e" in got["frontend/src/styles/print.test.ts"] and 'content="#7a1c3e"' in got["templates/spa.html"]
    assert len(plan.paths) == len(set(plan.paths))
    note = next(n for n in plan.notes if "توحيد لون العلامة" in n)
    assert "print.test.ts" in note and "CLAUDE.md" in note
    # الموحَّد لا يُوحَّد ثانية: الخطة على ناتجها بلا فرق
    wt = tmp_path / "wt"
    shutil.copytree(repo, wt)
    assert apply_plan(plan, wt) and apply_plan(plan_delivery(b, pkg, wt, 4, "a1", palette=palette, unify_brand=True), wt) == []


def test_delivered_guide_allowlists_its_build_stamp_and_leaves_the_package(tmp_path):
    """ختم الدليل بصمة ست عشرية يُسقط فحص الأسرار في مستودع المشروع؛ يُعلَّم في نسخة التسليم ولا تُمسّ الحزمة (بصمة قرار المالك)."""
    b = brief_from_dict(BRIEF)
    pkg = _package(tmp_path)
    (pkg / "identity").mkdir()
    book = '<!doctype html><html lang="ar" dir="rtl"><head>\n<meta name="sima-build" content="231e20dac1a3ff67d1f9084f805cd63ed5"><meta charset="utf-8">\n</head></html>'
    (pkg / "identity" / "brand-book.html").write_bytes(book.encode("utf-8"))
    (pkg / "identity" / "reveal.html").write_text("<html></html>", encoding="utf-8")
    writes = {w.path: w.content.decode("utf-8") for w in plan_delivery(b, pkg, _repo(tmp_path), 4, "a1").writes}
    sent = writes[f"brand/{b.project}/identity/brand-book.html"]
    stamp = next(ln for ln in sent.split("\n") if "sima-build" in ln)
    assert stamp.endswith('content="231e20dac1a3ff67d1f9084f805cd63ed5"> <!-- pragma: allowlist secret -->')
    assert sent.replace(" <!-- pragma: allowlist secret -->\n", "") == book
    assert writes[f"brand/{b.project}/identity/reveal.html"] == "<html></html>"
    assert (pkg / "identity" / "brand-book.html").read_bytes() == book.encode("utf-8")


def test_receipt_counts_what_changed_not_what_was_planned(tmp_path):
    """رسالة تسليم v4 قالت 78 ملفًا وتغييرًا في spa.html: الخطة تعدّ المسارات، والإيصال الآن يعدّ ما تغيّر محتواه."""
    b, ws, repo = _delivery_setup(tmp_path)
    (repo / "templates" / "spa.html").write_text(patch_spa_html(SPA), encoding="utf-8")  # مرقَّع سلفًا: لا فرق
    (ws.package_dir / "BrandLockup.vue").write_text("<template><svg class=\"brand-lockup\"/></template>", encoding="utf-8")
    rc = deliver(ws, b, FakeTarget(repo), repo)
    assert "templates/spa.html" in rc.paths and "templates/spa.html" not in rc.changed
    assert {"frontend/src/components/BrandLockup.vue", "frontend/src/styles/tokens.css"} <= set(rc.changed) < set(rc.paths)
    assert deliver(ws, b, FakeTarget(repo), repo).changed == rc.changed  # من العلامة

    b2, ws2, repo2 = _delivery_setup(tmp_path / "retry")
    target = FakeTarget(repo2, fail_commit=True)
    with pytest.raises(RuntimeError):
        deliver(ws2, b2, target, repo2)
    assert "frontend/src/styles/tokens.css" in deliver(ws2, b2, target, repo2).changed  # كُتب في المحاولة الأولى ويُعدّ
