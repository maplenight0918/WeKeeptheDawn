"""Opt-in paid smoke: one Core planning call, one isolated world, no retries.

Run from the repo root with: python -m checks.live_three_agents --allow-paid
Specialist services must already be running with their own configurations.
"""
import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
import socket
import time

import httpx
import uvicorn
from dotenv import load_dotenv

from agent_runner.core_port import CorePort
from agent_runner.runner import AgentBridge
from core_agent.core_agent import CoreAgent, GPTDecisionModel, HTTPSpecialist


class SingleDecisionPort(CorePort):
    def __init__(self, core, *, max_calls=1):
        super().__init__(core)
        if type(max_calls) is not int or max_calls < 1:
            raise ValueError("max_calls must be positive")
        self.max_calls = max_calls
        self.calls = 0
        self.failure = None
        self.attempted_ticks = set()

    async def decide(self, state, errors, emit):
        tick = getattr(state, "tick", None)
        if self.calls >= self.max_calls or tick in self.attempted_ticks:
            self.failure = {"type": "PaidRetryNotAuthorized"}
            raise RuntimeError("Single paid planning attempt exhausted")
        self.calls += 1
        self.attempted_ticks.add(tick)
        try:
            return await super().decide(state, errors, emit)
        except Exception as exc:
            # Report only types/status, never raw provider bodies or credentials.
            chain = []
            current = exc
            for _ in range(8):
                if current is None:
                    break
                item = {"type": type(current).__name__}
                if isinstance(getattr(current, "code", None), int):
                    item["http_status"] = current.code
                chain.append(item)
                current = current.__cause__
            self.failure = {"chain": chain}
            raise


async def run(args):
    if not Path(args.core_env).is_file():
        raise ValueError("Core env file not found")
    load_dotenv(args.core_env, override=False)
    # Import after explicitly loading Core config. Never share it with specialist processes.
    from backend.main import create_app
    port = SingleDecisionPort(CoreAgent(GPTDecisionModel(),
        HTTPSpecialist(args.plant_url, token=os.getenv("PLANT_AGENT_TOKEN")),
        HTTPSpecialist(args.human_url, token=os.getenv("HUMAN_AGENT_TOKEN")), max_rounds=3))
    app = create_app(mode="external", db_path=":memory:")
    if args.wait_for_power_emergency:
        from fastapi.middleware.cors import CORSMiddleware
        app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:15174"],
                           allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
    listener = socket.socket()
    listener.bind(("127.0.0.1", args.game_port))
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
    server_task = asyncio.create_task(server.serve(sockets=[listener]))
    bridge_task = None
    report = {"paid_opt_in": True, "fixture": False, "max_core_planning_calls": 1,
              "max_rounds": 3, "provider_connectivity": "not_yet_confirmed"}
    try:
        async with asyncio.timeout(15):
            while not server.started:
                if server_task.done():
                    await server_task
                    raise RuntimeError("Isolated server stopped")
                await asyncio.sleep(0.05)
        url = f"http://127.0.0.1:{listener.getsockname()[1]}"
        async with httpx.AsyncClient(base_url=url) as client:
            if args.wait_for_power_emergency:
                from backend.domain.models import TickPlan
                initial = (await client.get("/world")).json()
                async with asyncio.timeout(60):
                    old = None
                    while not old:
                        old = (await client.get("/decision")).json()
                        await asyncio.sleep(0.05)
                    while True:
                        edited = (await client.get("/world")).json()
                        if edited["version"] > initial["version"]:
                            break
                        await asyncio.sleep(0.1)
                assert edited["tick"] == 0 and not edited["failed"] and not edited["paused"]
                assert edited["resources"]["power"]["value"] < edited["resources"]["power"]["warning"]
                stale = await client.post("/ingest/decision-plan", json={"request_id": old["request_id"],
                    "submission_id": "emergency-stale-check", "plan": TickPlan(tick=old["tick"], state_version=old["state_version"]).model_dump()})
                assert stale.status_code == 409
                report["intervention"] = {"resource": "power", "before": initial["resources"]["power"]["value"],
                    "after": edited["resources"]["power"]["value"], "observed_version": edited["version"],
                    "stale_submission_status": stale.status_code,
                    "old_provider_call_started": False}
            bridge = AgentBridge(port, url)
            bridge_task = asyncio.create_task(bridge.run(max_ticks=1))
            deadline = time.monotonic() + 420
            while not bridge_task.done():
                state = (await client.get("/world")).json()
                if state["paused_reason"] == "error" or state["failed"] or time.monotonic() >= deadline:
                    break
                await asyncio.sleep(0.2)
            if bridge_task.done():
                await bridge_task
            state = (await client.get("/world")).json()
            if not state["paused"] and not state["failed"]:
                await client.post("/control", json={"cmd": "pause"})
            state = (await client.get("/world")).json()
            history = (await client.get("/history", params={"limit": 1000})).json()
            report.update(confirmed_ticks=bridge.completed, core_planning_calls=port.calls,
                          failure=port.failure, world=state, public_history=history,
                          actual_results=list(port.history),
                          passed=bridge.completed == 1 and not state["failed"])
            # Only confirmed settlement proves an end-to-end run, not a provider health probe.
            report["provider_connectivity"] = "see_public_results" if bridge.completed else "unconfirmed"
            if args.wait_for_power_emergency:
                await asyncio.sleep(3)  # Allow the browser to capture the final WS snapshot.
    finally:
        if bridge_task is not None:
            bridge_task.cancel()
            await asyncio.gather(bridge_task, return_exceptions=True)
        server.should_exit = True
        try:
            await asyncio.wait_for(server_task, 10)
        finally:
            listener.close()
    output = Path("artifacts") / f"live-three-agents-{time.time_ns()}.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "confirmed_ticks": report["confirmed_ticks"],
                      "failure": report["failure"], "report": str(output)}, ensure_ascii=False))
    return report["passed"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-paid", action="store_true")
    parser.add_argument("--core-env", default="core_agent/.env")
    parser.add_argument("--plant-url", default="http://127.0.0.1:8101/discuss")
    parser.add_argument("--human-url", default="http://127.0.0.1:8102/discuss")
    parser.add_argument("--game-port", type=int, default=0, help="Local isolated backend port; default ephemeral")
    parser.add_argument("--wait-for-power-emergency", action="store_true", help="Wait for a browser resource edit before the one paid call")
    args = parser.parse_args()
    if not args.allow_paid:
        parser.error("Explicit --allow-paid is required; this can incur provider charges")
    logging.basicConfig(level=logging.WARNING)
    raise SystemExit(0 if asyncio.run(run(args)) else 1)


if __name__ == "__main__":
    main()
