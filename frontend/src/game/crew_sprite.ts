import { Container, Graphics } from 'pixi.js';
import type { CrewState, WorldState } from '../../../shared/types';
import { C } from '../config';
import { interactive } from './interaction';
import { label, palette } from './style';
import { drinking_position, irrigation_console_position, plot_position, route, type Position } from './waypoints';

export class CrewSprite {
  readonly container = new Container();
  private body = new Graphics();
  private warning_icon = new Graphics();
  private name;
  private path: Position[] = [];
  private task = '';
  private movement_speed = 0;
  private alive = true;
  private work = 0;
  private low_energy = false;
  private low_water = false;
  private phase = 0;
  private facing = 1;
  private back = false;
  constructor(readonly id: string, readonly index: number) {
    this.container.position.set(674 + index * 38, 894);
    this.container.addChild(new Graphics().ellipse(0, 14, 15, 6).fill({ color: 0x0d2118, alpha: 0.35 }), this.body);
    this.name = label(this.container, id.toUpperCase(), -15, 30, 9);
    this.container.addChild(this.warning_icon);
    interactive(this.container, { kind: 'crew', id }, 44, 76);
    this.draw(false);
  }
  update(crew: CrewState, world: WorldState) {
    this.alive = crew.alive; this.work = crew.work_this_tick;
    this.name.text = `${crew.alive ? '' : '✕ '}${crew.name}`;
    this.name.x = -this.name.width / 2;
    this.low_energy = crew.alive && crew.food_energy < C.crew.food_energy.warning;
    this.low_water = crew.alive && crew.water < C.crew.water.warning;
    this.draw_warning_icons();
    const signature = `${crew.current_task}:${crew.location}`;
    const target = this.task_target(crew, world);
    // A state update is the start of a new settled tick. Animations represent
    // that tick's work only; never queue historical tasks behind a newer plan.
    if (crew.alive && target && this.task !== signature) this.start_task(signature, target);
    else if (crew.alive && crew.current_task === 'idle' && !this.path.length) this.task = signature;
    if (!crew.alive) { this.path = []; this.movement_speed = 0; }
  }
  frame(delta: number, time: number) {
    const walking = this.alive && this.path.length > 0;
    let distance = delta * this.movement_speed;
    while (this.path.length && distance > 0 && this.alive) {
      const target = this.path[0], dx = target.x - this.container.x, dy = target.y - this.container.y;
      const length = Math.hypot(dx, dy);
      if (length <= distance) { this.container.position.set(target.x, target.y); this.path.shift(); distance -= length; }
      else { this.container.x += dx / length * distance; this.container.y += dy / length * distance; distance = 0; }
      if (Math.abs(dx) > Math.abs(dy)) { this.facing = dx < 0 ? -1 : 1; this.back = false; }
      else { this.facing = 0; this.back = dy < 0; }
    }
    this.phase = walking ? time * 11 : (time % 3.1 < 0.28 ? Math.sin(time % 3.1 / 0.28 * Math.PI) : 0);
    this.draw(walking);
  }
  private task_target(crew: CrewState, world: WorldState): Position | null {
    if (crew.current_task === 'generating') return { x: 270 + this.index * 64, y: 610 };
    if (crew.current_task === 'eating') return { x: 350 + (this.index % 2) * 65, y: 860 + Math.floor(this.index / 2) * 64 };
    if (['planting', 'harvesting', 'clearing'].includes(crew.current_task)) {
      const plot_id = crew.location.replace(/^plot:/, '');
      let plot_index = world.plots.findIndex(plot => plot.id === plot_id);
      if (plot_index < 0) plot_index = this.index;
      const plot = plot_position(plot_index);
      return { x: plot.x, y: plot.y + 29 };
    }
    if (crew.current_task === 'water_plant') return { x: 1090, y: 622 };
    if (crew.current_task === 'irrigation_console') return irrigation_console_position;
    if (crew.current_task === 'drinking') return drinking_position;
    return null;
  }
  private start_task(signature: string, target: Position) {
    this.task = signature;
    this.path = route(this.container.position, target);
    const points = [this.container.position, ...this.path];
    const total_distance = points.slice(1).reduce((sum, point, index) =>
      sum + Math.hypot(point.x - points[index].x, point.y - points[index].y), 0);
    // Visual-only timing: the route consumes at most 70% of the authoritative
    // tick display window; the remainder shows the actual task pose. Because
    // `delta` is scaled by WorldState.speed, pause and fast-forward stay in sync.
    const travel_window = C.time.real_seconds_per_tick * 0.7;
    this.movement_speed = total_distance / Math.max(travel_window, 0.001);
  }
  private draw(walking: boolean) {
    const g = this.body; g.clear();
    const accents = [0x8dd0c4, 0xdeaa76, 0xb4a1d4, 0xe4ce83];
    if (!this.alive) {
      g.roundRect(-20, 0, 32, 12, 5).fill(0x788078); g.circle(18, 6, 8).fill(0x93958c); return;
    }
    const stride = walking ? Math.sin(this.phase) * 5 : 0;
    const kneel = !walking && /planting|harvesting|clearing/.test(this.task);
    const seated = !walking && /eating|generating/.test(this.task);
    const beat = !walking ? this.phase * (this.task.startsWith('generating') ? this.work * 3 : 2) : 0;
    if (seated) {
      g.roundRect(-14, 1, 28, 18, 4).fill(0x506d58).stroke({ width: 2, color: 0xabb69b });
      g.roundRect(-11, 12, 9, 11, 2).fill(0x263b35); g.roundRect(2, 12, 9, 11, 2).fill(0x263b35);
    } else {
      g.roundRect(-9, 7 + stride, 7, 13 - (kneel ? 5 : 0), 2).fill(0x263b35);
      g.roundRect(2, 7 - stride, 7, 13 - (kneel ? 5 : 0), 2).fill(0x263b35);
    }
    g.roundRect(-13, -13 + beat, 26, 27, 7).fill(0xdedec9).stroke({ width: 2, color: 0x37473f });
    g.rect(-5, -10 + beat, 10, 16).fill(accents[this.index % accents.length]);
    g.roundRect(-18, -8 + beat, 7, 19, 3).fill(0xc2caba);
    g.roundRect(11, -8 - beat, 7, 19, 3).fill(0xc2caba);
    g.circle(this.facing, -21, 11).fill(0xcdad87).stroke({ width: 2, color: 0x4c4c3c });
    g.arc(this.facing, -24, 10, Math.PI, 2 * Math.PI).stroke({ width: 6, color: 0x414c3b });
    if (this.back) g.ellipse(0, -22, 9, 7).fill(0x414c3b);
    else g.rect(this.facing * 4 - 2, -22, 4, 3).fill(0x2b3b33);
    if (seated && this.task.startsWith('eating')) g.ellipse(0, 7, 11, 5).fill(0xe5dbb9).ellipse(0, 7, 6, 3).fill(0x8d9c65);
  }
  private draw_warning_icons() {
    const g = this.warning_icon;
    g.clear();
    const offsets = this.low_energy && this.low_water ? [-10, 10] : [0];
    let offset_index = 0;
    if (this.low_energy) {
      const x = offsets[offset_index++], y = -49;
      // Cartoon drumstick: toasted meat with a bright bone end.
      g.ellipse(x - 3, y, 8, 6).fill(0xd57b4d).stroke({ width: 1.5, color: 0x653c2d });
      g.circle(x - 5, y - 2, 2).fill(0xf0a66f);
      g.moveTo(x + 3, y + 3).lineTo(x + 8, y + 8).stroke({ width: 3.5, color: 0xf1e5c9 });
      g.circle(x + 9, y + 9, 3).fill(0xf1e5c9).stroke({ width: 1, color: 0x8e806d });
      g.circle(x + 6, y + 11, 2.5).fill(0xf1e5c9).stroke({ width: 1, color: 0x8e806d });
    }
    if (this.low_water) {
      const x = offsets[offset_index], y = -51;
      // A compact blue droplet, outlined to stay readable on every floor tile.
      g.moveTo(x, y - 8).bezierCurveTo(x - 8, y + 2, x - 7, y + 10, x, y + 11)
        .bezierCurveTo(x + 7, y + 10, x + 8, y + 2, x, y - 8)
        .fill(0x61bfd0).stroke({ width: 1.5, color: 0x1e6674 });
      g.ellipse(x - 2, y + 3, 1.8, 3).fill({ color: 0xd1f2f1, alpha: 0.85 });
    }
  }
}
