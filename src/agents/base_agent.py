"""기본 에이전트 클래스"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AgentResponse:
    """에이전트 응답"""

    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    actions_taken: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class BaseAgent(ABC):
    """
    기본 에이전트 추상 클래스

    모든 에이전트는 이 클래스를 상속합니다.
    """

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self._is_running = False

    @abstractmethod
    async def run(self, task: str, context: Optional[Dict[str, Any]] = None) -> AgentResponse:
        """
        에이전트 작업 실행

        Args:
            task: 수행할 작업 설명
            context: 추가 컨텍스트 (선택)

        Returns:
            AgentResponse
        """

    @property
    def is_running(self) -> bool:
        return self._is_running

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r})"
