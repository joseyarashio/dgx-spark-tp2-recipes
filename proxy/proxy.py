import asyncio
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
        "DeepSeek-V4.1-Flash-TF": 4,
        "DeepSeek-V4.1-Flash-1017-TF": 4,
        "GLM-5.3-Flash": 4,
        "GLM-5.3-Flash-EXL3": 4,
    },
    "default_limit": 4,
    "queue_buffer": 4,
    "tiered_timeouts": [20.0, 15.0, 10.0, 5.0],
    "extension_seconds": 5.0,
    "poll_interval_seconds": 3,
    "current_model": "unknown",
    "current_limit": 4,
    "active_running": 0,
    "waiting_in_queue": 0,
    "upstream_healthy": False,
}


class Waiter:
    def __init__(self, pos: int, priority: int = 1, prefix_key: str = ""):
        self.pos = pos
        self.priority = priority  # 0: interactive/foreground, 1: normal, 2: background/batch
        self.prefix_key = prefix_key
        self.promoted = False
        self.extended = False
        self.deadline = 0.0
        self.event = asyncio.Event()


# Single-Flight Prefix State Machine (Strata Proposal 2)
# Tracks in-flight prefill per prefix key to eliminate Delay-Hit redundant prefill.
prefix_inflight: Dict[str, asyncio.Event] = {}
prefix_committed: Dict[str, float] = {}  # prefix_key -> timestamp committed
prefix_lock = asyncio.Lock()


def compute_prefix_key(body_bytes: bytes) -> str:
    """Extracts canonical prefix hash for prompts > 4000 characters."""
    if len(body_bytes) < 4000:
        return ""
    try:
        data = json.loads(body_bytes)
        messages = data.get("messages", [])
        if not messages:
            return ""
        prefix_str = ""
        for m in messages:
            content = m.get("content", "")
            if isinstance(content, str):
                prefix_str += content[:16384]
            elif isinstance(content, list):
                for p in content:
                    if p.get("type") == "text":
                        prefix_str += p.get("text", "")[:16384]
        if len(prefix_str) < 4000:
            return ""
        import hashlib
        return hashlib.sha256(prefix_str[:32768].encode()).hexdigest()[:16]
    except Exception:
        return ""


waiting_queue: deque[Waiter] = deque()
queue_lock = asyncio.Lock()
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
    "upgrade",
}


def load_config() -> None:
    if not CONFIG_PATH.exists():
        return
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            state["upstream_url"] = cfg.get("upstream_url", state["upstream_url"]).rstrip("/")
            state["model_limits"] = cfg.get("model_limits", state["model_limits"])
            state["default_limit"] = cfg.get("default_limit", state["default_limit"])
            state["queue_buffer"] = cfg.get("queue_buffer", state["queue_buffer"])
            state["tiered_timeouts"] = [float(t) for t in cfg.get("tiered_timeouts", state["tiered_timeouts"])]
            state["extension_seconds"] = float(cfg.get("extension_seconds", state["extension_seconds"]))
            state["poll_interval_seconds"] = cfg.get("poll_interval_seconds", state["poll_interval_seconds"])
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


async def monitor_upstream_model():
    """Background task to poll upstream /v1/models and detect active model & limits."""
    while True:
        try:
            load_config()
            url = f"{state['upstream_url']}/v1/models"
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
                            f"(was: {old_model} with limit {old_limit})"
                        )
                        async with queue_lock:
                            _wake_next_locked()
                else:
                    state["upstream_healthy"] = False
        except Exception:
            state["upstream_healthy"] = False

        await asyncio.sleep(state["poll_interval_seconds"])


def _wake_next_locked():
    """Promote waiting requests if active_running < current_limit, respecting priority order."""
    limit = state["current_limit"]
    while state["active_running"] < limit and len(waiting_queue) > 0:
        # Find highest priority waiter (lowest priority integer: 0 > 1 > 2)
        best_idx = 0
        best_prio = waiting_queue[0].priority
        for i, w in enumerate(waiting_queue):
            if w.priority < best_prio:
                best_prio = w.priority
                best_idx = i

        promoted_waiter = waiting_queue[best_idx]
        del waiting_queue[best_idx]

        promoted_waiter.promoted = True
        promoted_waiter.event.set()
        state["active_running"] += 1
        # Advance everyone else in queue
        for i, w in enumerate(waiting_queue):
            w.pos = i
            w.extended = False  # fresh tier gets fresh extension rights
            w.event.set()
    state["waiting_in_queue"] = len(waiting_queue)


async def acquire_slot(priority: int = 1, prefix_key: str = "") -> Tuple[bool, str]:
    """
    Acquire an execution slot with Tiered Dynamic Queue Management, Priority Scheduling, Anti-Herd Extension,
    and Strata Single-Flight Prefix Coordination.
    priority: 0 = high/foreground, 1 = normal, 2 = background/batch.
    Background requests (priority >= 2) cannot consume more than background_max_slots (default 3 of 4).
    """
    # Single-Flight Check: if another identical prefix is currently building in prefill,
    # wait briefly for it to complete its KV commit so we hit cache instead of duplicating prefill!
    leader_event: Optional[asyncio.Event] = None
    if prefix_key:
        now = time.time()
        async with prefix_lock:
            # Clean up old committed entries (> 300s)
            expired = [k for k, ts in prefix_committed.items() if now - ts > 300]
            for k in expired:
                del prefix_committed[k]

            if prefix_key in prefix_inflight:
                leader_event = prefix_inflight[prefix_key]
            elif prefix_key in prefix_committed and (now - prefix_committed[prefix_key] < 60):
                # Prefix recently committed within 60s: proceed immediately to attach cache!
                leader_event = None
            else:
                prefix_inflight[prefix_key] = asyncio.Event()

    if leader_event:
        logger.info(f"Single-Flight Delay-Hit Mitigation: Waiting for leader prefill [prefix: {prefix_key}]...")
        try:
            # Wait up to 25s for leader prefill to finish and commit KV
            await asyncio.wait_for(leader_event.wait(), timeout=25.0)
            logger.info(f"Single-Flight Leader finished: Follower attached to cached prefix [prefix: {prefix_key}]")
        except asyncio.TimeoutError:
            logger.warning(f"Single-Flight Leader wait timed out for prefix {prefix_key}, falling back to normal acquire.")

    async with queue_lock:
        limit = state["current_limit"]
        queue_max = state["queue_buffer"]
        bg_max = state.get("background_max_slots", 3)

        # Background ceiling check: reserve at least 1 slot for interactive
        if priority >= 2 and state["active_running"] >= bg_max:
            # Check if queue has room
            if len(waiting_queue) >= queue_max:
                return False, "bg_limit_queue_full"

        # 1. Direct GPU execution if slot free and nobody waiting ahead with higher priority
        if state["active_running"] < limit:
            has_higher_waiting = any(w.priority < priority for w in waiting_queue)
            if not has_higher_waiting:
                if not (priority >= 2 and state["active_running"] >= bg_max):
                    state["active_running"] += 1
                    logger.info(
                        f"Direct GPU execution [running: {state['active_running']}/{limit}, prio: {priority}] (model: {state['current_model']})"
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
                # Timed out at current position without promotion or advance signal
                async with queue_lock:
                    if waiter.promoted:
                        return True, "promoted"

                    # Anti-Herd Extension Check:
                    # If not already extended at this tier, check if ANY waiter ahead has remaining time <= 5s
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
                        # Advance waiters behind this one
                        for i in range(idx, len(waiting_queue)):
                            w = waiting_queue[i]
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
                logger.info(
                    f"Promoted to GPU execution [running: {state['active_running']}/{state['current_limit']}]"
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
                _wake_next_locked()
            elif waiter in waiting_queue:
                idx = waiting_queue.index(waiter)
                del waiting_queue[idx]
                for i in range(idx, len(waiting_queue)):
                    w = waiting_queue[i]
                    w.pos = i
                    w.extended = False
                    w.event.set()
                state["waiting_in_queue"] = len(waiting_queue)
        raise


async def release_slot():
    async with queue_lock:
        state["active_running"] = max(0, state["active_running"] - 1)
        _wake_next_locked()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    limits = httpx.Limits(max_keepalive_connections=100, max_connections=200)
    http_client = httpx.AsyncClient(limits=limits, timeout=httpx.Timeout(600.0, connect=10.0))
    monitor_task = asyncio.create_task(monitor_upstream_model())
    logger.info(
        f"Starting proxy with upstream: {state['upstream_url']} "
        f"(queue_buffer={state['queue_buffer']}, tiered_timeouts={state['tiered_timeouts']}, "
        f"anti_herd_extension={state['extension_seconds']}s)"
    )
    yield
    monitor_task.cancel()
    if http_client:
        await http_client.aclose()


app = FastAPI(title="Spark Fast-Fail Concurrency Proxy with Anti-Herd Dynamic Queue", lifespan=lifespan)


@app.get("/proxy/status")
async def get_proxy_status():
    async with queue_lock:
        running = state["active_running"]
        waiting = len(waiting_queue)
        positions = [w.pos + 1 for w in waiting_queue]
        extended_flags = [w.extended for w in waiting_queue]
    return {
        "status": "ok",
        "upstream_healthy": state["upstream_healthy"],
        "upstream_url": state["upstream_url"],
        "current_model": state["current_model"],
        "concurrency_limit": state["current_limit"],
        "queue_buffer": state["queue_buffer"],
        "tiered_timeouts": state["tiered_timeouts"],
        "extension_seconds": state["extension_seconds"],
        "active_running": running,
        "waiting_in_queue": waiting,
        "queue_positions": positions,
        "queue_extended": extended_flags,
        "model_limits_config": state["model_limits"],
        "default_limit": state["default_limit"],
    }


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def proxy_all(request: Request, path: str):
    is_completion = path.strip("/").endswith("chat/completions") or path.strip("/").endswith("completions")

    if is_completion and request.method == "POST":
        body_bytes = await request.body()
        prefix_key = compute_prefix_key(body_bytes)

        # Extract Priority Header: 0 = high/foreground, 1 = normal, 2 = background/batch
        prio_hdr = request.headers.get("x-priority") or request.headers.get("priority")
        priority = 1
        if prio_hdr:
            prio_lower = prio_hdr.lower()
            if prio_lower in ["high", "foreground", "interactive", "0"]:
                priority = 0
            elif prio_lower in ["low", "background", "batch", "2"]:
                priority = 2

        acquired, reason = await acquire_slot(priority=priority, prefix_key=prefix_key)
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
            return await handle_forward(request, path, release_on_close=True, cached_body=body_bytes, prefix_key=prefix_key)
        except Exception:
            await release_slot()
            if prefix_key:
                async with prefix_lock:
                    if prefix_key in prefix_inflight:
                        prefix_inflight[prefix_key].set()
                        del prefix_inflight[prefix_key]
            raise
    else:
        return await handle_forward(request, path, release_on_close=False)


async def handle_forward(
    request: Request,
    path: str,
    release_on_close: bool = False,
    cached_body: Optional[bytes] = None,
    prefix_key: str = "",
):
    upstream_url = f"{state['upstream_url']}/{path}"
    query = request.url.query
    if query:
        upstream_url = f"{upstream_url}?{query}"

    req_headers = {k: v for k, v in request.headers.items() if k.lower() not in EXCLUDE_HEADERS}
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
    except Exception as e:
        if release_on_close:
            await release_slot()
        if prefix_key:
            async with prefix_lock:
                if prefix_key in prefix_inflight:
                    prefix_inflight[prefix_key].set()
                    del prefix_inflight[prefix_key]
        logger.error(f"Failed to connect to upstream {upstream_url}: {e}")
        return JSONResponse(
            status_code=502,
            content={"error": {"message": f"Bad Gateway to Spark backend: {e}", "type": "bad_gateway", "code": 502}},
        )

    resp_headers = {
        k: v for k, v in upstream_resp.headers.items() if k.lower() not in EXCLUDE_HEADERS
    }
    if est_prompt_tokens > 0:
        resp_headers["x-spark-estimated-tokens"] = str(est_prompt_tokens)
        if est_prompt_tokens > 250000:
            resp_headers["x-spark-compaction-advisory"] = "prompt_exceeds_250k_compaction_recommended"

    async def stream_body():
        released = False
        prefix_notified = False
        try:
            async for chunk in upstream_resp.aiter_bytes():
                # Notify single-flight waiters as soon as first chunk arrives (prefill finished!)
                if prefix_key and not prefix_notified:
                    prefix_notified = True
                    async with prefix_lock:
                        prefix_committed[prefix_key] = time.time()
                        if prefix_key in prefix_inflight:
                            prefix_inflight[prefix_key].set()
                            del prefix_inflight[prefix_key]
                yield chunk
        finally:
            if not released and release_on_close:
                released = True
                await release_slot()
            if prefix_key and not prefix_notified:
                async with prefix_lock:
                    if prefix_key in prefix_inflight:
                        prefix_inflight[prefix_key].set()
                        del prefix_inflight[prefix_key]
            await upstream_resp.aclose()

    return StreamingResponse(
        stream_body(),
        status_code=upstream_resp.status_code,
        headers=resp_headers,
    )


if __name__ == "__main__":
    import uvicorn

    load_config()
    host = state.get("listen_host", "0.0.0.0")
    port = state.get("listen_port", 8889)
    uvicorn.run("proxy:app", host=host, port=port, log_level="info")
