import asyncio
import hashlib
import itertools
import json
import logging
import os
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

from cold_kv import ColdKVManager

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
        with open("/dev/shm/dgx_cluster_state.tmp", "w") as f:
            f.write(content)
        os.replace("/dev/shm/dgx_cluster_state.tmp", "/dev/shm/dgx_cluster_state")
    except Exception:
        pass


class Waiter:
    def __init__(self, pos: int, priority: int = 1, prefix_key: str = ""):
        self.pos = pos
        self.priority = priority  # 0: interactive/foreground, 1: normal, 2: background/batch
        self.prefix_key = prefix_key
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


def get_timeout(pos: int) -> float:
    timeouts = state["tiered_timeouts"]
    if pos < len(timeouts):
        return timeouts[pos]
    return timeouts[-1] if timeouts else 5.0


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


def _can_run_priority_locked(priority: int) -> bool:
    """
    Checks whether a request with `priority` is eligible to take an active GPU slot.
    Enforces both total concurrency limit AND background_max_slots ceiling (reserving at least
    `limit - bg_max` slots for foreground/normal requests when background_max_slots < current_limit).
    """
    limit = state["current_limit"]
    if state["active_running"] >= limit:
        return False
    if priority >= 2:
        bg_max = state.get("background_max_slots", 5)
        reserved_fg = max(1, limit - bg_max) if bg_max < limit else 0
        if state["bg_running"] >= bg_max or state["active_running"] >= max(1, limit - reserved_fg):
            return False
    return True


def _compute_waiter_score(priority: int, prefix_key: str, enqueued_at: float, now_mono: float) -> Tuple[int, int, float]:
    """
    Unified scheduling score used by both Direct Path and `_wake_next_locked`:
      1. Hard Anti-Starvation Ceiling: Any request waiting >= 15s gets elevated to top priority 0
         and `is_cold = 0` to prevent Head-of-Line inversion from newer short tasks.
      2. Effective priority: P2 ages to priority 1 after 8s (P0=0 always stays strictly highest).
      3. Cache-Aware tie-breaker: warm committed prefix gets `is_cold = 0`.
      4. Monotonic enqueue timestamp (FIFO).
    """
    wait_s = max(0.0, now_mono - enqueued_at)
    if wait_s >= 15.0:
        # Anti-Starvation Ceiling reached: elevate to highest rank
        return (0, 0, enqueued_at)

    eff_prio = max(1, priority - int(wait_s // 8.0)) if priority >= 2 else priority
    is_cold = 0 if (prefix_key and prefix_committed.get(prefix_key, 0.0) > now_mono) else 1
    return (eff_prio, is_cold, enqueued_at)


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
            if not _can_run_priority_locked(w.priority):
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


async def acquire_slot(priority: int = 1, prefix_key: str = "", req_id: int = 0) -> Tuple[bool, str]:
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
        try:
            await asyncio.wait_for(leader_entry.event.wait(), timeout=SINGLEFLIGHT_WAIT_TIMEOUT)
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

            # Background ceiling check when queue is also full
            if priority >= 2 and (state["active_running"] >= bg_max or state["bg_running"] >= bg_max):
                if len(waiting_queue) >= queue_max:
                    return False, "bg_limit_queue_full"

            # 1. Direct GPU execution if eligible and nobody waiting ahead with better unified score
            if _can_run_priority_locked(priority):
                now_m = time.monotonic()
                incoming_score = _compute_waiter_score(priority, prefix_key, now_m, now_m)
                has_better_waiting = any(
                    _can_run_priority_locked(w.priority)
                    and _compute_waiter_score(w.priority, w.prefix_key, w.enqueued_at, now_m) <= incoming_score
                    for w in waiting_queue
                )
                if not has_better_waiting:
                    state["active_running"] += 1
                    if priority >= 2:
                        state["bg_running"] += 1
                    slot_acquired = True
                    _sync_cluster_shm()
                    logger.info(
                        f"Direct GPU execution [running: {state['active_running']}/{limit}, bg: {state['bg_running']}/{bg_max}, prio: {priority}] "
                        f"(model: {state['current_model']})"
                    )
                    return True, "direct"

            # 2. Check if queue is already full -> immediate fast-fail
            if len(waiting_queue) >= queue_max:
                return False, "queue_full"

            # 3. Enter tiered queue with priority
            pos = len(waiting_queue)
            waiter = Waiter(pos, priority=priority, prefix_key=prefix_key)
            waiting_queue.append(waiter)
            state["waiting_in_queue"] = len(waiting_queue)
            _sync_cluster_shm()
            initial_timeout = get_timeout(pos)
            waiter.deadline = asyncio.get_event_loop().time() + initial_timeout
            logger.info(
                f"Entered standby queue at position {pos+1}/{queue_max} (prio={priority}, initial timeout={initial_timeout}s)"
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

                        # Anti-Herd Extension Check
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
                            cur_timeout = state.get("extension_seconds", 5.0)
                            waiter.deadline = asyncio.get_event_loop().time() + cur_timeout
                            logger.info(
                                f"Anti-herd extension: Waiter at pos {waiter.pos+1} EXTENDED by {cur_timeout}s "
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
                cur_timeout = get_timeout(waiter.pos)
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


async def release_slot(priority: int = 1):
    async with queue_lock:
        state["active_running"] = max(0, state["active_running"] - 1)
        if priority >= 2:
            state["bg_running"] = max(0, state["bg_running"] - 1)
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

        acquired, reason = await acquire_slot(priority=priority, prefix_key=prefix_key, req_id=req_id)
        if not acquired:
            curr_model = state["current_model"]
            limit = state["current_limit"]
            async with queue_lock:
                running = state["active_running"]
                waiting = len(waiting_queue)
            logger.warning(
                f"Fast-Fail 429 triggered: model '{curr_model}' (reason: {reason}, prio: {priority}, running: {running}/{limit}, queue: {waiting}/{state['queue_buffer']})"
            )
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
            )
        except BaseException:
            await release_slot(priority=priority)
            await _release_prefix(prefix_key, req_id, committed=False)
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
            raise
        logger.error(f"Failed to connect to upstream {upstream_url}: {e}")
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
    resp_closed = False

    async def cleanup_all():
        nonlocal released, prefix_notified, resp_closed
        if not released and release_on_close:
            released = True
            await release_slot(priority=priority)
        if prefix_key and not prefix_notified:
            prefix_notified = True
            await _release_prefix(prefix_key, req_id, committed=False)
        if not resp_closed:
            resp_closed = True
            try:
                await upstream_resp.aclose()
            except Exception:
                pass

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

    async def stream_body():
        nonlocal prefix_notified
        sse_rem = ""
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
                yield chunk
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
