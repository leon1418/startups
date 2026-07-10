"""Example agent with LangGraph and Fly Machines API."""
from langgraph.graph import StateGraph
import httpx


def agent_tool_loop(state):
    """LLM-powered agent loop with tools."""
    # Simplified agent logic
    response = httpx.post(
        "https://api.machines.dev/v1/apps/agent-app/machines",
        json={"config": {"image": "agent:latest"}},
    )
    return {"result": response.json()}


graph = StateGraph(dict)
graph.add_node("agent", agent_tool_loop)
