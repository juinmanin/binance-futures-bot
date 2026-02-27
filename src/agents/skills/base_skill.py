"""기본 스킬 추상 클래스"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SkillResult:
    """스킬 실행 결과"""

    success: bool
    data: Optional[Dict[str, Any]] = None
    message: str = ""
    errors: List[str] = field(default_factory=list)


class BaseSkill(ABC):
    """
    기본 스킬 추상 클래스

    Claude 에이전트가 호출할 수 있는 도구(스킬)의 기본 인터페이스입니다.
    모든 스킬은 이 클래스를 상속하고 as_tool_definition()을 구현합니다.
    """

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    @abstractmethod
    def as_tool_definition(self) -> Dict[str, Any]:
        """
        Claude tool_use API에 전달할 도구 정의 반환

        Returns:
            dict: {"name": ..., "description": ..., "input_schema": {...}}
        """

    @abstractmethod
    async def execute(self, **kwargs: Any) -> SkillResult:
        """
        스킬 실행

        Args:
            **kwargs: 스킬별 파라미터

        Returns:
            SkillResult
        """

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r})"
