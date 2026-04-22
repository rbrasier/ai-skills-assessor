# PHASE-3 Revision 2: Browser calls via self-hosted LiveKit

## Reference

- **Parent Phase:** [`v0.4-phase-3-infrastructure-deployment.md`](./v0.4-phase-3-infrastructure-deployment.md)
- **Prior revision:** [`PHASE-3-Revision-1-basic-call-runtime.md`](./PHASE-3-Revision-1-basic-call-runtime.md)
- **Revision date:** 2026-04-22
- **Status:** In progress
- **Version bump:** `0.4.1` → `0.4.2` (MINOR — new `DIALING_METHOD` + LiveKit adapter; no database schema change).

## Why a revision

Revision 1 only supported **telephone** outbound dialling through Daily. Some deployments need the candidate to join from the **browser** (WebRTC) without PSTN, using a **self-hosted LiveKit** server. This revision adds a runtime switch: **Daily (telephone)** or **LiveKit (browser)**, with Daily environment variables not required in browser mode.

## What this revision ships

### 1. `DIALING_METHOD` environment switch

- `daily` (default) — existing behaviour: `DailyVoiceTransport` + Pipecat `DailyTransport` + PSTN dial-out. **Requires** `DAILY_API_KEY` and `DAILY_DOMAIN` at process startup.
- `browser` — `LiveKitVoiceTransport`: Pipecat `LiveKitTransport`, **no Daily credentials**. **Requires** `LIVEKIT_URL`, `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET`.

### 2. LiveKit adapter

- `apps/voice-engine/src/adapters/livekit_transport.py` — room name + JWTs (bot + human) via `livekit-api`; launches `BasicCallBot` in `transport_mode="livekit"`.
- **Join link:** a URL for the default LiveKit “custom server” meet UI (`LIVEKIT_MEET_URL`, default `https://meet.livekit.io/custom` with `url` / `token` / `room` query parameters). Stored in session metadata and exposed on the status API for the web UI.
- `CallConnection` extended with `browser_join_url` (and optional LiveKit fields for future use).

### 3. `BasicCallBot` — LiveKit branch

- Uses `LiveKitTransport` with sample rates aligned to Pipecat’s WebRTC path (16 kHz in, 24 kHz out; Daily remains 8 kHz for PSTN).
- Lifecycle: `on_first_participant_joined` → `in_progress`; `on_participant_left` → completed path.

### 4. API + web

- `GET /api/v1/assessment/{id}/status` (and BFF) returns `dialing_method` and `browser_join_url` where applicable.
- Candidate `CallStateDisplay` shows a primary **Open the interview in your browser** CTA and copy for browser dialling.

### 5. Dependencies

- `pipecat-ai` voice extras now include the `livekit` extra; `livekit-api` is listed explicitly for room tokens.

## Verification

- Run `./validate.sh` from the repository root.
- For browser mode: set LiveKit, Deepgram, and ElevenLabs; start the stack; trigger a session; open `browserJoinUrl` from the status response or the candidate UI; confirm audio both ways.

## Deferrals

- Self-hosting a branded join app instead of `meet.livekit.io` (configure `LIVEKIT_MEET_URL`).
- Recording/egress for LiveKit (not wired to DB; same as Daily cloud recording in Rev 1).

## Revision history

| Date | Revision | Summary | Status |
|------|----------|---------|--------|
| 2026-04-22 | 2 | Optional browser path via self-hosted LiveKit; `DIALING_METHOD` switch. | In progress |
