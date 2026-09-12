export interface Position { x: number; y: number }
export const anchors = { core: { x: 720, y: 555 }, plant: { x: 285, y: 128 }, human: { x: 420, y: 775 } };
export const resource_positions = { water: { x: 1262, y: 598 }, oxygen: { x: 1210, y: 890 },
  // Keep the battery on the left so its power line naturally leads to the generators.
  // The smaller drawing leaves the Power Bay heading unobstructed.
  power: { x: 160, y: 620 }, food: { x: 174, y: 886 } };
export const irrigation_console_position: Position = { x: 720, y: 455 };
// Player-approved scene placement: drinking is supplied by Water Plant, while
// the Galley remains exclusively the food / dining destination.
export const drinking_position: Position = { x: 1170, y: 677 };
export function plot_position(index: number): Position { return { x: 350 + (index % 5) * 183, y: 165 + Math.floor(index / 5) * 65 }; }
export function route(from: Position, to: Position): Position[] {
  function exit(point: Position): Position[] {
    if (point.y < 435) return [{ x: point.x, y: 402 }, { x: 720, y: 402 }, { x: 720, y: 467 }];
    if (point.y > 775) {
      const door_x = point.x < 580 ? 390 : point.x < 900 ? 745 : 1110;
      return [{ x: point.x, y: 816 }, { x: door_x, y: 816 }, { x: door_x, y: 745 }];
    }
    if (point.y >= 500 && point.y <= 712 && (point.x < 562 || point.x > 915)) {
      const door_x = point.x < 562 ? 390 : 1110;
      return [{ x: point.x, y: 548 }, { x: door_x, y: 548 }, { x: door_x, y: 467 }];
    }
    return [{ x: 720, y: point.y < 620 ? 467 : 745 }];
  }
  const leaving = exit(from), entering = exit(to), a = leaving[leaving.length - 1], b = entering[entering.length - 1];
  return [...leaving, { x: 720, y: a.y }, { x: 720, y: b.y }, ...entering.reverse(), to];
}
