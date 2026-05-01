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

import struct as _struct
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

_VOICE_ENGINE_VERSION = "0.6.0"

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
    # Phase 4 — transcript and recording (null until call completes)
    transcript_snippet: str | None = None
    livekit_recording_url: str | None = None


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


# ─── Phase 6: Post-call pipeline & report retrieval ─────────────


class ProcessAssessmentResult(BaseModel):
    session_id: str
    expert_review_url: str
    supervisor_review_url: str
    total_claims: int
    overall_confidence: float
    status: str


class AssessmentReportPayload(BaseModel):
    session_id: str
    candidate_name: str | None = None
    expert_review_token: str | None = None
    supervisor_review_token: str | None = None
    overall_confidence: float | None = None
    report_status: str | None = None
    claims_json: list[Any] = []
    report_generated_at: str | None = None
    expires_at: str | None = None
    expert_submitted_at: str | None = None
    expert_reviewer_name: str | None = None
    expert_reviewer_email: str | None = None
    supervisor_submitted_at: str | None = None
    supervisor_reviewer_name: str | None = None
    supervisor_reviewer_email: str | None = None
    reviews_completed_at: str | None = None


class ExpertReviewClaimItem(BaseModel):
    id: str
    expert_level: int = Field(ge=1, le=7)


class ExpertReviewSubmitPayload(BaseModel):
    reviewer_full_name: str = Field(min_length=1)
    reviewer_email: str
    claims: list[ExpertReviewClaimItem]


class SupervisorReviewClaimItem(BaseModel):
    id: str
    supervisor_decision: str = Field(pattern="^(verified|rejected)$")
    supervisor_comment: str = Field(min_length=1)


class SupervisorReviewSubmitPayload(BaseModel):
    reviewer_full_name: str = Field(min_length=1)
    reviewer_email: str
    claims: list[SupervisorReviewClaimItem]


class ReviewSaveResponse(BaseModel):
    session_id: str
    report_status: str
    reviews_completed_at: str | None = None
    claims: list[Any] = []


def _post_call_pipeline(request: Request) -> Any:
    pipeline = getattr(request.app.state, "post_call_pipeline", None)
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Post-call pipeline not configured")
    return pipeline


def _persistence(request: Request) -> IPersistence:
    p: IPersistence | None = getattr(request.app.state, "persistence", None)
    if p is None:
        raise HTTPException(status_code=503, detail="Voice engine not ready")
    return p


@router.post(
    "/api/v1/assessment/{session_id}/process",
    response_model=ProcessAssessmentResult,
    tags=["assessment"],
)
async def process_assessment(session_id: str, request: Request) -> ProcessAssessmentResult:
    """Trigger the post-call pipeline for a completed session.

    Extracts claims, maps to SFIA, generates dual review tokens, and
    updates the session status to 'processed'.
    """
    pipeline = _post_call_pipeline(request)
    try:
        report = await pipeline.process(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Pipeline processing failed") from exc

    return ProcessAssessmentResult(
        session_id=session_id,
        expert_review_url=report.expert_review_url,
        supervisor_review_url=report.supervisor_review_url,
        total_claims=report.total_claims,
        overall_confidence=report.overall_confidence,
        status="processed",
    )


@router.get(
    "/api/v1/assessment/{session_id}/report",
    response_model=AssessmentReportPayload,
    tags=["assessment"],
)
async def get_assessment_report(session_id: str, request: Request) -> AssessmentReportPayload:
    """Return the generated report for a session, or 404 if not yet processed."""
    persistence = _persistence(request)
    report_data = await persistence.get_report(session_id)
    if not report_data:
        raise HTTPException(status_code=404, detail="Report not found")
    return AssessmentReportPayload(**report_data)


@router.get(
    "/api/v1/review/expert/{token}",
    response_model=AssessmentReportPayload,
    tags=["review"],
)
async def get_expert_review(token: str, request: Request) -> AssessmentReportPayload:
    """Expert reviewer — fetch report by expert NanoID token."""
    persistence = _persistence(request)
    report_data = await persistence.get_report_by_expert_token(token)
    if not report_data:
        raise HTTPException(status_code=404, detail="Review not found or expired")
    return AssessmentReportPayload(**report_data)


@router.put(
    "/api/v1/review/expert/{token}",
    response_model=ReviewSaveResponse,
    tags=["review"],
)
async def submit_expert_review(
    token: str,
    payload: ExpertReviewSubmitPayload,
    request: Request,
) -> ReviewSaveResponse:
    """Expert reviewer — submit expert_level per claim."""
    persistence = _persistence(request)
    try:
        result = await persistence.save_expert_review(
            expert_review_token=token,
            reviewer_full_name=payload.reviewer_full_name,
            reviewer_email=payload.reviewer_email,
            claims_patch=[c.model_dump() for c in payload.claims],
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ReviewSaveResponse(**result)


@router.get(
    "/api/v1/review/supervisor/{token}",
    response_model=AssessmentReportPayload,
    tags=["review"],
)
async def get_supervisor_review(token: str, request: Request) -> AssessmentReportPayload:
    """Supervisor reviewer — fetch report by supervisor NanoID token."""
    persistence = _persistence(request)
    report_data = await persistence.get_report_by_supervisor_token(token)
    if not report_data:
        raise HTTPException(status_code=404, detail="Review not found or expired")
    return AssessmentReportPayload(**report_data)


@router.put(
    "/api/v1/review/supervisor/{token}",
    response_model=ReviewSaveResponse,
    tags=["review"],
)
async def submit_supervisor_review(
    token: str,
    payload: SupervisorReviewSubmitPayload,
    request: Request,
) -> ReviewSaveResponse:
    """Supervisor reviewer — submit supervisor_decision + supervisor_comment per claim."""
    persistence = _persistence(request)
    try:
        result = await persistence.save_supervisor_review(
            supervisor_review_token=token,
            reviewer_full_name=payload.reviewer_full_name,
            reviewer_email=payload.reviewer_email,
            claims_patch=[c.model_dump() for c in payload.claims],
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ReviewSaveResponse(**result)


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
        #diag {{
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
    <div id="diag"></div>

    <script>
        const url = '{url}';
        const token = '{token}';
        const roomName = '{room}';

        // On-screen event log — visible inside the iframe without DevTools
        function diag(msg) {{
            // console.log('[DIAG]', msg);
            const el = document.getElementById('diag');
            if (el) {{
                const line = document.createElement('div');
                line.textContent = new Date().toISOString().slice(11,23) + ' ' + msg;
                el.appendChild(line);
            }}
        }}

        document.getElementById('join-btn').addEventListener('click', async function () {{
            const btn = this;
            btn.disabled = true;
            btn.textContent = 'Connecting…';

            // Create and unlock AudioContext while user-gesture token is active.
            try {{
                window._audioCtx = new AudioContext();
                await window._audioCtx.resume();
                diag('AudioContext ' + window._audioCtx.state + ' sr=' + window._audioCtx.sampleRate);

                // Proof-of-life: 300 ms 440 Hz tone through the AudioContext.
                // If the user hears this beep, the iframe CAN output audio.
                const osc = window._audioCtx.createOscillator();
                const g   = window._audioCtx.createGain();
                osc.frequency.value = 440;
                g.gain.value = 0.25;
                osc.connect(g);
                g.connect(window._audioCtx.destination);
                osc.start();
                setTimeout(() => osc.stop(), 300);
                diag('TEST TONE — you should hear a short beep now');
            }} catch (e) {{
                diag('AudioContext ERROR: ' + e.message);
                window._audioCtx = null;
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

                const room = new window.LivekitClient.Room();

                // Unlock LiveKit's internal AudioContext NOW, while we are still
                // inside (or close to) the user-gesture call stack.  Calling this
                // BEFORE room.connect() means the AudioContext is already running
                // when trackSubscribed fires during connect(), so audio elements
                // created by track.attach() start playing immediately.
                try {{
                    if (typeof room.startAudio === 'function') {{
                        await room.startAudio();
                        diag('startAudio() ok (pre-connect)');
                    }}
                }} catch (e) {{
                    diag('startAudio() pre-connect error: ' + e.message);
                }}

                room.on('disconnected', async () => {{
                    diag('room disconnected — ending call');
                    document.getElementById('status').textContent = 'Call ended.';
                    // Disable microphone so the browser mic indicator turns off
                    try {{
                        await room.localParticipant.setMicrophoneEnabled(false);
                    }} catch (e) {{
                        // Ignore — participant may already be disconnected
                    }}
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
                        diag('skip dup ' + track.sid);
                        return;
                    }}
                    attachedSids.add(track.sid);

                    const mst = track.mediaStreamTrack;
                    diag('attach ' + track.sid
                        + ' readyState=' + (mst ? mst.readyState : '?')
                        + ' muted=' + (mst ? mst.muted : '?'));

                    // track.attach() creates an <audio> element managed by
                    // LiveKit's SDK and tied to its internal AudioContext.
                    // room.startAudio() was called pre-connect, so the
                    // AudioContext is already running when this fires.
                    const el = track.attach();
                    el.volume = 1.0;
                    document.body.appendChild(el);

                    el.play()
                        .then(() => diag('play() ok'))
                        .catch(e => diag('play() err: ' + e.message));

                    if (mst) {{
                        mst.addEventListener('unmute', () => {{
                            diag('* UNMUTED — server sending audio');
                            el.play().catch(() => {{}});
                        }});
                        mst.addEventListener('mute', () =>
                            diag('* MUTED — server stopped'));
                        mst.addEventListener('ended', () =>
                            diag('* ENDED'));
                    }}

                    // getStats() reads RTCP statistics directly — the only
                    // reliable audioLevel source for remote WebRTC tracks.
                    // (AnalyserNode always reads 0 for remote WebRTC in Chrome.)
                    let n = 0;
                    const iv = setInterval(async () => {{
                        n++;
                        let line = 'chk[' + n + ']'
                            + ' muted=' + (mst ? mst.muted : '?')
                            + ' time=' + el.currentTime.toFixed(1);
                        try {{
                            const pc = room.engine && room.engine.subscriber && room.engine.subscriber.pc;
                            if (pc) {{
                                const stats = await pc.getStats();
                                stats.forEach(function(s) {{
                                    if (s.type === 'inbound-rtp' && s.kind === 'audio') {{
                                        line += ' audioLevel=' + (s.audioLevel != null
                                            ? s.audioLevel.toFixed(4) : '?');
                                        line += ' totalSamples=' + (s.totalSamplesReceived || 0);
                                    }}
                                }});
                            }}
                        }} catch (e) {{ line += ' statsErr=' + e.message; }}
                        diag(line);
                        if (n >= 30) clearInterval(iv);
                    }}, 500);
                }}

                room.on('trackSubscribed', (track, pub, participant) => {{
                    const msg = 'trackSubscribed kind=' + track.kind + ' sid=' + track.sid + ' from=' + participant.identity;
                    diag(msg);
                    attachAudioTrack(track);
                }});

                room.on('trackPublished', (pub, participant) => {{
                    diag('trackPublished kind=' + pub.kind + ' participant=' + participant.identity);
                }});

                await room.connect(url, token, {{
                    name: 'Candidate',
                    autoSubscribe: true,
                }});

                const remoteCount = room.remoteParticipants.size;
                diag('connected — remoteParticipants=' + remoteCount);

                // Attach any tracks already published before we connected
                room.remoteParticipants.forEach(function(participant) {{
                    diag('existing participant: ' + participant.identity + ' tracks=' + participant.trackPublications.size);
                    participant.trackPublications.forEach(function(pub) {{
                        if (pub.track) {{
                            diag('existing track kind=' + pub.kind + ' isSubscribed=' + pub.isSubscribed);
                            attachAudioTrack(pub.track);
                        }}
                    }});
                }});

                // Re-call startAudio() post-connect — handles the case where
                // the bot joined after we connected and startAudio() was called
                // before any tracks existed (rare but possible).
                try {{
                    if (typeof room.startAudio === 'function') await room.startAudio();
                }} catch (e) {{ /* ignore */ }}

                document.getElementById('status').textContent = 'Connected • Microphone active';

                await room.localParticipant.setMicrophoneEnabled(true);
                diag('microphone enabled');
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


@router.get("/tts-test", tags=["tts"])
async def tts_test(
    request: Request,
    text: str = Query(
        default="Hello, this is a test of the text to speech provider.",
        max_length=500,
    ),
) -> Response:
    """Standalone TTS provider check — bypasses Pipecat and LiveKit entirely.

    Synthesises ``text`` using whichever TTS provider is active (controlled by
    the ``TTS_PROVIDER`` environment variable: ``elevenlabs`` or ``kokoro``).
    Returns a WAV file playable in any browser tab.

    Usage: GET /tts-test
           GET /tts-test?text=Say+something+custom
    """
    settings = request.app.state.settings
    provider: str = getattr(settings, "tts_provider", "elevenlabs")

    if provider == "kokoro":
        return await _tts_test_kokoro(settings, text)
    return await _tts_test_elevenlabs(settings, text)


async def _tts_test_elevenlabs(settings: Any, text: str) -> Response:
    import httpx

    if not getattr(settings, "elevenlabs_api_key", None):
        raise HTTPException(status_code=503, detail="ELEVENLABS_API_KEY not configured")

    voice_id = settings.elevenlabs_voice_id
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            url,
            headers={
                "xi-api-key": settings.elevenlabs_api_key,
                "Content-Type": "application/json",
                "Accept": "audio/pcm",
            },
            json={
                "text": text,
                "model_id": "eleven_turbo_v2",
                "output_format": "pcm_24000",
            },
        )
    if r.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"ElevenLabs error {r.status_code}: {r.text[:200]}",
        )

    return _pcm_to_wav_response(r.content, sample_rate=24000, filename="tts-test-elevenlabs.wav")


async def _tts_test_kokoro(settings: Any, text: str) -> Response:
    import httpx

    base_url: str = getattr(settings, "kokoro_tts_url", "").strip()
    if not base_url:
        raise HTTPException(status_code=503, detail="KOKORO_TTS_URL not configured")

    voice: str = getattr(settings, "kokoro_voice", "af_sky")
    sample_rate: int = getattr(settings, "kokoro_sample_rate", 24000)
    speech_url = base_url.rstrip("/") + "/v1/audio/speech"

    pcm_chunks: list[bytes] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        async with client.stream(
            "POST",
            speech_url,
            json={
                "model": "kokoro",
                "input": text,
                "voice": voice,
                "response_format": "pcm",
                "speed": 1.0,
            },
        ) as r:
            if r.status_code != 200:
                body = await r.aread()
                raise HTTPException(
                    status_code=502,
                    detail=f"Kokoro error {r.status_code}: {body[:200].decode(errors='replace')}",
                )
            async for chunk in r.aiter_bytes(4096):
                if chunk:
                    pcm_chunks.append(chunk)

    return _pcm_to_wav_response(b"".join(pcm_chunks), sample_rate=sample_rate, filename="tts-test-kokoro.wav")


def _pcm_to_wav_response(pcm: bytes, *, sample_rate: int, filename: str) -> Response:
    ch, bps = 1, 16
    header = _struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(pcm), b"WAVE",
        b"fmt ", 16, 1, ch, sample_rate,
        sample_rate * ch * bps // 8, ch * bps // 8, bps,
        b"data", len(pcm),
    )
    return Response(
        content=header + pcm,
        media_type="audio/wav",
        headers={"Content-Disposition": f"inline; filename={filename}"},
    )
