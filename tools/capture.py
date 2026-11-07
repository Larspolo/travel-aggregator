"""The tools of the `capture` skill: save the responses of a travel site page as a HAR, remove the personal data,
and push the HAR to a capture branch (`.claude/skills/capture/SKILL.md`).

    python3 tools/capture.py hook --match REGEX           # the JavaScript for the page: it records the responses
    python3 tools/capture.py scrub RAW.har ... --out OUT.har [--match REGEX] [--private TEXT ...]
    python3 tools/capture.py publish OUT.har --issue N --source bahn.de [--branch owner/bahn-captures]

The hook only observes the responses that the page requested itself, as a userscript does: it sends no request (P1).
`scrub` keeps only the content type of the headers, no cookies, and replaces e-mail addresses, the values of personal
keys and the `--private` words (and the name and e-mail of `git config`) with REDACTED (P5). `publish` refuses a
file that `scrub` did not clean. It commits in a temporary git worktree, so the checkout of the user does not change.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REDACTED = "REDACTED"
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[a-z]{2,}", re.I)
# The keys whose values are personal data (compared in lower case, with no "-", "_" or ".").
PERSONAL = {"email", "emailadresse", "mail", "vorname", "nachname", "firstname", "lastname", "givenname",
            "familyname", "fullname", "surname", "voornaam", "achternaam", "geburtsdatum", "birthdate",
            "dateofbirth", "telefon", "telefonnummer", "phone", "phonenumber", "mobile", "kundennummer",
            "customerid", "customernumber", "kundenkonto", "bahncardnummer", "cardnumber", "iban", "password",
            "passwort", "authorization", "cookie", "setcookie", "accesstoken", "refreshtoken", "idtoken",
            "sessionid", "anschrift", "address", "street", "strasse", "postcode", "postleitzahl", "zipcode"}
KEEP_HEADERS = {"content-type"}
MAX_BYTES = 50_000_000      # GitHub refuses a file of more than 100 MB; a capture is much smaller

HOOK = r"""(() => {
  const MATCH = new RegExp(__MATCH__);
  const MAX = 20000000;
  const w = window;
  if (w.__taCap) { w.__taCap.match = MATCH; return JSON.stringify({installed: true, again: true, entries: w.__taCap.entries.length}); }
  const cap = {match: MATCH, entries: [], size: 0};
  w.__taCap = cap;
  const seen = new WeakSet();
  const add = (method, url, reqType, reqText, status, statusText, resType, resText, t0) => {
    try {
      const abs = new URL(String(url), location.href).href;
      if (!cap.match.test(abs) || typeof resText !== "string") return;
      if (cap.size + resText.length > MAX) return;
      cap.size += resText.length;
      const q = [...new URL(abs).searchParams].map(([name, value]) => ({name, value}));
      const request = {method: method === null ? "" : String(method || "GET").toUpperCase(), url: abs, httpVersion: "", cookies: [],
        headers: reqType ? [{name: "content-type", value: reqType}] : [], queryString: q, headersSize: -1,
        bodySize: reqText ? reqText.length : 0};
      if (typeof reqText === "string") request.postData = {mimeType: reqType || "", text: reqText};
      cap.entries.push({startedDateTime: new Date(t0).toISOString(), time: Date.now() - t0, request,
        response: {status, statusText: statusText || "", httpVersion: "", cookies: [],
          headers: resType ? [{name: "content-type", value: resType}] : [],
          content: {size: resText.length, mimeType: resType || "", text: resText},
          redirectURL: "", headersSize: -1, bodySize: resText.length},
        cache: {}, timings: {send: 0, wait: Date.now() - t0, receive: 0}});
    } catch (e) { /* the page must not break */ }
  };
  const RP = w.Response && w.Response.prototype;
  const plainText = RP && RP.text;
  const readText = (r) => (plainText ? plainText.call(r) : r.text());
  const origFetch = w.fetch;
  if (typeof origFetch === "function") {
    const hooked = function (input, init) {
      const t0 = Date.now();
      const promise = origFetch.apply(this, arguments);
      try {
        const url = input && typeof input === "object" && "url" in input ? input.url : input;
        const method = (init && init.method) || (input && input.method) || "GET";
        const body = init && typeof init.body === "string" ? init.body : null;
        let reqType = "";
        try { reqType = new Headers((init && init.headers) || {}).get("content-type") || ""; } catch (e) { /* ignore */ }
        promise.then((res) => {
          seen.add(res);
          return readText(res.clone()).then((text) =>
            add(method, url, reqType, body, res.status, res.statusText, res.headers.get("content-type"), text, t0));
        }, () => {}).catch(() => {});
      } catch (e) { /* ignore */ }
      return promise;
    };
    hooked.__taCap = true;
    w.fetch = hooked;
  }
  // The page may keep its own fetch reference: record a response when the page reads it (#399). The request is
  // unknown here (method ""). A response that the fetch wrapper recorded is not recorded again.
  let response = false;
  if (RP) {
    for (const name of ["text", "json", "arrayBuffer"]) {
      const read = RP[name];
      if (typeof read !== "function") continue;
      const wrapped = function () {
        let copy = null;
        const t0 = Date.now();
        try {
          const abs = new URL(String(this.url), location.href).href;
          if (cap.match.test(abs) && !seen.has(this) && !this.bodyUsed) copy = this.clone();
        } catch (e) { copy = null; }
        const promise = read.apply(this, arguments);
        if (copy) {
          seen.add(this);
          const res = this;
          readText(copy).then((text) => add(null, res.url, "", null, res.status, res.statusText,
            res.headers.get("content-type"), text, t0), () => {}).catch(() => {});
        }
        return promise;
      };
      try { RP[name] = wrapped; } catch (e) { /* the page keeps its own method */ }
      if (RP[name] === wrapped) response = true;
    }
  }
  const X = w.XMLHttpRequest && w.XMLHttpRequest.prototype;
  if (X) {
    const open = X.open, send = X.send, setHeader = X.setRequestHeader;
    const descText = Object.getOwnPropertyDescriptor(X, "responseText");
    const descResp = Object.getOwnPropertyDescriptor(X, "response");
    // One XHR response is recorded once: at loadend (open/send wrappers) or when the page reads it through the
    // getters (#169: the open/send wrappers may not see the request). The original getters are called directly.
    const doneX = new WeakSet();
    const recordXhr = (xhr) => {
      try {
        if (xhr.readyState !== 4 || doneX.has(xhr)) return;
        doneX.add(xhr);
        const m = xhr.__ta || {};
        const t = xhr.responseType;
        const text = !t || t === "text" ? descText.get.call(xhr) : t === "json" ? JSON.stringify(descResp.get.call(xhr)) : null;
        const url = m.url !== undefined ? m.url : xhr.responseURL;
        add(m.method === undefined ? null : m.method, url, m.type || "", typeof m.body === "string" ? m.body : null,
          xhr.status, xhr.statusText, xhr.getResponseHeader("content-type"), text, m.t0 || Date.now());
      } catch (e) { /* the page must not break */ }
    };
    X.open = function (method, url) { this.__ta = {method, url, type: ""}; return open.apply(this, arguments); };
    X.setRequestHeader = function (name, value) {
      if (this.__ta && String(name).toLowerCase() === "content-type") this.__ta.type = String(value);
      return setHeader.apply(this, arguments);
    };
    X.send = function (body) {
      const m = this.__ta;
      if (m) {
        m.body = body;
        m.t0 = Date.now();
        this.addEventListener("loadend", () => recordXhr(this));
      }
      return send.apply(this, arguments);
    };
    try {
      if (descText && descText.get) Object.defineProperty(X, "responseText", {configurable: true, enumerable: descText.enumerable,
        get() { const v = descText.get.call(this); recordXhr(this); return v; }});
      if (descResp && descResp.get) Object.defineProperty(X, "response", {configurable: true, enumerable: descResp.enumerable,
        get() { const v = descResp.get.call(this); recordXhr(this); return v; }});
    } catch (e) { /* the page keeps its own getters: the open/send wrappers still record */ }
  }
  cap.list = () => JSON.stringify(cap.entries.map((e) => ({method: e.request.method, url: e.request.url,
    status: e.response.status, size: e.response.content.size})));
  cap.save = (name) => {
    const har = {log: {version: "1.2", creator: {name: "travel-aggregator capture", version: "1"},
      pages: [], entries: cap.entries}};
    const blob = new Blob([JSON.stringify(har)], {type: "application/json"});
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = String(name).replace(/[^\w.-]+/g, "-") + ".har";
    document.body.appendChild(a);
    a.click();
    a.remove();
    return JSON.stringify({saved: a.download, entries: cap.entries.length, bytes: blob.size});
  };
  return JSON.stringify({installed: true, again: false, fetch: !!(w.fetch && w.fetch.__taCap), xhr: !!X, response});
})()"""


def hook(match):
    re.compile(match)
    return HOOK.replace("__MATCH__", json.dumps(match))


def private_words(extra=(), identity=True):
    """The words to remove: the `--private` texts, CAPTURE_PRIVATE (";" between texts), and with `identity` the
    name and e-mail of `git config`. A name gives each of its words of 4 or more letters ("Jeroen van Berg" gives
    "Jeroen" and "Berg")."""
    texts = list(extra) + os.environ.get("CAPTURE_PRIVATE", "").split(";")
    for key in ("user.name", "user.email") if identity else ():
        got = subprocess.run(["git", "config", key], capture_output=True, text=True, cwd=ROOT)
        texts.append(got.stdout.strip())
    words = set()
    for t in texts:
        t = t.strip()
        if not t:
            continue
        words.add(t)
        words.update(w for w in re.split(r"[\s@.,;<>()]+", t) if len(w) >= 4)
    return sorted(words, key=len, reverse=True)


def personal_key(key):
    return re.sub(r"[-_.\s]", "", str(key)).lower() in PERSONAL


class Cleaner:
    def __init__(self, words):
        self.count = 0
        self.words = [re.compile(re.escape(w), re.I) for w in words]

    def text(self, s):
        for pattern in [EMAIL, *self.words]:
            s, n = pattern.subn(REDACTED, s)
            self.count += n
        return s

    def value(self, v):
        if isinstance(v, dict):
            out = {}
            for k, x in v.items():
                if personal_key(k) and x not in (None, "", [], {}):
                    self.count += 1
                    out[k] = REDACTED
                else:
                    out[k] = self.value(x)
            return out
        if isinstance(v, list):
            return [self.value(x) for x in v]
        if isinstance(v, str):
            return self.text(v)
        return v

    def body(self, text):
        """A JSON body is cleaned per key and value; another body as text."""
        try:
            data = json.loads(text)
        except (TypeError, ValueError):
            return self.text(text)
        return json.dumps(self.value(data), ensure_ascii=False)


def entries_of(path):
    data = json.loads(Path(path).read_text("utf-8"))
    entries = (data.get("log") or {}).get("entries") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        raise SystemExit(f"{path}: no HAR (log.entries is missing)")
    return entries


def clean_entry(e, cleaner):
    req, res = e.get("request") or {}, e.get("response") or {}
    content = res.get("content") or {}
    post = req.get("postData")
    keep = lambda hs: [{"name": h["name"].lower(), "value": h.get("value", "")}  # noqa: E731
                       for h in hs or [] if str(h.get("name", "")).lower() in KEEP_HEADERS]
    request = {"method": req.get("method", "GET"), "url": cleaner.text(req.get("url", "")), "httpVersion": "",
               "cookies": [], "headers": keep(req.get("headers")),
               "queryString": [{"name": q.get("name", ""), "value": cleaner.text(str(q.get("value", "")))}
                               for q in req.get("queryString") or [] if not personal_key(q.get("name", ""))],
               "headersSize": -1, "bodySize": req.get("bodySize", -1)}
    if post and isinstance(post.get("text"), str):
        request["postData"] = {"mimeType": post.get("mimeType", ""), "text": cleaner.body(post["text"])}
    text = content.get("text")
    if isinstance(text, str) and content.get("encoding") == "base64":
        text = None                                   # a binary body: the parsers read only JSON
    response = {"status": res.get("status", 0), "statusText": res.get("statusText", ""), "httpVersion": "",
                "cookies": [], "headers": keep(res.get("headers")),
                "content": {"size": len(text) if text else 0, "mimeType": content.get("mimeType", ""),
                            **({"text": cleaner.body(text)} if text else {})},
                "redirectURL": "", "headersSize": -1, "bodySize": -1}
    return {"startedDateTime": e.get("startedDateTime", ""), "time": e.get("time", 0), "request": request,
            "response": response, "cache": {}, "timings": {"send": 0, "wait": e.get("time", 0), "receive": 0}}


def scrub(paths, match=None, private=(), identity=True):
    """The cleaned HAR of the entries of `paths` (one or more HAR files, also a HAR of the developer tools), and
    the number of replaced values."""
    pattern = re.compile(match) if match else None
    cleaner = Cleaner(private_words(private, identity))
    entries = []
    for p in paths:
        for e in entries_of(p):
            url = (e.get("request") or {}).get("url", "")
            if pattern is None or pattern.search(url):
                entries.append(clean_entry(e, cleaner))
    entries.sort(key=lambda e: e["startedDateTime"])
    har = {"log": {"version": "1.2", "creator": {"name": "travel-aggregator capture", "version": "1"},
                   "pages": [], "entries": entries}}
    return har, cleaner.count


def problems(har, private=(), identity=True):
    """The reasons why a HAR is not safe to publish ([] = safe)."""
    out = []
    entries = (har.get("log") or {}).get("entries")
    if not entries:
        return ["the HAR has no entries"]
    for i, e in enumerate(entries):
        for side in ("request", "response"):
            part = e.get(side) or {}
            if part.get("cookies"):
                out.append(f"entry {i}: {side} cookies")
            extra = [h.get("name") for h in part.get("headers") or [] if str(h.get("name")).lower() not in KEEP_HEADERS]
            if extra:
                out.append(f"entry {i}: {side} headers {extra}")
    text = json.dumps(har, ensure_ascii=False)
    if EMAIL.search(text):
        out.append(f"an e-mail address: {EMAIL.search(text).group(0)[:3]}...")
    for w in private_words(private, identity):
        if re.search(re.escape(w), text, re.I):
            out.append(f"a private word ({len(w)} letters)")
    return out


def summary(har, replaced):
    rows = [{"method": e["request"]["method"], "url": e["request"]["url"][:160], "status": e["response"]["status"],
             "size": e["response"]["content"]["size"]} for e in har["log"]["entries"]]
    return {"entries": len(rows), "replaced": replaced, "requests": rows}


def git(*args, cwd=None):
    r = subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd or ROOT)
    if r.returncode:
        raise SystemExit(f"git {' '.join(args)}: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout.strip()


def default_branch(source):
    return f"owner/{source.split('.')[0]}-captures"


def publish(path, issue, source, branch=None, private=(), root=ROOT, identity=True):
    """Commit the HAR to `captures/<source>/` of the capture branch of the git clone `root` and push it.
    Returns (branch, file, commit)."""
    path = Path(path)
    har = json.loads(path.read_text("utf-8"))
    bad = problems(har, private, identity)
    if bad:
        raise SystemExit("Not published: " + "; ".join(bad) + ". Run `scrub` first.")
    if path.stat().st_size > MAX_BYTES:
        raise SystemExit(f"Not published: {path} has more than {MAX_BYTES} bytes")
    branch = branch or default_branch(source)
    name = path.name if path.name.startswith(f"{issue}-") else f"{issue}-{path.name}"
    target = f"captures/{source}/{name}"
    exists = subprocess.run(["git", "fetch", "-q", "origin", branch], capture_output=True, cwd=root).returncode == 0
    if exists:
        base = git("rev-parse", "FETCH_HEAD", cwd=root)
    else:
        git("fetch", "-q", "origin", main_branch(), cwd=root)
        base = git("rev-parse", "FETCH_HEAD", cwd=root)
    tmp = Path(tempfile.mkdtemp(prefix="capture-"))
    work = tmp / "tree"
    try:
        git("worktree", "add", "-q", "--detach", str(work), base, cwd=root)
        (work / target).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, work / target)
        git("add", target, cwd=work)
        git("commit", "-q", "--no-verify", "-m", f"Add the {source} capture of #{issue}", cwd=work)
        git("push", "-q", "origin", f"HEAD:refs/heads/{branch}", cwd=work)
        commit = git("rev-parse", "HEAD", cwd=work)
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(work)], capture_output=True, cwd=root)
        shutil.rmtree(tmp, ignore_errors=True)
    return branch, target, commit


def config():
    try:
        return tomllib.loads((ROOT / "agent.toml").read_text("utf-8"))
    except OSError:
        return {}


def main_branch():
    return config().get("branch", "main")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("hook", help="print the JavaScript that records the responses of the page")
    h.add_argument("--match", default=".", help="a regular expression of the URLs to keep")
    s = sub.add_parser("scrub", help="clean one or more HAR files into one HAR")
    s.add_argument("files", nargs="+")
    s.add_argument("--out", required=True)
    s.add_argument("--match")
    s.add_argument("--private", action="append", default=[])
    p = sub.add_parser("publish", help="push a clean HAR to the capture branch")
    p.add_argument("file")
    p.add_argument("--issue", type=int, required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--branch")
    p.add_argument("--private", action="append", default=[])
    a = ap.parse_args(argv)
    if a.cmd == "hook":
        print(hook(a.match))
        return 0
    if a.cmd == "scrub":
        har, replaced = scrub(a.files, a.match, a.private)
        bad = problems(har, a.private)
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(har, ensure_ascii=False, indent=1), "utf-8")
        print(json.dumps({**summary(har, replaced), "out": a.out, "problems": bad}, ensure_ascii=False, indent=1))
        return 1 if bad else 0
    branch, target, commit = publish(a.file, a.issue, a.source, a.branch, a.private)
    repo = config().get("repo", "")
    print(json.dumps({"branch": branch, "file": target, "commit": commit,
                      "url": f"https://github.com/{repo}/blob/{commit}/{target}"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
