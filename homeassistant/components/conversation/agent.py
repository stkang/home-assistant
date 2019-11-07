"""Agent foundation for conversation integration."""
from abc import ABC, abstractmethod

from homeassistant.helpers import intent


class AbstractConversationAgent(ABC):
    """Abstract conversation agent."""

    @property
    def attribution(self):
        """Return the attribution."""
        return False

    async def async_get_onboarding(self):
        """Get onboard data."""
        return False

    async def async_set_onboarding(self, new_data):
        """Set onboard data."""
        return True

    @abstractmethod
    async def async_process(self, text: str) -> intent.IntentResponse:
        """Process a sentence."""
