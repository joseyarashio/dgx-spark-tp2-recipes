#!/usr/bin/env python3
import asyncio
import hashlib
import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Dict, Any, Optional, List

logger = logging.getLogger("cold-kv-manager")

COLD_KV_DIR = Path("/home/joseyarashio/.cache/dgx_cold_kv")
TIER1_IDLE_TTL_SECONDS = 600             # 10 minutes idle -> prune from active_sessions tracking
TIER2_PURGE_TTL_SECONDS = 86400          # 24 hours unaccessed -> purge from NVMe archive
MAX_COLD_STORAGE_BYTES = 50 * (1024 ** 3)  # 50 GB maximum cold storage quota
HIGH_WATERMARK_FREE_MEM_GIB = 3.0        # Only trigger cold offload when free memory drops below 3.0 GiB


def get_host_free_memory_gib() -> float:
    """Reads available memory from /proc/meminfo in GiB."""
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    parts = line.split()
                    kb = float(parts[1])
                    return kb / (1024.0 * 1024.0)
    except Exception:
        pass
    return 0.0  # conservative fallback on read failure


class ColdSessionEntry:
    def __init__(self, session_key: str, prompt_tokens: int, last_accessed: float, file_path: Path):
        self.session_key = session_key
        self.prompt_tokens = prompt_tokens
        self.last_accessed = last_accessed
        self.file_path = file_path
        self.file_size = 0


class ColdKVManager:
    """
    Session Transcript & Context Archive Manager with High-Watermark Guard.
    Maintains a bounded two-tier TTL hierarchy:
      - Active Tracking Tier: Tracks active session keys (pruned after 10m idle to prevent memory leaks).
      - NVMe Archive Tier: Asynchronously stages session payloads to NVMe ONLY when host free memory < 3.5 GiB.
      - Purge Tier: Stale archives (>24h unaccessed) or over-quota (>50GB) entries are pruned via LRU.
    """
    def __init__(self, storage_dir: Path = COLD_KV_DIR):
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.active_sessions: Dict[str, float] = {}  # session_key -> last_active_ts
        self.cold_index: Dict[str, ColdSessionEntry] = {}
        self.lock = asyncio.Lock()
        self._load_existing_index()

    def _load_existing_index(self):
        try:
            for p in self.storage_dir.glob("*.json"):
                try:
                    stat = p.stat()
                    key = p.stem
                    entry = ColdSessionEntry(
                        session_key=key,
                        prompt_tokens=0,
                        last_accessed=stat.st_mtime,
                        file_path=p
                    )
                    entry.file_size = stat.st_size
                    self.cold_index[key] = entry
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Error scanning cold KV index: {e}")

    async def touch_session(self, session_key: str):
        """Marks a session as actively running in memory tier."""
        if not session_key:
            return
        now = time.time()
        async with self.lock:
            self.active_sessions[session_key] = now
            if session_key in self.cold_index:
                self.cold_index[session_key].last_accessed = now

    async def offload_raw_body(self, session_key: str, body_bytes: bytes, prompt_tokens: int = 0, force: bool = False):
        """
        Non-blocking offload of raw request body bytes to NVMe ONLY when free memory drops below
        HIGH_WATERMARK_FREE_MEM_GIB (3.5 GiB). JSON parsing and atomic disk write run in worker thread
        so the asyncio event loop is never blocked.
        """
        if not session_key or not body_bytes:
            return

        free_mem = get_host_free_memory_gib()
        if not force and free_mem >= HIGH_WATERMARK_FREE_MEM_GIB:
            return

        file_path = self.storage_dir / f"{session_key}.json"
        tmp_path = self.storage_dir / f".{session_key}.{os.getpid()}.tmp"

        def _parse_and_write() -> int:
            try:
                data = json.loads(body_bytes)
                messages = data.get("messages", [])
                if not messages:
                    return 0
                payload = {
                    "session_key": session_key,
                    "prompt_tokens": prompt_tokens,
                    "saved_at": time.time(),
                    "messages": messages,
                }
                out_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                with open(tmp_path, "wb") as f:
                    f.write(out_bytes)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, file_path)
                return len(out_bytes)
            finally:
                if tmp_path.exists():
                    try:
                        tmp_path.unlink()
                    except Exception:
                        pass

        try:
            written_bytes = await asyncio.to_thread(_parse_and_write)
            if written_bytes <= 0:
                return
        except Exception as e:
            logger.warning(f"Failed to offload session {session_key}: {e}")
            return

        async with self.lock:
            entry = ColdSessionEntry(
                session_key=session_key,
                prompt_tokens=prompt_tokens,
                last_accessed=time.time(),
                file_path=file_path
            )
            entry.file_size = written_bytes
            self.cold_index[session_key] = entry
            logger.info(f"Offloaded session {session_key} to NVMe ({written_bytes/1024:.1f} KB, ~{prompt_tokens} tokens)")

    async def offload_session(self, session_key: str, messages: List[Dict[str, Any]], prompt_tokens: int = 0, force: bool = False):
        """Backward-compatible wrapper for offload."""
        if not session_key or not messages:
            return
        free_mem = get_host_free_memory_gib()
        if not force and free_mem >= HIGH_WATERMARK_FREE_MEM_GIB:
            return
        raw = json.dumps({"messages": messages}, ensure_ascii=False).encode("utf-8")
        await self.offload_raw_body(session_key, raw, prompt_tokens=prompt_tokens, force=force)

    async def restore_session(self, session_key: str) -> Optional[List[Dict[str, Any]]]:
        """Restores a session context from NVMe SSD."""
        if not session_key:
            return None
        async with self.lock:
            entry = self.cold_index.get(session_key)
            if not entry or not entry.file_path.exists():
                return None
            entry.last_accessed = time.time()
            fp = entry.file_path

        def _read():
            with open(fp, "rb") as f:
                return json.loads(f.read().decode("utf-8"))

        try:
            t0 = time.perf_counter()
            data = await asyncio.to_thread(_read)
            elapsed = (time.perf_counter() - t0) * 1000
            logger.info(f"Restored session {session_key} from NVMe in {elapsed:.2f}ms")
            return data.get("messages")
        except Exception as e:
            logger.warning(f"Failed to restore session {session_key}: {e}")
            return None

    async def run_maintenance_sweep(self):
        """Enforces Tier 1 active_sessions pruning (10m), Tier 2 TTL purge (24h), and 50GB storage quota."""
        now = time.time()
        async with self.lock:
            # 0. Prune idle entries from active_sessions to prevent unbounded dict growth
            idle_active_keys = [
                k for k, ts in self.active_sessions.items()
                if (now - ts) > TIER1_IDLE_TTL_SECONDS
            ]
            for k in idle_active_keys:
                self.active_sessions.pop(k, None)

            # 1. Purge expired cold sessions (> 24h unaccessed)
            expired_keys = [
                k for k, entry in self.cold_index.items()
                if (now - entry.last_accessed) > TIER2_PURGE_TTL_SECONDS
            ]
            for k in expired_keys:
                entry = self.cold_index.pop(k, None)
                if entry and entry.file_path.exists():
                    try:
                        entry.file_path.unlink()
                        logger.info(f"Purged expired cold session {k} (>24h unaccessed)")
                    except Exception:
                        pass

            # 2. Enforce 50 GB storage quota via LRU
            total_bytes = sum(entry.file_size for entry in self.cold_index.values())
            if total_bytes > MAX_COLD_STORAGE_BYTES:
                sorted_entries = sorted(self.cold_index.values(), key=lambda e: e.last_accessed)
                for entry in sorted_entries:
                    if total_bytes <= MAX_COLD_STORAGE_BYTES:
                        break
                    try:
                        entry.file_path.unlink()
                        total_bytes -= entry.file_size
                        del self.cold_index[entry.session_key]
                        logger.info(f"Quota eviction: pruned {entry.session_key} ({entry.file_size/1024:.1f} KB)")
                    except Exception:
                        pass

    def get_stats(self) -> Dict[str, Any]:
        total_bytes = sum(e.file_size for e in self.cold_index.values())
        return {
            "active_tracked_sessions": len(self.active_sessions),
            "cold_sessions_count": len(self.cold_index),
            "total_cold_bytes": total_bytes,
            "total_cold_mb": round(total_bytes / (1024 * 1024), 2),
            "storage_dir": str(self.storage_dir),
            "tier1_idle_ttl_s": TIER1_IDLE_TTL_SECONDS,
            "tier2_purge_ttl_s": TIER2_PURGE_TTL_SECONDS,
            "quota_gb": MAX_COLD_STORAGE_BYTES / (1024 ** 3),
            "high_watermark_free_gib": HIGH_WATERMARK_FREE_MEM_GIB,
        }
