import { useEffect, useRef } from "react";
import { audioLevel } from "../lib/voice";
import type { AgentState } from "../lib/store";

// Núcleo de JARVIS: esfera de energía en Canvas 2D que reacciona al estado y al audio.
// idle: respiración lenta · listening: pulsa con el micrófono · thinking: órbitas rápidas
// speaking: la membrana ondula con la voz.

const PALETTE: Record<AgentState, { core: string; mid: string; rim: string; speed: number }> = {
  idle: { core: "245,243,255", mid: "196,181,253", rim: "139,92,246", speed: 0.25 },
  listening: { core: "250,245,255", mid: "216,180,254", rim: "168,85,247", speed: 0.6 },
  transcribing: { core: "245,243,255", mid: "196,181,253", rim: "168,85,247", speed: 1.0 },
  thinking: { core: "245,243,255", mid: "196,181,253", rim: "139,92,246", speed: 1.35 },
  speaking: { core: "255,255,255", mid: "221,214,254", rim: "168,85,247", speed: 0.7 },
  offline: { core: "163,154,175", mid: "111,102,128", rim: "70,60,90", speed: 0.1 },
};

function noise(x: number, t: number) {
  return (Math.sin(x * 3 + t * 1.3) + Math.sin(x * 5 - t * 0.9) * 0.6 + Math.sin(x * 9 + t * 2.1) * 0.25) / 1.85;
}

export function Orb({ state, size = 320 }: { state: AgentState; size?: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const stateRef = useRef(state);
  stateRef.current = state;

  useEffect(() => {
    const canvas = ref.current!;
    const g = canvas.getContext("2d")!;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let raf = 0;
    let t = 0;
    let smooth = 0;
    let energy = 0;
    let rot = 0;
    let colors = { ...PALETTE.idle };
    const particles = Array.from({ length: 70 }, () => ({
      a: Math.random() * Math.PI * 2, r: 0.62 + Math.random() * 0.5, s: 0.15 + Math.random() * 0.6,
      z: Math.random(), size: 0.4 + Math.random() * 1.3,
    }));

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = canvas.clientWidth;
      canvas.width = w * dpr;
      canvas.height = w * dpr;
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);

    const draw = () => {
      const S = canvas.clientWidth;
      const c = S / 2;
      const st = stateRef.current;
      const target = PALETTE[st];
      colors = target;
      const lvl = audioLevel();
      smooth += (lvl - smooth) * 0.25;
      const wantEnergy = st === "thinking" ? 0.55 : st === "listening" ? 0.35 + smooth : st === "speaking" ? 0.3 + smooth * 1.2 : st === "transcribing" ? 0.5 : 0.12;
      energy += (wantEnergy - energy) * 0.06;
      const dt = reduce ? 0.002 : 0.016;
      t += dt * (0.6 + colors.speed);
      rot += dt * colors.speed * 0.6;

      g.clearRect(0, 0, S, S);
      const R = S * 0.24;

      // Halo ambiental
      const halo = g.createRadialGradient(c, c, R * 0.4, c, c, S * 0.5);
      halo.addColorStop(0, `rgba(${colors.rim},${0.22 + energy * 0.25})`);
      halo.addColorStop(0.5, `rgba(${colors.rim},${0.07 + energy * 0.08})`);
      halo.addColorStop(1, "rgba(8,6,13,0)");
      g.fillStyle = halo;
      g.fillRect(0, 0, S, S);

      // Anillos orbitales (arcos con huecos)
      const rings = [
        { r: R * 1.42, w: 1, a: 0.35, gaps: 3, dir: 1 },
        { r: R * 1.62, w: 1.4, a: 0.22, gaps: 5, dir: -0.7 },
        { r: R * 1.85, w: 0.8, a: 0.14, gaps: 2, dir: 0.45 },
      ];
      rings.forEach((ring, i) => {
        const span = (Math.PI * 2) / ring.gaps;
        for (let k = 0; k < ring.gaps; k++) {
          const start = rot * ring.dir * (1 + i * 0.3) + k * span;
          g.beginPath();
          g.arc(c, c, ring.r, start, start + span * (0.62 + 0.18 * Math.sin(t + k)));
          g.strokeStyle = `rgba(${colors.mid},${ring.a + energy * 0.25})`;
          g.lineWidth = ring.w;
          g.stroke();
        }
      });

      // Marcas de escala en el anillo exterior
      g.save();
      g.translate(c, c);
      g.rotate(-rot * 0.25);
      for (let i = 0; i < 72; i++) {
        const a = (i / 72) * Math.PI * 2;
        const long = i % 6 === 0;
        const r1 = R * 2.02;
        const r2 = r1 + (long ? 7 : 3);
        g.beginPath();
        g.moveTo(Math.cos(a) * r1, Math.sin(a) * r1);
        g.lineTo(Math.cos(a) * r2, Math.sin(a) * r2);
        g.strokeStyle = `rgba(${colors.mid},${long ? 0.28 : 0.1})`;
        g.lineWidth = 1;
        g.stroke();
      }
      g.restore();

      // Partículas orbitando
      particles.forEach((p) => {
        p.a += dt * p.s * (0.4 + colors.speed);
        const rr = R * (p.r + 0.9) * (1 + energy * 0.08);
        const x = c + Math.cos(p.a) * rr;
        const y = c + Math.sin(p.a) * rr * (0.35 + p.z * 0.65);
        const alpha = 0.15 + p.z * 0.5 * (0.5 + energy);
        g.beginPath();
        g.arc(x, y, p.size * (0.6 + p.z), 0, Math.PI * 2);
        g.fillStyle = `rgba(${colors.mid},${alpha})`;
        g.fill();
      });

      // Membrana (blob) que ondula con el audio
      const amp = R * (0.035 + energy * 0.12 + smooth * 0.18);
      for (let layer = 2; layer >= 0; layer--) {
        g.beginPath();
        const N = 96;
        for (let i = 0; i <= N; i++) {
          const a = (i / N) * Math.PI * 2;
          const d = noise(a + layer * 0.7, t * (1 + layer * 0.25)) * amp * (1 - layer * 0.25);
          const rr = R * (1 + layer * 0.07) + d;
          const x = c + Math.cos(a) * rr;
          const y = c + Math.sin(a) * rr;
          i === 0 ? g.moveTo(x, y) : g.lineTo(x, y);
        }
        g.closePath();
        if (layer === 0) {
          const core = g.createRadialGradient(c - R * 0.25, c - R * 0.3, R * 0.05, c, c, R * 1.08);
          core.addColorStop(0, `rgba(${colors.core},0.98)`);
          core.addColorStop(0.28, `rgba(${colors.mid},0.85)`);
          core.addColorStop(0.7, `rgba(${colors.rim},0.75)`);
          core.addColorStop(1, `rgba(46,16,101,0.9)`);
          g.fillStyle = core;
          g.shadowColor = `rgba(${colors.rim},0.9)`;
          g.shadowBlur = 40 + energy * 50;
          g.fill();
          g.shadowBlur = 0;
        } else {
          g.strokeStyle = `rgba(${colors.mid},${0.18 / layer + energy * 0.15})`;
          g.lineWidth = 1;
          g.stroke();
        }
      }

      // Brillo interior y filamentos
      g.save();
      g.globalCompositeOperation = "lighter";
      for (let i = 0; i < 4; i++) {
        const a = t * (0.5 + i * 0.2) + i * 1.6;
        g.beginPath();
        g.ellipse(c, c, R * (0.75 - i * 0.1), R * (0.22 + 0.1 * Math.sin(t + i)), a, 0, Math.PI * 2);
        g.strokeStyle = `rgba(${colors.core},${0.08 + energy * 0.12})`;
        g.lineWidth = 1;
        g.stroke();
      }
      const spec = g.createRadialGradient(c - R * 0.35, c - R * 0.4, 0, c - R * 0.35, c - R * 0.4, R * 0.6);
      spec.addColorStop(0, "rgba(255,255,255,0.35)");
      spec.addColorStop(1, "rgba(255,255,255,0)");
      g.fillStyle = spec;
      g.beginPath();
      g.arc(c, c, R, 0, Math.PI * 2);
      g.fill();
      g.restore();

      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, []);

  return (
    <canvas
      ref={ref}
      style={{ width: size, maxWidth: "100%", aspectRatio: "1 / 1" }}
      aria-label={`Núcleo de JARVIS: ${state}`}
      role="img"
    />
  );
}
