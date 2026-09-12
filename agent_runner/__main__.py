from __future__ import annotations

import argparse
import asyncio
import logging
import os

from core_agent.core_agent import CoreAgent, GPTDecisionModel, HTTPSpecialist
from agent_runner.core_port import CorePort
from agent_runner.runner import AgentBridge
from agent_runner.specialist_http import CancellableSpecialist


def main():
    parser = argparse.ArgumentParser(description="Space Greenhouse 三 Agent bridge")
    parser.add_argument("--game-url", default="http://127.0.0.1:8001")
    fixtures = parser.add_mutually_exclusive_group()
    fixtures.add_argument("--fixture", action="store_true", help="明確標示的灌溉替身；不呼叫模型或 specialist")
    fixtures.add_argument("--fixture-actions", action="store_true", help="完整動作展示：輪班補給、發電、製水及地塊操作")
    parser.add_argument("--core-env", help="明確指定 Core 的 dotenv 檔案；現有環境變數優先")
    parser.add_argument("--max-ticks", type=int)
    args = parser.parse_args()
    if args.max_ticks is not None and args.max_ticks < 1:
        parser.error("--max-ticks must be positive")
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if args.core_env:
        from pathlib import Path
        from dotenv import load_dotenv
        if not Path(args.core_env).is_file():
            parser.error("--core-env file not found")
        load_dotenv(args.core_env, override=False)
    mock = args.fixture or args.fixture_actions
    if mock:
        from agent_runner.fixtures import ActionFixtureModel, FixtureModel, FixtureSpecialist
        core = CoreAgent(ActionFixtureModel() if args.fixture_actions else FixtureModel(), FixtureSpecialist(), FixtureSpecialist())
    else:
        core = CoreAgent(GPTDecisionModel(timeout=120),
                         CancellableSpecialist(os.environ["PLANT_AGENT_URL"], token=os.getenv("PLANT_AGENT_TOKEN"), timeout=120),
                         CancellableSpecialist(os.environ["HUMAN_AGENT_URL"], token=os.getenv("HUMAN_AGENT_TOKEN"), timeout=120),
                         timeout=120)
    try:
        asyncio.run(AgentBridge(CorePort(core, mock=mock), args.game_url).run(max_ticks=args.max_ticks))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
