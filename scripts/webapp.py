# webapp.py — Flask UI for IG bot (fixed HTML block)
import os, sys, io, time, json, threading, contextlib
from collections import deque
from typing import List
from flask import Flask, request, Response, render_template_string, jsonify

from actions import (  # type: ignore
    run_auto_campaign,
    search_and_follow,
    set_login_credentials,
    unfollow_due,
)

app = Flask(__name__)
LOGQ: deque[str] = deque(maxlen=4000)
STATE = {
    "running": False,
    "thread": None,                   # type: ignore
    "stop": threading.Event(),
    "params": {},
}

HTML = """
<!doctype html>
<meta charset="utf-8">
<title>IG Clone Bot</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root { color-scheme: dark; }
  body{font:14px system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell;
       background:#0b0b0b; color:#ddd; margin:0}
  header{display:flex;align-items:center;gap:10px;padding:12px 16px;border-bottom:1px solid #222}
  .pill{font:12px mono;background:#222;border:1px solid #333;padding:2px 8px;border-radius:999px}
  .pill.on{background:#113a19;border-color:#1f6f2f;color:#c6f6d5}
  .pill.off{background:#3a1111;border-color:#6f1f1f;color:#f6c6c6}
  main{padding:16px;max-width:980px;margin:0 auto}
  fieldset{border:1px solid #222;border-radius:10px;padding:12px 16px}
  legend{opacity:.8}
  label{display:block;margin:6px 0}
  input[type="text"],input[type="password"],input[type="number"]{background:#111;color:#ddd;border:1px solid #222;border-radius:6px;padding:6px 8px}
  .row{display:flex;gap:16px;flex-wrap:wrap;margin:8px 0}
  button{background:#1a1a1a;border:1px solid #2a2a2a;border-radius:8px;padding:8px 12px;color:#ddd;cursor:pointer}
  button:hover{border-color:#666}
  pre{white-space:pre-wrap;background:#0f0f0f;border:1px solid #191919;border-radius:10px;padding:10px;min-height:280px}
  .muted{opacity:.7;font-size:12px}
</style>
<header>
  <h3 style="margin:0">IG Bot Runner</h3>
  <span id="status" class="pill off">STOPPED</span>
</header>
<main>
  <form id="cfg">
    <div class="row">
      <fieldset>
        <legend>Login (clone)</legend>
        <label>Username <input name="user" placeholder="sprvte.m4" type="text"></label>
        <label>Password <input name="pass" type="password" placeholder=""></label>
        <div class="muted">Leave blank to login manually in the Chrome window (cookies persist).</div>
      </fieldset>
      <fieldset>
        <legend>Mode</legend>
        <label><input type="radio" name="mode" value="auto" checked> AUTO (profile-mined)</label>
        <label><input type="radio" name="mode" value="manual"> Manual keywords</label>
        <label>Keywords (comma) <input name="keywords" style="min-width:340px" placeholder="cars toronto, carspotting" type="text"></label>
      </fieldset>
      <fieldset>
        <legend>Limits</legend>
        <label>Per-keyword follow cap <input name="perkw" type="number" min="1" max="50" value="6"></label>
      </fieldset>
    </div>
    <div class="row">
      <button type="button" onclick="startRun()">Start</button>
      <button type="button" onclick="stopRun()">Stop</button>
      <button type="button" onclick="doUnfollow()">Unfollow Due</button>
    </div>
  </form>

  <h3>Logs</h3>
  <pre id="log"></pre>
</main>

<script>
function $(s){return document.querySelector(s)}
function statusOn(on){ const el=$("#status"); if(on){el.classList.remove("off"); el.classList.add("on"); el.textContent="RUNNING"} else {el.classList.remove("on"); el.classList.add("off"); el.textContent="STOPPED"} }
function startRun(){
  const fd = new FormData($("#cfg"))
  const body = {
    user: fd.get("user")||"", pass: fd.get("pass")||"",
    mode: fd.get("mode")||"auto",
    keywords: (fd.get("keywords")||"").split(",").map(s=>s.trim()).filter(Boolean),
    perkw: parseInt(fd.get("perkw")||"6") || 6
  }
  fetch("/start", {method:"POST", headers:{"content-type":"application/json"}, body: JSON.stringify(body)})
    .then(r=>r.json()).then(j=>{ if(j.ok){ statusOn(true) } else { alert(j.error||"failed") } });
}
function stopRun(){ fetch("/stop", {method:"POST"}).then(()=>statusOn(false)); }
function doUnfollow(){
  fetch("/unfollow_due", {method:"POST"}).then(r=>r.json()).then(j=>{ alert("UNFOLLOW → ok="+j.ok+" skip="+j.skip+" err="+j.err) })
}
let es=null;
function connect(){
  if(es){ es.close(); es=null }
  es = new EventSource("/logs")
  es.onmessage = (ev)=>{
    const pre = $("#log"); pre.textContent += ev.data + "\\n"; pre.scrollTop = pre.scrollHeight;
  }
  es.onerror = ()=>{ setTimeout(connect, 1000) }
}
connect();
</script>
"""

def emit(line: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    LOGQ.append(f"[{ts}] {line}")

@contextlib.contextmanager
def tee_prints():
    o_out, o_err = sys.stdout, sys.stderr
    class _Tee(io.TextIOBase):
        def __init__(self, base): self.base, self.buf = base, ""
        def write(self, s):
            try: self.base.write(s)
            except Exception: pass
            self.buf += s
            while "\\n" in self.buf:
                line, self.buf = self.buf.split("\\n", 1)
                if line.strip(): emit(line)
        def flush(self):
            try: self.base.flush()
            except Exception: pass
    sys.stdout, sys.stderr = _Tee(o_out), _Tee(o_err)
    try:
        yield
    finally:
        sys.stdout, sys.stderr = o_out, o_err

@app.get("/")
def home():
    return render_template_string(HTML)

@app.get("/logs")
def logs():
    def gen():
        last = 0
        while True:
            if LOGQ:
                line = LOGQ.popleft()
                yield f"data: {line}\\n\\n"
                last = time.time()
            else:
                if time.time() - last > 5:
                    yield "data: .\\n\\n"
                    last = time.time()
                time.sleep(0.2)
    return Response(gen(), mimetype="text/event-stream")

@app.post("/start")
def start():
    if STATE["running"]:
        return jsonify({"ok": False, "error": "already running"}), 400
    payload = request.get_json(force=True) or {}
    mode = (payload.get("mode") or "auto").strip().lower()
    keywords: List[str] = [str(k).strip() for k in (payload.get("keywords") or []) if str(k).strip()]
    perkw = int(payload.get("perkw") or 6)
    user = payload.get("user") or ""
    pw = payload.get("pass") or ""
    STATE["params"] = {"mode": mode, "keywords": keywords, "perkw": perkw, "user": user, "pass": pw}
    STATE["stop"].clear()

    def worker(stop_evt: threading.Event, mode: str, keywords: List[str], perkw: int):
        STATE["running"] = True
        emit("starting worker")
        emit(f"mode={mode} perkw={perkw} user={'(manual login)' if not user else user}")
        set_login_credentials(user, pw)
        with tee_prints():
            try:
                if mode == "manual":
                    if not keywords:
                        print("no keywords provided"); return
                    for kw in keywords:
                        if stop_evt.is_set():
                            print("[STOP] requested — aborting before next keyword"); break
                        print(f"[RUN] keyword='{kw}', batch_limit={perkw}")
                        search_and_follow(str(kw), batch_limit=int(perkw), stop_evt=stop_evt)
                else:
                    # AUTO mode: either user-supplied keywords or auto-mined
                    print("run_auto_campaign()")
                    if keywords:
                        run_auto_campaign(keywords=keywords, per_keyword_cap=int(perkw), stop_evt=stop_evt)
                    else:
                        run_auto_campaign(keywords=None, per_keyword_cap=int(perkw), stop_evt=stop_evt)
            except Exception as e:
                print("worker error:", repr(e))
            finally:
                set_login_credentials(None, None)
                STATE["running"] = False
                emit("worker finished")

    t = threading.Thread(target=worker, args=(STATE["stop"], mode, keywords, perkw), daemon=True)
    STATE["thread"] = t
    t.start()
    return jsonify({"ok": True})

@app.post("/stop")
def stop():
    STATE["stop"].set()
    return jsonify({"ok": True})

@app.post("/unfollow_due")
def unfollow_due_route():
    payload = request.get_json(silent=True) or {}
    batch = int(payload.get("batch", 50))
    hours = int(payload.get("hours", 72))
    with tee_prints():
        res = unfollow_due(batch_limit=batch, hours=hours)
    return jsonify(res)

if __name__ == "__main__":
    emit("webapp boot")
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
