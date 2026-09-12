import { Assets, Container, Sprite, Texture } from 'pixi.js';

const textures = new Map<string, Promise<Texture>>();
export class CropSprites {
  readonly container = new Container();
  private crop: string | null = null;
  private generation = 0;
  private dead = false;
  set(crop: string | null, progress: number, mature: boolean, dead: boolean) {
    const stage = mature ? 3 : Math.min(2, Math.floor(progress * 3));
    this.container.scale.set([0.55, 0.7, 0.86, 1][stage]);
    this.dead = dead; this.container.alpha = dead ? 0.7 : 1;
    this.container.children.forEach(child => { if (child instanceof Sprite) child.tint = dead ? 0x443d30 : 0xffffff; });
    if (crop === this.crop) return;
    this.crop = crop; const generation = ++this.generation;
    this.container.removeChildren().forEach(child => child.destroy());
    if (!crop) return;
    if (!textures.has(crop)) textures.set(crop, Assets.load<Texture>(`/crops/${encodeURIComponent(crop)}.svg`));
    textures.get(crop)!.then(texture => {
      if (this.container.destroyed || generation !== this.generation) return;
      for (const x of [-44, 0, 44]) {
        const sprite = new Sprite(texture); sprite.anchor.set(0.5); sprite.position.set(x, -2);
        sprite.width = 40; sprite.height = 36; sprite.tint = this.dead ? 0x443d30 : 0xffffff; this.container.addChild(sprite);
      }
    }).catch(() => { /* Missing crop art stays an explicit bare trough; no crop-specific logic. */ });
  }
}
