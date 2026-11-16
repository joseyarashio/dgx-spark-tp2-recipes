#!/usr/bin/env python3
"""Offline test of scripts/cluster_watchdog.sh against a mock engine (no production traffic, DRY_RUN=1).

Each case starts a mock :health/:metrics/:chat server with a given behaviour, fakes rank1's `docker inspect`
output with a shell `echo`, runs the watchdog with DRY_RUN=1, and checks whether it decided to heal and why.
"""
import http.server, os, socketserver, subprocess, sys, tempfile, threading, time

WD = "/home/joseyarashio/dgx-spark-tp2-recipes/scripts/cluster_watchdog.sh"


class Mock(http.server.BaseHTTPRequestHandler):
    cfg = {}

    def log_message(self, format, *args):
        pass

    def _send(self, code, body=b"ok"):
        self.send_response(code); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send(self.cfg["health"])
        elif self.path == "/metrics":
            r = self.cfg["running"]
            self._send(200, f"tensorfold:requests_running {r}\ntensorfold:requests_waiting 0\n".encode())

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        Mock.cfg["probes"] += 1
        if self.cfg["chat"] == "hang":
            time.sleep(5)
            return
        self._send(200, b'{"choices":[]}')


class TS(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def case(name, health=200, running=0, chat="ok", inspect: "str | None" = "running_0_t1", prev=None, expect=None, holder=False):
    Mock.cfg = {"health": health, "running": running, "chat": chat, "probes": 0}
    srv = TS(("127.0.0.1", 0), Mock); port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    d = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
    log, state = f"{d}/wd.log", f"{d}/rank1"
    if prev is not None:
        open(state, "w").write(prev + "\n")
    env = dict(os.environ, DRY_RUN="1", LOG=log, STATE=state, PROBE_S="2",
               HEALTH_URL=f"http://127.0.0.1:{port}/health", METRICS_URL=f"http://127.0.0.1:{port}/metrics",
               CHAT_URL=f"http://127.0.0.1:{port}/v1/chat/completions",
               RANK1_INSPECT=("false" if inspect is None else f"echo {inspect}"))
    hold = subprocess.Popen(["bash", "-c", "exec -a start-dsv41.sh sleep 60"]) if holder else None
    t = time.time()
    rc = subprocess.run(["bash", WD], env=env, capture_output=True, text=True, timeout=200).returncode
    el = time.time() - t
    if hold:
        hold.kill()
    srv.shutdown()
    text = open(log).read().strip() if os.path.exists(log) else ""
    healed = "Triggering auto-heal" in text
    ok = (expect is None and not healed) or (expect is not None and healed and expect in text)
    if expect == "skip":
        ok = "already running; skip" in text and not healed
    print(f"{'PASS' if ok else 'FAIL'} {name:<34} rc={rc} {el:5.1f}s probes={Mock.cfg['probes']} log={text.splitlines()[-1][22:130] if text else '-'}")
    return ok


results = [
    case("healthy, rank1 steady, probe ok", prev="running_0_t1"),
    case("health 503 for 60 s", health=503, expect="unhealthy for 60s"),
    case("rank1 exited, rank0 health 200", inspect="exited_6_t2", prev="running_0_t1", expect="rank1 container is exited"),
    case("rank1 RestartCount grew 0 -> 3", inspect="running_3_t2", prev="running_0_t1", expect="RestartCount 0 -> 3"),
    case("first run, no state, rank1 count 6", inspect="running_6_t2", prev=None),
    case("recreated by start-dsv41 (6 -> 0)", inspect="running_0_t3", prev="running_6_t2"),
    case("idle and probe hangs twice", chat="hang", expect="no answer within 2s twice"),
    case("busy (running 3), probe would hang", running=3, chat="hang"),
    case("Node2 unreachable, health 200", inspect=None, prev="running_0_t1"),
    case("start-dsv41.sh running", health=503, holder=True, expect="skip"),
]
print(f"{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
