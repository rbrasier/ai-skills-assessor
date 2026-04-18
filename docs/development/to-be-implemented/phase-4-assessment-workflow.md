# Phase 4: Assessment Workflow & Interjection

## Status
To Be Implemented

## Date
2026-04-18

## References
- PRD-002: Assessment Interview Workflow
- ADR-004: Voice Engine Technology Decisions
- Phase 1: Foundation & Monorepo Scaffold (prerequisite)
- Phase 2: Basic Voice Engine & Call Tracking (prerequisite)
- Phase 3: Infrastructure Deployment (prerequisite)

## Objective

Build the SFIA assessment conversation flow on top of the basic voice engine from Phase 2. Implement the SFIAFlowController state machine (discovery → evidence gathering → summary), the 60-second interjection mechanism, and transcript persistence with phase metadata. By the end of this phase, the system can conduct a structured multi-phase assessment conversation and persist detailed transcripts with speaker turns and phase labels.

---

## 1. Deliverables

### 1.1 DailyTransport Adapter

**File:** `apps/voice-engine/src/adapters/daily_transport.py`

Implements the `VoiceTransport` port using Pipecat's `DailyTransport`.

**Key responsibilities:**
- Create a Daily room with recording and transcription enabled.
- Configure the room for `ap-southeast-2` (Sydney) region.
- Dial the candidate's Australian phone number via Daily's SIP/PSTN gateway.
- Expose call lifecycle events (connected, disconnected, error).
- Handle call recording URLs post-call.

**Configuration:**

```python
from pipecat.transports.services.daily import DailyTransport, DailyParams

class DailyVoiceTransport(VoiceTransport):
    def __init__(self, api_key: str, api_url: str = "https://api.daily.co/v1"):
        self.api_key = api_key
        self.api_url = api_url

    async def dial(self, phone_number: str, config: CallConfig) -> CallConnection:
        # 1. Create Daily room with Sydney region
        room = await self._create_room(config)
        
        # 2. Configure DailyTransport
        transport = DailyTransport(
            room_url=room.url,
            token=room.token,
            bot_name="SFIA Assessment Bot",
            params=DailyParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                transcription_enabled=True,
                vad_enabled=True,
                vad_analyzer=SileroVADAnalyzer(),
            ),
        )
        
        # 3. Dial the phone number
        await transport.dial(phone_number)
        
        return CallConnection(
            session_id=config.session_id,
            room_url=room.url,
            transport=transport,
        )

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
                        "exp": int(time.time()) + 3600,  # 1 hour expiry
                        "max_participants": 2,
                        "enable_chat": False,
                    }
                },
            )
            data = response.json()
            return DailyRoom(url=data["url"], name=data["name"], token=await self._create_token(data["name"]))
```

### 1.2 SFIAFlowController (Pipecat Flows State Machine)

**File:** `apps/voice-engine/src/flows/sfia_flow_controller.py`

The core conversation state machine using Pipecat Flows.

**States:**

```
┌──────────────┐
│ Introduction │  Consent + explain process
└──────┬───────┘
       │ candidate consents
       ▼
┌──────────────────┐
│ SkillDiscovery   │  "Tell me about your IT career and key responsibilities"
└──────┬───────────┘
       │ skills identified (LLM extracts skill mentions)
       ▼
┌──────────────────────┐
│ EvidenceGathering    │  Per-skill deep dive with RAG context
│ (loops per skill)    │  "Can you give me a specific example of..."
└──────┬───────────────┘
       │ all skills explored OR time limit
       ▼
┌──────────────────┐
│ Summary          │  Recap key points
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ Closing          │  Thank candidate, explain next steps
└──────────────────┘
```

**Flow Definition:**

```python
from pipecat_flows import FlowManager, FlowConfig, FlowResult

flow_config: FlowConfig = {
    "initial_node": "introduction",
    "nodes": {
        "introduction": {
            "role_messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a friendly, professional AI skills assessor. "
                        "Introduce yourself, explain you'll be conducting a skills assessment "
                        "based on the SFIA framework, and ask for verbal consent to proceed "
                        "and to record the call."
                    ),
                }
            ],
            "task_messages": [
                {
                    "role": "system",
                    "content": (
                        "After the candidate consents, transition to skill_discovery. "
                        "If they decline, transition to closing with a polite goodbye."
                    ),
                }
            ],
            "functions": [
                {
                    "type": "function",
                    "function": {
                        "name": "transition_to_skill_discovery",
                        "description": "Candidate has consented. Move to skill discovery.",
                        "parameters": {"type": "object", "properties": {}},
                        "transition_to": "skill_discovery",
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "transition_to_closing_declined",
                        "description": "Candidate declined. End the call politely.",
                        "parameters": {"type": "object", "properties": {}},
                        "transition_to": "closing",
                    },
                },
            ],
        },
        "skill_discovery": {
            "role_messages": [
                {
                    "role": "system",
                    "content": (
                        "Ask the candidate to describe their current role, key responsibilities, "
                        "and areas of IT expertise. Listen for mentions of skills that map to "
                        "SFIA categories. Keep the conversation natural and encouraging."
                    ),
                }
            ],
            "task_messages": [
                {
                    "role": "system",
                    "content": (
                        "Once you have identified 2-5 key skill areas, transition to "
                        "evidence_gathering with the identified skills. Use the "
                        "set_identified_skills function to record them."
                    ),
                }
            ],
            "functions": [
                {
                    "type": "function",
                    "function": {
                        "name": "set_identified_skills",
                        "description": "Record the SFIA skills identified from the candidate's description.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "skills": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "skill_code": {"type": "string"},
                                            "skill_name": {"type": "string"},
                                            "estimated_level": {"type": "integer"},
                                        },
                                    },
                                }
                            },
                            "required": ["skills"],
                        },
                        "handler": "handle_identified_skills",
                        "transition_to": "evidence_gathering",
                    },
                },
            ],
        },
        "evidence_gathering": {
            "role_messages": [
                {
                    "role": "system",
                    "content": (
                        "You are now probing for specific evidence. "
                        "For each identified skill, ask the candidate for concrete examples "
                        "that demonstrate their level of responsibility. "
                        "Focus on: Autonomy, Influence, Complexity, and Knowledge. "
                        "\n\n"
                        "DYNAMIC RAG CONTEXT (injected at runtime):\n"
                        "{rag_context}"
                    ),
                }
            ],
            "task_messages": [
                {
                    "role": "system",
                    "content": (
                        "Once you have gathered sufficient evidence for all identified skills "
                        "(at least one concrete example per skill), transition to summary. "
                        "If the candidate cannot provide evidence for a skill, note it and move on."
                    ),
                }
            ],
            "functions": [
                {
                    "type": "function",
                    "function": {
                        "name": "record_evidence",
                        "description": "Record a piece of evidence for a specific skill.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "skill_code": {"type": "string"},
                                "evidence_summary": {"type": "string"},
                                "estimated_level": {"type": "integer"},
                            },
                            "required": ["skill_code", "evidence_summary"],
                        },
                        "handler": "handle_evidence_recorded",
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "transition_to_summary",
                        "description": "Sufficient evidence gathered. Move to summary.",
                        "parameters": {"type": "object", "properties": {}},
                        "transition_to": "summary",
                    },
                },
            ],
        },
        "summary": {
            "role_messages": [
                {
                    "role": "system",
                    "content": (
                        "Summarise the key skills and evidence discussed. "
                        "Thank the candidate for their time. "
                        "Explain that an assessment report will be generated and reviewed "
                        "by a subject matter expert."
                    ),
                }
            ],
            "task_messages": [
                {
                    "role": "system",
                    "content": "After delivering the summary, transition to closing.",
                }
            ],
            "functions": [
                {
                    "type": "function",
                    "function": {
                        "name": "transition_to_closing",
                        "description": "Summary complete. Close the call.",
                        "parameters": {"type": "object", "properties": {}},
                        "transition_to": "closing",
                    },
                },
            ],
        },
        "closing": {
            "role_messages": [
                {
                    "role": "system",
                    "content": (
                        "Thank the candidate warmly. Let them know they will receive "
                        "information about the assessment outcome. Say goodbye."
                    ),
                }
            ],
            "task_messages": [],
            "functions": [
                {
                    "type": "function",
                    "function": {
                        "name": "end_call",
                        "description": "Call is complete. End the session.",
                        "parameters": {"type": "object", "properties": {}},
                        "handler": "handle_end_call",
                    },
                },
            ],
            "post_actions": [{"type": "end_conversation"}],
        },
    },
}
```

### 1.3 The Interjection Mechanism

**File:** `apps/voice-engine/src/flows/interjection_monitor.py`

Implements the "1-per-call Force Check" rule.

**Logic:**
1. A 60-second timer starts when the user begins speaking (`UserStartedSpeaking` event).
2. The timer resets each time the LLM detects a verifiable "work claim" in the user's speech.
3. If 60 seconds elapse without a detected claim, the bot injects a high-priority `TTSFrame` to redirect.
4. This interjection can only fire **once per call** (flag-guarded).

```python
import asyncio
from pipecat.frames.frames import TTSFrame
from pipecat.processors.frame_processor import FrameProcessor

class InterjectionMonitor(FrameProcessor):
    INTERJECTION_TIMEOUT = 60.0  # seconds
    INTERJECTION_MESSAGE = (
        "I appreciate you sharing that context. To help me assess your skills accurately, "
        "could you give me a specific example of a project or task where you applied "
        "these skills? For instance, what was the situation, what did you do, "
        "and what was the outcome?"
    )

    def __init__(self):
        super().__init__()
        self._timer_task: asyncio.Task | None = None
        self._has_interjected = False
        self._claim_detected_since_last_reset = False

    async def on_user_started_speaking(self):
        """Reset timer when user starts speaking."""
        if self._has_interjected:
            return
        self._cancel_timer()
        self._claim_detected_since_last_reset = False
        self._timer_task = asyncio.create_task(self._interjection_countdown())

    async def on_user_stopped_speaking(self):
        """Keep timer running — user might resume without a claim."""
        pass

    def mark_claim_detected(self):
        """Called by the LLM processor when a verifiable claim is detected."""
        self._claim_detected_since_last_reset = True
        self._cancel_timer()

    async def _interjection_countdown(self):
        try:
            await asyncio.sleep(self.INTERJECTION_TIMEOUT)
            if not self._claim_detected_since_last_reset and not self._has_interjected:
                await self._interject()
        except asyncio.CancelledError:
            pass

    async def _interject(self):
        """Inject a high-priority TTS frame to redirect the candidate."""
        self._has_interjected = True
        frame = TTSFrame(text=self.INTERJECTION_MESSAGE)
        await self.push_frame(frame, priority=True)

    def _cancel_timer(self):
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()
            self._timer_task = None
```

### 1.4 Pipeline Assembly

**File:** `apps/voice-engine/src/domain/services/assessment_orchestrator.py`

Wires the Pipecat pipeline together.

```python
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask, PipelineParams
from pipecat.services.deepgram import DeepgramSTTService
from pipecat.services.openai import OpenAILLMService
from pipecat.services.elevenlabs import ElevenLabsTTSService
from pipecat_flows import FlowManager

class AssessmentOrchestrator:
    def __init__(
        self,
        voice_transport: VoiceTransport,
        knowledge_base: KnowledgeBase,
        persistence: Persistence,
        config: VoiceEngineConfig,
    ):
        self.voice_transport = voice_transport
        self.knowledge_base = knowledge_base
        self.persistence = persistence
        self.config = config

    async def run_assessment(self, phone_number: str, candidate_id: str) -> str:
        """Run a full assessment call. Returns the session ID."""
        session = await self._create_session(candidate_id)
        
        connection = await self.voice_transport.dial(
            phone_number,
            CallConfig(session_id=session.id, region="ap-southeast-2"),
        )

        stt = DeepgramSTTService(api_key=self.config.deepgram_api_key)
        llm = OpenAILLMService(api_key=self.config.openai_api_key, model="gpt-4o")
        tts = ElevenLabsTTSService(
            api_key=self.config.elevenlabs_api_key,
            voice_id=self.config.elevenlabs_voice_id,
        )

        interjection_monitor = InterjectionMonitor()
        
        messages = []
        context = OpenAILLMContext(messages=messages)
        context_aggregator = llm.create_context_aggregator(context)

        pipeline = Pipeline([
            connection.transport.input(),
            stt,
            interjection_monitor,
            context_aggregator.user(),
            llm,
            tts,
            connection.transport.output(),
            context_aggregator.assistant(),
        ])

        task = PipelineTask(
            pipeline,
            params=PipelineParams(allow_interruptions=True),
        )

        flow_manager = FlowManager(
            task=task,
            llm=llm,
            tts=tts,
            flow_config=flow_config,
            context=context,
        )

        # Register event handlers
        @connection.transport.event_handler("on_participant_joined")
        async def on_joined(transport, participant):
            await flow_manager.initialize()

        @connection.transport.event_handler("on_call_state_updated")
        async def on_call_state(transport, state):
            if state == "left":
                await self._on_call_ended(session, context)

        runner = PipelineRunner()
        await runner.run(task)

        return session.id
```

### 1.5 FastAPI Routes

**File:** `apps/voice-engine/src/api/routes.py`

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import re

router = APIRouter(prefix="/api/v1")

class TriggerRequest(BaseModel):
    phone_number: str = Field(..., pattern=r"^\+61\d{9}$")
    candidate_id: str

class TriggerResponse(BaseModel):
    session_id: str
    status: str

@router.post("/assessment/trigger", response_model=TriggerResponse)
async def trigger_assessment(request: TriggerRequest):
    """Trigger an outbound assessment call."""
    session_id = await orchestrator.run_assessment(
        phone_number=request.phone_number,
        candidate_id=request.candidate_id,
    )
    return TriggerResponse(session_id=session_id, status="dialling")

@router.get("/assessment/{session_id}/status")
async def get_assessment_status(session_id: str):
    """Get the current status of an assessment session."""
    session = await persistence.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session.id, "status": session.status}
```

---

## 2. Event Handling

### UserStartedSpeaking / UserStoppedSpeaking

These Pipecat events are critical for:
1. **Interjection timer**: Reset on `UserStartedSpeaking`.
2. **Turn-taking**: The pipeline's VAD (Voice Activity Detection) manages when the bot should speak.
3. **Transcript segmentation**: Mark speaker turns for the transcript.

### Call Recording & Transcript

- Daily's built-in recording is enabled at room creation.
- Post-call, the recording URL is retrieved via Daily's REST API.
- Transcript segments are accumulated during the call via Pipecat's context aggregator.
- Full transcript is persisted to PostgreSQL when the call ends.

---

## 3. Acceptance Criteria

- [ ] `DailyVoiceTransport` adapter creates rooms in `ap-southeast-2` with recording enabled.
- [ ] `DailyVoiceTransport` can dial an Australian +61 number.
- [ ] `SFIAFlowController` implements all 5 states (Introduction, SkillDiscovery, EvidenceGathering, Summary, Closing).
- [ ] State transitions are driven by LLM function calls via Pipecat Flows.
- [ ] `InterjectionMonitor` fires after 60 seconds of speech without a claim.
- [ ] Interjection fires at most once per call.
- [ ] `InterjectionMonitor` resets timer on `UserStartedSpeaking`.
- [ ] Pipeline is fully assembled with STT → LLM → TTS chain.
- [ ] `/api/v1/assessment/trigger` endpoint accepts phone number and candidate ID.
- [ ] `/api/v1/assessment/{session_id}/status` returns session status.
- [ ] Full transcript is saved to Persistence port when call ends.
- [ ] Call recording URL is captured and stored.
- [ ] Unit tests exist for `InterjectionMonitor` (timer logic, single-fire guard).
- [ ] Unit tests exist for flow state transitions (mocked LLM).

## 4. Dependencies

- **Phase 1**: Monorepo structure, port interfaces, domain models.
- **Phase 2**: Working DailyTransport adapter, CallManager, basic voice infrastructure.
- **External**: Daily API key, STT provider (Deepgram/Azure/Google), LLM API key (OpenAI/Anthropic), TTS provider (ElevenLabs/Google/Azure).

## 5. Risks

| Risk | Mitigation |
|------|------------|
| Daily PSTN dial-out latency for AU | Test with real AU numbers early; Daily has Sydney PoP |
| Pipecat Flows API changes | Pin Pipecat version; review changelog before upgrades |
| STT accuracy for Australian accents | Evaluate Deepgram vs Google Cloud Speech for AU English |
| Interjection timing feels unnatural | Tune the 60-second threshold; consider speech pace analysis |
