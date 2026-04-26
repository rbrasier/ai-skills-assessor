"""FastAPI routers for the voice engine.

Phase 2 surface:

  GET  /health
  POST /api/v1/assessment/candidate
  POST /api/v1/assessment/trigger
  GET  /api/v1/assessment/{session_id}/status
  POST /api/v1/assessment/{session_id}/cancel
  GET  /api/v1/admin/sessions

The route handlers read the singleton :class:`CallManager` from
``request.app.state.call_manager`` which is wired in
``apps/voice-engine/src/main.py``. Tests may override
``app.state.call_manager`` with an in-memory manager.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr, Field

from src.domain.ports.persistence import IPersistence
from src.domain.services.call_manager import (
    CallManager,
    CallManagerError,
    SessionNotFoundError,
)
from src.domain.utils.phone import InvalidPhoneNumberError

_VOICE_ENGINE_VERSION = "0.4.2"

router = APIRouter()

_INVALID_FORM = "Invalid form data. Please update and try again."


def _manager(request: Request) -> CallManager:
    manager: CallManager | None = getattr(request.app.state, "call_manager", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="Voice engine not ready")
    return manager


# ─── Health ──────────────────────────────────────────────────────────


class HealthPayload(BaseModel):
    status: str
    version: str
    database: str


@router.get("/health", tags=["meta"], response_model=HealthPayload)
async def health(request: Request, response: Response) -> HealthPayload:
    """Deep health check.

    Returns HTTP 200 only when the voice engine *and* its persistence
    backend are reachable. Railway's healthcheck uses this to roll back
    deploys with an unreachable database — see Phase 3 / ADR-006.
    """

    persistence: IPersistence | None = getattr(
        request.app.state, "persistence", None
    )

    db_status = "unknown"
    if persistence is not None:
        try:
            db_status = "ok" if await persistence.ping() else "unreachable"
        except Exception:  # pragma: no cover — ping must not raise, but
            # still treat surprises as unhealthy.
            db_status = "unreachable"

    if db_status != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthPayload(
            status="degraded",
            version=_VOICE_ENGINE_VERSION,
            database=db_status,
        )

    return HealthPayload(
        status="ok",
        version=_VOICE_ENGINE_VERSION,
        database=db_status,
    )


# ─── Candidate intake (Step 01) ──────────────────────────────────────


class CandidateRequestPayload(BaseModel):
    work_email: EmailStr = Field(..., description="Work email — unique candidate id")
    first_name: str = Field(..., min_length=1, max_length=255)
    last_name: str = Field(..., min_length=1, max_length=255)
    employee_id: str = Field(..., min_length=1, max_length=64)


class CandidateResponsePayload(BaseModel):
    candidate_id: str
    work_email: str
    first_name: str
    last_name: str


@router.post(
    "/api/v1/assessment/candidate",
    response_model=CandidateResponsePayload,
    tags=["assessment"],
)
async def create_candidate(
    payload: CandidateRequestPayload,
    request: Request,
) -> CandidateResponsePayload:
    manager = _manager(request)
    try:
        candidate = await manager.get_or_create_candidate(
            email=str(payload.work_email),
            first_name=payload.first_name.strip(),
            last_name=payload.last_name.strip(),
            employee_id=payload.employee_id.strip(),
        )
    except CallManagerError as exc:
        raise HTTPException(status_code=400, detail=_INVALID_FORM) from exc

    return CandidateResponsePayload(
        candidate_id=candidate.email,
        work_email=candidate.email,
        first_name=candidate.first_name,
        last_name=candidate.last_name,
    )


# ─── Trigger a call (Step 02 start) ──────────────────────────────────


class TriggerCallPayload(BaseModel):
    candidate_id: str = Field(..., description="Candidate email")
    phone_number: str | None = Field(default=None, min_length=1, max_length=32)
    dialing_method: str | None = Field(default=None, description="'browser' or 'pstn'")


class TriggerCallResult(BaseModel):
    session_id: str
    status: str


@router.post(
    "/api/v1/assessment/trigger",
    response_model=TriggerCallResult,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["assessment"],
)
async def trigger_assessment_call(
    payload: TriggerCallPayload,
    request: Request,
) -> TriggerCallResult:
    manager = _manager(request)

    # Phone number is required for PSTN dialing
    if payload.dialing_method != "browser" and not payload.phone_number:
        raise HTTPException(status_code=400, detail=_INVALID_FORM)

    try:
        session = await manager.trigger_call(
            candidate_email=payload.candidate_id,
            phone_number=payload.phone_number or "",
            dialing_method=payload.dialing_method,
        )
    except InvalidPhoneNumberError as exc:
        raise HTTPException(status_code=400, detail=_INVALID_FORM) from exc
    except CallManagerError as exc:
        raise HTTPException(status_code=400, detail=_INVALID_FORM) from exc

    return TriggerCallResult(
        session_id=session.id,
        status=session.status.value,
    )


# ─── Status polling (Step 02) ────────────────────────────────────────


class CallStatusPayload(BaseModel):
    session_id: str
    status: str
    duration_seconds: float
    started_at: str | None = None
    ended_at: str | None = None
    failure_reason: str | None = None
    dialing_method: str | None = None
    browser_join_url: str | None = None
    livekit_room_name: str | None = None
    livekit_participant_token: str | None = None
    livekit_url: str | None = None


@router.get(
    "/api/v1/assessment/{session_id}/status",
    response_model=CallStatusPayload,
    tags=["assessment"],
)
async def get_call_status(session_id: str, request: Request) -> CallStatusPayload:
    manager = _manager(request)
    try:
        data = await manager.get_call_status(session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc
    return CallStatusPayload(**data)


@router.post(
    "/api/v1/assessment/{session_id}/cancel",
    response_model=CallStatusPayload,
    tags=["assessment"],
)
async def cancel_call(session_id: str, request: Request) -> CallStatusPayload:
    manager = _manager(request)
    try:
        await manager.cancel_call(session_id)
        data = await manager.get_call_status(session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc
    return CallStatusPayload(**data)


# ─── Admin listing ───────────────────────────────────────────────────


class SessionSummaryPayload(BaseModel):
    session_id: str
    candidate_email: str
    phone_number: str
    status: str
    duration_seconds: float
    created_at: str
    started_at: str | None = None
    ended_at: str | None = None


@router.get(
    "/api/v1/admin/sessions",
    response_model=list[SessionSummaryPayload],
    tags=["admin"],
)
async def list_admin_sessions(
    request: Request,
    status_: str | None = Query(default=None, alias="status"),
    email: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[SessionSummaryPayload]:
    manager = _manager(request)

    def _parse(ts: str | None) -> datetime | None:
        if ts is None or not ts.strip():
            return None
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail="`since`/`until` must be ISO-8601 timestamps",
            ) from exc

    created_after = _parse(since)
    created_before = _parse(until)

    summaries: list[dict[str, Any]] = await manager.list_sessions(
        status=status_,
        candidate_email=email,
        created_after=created_after,
        created_before=created_before,
        limit=limit,
        offset=offset,
    )
    return [SessionSummaryPayload(**s) for s in summaries]


# ─── LiveKit join page ───────────────────────────────────────────


@router.get("/join", response_class=HTMLResponse, tags=["livekit"])
async def livekit_join_page(
    url: str = Query(..., description="LiveKit WebSocket URL"),
    token: str = Query(..., description="LiveKit participant token"),
    room: str = Query(..., description="LiveKit room name"),
) -> str:
    """Serve a simple HTML page to join a LiveKit room.

    This page can be used as LIVEKIT_MEET_URL when self-hosting
    the join page locally (e.g., LIVEKIT_MEET_URL=http://localhost:8000/join).
    """
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Interview Call</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            margin: 0;
            padding: 8px 0;
            background: transparent;
            color: #1b1a17;
            font-size: 13px;
            display: flex;
            flex-direction: column;
            align-items: center;
        }}
        #join-btn {{
            background: #1b1a17;
            color: #fff;
            border: none;
            border-radius: 6px;
            padding: 10px 28px;
            font-size: 13px;
            font-family: inherit;
            cursor: pointer;
            letter-spacing: 0.01em;
        }}
        #join-btn:hover {{ background: #333; }}
        #join-btn:disabled {{ opacity: 0.5; cursor: default; }}
        #status {{
            padding: 6px 0;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            text-align: center;
            font-style: italic;
            display: none;
        }}
        .error {{
            color: #c0392b;
            font-size: 12px;
            margin-top: 6px;
            text-align: center;
        }}
    </style>
</head>
<body>
    <!-- Button is required: browser AudioContext stays suspended until a user
         gesture occurs inside this frame. Connecting automatically (no click)
         means room.startAudio() and audioEl.play() are both rejected silently,
         so the candidate hears nothing even though TTS is generated server-side. -->
    <button id="join-btn">Join Interview</button>
    <div id="status">Loading…</div>

    <script>
        const url = '{url}';
        const token = '{token}';
        const roomName = '{room}';

        document.getElementById('join-btn').addEventListener('click', async function () {{
            const btn = this;
            btn.disabled = true;
            btn.textContent = 'Connecting…';

            // Resume AudioContext synchronously while the user-gesture token is
            // still active. This must happen before any awaited network calls.
            try {{
                const ac = new AudioContext();
                await ac.resume();
                console.log('[LK] AudioContext state after resume:', ac.state);
            }} catch (e) {{
                console.warn('[LK] AudioContext resume failed:', e.message);
            }}

            btn.style.display = 'none';
            document.getElementById('status').style.display = 'block';

            await connectToRoom();
        }});

        function loadLiveKitSDK() {{
            return new Promise((resolve, reject) => {{
                const script = document.createElement('script');
                script.src = 'https://unpkg.com/livekit-client@latest/dist/livekit-client.umd.js';
                script.onload = () => {{
                    console.log('[LK] SDK loaded');
                    if (window.LivekitClient) {{
                        resolve();
                    }} else {{
                        reject(new Error('LiveKit SDK did not load properly'));
                    }}
                }};
                script.onerror = (err) => {{
                    console.error('[LK] Failed to load SDK from CDN:', err);
                    reject(new Error('Failed to load LiveKit SDK'));
                }};
                document.head.appendChild(script);
            }});
        }}

        async function connectToRoom() {{
            try {{
                document.getElementById('status').textContent = 'Loading LiveKit SDK…';
                await loadLiveKitSDK();

                if (!window.LivekitClient || !window.LivekitClient.Room) {{
                    console.error('[LK] LivekitClient object:', window.LivekitClient);
                    throw new Error('LiveKit SDK did not load properly. Please refresh the page.');
                }}

                document.getElementById('status').textContent = 'Connecting to interview…';

                const room = new window.LivekitClient.Room({{
                    adaptiveStream: true,
                    dynacast: true,
                }});

                room.on('disconnected', () => {{
                    document.getElementById('status').textContent = 'Call ended.';
                }});
                room.on('reconnecting', () => {{
                    document.getElementById('status').textContent = 'Reconnecting…';
                }});
                room.on('reconnected', () => {{
                    document.getElementById('status').textContent = 'Connected • Interview in progress';
                }});

                const attachedSids = new Set();

                function attachAudioTrack(track) {{
                    if (track.kind !== 'audio') return;
                    if (attachedSids.has(track.sid)) {{
                        console.log('[LK] skip duplicate attach for', track.sid);
                        return;
                    }}
                    attachedSids.add(track.sid);
                    console.log('[LK] attaching audio track', track.sid,
                        'muted:', track.mediaStreamTrack ? track.mediaStreamTrack.muted : 'n/a');

                    const stream = new MediaStream([track.mediaStreamTrack]);
                    const audioEl = document.createElement('audio');
                    audioEl.srcObject = stream;
                    audioEl.autoplay = true;
                    audioEl.volume = 1.0;
                    document.body.appendChild(audioEl);

                    const tryPlay = () => {{
                        audioEl.play()
                            .then(() => console.log('[LK] play() resolved, readyState:', audioEl.readyState))
                            .catch(e => console.warn('[LK] play() rejected:', e.name, e.message));
                    }};
                    tryPlay();

                    // Re-attempt when track unmutes (first audio frames arrive)
                    track.mediaStreamTrack.addEventListener('unmute', () => {{
                        console.log('[LK] track unmuted — re-triggering play');
                        tryPlay();
                    }});
                }}

                room.on('trackSubscribed', (track, pub, participant) => {{
                    console.log('[LK] trackSubscribed kind=%s sid=%s participant=%s',
                        track.kind, track.sid, participant.identity);
                    attachAudioTrack(track);
                }});

                await room.connect(url, token, {{
                    name: 'Candidate',
                    autoSubscribe: true,
                }});

                console.log('[LK] connected — remoteParticipants=%d', room.remoteParticipants.size);

                // Ask LiveKit SDK to resume its internal AudioContext too
                try {{
                    if (typeof room.startAudio === 'function') await room.startAudio();
                }} catch (e) {{
                    console.warn('[LK] startAudio threw:', e.message);
                }}

                document.getElementById('status').textContent = 'Connected • Microphone active';

                await room.localParticipant.setMicrophoneEnabled(true);
                console.log('[LK] microphone enabled');
            }} catch (error) {{
                // Show retry button on failure
                const btn = document.getElementById('join-btn');
                if (btn) {{
                    btn.style.display = 'block';
                    btn.disabled = false;
                    btn.textContent = 'Retry';
                }}
                document.getElementById('status').style.display = 'none';
                const errorDiv = document.createElement('div');
                errorDiv.className = 'error';
                errorDiv.textContent = 'Failed to connect: ' + error.message;
                document.body.appendChild(errorDiv);
                console.error('[LK] Connection error:', error);
            }}
        }}
    </script>
</body>
</html>
"""
