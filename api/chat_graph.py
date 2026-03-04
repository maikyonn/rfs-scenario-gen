"""LangGraph ReAct agent + SSE streaming for the crash scenario chat pipeline."""

from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

from langchain_aws import ChatBedrock
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from api.chat_progress import _event_loop_var, _progress_queue
from api.chat_tools import (
    build_scenario,
    generate_crash_config,
    modify_config,
    render_scenario,
    validate_collision,
)
from api.pipeline import AWS_PROFILE

# ── System prompt ─────────────────────────────────────────────────────────────

CHAT_SYSTEM_PROMPT = """You are a crash scenario generation assistant for the Richmond, CA autonomous vehicle test environment.

## Strict Workflow Order:
1. Call generate_crash_config (or modify_config for tweaks) → get config JSON
2. Call build_scenario → get xosc_path
3. ALWAYS call validate_collision with xosc_path
   - If collision_detected=false: look at closest_approach in the output (distance_m, time, entity_a, entity_b).
     Call modify_config with the current config AND a message like:
     "No collision. Closest approach was Xm at t=Ys. Adjust speeds/positions so vehicles meet at the same point at the same time."
     Use the closest approach distance to guide your fix — large distance means fine-tune speeds/timing.
   - After 3 failed attempts on the same junction/road, switch to a DIFFERENT junction or road
     (e.g. try J199 instead of J323, or a different pattern entirely). Do NOT simplify the scenario —
     keep the same crash type and vehicles, just change the location.
   - Keep retrying (modify → build → validate) until collision_detected=true. Never give up.
4. Call render_scenario ONLY after validate_collision returns collision_detected=true
5. Tell the user the result: what the scenario is, where it happens, and include the video URL from render_scenario output.

## Tweaks:
When user asks to modify speed/position/vehicle/pattern:
  → modify_config → build_scenario → validate_collision → render_scenario

## Domain:
- Patterns: junction_tbone, rear_end, head_on, sideswipe, pedestrian_crossing, dooring, parking_backing
- Vehicles: sedan, suv, pickup, motorcycle, bicycle, pedestrian
- Key junctions: J323 (23rd St/Harbour Way), J199 (Central Ave), J103 (Marina Bay Pkwy)
- Longest roads: Road 53 (321m), Road 46 (151m, 6-lane), Road 54 (has parking lanes)
- Road 33 (81m, 2 backward lanes) is great for sideswipe
- J103 has a very short exit road (37, only 1.78m) — avoid using it

## Parked vehicles:
- NEVER place a stationary vehicle (speed_mph=0) in a driving lane without offset — it blocks the middle of the road.
- Preferred: Road 54, lane 2 with lane_type="parking" — the only real parking lane.
- Alternative: Use "offset": 1.2 on any road to push the vehicle toward the curb.

## Important:
- Always pass session_id to build_scenario so filenames are unique per session.
- Never render without a confirmed collision from validate_collision.
- If modify_config or generate_crash_config returns an ERROR: string, tell the user what went wrong.
"""

# ── Agent singleton ───────────────────────────────────────────────────────────

_checkpointer = MemorySaver()
_tools = [generate_crash_config, modify_config, build_scenario, validate_collision, render_scenario]


def _make_agent():
    llm = ChatBedrock(
        model_id="us.anthropic.claude-sonnet-4-6",
        region_name="us-west-2",
        credentials_profile_name=AWS_PROFILE,
    )
    return create_react_agent(
        llm,
        _tools,
        checkpointer=_checkpointer,
        prompt=CHAT_SYSTEM_PROMPT,
    )


_agent = _make_agent()


# ── SSE event builder ─────────────────────────────────────────────────────────

def _event_to_sse(event: dict) -> str | None:
    """Convert a LangGraph astream_events v2 event to an SSE line, or None to skip."""
    kind = event.get("event", "")
    name = event.get("name", "")

    if kind == "on_chat_model_stream":
        chunk = event.get("data", {}).get("chunk")
        if chunk is None:
            return None
        # AIMessageChunk — extract text delta
        delta = ""
        if hasattr(chunk, "content"):
            content = chunk.content
            if isinstance(content, str):
                delta = content
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        delta += part.get("text", "")
        if not delta:
            return None
        payload = json.dumps({"type": "text_delta", "delta": delta})
        return f"data: {payload}\n\n"

    if kind == "on_tool_start":
        tool_input = event.get("data", {}).get("input", {})
        payload = json.dumps({"type": "tool_start", "name": name, "input": tool_input})
        return f"data: {payload}\n\n"

    if kind == "on_tool_end":
        raw_output = event.get("data", {}).get("output")
        # raw_output is a ToolMessage; extract its content
        if hasattr(raw_output, "content"):
            output_str = raw_output.content
        else:
            output_str = str(raw_output) if raw_output is not None else ""

        # Try to parse the tool output as JSON for richer frontend handling
        try:
            output_obj = json.loads(output_str)
        except (json.JSONDecodeError, TypeError):
            output_obj = {"raw": output_str}

        payload = json.dumps({"type": "tool_end", "name": name, "output": output_obj})
        return f"data: {payload}\n\n"

    return None


# ── Public streaming function ─────────────────────────────────────────────────

async def stream_chat(session_id: str, user_message: str) -> AsyncGenerator[str, None]:
    """Yield SSE-formatted event strings for a single chat turn.

    Event types emitted:
      text_delta    — {"type": "text_delta", "delta": str}
      tool_start    — {"type": "tool_start", "name": str, "input": obj}
      tool_end      — {"type": "tool_end", "name": str, "output": obj}
      tool_progress — {"type": "tool_progress", "name": str, "message": str}
      done          — {"type": "done"}
      error         — {"type": "error", "message": str}

    Note: tool_progress events are emitted from sync @tool threads via emit_tool_progress()
    in chat_tools.py. They are forwarded through a shared asyncio.Queue that is drained
    concurrently via a background task alongside the main astream_events loop.
    """
    config = {"configurable": {"thread_id": session_id}, "recursion_limit": 200}
    progress_q: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    # Inject context vars so sync tool threads can push progress events
    tok_q = _progress_queue.set(progress_q)
    tok_l = _event_loop_var.set(loop)

    try:
        # Wrap astream_events so we can send keepalive comments during long gaps
        last_yield = asyncio.get_event_loop().time()

        async def _heartbeat_wrapper():
            nonlocal last_yield
            async for event in _agent.astream_events(
                {"messages": [("user", user_message)]},
                config=config,
                version="v2",
            ):
                yield event
                last_yield = asyncio.get_event_loop().time()

        # Background task that sends SSE comments every 15s to keep connection alive
        heartbeat_q: asyncio.Queue[str] = asyncio.Queue()
        heartbeat_done = asyncio.Event()

        async def _heartbeat():
            while not heartbeat_done.is_set():
                await asyncio.sleep(15)
                if heartbeat_done.is_set():
                    break
                elapsed = asyncio.get_event_loop().time() - last_yield
                if elapsed >= 14:
                    await heartbeat_q.put(": keepalive\n\n")

        heartbeat_task = asyncio.create_task(_heartbeat())

        try:
            async for event in _heartbeat_wrapper():
                # Drain heartbeats
                while not heartbeat_q.empty():
                    yield heartbeat_q.get_nowait()

                # Drain any buffered progress events before emitting the next agent event
                while not progress_q.empty():
                    item = progress_q.get_nowait()
                    if item is not None:
                        payload = json.dumps({"type": "tool_progress", "name": item["tool"], "message": item["message"]})
                        yield f"data: {payload}\n\n"

                sse_line = _event_to_sse(event)
                if sse_line:
                    yield sse_line
        finally:
            heartbeat_done.set()
            heartbeat_task.cancel()
    except Exception as e:
        payload = json.dumps({"type": "error", "message": str(e)})
        yield f"data: {payload}\n\n"
    finally:
        _progress_queue.reset(tok_q)
        _event_loop_var.reset(tok_l)

    yield 'data: {"type":"done"}\n\n'


# ── History reader ────────────────────────────────────────────────────────────

def get_chat_history(session_id: str) -> list[dict]:
    """Return simplified message history for a session from the checkpointer."""
    thread_config = {"configurable": {"thread_id": session_id}}
    state = _checkpointer.get(thread_config)
    if state is None:
        return []

    messages = state.get("channel_values", {}).get("messages", [])
    result = []
    for msg in messages:
        role = getattr(msg, "type", None)
        # LangChain message types: "human", "ai", "tool"
        if role == "human":
            result.append({"role": "user", "content": msg.content})
        elif role == "ai":
            content = msg.content
            if isinstance(content, list):
                text = " ".join(
                    p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"
                )
            else:
                text = str(content)
            if text.strip():
                result.append({"role": "assistant", "content": text})
    return result
