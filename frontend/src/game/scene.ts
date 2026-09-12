import { Application, Container, Graphics } from 'pixi.js';
import type { WorldState } from '../../../shared/types';
import { useGameStore } from '../store/gameStore';
import { CrewSprite } from './crew_sprite';
import { MAP, label, palette } from './style';
import { anchors, plot_position, resource_positions, type Position } from './waypoints';
import { WorldObjects } from './world_objects';

declare global { interface Window { __GREENHOUSE_DEBUG__?: Record<string, unknown> } }

function room(parent: Container, x: number, y: number, w: number, h: number, title: string, detail: string, tint: number) {
  const g = new Graphics(); parent.addChild(g);
  g.roundRect(x - 10, y - 5, w + 27, h + 24, 8).fill({ color: 0x28362a, alpha: 0.5 });
  g.rect(x, y, w, h).fill(tint).stroke({ width: 16, color: palette.wall });
  for (let cx = x + 7; cx < x + w - 12; cx += 32) for (let cy = y + 7; cy < y + h - 12; cy += 32) {
    g.rect(cx, cy, 30, 30).fill({ color: (Math.floor(cx / 32) + Math.floor(cy / 32)) % 2 ? 0x96a18a : 0x293e2e, alpha: 0.08 });
  }
  g.moveTo(x - 2, y).lineTo(x + w, y).lineTo(x + w, y + h).stroke({ width: 3, color: palette.rim });
  g.moveTo(x, y + h).lineTo(x, y).stroke({ width: 4, color: 0x647963 });
  for (let wx = x + 24; wx < x + w - 30; wx += 86) {
    g.rect(wx, y - 8, 46, 10).fill(0x9daf9a); g.rect(wx + 4, y - 5, 38, 3).fill(0xd8ddbf);
  }
  label(parent, title, x + 22, y + 18, 15, 0xe0e3c9);
  label(parent, detail, x + 22, y + 40, 9, 0xafbf9f);
}

function build_map(parent: Container) {
  const terrain = new Graphics(); parent.addChild(terrain);
  terrain.rect(-3000, -3000, 7500, 7500).fill(palette.earth);
  for (let i = 0; i < 300; i++) {
    const x = (i * 173.91) % 1900 - 230, y = (i * 89.41) % 1450 - 140;
    terrain.ellipse(x, y, 3 + i % 10, 2 + i % 4).fill({ color: i % 3 ? 0x8b6652 : 0x4f463c, alpha: 0.33 });
  }
  terrain.roundRect(57, 47, 1335, 992, 20).fill(0x524e40).stroke({ width: 5, color: 0x9c8770 });
  terrain.rect(93, 432, 1260, 69).fill(palette.corridor);
  terrain.rect(563, 463, 354, 313).fill(palette.corridor);
  terrain.rect(93, 711, 1260, 68).fill(palette.corridor);
  for (let x = 110; x < 1340; x += 32) {
    terrain.rect(x, 460, 16, 3).fill(0x9f9f77); terrain.rect(x, 740, 16, 3).fill(0x9f9f77);
  }
  for (let y = 500; y < 710; y += 32) terrain.rect(718, y, 3, 16).fill(0x899d80);
  room(parent, 90, 80, 1260, 350, '01 / GREENHOUSE', 'BOTANICAL ARRAY · CONTROLLED ENVIRONMENT', 0x62735a);
  room(parent, 90, 500, 470, 210, '02 / POWER BAY', 'HUMAN-POWERED ENERGY SYSTEM', 0x77765e);
  room(parent, 920, 500, 430, 210, '03 / WATER PLANT', 'OXYGEN–ENERGY CONVERSION', 0x5b746a);
  room(parent, 90, 775, 470, 225, '04 / GALLEY', 'COMMON TABLE · FOOD STORAGE', 0x79735a);
  room(parent, 620, 775, 250, 225, '05 / QUARTERS', 'CREW HABITAT', 0x707360);
  room(parent, 930, 775, 420, 225, '06 / LIFE SUPPORT', 'ATMOSPHERIC RESERVE', 0x637b6c);
  const decor = new Graphics(); parent.addChild(decor);
  // Door recesses join the rooms to the actual corridor network.
  for (const [x, y, width] of [[691, 430, 58], [361, 500, 60], [1080, 500, 60], [360, 775, 60], [716, 775, 60], [1080, 775, 60]]) {
    decor.rect(x, y - 9, width, 19).fill(palette.corridor);
    decor.rect(x - 4, y - 12, 5, 24).fill(0xa6a890); decor.rect(x + width, y - 12, 5, 24).fill(0xa6a890);
  }
  for (let i = 0; i < 5; i++) {
    const x = 342 + i * 183;
    decor.rect(x - 75, 118, 163, 5).fill(0xcdd6b2); decor.rect(x - 65, 124, 143, 3).fill({ color: 0xedf2c3, alpha: 0.4 });
  }
  // Seed cabinet and greenhouse wall plumbing are purely decorative.
  decor.roundRect(122, 337, 164, 61, 4).fill(0x3e5540).stroke({ width: 2, color: 0x9baa7b });
  for (let i = 0; i < 4; i++) decor.rect(135 + i * 37, 347, 25, 37).fill(0x95a271).stroke({ width: 2, color: 0x506244 });
  decor.moveTo(318, 125).lineTo(318, 410).lineTo(1290, 410).stroke({ width: 5, color: 0x8ea993 });
  // Shared dining table, seats and small habitat possessions.
  decor.roundRect(343, 854, 92, 71, 8).fill(0xb8a478).stroke({ width: 4, color: 0x675c41 });
  for (const [x, y] of [[327, 865], [446, 865], [327, 913], [446, 913]]) decor.roundRect(x, y, 19, 27, 4).fill(0x577365).stroke({ width: 2, color: 0xa6ac89 });
  for (const [x, y] of [[365, 876], [409, 902]]) {
    decor.circle(x, y, 10).fill(0xe0d8b9); decor.circle(x, y, 6).fill(0x879664);
  }
  for (let i = 0; i < 4; i++) {
    const x = 642 + (i % 2) * 104, y = 851 + Math.floor(i / 2) * 76;
    decor.roundRect(x, y, 81, 56, 5).fill(0x374b3b).stroke({ width: 3, color: 0xa6ad93 });
    decor.roundRect(x + 5, y + 6, 70, 42, 4).fill(i % 2 ? 0x869b8b : 0x7d9280);
    decor.roundRect(x + 8, y + 10, 19, 34, 3).fill(0xd4d3b4); decor.rect(x + 37, y + 8, 3, 38).fill(0xa7baa1);
  }
  decor.roundRect(968, 848, 108, 105, 5).fill(0x374c40).stroke({ width: 3, color: 0x96ad95 });
  for (let i = 0; i < 6; i++) decor.rect(979, 860 + i * 13, 83, 7).fill(i === 1 ? 0xaac690 : 0x658871);
  decor.moveTo(1080, 923).lineTo(1130, 923).lineTo(1130, 890).lineTo(1155, 890).stroke({ width: 7, color: 0x9fb498 });
  const core_caption = label(parent, 'CORE', 720, 640, 12, palette.purple);
  core_caption.anchor.set(0.5, 0);
  label(parent, 'MARS · HABITAT 01', 80, 1027, 13, 0xd2bba0);
  label(parent, 'SPACE GREENHOUSE', 1055, 1027, 13, 0xd2bba0);
}

export class GreenhouseScene {
  readonly root = new Container();
  readonly objects = new WorldObjects();
  private actors = new Map<string, CrewSprite>();
  private time = 0;
  private validation = new Graphics();
  private validation_targets: string[] = [];
  private validation_until = 0;
  private unsubscribe: () => void;
  private last_world: WorldState | null = null;
  private pointer: { x: number; y: number; moved: boolean } | null = null;
  private resize_observer: ResizeObserver;
  constructor(readonly app: Application, readonly host: HTMLElement) {
    build_map(this.root); this.root.addChild(this.objects.container, this.validation); app.stage.addChild(this.root);
    app.canvas.dataset.testid = 'world-canvas'; app.canvas.setAttribute('aria-label', '火星基地俯視世界：六區域、20 地塊與四種資源物件');
    app.canvas.style.display = 'block'; app.canvas.style.touchAction = 'none';
    host.appendChild(app.canvas);
    this.unsubscribe = useGameStore.subscribe((state, previous) => {
      if (state.world !== previous.world) this.update(state.world);
      if (state.camera !== previous.camera) this.layout();
      if (state.thoughts !== previous.thoughts) {
        const thought = state.thoughts[state.thoughts.length - 1];
        if (thought?.kind === 'validation_error' && thought.payload && typeof thought.payload === 'object') {
          const errors = (thought.payload as { errors?: { target?: unknown }[] }).errors;
          this.validation_targets = Array.isArray(errors) ? errors.map(error => error.target).filter((target): target is string => typeof target === 'string') : [];
          this.validation_until = this.time + 4.6;
        }
      }
    });
    this.resize_observer = new ResizeObserver(() => this.layout()); this.resize_observer.observe(host);
    app.canvas.addEventListener('wheel', this.wheel, { passive: false });
    app.canvas.addEventListener('pointerleave', this.leave);
    app.canvas.addEventListener('pointerdown', this.down); window.addEventListener('pointermove', this.move); window.addEventListener('pointerup', this.up);
    app.ticker.add(this.frame); this.update(useGameStore.getState().world); this.layout();
  }
  world_to_screen(position: Position): Position { return { x: this.root.x + position.x * this.root.scale.x, y: this.root.y + position.y * this.root.scale.y }; }
  private layout() {
    const w = this.host.clientWidth, h = this.host.clientHeight;
    this.app.renderer.resize(w, h);
    const camera = useGameStore.getState().camera;
    const scale = Math.min((w - 70) / MAP.width, (h - 110) / MAP.height) * camera.zoom;
    this.root.scale.set(scale); this.root.position.set((w - MAP.width * scale) / 2 + camera.x, (h - MAP.height * scale) / 2 + camera.y - 5);
    const screen = Object.fromEntries(Object.entries({ ...anchors, ...resource_positions }).map(([key, point]) => [key, this.world_to_screen(point)]));
    const stored = useGameStore.getState().anchors;
    if (JSON.stringify(stored) !== JSON.stringify(screen)) useGameStore.getState().set_anchors(screen);
    window.dispatchEvent(new CustomEvent('greenhouse:anchors', { detail: screen }));
    this.debug();
  }
  private update(world: WorldState | null) {
    if (!world) return;
    this.last_world = world; this.objects.update(world);
    Object.values(world.crew).forEach((crew, index) => {
      if (!this.actors.has(crew.id)) { const actor = new CrewSprite(crew.id, index); this.actors.set(crew.id, actor); this.root.addChild(actor.container); }
      this.actors.get(crew.id)!.update(crew, world);
    });
    this.root.alpha = world.failed ? 0.55 : 1; this.debug();
  }
  private debug() {
    window.__GREENHOUSE_DEBUG__ = { ready: true, plot_count: this.last_world?.plots.length ?? 0,
      targets: Object.fromEntries(Object.entries(resource_positions).map(([key, point]) => [key, this.world_to_screen(point)])),
      plot_positions: this.last_world?.plots.map((plot, index) => ({ id: plot.id, ...this.world_to_screen(plot_position(index)) })),
      crew_positions: [...this.actors].map(([id, actor]) => ({ id, ...this.world_to_screen(actor.container.position) })),
      anchors: useGameStore.getState().anchors, tick: this.last_world?.tick,
      paused: this.last_world?.paused ?? true, speed: this.last_world?.speed ?? 1,
    };
  }
  private frame = () => {
    const raw_delta = Math.min(this.app.ticker.deltaMS / 1000, 0.1);
    const world = this.last_world;
    // `paused` and `speed` are authoritative WorldState fields from either
    // the mock recording or the real backend. Every world-facing animation
    // consumes the same simulation delta, never a separate wall clock.
    const simulation_delta = world && !world.paused && !world.failed ? raw_delta * world.speed : 0;
    this.time += simulation_delta;
    this.objects.frame(this.time); this.actors.forEach(actor => actor.frame(simulation_delta, this.time));
    this.validation.clear();
    if (this.time < this.validation_until) for (const target of this.validation_targets) {
      let position: Position | undefined, width = 100, height = 100;
      const plot_index = this.last_world?.plots.findIndex(plot => plot.id === target) ?? -1;
      if (plot_index >= 0) { position = plot_position(plot_index); width = 172; height = 54; }
      else if (this.actors.has(target)) { position = this.actors.get(target)!.container.position; width = 48; height = 70; }
      else if (target in resource_positions) position = resource_positions[target as keyof typeof resource_positions];
      else if (target.includes('generation')) { position = { x: 365, y: 610 }; width = 280; }
      else if (target.includes('water_production')) position = { x: 1055, y: 605 };
      if (position) this.validation.roundRect(position.x - width / 2, position.y - height / 2, width, height, 5).stroke({ width: 4, color: 0xf07264, alpha: 0.65 + Math.sin(this.time * 7) * 0.25 });
    }
    if (simulation_delta > 0 && Math.floor(this.time * 4) !== Math.floor((this.time - simulation_delta) * 4)) this.debug();
  };
  private wheel = (event: WheelEvent) => { event.preventDefault(); const store = useGameStore.getState(); store.set_camera({ zoom: Math.max(0.75, Math.min(2, store.camera.zoom * (event.deltaY > 0 ? 0.94 : 1.06))) }); };
  private down = (event: PointerEvent) => { if (event.button === 0) this.pointer = { x: event.clientX, y: event.clientY, moved: false }; };
  private move = (event: PointerEvent) => {
    if (!this.pointer) return;
    const dx = event.clientX - this.pointer.x, dy = event.clientY - this.pointer.y;
    if (!this.pointer.moved && Math.abs(dx) + Math.abs(dy) < 5) return;
    this.pointer = { x: event.clientX, y: event.clientY, moved: true };
    const store = useGameStore.getState(); store.set_hover(null); store.set_camera({ x: store.camera.x + dx, y: store.camera.y + dy });
  };
  private up = () => { this.pointer = null; };
  private leave = () => { useGameStore.getState().set_hover(null); };
  destroy() {
    this.unsubscribe(); this.resize_observer.disconnect(); this.app.ticker.remove(this.frame);
    this.app.canvas.removeEventListener('wheel', this.wheel); this.app.canvas.removeEventListener('pointerdown', this.down);
    this.app.canvas.removeEventListener('pointerleave', this.leave);
    window.removeEventListener('pointermove', this.move); window.removeEventListener('pointerup', this.up);
    this.app.destroy(true, { children: true }); delete window.__GREENHOUSE_DEBUG__;
  }
}
