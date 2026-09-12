"""Explicit paid, five-tick browser demo against a separately provisioned world."""
import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
import time

from dotenv import load_dotenv
import httpx

from agent_runner.runner import AgentBridge
from checks.live_three_agents import SingleDecisionPort
from core_agent.core_agent import CoreAgent, GPTDecisionModel, HTTPSpecialist


async def run(args):
    if not Path(args.core_env).is_file():
        raise ValueError("Core env file not found")
    load_dotenv(args.core_env, override=False)
    port = SingleDecisionPort(CoreAgent(GPTDecisionModel(),
        HTTPSpecialist("http://127.0.0.1:8101/discuss", token=os.getenv("PLANT_AGENT_TOKEN")),
        HTTPSpecialist("http://127.0.0.1:8102/discuss", token=os.getenv("HUMAN_AGENT_TOKEN")),
        max_rounds=3), max_calls=5)
    async with httpx.AsyncClient(base_url=args.game_url) as client:
        initial = (await client.get("/world")).json()
        if initial["tick"] != 0 or initial["failed"]:
            raise ValueError("Requires a separate fresh tick-zero world; never resets an existing world")
        bridge = AgentBridge(port, args.game_url)
        task = asyncio.create_task(bridge.run(max_ticks=5))
        seen_tick = -1
        stop_reason = "completed"
        deadline = time.monotonic() + 5 * 420
        try:
            while not task.done():
                state = (await client.get("/world")).json()
                if state["tick"] != seen_tick:
                    seen_tick = state["tick"]
                    print(json.dumps({"tick": seen_tick, "confirmed": bridge.completed,
                                      "core_calls": port.calls}), flush=True)
                if state["failed"] or state["paused_reason"] == "error":
                    stop_reason = "world_failed_or_error_paused"
                    break
                if time.monotonic() >= deadline:
                    stop_reason = "demo_deadline"
                    break
                await asyncio.sleep(0.2)
            if task.done():
                await task
        except Exception as exc:
            stop_reason = type(exc).__name__  # No raw provider data.
        finally:
            # Stop the observer/bridge before pausing so no new paid call starts.
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            state = (await client.get("/world")).json()
            if not state["paused"] and not state["failed"]:
                await client.post("/control", json={"cmd": "pause"})
        state = (await client.get("/world")).json()
        history = (await client.get("/history", params={"limit": 1000})).json()
        report = {"paid_opt_in": True, "fixture": False, "max_ticks": 5, "max_core_planning_calls": 5,
                  "max_rounds_per_call": 3, "core_calls": port.calls, "confirmed_ticks": bridge.completed,
                  "stop_reason": stop_reason, "failure": port.failure, "world": state,
                  "public_history": history, "actual_results": list(port.history),
                  "passed": bridge.completed == 5 and state["tick"] == 5 and not state["failed"]}
        output = Path("artifacts") / f"live-five-ticks-{time.time_ns()}.json"
        output.parent.mkdir(exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"passed": report["passed"], "confirmed_ticks": bridge.completed,
                          "stop_reason": stop_reason, "failure": port.failure, "report": str(output)}), flush=True)
        return report["passed"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-paid", action="store_true")
    parser.add_argument("--game-url", default="http://127.0.0.1:8001")
    parser.add_argument("--core-env", default="core_agent/.env")
    args = parser.parse_args()
    if not args.allow_paid:
        parser.error("Requires explicit paid authorization for five ticks")
    logging.basicConfig(level=logging.WARNING)
    raise SystemExit(0 if asyncio.run(run(args)) else 1)


if __name__ == "__main__":
    main()
