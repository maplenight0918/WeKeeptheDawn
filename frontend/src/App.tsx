import { useEffect, type CSSProperties } from 'react';
import GameView from './game/GameView';
import MissionBadge from './components/MissionBadge';
import Toolbar from './components/Toolbar';
import AgentDrawer from './components/AgentDrawer';
import Bubble from './components/Bubble';
import Tooltip from './components/Tooltip';
import DetailCard from './components/DetailCard';
import FailureCard from './components/FailureCard';
import { connect_world } from './net/ws';
import { useGameStore } from './store/gameStore';

export default function App() {
  const world = useGameStore((state) => state.world);
  useEffect(() => connect_world(), []);
  const frozen = Boolean(world?.paused || world?.failed);
  const speed = world?.speed ?? 1;
  return <main className={`game-shell${frozen ? ' world-paused' : ''}`} style={{ '--world-speed': String(speed) } as CSSProperties}>
    <GameView />
    <MissionBadge />
    <Toolbar />
    <AgentDrawer />
    <Bubble />
    <Tooltip />
    <DetailCard />
    <FailureCard />
  </main>;
}
