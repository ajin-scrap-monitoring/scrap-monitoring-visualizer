"""FastAPI preview endpoints and bounded request admission."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from .store import LatestFrameStore

StatusProvider = Callable[[], Mapping[str, Any]]

_INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Scrap Monitoring Visualizer</title>
  <style>
    body{margin:0;background:#f4f6f8;color:#202124;font:14px sans-serif}
    main{max-width:1400px;margin:auto;padding:24px}
    figure{margin:0}
    figcaption{font-weight:600;margin:0 0 8px}
    nav{margin:0 0 12px}
    img{display:block;width:100%;background:#fff;border:1px solid #9aa0a6}
    pre{white-space:pre-wrap;background:#fff;border:1px solid #dadce0;padding:12px}
  </style>
</head>
<body><main>
  <h1>Scrap Monitoring Visualizer</h1>
  <nav><a id="camera-link" href="/camera/" hidden>Open synthetic camera</a></nav>
  <figure><figcaption>3D model</figcaption>
    <img id="frame" alt="Latest rendered observation">
  </figure>
  <pre id="status">Waiting for server status.</pre>
</main><script>
const frame=document.getElementById("frame");
const statusNode=document.getElementById("status");
const cameraLink=document.getElementById("camera-link");
let displayedRevision=null;
async function refresh(){
  try{
    const response=await fetch("/status",{cache:"no-store"});
    const status=await response.json();
    statusNode.textContent=JSON.stringify(status,null,2);
    cameraLink.hidden=status.synthetic_camera?.camera_enabled!==true;
    if(status.frame_revision!==null&&status.frame_revision!==displayedRevision){
      frame.src="/frame.png?revision="+status.frame_revision;
      displayedRevision=status.frame_revision;
    }else if(status.frame_revision===null){
      frame.removeAttribute("src");
      displayedRevision=null;
    }
  }catch(error){statusNode.textContent=String(error);}
  setTimeout(refresh,500);
}
refresh();
</script></body></html>
"""


class RequestGate:
    def __init__(self, limit: int) -> None:
        if limit <= 0:
            raise ValueError("request limit must be positive")
        self._limit = limit
        self._active = 0
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        async with self._lock:
            if self._active >= self._limit:
                return False
            self._active += 1
            return True

    async def release(self) -> None:
        async with self._lock:
            if self._active <= 0:
                raise RuntimeError("request gate release without acquire")
            self._active -= 1


def create_preview_app(
    frames: LatestFrameStore,
    status_provider: StatusProvider,
    *,
    max_requests: int = 16,
    request_timeout_s: float = 5.0,
) -> FastAPI:
    if request_timeout_s <= 0:
        raise ValueError("request timeout must be positive")
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    gate = RequestGate(max_requests)

    @app.middleware("http")
    async def bounded_request(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if not await gate.acquire():
            return JSONResponse({"detail": "request limit exceeded"}, status_code=503)
        try:
            async with asyncio.timeout(request_timeout_s):
                return await call_next(request)
        except TimeoutError:
            return JSONResponse({"detail": "request timeout"}, status_code=504)
        finally:
            await gate.release()

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        return HTMLResponse(_INDEX_HTML, headers={"Cache-Control": "no-store"})

    @app.get("/frame.png")
    async def frame() -> Response:
        snapshot = frames.get()
        if snapshot is None:
            return Response(status_code=204, headers={"Cache-Control": "no-store"})
        return Response(
            snapshot.png,
            media_type="image/png",
            headers={
                "Cache-Control": "no-store",
                "X-Frame-Revision": str(snapshot.revision),
                "X-Sequence": str(snapshot.sequence),
            },
        )

    @app.get("/status")
    async def status() -> JSONResponse:
        payload = dict(status_provider())
        frame_snapshot = frames.get()
        payload["frame_revision"] = (
            frame_snapshot.revision if frame_snapshot is not None else None
        )
        payload["rendered_sequence"] = (
            frame_snapshot.sequence if frame_snapshot is not None else None
        )
        return JSONResponse(payload, headers={"Cache-Control": "no-store"})

    return app
