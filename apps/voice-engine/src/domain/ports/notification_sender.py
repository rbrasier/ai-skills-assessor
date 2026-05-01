"""``INotificationSender`` port — stub for Phase 7 SME notification.

Phase 6 wires ``notification_sender=None`` at startup. Phase 7 injects a real
email/webhook adapter that implements this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class INotificationSender(ABC):

    @abstractmethod
    async def send_review_link(
        self,
        sme_email: str,
        review_url: str,
        candidate_name: str,
    ) -> None:
        """Send the SME review link after the post-call report is generated."""
        ...


__all__ = ["INotificationSender"]
