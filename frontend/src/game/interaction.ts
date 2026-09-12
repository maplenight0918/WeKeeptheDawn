import { Container, Rectangle } from 'pixi.js';
import { useGameStore } from '../store/gameStore';

export type Target = { kind: 'object' | 'plot' | 'crew'; id: string };
export function interactive(node: Container, target: Target, width: number, height: number) {
  node.eventMode = 'static'; node.cursor = 'pointer'; node.hitArea = new Rectangle(-width / 2, -height / 2, width, height);
  node.on('pointermove', (event) => useGameStore.getState().set_hover({ ...target, x: event.global.x, y: event.global.y }));
  node.on('pointerout', () => useGameStore.getState().set_hover(null));
  node.on('pointertap', () => useGameStore.getState().set_selected(target));
}
