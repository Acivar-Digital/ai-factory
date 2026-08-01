import warnings
from abc import ABC, abstractmethod
from typing import Any


class Skill(ABC):
    """
    Base class for agent capabilities.
    Each Skill encapsulates its toolsets and its own specific usage instructions.
    """

    @property
    @abstractmethod
    def toolsets(self) -> list[Any]:
        """Return list of FunctionToolset instances (e.g. MCPToolset) for the agent.
        Passed via the agent's `toolsets=` parameter."""
        pass

    @property
    def tools(self) -> list[Any]:
        """Return list of individual Tool instances for the agent.
        Passed via the agent's `tools=` parameter.
        Override this if you have individual tools to register."""
        warnings.warn(
            "Skill.tools is deprecated — use Skill.toolsets instead. "
            "tools returns an empty list by default and will be removed.",
            DeprecationWarning,
            stacklevel=2,
        )
        return []

    @property
    @abstractmethod
    def instructions(self) -> str:
        pass
