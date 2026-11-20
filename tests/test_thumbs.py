"""مصغّرات الأفكار: تُرسم لكل فكرة مصغّرة ويقرؤها القارئ الأعمى قبل الرسم الكامل، والمردودة لا يُبنى عليها مفهوم."""
import yaml

from sima import config
from sima.adapters.geometry import build_svg
from sima.domain import Medium, brief_from_dict
from sima.services import blind, protocol, thumbs
from sima.services.pipeline import AWAIT_MODEL, Pipeline, record_switch
from sima.services.shaping import ShapingService

from .fakes import FakeRenderer
from .test_domain_ledger_workspace import BRIEF
from .test_pipeline import FAMILIES, NoShaper, _five_distinct, _write_concepts


def _pipe(tmp_path, embedder=None):
    return Pipeline(FakeRenderer(), ShapingService(NoShaper()), None, tmp_path / "out", catalog=[], decide_cmd="sima decide b.yaml",
                    build_mark=build_svg, thumbs_gate=True, embedder=embedder)


def _ideas(ws, n=12, shift=0):
    """أفكار بالصيغة التي يكتبها _write_concepts، ولكل منها مصغّرة مستطيل مختلف."""
    ideas = [{"id": f"i{k}", "family": FAMILIES[k % 5], "sentence": f"فكرة {k}", "twist": f"حيلة {k}"} for k in range(n)]
    (ws.work / "ideas.yaml").write_text(yaml.safe_dump({"ideas": ideas}, allow_unicode=True), encoding="utf-8")
    thumbs.thumbs_dir(ws).mkdir(exist_ok=True)
    for k in range(n):
        (thumbs.thumbs_dir(ws) / f"i{k}.mark.yaml").write_text(f"mark: {{rect: [{40 + k + shift}, 40, {100 + 4 * k}, 160]}}", encoding="utf-8")


def _read(ws, blocked=()):
    ideas = protocol.read_ideas(ws)
    dg = thumbs.digest(thumbs.svgs(ws, ideas))
    rows = {i.id: ({"seen": "حرف لاتيني", "reads_as": "ö", "kind": "foreign_letter", "strength": 3} if i.id in blocked
                   else {"seen": f"شكل {i.id}", "reads_as": "", "kind": "none", "strength": 0}) for i in ideas}
    blind.blind_dir(ws, thumbs.KIND).mkdir(parents=True, exist_ok=True)
    blind.path(ws, dg, thumbs.KIND).write_text(yaml.safe_dump({"digest": dg, "readings": rows}, allow_unicode=True), encoding="utf-8")
    return dg


def _concepts(ws, idea_ids):
    _write_concepts(ws, _five_distinct())
    data = yaml.safe_load((ws.work / "concepts.yaml").read_text(encoding="utf-8"))
    for c, iid in zip(data["concepts"], idea_ids, strict=True):
        c["idea_id"] = iid
        (ws.concepts_dir / f"{c['id']}.mark.yaml").write_text("mark: {rect: [40, 40, 176, 176]}", encoding="utf-8")
    (ws.work / "concepts.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def test_thumbs_come_before_drawing_and_blocked_ideas_cannot_become_concepts(tmp_path):
    b = brief_from_dict(BRIEF, source="b.yaml")
    pipe = _pipe(tmp_path)
    out = pipe.run(b)
    ws = out.workspace
    assert out.code == AWAIT_MODEL and "مصغّرات الأفكار" in out.message and not (ws.work / "REQUEST-diverge.md").exists()
    req = (ws.work / thumbs.REQUEST).read_text(encoding="utf-8")
    assert "work/thumbs/<idea_id>.mark.yaml" in req and "قواعد الأداة الملزمة" in req and "لا تكتب `work/concepts.yaml`" in req
    _ideas(ws)
    (thumbs.thumbs_dir(ws) / "i3.mark.yaml").unlink()
    out = pipe.run(b)
    assert "لا مصغّرة للفكرة i3" in out.message and "لا مصغّرة للفكرة i3" in (ws.work / thumbs.REQUEST).read_text(encoding="utf-8")
    _ideas(ws)
    out = pipe.run(b)
    assert out.code == AWAIT_MODEL and "القراءة العمياء للمصغّرات" in out.message
    blind_req = (ws.work / thumbs.BLIND_REQUEST).read_text(encoding="utf-8")
    assert "work/blind/thumbs/" in blind_req and "فكرة 1" not in blind_req and b.name_ar not in blind_req  # عمياء: لا جملة ولا اسم
    assert all(p.is_file() and str(p) in blind_req for p in thumbs.images(ws, "i0")) and len(thumbs.images(ws, "i0")) == 2
    _read(ws, blocked=("i0", "i1"))
    out = pipe.run(b)
    assert out.code == AWAIT_MODEL and "REQUEST-diverge.md" in out.message
    m = ws.read_marker(thumbs.KIND)
    assert set(m["blocked"]) == {"i0", "i1"} and len(m["allowed"]) == 10 and not m["exhausted"] and blind.rounds(ws) == 0
    diverge = (ws.work / "REQUEST-diverge.md").read_text(encoding="utf-8")
    assert "الأفكار بعد القراءة العمياء للمصغّرات" in diverge and "لا تُعد كتابته" in diverge and "- i0: رأى «حرف لاتيني»" in diverge
    _concepts(ws, ["i0", "i2", "i3", "i4", "i5"])  # c1 على فكرة مردودة
    out = pipe.run(b)
    assert out.code == AWAIT_MODEL and "المفهوم c1 مبني على الفكرة i0 التي ردّها القارئ الأعمى" in out.message
    _concepts(ws, ["i6", "i2", "i3", "i4", "i5"])
    out = pipe.run(b)
    assert out.code == AWAIT_MODEL and "الجولة 1" in out.message  # مضى الخط إلى النقد: المصغّرات لا تُعاد في أثناء الدورة
    assert pipe.run(b).code == AWAIT_MODEL and (ws.work / thumbs.REQUEST).stat().st_mtime < (ws.work / "REQUEST-diverge.md").stat().st_mtime


def test_too_few_survivors_asks_once_for_replacements_then_proceeds_with_a_warning(tmp_path):
    b = brief_from_dict(BRIEF, source="b.yaml")
    pipe = _pipe(tmp_path)
    ws = pipe.run(b).workspace
    _ideas(ws)
    pipe.run(b)
    bad = tuple(f"i{k}" for k in range(9))
    _read(ws, blocked=bad)  # ثلاث مجتازة فقط
    out = pipe.run(b)
    assert out.code == AWAIT_MODEL and "استبدال قبل الرسم" in out.message and not ws.done(thumbs.KIND)
    req = (ws.work / thumbs.REQUEST).read_text(encoding="utf-8")
    assert "قراءة المصغّرات السابقة" in req and "- i0 مردودة" in req and "- i11 مجتازة" in req and "اجتازت القراءة العمياء 3 أفكار" in req
    assert "استبدال قبل الرسم" in pipe.run(b).message  # idempotent: لم يتغيّر شيء فلا قراءة جديدة
    _ideas(ws, shift=7)  # الرسّام بدّل المصغّرات
    assert "القراءة العمياء للمصغّرات" in pipe.run(b).message
    _read(ws, blocked=bad)  # ما زالت ثلاث: استُنفدت الجولتان
    out = pipe.run(b)
    m = ws.read_marker(thumbs.KIND)
    assert "REQUEST-diverge.md" in out.message and m["exhausted"] and m["blocked"] == {} and set(m["weak"]) == set(bad)
    assert "لم تجتز خمس أفكار" in (ws.work / "REQUEST-diverge.md").read_text(encoding="utf-8")
    _concepts(ws, ["i0", "i1", "i2", "i3", "i4"])
    assert "ردّها القارئ الأعمى" not in pipe.run(b).message  # لا منع بعد الاستنفاد وإلا تعذّر رسم خمسة


def test_new_drawing_cycle_archives_thumbs_and_starts_again(tmp_path):
    b = brief_from_dict(BRIEF, source="b.yaml")
    pipe = _pipe(tmp_path)
    ws = pipe.run(b).workspace
    _ideas(ws)
    pipe.run(b)
    _read(ws)
    pipe.run(b)
    _concepts(ws, ["i0", "i1", "i2", "i3", "i4"])
    pipe.run(b)
    record_switch(ws, Medium.ABSTRACT_MARK, "ارسم من جديد")
    out = pipe.run(b)
    assert out.code == AWAIT_MODEL and "مصغّرات الأفكار" in out.message and not ws.done(thumbs.KIND)
    hist = next((ws.work / "history").glob("medium-abstract_mark-*"))
    assert (hist / "thumbs" / "i0.mark.yaml").is_file() and not any(thumbs.thumbs_dir(ws).glob("*.mark.yaml"))
    assert any((ws.work / "history").glob("blind-thumbs-medium-abstract_mark-*/*.yaml")) and blind.rounds(ws, thumbs.KIND) == 0


def test_survivors_are_ranked_by_how_close_the_reading_is_to_the_intent():
    class Embed:
        model = "fake"

        def embed(self, texts):  # ما رُئي في i2 يطابق قصدها؛ البقية متعامدة
            return [[1.0, 0.0] if "2" in t else [0.0, 1.0] if t.startswith("فكرة") else [0.6, 0.8] for t in texts]

    from sima.domain import Family, Idea
    ideas = [Idea(f"i{k}", Family.ABSTRACT, f"فكرة {k}", f"حيلة {k}") for k in range(4)]
    r = blind.Readings("d", {i.id: blind.Reading(i.id, f"شكل {i.id[1:]}", "", "none", 0) for i in ideas})
    r.readings["i0"] = blind.Reading("i0", "حرف", "a", "foreign_letter", 3)
    sel = thumbs.select(r, ideas, Embed())
    assert sel.allowed[0] == "i2" and sel.reach["i2"] == 1.0 and "i0" in sel.blocked and "i0" not in sel.allowed
    plain = thumbs.select(r, ideas, None)
    assert plain.allowed == ["i1", "i2", "i3"] and plain.reach == {}  # بلا نموذج تضمين: ترتيب الملف


def test_stage_is_skipped_without_the_gate_the_build_tool_or_on_a_cycle_in_progress(tmp_path):
    b = brief_from_dict(BRIEF, source="b.yaml")
    plain = Pipeline(FakeRenderer(), ShapingService(NoShaper()), None, tmp_path / "a", catalog=[], decide_cmd="x", thumbs_gate=True)
    assert "REQUEST-diverge.md" in plain.run(b).message  # بلا أداة بناء لا مصغّرات
    pipe = _pipe(tmp_path / "b")
    ws = Pipeline(FakeRenderer(), ShapingService(NoShaper()), None, tmp_path / "b" / "out", catalog=[], decide_cmd="x",
                  build_mark=build_svg).run(b).workspace
    _concepts(ws, ["i0", "i1", "i2", "i3", "i4"])  # دورة بدأت قبل تفعيل المرحلة
    out = pipe.run(b)
    assert not (ws.work / thumbs.REQUEST).exists() and "الجولة 1" in out.message
    assert config.THUMBS_MAX_ROUNDS == 2 and config.THUMB_SIZES == (128, 16)


def test_thumb_requests_use_the_drawer_at_high_effort_and_the_blind_reader(monkeypatch):
    from sima.adapters import claude_model

    monkeypatch.setattr(claude_model, "_env", lambda k, d: d)
    assert claude_model.design_flags("REQUEST-thumbs.md") == ["--model", "claude-fable-5-2", "--effort", "high"]
    assert claude_model.design_flags("REQUEST-blind-thumbs.md") == ["--model", "sonnet", "--effort", "low"]
    root = config.ROOT / "out" / "x" / "v3"
    cmd = claude_model.ClaudeCodeModel(budget_usd=1, timeout_s=60).command(root / "work" / "REQUEST-blind-thumbs.md", root)
    allowed = cmd[cmd.index("--allowedTools") + 1:cmd.index("--disallowedTools")]
    assert allowed == ["Read(./out/x/v3/work/REQUEST-blind-thumbs.md)", "Read(./out/x/v3/work/render/**)",
                       "Write(./out/x/v3/work/blind/**)", "Edit(./out/x/v3/work/blind/**)"]
