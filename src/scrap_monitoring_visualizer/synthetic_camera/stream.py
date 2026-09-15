"""Latest-only MJPEG WebSocket delivery for an edge camera bridge."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping
from dataclasses import asdict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

from .models import StreamDescriptor
from .store import LatestJpegStore

CameraStatusProvider = Callable[[], Mapping[str, object]]
CAMERA_STREAM_PATH = "/camera/v1/stream"
CAMERA_STATUS_PATH = "/camera/v1/status"
CAMERA_PAGE_PATH = "/camera/"
_MAX_CAMERA_CLIENTS = 4

_CAMERA_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Synthetic Camera - Scrap Monitoring Visualizer</title>
  <style>
    body{margin:0;background:#f4f6f8;color:#202124;font:14px sans-serif}
    main{max-width:1920px;margin:auto;padding:24px}
    h1{font-size:20px;margin:0 0 12px}
    figure{margin:0}
    img{display:block;width:100%;aspect-ratio:16/9;object-fit:contain;background:#111;border:1px solid #9aa0a6}
    figcaption{margin-top:8px;color:#4b5563}
  </style>
</head>
<body><main>
  <h1>Synthetic camera</h1>
  <figure>
    <img id="camera" alt="Live synthetic camera frame">
    <figcaption id="status">Connecting.</figcaption>
  </figure>
</main><script>
const frame=document.getElementById("camera");
const statusNode=document.getElementById("status");
let socket=null;
let visibleUrl=null;
let pendingBlob=null;
let decoding=false;
let descriptor=null;
let retryTimer=null;

async function displayLatest(){
  if(decoding)return;
  decoding=true;
  while(pendingBlob!==null){
    const blob=pendingBlob;
    pendingBlob=null;
    const nextUrl=URL.createObjectURL(blob);
    await new Promise(resolve=>{
      frame.onload=resolve;
      frame.onerror=resolve;
      frame.src=nextUrl;
    });
    if(visibleUrl!==null)URL.revokeObjectURL(visibleUrl);
    visibleUrl=nextUrl;
  }
  decoding=false;
}

function reconnect(){
  clearTimeout(retryTimer);
  retryTimer=setTimeout(connect,1000);
}

function connect(){
  descriptor=null;
  statusNode.textContent="Connecting.";
  const url=new URL("v1/stream",window.location.href);
  url.protocol=window.location.protocol==="https:"?"wss:":"ws:";
  socket=new WebSocket(url);
  socket.binaryType="blob";
  socket.onmessage=event=>{
    if(typeof event.data==="string"){
      try{
        const value=JSON.parse(event.data);
        if(value.type!=="camera_stream_descriptor"||value.version!==1||value.format!=="MJPEG")throw new Error("Unsupported camera stream.");
        descriptor=value;
        statusNode.textContent=`Live ${value.width}x${value.height} ${value.format} ${value.fps} FPS`;
      }catch(error){
        statusNode.textContent=String(error);
        socket.close(1002,"invalid descriptor");
      }
      return;
    }
    if(descriptor===null){
      socket.close(1002,"descriptor required");
      return;
    }
    pendingBlob=event.data;
    displayLatest();
  };
  socket.onerror=()=>socket.close();
  socket.onclose=()=>{
    statusNode.textContent="Disconnected. Reconnecting.";
    reconnect();
  };
}

window.addEventListener("beforeunload",()=>{
  clearTimeout(retryTimer);
  if(socket!==null)socket.close();
  if(visibleUrl!==null)URL.revokeObjectURL(visibleUrl);
});
connect();
</script></body></html>
"""


class _ConnectionGate:
    def __init__(self, limit: int) -> None:
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
            self._active -= 1


async def _wait_for_client_end(websocket: WebSocket) -> tuple[int, str] | None:
    try:
        message = await websocket.receive()
    except RuntimeError, WebSocketDisconnect:
        return None
    if message["type"] == "websocket.disconnect":
        return None
    return 1003, "camera stream is send-only"


def install_camera_routes(
    app: FastAPI,
    store: LatestJpegStore,
    status_provider: CameraStatusProvider,
    fps: int = 30,
) -> None:
    if fps <= 0 or fps > 60:
        raise ValueError("camera stream fps must be between 1 and 60")
    connection_gate = _ConnectionGate(_MAX_CAMERA_CLIENTS)
    descriptor = StreamDescriptor(
        type="camera_stream_descriptor",
        version=1,
        format="MJPEG",
        width=0,
        height=0,
        fps=fps,
        max_frame_bytes=store.max_frame_bytes,
    )

    @app.get(CAMERA_PAGE_PATH)
    async def camera_page() -> HTMLResponse:
        return HTMLResponse(_CAMERA_HTML, headers={"Cache-Control": "no-store"})

    @app.get(CAMERA_STATUS_PATH)
    async def camera_status() -> JSONResponse:
        return JSONResponse(
            dict(status_provider()), headers={"Cache-Control": "no-store"}
        )

    @app.websocket(CAMERA_STREAM_PATH)
    async def camera_stream(websocket: WebSocket) -> None:
        await websocket.accept()
        if not await connection_gate.acquire():
            await websocket.close(code=1013, reason="camera client limit exceeded")
            return
        try:
            status = status_provider()
            width = status.get("camera_width")
            height = status.get("camera_height")
            if not isinstance(width, int) or not isinstance(height, int):
                await websocket.close(code=1011, reason="camera dimensions unavailable")
                return
            connection_descriptor = StreamDescriptor(
                type=descriptor.type,
                version=descriptor.version,
                format=descriptor.format,
                width=width,
                height=height,
                fps=descriptor.fps,
                max_frame_bytes=descriptor.max_frame_bytes,
            )
            await websocket.send_text(
                json.dumps(asdict(connection_descriptor), separators=(",", ":"))
            )
            client_end = asyncio.create_task(_wait_for_client_end(websocket))
            try:
                interval_s = 1.0 / fps
                clock = asyncio.get_running_loop()
                next_send_at = clock.time()
                sent_frame = False
                try:
                    while True:
                        snapshot = store.get()
                        if snapshot is not None:
                            async with asyncio.timeout(1.0):
                                await websocket.send_bytes(snapshot.jpeg)
                            sent_frame = True
                        elif sent_frame:
                            await websocket.close(
                                code=1012,
                                reason="camera source unavailable",
                            )
                            return
                        next_send_at += interval_s
                        now = clock.time()
                        if next_send_at < now - interval_s:
                            next_send_at = now
                        completed, _ = await asyncio.wait(
                            (client_end,),
                            timeout=max(0.0, next_send_at - now),
                        )
                        if completed:
                            close_request = client_end.result()
                            if close_request is not None:
                                await websocket.close(
                                    code=close_request[0],
                                    reason=close_request[1],
                                )
                            return
                except TimeoutError, WebSocketDisconnect, RuntimeError:
                    try:
                        await websocket.close()
                    except RuntimeError:
                        pass
            finally:
                client_end.cancel()
                await asyncio.gather(client_end, return_exceptions=True)
        finally:
            await connection_gate.release()
