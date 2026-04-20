# Phase 2: Basic Voice Engine & Call Tracking

## Status
To Be Implemented

## Date
2026-04-18

## References
- PRD-001: Voice-AI Skills Assessment Platform
- ADR-001: Hexagonal Architecture (Ports & Adapters)
- ADR-004: Voice Engine Technology Decisions
- Phase 1: Foundation & Monorepo Scaffold (prerequisite)

## ⚠️ Blocking Note

**Phase 2 implementation is blocked until PRD-001 reach 🟢 Approved status.** Use `/check-prd PRD-001` to verify before starting.

---

## Objective

Establish a minimal, working voice engine that enables **candidate self-service assessments**:
1. Candidates fill in intake form (name, email, employee ID, phone number).
2. System places outbound calls via Daily's PSTN gateway (international numbers supported).
3. Bot "Noa" conducts a simple greeting conversation (introduces self, asks confirmation question, thanks candidate, ends call).
4. Call state is tracked in the database and displayed in real-time to the candidate.
5. Admin can view call history and status via read-only monitoring dashboard.

By the end of Phase 2, a candidate can self-initiate an assessment call via a web form and see real-time status updates (Dialling → Call In Progress → Interview Complete) with call duration.

**Key constraint**: No assessment workflow, no SFIA skill mapping, no claim extraction, no structured interview phases. This is a vertical slice focused on call infrastructure and candidate intake.

---

## 1. Deliverables

### 1.1 VoiceTransport Port (Interface)

**File:** `packages/core/src/ports/voice_transport.py`

Defines the interface (port) that all voice transport implementations must follow.

```python
from abc import ABC, abstractmethod
from typing import Optional

class CallConnection:
    session_id: str
    room_url: str
    started_at: datetime
    ended_at: Optional[datetime] = None

class CallConfig:
    session_id: str
    region: str  # e.g., "ap-southeast-2"

class VoiceTransport(ABC):
    @abstractmethod
    async def dial(self, phone_number: str, config: CallConfig) -> CallConnection:
        """Dial an outbound call. Returns connection object."""
        pass

    @abstractmethod
    async def hangup(self, session_id: str) -> None:
        """End an active call."""
        pass

    @abstractmethod
    async def get_call_duration(self, session_id: str) -> float:
        """Return call duration in seconds."""
        pass
```

**Rationale:** Per ADR-001, define ports before adapters. This interface is implemented by `DailyTransport` (real) and test adapters (mock).

---

### 1.2 DailyTransport Adapter

**File:** `packages/adapters/src/voice_transport/daily_transport.py`

Implements the `VoiceTransport` port using Pipecat's `DailyTransport` for real call handling.

**Key responsibilities:**
- Create a Daily room with recording enabled in `ap-southeast-2` (Sydney).
- Dial the candidate's phone number (international format) via Daily's PSTN gateway.
- Expose call lifecycle events (dialling, connected, disconnected, error).
- Capture call duration and recording URL post-call (stored in Daily's cloud indefinitely).
- Normalize phone numbers to international format (e.g., +61... or +44...).

**Implementation sketch:**

```python
from pipecat.transports.services.daily import DailyTransport, DailyParams
from core.ports.voice_transport import VoiceTransport, CallConfig, CallConnection
import httpx
import datetime

class DailyVoiceTransport(VoiceTransport):
    def __init__(self, api_key: str, persistence, api_url: str = "https://api.daily.co/v1"):
        self.api_key = api_key
        self.persistence = persistence  # IPersistence port
        self.api_url = api_url
        self.active_calls = {}  # Track ongoing calls by session_id

    async def dial(self, phone_number: str, config: CallConfig) -> CallConnection:
        """Dial an outbound call. Phone number normalized to +format."""
        # Normalize phone number if needed (remove spaces, add + prefix)
        normalized_phone = self._normalize_phone(phone_number)
        
        # Create Daily room
        room = await self._create_room(config)
        
        # Configure DailyTransport for Pipecat pipeline
        transport = DailyTransport(
            room_url=room.url,
            token=room.token,
            bot_name="Noa",
            params=DailyParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                transcription_enabled=True,
                vad_enabled=True,
            ),
        )
        
        # Register event handlers for state transitions
        @transport.event_handler("on_call_state_updated")
        async def on_call_state(state):
            await self._on_call_state_changed(config.session_id, state)
        
        @transport.event_handler("on_error")
        async def on_error(error):
            await self._on_call_error(config.session_id, error)
        
        # Dial the phone number
        await transport.dial(normalized_phone)
        
        # Create connection object
        connection = CallConnection(
            session_id=config.session_id,
            room_url=room.url,
            started_at=datetime.datetime.utcnow(),
        )
        self.active_calls[config.session_id] = (connection, transport)
        
        return connection

    async def hangup(self, session_id: str) -> None:
        """End an active call."""
        if session_id in self.active_calls:
            connection, transport = self.active_calls[session_id]
            await transport.leave_room()
            connection.ended_at = datetime.datetime.utcnow()
            del self.active_calls[session_id]

    async def get_call_duration(self, session_id: str) -> float:
        """Return call duration in seconds."""
        if session_id not in self.active_calls:
            return 0.0
        connection, _ = self.active_calls[session_id]
        end_time = connection.ended_at or datetime.datetime.utcnow()
        return (end_time - connection.started_at).total_seconds()

    def _normalize_phone(self, phone_number: str) -> str:
        """Normalize phone number to +format. E.g., '44 7700 900118' → '+447700900118'."""
        # Remove spaces, hyphens, parentheses
        cleaned = ''.join(c for c in phone_number if c.isdigit())
        # If no +, add it
        if not phone_number.startswith('+'):
            return f"+{cleaned}"
        return phone_number

    async def _create_room(self, config: CallConfig):
        """Create a Daily room with recording enabled."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_url}/rooms",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "properties": {
                        "enable_recording": "cloud",
                        "geo": config.region,
                        "exp": int(datetime.datetime.utcnow().timestamp()) + 7200,
                        "max_participants": 2,
                    }
                },
            )
            data = response.json()
            token = await self._create_token(data["name"])
            return type('Room', (), {
                'url': data["url"],
                'name': data["name"],
                'token': token,
                'recording_url': data.get("recording_url"),
            })()

    async def _create_token(self, room_name: str) -> str:
        """Create a Daily room token."""
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
        status_map = {
            "connecting": "dialling",
            "connected": "in_progress",
            "left": "completed",
        }
        await self.persistence.update_session_status(
            session_id, status_map.get(state, "failed")
        )

    async def _on_call_error(self, session_id: str, error: Exception) -> None:
        """Handle call errors. Store error reason in metadata."""
        await self.persistence.update_session_status(
            session_id, "failed", 
            metadata={"failureReason": str(error)}
        )
```

### 1.3 Simple Greeting Flow

**File:** `apps/voice-engine/src/flows/greeting_flow.py`

A minimal Pipecat Flows state machine with one state: introduce self, ask confirmation question, thank, and end.

**Flow description:**
1. Bot introduces itself: "Hi, I'm Noa from Resonant. I'm here to conduct a brief skills assessment interview."
2. Bot asks a simple confirmation question: "Can you hear me clearly?" (to confirm two-way communication and understanding).
3. Bot thanks the candidate: "Thank you for taking the time to do this assessment."
4. Bot ends the call gracefully.

**Implementation note:** The greeting flow uses a stub LLM provider for Phase 2 (hardcoded responses). Real Claude integration comes in Phase 4+.

```python
flow_config = {
    "initial_node": "greeting",
    "nodes": {
        "greeting": {
            "role_messages": [
                {
                    "role": "system",
                    "content": (
                        "You are Noa, an AI assessment interviewer from Resonant. "
                        "Your job is to: "
                        "1. Introduce yourself: 'Hi, I'm Noa from Resonant. I'm here to conduct a brief skills assessment interview.' "
                        "2. Ask a simple confirmation question: 'Can you hear me clearly?' "
                        "3. Thank them: 'Thank you for taking the time to do this assessment.' "
                        "4. End the call gracefully."
                    ),
                }
            ],
            "post_actions": [{"type": "end_conversation"}],
        }
    },
}
```

### 1.4 Persistence Port (Interface)

**File:** `packages/core/src/ports/persistence.py`

Defines the interface for candidate and session persistence.

```python
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from dataclasses import dataclass

@dataclass
class Candidate:
    email: str  # Unique identifier
    first_name: str
    last_name: str
    metadata: Dict[str, Any]  # Contains: {employee_id, ...}
    created_at: datetime

@dataclass
class AssessmentSession:
    id: str
    candidate_id: str  # FK to Candidate.email
    phone_number: str
    status: str  # pending, dialling, in_progress, completed, failed, cancelled
    metadata: Dict[str, Any]  # Contains: {failureReason, cancelledAt, ...}
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    recording_url: Optional[str] = None
    created_at: datetime

class Persistence(ABC):
    @abstractmethod
    async def get_or_create_candidate(
        self, email: str, first_name: str, last_name: str, employee_id: str
    ) -> Candidate:
        """Get candidate by email, or create if not exists."""
        pass

    @abstractmethod
    async def create_session(self, session: AssessmentSession) -> AssessmentSession:
        """Create a new assessment session."""
        pass

    @abstractmethod
    async def get_session(self, session_id: str) -> AssessmentSession:
        """Fetch session by ID."""
        pass

    @abstractmethod
    async def update_session_status(
        self, session_id: str, status: str, metadata: Optional[Dict] = None
    ) -> None:
        """Update session status and optionally merge metadata."""
        pass
```

---

### 1.5 Call Session Tracking

**File:** `packages/core/src/domain/services/call_manager.py`

Orchestrates call lifecycle and persists state. Uses VoiceTransport and Persistence ports (zero platform dependencies).

```python
import asyncio
import uuid
from datetime import datetime
from core.ports.voice_transport import VoiceTransport, CallConfig
from core.ports.persistence import Persistence, AssessmentSession

class CallManager:
    def __init__(self, voice_transport: VoiceTransport, persistence: Persistence):
        self.voice_transport = voice_transport
        self.persistence = persistence

    async def trigger_call(self, candidate_email: str, phone_number: str) -> str:
        """
        Trigger a call for a candidate. Returns session_id immediately.
        
        Steps:
        1. Lookup/create Candidate record by email.
        2. Create AssessmentSession with status "pending".
        3. Place call asynchronously via voice_transport.
        4. Return session_id to candidate (call is async, not blocking).
        """
        # Create session (status starts as "pending")
        session = AssessmentSession(
            id=str(uuid.uuid4()),
            candidate_id=candidate_email,
            phone_number=phone_number,
            status="pending",
            metadata={},
            created_at=datetime.utcnow(),
        )
        session = await self.persistence.create_session(session)

        # Place the call asynchronously (does not block response)
        asyncio.create_task(self._place_call(session.id, phone_number))

        return session.id

    async def _place_call(self, session_id: str, phone_number: str) -> None:
        """Place the call and handle lifecycle via event handlers."""
        try:
            # Update status to "dialling" before dialling
            await self.persistence.update_session_status(session_id, "dialling")
            
            # Dial the phone number (DailyTransport event handlers will update status)
            config = CallConfig(session_id=session_id, region="ap-southeast-2")
            await self.voice_transport.dial(phone_number, config)
            
        except Exception as e:
            # On error, update session to "failed" with reason
            await self.persistence.update_session_status(
                session_id, "failed",
                metadata={"failureReason": str(e)}
            )

    async def get_call_status(self, session_id: str) -> dict:
        """
        Fetch current call status and duration.
        
        Returns: {
            "session_id": "...",
            "status": "pending|dialling|in_progress|completed|failed|cancelled",
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

### 1.6 FastAPI Routes

**File:** `apps/voice-engine/src/api/routes.py`

Three endpoints: (1) create/lookup candidate from form, (2) trigger call, (3) get call status.

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, EmailStr
from typing import Optional

router = APIRouter(prefix="/api/v1")

# Step 01: Candidate intake form
class CandidateRequest(BaseModel):
    work_email: EmailStr = Field(..., description="Work email (unique identifier)")
    first_name: str = Field(..., min_length=1, description="First name")
    last_name: str = Field(..., min_length=1, description="Last name")
    employee_id: str = Field(..., min_length=1, description="Employee ID (for metadata matching)")

class CandidateResponse(BaseModel):
    candidate_id: str  # Will be the email for now
    work_email: str

@router.post("/assessment/candidate", response_model=CandidateResponse)
async def get_or_create_candidate(request: CandidateRequest):
    """Create or lookup a candidate by email. Idempotent."""
    try:
        candidate = await call_manager.persistence.get_or_create_candidate(
            email=request.work_email,
            first_name=request.first_name,
            last_name=request.last_name,
            employee_id=request.employee_id,
        )
        return CandidateResponse(candidate_id=candidate.email, work_email=candidate.email)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid form data. Please update and try again.")

# Step 02: Trigger call
class TriggerCallRequest(BaseModel):
    candidate_id: str = Field(..., description="Candidate email")
    phone_number: str = Field(..., description="Phone number (international format, e.g., +441234567890 or 44 1234 567890)")

class TriggerCallResponse(BaseModel):
    session_id: str
    status: str

@router.post("/assessment/trigger", response_model=TriggerCallResponse)
async def trigger_assessment_call(request: TriggerCallRequest):
    """Trigger a call to the candidate's phone number. Phone numbers accept international format."""
    try:
        session_id = await call_manager.trigger_call(
            candidate_email=request.candidate_id,
            phone_number=request.phone_number,
        )
        return TriggerCallResponse(session_id=session_id, status="pending")
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid form data. Please update and try again.")

# Status polling endpoint
class CallStatusResponse(BaseModel):
    session_id: str
    status: str
    duration_seconds: float
    started_at: Optional[str] = None
    ended_at: Optional[str] = None

@router.get("/assessment/{session_id}/status", response_model=CallStatusResponse)
async def get_assessment_status(session_id: str):
    """Get the status of an assessment call."""
    try:
        status_info = await call_manager.get_call_status(session_id)
        return CallStatusResponse(**status_info)
    except Exception:
        raise HTTPException(status_code=404, detail="Session not found")

# Admin: Read-only call history
class SessionSummary(BaseModel):
    session_id: str
    candidate_email: str
    phone_number: str
    status: str
    duration_seconds: float
    created_at: str

@router.get("/admin/sessions", response_model=list[SessionSummary])
async def list_sessions(
    status: Optional[str] = None,
    email: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = 50,
):
    """Admin endpoint: List sessions with optional filters (status, email, date range). Read-only."""
    try:
        sessions = await call_manager.persistence.query_sessions(
            status=status,
            candidate_email=email,
            created_after=since,
            created_before=until,
            limit=limit,
        )
        return [
            SessionSummary(
                session_id=s.id,
                candidate_email=s.candidate_id,
                phone_number=s.phone_number,
                status=s.status,
                duration_seconds=await call_manager.voice_transport.get_call_duration(s.id),
                created_at=s.created_at.isoformat(),
            )
            for s in sessions
        ]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
```

### 1.7 Candidate Portal UI (STEP 01 & 02)

**Design reference:** [Resonant Skills Interview mockup](/frontend/public/index.html)

**File:** `apps/web/src/app/page.tsx`

The candidate-facing assessment portal. Two-step flow: intake form (Step 01) → call state display (Step 02).

**Step 01: Intake Form**

```typescript
"use client";
import { useState } from "react";

export default function CandidatePortal() {
  const [step, setStep] = useState<"intake" | "calling">("intake");
  const [sessionId, setSessionId] = useState<string>("");
  
  // Step 01 form state
  const [formData, setFormData] = useState({
    first_name: "",
    last_name: "",
    work_email: "",
    employee_id: "",
    phone_number: "",
  });
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});

  // Client-side validation
  const validateForm = (): boolean => {
    const errors: Record<string, string> = {};
    
    if (!formData.first_name.trim()) errors.first_name = "Required";
    if (!formData.last_name.trim()) errors.last_name = "Required";
    if (!formData.work_email.includes("@")) errors.work_email = "Invalid email";
    if (!formData.employee_id.trim()) errors.employee_id = "Required";
    
    // Accept international phone formats: +1234567890 or 1234567890 or spaces/hyphens
    const phoneRegex = /^\+?[\d\s\-()]{10,}$/;
    if (!phoneRegex.test(formData.phone_number)) errors.phone_number = "Invalid phone";
    
    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleStartCall = async () => {
    if (!validateForm()) return;

    try {
      // Step 1: Create/lookup candidate
      const candidateRes = await fetch("/api/v1/assessment/candidate", {
        method: "POST",
        body: JSON.stringify({
          work_email: formData.work_email,
          first_name: formData.first_name,
          last_name: formData.last_name,
          employee_id: formData.employee_id,
        }),
      });
      if (!candidateRes.ok) throw new Error("Invalid form data. Please update and try again.");

      // Step 2: Trigger call
      const triggerRes = await fetch("/api/v1/assessment/trigger", {
        method: "POST",
        body: JSON.stringify({
          candidate_id: formData.work_email,
          phone_number: formData.phone_number,
        }),
      });
      if (!triggerRes.ok) throw new Error("Invalid form data. Please update and try again.");

      const { session_id } = await triggerRes.json();
      setSessionId(session_id);
      setStep("calling");
    } catch (error) {
      setFormErrors({ submit: error.message });
    }
  };

  if (step === "intake") {
    return (
      <div className="max-w-md mx-auto p-6 space-y-8">
        <div className="text-center">
          <h1 className="text-3xl font-bold">Your skills, <span className="italic text-teal-600">in your own words.</span></h1>
          <p className="text-gray-600 mt-4">A 20-minute phone conversation — no camera, no coding test</p>
        </div>

        <div className="space-y-6 bg-gray-50 p-6 rounded-lg">
          <h2 className="text-lg font-semibold">STEP 01 OF 02</h2>
          <h3 className="text-2xl font-bold">A few <span className="italic text-teal-600">quick details.</span></h3>
          <p className="text-gray-600">We use these to reach you and match your interview to the right review panel.</p>

          <div className="space-y-4">
            <input
              type="text"
              placeholder="Amara"
              className="w-full border rounded px-4 py-2"
              value={formData.first_name}
              onChange={(e) => setFormData({ ...formData, first_name: e.target.value })}
              title="FIRST NAME"
            />
            {formErrors.first_name && <p className="text-red-500 text-sm">{formErrors.first_name}</p>}

            <input
              type="text"
              placeholder="Okafor"
              className="w-full border rounded px-4 py-2"
              value={formData.last_name}
              onChange={(e) => setFormData({ ...formData, last_name: e.target.value })}
              title="LAST NAME"
            />
            {formErrors.last_name && <p className="text-red-500 text-sm">{formErrors.last_name}</p>}

            <input
              type="email"
              placeholder="amara@helixrobotics.com"
              className="w-full border rounded px-4 py-2"
              value={formData.work_email}
              onChange={(e) => setFormData({ ...formData, work_email: e.target.value })}
              title="WORK EMAIL"
            />
            {formErrors.work_email && <p className="text-red-500 text-sm">{formErrors.work_email}</p>}

            <input
              type="text"
              placeholder="HLX-00481"
              className="w-full border rounded px-4 py-2"
              value={formData.employee_id}
              onChange={(e) => setFormData({ ...formData, employee_id: e.target.value })}
              title="EMPLOYEE ID"
            />
            {formErrors.employee_id && <p className="text-red-500 text-sm">{formErrors.employee_id}</p>}

            <input
              type="tel"
              placeholder="+44 7700 900118"
              className="w-full border rounded px-4 py-2"
              value={formData.phone_number}
              onChange={(e) => setFormData({ ...formData, phone_number: e.target.value })}
              title="PHONE NUMBER"
            />
            {formErrors.phone_number && <p className="text-red-500 text-sm">{formErrors.phone_number}</p>}

            <button
              onClick={handleStartCall}
              className="w-full bg-black text-white py-3 rounded-full font-semibold hover:bg-gray-800"
            >
              Start the call 📞
            </button>

            <p className="text-gray-600 text-sm">
              By starting, you agree to the call being recorded and analysed for this assessment. Read our <a href="/privacy" className="text-teal-600 underline">privacy notice</a>.
            </p>
          </div>
        </div>
      </div>
    );
  }

  // Step 02: Call state display (see below)
  return <CallStateDisplay sessionId={sessionId} />;
}
```

**Step 02: Call State Display**

The `CallStateDisplay` component shows real-time call status with three possible states:

1. **Dialling**: "Your phone should ring in a moment. Answer when it does — caller ID will show Resonant · Noa."
2. **Call In Progress**: Waveform animation, timer (HH:MM format), "Relax and speak naturally. Noa will guide the conversation through three short phases — there are no wrong answers."
3. **Interview Complete**: Checkmark, "Thank you", "Your interview will now be analysed and reviewed before the results are available. You'll hear back by email, usually within 2 working days."

States are mapped as:
- `pending` or `dialling` → Display "DIALLING" label + "Your phone should ring in a moment..."
- `in_progress` → Display "CALL IN PROGRESS" label + waveform + timer
- `completed` → Display "INTERVIEW COMPLETE" label + checkmark + thank you message
- `failed` → Display "Failed" label + failure reason (if available)
- `cancelled` → Display "Cancelled" label

The UI polls `GET /api/v1/assessment/{session_id}/status` every 2 seconds to update state in real-time.

---

### 1.8 Admin Dashboard (Read-Only)

**File:** `apps/web/src/app/(dashboard)/page.tsx`

A lightweight read-only monitoring dashboard for admins to view recent assessment calls and their status.

**Key responsibilities:**
- Display list of recent sessions with: candidate email, phone number, status, duration, created_at
- Support filtering: by status (pending, dialling, in_progress, completed, failed, cancelled), by email, by date range
- Poll GET `/api/v1/admin/sessions` to fetch filtered list (paginated, max 50 per request)
- Display pagination controls for browsing sessions

**Implementation note:** Admin dashboard is read-only; no ability to trigger calls. The primary assessment workflow is candidate self-service via the candidate portal.

---

### 1.9 Database Schema

**Files:** `packages/database/prisma/schema.prisma` (Prisma schema, generated from Phase 1)

Phase 2 requires these tables:

**Candidate table:**
```prisma
model Candidate {
  email       String    @id  // Unique identifier
  first_name  String
  last_name   String
  metadata    Json      // Contains: { employee_id, ... }
  created_at  DateTime  @default(now())
  sessions    AssessmentSession[]
}
```

**AssessmentSession table:**
```prisma
model AssessmentSession {
  id            String    @id @default(cuid())
  candidate     Candidate @relation(fields: [candidate_id], references: [email])
  candidate_id  String
  phone_number  String    // Normalized to +format
  status        String    // pending, dialling, in_progress, completed, failed, cancelled
  metadata      Json      // Contains: { failureReason, cancelledAt, ... }
  recording_url String?   // URL to Daily's cloud recording (indefinite retention)
  started_at    DateTime?
  ended_at      DateTime?
  created_at    DateTime  @default(now())
  
  @@index([candidate_id])
  @@index([status])
  @@index([created_at])
}
```

**Notes:**
- No schema migrations required in Phase 2 (Phase 1 defines these tables).
- `metadata` JSON fields store optional/extensible data (failure reasons, cancellation timestamps, etc.).
- Recordings stored in Daily's cloud storage indefinitely.
- Email is the unique candidate identifier (not candidate_id).

---

## 2. Data Flow

### Candidate Self-Service Assessment Initiation

```
Candidate Portal (/page.tsx)
    │
    ├─ STEP 01: Intake form
    │   ├─ Enter: FIRST NAME, LAST NAME, WORK EMAIL, EMPLOYEE ID, PHONE NUMBER
    │   ├─ Client-side validation (all mandatory, email format, phone format)
    │   │
    │   ▼
    │  POST /api/v1/assessment/candidate
    │   ├─ Create or lookup Candidate by email
    │   ├─ Store metadata: { employee_id, ... }
    │   │
    │   ▼
    │  POST /api/v1/assessment/trigger
    │   ├─ CallManager.trigger_call(email, phone_number)
    │   ├─ Create AssessmentSession (status: pending)
    │   ├─ Return session_id to candidate
    │   │
    │   └─ Place call asynchronously (does not block)
    │
    ├─ STEP 02: Call state display
    │   ├─ Poll GET /api/v1/assessment/{session_id}/status every 2 seconds
    │   ├─ Display state transitions:
    │   │   • pending/dialling → "DIALLING"
    │   │   • in_progress → "CALL IN PROGRESS" (with timer)
    │   │   • completed → "INTERVIEW COMPLETE" (with checkmark)
    │   │   • failed → "Failed" (with reason)
    │   │   • cancelled → "Cancelled"
    │   │
    │   ▼
    │  DailyTransport.dial()
    │   ├─ Normalize phone number to +format
    │   ├─ Create Daily room (ap-southeast-2)
    │   ├─ Register event handlers
    │   ├─ Dial phone number
    │   ├─ Update session status → "dialling"
    │   │
    │   ▼
    │  DailyTransport connected
    │   ├─ Update session status → "in_progress"
    │   │
    │   ▼
    │  Pipecat Pipeline (STT stub → LLM stub → TTS stub)
    │   ├─ Bot "Noa" introduces self: "Hi, I'm Noa from Resonant..."
    │   ├─ Bot asks confirmation: "Can you hear me clearly?"
    │   ├─ Candidate responds
    │   ├─ Bot thanks: "Thank you for taking the time..."
    │   ├─ Bot ends call gracefully
    │   │
    │   ▼
    │  DailyTransport disconnect event
    │   ├─ Update session status → "completed"
    │   ├─ Calculate call duration
    │   ├─ Store recording URL (Daily cloud)
    │   │
    │   ▼
    │  Candidate UI displays "INTERVIEW COMPLETE"
    │   └─ "Your interview will now be analysed and reviewed...
    │      You'll hear back by email, usually within 2 working days."

Admin Dashboard (/dashboard/page.tsx)
    │
    └─ Poll GET /api/v1/admin/sessions (with filters)
       └─ Display read-only call history + status
```

### Error Handling

- **Form validation error**: Display "Invalid form data. Please update and try again." to candidate
- **Call trigger error**: Display "Failed" state with failure reason (if available)
- **Cancelled**: Candidate clicks Cancel during Step 02 → Update session status to "cancelled"

---

## 3. Acceptance Criteria

### Ports & Architecture
- [ ] `IVoiceTransport` port defined in `packages/core/src/ports/voice_transport.py`
- [ ] `IPersistence` port defined in `packages/core/src/ports/persistence.py`
- [ ] `DailyVoiceTransport` adapter implements `IVoiceTransport` in `packages/adapters/`
- [ ] `PostgresAdapter` implements `IPersistence` in `packages/adapters/`
- [ ] `CallManager` in `packages/core/src/domain/` has zero platform dependencies (uses ports only)
- [ ] ESLint/type checking prevents `packages/core` from importing adapters

### Database
- [ ] `Candidate` table with email (unique), first_name, last_name, metadata JSON
- [ ] `AssessmentSession` table with phone_number, status, metadata JSON (failureReason, cancelledAt)
- [ ] Recordings stored in Daily's cloud storage indefinitely
- [ ] Database indexes on candidate_id, status, created_at

### Voice Transport (DailyTransport)
- [ ] DailyTransport creates rooms in `ap-southeast-2` (Sydney) with recording enabled
- [ ] DailyTransport accepts international phone numbers (+format and formats with spaces/hyphens)
- [ ] DailyTransport normalizes phone numbers to +format (e.g., "44 7700 900118" → "+447700900118")
- [ ] DailyTransport registers event handlers for call state changes (connecting, connected, left, error)
- [ ] DailyTransport captures recording URL from Daily API post-call
- [ ] Call duration calculated correctly (endTime - startTime, or currentTime if ongoing)

### Call Management
- [ ] CallManager.trigger_call(email, phone) creates session with status "pending"
- [ ] CallManager places call asynchronously (returns session_id immediately)
- [ ] Call status transitions: pending → dialling → in_progress → completed (or failed/cancelled)
- [ ] Error handling: call failures store failureReason in session metadata

### Candidate Intake Form (Step 01)
- [ ] Form fields: FIRST NAME, LAST NAME, WORK EMAIL, EMPLOYEE ID, PHONE NUMBER (all mandatory)
- [ ] Client-side validation: email format, phone format (international), all fields required
- [ ] Error message: "Invalid form data. Please update and try again."
- [ ] POST `/api/v1/assessment/candidate` creates or looks up candidate by email
- [ ] POST `/api/v1/assessment/trigger` accepts (candidate_id, phone_number), triggers call

### Candidate Call State Display (Step 02)
- [ ] Candidate UI is the default page (`/`)
- [ ] Candidate UI shows form (Step 01) then call state display (Step 02)
- [ ] Call state displays with labels:
  - [ ] pending/dialling → "DIALLING" + "Your phone should ring in a moment..."
  - [ ] in_progress → "CALL IN PROGRESS" + waveform + timer (HH:MM format)
  - [ ] completed → "INTERVIEW COMPLETE" + checkmark + "Thank you" message
  - [ ] failed → "Failed" + failure reason (if available)
  - [ ] cancelled → "Cancelled"
- [ ] Candidate UI polls GET `/api/v1/assessment/{session_id}/status` every 2 seconds
- [ ] Candidate UI displays real-time state transitions
- [ ] Candidate can click Cancel to stop waiting for call

### Greeting Flow
- [ ] Bot name is "Noa"
- [ ] Caller ID displays "Resonant · Noa"
- [ ] Greeting flow: introduce (name + company) → ask confirmation question ("Can you hear me clearly?") → thank → end call
- [ ] Greeting flow uses stub LLM provider (hardcoded responses for Phase 2)
- [ ] Call completes gracefully without crashes

### Admin Dashboard (Read-Only)
- [ ] GET `/api/v1/admin/sessions` returns paginated list of sessions
- [ ] Admin can filter by: status, candidate email, date range (since/until)
- [ ] Admin dashboard displays: session_id, candidate_email, phone_number, status, duration, created_at
- [ ] Admin dashboard is read-only (no ability to trigger calls)

### Testing
- [ ] Unit tests: CallManager (session creation, async call placement, status transitions)
- [ ] Unit tests: Phone number normalization
- [ ] Integration test: form submission → candidate creation → call trigger → status polling
- [ ] Mock VoiceTransport and Persistence adapters for testing (no real Daily/database needed)

### Documentation
- [ ] Local setup guide in `/docs/guides/local-setup.md`: Dependencies, environment variables, database initialization, Prisma migrations, Daily API credentials, running voice engine and web app locally
- [ ] Railway deployment guide in `/docs/guides/deployed-setup.md`: Deploying to Railway (environment variables, Postgres setup, service configuration), Daily region configuration, API endpoint documentation, monitoring/health checks

---

## 4. Out of Scope (Phase 2)

- **Structured assessment interview**: Multi-phase discovery/evidence gathering (deferred to Phase 3+)
- **Structured consent flow**: Verbal consent capture and framework explanation (deferred to Phase 3)
- **SFIA framework**: SFIA-specific questions, interjection rules, skill mapping (deferred to Phase 4+)
- **Claim extraction**: Post-call LLM analysis, claim mapping, confidence scoring (deferred to Phase 5+)
- **RAG/Knowledge base**: Vector store, framework definitions, dynamic skill retrieval (deferred to Phase 5)
- **SME review portal**: Claim approval/adjustment workflow (deferred to Phase 7)
- **Transcript processing**: Speech-to-text output, segmentation by phase, transcription (recording URL only in Phase 2)
- **Real STT/TTS/LLM providers**: Deepgram, ElevenLabs, Claude APIs (stub implementations in Phase 2; real providers in Phase 3+)
- **Multi-language support**: English only in Phase 2
- **Email domain whitelisting**: Candidate filtering by domain (deferred to Phase 3; admin toggle configuration)
- **Privacy notice implementation**: Privacy policy link (deferred to Phase 3)

---

## 5. Build Sequence (Recommended Implementation Order)

Follow this sequence to minimize blockers and enable parallel work:

1. **Database schema** (Candidate, AssessmentSession tables with metadata JSON)
   - Define Prisma models with indexes
   - Generate Prisma client
   - ⏱️ ~2 hours

2. **Ports** (interfaces in `packages/core/src/ports/`)
   - `IVoiceTransport` interface
   - `IPersistence` interface
   - ⏱️ ~1 hour

3. **Domain logic** (CallManager in `packages/core/src/domain/services/`)
   - `CallManager.trigger_call()`, `get_call_status()`
   - Uses ports, zero platform dependencies
   - ⏱️ ~2 hours

4. **Adapters** (implementations in `packages/adapters/src/`)
   - `DailyTransport` (DailyVoiceTransport adapter)
   - `PostgresAdapter` (Persistence implementation)
   - ⏱️ ~6 hours (Daily integration is most complex)

5. **API routes** (FastAPI in voice-engine and Next.js in web)
   - POST `/assessment/candidate`
   - POST `/assessment/trigger`
   - GET `/assessment/{session_id}/status`
   - GET `/admin/sessions`
   - ⏱️ ~3 hours

6. **Candidate portal UI** (Step 01 form + Step 02 call display)
   - Form validation, styling
   - Status display, polling, state transitions
   - ⏱️ ~4 hours

7. **Admin dashboard** (read-only monitoring)
   - List sessions, filters, pagination
   - ⏱️ ~2 hours

8. **Tests** (unit + integration)
   - Mock adapters
   - CallManager tests
   - End-to-end test (form → call → status)
   - ⏱️ ~4 hours

**Total estimated effort: ~24 hours (3 days)**

**Parallelization opportunities:**
- Steps 3 & 4 can start before steps 5 (domain before API)
- Steps 6 & 7 can start once step 5 API routes are defined (can mock backend)
- Step 8 can start as soon as step 4 adapters are stubbed

---

## 6. Dependencies

**Upstream blockers:**
- 🔴 **Phase 1 complete**: Monorepo structure, Prisma setup, database schema foundation
- 🔴 **PRD-001 & PRD-002 Approved**: Required before implementation starts
- 🟡 **Daily API account & credentials**: API key needed for DailyTransport testing
- 🟡 **STT/TTS/LLM provider selection**: Currently using stubs; real providers needed in Phase 3

**Within Phase 2:**
- Database schema must exist before adapters
- Ports must be defined before adapters
- Adapters must be implemented before API routes
- API routes must be implemented before UI can be tested against real backend

---

## 7. Estimated Complexity by Component

| Component | Effort | Notes |
|-----------|--------|-------|
| **Ports (IVoiceTransport, IPersistence)** | Low (1h) | Interface definitions only |
| **DailyTransport adapter** | Medium (6h) | HTTP API calls, event handling, connection lifecycle, phone normalization |
| **Persistence adapter (PostgresAdapter)** | Low (2h) | CRUD operations, metadata JSON handling |
| **CallManager** | Low (2h) | Orchestration, async call placement |
| **Greeting flow (Pipecat)** | Low (2h) | Single state, hardcoded responses |
| **FastAPI routes** | Low (3h) | Four endpoints, error handling |
| **Candidate UI (form + call state)** | Medium (4h) | Form validation, real-time polling, state transitions, styling per design |
| **Admin dashboard** | Low (2h) | Read-only list, filtering, pagination |
| **Database schema** | Low (2h) | Prisma models, indexes, metadata JSON |
| **Tests (unit + integration)** | Medium (4h) | Mock adapters, end-to-end flow |

**Total: ~24–30 hours (3–4 days)**

---

## 8. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|-----------|
| Daily PSTN dial-out latency for international numbers | Medium | Medium | Test with real numbers early; Daily has regional PoPs; use Sydney region for AU numbers |
| Phone number parsing/normalization edge cases | Medium | Low | Test common formats (+format, spaces, hyphens); use international phone validation library (e.g., `phonenumbers`) |
| Event handler timing (status updates lag behind actual call state) | Low | Low | Use polling from candidate UI (every 2 seconds acceptable for MVP); DailyTransport event handlers update DB in background |
| STT/TTS/LLM providers not finalized | High | Medium | Use stub implementations (hardcoded responses) in Phase 2; swap real providers in Phase 3+ |
| Call duration calculation (missing start/end timestamps) | Low | Low | Capture timestamps in DailyTransport when creating/closing connection; validate in tests |
| Recording URL not available immediately post-call | Low | Low | Daily API docs confirm URL available in disconnect event; store async if needed |
| Candidate form validation bypassed on API side | Low | Medium | Validate all fields on POST `/assessment/candidate` and `/assessment/trigger` endpoints |
| Candidate abandons form during intake | Low | Low | Acceptable in Phase 2 (no charge/consequences); Session stays "pending" indefinitely (can be cleaned up later) |
| Database constraint violations (duplicate candidate email, cascade deletes) | Low | Medium | Use database constraints (UNIQUE on email); test cascade behavior |

---

## 9. Notes

- **Minimal vertical slice**: Phase 2 is intentionally minimal to establish call infrastructure. Assessment workflow, claim extraction, and SME review are deferred.
- **Candidate-driven, not admin-driven**: The primary workflow is candidate self-service intake form → call trigger (not admin dashboard triggering).
- **Stub providers for Phase 2**: STT, TTS, and LLM use hardcoded/placeholder implementations. Real integrations (Deepgram, ElevenLabs, Claude) come in Phase 3+.
- **Design reference**: The candidate UI must match the mockup provided in the Resonant design file (Step 01 form labels, Step 02 call state labels).
- **Recordings stored indefinitely**: All calls recorded in Daily's cloud storage indefinitely for compliance/audit (Phase 3 may add retention policy).
- **Admin dashboard is secondary**: Read-only monitoring for ops/support; primary user journey is candidate self-service.
- **By end of Phase 2**: A candidate can fill in the form, receive a call, see real-time status, complete the call, and see a completion message.

---

## 10. Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-04-19 | AI Skills Assessor Team | **Comprehensive refinement via /doc-refiner**: (1) Reframe from admin-triggered to candidate self-service intake form. (2) Add two-endpoint API design: POST `/assessment/candidate` + POST `/assessment/trigger`. (3) Document exact form field labels from Resonant mockup: FIRST NAME, LAST NAME, WORK EMAIL, EMPLOYEE ID, PHONE NUMBER. (4) Document Step 02 call state display labels: DIALLING, CALL IN PROGRESS, INTERVIEW COMPLETE, Failed, Cancelled. (5) Define IVoiceTransport and IPersistence ports per ADR-001. (6) Add explicit build sequence with effort estimates. (7) Update greeting flow: simple introduction ("Hi, I'm Noa from Resonant") + confirmation question ("Can you hear me clearly?") + thank you + end. (8) Add phone number normalization for international format. (9) Document database schema with metadata JSON fields (failureReason, cancelledAt). (10) Add admin read-only dashboard endpoint GET `/api/v1/admin/sessions`. (11) Add blocking note: Phase 2 blocked until PRD-001 and PRD-002 are Approved. (12) Expand acceptance criteria with 40+ specific, testable items. (13) Expand risks table with 8 identified risks and mitigations. |
| 2026-04-18 | AI Skills Assessor Team | Initial draft |
