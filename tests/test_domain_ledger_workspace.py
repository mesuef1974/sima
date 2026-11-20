from dataclasses import replace

from sima.domain import Decision, Medium, MediumLock, Verdict, brief_from_dict
from sima.services.ledger import Ledger
from sima.services.workspace import close_workspace, open_workspace

BRIEF = {
    "project": "demo", "name_ar": "تجربة", "name_short": "تجربة", "sector": "تعليم", "audience": "معلمون",
    "purpose": "اختبار", "archetype": "Sage", "three_words": ["دقة", "هدوء", "وضوح"],
    "taste": {"feeling": "هندسي", "avoid": ["نخلة"]}, "palette": {"paper": "#F7F4EE", "ink": "#1B1E23", "brand": "#7A1C3E"},
    "contexts": ["header"],
}


def test_brief_hash_ignores_seed_and_source_but_not_content():
    a = brief_from_dict(BRIEF, source="a.yaml")
    b = brief_from_dict({**BRIEF, "seed": 9}, source="b.yaml")
    c = brief_from_dict({**BRIEF, "name_short": "أوراق"})
    assert a.hash() == b.hash() and a.hash() != c.hash()
    assert a.wordmark_text == "تجربة" and len(a.hash()) == 12


def _rej(m: Medium, cid: str = "c1") -> Decision:
    return Decision(concept_id=cid, verdict=Verdict.REJECTED, medium=m, reason="", at="t")


def test_medium_lock_legacy_rotation_after_three_rejections():
    lock = MediumLock(auto_rotate=True)
    assert lock.current() is Medium.ABSTRACT_MARK
    for _ in range(2):
        lock.record(_rej(Medium.ABSTRACT_MARK))
    assert lock.current() is Medium.ABSTRACT_MARK
    lock.record(_rej(Medium.ABSTRACT_MARK))
    assert lock.is_locked(Medium.ABSTRACT_MARK) and lock.current() is Medium.WORDMARK
    lock.record(Decision("c9", Verdict.APPROVED, Medium.WORDMARK, "", "t"))
    assert lock.current() is Medium.WORDMARK
    for m in (Medium.WORDMARK, Medium.EMBLEM, Medium.PATTERN):
        for _ in range(3):
            lock.record(_rej(m))
    assert lock.current() is None


def test_medium_changes_only_by_owner_switch():
    lock = MediumLock()
    for _ in range(5):
        lock.record(_rej(Medium.ABSTRACT_MARK))
    assert lock.current() is Medium.ABSTRACT_MARK and not lock.locked
    lock.record(Decision(None, Verdict.SWITCH, Medium.EMBLEM, "أريد شارة", "t"))
    assert lock.current() is Medium.EMBLEM
    lock.record(Decision(None, Verdict.SWITCH, Medium.ABSTRACT_MARK, "عودة", "t"))
    assert lock.current() is Medium.ABSTRACT_MARK


def test_ledger_roundtrip_and_lock(tmp_path):
    led = Ledger(tmp_path / "d.jsonl")
    assert led.read() == [] and led.approved() is None
    led.record("c1", Verdict.REJECTED, Medium.ABSTRACT_MARK, "ضعيف")
    led.record("c2", Verdict.APPROVED, Medium.ABSTRACT_MARK, "جيد", 2)
    ds = led.read()
    assert [d.verdict for d in ds] == [Verdict.REJECTED, Verdict.APPROVED]
    assert ds[1].round == 2 and led.approved().concept_id == "c2"
    assert led.lock().rejections[Medium.ABSTRACT_MARK] == 1


def test_workspace_versions_are_siblings_not_replacements(tmp_path):
    b = brief_from_dict(BRIEF, source="x")
    ws1 = open_workspace(tmp_path, b)
    assert ws1.version == 1 and (ws1.root / "run.json").is_file()
    ws1b = open_workspace(tmp_path, b)
    assert ws1b.root == ws1.root
    ws2 = open_workspace(tmp_path, b, new_version=True)
    assert ws2.version == 2 and ws1.root.is_dir()
    changed = replace(b, purpose="آخر")
    ws3 = open_workspace(tmp_path, changed)
    assert ws3.version == 3
    close_workspace(ws3)
    assert open_workspace(tmp_path, changed).root == ws3.root  # الإصدار المغلق يُعاد لا يُستبدل
    ws4 = open_workspace(tmp_path, changed, new_version=True)
    assert ws4.version == 4
    ws4.mark_done("brief", {"x": 1})
    assert ws4.done("brief") and ws4.read_marker("brief") == {"x": 1} and not ws4.done("render")
