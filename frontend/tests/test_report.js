// Checks guessViewport, reportRows/reportText/reportHtml, renderScan and
// renderMatch of frontend/index.html against fake scan results. Offline.
// Run: node frontend/tests/test_report.js — backend/tests/test_frontend_report.py
// runs it under pytest. Prints "<n> passed, <m> failed"; exits 1 on a failure.
const { x, els } = require("./harness.js");
let fails = 0, passes = 0;
function check(name, cond, extra) {
  if (cond) { passes++; return; }
  fails++;
  console.log("FAIL:", name, extra !== undefined ? "\n" + extra : "");
}

// ── viewport ──────────────────────────────────────────────────────────────
const vp = (t) => x.guessViewport(Object.assign({ desc: "", variant: "", size: "" }, t));
const WP = "https://www.money.pl/?wfName=281086_3065732_BankClient_faktoring_01&testPos=3&creName=";
// "mob" as a token of the creative's name.
check("creName _mob 300x600", vp({ url: WP + "Faktoring_300x600_mob", size: "300x600", variant: "mob" }) === "mobile");
check("creName _mob, label variant", vp({ url: WP + "Faktoring_300x250_mob", size: "300x250", variant: "faktoring",
                                          desc: "Faktoring 300x250" }) === "mobile");
check("creName -mob", vp({ url: WP + "Faktoring-300x600-mob", size: "300x600", variant: "x" }) === "mobile");
check("creName mob_ first", vp({ url: WP + "mob_Faktoring_300x600", size: "300x600", variant: "faktoring" }) === "mobile");
check("encoded creName", vp({ url: "https://www.money.pl/?creName%3DFaktoring_300x600_mob", size: "300x600", variant: "x" }) === "mobile");
check("camelCase FaktoringMob", vp({ url: WP + "FaktoringMob_300x600", size: "300x600", variant: "x" }) === "mobile");
check("desc -mob", vp({ url: "https://www.dziennik.pl/?version=x", desc: "Billboard 300x600-mob" }) === "mobile");
check("infor version=…-mob", vp({ url: "https://www.dziennik.pl/?version=300x600-mob", desc: "Halfpage" }) === "mobile");
check("desktop creName stays desktop", vp({ url: WP + "Faktoring_970x250_desktop", size: "970x250", variant: "desktop" }) === "desktop");
check("MOBILITY desc stays desktop", vp({ url: WP + "Faktoring_300x600", desc: "MOBILITY Faktoring 300x600", size: "300x600" }) === "desktop");
check("mobility path stays desktop", vp({ url: "https://www.money.pl/mobility/?creName=Faktoring_300x600", size: "300x600" }) === "desktop");
check("Automobilklub stays desktop", vp({ url: WP + "Automobilklub_300x600", size: "300x600", variant: "automobilklub" }) === "desktop");
check("host mob. stays desktop", vp({ url: "https://mob.example.pl/?creName=Faktoring_300x600", size: "300x600" }) === "desktop");
check("host mob-portal stays desktop", vp({ url: "https://www.mob-portal.pl/a/b?creName=Faktoring_300x600", size: "300x600" }) === "desktop");
check("existing mobile hint kept", vp({ url: WP + "giga_mobile" }) === "mobile");
check("existing mob_ hint kept", vp({ url: "https://x.pl/#adbeta=r1!slot.mob_top" }) === "mobile");
check("link in the label: host not a name", vp({ url: "https://www.money.pl/?creName=X_300x600", desc: "Halfpage https://mob.example.pl/x", size: "300x600" }) === "desktop");
check("label word mob beside a link still mobile", vp({ url: "https://www.money.pl/?creName=X_300x600", desc: "Halfpage mob https://www.example.pl/x", size: "300x600" }) === "mobile");

// "mobile" anywhere but inside "automobile".
check("Automobile creName stays desktop", vp({ url: WP + "Automobile_300x600", size: "300x600", variant: "automobile" }) === "desktop");
check("automobile desc stays desktop", vp({ url: "https://www.money.pl/?creName=X_300x600", desc: "Automobile club 300x600", size: "300x600" }) === "desktop");
check("automobile path stays desktop", vp({ url: "https://moto.pl/automobile/?creName=X_300x600", size: "300x600" }) === "desktop");
check("300x250mobile still mobile", vp({ url: WP + "Faktoring_300x250mobile", size: "300x250" }) === "mobile");
check("'Mobile Billboard' desc still mobile", vp({ url: "https://x.pl/?a", desc: "Mobile Billboard" }) === "mobile");
check("mobile at start of hay still mobile", vp({ url: "https://x.pl/?a", desc: "mobile" }) === "mobile");
// camelCase and percent-encoded separators: mobile at HEAD, and must stay so.
// 300x600 and 600x200 are not mobile-only sizes, so the name is all there is.
const camel = (desc, size) => vp({ url: "https://www.wp.pl/?a=1", desc, size });
check("label CommercialBreakMobile_bieg", camel("300x600-CommercialBreakMobile_bieg", "300x600") === "mobile");
check("label Wp_direct_…CommercialBreakMobile", camel("Wp_direct_300x600-CommercialBreakMobile", "300x600") === "mobile");
check("label WP_300x600 CommercialBreakMobile", camel("WP_300x600 CommercialBreakMobile", "300x600") === "mobile");
check("label 600x200-TopMobileBoard", camel("600x200-TopMobileBoard", "600x200") === "mobile");
check("desc HalfpageMobile", camel("HalfpageMobile", "300x600") === "mobile");
check("creName=BillboardMobile", vp({ url: WP + "BillboardMobile", size: "750x200" }) === "mobile");
const TCID = "https://www.wp.pl/?wfName=x&creName=y&tcidma=%5B%7B%22slot%22%3A%22035%22%2C%22id%22%3A%22200218%2F1458777%2Fiaq%2F";
check("tcidma %2FCommercialBreakMobile%2F", vp({ url: TCID + "CommercialBreakMobile%2F1580928%22%7D%5D", size: "300x600" }) === "mobile");
check("tcidma %2FMobile_Rectangle%2F", vp({ url: TCID + "Mobile_Rectangle%2F1580928%22%7D%5D", size: "300x250" }) === "mobile");
check("nested url ?ress%3Dmobile", vp({ url: "https://adbeta.example/p?url=https%3A%2F%2Fkobieta.onet.pl%2F%3Fress%3Dmobile" }) === "mobile");
check("u=…%2Fmobile", vp({ url: "https://preview.example/p?u=https%3A%2F%2Fwww.example.pl%2Fmobile" }) === "mobile");
check("creName=Banner%5Fmobile", vp({ url: "https://www.wp.pl/?creName=Banner%5Fmobile", size: "300x250" }) === "mobile");

// ── sheet ─────────────────────────────────────────────────────────────────
const S = x.state;
function reset() {
  S.rows = []; S.groups = []; S.testTargets = []; S.sources = []; S.scan = {};
  S._seenRows = new Set(); S._seenTargets = new Set();
  S.selectedVendors = new Set(["Adform", "CM360", "ABT Shield"]); S.vendorTouched = false;
  S.phase = "results";
}
function loadSheet() {
  x.extract([
    { cells: ["Money.pl_direct_300x600-Faktoring_desktop",
              "https://track.adform.net/adfserve/?bn=90565324;1x1inv=1;srctype=3"], ref: "S!row2", isSheet: true },
    { cells: ["Infor_direct_1140x300-Korpo",
              "https://track.adform.net/adfserve/?bn=90571110;1x1inv=1;srctype=3"], ref: "S!row3", isSheet: true },
  ], "sheet");
}
// The tid doubles as the variant, so a scan row's label (size_variant) is unique.
function target(tid, url, desc, size) {
  S.testTargets.push({ tid, url, desc, size: size || "", variant: tid });
}
const NL = String.fromCharCode(10);
function block(text, test) {
  // The lines of the text report belonging to one test.
  const lines = text.split(NL), i = lines.findIndex(l => l.includes(test));
  if (i < 0) return "";
  const out = [lines[i]];
  for (let j = i + 1; j < lines.length && lines[j] !== ""; j++) out.push(lines[j]);
  return out.join(NL);
}
const trOf = (html, needle) => (html.split("<tr>").find(s => s.includes(needle)) || "");
// One row of the Step 1 scan list, found by the test's label (size_variant).
function scanRow(label) {
  return els.scanList.innerHTML.split('<div class="scan-row">').find(s => s.includes(`<span class="plat">${label}</span>`)) || "";
}
const RED = "#f8e9e7", AMBER = "#f6efdd";

reset(); loadSheet();
check("sheet indexed", Object.keys((x.sheetIndex().Adform || {}).bn || {}).length === 2,
      JSON.stringify(Object.keys(x.sheetIndex())));

// A — an unbooked id with impression + click, from a backend that does not
// send working_unbooked. The page cannot tell which click was aimed at the
// creative, so it does not guess: the row reads as before.
target("t0", WP + "Faktoring_300x600_mob", "Faktoring 300x600 mob", "300x600");
S.scan.t0 = { status: "done", vendors: { Adform: { bn: ["90626723"] } },
  kinds: { Adform: { impression: ["90626723"], click: ["90626723"] } },
  diagnosis: ["none of the sheet's placements fired within 45s", "the click landed on another advertiser's creative"],
  click_attempted: true, click_result: "other_advertiser" };
// A2 — the backend names it, with another advertiser's tag beside it.
target("t1", WP + "Faktoring_300x250_mob", "Faktoring 300x250 mob", "300x250");
S.scan.t1 = { status: "done", vendors: { Adform: { bn: ["90626724"] }, CM360: { placement: ["455988298"] } },
  kinds: { Adform: { impression: ["90626724"], click: ["90626724"] }, CM360: { impression: ["455988298"] } },
  working_unbooked: [{ vendor: "Adform", id: 90626724 }],
  diagnosis: ["the creative works — Adform 90626724 impression and click — but the sheet does not book it"],
  click_attempted: true };
// A3 — the backend found none.
target("t2", WP + "Faktoring_160x600_mob", "Faktoring 160x600", "160x600");
S.scan.t2 = { status: "done", vendors: { Adform: { bn: ["90626725"] } },
  kinds: { Adform: { impression: ["90626725"], click: ["90626725"] } }, working_unbooked: [],
  diagnosis: ["tags fired on the page, but none this campaign books: Adform 90626725"], click_attempted: true };
// A4 — the booked id fired; an unbooked id beside it is "also on the page".
target("t3", "https://www.money.pl/?creName=Faktoring_300x600_desktop", "Faktoring 300x600 desktop", "300x600");
S.scan.t3 = { status: "done", vendors: { Adform: { bn: ["90565324", "90626726"] } },
  kinds: { Adform: { impression: ["90565324", "90626726"], click: ["90565324", "90626726"] } },
  diagnosis: [], click_attempted: true };
// A5 — an Adform-only sheet on a portal page where the click hit another
// advertiser's CM360 creative, old backend: not "our creative works".
target("t10", "https://www.dziennik.pl/?version=1140x300-portal", "1140x300 portal", "1140x300");
S.scan.t10 = { status: "done", vendors: { CM360: { placement: ["457769682"] } },
  kinds: { CM360: { impression: ["457769682"], click: ["457769682"] } },
  diagnosis: ["the click landed on another advertiser's creative"],
  click_attempted: true, click_result: "other_advertiser" };
// B — delivered, never shown (1140 on dziennik), with the pop-up's foreign tag.
target("t4", "https://www.dziennik.pl/?version=1140x300-korpo", "1140x300 korpo", "1140x300");
S.scan.t4 = { status: "done", vendors: { CM360: { placement: ["457769682"] } },
  kinds: { CM360: { impression: ["457769682"] } },
  diagnosis: ["Adform 90571110 was delivered to slot /17796319/newdz/newdz_sg/bill_top at 10s but its impression never fired — the slot was never in view",
              "tags fired on the page, but none this campaign books: CM360 457769682",
              "the vision check could not find the creative on screen"],
  click_attempted: true };
// B2 — nothing fired at all, only the delivered line.
target("t5", "https://www.dziennik.pl/?version=1140x600-korpo", "1140x600 korpo", "1140x600");
S.scan.t5 = { status: "none", vendors: {}, kinds: {},
  diagnosis: ["Adform 90571110 was delivered to slot /17796319/newdz/newdz_sg/bill_top at 12s but its impression never fired — slot never brought into view"] };
// C — delivered and in view, still never fired: a defect.
target("t6", "https://displayvideo.google.com/doubleclick/preview/main?creativeId=xbid.1&flexWidth=300&flexHeight=250", "DV360 300x250", "300x250");
S.scan.t6 = { status: "none", vendors: {}, kinds: {},
  diagnosis: ["Adform 90571110 was delivered to slot preview at 2s but its impression never fired, although the slot was in view from 3s"] };
// D — tracker pasted as plain text.
target("t7", "https://displayvideo.google.com/doubleclick/preview/main?creativeId=xbid.2&flexWidth=300&flexHeight=600", "DV360 300x600", "300x600");
S.scan.t7 = { status: "none", vendors: {}, kinds: {},
  diagnosis: ["Adform 90571110 was delivered to slot preview at 2s but its impression never fired",
              "tracker URL pasted as plain text after </script>, so no browser requests it: Adform 90571110"] };
// E — a delivered line plus a slow page only: still inconclusive.
target("t8", "https://www.dziennik.pl/?version=1140x300-euro", "1140x300 euro", "1140x300");
S.scan.t8 = { status: "none", vendors: {}, kinds: {},
  diagnosis: ["the page took longer than 60s to finish loading",
              "Adform 90571110 was delivered to slot bill_top at 30s but its impression never fired — the slot was not in view"] };
// F — consent wall + delivered: the consent wall is a problem of its own.
target("t9", "https://www.dziennik.pl/?version=1140x300-waluty", "1140x300 waluty", "1140x300");
S.scan.t9 = { status: "none", vendors: {}, kinds: {},
  diagnosis: ["the consent wall was not dismissed, so nothing served",
              "Adform 90571110 was delivered to slot bill_top at 30s but its impression never fired — the slot was not in view"] };

const rows = x.reportRows();
const text = x.reportText(rows);
const htmlR = x.reportHtml(rows);

const a = block(text, "Faktoring 300x600 mob");
check("A: old backend, no working sentence", !a.includes("impression and click work"), a);
check("A: old row kept", a.includes("no tags from this campaign fired — other tags on the page: Adform 90626723"), a);
check("A: marked !!", a.startsWith("!!"), a);
check("A: 'another advertiser' click line kept", a.includes("problem: the click landed on another advertiser's creative"), a);
check("A: NOTHING_FIRED line kept", a.includes("problem: none of the sheet's placements fired within 45s"), a);

const a2 = block(text, "Faktoring 300x250 mob");
check("A2: working sentence from backend", a2.includes("Adform 90626724: impression and click work, but the sheet does not book this ID"), a2);
check("A2: other tags listed without the working id", a2.includes(" — other tags on the page: CM360 455988298") && !/other tags on the page:.*90626724/.test(a2), a2);
check("A2: a backend line in other words shown unchanged", a2.includes("problem: the creative works — Adform 90626724 impression and click — but the sheet does not book it"), a2);

const a3 = block(text, "Faktoring 160x600");
check("A3: explicit [] respected", a3.includes("no tags from this campaign fired — other tags on the page: Adform 90626725") && !a3.includes("impression and click work"), a3);
check("A3: the backend's same list not repeated", !a3.includes("problem: tags fired on the page, but none this campaign books"), a3);

const a4 = block(text, "Faktoring 300x600 desktop");
check("A4: booked row OK, no working sentence", a4.startsWith("OK") && !a4.includes("impression and click work"), a4);
check("A4: unbooked listed as also on the page", a4.includes("also on the page, not this campaign: Adform 90626726"), a4);

const a5 = block(text, "1140x300 portal");
check("A5: another advertiser's CM360 is not 'ours, unbooked'", !a5.includes("impression and click work"), a5);
check("A5: old row and other-advertiser line", a5.includes("no tags from this campaign fired — other tags on the page: CM360 457769682")
      && a5.includes("problem: the click landed on another advertiser's creative"), a5);

const b = block(text, "1140x300 korpo");
check("B: delivered-never-shown is ??", b.startsWith("??"), b);
check("B: delivered line unchanged", b.includes("problem: Adform 90571110 was delivered to slot /17796319/newdz/newdz_sg/bill_top at 10s but its impression never fired — the slot was never in view"), b);
const b2 = block(text, "1140x600 korpo");
check("B2: nothing fired, only delivered -> ??", b2.startsWith("??"), b2);
const c = block(text, "DV360 300x250");
check("C: delivered while in view -> !!", c.startsWith("!!"), c);
const d = block(text, "DV360 300x600");
check("D: plain-text tracker -> !!", d.startsWith("!!"), d);
check("D: plain-text line unchanged", d.includes("problem: tracker URL pasted as plain text after </script>, so no browser requests it: Adform 90571110"), d);
const e = block(text, "1140x300 euro");
check("E: slow page + delivered -> ??", e.startsWith("??"), e);
const f = block(text, "1140x300 waluty");
check("F: consent wall + delivered -> !!", f.startsWith("!!"), f);
check("footnote for ??", text.includes("\"??\" on a delivered creative: the ad server sent it, but the run never confirmed it on")
      && text.includes("look at it in view before calling the tag missing"), text.slice(-400));

// HTML report
const ha = trOf(htmlR, "Faktoring 300x600 mob");
check("HTML A: old row, red", ha.includes("no tags from this campaign fired") && ha.includes(RED), ha);
const ha2 = trOf(htmlR, "Faktoring 300x250 mob");
check("HTML A2: sentence", ha2.includes("Adform 90626724: impression and click work, but the sheet does not book this ID"), ha2);
check("HTML A2: ID cell names the id", ha2.includes(">Adform 90626724<"), ha2);
check("HTML A2: red tint", ha2.includes(RED), ha2);
const hb = trOf(htmlR, "1140x300 korpo");
check("HTML B: amber, not red", hb.includes(AMBER) && !hb.includes(RED), hb);
check("HTML B: delivered line present", hb.includes("was delivered to slot /17796319/newdz/newdz_sg/bill_top"), hb);
const hd = trOf(htmlR, "DV360 300x600");
check("HTML D: red", hd.includes(RED), hd);
check("HTML D: plain-text line escaped", hd.includes("after &lt;/script&gt;"), hd);

// On-page: step 1 scan list and step 3 match table.
x.renderScan();
const scan = els.scanList.innerHTML;
check("scan A: no sentence from an old backend", !scan.includes("90626723: impression and click work"));
check("scan A5: no sentence for another advertiser", !scan.includes("457769682: impression and click work"));
const sa2 = scan.split('<div class="scan-row">').find(s => s.includes("90626724: impression and click work")) || "";
check("scan A2: red pill 'ID not in sheet'", sa2.includes('status-pill fail">ID not in sheet'), scan.slice(0, 900));
check("scan A4: no sentence for the booked row", !scan.includes("90626726: impression and click work"));
x.renderMatch && x.renderMatch();
const match = els.matchList.innerHTML;
check("match A2: sentence in verdict", match.includes("Adform 90626724: impression and click work, but the sheet does not book this ID"), match.slice(0, 600));
check("match A: old backend says 'not in sheet'", !match.includes("90626723: impression and click work"));
check("match A4: unbooked beside booked is another advertiser", !match.includes("90626726: impression and click work"));

// Step 2 unticks Adform: the scan list and the report agree.
S.selectedVendors = new Set(["CM360", "ABT Shield"]);
const uRows = x.reportRows(), uText = x.reportText(uRows);
x.renderScan();
const ua2 = block(uText, "Faktoring 300x250 mob");
check("unticked: report has no working sentence", !ua2.includes("impression and click work")
      && ua2.includes("no tags from this campaign fired — other tags on the page: CM360 455988298"), ua2);
check("unticked: scan has no 'ID not in sheet'", !els.scanList.innerHTML.includes("90626724: impression and click work")
      && !els.scanList.innerHTML.includes("ID not in sheet"), els.scanList.innerHTML.slice(0, 900));

// No sheet loaded: nothing is "not booked".
reset();
target("t0", WP + "Faktoring_300x600_mob", "Faktoring 300x600 mob", "300x600");
S.scan.t0 = { status: "done", vendors: { Adform: { bn: ["90626723"] } },
  kinds: { Adform: { impression: ["90626723"], click: ["90626723"] } },
  working_unbooked: [{ vendor: "Adform", id: "90626723" }], diagnosis: [], click_attempted: true };
check("no sheet: nothing named", x.workingUnbooked(S.scan.t0).length === 0);
const nt = x.reportText(x.reportRows());
check("no sheet: plain OK row", block(nt, "Faktoring 300x600 mob").startsWith("OK"), nt);

// ── isUnshown ─────────────────────────────────────────────────────────────
check("isUnshown: design wording, never in view", x.isUnshown("ad server delivered Adform 1 to /a/bill_top at 10s; impression never requested — slot never in view"));
check("isUnshown: design wording, in view from", !x.isUnshown("ad server delivered Adform 1 to /a/bill_top at 10s; impression never requested — in view from 13s"));
check("isUnshown: was never requested", x.isUnshown("this campaign's creative was delivered (Adform 90571110 in Ad Manager slot bill_top) but its impression was never requested — the slot was not in view; not a missing tag"));
check("isUnshown: 'although in view' is a defect", !x.isUnshown("Adform 1 was delivered to slot x but its impression never fired although the slot was in view for 3s"));
check("isUnshown: plain text is a defect", !x.isUnshown("Adform 1 was delivered to slot x but its impression never fired: tracker URL pasted as plain text"));
check("isUnshown: unrelated line", !x.isUnshown("none of the sheet's placements fired within 260s"));

// The engine's exact wording (backend/engine.py, discover).
const ENG_SLOT = "Adform 90571110 was delivered to slot bill_top but its impression never fired — the slot was not rendered/in view during the test";
const ENG_SRC = "Adform 90571110 was delivered by securepubads.g.doubleclick.net but its impression never fired — the creative was not rendered/in view during the test";
const ENG_OTHERS = "other tags that fired on the page are not in the sheet: CM360 457769682";
const ENG_PLAIN = "Adform 90571110 impression: tracker URL pasted as plain text — no browser will request it";
const ENG_CARRIED = "the previewed creative (creativeId 752653503) carries Adform 90000001, which the sheet does not book";
const ENG_WORKS = "the creative works — impression and click both carry Adform 90626723 — but the sheet does not book 90626723";
const ENG_OTHER_ADV = "the click landed on another advertiser's creative";
// What the backend could say once it knows whether the slot came into view.
const SLOT_IN_VIEW = "Adform 90571110 was delivered to slot bill_top but its impression never fired — the slot was in view from 23.4s";
const SLOT_NEVER = "Adform 90571110 was delivered to slot bill_top but its impression never fired — the slot was never in view";
check("isUnshown: engine slot line", x.isUnshown(ENG_SLOT));
check("isUnshown: engine source line", x.isUnshown(ENG_SRC));
check("isUnshown: 'not rendered or in view'", x.isUnshown("Adform 1 was delivered to slot x but its impression never fired — the slot was not rendered or in view"));
check("isUnshown: engine plain-text line", !x.isUnshown(ENG_PLAIN));
check("isUnshown: doubled quotes line", !x.isUnshown("IAS 1 measurement: the tag is delivered with its attribute wrapped in doubled quotes, so its address is empty and the browser never requests it"));
check("isUnshown: 'in view from 23.4s' is a defect", !x.isUnshown(SLOT_IN_VIEW));
check("isUnshown: 'never in view'", x.isUnshown(SLOT_NEVER));

// ── the backend's structured fields ───────────────────────────────────────
reset(); loadSheet();
const DNF = (slot) => [{ vendor: "Adform", id: "90571110", slot, source: "securepubads.g.doubleclick.net" }];
target("e0", "https://www.dziennik.pl/?version=1140x300-korpo", "E0 1140x300 korpo", "1140x300");
S.scan.e0 = { status: "done", vendors: { CM360: { placement: ["457769682"] } }, kinds: { CM360: { impression: ["457769682"] } },
  delivered_not_fired: DNF("bill_top"), working_unbooked: [],
  diagnosis: [ENG_SLOT, ENG_OTHERS, "the vision check could not find the creative on screen"], click_attempted: true };
target("e1", "https://www.dziennik.pl/?version=1140x600-korpo", "E1 1140x600 korpo", "1140x600");
S.scan.e1 = { status: "none", vendors: {}, kinds: {}, working_unbooked: [], delivered_not_fired: DNF(null), diagnosis: [ENG_SRC] };
target("e2", "https://displayvideo.google.com/doubleclick/preview/main?creativeId=xbid.3", "E2 DV360 plain", "300x250");
S.scan.e2 = { status: "none", vendors: {}, kinds: {}, working_unbooked: [], delivered_not_fired: [],
  markup_defects: [{ vendor: "Adform", kind: "impression", id: "90571110", tag: "text", problem: "tracker URL pasted as plain text — no browser will request it" }],
  diagnosis: [ENG_PLAIN] };
target("e3", "https://displayvideo.google.com/doubleclick/preview/main?creativeId=xbid.752653503", "E3 DV360 carried", "300x600");
S.scan.e3 = { status: "done", vendors: { Adform: { bn: ["90000001"] } }, kinds: { Adform: { impression: ["90000001"] } },
  working_unbooked: [], delivered_not_fired: [], diagnosis: [ENG_CARRIED] };
target("e4", WP + "Faktoring_300x600_mob", "E4 Faktoring mob", "300x600");
S.scan.e4 = { status: "done", vendors: { Adform: { bn: ["90626723"] }, CM360: { placement: ["455988298"] } },
  kinds: { Adform: { impression: ["90626723"], click: ["90626723"] }, CM360: { impression: ["455988298"] } },
  working_unbooked: [{ vendor: "Adform", id: "90626723" }], delivered_not_fired: [],
  diagnosis: [ENG_WORKS, "other tags that fired on the page are not in the sheet: CM360 455988298"],
  click_attempted: true, click_result: "other_advertiser" };
// The backend kept the other-advertiser line: a second click really did land elsewhere.
target("e5", WP + "Faktoring_300x250_mob", "E5 Faktoring mob 300x250", "300x250");
S.scan.e5 = { status: "done", vendors: { Adform: { bn: ["90626720"] }, CM360: { placement: ["457769682"] } },
  kinds: { Adform: { impression: ["90626720"], click: ["90626720"] }, CM360: { impression: ["457769682"], click: ["457769682"] } },
  working_unbooked: [{ vendor: "Adform", id: "90626720" }], delivered_not_fired: [],
  diagnosis: ["the creative works — impression and click both carry Adform 90626720 — but the sheet does not book 90626720",
              "other tags that fired on the page are not in the sheet: CM360 457769682", ENG_OTHER_ADV],
  click_attempted: true, click_result: "other_advertiser" };
// Delivered, and the slot was in view: a defect, whatever the field says.
target("e6", "https://www.dziennik.pl/?version=1140x300-inview", "E6 1140x300 in view", "1140x300");
S.scan.e6 = { status: "none", vendors: {}, kinds: {}, working_unbooked: [], delivered_not_fired: DNF("bill_top"),
  diagnosis: [SLOT_IN_VIEW] };
// Delivered, and the consent wall stayed up: the wall is the finding.
target("e7", "https://www.dziennik.pl/?version=1140x300-wall", "E7 1140x300 wall", "1140x300");
S.scan.e7 = { status: "none", vendors: {}, kinds: {}, working_unbooked: [], delivered_not_fired: DNF("bill_top"),
  diagnosis: ["the consent wall was not dismissed, so nothing served", ENG_SLOT] };
// Delivered on a page where only an unticked vendor's tag fired.
target("e8", "https://www.dziennik.pl/?version=1140x300-ias", "E8 1140x300 ias", "1140x300");
S.scan.e8 = { status: "done", vendors: { IAS: { pixel: ["123"] } }, kinds: { IAS: { impression: ["123"] } },
  working_unbooked: [], delivered_not_fired: DNF("bill_top"), diagnosis: [SLOT_NEVER] };

const eRows = x.reportRows(), eText = x.reportText(eRows), eHtml = x.reportHtml(eRows);
const eb0 = block(eText, "E0 1140x300 korpo");
check("E0: delivered + others + vision -> ??", eb0.startsWith("??"), eb0);
check("E0: headline names the delivered tag", eb0.includes("delivered, not viewed — Adform 90571110 in bill_top — other tags on the page: CM360 457769682"), eb0);
check("E0: not 'no tags from this campaign fired'", !eb0.includes("no tags from this campaign fired"), eb0);
check("E0: engine line unchanged", eb0.includes("problem: " + ENG_SLOT), eb0);
check("E0: other-tags line not repeated", !eb0.includes("problem: " + ENG_OTHERS), eb0);
check("E0: vision line kept", eb0.includes("problem: the vision check could not find the creative on screen"), eb0);
const eb1 = block(eText, "E1 1140x600 korpo");
check("E1: engine source line alone -> ??", eb1.startsWith("??"), eb1);
check("E1: headline without a slot", eb1.includes("    delivered, not viewed — Adform 90571110" + NL), eb1);
const eb2 = block(eText, "E2 DV360 plain");
check("E2: plain text -> !!", eb2.startsWith("!!") && eb2.includes("problem: " + ENG_PLAIN), eb2);
check("E2: no delivered headline", eb2.includes("no tags fired") && !eb2.includes("delivered, not viewed"), eb2);
const eb3 = block(eText, "E3 DV360 carried");
check("E3: carried unbooked tag -> !!", eb3.startsWith("!!") && eb3.includes("problem: " + ENG_CARRIED), eb3);
const eb4 = block(eText, "E4 Faktoring mob");
check("E4: working sentence", eb4.includes("Adform 90626723: impression and click work, but the sheet does not book this ID — other tags on the page: CM360 455988298"), eb4);
check("E4: !!", eb4.startsWith("!!"), eb4);
check("E4: works line not repeated", !eb4.includes("problem: " + ENG_WORKS), eb4);
check("E4: other-tags line not repeated", !eb4.includes("problem: other tags that fired on the page"), eb4);
const eb5 = block(eText, "E5 Faktoring mob 300x250");
check("E5: working sentence", eb5.includes("Adform 90626720: impression and click work, but the sheet does not book this ID — other tags on the page: CM360 457769682"), eb5);
check("E5: the backend's other-advertiser line kept", eb5.includes("problem: " + ENG_OTHER_ADV), eb5);
const eb6 = block(eText, "E6 1140x300 in view");
check("E6: in view, never fired -> !!", eb6.startsWith("!!"), eb6);
check("E6: headline does not say 'not viewed'", eb6.includes("delivered, impression never fired — Adform 90571110 in bill_top") && !eb6.includes("not viewed"), eb6);
const eb7 = block(eText, "E7 1140x300 wall");
check("E7: consent wall + delivered -> !!", eb7.startsWith("!!"), eb7);
const eb8 = block(eText, "E8 1140x300 ias");
check("E8: only an unticked vendor fired -> ??", eb8.startsWith("??") && eb8.includes("delivered, not viewed — Adform 90571110 in bill_top (other tags on the page: IAS)"), eb8);
check("HTML E0: amber", trOf(eHtml, "E0 1140x300").includes(AMBER) && !trOf(eHtml, "E0 1140x300").includes(RED), trOf(eHtml, "E0 1140x300"));
check("HTML E0: ID cell names the delivered tag", trOf(eHtml, "E0 1140x300").includes(">Adform 90571110<"), trOf(eHtml, "E0 1140x300"));
check("HTML E1: amber", trOf(eHtml, "E1 1140x600").includes(AMBER) && !trOf(eHtml, "E1 1140x600").includes(RED));
check("HTML E2: red", trOf(eHtml, "E2 DV360").includes(RED));
check("HTML E4: red, sentence", trOf(eHtml, "E4 Faktoring").includes(RED) && trOf(eHtml, "E4 Faktoring").includes("impression and click work, but the sheet does not book this ID"));
check("HTML E6: red", trOf(eHtml, "E6 1140x300").includes(RED), trOf(eHtml, "E6 1140x300"));

x.renderScan();
const s0 = scanRow("1140x300_e0"), s1 = scanRow("1140x600_e1");
check("scan E0: amber 'delivered, not viewed'", s0.includes('status-pill warn">delivered, not viewed<'), s0);
check("scan E0: detail names the tag", s0.includes("delivered, not viewed — Adform 90571110 in bill_top"), s0);
check("scan E1: status none, amber", s1.includes('status-pill warn">delivered, not viewed<'), s1);
const s6 = scanRow("1140x300_e6"), s7 = scanRow("1140x300_e7");
check("scan E6: in view stays red 'no tags fired'", s6.includes('status-pill fail">no tags fired<')
      && s6.includes("delivered, impression never fired"), s6);
check("scan E7: consent wall stays red", s7.includes('status-pill fail">no tags fired<'), s7);
check("scan E4: red 'ID not in sheet'", scanRow("300x600_e4").includes('status-pill fail">ID not in sheet<'), scanRow("300x600_e4"));
check("scan E2: plain text stays red", scanRow("300x250_e2").includes('status-pill fail">no tags fired<'), scanRow("300x250_e2"));

console.log(`${passes} passed, ${fails} failed`);
process.exit(fails ? 1 : 0);
