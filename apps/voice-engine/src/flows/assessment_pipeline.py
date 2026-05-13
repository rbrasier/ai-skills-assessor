"""SFIA assessment pipeline — Pipecat pipeline wiring for Phase 4.

Builds the full pipeline for a single assessment session:

    LiveKit/Daily input
      → STT
      → LLM context aggregator (user side)
      → AnthropicLLMService  ← managed by FlowManager (SFIAFlowController)
      → TTS
      → TranscriptFrameObserver  ← captures bot + candidate turns
      → LiveKit/Daily output
      → LLM context aggregator (assistant side)

All Pipecat imports are lazy so this module loads in the lean CI image.

Public entry point::

    task = await build_sfia_pipeline(
        transport=livekit_transport,
        settings=settings,
        controller=sfia_controller,
        recorder=transcript_recorder,
        in_sample_rate=16000,
        out_sample_rate=24000,
    )
"""

from __future__ import annotations

import logging
from typing import Any

from src.config import Settings
from src.domain.services.transcript_recorder import TranscriptRecorder
from src.flows.sfia_flow_controller import SfiaFlowController

logger = logging.getLogger(__name__)


async def build_sfia_pipeline(
    *,
    transport: Any,
    settings: Settings,
    controller: SfiaFlowController,
    recorder: TranscriptRecorder,
    in_sample_rate: int = 16000,
    out_sample_rate: int = 24000,
) -> Any:
    """Assemble and return a configured ``PipelineTask`` for the SFIA flow.

    Raises ``RuntimeError`` if ``ANTHROPIC_API_KEY`` is not configured or
    Pipecat is not installed.
    """
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is required for the SFIA flow. "
            "Set the environment variable or disable ENABLE_SFIA_FLOW."
        )

    try:
        from pipecat.pipeline.pipeline import Pipeline
        from pipecat.pipeline.task import PipelineParams, PipelineTask
        from pipecat_flows import FlowManager
    except ImportError as exc:
        raise RuntimeError(
            "Pipecat or pipecat-ai-flows is not installed. "
            "Install with `pip install -e .[voice]`."
        ) from exc

    # pipecat >= 0.0.99 moved to a universal LLMContext + LLMContextAggregatorPair;
    # fall back to the legacy OpenAILLMContext + create_context_aggregator() for
    # older installs so the error message stays actionable rather than cryptic.
    try:
        from pipecat.processors.aggregators.llm_context import LLMContext
        from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
        _new_context_api = True
    except ImportError:
        try:
            from pipecat.processors.aggregators.openai_llm_context import (
                OpenAILLMContext as LLMContext,  # type: ignore[no-redef]
            )
            _new_context_api = False
        except ImportError as exc:
            raise RuntimeError(
                "Cannot import LLMContext or OpenAILLMContext from pipecat. "
                "Ensure pipecat-ai>=0.0.105 is installed (`pip install -e .[voice]`)."
            ) from exc

    # pipecat >= 0.0.99 moved AnthropicLLMService into a submodule.
    try:
        from pipecat.services.anthropic.llm import AnthropicLLMService
    except ImportError:
        from pipecat.services.anthropic import AnthropicLLMService  # type: ignore[no-redef]

    from src.adapters.stt import create_stt_service
    from src.adapters.tts import create_tts_service

    stt = create_stt_service(settings)
    tts = create_tts_service(settings)

    use_chunker = settings.audio_chunking_enabled and settings.stt_provider == "local"
    if use_chunker:
        from src.processors.pipecat_audio_chunker import build_audio_chunking_frame_processor
        audio_chunker = build_audio_chunking_frame_processor()
        logger.info("SFIAAssessmentPipeline: audio chunking enabled (5-second chunks)")
    else:
        audio_chunker = None
        logger.info("SFIAAssessmentPipeline: audio chunking disabled (full-clip STT)")

    # pipecat >= 0.0.105 prefers settings= over top-level model= kwarg.
    try:
        llm = AnthropicLLMService(
            api_key=settings.anthropic_api_key,
            settings=AnthropicLLMService.Settings(model=settings.anthropic_in_call_model),
        )
    except (TypeError, AttributeError):
        llm = AnthropicLLMService(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_in_call_model,
        )

    context = LLMContext()
    if _new_context_api:
        context_aggregator = LLMContextAggregatorPair(context)
    else:
        context_aggregator = llm.create_context_aggregator(context)  # type: ignore[attr-defined]

    observer = _TranscriptFrameObserver(recorder=recorder)

    pipeline_stages: list[Any] = [transport.input()]
    if audio_chunker is not None:
        pipeline_stages.append(audio_chunker)
    pipeline_stages.extend([
        stt,
        context_aggregator.user(),
        llm,
        tts,
        observer,
        transport.output(),
        context_aggregator.assistant(),
    ])

    pipeline = Pipeline(pipeline_stages)

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=in_sample_rate,
            audio_out_sample_rate=out_sample_rate,
        ),
    )

    flow_manager = FlowManager(
        task=task,
        llm=llm,
        context_aggregator=context_aggregator,
    )
    await flow_manager.initialize(initial_node=controller.get_initial_node())

    logger.info("SFIAAssessmentPipeline: pipeline ready (model=%s)", settings.anthropic_in_call_model)
    return task


def _TranscriptFrameObserver(recorder: TranscriptRecorder) -> Any:
    """Factory that returns a Pipecat FrameProcessor capturing transcript turns.

    Captures:
    - ``TranscriptionFrame`` (downstream) → candidate speech turns
    - ``TTSSpeakFrame`` (downstream) → bot speech turns
    """
    try:
        from pipecat.frames.frames import TranscriptionFrame, TTSSpeakFrame
        from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
    except ImportError as exc:
        raise RuntimeError("Pipecat not installed") from exc

    class _Observer(FrameProcessor):
        def __init__(self) -> None:
            super().__init__()

        async def process_frame(self, frame: Any, direction: Any) -> None:
            await super().process_frame(frame, direction)

            if direction is FrameDirection.DOWNSTREAM:
                if isinstance(frame, TranscriptionFrame):
                    text = getattr(frame, "text", "") or ""
                    if text.strip():
                        recorder.record_turn(speaker="candidate", text=text)

                elif isinstance(frame, TTSSpeakFrame):
                    text = getattr(frame, "text", "") or ""
                    if text.strip():
                        recorder.record_turn(speaker="bot", text=text)

            await self.push_frame(frame, direction)

    return _Observer()


__all__ = ["build_sfia_pipeline"]
