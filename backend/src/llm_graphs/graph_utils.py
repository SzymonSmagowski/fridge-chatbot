"""Generic LangGraph helpers: message pruning + summary extraction."""
from langchain_core.messages import RemoveMessage
from langgraph.graph import MessagesState


async def delete_tool_messages(state: MessagesState) -> dict:
    """Remove ToolMessages and AIMessages that carry tool_calls from the state."""
    messages = state["messages"]
    ids_to_remove = []
    for msg in messages:
        cls = msg.__class__.__name__
        if cls == "ToolMessage" or (cls == "AIMessage" and msg.additional_kwargs.get("tool_calls")):
            ids_to_remove.append(msg.id)
    return {"messages": [RemoveMessage(id=i) for i in ids_to_remove]}


def extract_relevant_messages(messages, for_model: bool = True):
    """Trim long history: keep the last 10 post-summary messages plus the latest summary."""
    tool_messages = [
        m for m in messages
        if m.__class__.__name__ == "ToolMessage"
        or (m.__class__.__name__ == "AIMessage" and m.additional_kwargs.get("tool_calls"))
    ]
    without_summaries = [
        m for m in messages
        if not m.additional_kwargs.get("is_summary") and m not in tool_messages
    ]
    summary = next((m for m in reversed(messages) if m.additional_kwargs.get("is_summary")), None)

    n = len(without_summaries)
    if n <= 20:
        relevant = without_summaries
    else:
        cutoff = n - (n % 10)
        relevant = without_summaries[cutoff - 10:]

    if for_model and summary:
        relevant = [summary] + relevant
    if for_model and tool_messages:
        relevant = relevant + tool_messages
    return relevant
