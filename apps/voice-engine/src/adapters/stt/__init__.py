"""STT provider abstraction layer.

Usage (inside ``_build`` — after voice extras are importable):

    from src.adapters.stt import create_stt_service
    stt = create_stt_service(settings)
    # drop into the Pipecat pipeline exactly where DeepgramSTTService went
"""

from src.adapters.stt.factory import create_stt_service

__all__ = ["create_stt_service"]
