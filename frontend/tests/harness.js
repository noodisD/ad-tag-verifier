// Loads the page script of frontend/index.html into a vm with a stub DOM, so
// its report and viewport logic can be checked offline. No network, no
// browser. FE_HTML points it at another copy of the page (a HEAD checkout, to
// compare the two).
const fs = require("fs"), path = require("path"), vm = require("vm");
const html = fs.readFileSync(process.env.FE_HTML || path.join(__dirname, "..", "index.html"), "utf8");
const m = html.match(/<script>\s*"use strict";([\s\S]*?)<\/script>\s*<\/body>/);
if (!m) throw new Error("no page script found in index.html");
let src = '"use strict";' + m[1];
// The page pings the backend on load; there is none here.
src = src.replace(/\s*checkBackend\(\);\s*$/, "\n");
// Names an older copy of the page may lack come out as null.
const opt = ["hasMobToken", "workingUnbooked", "bookedFired", "isUnshown", "unshownOnly",
             "deliveredUnfired", "pickedVendor", "runOptions", "clampParallel", "renderVerify",
             "watchActiveOf", "settleUnfinished", "cancelRun", "endWatch", "runScan",
             "runVerification", "clearAll"]
  .map(n => `${n}: typeof ${n} === 'undefined' ? null : ${n}`).join(", ");
src += "\n;globalThis.__x = {state, extract, reportRows, reportText, reportHtml, renderScan, renderMatch,"
     + " guessViewport, sheetIndex, " + opt + "};";

function el(id) {
  const store = { id, innerHTML: "", textContent: "", hidden: false, value: "", disabled: false, title: "", className: "",
    dataset: {}, style: {}, children: [], _l: {} };
  store.classList = { add(){}, remove(){}, toggle(){}, contains(){ return false; } };
  store.addEventListener = (t, f) => { store._l[t] = f; };
  store.appendChild = () => {}; store.select = () => {}; store.focus = () => {};
  store.closest = () => null;
  return store;
}
const els = {};
const document = {
  getElementById: (id) => els[id] || (els[id] = el(id)),
  querySelector: () => el("q"),
  createElement: () => el("c"),
  body: el("body"),
  execCommand: () => true,
};
const ctx = { document, window: null, console, setTimeout: () => 0, clearTimeout(){},
  localStorage: { getItem(){ return null; }, setItem(){} },
  fetch: () => Promise.reject(new Error("offline")),
  AbortController, Blob, URL, navigator: {}, atob: (s) => Buffer.from(s, "base64").toString("binary"),
  FileReader: function(){}, XLSX: undefined, ClipboardItem: undefined };
ctx.window = ctx; ctx.window.addEventListener = () => {};
ctx.globalThis = ctx;
vm.createContext(ctx);
vm.runInContext(src, ctx, { filename: "index.html.js" });
// `ctx` is exported so a test can stand in for the network (ctx.fetch) and the
// clock (ctx.setTimeout) and drive a run from start to finish.
module.exports = { x: ctx.__x, els, ctx };
