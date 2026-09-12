import { Text, type Container } from 'pixi.js';

export const MAP = { width: 1440, height: 1080 };
export const palette = { earth: 0x735347, earth_dark: 0x60483f, wall: 0x343c37, rim: 0x98a394,
  floor: 0x657266, floor_alt: 0x606d63, corridor: 0x53605a, ink: 0x172621, white: 0xe9e7d1,
  cyan: 0x79c8c8, green: 0xa7c687, gold: 0xe3b86c, purple: 0xb8a4e9 };

export function label(parent: Container, text: string, x: number, y: number, size = 12, color = palette.white) {
  const node = new Text({ text, style: { fontFamily: 'Noto Sans TC, ui-monospace, monospace', fontSize: size, fill: color, letterSpacing: 1.5 } });
  node.position.set(x, y); parent.addChild(node); return node;
}
