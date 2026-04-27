"""TTS provider abstraction layer.

Usage (inside ``_build`` — after voice extras are importable):

    from src.adapters.tts import create_tts_service
    tts = create_tts_service(settings)
    # drop into the Pipecat pipeline exactly where ElevenLabsTTSService went
"""

from src.adapters.tts.factory import create_tts_service

__all__ = ["create_tts_service"]
