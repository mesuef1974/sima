import { readInbound, type Inbound } from "@/utils/boxLink";

// يُستورد أول شيء في main.ts، قبل الموجّه: ردّ المصمّم الوارد في جزء الرابط يُحفظ في الذاكرة ويُزال من الرابط،
// فلا يقرؤه الموجّه مسارًا ولا يبقى في تاريخ التصفح. لا يُخزَّن في المتصفح.
let stash: Inbound | null = readInbound(window.location.hash);
if (stash) window.history.replaceState(null, "", "#/box");

export function takeInbound(): Inbound | null {
  const got = stash;
  stash = null;
  return got;
}
