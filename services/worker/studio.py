"""Run HyperFrames Studio (the timeline editor) for a project's composition.

``npx hyperframes preview`` serves Studio on 127.0.0.1 only. In Docker the
browser cannot reach that, so when ``STUDIO_PUBLIC_BIND`` is set each Studio
gets a TCP forwarder on a published port (Studio itself moves to
``port + STUDIO_INTERNAL_OFFSET``). The forwarder is plain TCP, so Studio's
hot-reload websocket passes through unchanged.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("video-editor-studio")

STUDIO_INTERNAL_OFFSET = 100


@dataclass
class StudioSession:
    composition: Path
    public_port: int
    project_name: str
    url: str
    forwarder: asyncio.base_events.Server | None = None


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except (ConnectionError, asyncio.CancelledError):
        pass
    finally:
        writer.close()


async def _forward(bind: str, public_port: int, target_port: int) -> asyncio.base_events.Server:
    async def handle(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter) -> None:
        try:
            upstream_reader, upstream_writer = await asyncio.open_connection("127.0.0.1", target_port)
        except OSError:
            client_writer.close()
            return
        await asyncio.gather(_pipe(client_reader, upstream_writer), _pipe(upstream_reader, client_writer))

    return await asyncio.start_server(handle, bind, public_port)


class StudioManager:
    def __init__(self, *, first_port: int | None = None, slots: int | None = None, public_bind: str | None = None, public_host: str | None = None):
        self.first_port = first_port or int(os.getenv("STUDIO_FIRST_PORT", "3400"))
        self.slots = slots or int(os.getenv("STUDIO_SLOTS", "10"))
        self.public_bind = public_bind if public_bind is not None else os.getenv("STUDIO_PUBLIC_BIND", "")
        self.public_host = public_host or os.getenv("STUDIO_PUBLIC_HOST", "localhost")
        self.sessions: dict[str, StudioSession] = {}
        self._lock = asyncio.Lock()

    def _free_port(self) -> int:
        used = {session.public_port for session in self.sessions.values()}
        for port in range(self.first_port, self.first_port + self.slots):
            if port not in used:
                return port
        # Every slot is taken: recycle the oldest Studio.
        oldest = next(iter(self.sessions))
        return self.sessions[oldest].public_port

    async def _run_preview(self, composition: Path, port: int) -> dict:
        argv = [shutil.which("npx") or "npx", "hyperframes", "preview", str(composition), "--background", "--no-open", "--json", "--port", str(port)]
        process = await asyncio.create_subprocess_exec(*argv, cwd=composition, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=180)
        text = stdout.decode(errors="replace").strip().splitlines()
        payload = next((json.loads(line) for line in reversed(text) if line.startswith("{")), None)
        if not payload or not payload.get("ok"):
            raise RuntimeError(f"HyperFrames Studio failed to start: {(stderr.decode(errors='replace') or stdout.decode(errors='replace')).strip()[-1500:]}")
        return payload["result"]

    async def _stop(self, session: StudioSession) -> None:
        if session.forwarder is not None:
            session.forwarder.close()
        argv = [shutil.which("npx") or "npx", "hyperframes", "preview", str(session.composition), "--stop", "--json"]
        process = await asyncio.create_subprocess_exec(*argv, cwd=session.composition, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        await process.wait()

    async def open(self, key: str, composition: Path) -> StudioSession:
        """Start (or reuse) Studio for ``composition`` and return its browser URL."""

        async with self._lock:
            existing = self.sessions.get(key)
            if existing and existing.composition == composition:
                return existing
            if existing:
                await self._stop(self.sessions.pop(key))
            public_port = self._free_port()
            for other_key, other in list(self.sessions.items()):
                if other.public_port == public_port:
                    await self._stop(self.sessions.pop(other_key))
            internal_port = public_port + STUDIO_INTERNAL_OFFSET if self.public_bind else public_port
            result = await self._run_preview(composition, internal_port)
            port = int(result.get("port") or internal_port)
            name = str(result.get("projectName") or composition.name)
            forwarder = await _forward(self.public_bind, public_port, port) if self.public_bind else None
            shown_port = public_port if self.public_bind else port
            url = f"http://{self.public_host}:{shown_port}/#project/{name}"
            session = StudioSession(composition, public_port, name, url, forwarder)
            self.sessions[key] = session
            logger.info("studio_open key=%s url=%s", key, url)
            return session
