import { useEffect, useRef } from "react";
import { audioLevel } from "../lib/voice";

// Visualización de ondas de voz: barras simétricas que siguen el nivel de audio.
export function Waveform({ active, bars = 48 }: { active: boolean; bars?: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const activeRef = useRef(active);
  activeRef.current = active;

  useEffect(() => {
    const canvas = ref.current!;
    const g = canvas.getContext("2d")!;
    let raf = 0;
    let t = 0;
    const hist = new Array(bars).fill(0);
    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = canvas.clientWidth * dpr;
      canvas.height = canvas.clientHeight * dpr;
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);
    const draw = () => {
      t += 0.05;
      const W = canvas.clientWidth;
      const H = canvas.clientHeight;
      g.clearRect(0, 0, W, H);
      const lvl = activeRef.current ? audioLevel() : 0;
      hist.shift();
      hist.push(lvl);
      const bw = W / bars;
      for (let i = 0; i < bars; i++) {
        const center = 1 - Math.abs(i - bars / 2) / (bars / 2);
        const idle = 0.06 + 0.04 * Math.sin(t + i * 0.45);
        const v = Math.max(idle, hist[i] * (0.4 + center * 0.9));
        const h = Math.max(2, v * H * 0.92);
        const x = i * bw + bw * 0.3;
        const grad = g.createLinearGradient(0, H / 2 - h / 2, 0, H / 2 + h / 2);
        grad.addColorStop(0, "rgba(196,181,253,0.15)");
        grad.addColorStop(0.5, `rgba(168,85,247,${0.45 + v * 0.55})`);
        grad.addColorStop(1, "rgba(196,181,253,0.15)");
        g.fillStyle = grad;
        g.beginPath();
        g.roundRect(x, H / 2 - h / 2, bw * 0.4, h, 3);
        g.fill();
      }
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, [bars]);

  return <canvas ref={ref} className="h-10 w-full" aria-hidden />;
}
