from app.agents.base import BaseAgent
from app.models.schemas import AgentType


class AgentRegistry:
    """Registry of available AI agents."""

    def __init__(self) -> None:
        self._agents: dict[AgentType, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        self._agents[agent.agent_type] = agent

    def get(self, agent_type: AgentType) -> BaseAgent:
        if agent_type not in self._agents:
            raise KeyError(f"Agent not registered: {agent_type}")
        return self._agents[agent_type]

    def list_agents(self) -> list[dict]:
        return [
            {
                "type": agent.agent_type.value,
                "name": agent.name,
                "description": agent.description,
            }
            for agent in self._agents.values()
        ]


_registry: AgentRegistry | None = None


def get_agent_registry() -> AgentRegistry:
    global _registry
    if _registry is None:
        _registry = AgentRegistry()
        _register_default_agents(_registry)
    return _registry


def _register_default_agents(registry: AgentRegistry) -> None:
    from app.agents.requirements_agent import RequirementsAgent
    from app.agents.test_design_agent import TestDesignAgent
    from app.agents.automation_agent import AutomationAgent
    from app.agents.performance_agent import PerformanceAgent
    from app.agents.self_healing_agent import SelfHealingAgent
    from app.agents.defect_intelligence_agent import DefectIntelligenceAgent

    for agent_cls in [
        RequirementsAgent,
        TestDesignAgent,
        AutomationAgent,
        PerformanceAgent,
        SelfHealingAgent,
        DefectIntelligenceAgent,
    ]:
        registry.register(agent_cls())
