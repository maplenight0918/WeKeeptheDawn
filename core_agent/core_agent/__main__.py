"""One discussion from a JSON snapshot; never advances or modifies the world."""
import argparse
import asyncio
import json
import os
from pathlib import Path
from . import CoreAgent, GPTDecisionModel, HTTPSpecialist, PlanningError
from .rules import get_rules


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('--plant-url', default=os.environ.get('PLANT_AGENT_URL'))
    parser.add_argument('--human-url', default=os.environ.get('HUMAN_AGENT_URL'))
    args = parser.parse_args()
    if not args.plant_url or not args.human_url:
        parser.error('set PLANT_AGENT_URL and HUMAN_AGENT_URL or pass endpoint arguments')
    core = CoreAgent(GPTDecisionModel(),
                     HTTPSpecialist(args.plant_url, token=os.environ.get('PLANT_AGENT_TOKEN')),
                     HTTPSpecialist(args.human_url, token=os.environ.get('HUMAN_AGENT_TOKEN')))
    result = await core.plan(json.loads(args.snapshot.read_text()), get_rules())
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (PlanningError, ValueError, OSError) as exc:
        raise SystemExit(f'Core planning failed; world must remain paused: {exc}')
