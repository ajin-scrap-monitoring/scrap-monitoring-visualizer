from __future__ import annotations

import asyncio
import socket
from queue import Queue
from typing import Any

import pytest
import uvicorn

from scrap_monitoring_visualizer.live import LiveCoordinator
from scrap_monitoring_visualizer.preview import (
    LatestFrameStore,
    RequestGate,
    create_preview_app,
)
from scrap_monitoring_visualizer.rendering import RenderConfig
from scrap_monitoring_visualizer.rendering.worker import (
    LatestRenderWorker,
    RenderOutcome,
)


async def _request(port: int, path: str) -> tuple[int, dict[str, str], bytes]:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(
        f"GET {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n".encode()
    )
    await writer.drain()
    response = await reader.read()
    writer.close()
    await writer.wait_closed()
    header_bytes, body = response.split(b"\r\n\r\n", 1)
    header_lines = header_bytes.decode("latin-1").split("\r\n")
    status = int(header_lines[0].split()[1])
    headers = {
        key.lower(): value.strip()
        for key, value in (line.split(":", 1) for line in header_lines[1:])
    }
    return status, headers, body


def test_latest_frame_store_replaces_without_history() -> None:
    store = LatestFrameStore()

    first = store.publish(b"first", sequence=1)
    second = store.publish(b"second", sequence=2)

    assert first.revision == 1
    assert second.revision == 2
    assert store.get() == second
    store.clear()
    assert store.get() is None
    assert store.revision == 3


def test_request_gate_rejects_excess_concurrency() -> None:
    async def exercise() -> None:
        gate = RequestGate(1)
        assert await gate.acquire() is True
        assert await gate.acquire() is False
        await gate.release()
        assert await gate.acquire() is True
        await gate.release()

    asyncio.run(exercise())


def test_renderer_invalidation_discards_previous_run_outcome() -> None:
    frames = LatestFrameStore()
    worker = LatestRenderWorker.__new__(LatestRenderWorker)
    worker._frames = frames
    worker._generation = 2
    worker._inflight = True
    worker._requests = Queue[Any]()
    worker._outcomes = Queue[Any]()
    worker._pending = None
    worker._outcomes.put(
        RenderOutcome(
            generation=1,
            sequence=9,
            png=b"old frame",
            error=None,
        )
    )
    worker.last_error = "old renderer error"

    worker.invalidate()

    assert worker.poll() is None
    assert frames.get() is None
    assert worker.last_error is None


def test_renderer_sends_latest_pending_request_after_inflight_finishes() -> None:
    frames = LatestFrameStore()
    worker = LatestRenderWorker.__new__(LatestRenderWorker)
    worker._frames = frames
    worker._generation = 0
    worker._inflight = True
    worker._requests = Queue[Any](maxsize=1)
    worker._outcomes = Queue[Any]()
    worker._pending = None
    worker.last_error = None
    worker.submit("waiting")
    worker.submit("latest")

    assert worker._pending == (0, "latest")
    assert worker.poll() is None
    assert worker._pending == (0, "latest")
    worker._outcomes.put(
        RenderOutcome(
            generation=0,
            sequence=1,
            png=None,
            error="old renderer error",
        )
    )

    assert worker.poll() is not None
    assert worker._requests.get_nowait() == (0, "latest")
    assert worker._pending is None
    assert worker._inflight is True


def test_coordinator_fails_when_browser_renderer_exits() -> None:
    frames = LatestFrameStore()
    worker = LatestRenderWorker.__new__(LatestRenderWorker)
    worker._frames = frames
    worker._generation = 0
    worker._inflight = False
    worker._requests = Queue[Any]()
    worker._outcomes = Queue[Any]()
    worker._pending = None
    worker.last_error = None
    worker._process = type(
        "DeadProcess",
        (),
        {"is_alive": staticmethod(lambda: False)},
    )()
    coordinator = LiveCoordinator(frames, worker, RenderConfig())

    with pytest.raises(RuntimeError, match="browser renderer process exited"):
        coordinator.poll_renderers()


def test_preview_http_endpoints_return_latest_frame() -> None:
    async def exercise() -> None:
        frames = LatestFrameStore()
        app = create_preview_app(
            frames,
            lambda: {"connected": True, "received_sequence": 7},
        )
        listener = socket.socket()
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = int(listener.getsockname()[1])
        server = uvicorn.Server(
            uvicorn.Config(app, lifespan="off", access_log=False, log_level="error")
        )
        task = asyncio.create_task(server.serve(sockets=[listener]))
        while not server.started:
            await asyncio.sleep(0.01)
        try:
            status, headers, body = await _request(port, "/frame.png")
            assert status == 204
            assert body == b""
            assert headers["cache-control"] == "no-store"

            frames.publish(b"\x89PNG\r\n\x1a\nframe", sequence=7)
            status, headers, body = await _request(port, "/frame.png")
            assert status == 200
            assert headers["content-type"] == "image/png"
            assert headers["x-frame-revision"] == "1"
            assert "x-run-id" not in headers
            assert headers["x-sequence"] == "7"
            assert body.startswith(b"\x89PNG")

            status, _, body = await _request(port, "/status")
            assert status == 200
            assert b'"frame_revision":1' in body
            assert b'"rendered_sequence":7' in body

            status, _, body = await _request(port, "/")
            assert status == 200
            assert b"/frame.png?revision=" in body
            assert b'href="/camera/"' not in body
            assert b'new URL("/camera/v1/stream"' in body
            assert body.count(b"<img ") == 2
            assert b'class="views"' in body
            assert b"status.frame_revision!==displayedRevision" in body
        finally:
            server.should_exit = True
            await task

    asyncio.run(exercise())
