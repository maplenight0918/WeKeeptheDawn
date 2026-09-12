"""Real HTTP/WebSocket smoke probe against an already-running local API.

This script never starts a server. It intentionally modifies the demo world,
then resets and pauses it for the next manual/frontend demonstration.
"""
from __future__ import annotations

import asyncio
import json
import os
from urllib.parse import urlsplit, urlunsplit

import httpx
import websockets


async def receive(ws, timeout=10):
    return json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))


async def drain(ws):
    count = 0
    while True:
        try:
            await receive(ws, timeout=0.15)
            count += 1
        except asyncio.TimeoutError:
            return count


async def main():
    root = os.environ.get('API_ROOT', 'http://127.0.0.1:8000').rstrip('/')
    parsed = urlsplit(root)
    socket_url = urlunsplit(('wss' if parsed.scheme == 'https' else 'ws', parsed.netloc,
                            parsed.path.rstrip('/') + '/ws', '', ''))
    async with httpx.AsyncClient(base_url=root, timeout=10) as client:
        health = await client.get('/healthz')
        health.raise_for_status()
        print(f'GET /healthz -> {health.status_code}: {health.text}')
        async with websockets.connect(socket_url) as ws:
            try:
                response = await client.post('/world/reset')
                response.raise_for_status()
                response = await client.post('/control', json={'cmd': 'resume'})
                response.raise_for_status()
                required = {'state_update', 'tick_plan', 'agent_thought'}
                received = set()
                thoughts = []
                async def collect():
                    while not required.issubset(received) or not thoughts:
                        envelope = await receive(ws)
                        received.add(envelope['type'])
                        if envelope['type'] == 'agent_thought':
                            thoughts.append(envelope['payload'])
                await asyncio.wait_for(collect(), timeout=30)
                thought = thoughts[0]
                metadata = thought.get('payload') or {}
                assert metadata.get('conversation_id'), f'Missing conversation_id: {thought}'
                assert metadata.get('to') or metadata.get('recipient'), f'Missing recipient: {thought}'
                assert metadata.get('mock') is True, f'Mock source must identify itself: {thought}'
                print('WebSocket -> state_update / tick_plan / agent_thought received; chat metadata valid')

                response = await client.post('/control', json={'cmd': 'pause'})
                response.raise_for_status()
                snapshot = await client.get('/world')
                snapshot.raise_for_status()
                paused_version = snapshot.json()['version']
                async def await_paused_snapshot():
                    while True:
                        envelope = await receive(ws)
                        payload = envelope.get('payload', {})
                        if envelope['type'] == 'state_update' and payload.get('paused') and payload['version'] >= paused_version:
                            return
                await asyncio.wait_for(await_paused_snapshot(), timeout=10)
                drained = await drain(ws)
                response = await client.post('/resources', json={'oxygen': 0})
                response.raise_for_status()
                first = await receive(ws)
                assert first['type'] == 'mission_failed', f'First post-edit message: {first}'
                assert first['payload']['deaths'], first
                snapshot = await client.get('/world')
                snapshot.raise_for_status()
                failed = snapshot.json()
                assert failed['failed'] and all(not crew['alive'] for crew in failed['crew'].values())
                print(f'Paused and drained {drained} queued messages; oxygen=0 -> mission_failed first, all crew dead')

                response = await client.post('/world/reset')
                response.raise_for_status()
                response = await client.post('/control', json={'cmd': 'resume'})
                response.raise_for_status()
                async def await_reset_progress():
                    while True:
                        envelope = await receive(ws)
                        payload = envelope.get('payload', {})
                        if envelope['type'] == 'state_update' and not payload.get('failed') and payload.get('tick', 0) > 0:
                            return payload
                restarted = await asyncio.wait_for(await_reset_progress(), timeout=30)
                assert all(crew['alive'] for crew in restarted['crew'].values())
                print(f'Reset -> world resumed, observed tick {restarted["tick"]}')
            finally:
                # Leave a reproducible initial snapshot for subsequent demo work.
                reset = await client.post('/world/reset')
                reset.raise_for_status()
                paused = await client.post('/control', json={'cmd': 'pause'})
                paused.raise_for_status()
                print('Cleanup -> reset + pause complete')
    print('PASS: real HTTP/WebSocket smoke checks')


if __name__ == '__main__':
    asyncio.run(main())
