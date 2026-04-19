"""Port interfaces (ABCs) — boundaries between domain and infrastructure."""

from src.domain.ports.assessment_trigger import IAssessmentTrigger
from src.domain.ports.knowledge_base import IKnowledgeBase
from src.domain.ports.llm_provider import ILLMProvider
from src.domain.ports.persistence import IPersistence
from src.domain.ports.voice_transport import IVoiceTransport

__all__ = [
    "IAssessmentTrigger",
    "IKnowledgeBase",
    "ILLMProvider",
    "IPersistence",
    "IVoiceTransport",
]
