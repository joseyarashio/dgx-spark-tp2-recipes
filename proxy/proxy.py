import asyncio
import codecs
import hashlib
import itertools
import json
import logging
import os
import re
import sys
import time
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.background import BackgroundTask

from cold_kv import ColdKVManager, get_host_free_memory_gib

AUDIT_LOG_PATH = Path(
    os.environ.get(
        "SPARK_PROXY_AUDIT_LOG",
        str(Path.home() / ".cache" / "spark-proxy-audit" / "completions.jsonl"),
    )
)
AUDIT_LOG_MAX_BYTES = int(os.environ.get("SPARK_PROXY_AUDIT_MAX_BYTES", str(100 * 1024 * 1024)))
SHADOW_LOOP_RE = re.compile(r"(.{20,600}?)\1{4,}", re.S)
SHADOW_TAIL_WINDOW = 12000
SHADOW_CHECK_STEP = 3000
SHORT_NO_THINK_MAX_TOKENS = int(os.environ.get("SPARK_PROXY_SHORT_NO_THINK_MAX_TOKENS", "256"))
DSML_CONTENT_MARKERS = ("<｜DSML｜", "</｜DSML｜", "<tool_call>")
# Reasoning-loop fallback: thinking chat completions ask the engine for the per-request loop stop
# ("loop_guard_stop": true). When the guard fires the engine ends the reply (finish_reason=content_filter,
# error.code=reasoning_loop) instead of forcing the think block closed (which makes DeepSeek call read_file under
# long context + tools). The proxy then re-sends the same request once at LOOP_FALLBACK_EFFORT (default "none",
# thinking off) inside the same slot and splices that answer into the client's stream / reply.
LOOP_FALLBACK_ENABLED = os.environ.get("SPARK_PROXY_LOOP_FALLBACK", "1") == "1"
LOOP_FALLBACK_EFFORT = os.environ.get("SPARK_PROXY_LOOP_FALLBACK_EFFORT", "none")


def _write_audit_record(rec: Dict[str, Any]) -> None:
    try:
        AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        if AUDIT_LOG_PATH.exists() and AUDIT_LOG_PATH.stat().st_size >= AUDIT_LOG_MAX_BYTES:
            rot = AUDIT_LOG_PATH.with_suffix(".jsonl.1")
            if rot.exists():
                rot.unlink()
            AUDIT_LOG_PATH.rename(rot)
        line = json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n"
        with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def _build_audit_meta(
    request: Request,
    path: str,
    body_json: dict,
    body_bytes: bytes,
    priority: int,
    req_id: int,
    est_prompt_tokens: int,
    is_warm_cache: bool,
    orig_tool_choice: Any,
    orig_effort: Any = None,
    effort_rewritten: bool = False,
) -> Dict[str, Any]:
    msgs = body_json.get("messages") if isinstance(body_json, dict) else None
    hist_reas = 0
    if isinstance(msgs, list):
        for m in msgs:
            if isinstance(m, dict) and m.get("reasoning_content"):
                hist_reas += 1
    ctk = body_json.get("chat_template_kwargs") if isinstance(body_json, dict) else None
    enable_thinking = ctk.get("enable_thinking") if isinstance(ctk, dict) else None
    client_ip = (
        request.headers.get("x-forwarded-for")
        or (request.client.host if request.client else None)
        or "unknown"
    ).split(",")[0].strip()
    tc_repr = None
    if orig_tool_choice is not None:
        tc_repr = orig_tool_choice if isinstance(orig_tool_choice, str) else str(orig_tool_choice.get("type") or "object")[:32]
    tools = body_json.get("tools") if isinstance(body_json, dict) else None
    max_tok = None
    if isinstance(body_json, dict):
        max_tok = body_json.get("max_tokens") if body_json.get("max_tokens") is not None else body_json.get("max_completion_tokens")
    return {
        "ts": round(time.time(), 3),
        "req_id": req_id,
        "client_ip": client_ip,
        "path": path,
        "priority": priority,
        "stream": bool(body_json.get("stream")) if isinstance(body_json, dict) else False,
        "model": body_json.get("model") if isinstance(body_json, dict) else None,
        "effort": body_json.get("reasoning_effort") if isinstance(body_json, dict) else None,
        "orig_effort": orig_effort,
        "effort_rewritten": bool(effort_rewritten),
        "enable_thinking": enable_thinking,
        "thinking_budget": body_json.get("thinking_budget") if isinstance(body_json, dict) else None,
        "temperature": body_json.get("temperature") if isinstance(body_json, dict) else None,
        "max_tokens": max_tok,
        "tools_count": len(tools) if isinstance(tools, list) else 0,
        "tool_choice": tc_repr,
        "messages_count": len(msgs) if isinstance(msgs, list) else 0,
        "hist_reasoning_msgs": hist_reas,
        "body_bytes": len(body_bytes),
        "est_text_tokens": est_prompt_tokens,
        "is_warm_cache": bool(is_warm_cache),
        "free_ram_start_gib": round(get_host_free_memory_gib(), 3),
        "free_ram_end_gib": None,
        "upstream_id": None,
        "finish_reason": None,
        "prompt_tokens": None,
        "cached_tokens": None,
        "completion_tokens": None,
        "reasoning_tokens": None,
        "content_tokens": None,
        "tool_calls_out": 0,
        "dsml_in_content": False,
        "budget_hit": False,
        "valid_delivery": False,
        "loop_period": None,
        "r_chars": 0,
        "c_chars": 0,
        "shadow_loop_ch": None,
        "shadow_loop_period_chars": None,
        "shadow_loop_at_chars": None,
        "_first_tok_t": None,
        "_tc_indices": set(),
        "_r_tail": "",
        "_c_tail": "",
        "_r_next_chk": SHADOW_CHECK_STEP,
        "_c_next_chk": SHADOW_CHECK_STEP,
    }


def _check_shadow_loop(audit: Dict[str, Any], force: bool = False) -> None:
    if audit.get("shadow_loop_ch") is not None:
        return
    for ch, tail_k, cnt_k, nxt_k in (
        ("reasoning", "_r_tail", "r_chars", "_r_next_chk"),
        ("content", "_c_tail", "c_chars", "_c_next_chk"),
    ):
        cnt = audit[cnt_k]
        if (force and cnt >= 100) or (cnt >= audit[nxt_k]):
            audit[nxt_k] = cnt + SHADOW_CHECK_STEP
            m = SHADOW_LOOP_RE.search(audit[tail_k][-SHADOW_TAIL_WINDOW:])
            if m:
                audit["shadow_loop_ch"] = ch
                audit["shadow_loop_period_chars"] = len(m.group(1))
                audit["shadow_loop_at_chars"] = cnt
                return


def _finalize_audit_record(audit: Dict[str, Any], **updates: Any) -> None:
    _check_shadow_loop(audit, force=True)
    for k in [k for k in audit if k.startswith("_")]:
        audit.pop(k, None)
    audit.update(updates)
    if audit.get("free_ram_end_gib") is None:
        audit["free_ram_end_gib"] = round(get_host_free_memory_gib(), 3)
    tb = audit.get("thinking_budget")
    rtok = audit.get("reasoning_tokens")
    if isinstance(tb, int) and tb > 0 and isinstance(rtok, int):
        audit["budget_hit"] = (rtok >= tb)
    fin = audit.get("finish_reason")
    audit["valid_delivery"] = (
        audit.get("outcome") == "ok"
        and not audit.get("dsml_in_content")
        and (
            (fin == "stop" and audit.get("c_chars", 0) > 0)
            or (fin == "tool_calls" and audit.get("tool_calls_out", 0) > 0)
        )
    )
    if audit.get("dsml_in_content"):
        logger.warning(
            f"Audit: DSML marker leaked into content (req_id={audit.get('req_id')}, "
            f"finish={audit.get('finish_reason')}, effort={audit.get('effort')}, budget={tb})"
        )
    _write_audit_record(audit)


def _update_audit_from_obj(audit: Dict[str, Any], obj: Any, now_perf: float) -> None:
    if not isinstance(obj, dict):
        return
    if audit["upstream_id"] is None and isinstance(obj.get("id"), str):
        audit["upstream_id"] = obj["id"]
    tf = obj.get("tensorfold")
    if isinstance(tf, dict) and isinstance(tf.get("loop"), dict):
        audit["loop_period"] = tf["loop"].get("period")
    u = obj.get("usage")
    if isinstance(u, dict):
        if u.get("prompt_tokens") is not None:
            audit["prompt_tokens"] = u.get("prompt_tokens")
        ptd = u.get("prompt_tokens_details")
        if isinstance(ptd, dict) and ptd.get("cached_tokens") is not None:
            audit["cached_tokens"] = ptd.get("cached_tokens")
        if u.get("completion_tokens") is not None:
            audit["completion_tokens"] = u.get("completion_tokens")
        ctd = u.get("completion_tokens_details")
        if isinstance(ctd, dict) and ctd.get("reasoning_tokens") is not None:
            audit["reasoning_tokens"] = ctd.get("reasoning_tokens")
        if audit["completion_tokens"] is not None and audit["reasoning_tokens"] is not None:
            audit["content_tokens"] = max(0, audit["completion_tokens"] - audit["reasoning_tokens"])
    for ch in obj.get("choices") or []:
        if not isinstance(ch, dict):
            continue
        if ch.get("finish_reason"):
            audit["finish_reason"] = ch["finish_reason"]
        delta = ch.get("delta")
        msg = delta if isinstance(delta, dict) else (ch.get("message") if isinstance(ch.get("message"), dict) else None)
        if msg is not None:
            c_txt = msg.get("content") if isinstance(msg.get("content"), str) else ""
            r_txt = msg.get("reasoning_content") if isinstance(msg.get("reasoning_content"), str) else ""
            if not r_txt and isinstance(msg.get("reasoning"), str):
                r_txt = msg["reasoning"]
            t_txt = ch.get("text") if isinstance(ch.get("text"), str) else ""
            if c_txt:
                audit["c_chars"] += len(c_txt)
                if audit.get("shadow_loop_ch") is None or not audit.get("dsml_in_content"):
                    audit["_c_tail"] = (audit["_c_tail"] + c_txt)[-16000:]
                if not audit.get("dsml_in_content") and any(mk in audit["_c_tail"] for mk in DSML_CONTENT_MARKERS):
                    audit["dsml_in_content"] = True
            if r_txt:
                audit["r_chars"] += len(r_txt)
                if audit.get("shadow_loop_ch") is None:
                    audit["_r_tail"] = (audit["_r_tail"] + r_txt)[-16000:]
            if t_txt:
                audit["c_chars"] += len(t_txt)
                if audit.get("shadow_loop_ch") is None or not audit.get("dsml_in_content"):
                    audit["_c_tail"] = (audit["_c_tail"] + t_txt)[-16000:]
                if not audit.get("dsml_in_content") and any(mk in audit["_c_tail"] for mk in DSML_CONTENT_MARKERS):
                    audit["dsml_in_content"] = True
            if c_txt or r_txt:
                _check_shadow_loop(audit, force=False)
            has_tok = (
                len(c_txt) > 0
                or len(r_txt) > 0
                or (isinstance(msg.get("tool_calls"), list) and len(msg["tool_calls"]) > 0)
                or len(t_txt) > 0
            )
            if has_tok and audit["_first_tok_t"] is None:
                audit["_first_tok_t"] = now_perf
            tcs = msg.get("tool_calls")
            if isinstance(tcs, list) and len(tcs) > 0:
                if isinstance(delta, dict):
                    for tc in tcs:
                        if isinstance(tc, dict) and tc.get("index") is not None:
                            audit["_tc_indices"].add(tc["index"])
                    audit["tool_calls_out"] = max(audit["tool_calls_out"], len(audit["_tc_indices"]) or len(tcs))
                else:
                    audit["tool_calls_out"] = len(tcs)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("spark-fastfail-proxy")

CONFIG_PATH = Path(__file__).parent / "config.json"

# State
state: Dict[str, Any] = {
    "upstream_url": "http://127.0.0.1:8888",
    "listen_host": "0.0.0.0",
    "listen_port": 8889,
    "model_limits": {
        "dsv41": 2,
        "DeepSeek-V4.1-Flash-EXL3": 2,
        "DeepSeek-V4.1-Flash-TF": 6,
        "DeepSeek-V4.1-Flash-1017-TF": 6,
        "GLM-5.3-Flash": 4,
        "GLM-5.3-Flash-EXL3": 4,
    },
    "default_limit": 6,
    "queue_buffer": 8,
    "background_max_slots": 5,
    "tiered_timeouts": [25.0, 22.0, 19.0, 16.0, 13.0, 10.0, 7.0, 4.0],
    "extension_seconds": 5.0,
    "poll_interval_seconds": 3,
    "current_model": "unknown",
    "current_limit": 6,
    "active_running": 0,
    "bg_running": 0,
    "active_large_prefills": 0,
    "waiting_in_queue": 0,
    "upstream_healthy": False,
}

_req_id_counter = itertools.count(1)

def _sync_cluster_shm():
    try:
        active = state.get("active_running", 0)
        waiting = state.get("waiting_in_queue", 0)
        limit = state.get("current_limit", 8)
        now_ms = int(time.time() * 1000)
        content = f"{active},{waiting},{limit},{now_ms}\n"
        tmp_path = f"/dev/shm/dgx_cluster_state.{os.getpid()}_{time.time_ns()}.tmp"
        with open(tmp_path, "w") as f:
            f.write(content)
        os.replace(tmp_path, "/dev/shm/dgx_cluster_state")
    except Exception:
        pass


LARGE_PREFILL_TOKEN_THRESHOLD = 20000


class Waiter:
    def __init__(self, pos: int, priority: int = 1, prefix_key: str = "", est_tokens: int = 0):
        self.pos = pos
        self.priority = priority  # 0: interactive/foreground, 1: normal, 2: background/batch
        self.prefix_key = prefix_key
        self.est_tokens = est_tokens
        self.promoted = False
        self.extended = False
        self.deadline = 0.0
        self.enqueued_at = time.monotonic()
        self.event = asyncio.Event()


class SingleFlightEntry:
    """
    Bounded Single-Flight Prefix Coordination State.
    Tracks owner_id to prevent ABA deletion races and ensures immediate cleanup on 429/cancel/error.
    """
    def __init__(self, owner_id: int):
        self.owner_id = owner_id
        self.event = asyncio.Event()
        self.waiters = 0
        self.status = "BUILDING"  # BUILDING | READY | FAILED
        self.created_at = time.monotonic()


prefix_inflight: Dict[str, SingleFlightEntry] = {}
prefix_committed: Dict[str, float] = {}  # prefix_key -> expiry monotonic timestamp
prefix_lock = asyncio.Lock()

PREFIX_COMMITTED_TTL_SECONDS = 90.0
MAX_SINGLEFLIGHT_WAITERS = 8
SINGLEFLIGHT_WAIT_TIMEOUT = 25.0


def compute_prefix_key(body_bytes: bytes) -> str:
    """
    Extracts canonical shared prefix hash for prompts.
    Supports both text codebases (>=4000 bytes) and multi-turn vision inputs (with image hashing).
    Strips trailing 256+ characters of final message for codebases so sibling requests
    map to the exact same prefix_key; and maps multi-turn vision dialogs on the same image
    to an image-bound prefix key so Turn 2+ requests benefit from Cache-Aware Promotion.
    """
    if len(body_bytes) < 100:
        return ""
    try:
        data = json.loads(body_bytes)
        messages = data.get("messages", [])
        if not messages:
            return ""
        model_tag = str(data.get("model", ""))

        # Check for image parts across all messages
        for m in messages:
            content = m.get("content", "")
            if isinstance(content, list):
                for p in content:
                    if isinstance(p, dict) and p.get("type") == "image_url":
                        img_obj = p.get("image_url", {})
                        url_str = str(img_obj.get("url", "")) if isinstance(img_obj, dict) else str(img_obj)
                        h_img = hashlib.sha256(url_str.encode("utf-8", errors="ignore")).hexdigest()[:16]
                        return f"img:{model_tag}:{h_img}"

        # Pure text codebase handling
        if len(body_bytes) < 4000:
            return ""
        parts: List[str] = [f"model:{model_tag}"]
        total_chars = 0
        num_msgs = len(messages)
        for idx, m in enumerate(messages):
            role = str(m.get("role", ""))
            content = m.get("content", "")
            text_val = ""
            if isinstance(content, str):
                text_val = content
            elif isinstance(content, list):
                sub_parts = []
                for p in content:
                    if isinstance(p, dict) and p.get("type") == "text":
                        sub_parts.append(str(p.get("text", "")))
                text_val = "".join(sub_parts)
            # Quantize the final message to a fixed 2048-char block boundary (excluding up to 512 trailing query chars)
            # so sibling tasks with different-length trailing questions slice the exact same prefix length!
            if idx == num_msgs - 1 and len(text_val) >= 4608:
                safe_len = ((len(text_val) - 512) // 2048) * 2048
                chunk = text_val[:min(16384, safe_len)]
            else:
                chunk = text_val[:16384]
            parts.append(f"{role}:{chunk}")
            total_chars += len(chunk)
            if total_chars >= 32768:
                break
        if total_chars < 3500:
            return ""
        canonical = "\n".join(parts)[:32768]
        return hashlib.sha256(canonical.encode("utf-8", errors="ignore")).hexdigest()[:16]
    except Exception:
        return ""


async def _release_prefix(prefix_key: str, owner_id: int, committed: bool = False) -> None:
    """
    Idempotently releases Single-Flight ownership for `owner_id` with strict owner fencing.
    Only the active owner may transition the entry or record `prefix_committed`.
    """
    if not prefix_key or owner_id <= 0:
        return
    now = time.monotonic()
    async with prefix_lock:
        entry = prefix_inflight.get(prefix_key)
        if entry is not None and entry.owner_id == owner_id:
            if committed:
                prefix_committed[prefix_key] = now + PREFIX_COMMITTED_TTL_SECONDS
            entry.status = "READY" if committed else "FAILED"
            entry.event.set()
            del prefix_inflight[prefix_key]


waiting_queue: deque[Waiter] = deque()
queue_lock = asyncio.Lock()
cold_kv_mgr = ColdKVManager()
http_client: Optional[httpx.AsyncClient] = None

# Hop-by-hop headers to exclude when forwarding
EXCLUDE_HEADERS = {
    "host",
    "content-length",
    "transfer-encoding",
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "trailer",
    "upgrade",
}


def load_config() -> None:
    if not CONFIG_PATH.exists():
        return
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            state["upstream_url"] = cfg.get("upstream_url", state["upstream_url"]).rstrip("/")
            state["listen_host"] = cfg.get("listen_host", state["listen_host"])
            state["listen_port"] = int(cfg.get("listen_port", state["listen_port"]))
            state["model_limits"] = cfg.get("model_limits", state["model_limits"])
            state["default_limit"] = int(cfg.get("default_limit", state["default_limit"]))
            state["queue_buffer"] = int(cfg.get("queue_buffer", state["queue_buffer"]))
            state["background_max_slots"] = int(cfg.get("background_max_slots", state["background_max_slots"]))
            state["tiered_timeouts"] = [float(t) for t in cfg.get("tiered_timeouts", state["tiered_timeouts"])]
            state["extension_seconds"] = float(cfg.get("extension_seconds", state["extension_seconds"]))
            state["poll_interval_seconds"] = float(cfg.get("poll_interval_seconds", state["poll_interval_seconds"]))
    except Exception as e:
        logger.warning(f"Failed to reload config: {e}")


def get_timeout(pos: int, priority: int = 1) -> float:
    timeouts = state.get("tiered_timeouts", [25.0, 22.0, 19.0, 16.0, 13.0, 10.0, 7.0, 4.0])
    base_t = timeouts[pos] if pos < len(timeouts) else (timeouts[-1] if timeouts else 5.0)
    if priority == 0:
        # Adaptive P0 timeout (Astra & Opus 5.5 recommendation):
        # Allow up to 16.0s at queue head (never clamped below 14.0s) so interactive/Turn 2 requests
        # can cross the 12-15s GPU batch cycle without premature decapitation!
        return max(14.0, min(base_t, 16.0))
    # Background tasks get the full tiered timeout matrix (matching P11 baseline, up to 25.0s)
    return base_t


def resolve_limit(model_ids: list[str]) -> tuple[str, int]:
    limits = state["model_limits"]
    default_lim = state["default_limit"]

    candidates = [m for m in model_ids if m != "current"]
    if not candidates:
        candidates = model_ids

    for mid in candidates:
        if mid in limits:
            return mid, limits[mid]
        mid_lower = mid.lower()
        for k, v in limits.items():
            if k.lower() == mid_lower or k.lower() in mid_lower:
                return mid, v

    first_model = candidates[0] if candidates else "unknown"
    return first_model, default_lim


def _can_run_priority_locked(priority: int, est_tokens: int = 0) -> bool:
    """
    Checks whether a request with `priority` is eligible to take an active GPU slot.
    Enforces total concurrency limit (8 slots).
    Optimal Erlang-Pooling Safe Work Stealing (Opus 5.5 + Astra consensus):
      - Slots 1~6: Standard pool for all priorities (P0, P1, P2).
      - Slot 7: Borrowable by P2 if no RUNNABLE urgent waiter is in queue (prevents prefill deadlock).
      - Slot 8: Absolute Sacred Reservation for P0/P1. P2 NEVER allowed into Slot 8.
    Dynamic Prefill Admission Barrier (aligned with 3.05 GiB steady-state watermark):
      - Memory ladder: >= 3.05 GiB -> allow 3 large prefills; >= 2.65 GiB -> allow 2; < 2.65 GiB -> allow 1.
      - P0 is exempt from prefill barrier if free RAM >= 2.65 GiB to protect interactive SLA.
    """
    limit = state["current_limit"]
    active = state["active_running"]
    bg_active = state["bg_running"]

    if active >= limit:
        return False

    if priority >= 2:
        # Total cluster limit is 8. Slot 8 is sacred for P0/P1.
        # P2 is allowed up to 7 slots total (Slots 1-6 standard, Slot 7 borrowable).
        if active >= 7:
            return False

        # Safe Work Stealing on Slot 7 (active == 6):
        # P2 can borrow Slot 7 if and only if NO runnable urgent waiter (P0/P1) is waiting in queue.
        if active == 6:
            has_runnable_urgent = any(
                w.priority < 2 and _can_run_priority_locked(w.priority, w.est_tokens)
                for w in waiting_queue
            )
            if has_runnable_urgent:
                return False

        # Enforce ceiling on total background concurrency (up to 7)
        bg_max = state.get("background_max_slots", 7)
        if bg_active >= bg_max:
            return False

    # Dynamic Prefill Admission Barrier (aligned with 3.05 GiB steady-state watermark)
    # Threshold at 20,000 tokens prevents 12K code prompts from being blocked
    if est_tokens > LARGE_PREFILL_TOKEN_THRESHOLD:
        free_ram = get_host_free_memory_gib()
        # Memory ladder: >= 3.05 GiB permits 3 large prefills; >= 2.65 GiB permits 2; < 2.65 GiB permits 1
        max_large = 3 if free_ram >= 3.05 else (2 if free_ram >= 2.65 else 1)
        if priority > 0:
            if free_ram < 2.65 or state.get("active_large_prefills", 0) >= max_large:
                return False
        else:
            if free_ram < 2.65:
                return False

    return True


def _compute_waiter_score(priority: int, prefix_key: str, enqueued_at: float, now_mono: float) -> Tuple[int, int, float]:
    """
    Unified scheduling score used by both Direct Path and `_wake_next_locked`:
      1. Hard Anti-Starvation Ceiling: Any request waiting >= 15s gets elevated to top priority 0
         and `is_cold = 0` to prevent Head-of-Line inversion from newer short tasks.
      2. Cache-Aware Priority Elevation (Astra recommendation):
         Requests matching a warm committed prefix in engine RAM get a 1-tier priority bonus
         to ensure they are dispatched before the LRU cache window expires.
      3. Effective priority: P2 ages to priority 1 after 8s (P0=0 always stays strictly highest).
      4. Monotonic enqueue timestamp (FIFO).
    """
    wait_s = max(0.0, now_mono - enqueued_at)
    if wait_s >= 15.0:
        # Anti-Starvation Ceiling reached: elevate to highest rank
        return (0, 0, enqueued_at)

    is_warm = 0 if (prefix_key and prefix_committed.get(prefix_key, 0.0) > now_mono) else 1
    eff_prio = priority
    # Warm cache promotion: promote by one priority tier to service within LRU cache lifetime
    if is_warm == 0 and eff_prio > 0:
        eff_prio -= 1

    eff_prio = max(1, eff_prio - int(wait_s // 8.0)) if eff_prio >= 2 else eff_prio
    return (eff_prio, is_warm, enqueued_at)


def _wake_next_locked():
    """
    Promote eligible waiting requests using unified `_compute_waiter_score`.
    """
    limit = state["current_limit"]
    promoted_any = False
    now_mono = time.monotonic()
    while state["active_running"] < limit and len(waiting_queue) > 0:
        best_idx = -1
        best_score = (999, 999, float("inf"))
        for i, w in enumerate(waiting_queue):
            if not _can_run_priority_locked(w.priority, w.est_tokens):
                continue
            score = _compute_waiter_score(w.priority, w.prefix_key, w.enqueued_at, now_mono)
            if score < best_score:
                best_score = score
                best_idx = i

        if best_idx < 0:
            break

        promoted_waiter = waiting_queue[best_idx]
        del waiting_queue[best_idx]

        promoted_waiter.promoted = True
        state["active_running"] += 1
        if promoted_waiter.priority >= 2:
            state["bg_running"] += 1
        if promoted_waiter.est_tokens > LARGE_PREFILL_TOKEN_THRESHOLD:
            state["active_large_prefills"] = state.get("active_large_prefills", 0) + 1
        promoted_waiter.event.set()
        promoted_any = True

    if promoted_any:
        for i, w in enumerate(waiting_queue):
            if w.pos != i:
                w.pos = i
                w.extended = False  # fresh tier gets fresh extension rights
                w.event.set()
    state["waiting_in_queue"] = len(waiting_queue)
    _sync_cluster_shm()


async def monitor_upstream_model():
    """Background task to poll upstream /v1/models and detect active model & limits."""
    while True:
        try:
            load_config()
            url = f"{state['upstream_url']}/v1/models"
            if http_client is not None:
                resp = await http_client.get(url, timeout=4.0)
            else:
                async with httpx.AsyncClient(timeout=4.0) as client:
                    resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                model_list = [item["id"] for item in data.get("data", []) if "id" in item]
                matched_model, limit = resolve_limit(model_list)
                old_model = state["current_model"]
                old_limit = state["current_limit"]

                state["current_model"] = matched_model
                state["current_limit"] = limit
                state["background_max_slots"] = 7
                state["upstream_healthy"] = True

                if old_model != matched_model or old_limit != limit:
                    logger.info(
                        f"Detected upstream model: '{matched_model}' -> Concurrency limit set to {limit} "
                        f"(was: {old_model} with limit {old_limit}, bg_max={state['background_max_slots']})"
                    )
                    async with queue_lock:
                        _wake_next_locked()
            else:
                state["upstream_healthy"] = False
        except Exception:
            state["upstream_healthy"] = False

        await asyncio.sleep(state["poll_interval_seconds"])


async def acquire_slot(priority: int = 1, prefix_key: str = "", req_id: int = 0, est_tokens: int = 0) -> Tuple[bool, str]:
    """
    Acquire an execution slot with Tiered Dynamic Queue Management, Priority Scheduling, Anti-Herd Extension,
    and Leak-Free Strata Single-Flight Prefix Coordination.
    priority: 0 = high/foreground, 1 = normal, 2 = background/batch.
    """
    leader_entry: Optional[SingleFlightEntry] = None
    registered_as_leader = False

    if prefix_key:
        now_mono = time.monotonic()
        async with prefix_lock:
            # Prune expired committed prefixes and stale inflight entries
            expired_c = [k for k, exp in prefix_committed.items() if exp <= now_mono]
            for k in expired_c:
                del prefix_committed[k]
            stale_if = [k for k, ent in prefix_inflight.items() if (now_mono - ent.created_at) > 45.0]
            for k in stale_if:
                ent = prefix_inflight.pop(k)
                ent.status = "FAILED"
                ent.event.set()

            if prefix_key in prefix_committed:
                # Prefix is already warm in engine RAM cache! Skip Single-Flight serialization.
                pass
            elif prefix_key in prefix_inflight:
                ent = prefix_inflight[prefix_key]
                if ent.waiters < MAX_SINGLEFLIGHT_WAITERS:
                    ent.waiters += 1
                    leader_entry = ent
            else:
                prefix_inflight[prefix_key] = SingleFlightEntry(owner_id=req_id)
                registered_as_leader = True

    if leader_entry is not None:
        logger.info(f"Single-Flight Delay-Hit Mitigation: Waiting for leader prefill [prefix: {prefix_key}]...")
        # For Priority 0 interactive requests, wait at most 3.0s on leader
        sf_timeout = min(SINGLEFLIGHT_WAIT_TIMEOUT, 3.0 if priority == 0 else 8.0)
        try:
            await asyncio.wait_for(leader_entry.event.wait(), timeout=sf_timeout)
            logger.info(
                f"Single-Flight Leader finished (status={leader_entry.status}): "
                f"Follower proceeding [prefix: {prefix_key}]"
            )
        except asyncio.TimeoutError:
            logger.warning(f"Single-Flight Leader wait timed out for prefix {prefix_key}, falling back to normal acquire.")
        finally:
            async with prefix_lock:
                leader_entry.waiters = max(0, leader_entry.waiters - 1)

    slot_acquired = False
    try:
        async with queue_lock:
            limit = state["current_limit"]
            queue_max = state["queue_buffer"]
            bg_max = state.get("background_max_slots", 5)

            # Background queue buffer partition:
            # Low-priority background tasks (prio >= 2) cannot consume more than queue_max - 1 spots!
            # Always preserve at least 1 queue spot for interactive P0 / normal P1!
            if priority >= 2 and len(waiting_queue) >= max(1, queue_max - 1):
                return False, "bg_queue_capacity_reached"

            # 1. Direct GPU execution if eligible and nobody waiting ahead with better unified score
            if _can_run_priority_locked(priority, est_tokens):
                now_m = time.monotonic()
                incoming_score = _compute_waiter_score(priority, prefix_key, now_m, now_m)
                has_better_waiting = any(
                    _can_run_priority_locked(w.priority, w.est_tokens)
                    and _compute_waiter_score(w.priority, w.prefix_key, w.enqueued_at, now_m) <= incoming_score
                    for w in waiting_queue
                )
                if not has_better_waiting:
                    state["active_running"] += 1
                    if priority >= 2:
                        state["bg_running"] += 1
                    if est_tokens > LARGE_PREFILL_TOKEN_THRESHOLD:
                        state["active_large_prefills"] = state.get("active_large_prefills", 0) + 1
                    slot_acquired = True
                    _sync_cluster_shm()
                    logger.info(
                        f"Direct GPU execution [running: {state['active_running']}/{limit}, bg: {state['bg_running']}/{bg_max}, prio: {priority}, est_tok: {est_tokens}] "
                        f"(model: {state['current_model']})"
                    )
                    return True, "direct"

            # 2. Check if queue is already full -> immediate fast-fail
            if len(waiting_queue) >= queue_max:
                return False, "queue_full"

            # 3. Enter tiered queue with priority
            pos = len(waiting_queue)
            waiter = Waiter(pos, priority=priority, prefix_key=prefix_key, est_tokens=est_tokens)
            waiting_queue.append(waiter)
            state["waiting_in_queue"] = len(waiting_queue)
            _sync_cluster_shm()
            initial_timeout = get_timeout(pos, priority)
            waiter.deadline = asyncio.get_event_loop().time() + initial_timeout
            logger.info(
                f"Entered standby queue at position {pos+1}/{queue_max} (prio={priority}, initial timeout={initial_timeout:.1f}s)"
            )

        # Wait outside lock
        try:
            cur_timeout = initial_timeout
            while True:
                cur_pos = waiter.pos
                waiter.deadline = asyncio.get_event_loop().time() + cur_timeout
                try:
                    await asyncio.wait_for(waiter.event.wait(), timeout=cur_timeout)
                except asyncio.TimeoutError:
                    async with queue_lock:
                        if waiter.promoted:
                            slot_acquired = True
                            return True, "promoted"

                        # Anti-Herd Extension Check (restored to 5.0s P11 baseline)
                        can_extend = False
                        if not waiter.extended:
                            now = asyncio.get_event_loop().time()
                            ext_threshold = state.get("extension_seconds", 5.0)
                            for w in waiting_queue:
                                if w.pos < waiter.pos:
                                    rem = w.deadline - now
                                    if rem <= ext_threshold:
                                        can_extend = True
                                        break

                        if can_extend:
                            waiter.extended = True
                            # Grant extra breathing room (+8.0s) for heavy root prompts (>12K) to prevent decapitation
                            cur_timeout = 8.0 if (waiter.est_tokens > 12000 and waiter.pos <= 2) else state.get("extension_seconds", 5.0)
                            waiter.deadline = asyncio.get_event_loop().time() + cur_timeout
                            logger.info(
                                f"Anti-herd extension: Waiter at pos {waiter.pos+1} (prio={priority}, est={waiter.est_tokens}) EXTENDED by {cur_timeout:.1f}s "
                                "(waiter ahead is about to exit/promote)"
                            )
                            continue

                        # Cannot extend or already extended once -> Dropout to 429
                        if waiter in waiting_queue:
                            idx = waiting_queue.index(waiter)
                            del waiting_queue[idx]
                            for i in range(idx, len(waiting_queue)):
                                w = waiting_queue[i]
                                if w.pos != i:
                                    w.pos = i
                                    w.extended = False
                                    w.event.set()
                            state["waiting_in_queue"] = len(waiting_queue)
                    logger.warning(
                        f"Tiered queue timeout at position {cur_pos+1} (extended={waiter.extended}) -> fast-fail 429"
                    )
                    return False, f"tiered_timeout_pos_{cur_pos+1}"

                # Waiter was signaled
                if waiter.promoted:
                    slot_acquired = True
                    logger.info(
                        f"Promoted to GPU execution [running: {state['active_running']}/{state['current_limit']}, bg: {state['bg_running']}/{state['background_max_slots']}]"
                    )
                    return True, "promoted"

                # Position advanced! Reset event, clear extension flag for new tier, and loop
                waiter.event.clear()
                waiter.extended = False
                cur_timeout = get_timeout(waiter.pos, waiter.priority)
                logger.info(
                    f"Queue position advanced to {waiter.pos+1}/{state['queue_buffer']}! Timeout reset to {cur_timeout}s"
                )

        except asyncio.CancelledError:
            async with queue_lock:
                if waiter.promoted:
                    state["active_running"] = max(0, state["active_running"] - 1)
                    if priority >= 2:
                        state["bg_running"] = max(0, state["bg_running"] - 1)
                    _wake_next_locked()
                elif waiter in waiting_queue:
                    idx = waiting_queue.index(waiter)
                    del waiting_queue[idx]
                    for i in range(idx, len(waiting_queue)):
                        w = waiting_queue[i]
                        if w.pos != i:
                            w.pos = i
                            w.extended = False
                            w.event.set()
                    state["waiting_in_queue"] = len(waiting_queue)
            raise
    finally:
        # CRITICAL FIX (P0-1): If Leader failed to acquire a slot (429 or CancelledError),
        # immediately release `prefix_inflight` so followers never hang for 30s on a dead leader!
        if registered_as_leader and not slot_acquired:
            await _release_prefix(prefix_key, req_id, committed=False)


async def release_slot(priority: int = 1, est_tokens: int = 0):
    async with queue_lock:
        state["active_running"] = max(0, state["active_running"] - 1)
        if priority >= 2:
            state["bg_running"] = max(0, state["bg_running"] - 1)
        if est_tokens > LARGE_PREFILL_TOKEN_THRESHOLD:
            state["active_large_prefills"] = max(0, state.get("active_large_prefills", 1) - 1)
        _wake_next_locked()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    load_config()
    limits = httpx.Limits(max_keepalive_connections=100, max_connections=200)
    http_client = httpx.AsyncClient(limits=limits, timeout=httpx.Timeout(600.0, connect=10.0))
    monitor_task = asyncio.create_task(monitor_upstream_model())

    async def cold_kv_sweep_loop():
        while True:
            try:
                await asyncio.sleep(60.0)
                await cold_kv_mgr.run_maintenance_sweep()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Error in cold KV maintenance loop: {e}")

    sweep_task = asyncio.create_task(cold_kv_sweep_loop())
    logger.info(
        f"Starting proxy with upstream: {state['upstream_url']} "
        f"(limit={state['current_limit']}, bg_max={state['background_max_slots']}, "
        f"queue_buffer={state['queue_buffer']}, tiered_timeouts={state['tiered_timeouts']}, "
        f"anti_herd_extension={state['extension_seconds']}s, cold_kv=enabled)"
    )
    yield
    sweep_task.cancel()
    monitor_task.cancel()
    if http_client:
        await http_client.aclose()


app = FastAPI(title="Spark Fast-Fail Concurrency Proxy with Anti-Herd Dynamic Queue", lifespan=lifespan)


@app.get("/proxy/status")
async def get_proxy_status():
    now_mono = time.monotonic()
    async with queue_lock:
        running = state["active_running"]
        bg_running = state["bg_running"]
        waiting = len(waiting_queue)
        positions = [w.pos + 1 for w in waiting_queue]
        extended_flags = [w.extended for w in waiting_queue]
    async with prefix_lock:
        inflight_count = len(prefix_inflight)
        committed_count = sum(1 for exp in prefix_committed.values() if exp > now_mono)
    return {
        "status": "ok",
        "upstream_healthy": state["upstream_healthy"],
        "upstream_url": state["upstream_url"],
        "current_model": state["current_model"],
        "concurrency_limit": state["current_limit"],
        "background_max_slots": state["background_max_slots"],
        "queue_buffer": state["queue_buffer"],
        "tiered_timeouts": state["tiered_timeouts"],
        "extension_seconds": state["extension_seconds"],
        "active_running": running,
        "bg_running": bg_running,
        "waiting_in_queue": waiting,
        "queue_positions": positions,
        "queue_extended": extended_flags,
        "singleflight_inflight": inflight_count,
        "singleflight_committed": committed_count,
        "model_limits_config": state["model_limits"],
        "default_limit": state["default_limit"],
        "cold_kv": cold_kv_mgr.get_stats(),
    }


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def proxy_all(request: Request, path: str):
    req_start_t = time.perf_counter()
    is_completion = path.strip("/").endswith("chat/completions") or path.strip("/").endswith("completions")

    if is_completion and request.method == "POST":
        req_id = next(_req_id_counter)
        body_bytes = await request.body()
        body_json: dict = {}
        orig_tool_choice = None
        orig_effort = None
        effort_rewritten = False
        loop_fallback_bytes: Optional[bytes] = None
        # Request interceptors:
        # 1. DSML Interceptor: rewrite non-standard tool_choice to "auto" for DeepSeek-V4.1
        # 2. Short No-Think Stop-Loss: short tool-less requests (max_tokens <= 256) burn budget in <think> -> set effort="none"
        try:
            body_json = json.loads(body_bytes)
            if isinstance(body_json, dict):
                body_modified = False
                orig_tool_choice = body_json.get("tool_choice")
                tc = orig_tool_choice
                if tc is not None and tc != "auto" and tc != "none":
                    logger.info(f"DSML Interceptor: rewriting tool_choice={tc} to 'auto' for DeepSeek compatibility")
                    body_json["tool_choice"] = "auto"
                    body_modified = True

                orig_effort = body_json.get("reasoning_effort")
                tools_val = body_json.get("tools")
                has_tools = isinstance(tools_val, list) and len(tools_val) > 0
                max_tok_val = body_json.get("max_tokens") if body_json.get("max_tokens") is not None else body_json.get("max_completion_tokens")
                ctk_val = body_json.get("chat_template_kwargs")
                enable_thinking_explicit = ctk_val.get("enable_thinking") if isinstance(ctk_val, dict) else None
                if (
                    SHORT_NO_THINK_MAX_TOKENS > 0
                    and not has_tools
                    and isinstance(max_tok_val, int)
                    and not isinstance(max_tok_val, bool)
                    and 0 < max_tok_val <= SHORT_NO_THINK_MAX_TOKENS
                    and orig_effort != "none"
                    and enable_thinking_explicit is not True
                ):
                    logger.info(
                        f"Short No-Think Stop-Loss: rewriting reasoning_effort={orig_effort!r} to 'none' "
                        f"(max_tokens={max_tok_val}, tools=0)"
                    )
                    body_json["reasoning_effort"] = "none"
                    effort_rewritten = True
                    body_modified = True

                thinking_off = body_json.get("reasoning_effort") == "none" or enable_thinking_explicit is False
                if (
                    LOOP_FALLBACK_ENABLED
                    and path.strip("/").endswith("chat/completions")
                    and not thinking_off
                    and "loop_guard_stop" not in body_json
                    and isinstance(body_json.get("messages"), list)
                ):
                    fb = {k: v for k, v in body_json.items() if k not in ("thinking_budget",)}
                    fb["reasoning_effort"] = LOOP_FALLBACK_EFFORT
                    if LOOP_FALLBACK_EFFORT == "none":
                        ctk_fb = dict(ctk_val) if isinstance(ctk_val, dict) else {}
                        ctk_fb["enable_thinking"] = False
                        fb["chat_template_kwargs"] = ctk_fb
                    loop_fallback_bytes = json.dumps(fb, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                    body_json["loop_guard_stop"] = True
                    body_modified = True

                if body_modified:
                    body_bytes = json.dumps(body_json, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        except Exception:
            pass
        prefix_key = compute_prefix_key(body_bytes)
        if prefix_key:
            await cold_kv_mgr.touch_session(prefix_key)

        # Extract Priority Header: 0 = high/foreground, 1 = normal, 2 = background/batch
        prio_hdr = request.headers.get("x-priority") or request.headers.get("priority")
        priority = 1
        if prio_hdr:
            prio_lower = prio_hdr.lower()
            if prio_lower in ["high", "foreground", "interactive", "0"]:
                priority = 0
            elif prio_lower in ["low", "background", "batch", "2"]:
                priority = 2

        # Accurate token estimation: compute token length on pure text content, excluding base64 image strings
        est_prompt_tokens = 0
        try:
            if isinstance(body_json.get("messages"), list):
                text_bytes_len = 0
                for m in body_json["messages"]:
                    content = m.get("content")
                    if isinstance(content, str):
                        text_bytes_len += len(content)
                    elif isinstance(content, list):
                        for part in content:
                            if isinstance(part, dict) and part.get("type") == "text":
                                text_bytes_len += len(part.get("text", ""))
                est_prompt_tokens = text_bytes_len // 4 if text_bytes_len > 1024 else 0
            else:
                est_prompt_tokens = len(body_bytes) // 4 if len(body_bytes) > 1024 else 0
        except Exception:
            est_prompt_tokens = len(body_bytes) // 4 if len(body_bytes) > 1024 else 0

        # Cache-Aware barrier exemption (Astra / Opus 5.5 recommendation):
        # If prefix is already warm and committed in RAM, cold prefill workspace is tiny (<512 tokens)
        now_mono = time.monotonic()
        is_warm_cache = prefix_key and (prefix_committed.get(prefix_key, 0.0) > now_mono)
        barrier_est_tokens = 512 if is_warm_cache else est_prompt_tokens
        audit_meta = _build_audit_meta(
            request=request,
            path=path,
            body_json=body_json,
            body_bytes=body_bytes,
            priority=priority,
            req_id=req_id,
            est_prompt_tokens=est_prompt_tokens,
            is_warm_cache=bool(is_warm_cache),
            orig_tool_choice=orig_tool_choice,
            orig_effort=orig_effort,
            effort_rewritten=effort_rewritten,
        )

        acquired, reason = await acquire_slot(priority=priority, prefix_key=prefix_key, req_id=req_id, est_tokens=barrier_est_tokens)
        if not acquired:
            curr_model = state["current_model"]
            limit = state["current_limit"]
            async with queue_lock:
                running = state["active_running"]
                waiting = len(waiting_queue)
            logger.warning(
                f"Fast-Fail 429 triggered: model '{curr_model}' (reason: {reason}, prio: {priority}, running: {running}/{limit}, queue: {waiting}/{state['queue_buffer']})"
            )
            _finalize_audit_record(audit_meta, status=429, outcome="proxy_429", reject_reason=reason, wall_s=round(time.perf_counter() - req_start_t, 3))
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": "1"},
                content={
                    "error": {
                        "message": (
                            f"DGX Spark concurrency limit reached for '{curr_model}' "
                            f"(running: {running}/{limit}, tiered queue: {waiting}/{state['queue_buffer']}, reason: {reason}, prio: {priority}). "
                            "Fast-failing for client fallback."
                        ),
                        "type": "server_busy",
                        "code": 429,
                        "param": None,
                    }
                },
            )

        try:
            return await handle_forward(
                request,
                path,
                release_on_close=True,
                cached_body=body_bytes,
                prefix_key=prefix_key,
                priority=priority,
                req_id=req_id,
                req_start_t=req_start_t,
                est_tokens=barrier_est_tokens,
                audit_meta=audit_meta,
                loop_fallback_bytes=loop_fallback_bytes,
            )
        except BaseException as exc:
            await release_slot(priority=priority, est_tokens=barrier_est_tokens)
            await _release_prefix(prefix_key, req_id, committed=False)
            _finalize_audit_record(audit_meta, status=499 if isinstance(exc, asyncio.CancelledError) else 500, outcome="client_left_pre_send" if isinstance(exc, asyncio.CancelledError) else "proxy_error", wall_s=round(time.perf_counter() - req_start_t, 3))
            raise
    else:
        return await handle_forward(request, path, release_on_close=False)


async def handle_forward(
    request: Request,
    path: str,
    release_on_close: bool = False,
    cached_body: Optional[bytes] = None,
    prefix_key: str = "",
    priority: int = 1,
    req_id: int = 0,
    req_start_t: float = 0.0,
    est_tokens: int = 0,
    audit_meta: Optional[Dict[str, Any]] = None,
    loop_fallback_bytes: Optional[bytes] = None,
):
    upstream_url = f"{state['upstream_url']}/{path}"
    query = request.url.query
    if query:
        upstream_url = f"{upstream_url}?{query}"

    # Ensure Connection: keep-alive is maintained and hop-by-hop headers stripped
    req_headers = {k: v for k, v in request.headers.items() if k.lower() not in EXCLUDE_HEADERS}
    req_headers["connection"] = "keep-alive"
    body = cached_body if cached_body is not None else await request.body()

    # Context volume estimation & advisory
    est_prompt_tokens = 0
    if len(body) > 1024:
        est_prompt_tokens = len(body) // 3
        if est_prompt_tokens > 250000:
            logger.warning(
                f"Large context payload detected: ~{est_prompt_tokens} tokens ({len(body)/1024/1024:.2f} MB). Upstream cold prefill may require extended TTFT."
            )

    try:
        upstream_req = http_client.build_request(
            method=request.method,
            url=upstream_url,
            headers=req_headers,
            content=body,
        )
        upstream_resp = await http_client.send(upstream_req, stream=True)
    except BaseException as e:
        if release_on_close:
            await release_slot(priority=priority)
        await _release_prefix(prefix_key, req_id, committed=False)
        if isinstance(e, asyncio.CancelledError):
            if audit_meta is not None:
                _finalize_audit_record(audit_meta, status=499, outcome="client_left_connect", wall_s=round(time.perf_counter() - req_start_t, 3) if req_start_t > 0 else None)
            raise
        logger.error(f"Failed to connect to upstream {upstream_url}: {e}")
        if audit_meta is not None:
            _finalize_audit_record(audit_meta, status=502, outcome="upstream_502", error=str(e)[:200], wall_s=round(time.perf_counter() - req_start_t, 3) if req_start_t > 0 else None)
        return JSONResponse(
            status_code=502,
            content={"error": {"message": f"Bad Gateway to Spark backend: {e}", "type": "bad_gateway", "code": 502}},
        )

    # If upstream returned an HTTP error (>= 400), release prefix immediately without marking committed
    if upstream_resp.status_code >= 400 and prefix_key:
        await _release_prefix(prefix_key, req_id, committed=False)

    resp_headers = {
        k: v for k, v in upstream_resp.headers.items() if k.lower() not in EXCLUDE_HEADERS
    }
    if est_prompt_tokens > 0:
        resp_headers["x-spark-estimated-tokens"] = str(est_prompt_tokens)
        if est_prompt_tokens > 250000:
            resp_headers["x-spark-compaction-advisory"] = "prompt_exceeds_250k_compaction_recommended"
    if req_start_t > 0.0:
        resp_headers["x-spark-ttfe-seconds"] = f"{time.perf_counter() - req_start_t:.4f}"

    released = False
    prefix_notified = False
    prefill_notified = False
    resp_closed = False
    audit_written = False
    stream_eof = False
    stream_err: Optional[str] = None
    audit_sse_rem = ""
    audit_json_buf = bytearray()

    async def cleanup_all():
        nonlocal released, prefix_notified, prefill_notified, resp_closed, audit_written
        if not released and release_on_close:
            released = True
            if est_tokens > LARGE_PREFILL_TOKEN_THRESHOLD and not prefill_notified:
                prefill_notified = True
                async with queue_lock:
                    state["active_large_prefills"] = max(0, state.get("active_large_prefills", 1) - 1)
            await release_slot(priority=priority, est_tokens=est_tokens)
        if prefix_key and not prefix_notified:
            prefix_notified = True
            await _release_prefix(prefix_key, req_id, committed=False)
        if not resp_closed:
            resp_closed = True
            try:
                await upstream_resp.aclose()
            except Exception:
                pass
        if audit_meta is not None and not audit_written:
            audit_written = True
            try:
                now_p = time.perf_counter()
                if not audit_meta["stream"] and audit_json_buf:
                    _update_audit_from_obj(audit_meta, json.loads(audit_json_buf.decode("utf-8", errors="ignore")), now_p)
                elif audit_meta["stream"] and audit_sse_rem.strip():
                    for line in audit_sse_rem.splitlines():
                        s = line.strip()
                        if s.startswith("data:"):
                            s = s[5:].strip()
                        if s.startswith("{"):
                            _update_audit_from_obj(audit_meta, json.loads(s), now_p)
            except Exception:
                pass
            first_tok_t = audit_meta.get("_first_tok_t")
            if upstream_resp.status_code >= 400:
                outcome = "upstream_error"
            elif stream_err is not None:
                outcome = "stream_error"
            elif stream_eof:
                outcome = "ok"
            else:
                outcome = "client_left"
            extra = {
                "status": upstream_resp.status_code,
                "outcome": outcome,
                "ttft_s": round(first_tok_t - req_start_t, 4) if (first_tok_t is not None and req_start_t > 0) else None,
                "wall_s": round(time.perf_counter() - req_start_t, 4) if req_start_t > 0 else None,
            }
            if stream_err is not None:
                extra["error"] = stream_err
            _finalize_audit_record(audit_meta, **extra)

    def _chunk_has_generated_token(raw_text: str) -> bool:
        for line in raw_text.splitlines():
            s = line.strip()
            if not s:
                continue
            if s.startswith("data:"):
                s = s[5:].strip()
                if s == "[DONE]":
                    continue
            if not s.startswith("{"):
                continue
            try:
                obj = json.loads(s)
                if obj.get("object") == "chat.completion":
                    return True
                for ch in obj.get("choices") or []:
                    delta = ch.get("delta") or {}
                    if (
                        (isinstance(delta.get("content"), str) and len(delta["content"]) > 0)
                        or (isinstance(delta.get("reasoning_content"), str) and len(delta["reasoning_content"]) > 0)
                        or (isinstance(delta.get("tool_calls"), list) and len(delta["tool_calls"]) > 0)
                        or (isinstance(ch.get("text"), str) and len(ch["text"]) > 0)
                    ):
                        return True
            except Exception:
                pass
        return False

    def _sse_obj(ev: str) -> Any:
        for line in ev.splitlines():
            t = line.strip()
            if t.startswith("data:"):
                t = t[5:].strip()
                if t.startswith("{"):
                    try:
                        return json.loads(t)
                    except Exception:
                        return None
        return None

    def _is_loop_stop(obj: Any) -> bool:
        if not isinstance(obj, dict):
            return False
        err = obj.get("error")
        if isinstance(err, dict) and err.get("code") == "reasoning_loop":
            return True
        for ch in obj.get("choices") or []:
            if isinstance(ch, dict) and ch.get("finish_reason") == "content_filter":
                return True
        return False

    def _audit_feed(chunk: bytes) -> None:
        nonlocal audit_sse_rem
        if audit_meta is None:
            return
        try:
            if not audit_meta["stream"]:
                if len(audit_json_buf) + len(chunk) <= 2 * 1024 * 1024:
                    audit_json_buf.extend(chunk)
            else:
                audit_sse_rem += chunk.decode("utf-8", errors="ignore")
                if "\n" in audit_sse_rem:
                    idx = audit_sse_rem.rfind("\n")
                    ready = audit_sse_rem[:idx]
                    audit_sse_rem = audit_sse_rem[idx + 1 :]
                    if len(audit_sse_rem) > 262144:
                        audit_sse_rem = ""
                    now_p = time.perf_counter()
                    for line in ready.splitlines():
                        t = line.strip()
                        if not t:
                            continue
                        if t.startswith("data:"):
                            t = t[5:].strip()
                        if not t.startswith("{"):
                            continue
                        _update_audit_from_obj(audit_meta, json.loads(t), now_p)
                elif len(audit_sse_rem) > 262144:
                    audit_sse_rem = ""
        except Exception:
            pass

    async def _run_loop_fallback():
        """Re-send the request at LOOP_FALLBACK_EFFORT; yields its raw body chunks. Raises on a non-200 answer."""
        fb_req = http_client.build_request(method=request.method, url=upstream_url, headers=req_headers, content=loop_fallback_bytes)
        fb_resp = await http_client.send(fb_req, stream=True)
        try:
            if fb_resp.status_code != 200:
                raise RuntimeError(f"loop fallback upstream status {fb_resp.status_code}")
            async for c in fb_resp.aiter_bytes():
                yield c
        finally:
            await fb_resp.aclose()

    gate = loop_fallback_bytes is not None and upstream_resp.status_code == 200

    async def stream_body():
        nonlocal prefix_notified, prefill_notified, stream_eof, stream_err, audit_sse_rem
        sse_rem = ""
        dec = codecs.getincrementaldecoder("utf-8")(errors="replace")
        ev_buf = ""
        held: List[str] = []
        whole = bytearray()
        try:
            async for chunk in upstream_resp.aiter_bytes():
                # Notify single-flight waiters ONLY after prefill completes and first non-empty generated token arrives
                if prefix_key and not prefix_notified and upstream_resp.status_code == 200:
                    sse_rem += chunk.decode("utf-8", errors="ignore")
                    if "\n" in sse_rem or sse_rem.strip().endswith("}"):
                        lines = sse_rem.splitlines(keepends=True)
                        complete_part = "".join(lines[:-1]) if not lines[-1].endswith("\n") else sse_rem
                        sse_rem = lines[-1] if not lines[-1].endswith("\n") else ""
                        check_str = complete_part or sse_rem
                        if _chunk_has_generated_token(check_str):
                            prefix_notified = True
                            sse_rem = ""
                            await _release_prefix(prefix_key, req_id, committed=True)
                            if est_tokens > LARGE_PREFILL_TOKEN_THRESHOLD and not prefill_notified:
                                prefill_notified = True
                                async with queue_lock:
                                    state["active_large_prefills"] = max(0, state.get("active_large_prefills", 1) - 1)
                                    _wake_next_locked()
                if upstream_resp.status_code == 200:
                    _audit_feed(chunk)
                if not gate:
                    yield chunk
                elif audit_meta is not None and not audit_meta["stream"]:
                    whole.extend(chunk)  # a whole reply: judged once it is complete
                else:
                    # SSE: pass whole events through until the engine's loop stop, then hold the rest
                    ev_buf += dec.decode(chunk)
                    while "\n\n" in ev_buf:
                        ev, ev_buf = ev_buf.split("\n\n", 1)
                        ev += "\n\n"
                        if not held and _is_loop_stop(_sse_obj(ev)):
                            held.append(ev)
                        elif held:
                            held.append(ev)
                        else:
                            yield ev.encode("utf-8")
            stream_eof = True
            if gate:
                tail = ev_buf + dec.decode(b"", final=True)
                looped = bool(held)
                if whole:
                    try:
                        looped = _is_loop_stop(json.loads(bytes(whole)))
                    except Exception:
                        looped = False
                if looped:
                    period = audit_meta.get("loop_period") if audit_meta is not None else None
                    logger.warning(
                        f"Loop fallback: engine stopped a reasoning loop (req_id={req_id}, period={period}); "
                        f"re-sending at effort={LOOP_FALLBACK_EFFORT!r}"
                    )
                    t_fb = time.perf_counter()
                    fb_chunks = 0
                    try:
                        if audit_meta is not None:
                            audit_meta["loop_fallback"] = True
                            audit_meta["loop_fallback_effort"] = LOOP_FALLBACK_EFFORT
                            audit_meta["finish_reason"] = None
                            if not audit_meta["stream"]:
                                audit_json_buf.clear()
                        async for c in _run_loop_fallback():
                            fb_chunks += 1
                            _audit_feed(c)
                            yield c
                        if audit_meta is not None:
                            audit_meta["loop_fallback_ok"] = True
                            audit_meta["loop_fallback_s"] = round(time.perf_counter() - t_fb, 3)
                    except Exception as e:
                        logger.error(f"Loop fallback failed (req_id={req_id}): {e}")
                        if audit_meta is not None:
                            audit_meta["loop_fallback_ok"] = False
                            audit_meta["loop_fallback_error"] = str(e)[:200]
                            audit_meta["finish_reason"] = "content_filter"
                        if fb_chunks == 0:  # nothing of the fallback went out: the engine's own honest stop does
                            if whole:
                                yield bytes(whole)
                            else:
                                for ev in held:
                                    yield ev.encode("utf-8")
                                if tail:
                                    yield tail.encode("utf-8")
                else:
                    if whole:
                        yield bytes(whole)
                    elif tail:
                        yield tail.encode("utf-8")
        except Exception as e:
            stream_err = str(e)[:200]
            raise
        finally:
            await cleanup_all()
            # Asynchronously offload session to NVMe cold storage ONLY when memory drops below high-watermark
            if prefix_key and body and len(body) > 8000:
                asyncio.create_task(
                    cold_kv_mgr.offload_raw_body(prefix_key, body, prompt_tokens=est_prompt_tokens)
                )

    return StreamingResponse(
        stream_body(),
        status_code=upstream_resp.status_code,
        headers=resp_headers,
        background=BackgroundTask(cleanup_all),
    )


load_config()

if __name__ == "__main__":
    import uvicorn

    host = state.get("listen_host", "0.0.0.0")
    port = state.get("listen_port", 8889)
    uvicorn.run("proxy:app", host=host, port=port, log_level="info")
