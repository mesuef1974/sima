"""عتبة الاحتراف تحسبها الأداة لا الحَكَم."""
from sima import config
from sima.services.judge import Judgement, Score, shortlist


def _s(cid, base=4, **kw):
    return Score(cid, {k: kw.get(k, base) for k in config.JUDGE_CRITERIA})


def test_threshold_total_each_and_key_criteria():
    assert _s("a").passed and _s("a").total == 32
    assert not _s("a", base=3).passed  # 24 < 30
    assert not _s("a", base=5, scale=2).passed  # معيار دون 3
    assert not _s("a", base=5, craft=3).passed  # الحرفية دون 4
    assert any("craft=3" in f for f in _s("a", base=5, craft=3).failures())


def test_shortlist_ranks_passing_then_flags_below_bar():
    j = Judgement("d", {c: s for c, s in {"c1": _s("c1", idea=5), "c2": _s("c2"), "c3": _s("c3", base=3), "c4": _s("c4")}.items()})
    assert shortlist(j, ["c1", "c2", "c3", "c4"]) == (["c1", "c2", "c4"], False)
    assert shortlist(j, ["c1", "c2", "c3"]) == (["c1", "c2", "c3"], True)
    assert shortlist(j, ["c2", "c4"], n=3) == (["c2", "c4"], True)
