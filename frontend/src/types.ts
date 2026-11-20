// عقد /api/state كما تبنيه services/board.py وservices/inbox.py في سِمة.

// خطوات sima[] بنموذج خطوات سجل المشروع نفسه وترتيبه (services/timeline.py)؛ الخادم لا يرسل «fail» لخطوة: الفحص المردود في audit.
export type StepStatus = "done" | "current" | "pending";
export type NodeStatus = "done" | "active" | "pending" | "fail";

export interface Step { key: string; label: string; status: StepStatus }
export interface Decision { at: string; verdict: string; verdict_ar: string; concept: string; medium_ar: string; reason: string }
export interface SimaRun {
  project: string; name_ar: string; version: string; key: string; closed: boolean; mark: string; preview: string;
  concept: { id?: string; name?: string; medium_ar?: string; sentence?: string };
  name_check: { status: string; status_ar: string; at: string; note: string };
  deliver: { card: string; branch: string; in_place?: string; manual?: string; repo?: string };
  // unknown: استدعاءات قُطعت فلم تُبلَّغ كلفتها، وتُعدّ بحدّها المحجوز الأعلى
  cost?: { usd: number; calls: number; ref: number; level: "ok" | "warn" | "over"; unknown?: number };
  // نتيجة الفحوص الحتمية لآخر إصدار
  audit?: { passed: number; failed: number };
  judge?: { total: number | null; bar: number; below: boolean };
  files: { name: string; href: string }[];
  steps: Step[];
  decisions: Decision[];
}
export interface TrackNode { key: string; label: string; status: NodeStatus; at: string }
export interface Card {
  id: string; title: string; state: string; state_ar: string; url: string; created: string; updated: string;
  log: { at: string; text: string; kind?: string }[];
  track: { nodes: TrackNode[]; p: number; chip: string; status: string; status_kind: string; attempts: number; attempt_start: string; stage_since: string };
}
// stopped: خرج الخط وهو ينتظر النموذج (سقف، تكرار، فشل استدعاء، أو استدعاء آلي معطّل)؛ ليس اكتمالًا ويُستأنف بزر
export interface Job { project: string; state: "running" | "done" | "stopped" | "failed"; code: number | null; code_ar: string; started: string; ended: string; message: string }

interface ItemBase { project: string; version: number; key: string; title: string; after: string }
export interface ConceptOption {
  id: string; name: string; medium_ar: string; sentence: string; img: string; last: string; score?: number | null; passed?: boolean;
}
export interface ConceptsItem extends ItemBase {
  kind: "concepts"; preview: string; digest: string; concepts: ConceptOption[];
  below_bar?: boolean; bar?: number; medium?: string; mediums?: { id: string; ar: string }[];
}
export interface NameItem extends ItemBase {
  kind: "name_check"; preview: string; concept: string; name: string; note: string;
  sources: { key: string; label: string; url: string; hint: string }[];
}
export interface Direction { id: string; name: string; idea: string; img: string; swatches: string[] }
export interface Strategy {
  positioning: string; promise: string; tagline: string;
  personality: { trait: string; means: string; not: string }[];
  voice_do: string[]; voice_dont: string[];
}
export interface IdentityItem extends ItemBase {
  kind: "identity"; gate: "strategy" | "directions" | "book"; gate_ar: string; digest: string; directions_digest?: string;
  history: { at: string; verdict: string; option: string; reason: string }[];
  strategy?: Strategy; options?: Direction[]; board?: string; book?: string; pdf?: string; apps?: string[];
  reply?: { note: string; text: string } | null; // طلب تعديل أجابه النموذج ولم يغيّر المعروض (أي بوابة): ملاحظة المالك وجواب الخط كاملًا
  designer_sketch?: number; // مسار المصمّم الخارجي: رقم السكتش الذي بُني منه الرمز المعروض في الدليل (0 أو غائب: لا ينطبق)
  visuals?: { mark?: string; reveal?: string; preview?: string; board?: string; options?: Direction[] };
}
export interface StyleOption { id: string; name: string; principle: string; img: string }
export interface StyleItem extends ItemBase { kind: "style"; digest: string; max: number; styles: StyleOption[] }
// ورشة الرسم (services/workshop.py): ما يُرسم الآن قبل الحَكَم، للقراءة فقط
export interface WorkshopThumb { id: string; sentence: string; img: string; stamp: number; state: "" | "allowed" | "blocked" | "weak"; state_ar: string; seen: string }
export interface WorkshopConcept { id: string; name: string; sentence: string; idea: string; img: string; stamp: number; seen: string; misread: boolean; score?: number; passed?: boolean }
export interface WorkshopBoard { id: string; name: string; detail: string; misread: string; img: string; stamp: number; source: string }
// eval: حالة خيالية من مجموعة تقييم الرسّام (ليست مشروعًا)، ومفاهيمها تحمل درجة الحَكَم الأولى
export interface Workshop { project: string; version: number; stage: string; thumbs: WorkshopThumb[]; concepts: WorkshopConcept[]; explore?: WorkshopBoard[]; eval?: { run: string; name: string }; designer?: boolean }
// صفحة سكتشات المصمّم الخارجي (services/designer.py): يختار المالك منها سكتشًا واحدًا برقمه
export interface SketchOption { id: number; idea: string; pick: boolean }
export interface SketchesItem extends ItemBase { kind: "sketches"; digest: string; img: string; source: string; sketches: SketchOption[] }
// الخط وقف عند المالك بلا قرار يُعرض في بطاقة (أو تغيّر المعروض بعد وقوفه): يُعرض ما وقف عنده مع زر الاستئناف
// gate: البوابة التي وقف عندها (قد تكون فارغة)؛ designer_fix: نفدت جولات تصحيح المصمّم الخارجي، فيُردّ المتجه من البطاقة
export interface StalledItem extends ItemBase { kind: "stalled"; preview: string; digest: string; message: string; gate?: string }
export type InboxItem = ConceptsItem | NameItem | IdentityItem | StyleItem | SketchesItem | StalledItem;

export interface BoardState {
  now: string; repo: string | null;
  runner: { running: boolean; pid: string | number | null };
  sima: SimaRun[]; cards: Card[]; inbox: InboxItem[]; jobs: Job[]; workshop?: Workshop[];
  limits?: Partial<Limits>;
}
/** أقصى عدد أحرف يقبله الخادم لكل ملاحظة أو سبب؛ الزائد يُرفض بخطأ لا يُقصّ. */
export interface Limits { decide: number; medium: number; identity: number; note: number; reason: number }
export interface Registry {
  online: boolean; error?: string; runs: number; gate_decisions: number;
  identities: { project: string; name_ar: string; version: number; direction: string; direction_name: string; colors: Record<string, string>;
    checks: string; assets: number; approved_at: string; book_digest: string }[];
}
export interface Reply { ok: boolean; message?: string; error?: string }
/** منافذ الكتابة في /api؛ كلها برمز التشغيل. resume يستأنف الخط حيث وقف بلا قرار. */
export type PostPath = "decide" | "identity" | "name-check" | "medium" | "style" | "sketch" | "sketch-develop" | "sketch-reject" | "vector-return" | "designer-box/intake" | "resume" | "new-version";
/** طلب ينتظر الإرسال إلى المصمّم الخارجي: النص المرسل وحده وبصمته. */
export interface BoxItem { project: string; version: number; key: string; kind: "sketches" | "vector" | "fix"; kind_ar: string;
  text: string; chars: number; sha256: string; invoke: boolean }

export type Who = "owner" | "model" | "script" | "project" | "designer";
export interface Timeline {
  project: string; version: string; key: string; closed: boolean;
  // state: التوقف يُعرض تحذيرًا بسببه لا اكتمالًا. resume: يُستأنف الخط بزر (إصدار مفتوح بلا تشغيل جارٍ)
  now: { who: Who; text: string; since: string; after?: string; command?: string; pr_url?: string; state?: "stopped"; resume?: boolean; renew?: string };
  events: { at: string; who: Who; text: string }[];
  progress: { done: number; total: number; current: string | null; steps: { key: string; label: string; status: "done" | "current" | "pending" }[] };
  // تعذّر جلب السجل في آخر تحديث فبقي آخر ما وصل منه
  stale?: boolean;
}
