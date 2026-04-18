# Phase 2: Basic Voice Engine & Call Tracking

## Status
To Be Implemented

## Date
2026-04-18

## References
- PRD-001: Voice-AI Skills Assessment Platform
- ADR-001: Hexagonal Architecture (Ports & Adapters)
- Phase 1: Foundation & Monorepo Scaffold (prerequisite)

## Objective

Establish a minimal, working voice engine that can:
1. Place outbound calls to Australian phone numbers via Daily.
2. Conduct a simple greeting conversation (bot introduces itself, thanks candidate, ends call).
3. Track call state and duration in the database.
4. Expose admin endpoints to trigger calls and view status.

By the end of Phase 2, a user can trigger an assessment call from the admin dashboard and see real-time status updates (dialling → in-progress → completed) with call duration.

**Key constraint**: No assessment workflow, no SFIA skill mapping, no claim extraction. This is a vertical slice focused on call infrastructure.

---

## 1. Deliverables

### 1.1 DailyTransport Adapter (Simplified)

**File:** `apps/voice-engine/src/adapters/daily_transport.py`

Implements the `VoiceTransport` port using Pipecat's `DailyTransport` for basic call handling.

**Key responsibilities:**
- Create a Daily room with recording enabled in `ap-southeast-2` (Sydney).
- Dial the candidate's Australian phone number via Daily's PSTN gateway.
- Expose call lifecycle events (dialling, connected, disconnected, error).
- Capture call duration and recording URL post-call.

**Implementation sketch:**

```python
from pipecat.transports.services.daily import DailyTransport, DailyParams
from domain.ports.voice_transport import VoiceTransport
from domain.models.assessment import CallConfig, CallConnection

class DailyVoiceTransport(VoiceTransport):
    def __init__(self, api_key: str, api_url: str = "https://api.daily.co/v1"):
        self.api_key = api_key
        self.api_url = api_url
        self.active_calls = {}  # Track ongoing calls by session_id

    async def dial(self, phone_number: str, config: CallConfig) -> CallConnection:
        """Dial an outbound call."""
        # 1. Create Daily room
        room = await self._create_room(config)
        
        # 2. Configure DailyTransport
        transport = DailyTransport(
            room_url=room.url,
            token=room.token,
            bot_name="AI Assessment Bot",
            params=DailyParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                transcription_enabled=True,  # For transcript logging
                vad_enabled=True,
                vad_analyzer=SileroVADAnalyzer(),
            ),
        )
        
        # 3. Register event handlers
        @transport.event_handler("on_call_state_updated")
        async def on_call_state(state):
            await self._on_call_state_changed(config.session_id, state)
        
        @transport.event_handler("on_error")
        async def on_error(error):
            await self._on_call_error(config.session_id, error)
        
        # 4. Dial the phone number
        await transport.dial(phone_number)
        
        # 5. Return connection object
        connection = CallConnection(
            session_id=config.session_id,
            room_url=room.url,
            transport=transport,
            started_at=datetime.utcnow(),
        )
        self.active_calls[config.session_id] = connection
        
        return connection

    async def hangup(self, session_id: str) -> None:
        """End an active call."""
        connection = self.active_calls.get(session_id)
        if connection:
            await connection.transport.leave_room()
            connection.ended_at = datetime.utcnow()
            del self.active_calls[session_id]

    async def get_call_duration(self, session_id: str) -> float:
        """Return call duration in seconds."""
        connection = self.active_calls.get(session_id)
        if not connection:
            return 0.0
        end_time = connection.ended_at or datetime.utcnow()
        return (end_time - connection.started_at).total_seconds()

    async def _create_room(self, config: CallConfig) -> DailyRoom:
        """Create a Daily room with recording enabled in Sydney region."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_url}/rooms",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "properties": {
                        "enable_recording": "cloud",
                        "enable_transcription": True,
                        "geo": "ap-southeast-2",
                        "exp": int(time.time()) + 7200,  # 2-hour expiry
                        "max_participants": 2,
                    }
                },
            )
            data = response.json()
            return DailyRoom(
                url=data["url"],
                name=data["name"],
                token=await self._create_token(data["name"]),
            )

    async def _create_token(self, room_name: str) -> str:
        """Create a token for joining the room."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_url}/tokens",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"properties": {"room_name": room_name}},
            )
            data = response.json()
            return data["token"]

    async def _on_call_state_changed(self, session_id: str, state: str) -> None:
        """Handle call state transitions."""
        # States: connecting, connected, left, error
        # Map to our session statuses: dialling, in_progress, completed
        status_map = {
            "connecting": "dialling",
            "connected": "in_progress",
            "left": "completed",
        }
        await self.persistence.update_session_status(
            session_id, status_map.get(state, "failed")
        )

    async def _on_call_error(self, session_id: str, error: Exception) -> None:
        """Handle call errors."""
        await self.persistence.update_session_status(session_id, "failed")
```

### 1.2 Simple Greeting Flow

**File:** `apps/voice-engine/src/flows/greeting_flow.py`

A minimal Pipecat Flows state machine with just one state: greet and end.

```python
from pipecat_flows import FlowManager, FlowConfig

flow_config: FlowConfig = {
    "initial_node": "greeting",
    "nodes": {
        "greeting": {
            "role_messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a friendly AI assistant. "
                        "Introduce yourself as an AI assessment bot. "
                        "Thank the person for their time, and let them know the call will now end. "
                        "Be warm and professional."
                    ),
                }
            ],
            "task_messages": [
                {
                    "role": "system",
                    "content": "After greeting, end the call using the end_call function.",
                }
            ],
            "functions": [
                {
                    "type": "function",
                    "function": {
                        "name": "end_call",
                        "description": "End the call gracefully.",
                        "parameters": {"type": "object", "properties": {}},
                        "handler": "handle_end_call",
                    },
                }
            ],
            "post_actions": [{"type": "end_conversation"}],
        }
    },
}
```

### 1.3 Call Session Tracking

**File:** `apps/voice-engine/src/domain/services/call_manager.py`

Orchestrates call lifecycle and persists state.

```python
from domain.ports.voice_transport import VoiceTransport
from domain.ports.persistence import Persistence
from domain.models.assessment import AssessmentSession, CallConfig

class CallManager:
    def __init__(
        self,
        voice_transport: VoiceTransport,
        persistence: Persistence,
    ):
        self.voice_transport = voice_transport
        self.persistence = persistence

    async def initiate_call(self, phone_number: str, candidate_id: str) -> str:
        """
        Initiate a call and return the session ID.
        
        Steps:
        1. Create a session in the database with status "pending".
        2. Update status to "dialling" as the call is placed.
        3. DailyTransport updates status to "in_progress" when connected.
        4. Returns immediately with session ID (call is async).
        """
        # Create session
        session = AssessmentSession(
            candidate_id=candidate_id,
            status="pending",
            framework_type="sfia-9",  # Default; not used in basic phase
        )
        session = await self.persistence.create_session(session)

        # Place the call (async; does not block)
        asyncio.create_task(self._place_call(session.id, phone_number))

        return session.id

    async def _place_call(self, session_id: str, phone_number: str) -> None:
        """Place the call and handle lifecycle."""
        try:
            config = CallConfig(session_id=session_id, region="ap-southeast-2")
            connection = await self.voice_transport.dial(phone_number, config)
            
            # Update to "in_progress" (DailyTransport will also update this)
            await self.persistence.update_session(session_id, status="in_progress")
            
            # Wait for call to end (the transport's event handler will end it)
            # For now, we just let the connection live until it's disconnected.
            
        except Exception as e:
            await self.persistence.update_session(session_id, status="failed")

    async def get_call_status(self, session_id: str) -> dict:
        """
        Fetch current call status and duration.
        
        Returns:
        {
            "session_id": "...",
            "status": "pending|dialling|in_progress|completed|failed",
            "duration_seconds": 42.5,
            "started_at": "2026-04-18T10:35:00Z",
            "ended_at": "2026-04-18T10:36:30Z",
        }
        """
        session = await self.persistence.get_session(session_id)
        duration = await self.voice_transport.get_call_duration(session_id)
        
        return {
            "session_id": session.id,
            "status": session.status,
            "duration_seconds": duration,
            "started_at": session.started_at,
            "ended_at": session.ended_at,
        }
```

### 1.4 FastAPI Routes

**File:** `apps/voice-engine/src/api/routes.py`

Two minimal endpoints for the admin dashboard.

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import re

router = APIRouter(prefix="/api/v1")

class TriggerRequest(BaseModel):
    phone_number: str = Field(..., pattern=r"^\+61\d{9}$", description="Australian number")
    candidate_id: str

class TriggerResponse(BaseModel):
    session_id: str
    status: str

class CallStatusResponse(BaseModel):
    session_id: str
    status: str
    duration_seconds: float
    started_at: str | None
    ended_at: str | None

@router.post("/assessment/trigger", response_model=TriggerResponse)
async def trigger_assessment(request: TriggerRequest):
    """Trigger a call to an Australian phone number."""
    try:
        session_id = await call_manager.initiate_call(
            phone_number=request.phone_number,
            candidate_id=request.candidate_id,
        )
        return TriggerResponse(session_id=session_id, status="pending")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/assessment/{session_id}/status", response_model=CallStatusResponse)
async def get_assessment_status(session_id: str):
    """Get the status of an assessment call."""
    try:
        status_info = await call_manager.get_call_status(session_id)
        return CallStatusResponse(**status_info)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")
```

### 1.5 Admin Dashboard - Call Tracking UI

**File:** `apps/web/src/app/(dashboard)/page.tsx`

Minimal dashboard showing triggered calls and their status.

```typescript
"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function AdminDashboard() {
  const [phoneNumber, setPhoneNumber] = useState("");
  const [candidateId, setCandidateId] = useState("");
  const [calls, setCalls] = useState<CallRecord[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  interface CallRecord {
    session_id: string;
    status: string;
    duration_seconds: number;
    started_at: string | null;
    ended_at: string | null;
  }

  const handleTriggerCall = async () => {
    setIsLoading(true);
    try {
      const response = await fetch("/api/assessment/trigger", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone_number: phoneNumber, candidate_id: candidateId }),
      });
      const data = await response.json();
      setCalls([...calls, data]);
      setPhoneNumber("");
      setCandidateId("");
    } catch (error) {
      console.error("Failed to trigger call", error);
    } finally {
      setIsLoading(false);
    }
  };

  // Poll for status updates
  useEffect(() => {
    const pollInterval = setInterval(async () => {
      const updatedCalls = await Promise.all(
        calls.map(async (call) => {
          const response = await fetch(`/api/assessment/${call.session_id}/status`);
          return response.json();
        })
      );
      setCalls(updatedCalls);
    }, 2000); // Poll every 2 seconds

    return () => clearInterval(pollInterval);
  }, [calls]);

  const statusColor = (status: string) => {
    const colors: Record<string, string> = {
      pending: "bg-gray-100",
      dialling: "bg-yellow-100",
      in_progress: "bg-blue-100",
      completed: "bg-green-100",
      failed: "bg-red-100",
    };
    return colors[status] || "bg-gray-100";
  };

  return (
    <div className="space-y-6 p-6">
      <h1 className="text-3xl font-bold">Admin Dashboard</h1>

      <Card>
        <CardHeader>
          <CardTitle>Trigger Assessment Call</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Input
            placeholder="+61XXXXXXXXX"
            value={phoneNumber}
            onChange={(e) => setPhoneNumber(e.target.value)}
          />
          <Input
            placeholder="Candidate ID"
            value={candidateId}
            onChange={(e) => setCandidateId(e.target.value)}
          />
          <Button onClick={handleTriggerCall} disabled={isLoading}>
            {isLoading ? "Dialling..." : "Trigger Call"}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Active Calls</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {calls.length === 0 ? (
              <p className="text-gray-500">No calls yet</p>
            ) : (
              calls.map((call) => (
                <div
                  key={call.session_id}
                  className={`p-3 rounded ${statusColor(call.status)}`}
                >
                  <div className="font-mono text-sm">{call.session_id}</div>
                  <div className="text-sm">
                    Status: <strong>{call.status}</strong> | Duration: <strong>{call.duration_seconds.toFixed(1)}s</strong>
                  </div>
                </div>
              ))
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
```

### 1.6 Candidate UI

**Design reference:** [index.html](https://api.anthropic.com/v1/design/h/eYopn19yj1-13nKkVwDedg?open_file=index.html)

**File:** `apps/web/src/app/page.tsx`

The default landing page of the candidate portal — what candidates see when they first access the application. Implements the UI as specified in the design file linked above.

**Key responsibilities:**
- Display the candidate-facing assessment portal home screen.
- Show contextual information (what to expect, how the assessment works).
- Poll `GET /api/v1/assessment/{session_id}/status` to reflect real-time call state (waiting → dialling → in-progress → completed/failed).
- Present a clean, professional experience appropriate for an assessment context.

**Implementation note:** Implement `index.html` from the design reference exactly, translating the design into a Next.js page component. Use Tailwind CSS classes to match the design's visual style.

---

### 1.7 Updated Database Schema

**File:** `packages/database/src/schema/assessment-sessions.ts`

Minimal schema for tracking calls (no claim-related fields yet).

```typescript
import { pgTable, uuid, text, timestamp } from "drizzle-orm/pg-core";

export const assessmentSessions = pgTable("assessment_sessions", {
  id: uuid("id").defaultRandom().primaryKey(),
  candidateId: uuid("candidate_id").notNull(),
  status: text("status", {
    enum: ["pending", "dialling", "in_progress", "completed", "failed"],
  })
    .notNull()
    .default("pending"),
  frameworkType: text("framework_type").notNull().default("sfia-9"),
  dailyRoomUrl: text("daily_room_url"),
  recordingUrl: text("recording_url"),
  startedAt: timestamp("started_at"),
  endedAt: timestamp("ended_at"),
  createdAt: timestamp("created_at").defaultNow().notNull(),
});
```

---

## 2. Data Flow

```
Admin Dashboard
    │
    ├─ Enter phone + candidate ID
    │
    ▼
POST /api/v1/assessment/trigger
    │
    ▼
CallManager.initiate_call()
    ├─ Create session (status: pending)
    ├─ Place call async via DailyTransport
    │
    ▼
DailyTransport.dial()
    ├─ Create Daily room (Sydney region)
    ├─ Register event handlers
    ├─ Dial phone number
    └─ Update session status → "dialling" → "in_progress"
    │
    ▼
Pipecat Pipeline (STT → LLM → TTS)
    ├─ Bot greets candidate
    ├─ Candidate responds (optional)
    ├─ Bot thanks and ends call
    │
    ▼
DailyTransport disconnect event
    ├─ Update session status → "completed"
    ├─ Record call duration
    └─ Store recording URL
    │
    ▼
Admin Dashboard polls GET /api/v1/assessment/{session_id}/status
    └─ Display call status + duration in real-time
```

---

## 3. Acceptance Criteria

- [ ] DailyTransport adapter creates rooms in `ap-southeast-2` with recording enabled.
- [ ] DailyTransport can dial an Australian +61 number.
- [ ] DailyTransport registers event handlers for call state changes (dialling, connected, left, error).
- [ ] CallManager creates a session in the database before dialling.
- [ ] CallManager initiates call asynchronously and returns session ID immediately.
- [ ] Call status updates propagate to the database (pending → dialling → in_progress → completed/failed).
- [ ] Call duration is calculated and stored (or retrieved from ongoing call).
- [ ] POST `/api/v1/assessment/trigger` accepts phone number and candidate ID, validates Australian format.
- [ ] GET `/api/v1/assessment/{session_id}/status` returns session status and duration.
- [ ] Admin dashboard displays triggered calls with real-time status updates.
- [ ] Admin dashboard shows call duration in seconds.
- [ ] Candidate UI renders as per the design at the linked reference (`index.html`).
- [ ] Candidate UI is the default page of the candidate portal (`/`).
- [ ] Candidate UI polls the backend and reflects real-time call state transitions (waiting → dialling → in-progress → completed/failed).
- [ ] Greeting flow starts when call connects and completes without error.
- [ ] Call can be placed, connected, and ended gracefully without crashes.
- [ ] Recording URL is captured and stored in the database.
- [ ] Unit tests for CallManager (session creation, status transitions).
- [ ] Integration test: trigger call → see status updates in dashboard.

---

## 4. Out of Scope (Phase 2)

- Assessment workflow (skill discovery, evidence gathering, summary).
- SFIA framework questions or interjection logic.
- Claim extraction or skill mapping.
- RAG/Knowledge base queries.
- SME review portal.
- Transcript segmentation by conversation phase.
- Multi-language or accent-specific tuning.
- Call recording transcription (recording URL only, no post-processing).

---

## 5. Dependencies

- **Phase 1**: Monorepo structure, database schema, port interfaces, shared types.
- **External**: Daily API key, STT provider (Deepgram/Azure/Google), TTS provider (ElevenLabs/Google/Azure).

---

## 6. Estimated Complexity

- **DailyTransport adapter**: Medium — HTTP API calls, event handling, connection lifecycle.
- **CallManager**: Low — basic session CRUD and orchestration.
- **Greeting flow**: Low — single Pipecat Flows state.
- **FastAPI routes**: Low — two simple endpoints.
- **Dashboard UI**: Low — form + polling list.
- **Candidate UI**: Low — status display with polling; implement from design reference.
- **Database schema**: Low — minimal tables.
- **Integration testing**: Medium — need real Daily account + phone number.

---

## 7. Risks

| Risk | Mitigation |
|------|------------|
| Daily PSTN dial-out latency for AU numbers | Test with real AU numbers early; Daily has Sydney PoP |
| Event handler timing (status updates lag) | Use polling from admin dashboard; acceptable for MVP |
| STT/TTS provider selection not final | Stub with placeholder providers; swap in Phase 3 |
| Call duration calculation (started_at/ended_at not set in time) | Use DailyTransport timestamps; validate in tests |
| Recording URL not available immediately | Daily docs confirm URL available post-call; handle async |

---

## 8. Notes

- This phase is intentionally minimal to provide a working vertical slice: trigger → dial → track → display.
- Assessment logic (skill discovery, evidence gathering, interjection) moves to **Phase 3**.
- RAG/Knowledge base integration moves to **Phase 4**.
- Claim extraction and SME review are **Phase 5–6**.
- By the end of Phase 2, a user can visually confirm that calls are being placed and tracked.
