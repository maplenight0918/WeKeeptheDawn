import { useEffect, useRef, useState } from 'react';
import { Application } from 'pixi.js';
import { GreenhouseScene } from './scene';

export default function GameView() {
  const host = useRef<HTMLDivElement>(null);
  const [error, set_error] = useState('');
  useEffect(() => {
    let cancelled = false, scene: GreenhouseScene | null = null;
    const app = new Application();
    document.fonts.load('12px "Noto Sans TC"', '共用灌溉控制台').then(() => app.init({ background: '#735347', antialias: true, resolution: Math.min(window.devicePixelRatio || 1, 2), autoDensity: true, preference: 'webgl' }))
      .then(() => { if (cancelled) { app.destroy(true); return; } if (host.current) scene = new GreenhouseScene(app, host.current); })
      .catch(() => { if (!cancelled) set_error('無法啟動基地畫面，請確認瀏覽器支援 WebGL。'); });
    return () => { cancelled = true; scene?.destroy(); };
  }, []);
  return <div ref={host} className="world-scene" data-testid="game-view" style={{ position: 'fixed', inset: 0, background: '#735347' }}>
    {error && <p role="alert" style={{ color: '#eee8d8', position: 'absolute', top: '50%', left: '25%' }}>{error}</p>}
  </div>;
}
