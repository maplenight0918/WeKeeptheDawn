import { Container, Graphics } from 'pixi.js';
import type { WorldState } from '../../../shared/types';
import { C, CROPS } from '../config';
import { CropSprites } from './crops_sprites';
import { interactive } from './interaction';
import { label, palette } from './style';
import { drinking_position, irrigation_console_position, plot_position, resource_positions } from './waypoints';

export class WorldObjects {
  readonly container = new Container();
  private resources = new Map<string, Graphics>();
  private plots: { frame: Graphics; crop: CropSprites; text: ReturnType<typeof label>; mark: ReturnType<typeof label> }[] = [];
  private machine = new Graphics();
  private irrigation_text;
  private state: WorldState | null = null;
  constructor() {
    for (const [id, position] of Object.entries(resource_positions)) {
      const object = new Container(); object.position.copyFrom(position);
      const drawing = new Graphics(); object.addChild(drawing); this.resources.set(id, drawing);
      interactive(object, { kind: 'object', id }, 116, 140); this.container.addChild(object);
      const caption = label(object, ({ water: 'H2O', oxygen: 'O2', food: 'RATIONS', power: 'BATTERY' } as Record<string, string>)[id], 0, 80, 11);
      caption.anchor.set(0.5, 0);
    }
    for (let i = 0; i < C.plots.count; i++) {
      const object = new Container(); object.position.copyFrom(plot_position(i));
      const frame = new Graphics(), crop = new CropSprites(); object.addChild(frame, crop.container);
      const text = label(object, '', -76, 26, 8, 0xc7d2ba), mark = label(object, '', 65, -19, 13, palette.gold);
      interactive(object, { kind: 'plot', id: `p${String(i + 1).padStart(2, '0')}` }, 165, 60);
      this.container.addChild(object); this.plots.push({ frame, crop, text, mark });
    }
    // Place the shared panel at the greenhouse entrance, in the corridor rather
    // than over a cultivable plot or its crop label.
    const console = new Container(); console.position.copyFrom(irrigation_console_position);
    console.addChild(new Graphics().roundRect(-49, -40, 98, 70, 6).fill(0x354a40).stroke({ width: 3, color: 0x8f9f83 })
      .rect(-38, -31, 76, 39).fill(0x162f27).rect(-28, 17, 18, 5).fill(palette.cyan).rect(12, 17, 18, 5).fill(palette.gold));
    this.irrigation_text = label(console, 'IRRIGATION', 0, -22, 9, palette.green);
    this.irrigation_text.anchor.set(0.5, 0);
    const console_caption = label(console, '共用灌溉控制台', 0, 44, 10);
    console_caption.anchor.set(0.5, 0);
    interactive(console, { kind: 'object', id: 'irrigation_console' }, 120, 100);
    this.container.addChild(console);
    this.container.addChild(this.machine);
    for (const object of [
      { id: 'generator', x: 366, y: 610, w: 275, h: 125 },
      { id: 'water_plant', x: 1056, y: 605, w: 160, h: 125 },
      { id: 'core', x: 720, y: 599, w: 85, h: 75 },
      { id: 'drinking_point', x: drinking_position.x, y: drinking_position.y - 25, w: 64, h: 100 },
    ]) {
      const hit = new Container(); hit.position.set(object.x, object.y);
      interactive(hit, { kind: 'object', id: object.id }, object.w, object.h); this.container.addChild(hit);
    }
    this.draw_machines(0);
  }
  update(state: WorldState) {
    this.state = state;
    for (const [id, graphics] of this.resources) {
      const resource = state.resources[id as keyof typeof state.resources];
      const ratio = Math.max(0, Math.min(1, resource.value / resource.capacity));
      const low = resource.value < resource.warning; graphics.clear();
      if (id === 'water') {
        graphics.ellipse(4, 56, 55, 18).fill({ color: 0x20382d, alpha: 0.4 });
        graphics.roundRect(-44, -55, 88, 111, 13).fill(0x283e37).stroke({ width: 4, color: 0xa5b5a1 });
        graphics.rect(-32, -42, 64, 87).fill(0x1f322c);
        const height = 87 * ratio;
        graphics.rect(-32, 45 - height, 64, height).fill(low ? palette.gold : 0x64babc);
        graphics.rect(-32, 45 - height, 64, 3).fill(0xb6e3d1);
        for (let n = 0; n < 6; n++) graphics.rect(23, -38 + n * 15, 8, 2).fill(0xd1dfc7);
        graphics.ellipse(0, -55, 44, 10).fill(0x899e8f).stroke({ width: 3, color: 0xb1baa4 });
        graphics.rect(-9, -72, 18, 16).fill(0xb3b49a);
      } else if (id === 'oxygen') {
        graphics.ellipse(2, 49, 64, 20).fill({ color: 0x20382d, alpha: 0.4 });
        graphics.circle(0, 0, 55).fill(0x718a7c).stroke({ width: 5, color: 0xb4c0a8 });
        graphics.circle(0, 0, 42).fill(0x263d36).stroke({ width: 8, color: 0x40574a });
        if (ratio > 0) graphics.arc(0, 0, 42, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * ratio).stroke({ width: 8, color: low ? 0xde8471 : 0xa3d5cc });
        graphics.roundRect(-19, -14, 38, 28, 6).fill(0x829e87); graphics.rect(-6, -75, 12, 20).fill(0xa4b397);
        graphics.rect(-17, -78, 34, 6).fill(palette.gold);
      } else if (id === 'power') {
        graphics.roundRect(-30, -50, 60, 105, 5).fill(0x293d34).stroke({ width: 4, color: 0x85967b });
        for (let i = 0; i < 10; i++) {
          const lit = i < Math.ceil(ratio * 10);
          graphics.roundRect(-21, 43 - i * 9, 42, 6, 2).fill(lit ? palette.gold : 0x465146);
          if (lit) graphics.rect(-18, 43 - i * 9, 36, 2).fill(0xf1d590);
        }
      } else {
        graphics.poly([-53, 30, 0, 48, 54, 30, 54, 54, 0, 72, -53, 53]).fill(0x3b392a);
        for (let i = 0; i < Math.ceil(ratio * 8); i++) {
          const x = (i % 2) * 45 - 45, y = 25 - Math.floor(i / 2) * 25;
          graphics.roundRect(x, y, 43, 26, 3).fill(i % 2 ? 0xa7905d : 0xc3a66a).stroke({ width: 2, color: 0x685e3e });
          graphics.rect(x + 17, y, 6, 26).fill(0xddc38d); graphics.rect(x + 6, y + 7, 9, 5).fill(0x677553);
        }
      }
    }
    state.plots.forEach((plot, i) => {
      const visual = this.plots[i]; if (!visual) return;
      const color = plot.dead ? 0x675e52 : plot.consecutive_unirrigated_ticks >= C.irrigation.critical_after_ticks ? 0xd37561
        : plot.consecutive_unirrigated_ticks ? palette.gold : 0xa8bea0;
      visual.frame.clear().roundRect(-81, -24, 162, 46, 5).fill(0x243f33).stroke({ width: plot.consecutive_unirrigated_ticks ? 3 : 2, color });
      visual.frame.rect(-73, -17, 146, 31).fill(plot.dead ? 0x3a3830 : 0x4f6744);
      for (const x of [-60, -15, 30]) visual.frame.rect(x, 17, 30, 3).fill(plot.irrigated_last_tick ? 0x7bcec1 : 0x536349);
      visual.crop.set(plot.crop, plot.crop ? plot.progress_ticks / CROPS[plot.crop].maturity_ticks : 0, plot.mature, plot.dead);
      visual.text.text = `${plot.id.toUpperCase()}  ${plot.crop ? plot.crop.toUpperCase() : 'EMPTY'}`;
      visual.mark.text = plot.dead ? '✕' : plot.consecutive_unirrigated_ticks ? '!' : plot.mature ? '◆' : '';
    });
    const alive = state.plots.filter(plot => plot.crop && !plot.dead).length;
    this.irrigation_text.text = `SUPPLY ${state.last_summary?.irrigation.succeeded.length ?? 0}/${alive}`;
  }
  frame(time: number) {
    this.draw_machines(this.state?.failed ? 0 : time);
    this.plots.forEach((visual, index) => {
      const plot = this.state?.plots[index];
      visual.frame.alpha = plot && !plot.dead && plot.consecutive_unirrigated_ticks >= C.irrigation.critical_after_ticks
        ? 0.65 + Math.sin(time * 4) * 0.35 : 1;
    });
  }
  private draw_machines(time: number) {
    const g = this.machine; g.clear();
    for (let i = 0; i < C.generation.stations; i++) {
      const x = 270 + i * 64, y = 618;
      g.roundRect(x - 23, y - 55, 46, 88, 7).fill(0x3a4d3d).stroke({ width: 3, color: 0x9aa383 });
      g.roundRect(x - 15, y - 46, 30, 18, 3).fill(0x29392c); g.rect(x - 10, y - 26, 20, 7).fill(palette.gold);
      g.circle(x, y + 16, 17).fill(0x263b2e).stroke({ width: 3, color: 0xaeb997 });
      const work = this.state ? Object.values(this.state.crew)[i]?.work_this_tick ?? 0 : 0;
      const angle = time * work * 3;
      g.moveTo(x - Math.cos(angle) * 13, y + 16 - Math.sin(angle) * 13).lineTo(x + Math.cos(angle) * 13, y + 16 + Math.sin(angle) * 13).stroke({ width: 4, color: palette.gold });
    }
    // Physical cable: battery output → junction rail → all four generator stations.
    // Keep the rail below the units so each branch visibly reaches its base.
    g.moveTo(190, 650).lineTo(220, 650).lineTo(220, 665).lineTo(526, 665).stroke({ width: 5, color: 0xd2b579 });
    g.circle(190, 650, 4).fill(0xf0d393);
    for (const x of [270, 334, 398, 462]) {
      g.moveTo(x, 665).lineTo(x, 650).stroke({ width: 4, color: 0xd2b579 });
      g.circle(x, 650, 3).fill(0xf0d393);
    }
    const generation = this.state?.last_summary?.generation.actual ?? 0;
    if (generation > 0 && !this.state?.failed) {
      const x = 220 + ((time * 45 * generation) % 306);
      g.roundRect(x, 662, 15, 6, 2).fill(0xf2d794);
    }
    g.roundRect(984, 552, 145, 109, 8).fill(0x3b5447).stroke({ width: 4, color: 0x8faaa0 });
    for (const x of [1010, 1045, 1080]) {
      g.roundRect(x, 570, 21, 62, 7).fill(0x97b7a2).stroke({ width: 2, color: 0xc8d3b4 });
      g.rect(x + 5, 578, 11, 36).fill(0x4c8781);
    }
    g.moveTo(1129, 608).lineTo(1175, 608).lineTo(1175, 648).lineTo(1230, 648).stroke({ width: 10, color: 0x456155 });
    g.moveTo(1129, 608).lineTo(1175, 608).lineTo(1175, 648).lineTo(1230, 648).stroke({ width: 4, color: 0x86b9a9 });
    if (this.state?.last_summary?.water_plant.actual) {
      const rate = this.state.last_summary.water_plant.actual / C.water_plant.max_l_per_tick;
      const offset = (time * 90 * rate) % 140;
      const x = offset < 46 ? 1129 + offset : offset < 86 ? 1175 : 1175 + offset - 86;
      const y = offset < 46 ? 608 : offset < 86 ? 608 + offset - 46 : 648;
      g.circle(x, y, 4).fill(0xc2f0d7);
    }
    g.roundRect(685, 570, 70, 58, 7).fill(0x3d4e46).stroke({ width: 4, color: 0x9ba38e });
    g.rect(695, 580, 50, 27).fill(0x202e2b); g.rect(702, 587, 36, 3).fill(palette.purple); g.rect(702, 595, 24, 3).fill(palette.purple);
    // Water Plant drinking point. This is distinct from the Galley's meal
    // table, giving water refills a truthful, visible destination.
    g.roundRect(1148, 594, 44, 57, 6).fill(0x365149).stroke({ width: 3, color: 0x9bb8ab });
    g.roundRect(1155, 603, 30, 20, 4).fill(0x1d3934).stroke({ width: 2, color: 0x6dc7c4 });
    g.rect(1166, 625, 8, 12).fill(0x9fdad2); g.circle(1170, 639, 5).fill(0x74c8ca);
    g.roundRect(1154, 652, 32, 5, 2).fill(0x213a34);
    if (this.state && !this.state.failed) {
      if (this.state.resources.power.value < this.state.resources.power.warning) {
        g.roundRect(128, 568, 64, 110, 4).stroke({ color: palette.gold, width: 3, alpha: 0.5 + Math.sin(time * 4) * 0.4 });
      }
      if (this.state.last_summary?.oxygen_overflow) for (let i = 0; i < 3; i++) {
        const offset = (time * 16 + i * 11) % 35;
        g.circle(1210 + Math.sin(i * 2) * offset / 3, 815 - offset, 3 + offset / 5).fill({ color: 0xd8e5ce, alpha: (1 - offset / 35) * 0.4 });
      }
    }
  }
}
