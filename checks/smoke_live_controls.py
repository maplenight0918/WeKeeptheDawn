"""Smoke test for a running real WorldLoop; no browser or frontend arithmetic."""
from __future__ import annotations

import os
import time

import httpx


root = os.environ.get("API_ROOT", "http://127.0.0.1:8010")


def world(client: httpx.Client) -> dict:
    response = client.get(f"{root}/world")
    response.raise_for_status()
    return response.json()


with httpx.Client(timeout=5) as client:
    deadline = time.monotonic() + 5
    initial = world(client)
    while initial["tick"] < 1 and time.monotonic() < deadline:
        time.sleep(0.05)
        initial = world(client)
    assert initial["tick"] >= 1, "world did not begin settling"

    paused = client.post(f"{root}/control", json={"cmd": "pause"})
    paused.raise_for_status()
    frozen = paused.json()
    time.sleep(0.25)  # Longer than the x20 world loop delay.
    after_pause = world(client)
    assert after_pause["paused"] is True
    assert after_pause["tick"] == frozen["tick"]
    assert after_pause["resources"] == frozen["resources"]
    assert after_pause["plots"] == frozen["plots"]

    speed = client.post(f"{root}/control", json={"cmd": "speed", "value": 20})
    speed.raise_for_status()
    assert speed.json()["speed"] == 20
    time.sleep(0.15)
    assert world(client)["tick"] == frozen["tick"], "speed must not unpause world"

    resumed = client.post(f"{root}/control", json={"cmd": "resume"})
    resumed.raise_for_status()
    deadline = time.monotonic() + 2
    after_resume = world(client)
    while after_resume["tick"] <= frozen["tick"] and time.monotonic() < deadline:
        time.sleep(0.03)
        after_resume = world(client)
    assert after_resume["tick"] > frozen["tick"], "world did not resume at x20"
    print({"passed": True, "paused_tick": frozen["tick"], "resumed_tick": after_resume["tick"]})
