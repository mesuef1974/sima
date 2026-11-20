"""معايرة الحَكَم: هل العتبة قابلة للبلوغ؟ استدعاء تحكيم حقيقي واحد على علامات محترفة من مكتبة المراجع.

في سِمة v2 لم ينل أي مفهوم من ثلاثين 4 في التميّز، وهو شرط العتبة. قبل لوم الرسّام نسأل: هل يمنح الحَكَم نفسه، بالطلب
نفسه والمعيار نفسه، درجة الاجتياز لعلامات يشهد لها السوق؟ إن رسبت هي أيضًا فالعتبة أو قاعدة «القراءة الخاطئة» هي الخلل.

    uv run python scripts/calibrate_judge.py [--marks buck loader ...] [--anchor out/sima/v2/work/concepts/c3.svg] [--budget 1]

العلامات المرجعية ملك أصحابها: تُصيَّر أحادية في مجلد مؤقت (out/_calibration، يُحذف في النهاية) للدراسة فقط، ولا يدخل منها
شيء في أي مخرج. النتيجة (درجات وأسماء فقط) تُكتب في var/calibration/ خارج git. الكلفة نحو نصف دولار.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import yaml

from sima import config
from sima.adapters.claude_model import ClaudeCodeModel
from sima.adapters.playwright_renderer import PlaywrightRenderer
from sima.domain import Medium
from sima.services import judge as judging
from sima.services import svgtools
from sima.services.pipeline import Pipeline
from sima.services.render import RenderService

# علامات أحادية اللون بلا خلفية، موسومة exemplary في الفهرس، ولكل منها حيلة قراءة مزدوجة؛ وairbnb شاهد على أثر الشهرة
DEFAULT_MARKS = ("buck", "loader", "processwire", "houndci", "ramda", "airbnb")
DIGEST = "calibration"


def _catalog() -> dict[str, dict]:
    rows = json.loads(config.LIBRARY_CATALOG.read_text(encoding="utf-8"))
    return {Path(r["file"]).stem: r for r in rows}


def _anchor_meta(svg: Path, name: str, idea: str) -> tuple[str, str]:
    """اسم المفهوم وجملته من concepts.yaml المجاور إن وُجد، كي يُحكم عليه هنا بالفكرة التي حُكم عليه بها هناك."""
    listing = svg.parent.parent / "concepts.yaml"
    if listing.is_file():
        for c in (yaml.safe_load(listing.read_text(encoding="utf-8")) or {}).get("concepts") or []:
            if c.get("id") == svg.stem:
                return f"{name}: {c.get('name') or svg.stem}", str(c.get("sentence") or idea)
    return name, idea


def _request(marks: list[tuple[str, str, str, str]], work: Path) -> str:
    """الطلب بصيغة طلب التحكيم الحقيقي (المرجع والاختبارات والعتبة وقواعد الأداة)، بموجز من سطر لكل علامة بدل موجز واحد."""
    crit = "، ".join(config.JUDGE_CRITERIA)
    lines = [
        "# طلب التحكيم المستقل: معايرة", "",
        "أنت الحَكَم، ولم ترسم هذه العلامات. اقرأ `.claude/skills/sima-design/references/40-professional-bar.md` كاملًا،",
        "ثم افتح صور كل علامة فعليًا (256 و16 والمعكوس والمطموس) قبل أي درجة، واحكم بالصرامة نفسها التي تحكم بها أي مسودة.",
        "**اختبار الجملة**: اكتب لنفسك ما تراه في صورة 256 في جملة قبل أن تقرأ جملة الفكرة؛ إن لم يتطابقا فالفكرة لم تصل",
        "(idea ≤ 3) واذكر في blockers ما رأيتَه فعلًا. العلامات لمنتجات مختلفة، ولكل منها موجزه في سطر. إن عرفتَ علامة قائمة",
        "فاكتب في أول blockers «معروفة: <الاسم>» ثم احكم على الشكل نفسه كأنه مسودة بلا تاريخ. كتابتك محصورة في work/judge/.", "",
        f"اكتب `work/judge/{DIGEST}.yaml` بالضبط:", "", "```yaml", f"digest: {DIGEST}", "verdicts:", "  k1:",
        "    scores: {" + ", ".join(f"{k}: 0-5" for k in config.JUDGE_CRITERIA) + "}",
        '    blockers: ["العيب بالضبط: أين وما المقاس"]', '    direction: "تعديل هندسي قابل للتنفيذ"', "    replace: false", "```", "",
        f"المعايير: {crit}. العتبة تحسبها الأداة: المجموع ≥ {config.JUDGE_MIN_TOTAL} من 40، ولا معيار دون {config.JUDGE_MIN_EACH}، "
        "و" + "، ".join(f"{k} ≥ {m}" for k, m in config.JUDGE_KEY_MIN.items()) + ".", "",
        *Pipeline._tool_rules(Medium.ABSTRACT_MARK),
    ]
    for kid, name, industry, idea in marks:
        d = work / "render" / kid
        lines += [f"## {kid} «{name}» (المجال: {industry})", f"الفكرة: {idea}",
                  "الصور: " + ", ".join(str(d / f"{n}.png") for n in ("256", "16", "48", "reversed", "blurred")), ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--marks", nargs="+", default=list(DEFAULT_MARKS))
    ap.add_argument("--anchor", help="SVG لمفهوم من سِمة حُكم عليه سابقًا، ليُقارن حكمه هنا بحكمه هناك")
    ap.add_argument("--anchor-name", default="سِمة")
    ap.add_argument("--anchor-idea", default="الاسم مرسومًا بخط واحد")
    ap.add_argument("--budget", type=float, default=1.0)
    args = ap.parse_args(argv)

    cat = _catalog()
    missing = [m for m in args.marks if m not in cat]
    if missing:
        print("ليست في فهرس المكتبة: " + "، ".join(missing))
        return 2
    vroot = config.ROOT / "out" / "_calibration" / "v1"
    work = vroot / "work"
    renderer = PlaywrightRenderer()
    try:
        shutil.rmtree(vroot.parent, ignore_errors=True)
        (work / "judge").mkdir(parents=True)
        render = RenderService(renderer)
        marks: list[tuple[str, str, str, str]] = []
        for n, stem in enumerate(args.marks, 1):
            row = cat[stem]
            svg = svgtools.mono((config.LIBRARY_SVG_DIR / row["file"]).read_text(encoding="utf-8"))
            render.render_concept(f"k{n}", svg, work / "render" / f"k{n}")
            marks.append((f"k{n}", row["brand"], row.get("industry") or "غير مذكور", row.get("subject") or "غير معلنة"))
        if args.anchor:
            kid = f"k{len(marks) + 1}"
            render.render_concept(kid, Path(args.anchor).read_text(encoding="utf-8"), work / "render" / kid)
            name, idea = _anchor_meta(Path(args.anchor), args.anchor_name, args.anchor_idea)
            marks.append((kid, name, "design-creative", idea))
        req = work / "REQUEST-judge.md"
        req.write_text(_request(marks, work), encoding="utf-8")
        res = ClaudeCodeModel(budget_usd=args.budget, timeout_s=900).run(req, vroot)
        print(f"الاستدعاء: ok={res.ok} الكلفة={res.cost_usd:.2f}$ المدة={res.seconds} ث")
        j = judging.read(SimpleNamespace(work=work), DIGEST, [m[0] for m in marks])
        if j is None or not j.scores:
            print("لم يكتب الحَكَم ملفًا صالحًا: " + (res.summary if j is None else "؛ ".join(j.problems)))
            return 1
        rows = []
        for kid, name, _industry, _idea in marks:
            s = j.scores.get(kid)
            if s is None:
                continue
            rows.append({"id": kid, "mark": name, "total": s.total, "passed": s.passed, "scores": s.scores,
                         "failures": s.failures(), "blockers": list(s.blockers), "replace": s.replace})
            print(f"{kid} {name}: {s.total}/40 {'مجتاز' if s.passed else 'دون العتبة'} {s.scores}")
        out = config.ROOT / "var" / "calibration"
        out.mkdir(parents=True, exist_ok=True)
        dst = out / f"judge-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.yaml"
        dst.write_text(yaml.safe_dump({"cost_usd": res.cost_usd, "seconds": res.seconds, "problems": j.problems, "marks": rows},
                                      allow_unicode=True, sort_keys=False), encoding="utf-8")
        print(f"اجتاز {sum(r['passed'] for r in rows)} من {len(rows)}. النتيجة في {dst}")
        return 0
    finally:
        renderer.close()
        shutil.rmtree(vroot.parent, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
