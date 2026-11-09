import { useEffect, useRef, useState } from "react";
import type { AgentState } from "../lib/store";
import { audioLevel } from "../lib/voice";
import { Orb } from "./Orb";

// Núcleo de JARVIS en WebGL: esfera de plasma 3D con ruido simplex, iluminación, brillo de borde,
// filamentos de energía, membrana que ondula con la voz, anillos orbitales y chispas.

const VERT = `attribute vec2 a;void main(){gl_Position=vec4(a,0.,1.);}`;

const FRAG = `
precision highp float;
uniform vec2 uRes; uniform float uTime, uLevel, uEnergy, uSpin, uDim;
uniform vec3 uCore, uMid, uRim;

vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 mod289(vec4 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 permute(vec4 x){return mod289(((x*34.0)+1.0)*x);}
vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-0.85373472095314*r;}
float snoise(vec3 v){
  const vec2 C=vec2(1.0/6.0,1.0/3.0); const vec4 D=vec4(0.0,0.5,1.0,2.0);
  vec3 i=floor(v+dot(v,C.yyy)); vec3 x0=v-i+dot(i,C.xxx);
  vec3 g=step(x0.yzx,x0.xyz); vec3 l=1.0-g; vec3 i1=min(g.xyz,l.zxy); vec3 i2=max(g.xyz,l.zxy);
  vec3 x1=x0-i1+C.xxx; vec3 x2=x0-i2+C.yyy; vec3 x3=x0-D.yyy;
  i=mod289(i);
  vec4 p=permute(permute(permute(i.z+vec4(0.0,i1.z,i2.z,1.0))+i.y+vec4(0.0,i1.y,i2.y,1.0))+i.x+vec4(0.0,i1.x,i2.x,1.0));
  float n_=0.142857142857; vec3 ns=n_*D.wyz-D.xzx;
  vec4 j=p-49.0*floor(p*ns.z*ns.z); vec4 x_=floor(j*ns.z); vec4 y_=floor(j-7.0*x_);
  vec4 x=x_*ns.x+ns.yyyy; vec4 y=y_*ns.x+ns.yyyy; vec4 h=1.0-abs(x)-abs(y);
  vec4 b0=vec4(x.xy,y.xy); vec4 b1=vec4(x.zw,y.zw);
  vec4 s0=floor(b0)*2.0+1.0; vec4 s1=floor(b1)*2.0+1.0; vec4 sh=-step(h,vec4(0.0));
  vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy; vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
  vec3 p0=vec3(a0.xy,h.x); vec3 p1=vec3(a0.zw,h.y); vec3 p2=vec3(a1.xy,h.z); vec3 p3=vec3(a1.zw,h.w);
  vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
  p0*=norm.x; p1*=norm.y; p2*=norm.z; p3*=norm.w;
  vec4 m=max(0.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0); m=m*m;
  return 42.0*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
}
float fbm(vec3 p){float a=0.5,s=0.0;for(int i=0;i<4;i++){s+=a*snoise(p);p*=2.03;a*=0.5;}return s;}

void main(){
  vec2 p=(gl_FragCoord.xy-0.5*uRes)/min(uRes.x,uRes.y);
  float d=length(p); float ang=atan(p.y,p.x); float t=uTime;
  float R=0.235+0.008*sin(t*1.1)+0.035*uLevel;
  float wob=snoise(vec3(cos(ang)*1.5,sin(ang)*1.5,t*0.7))*(0.008+0.035*uEnergy+0.07*uLevel)
           +snoise(vec3(cos(ang)*4.0,sin(ang)*4.0,t*1.3))*0.025*uLevel;
  float r=R+wob;
  vec3 col=vec3(0.0); float alpha=0.0;

  // Halo exterior
  float g=exp(-max(d-r,0.0)*7.0)*(0.38+0.55*uEnergy+0.6*uLevel);
  float g2=exp(-max(d-r,0.0)*24.0)*(0.6+uLevel);
  col+=uRim*g*0.6+mix(uRim,uMid,0.5)*g2*0.45; alpha+=g*0.5+g2*0.4;

  // Esfera de plasma
  float inside=smoothstep(r+0.005,r-0.003,d);
  if(inside>0.0){
    float z=sqrt(max(0.0,1.0-(d*d)/(r*r)));
    vec3 n=normalize(vec3(p/r,z));
    float sp=t*(0.12+0.35*uEnergy);
    vec3 q=vec3(n.x*cos(sp)-n.z*sin(sp),n.y,n.x*sin(sp)+n.z*cos(sp));
    float f=fbm(q*1.35+vec3(0.0,t*0.10,t*0.05));
    float f2=fbm(q*2.8-vec3(t*0.16,0.0,0.0)+f*1.4);
    float plasma=smoothstep(-0.45,0.9,f+0.6*f2);
    vec3 deep=vec3(0.13,0.03,0.33);
    vec3 base=mix(deep,uRim*1.05,plasma);
    base=mix(base,uMid,plasma*plasma*0.55);
    vec3 L=normalize(vec3(-0.45,0.55,0.75));
    float diff=max(dot(n,L),0.0);
    float spec=pow(max(dot(reflect(-L,n),vec3(0.0,0.0,1.0)),0.0),30.0);
    float fres=pow(1.0-z,2.2);
    vec3 c=base*(0.55+0.5*diff);
    c+=uCore*pow(z,5.0)*(0.28+0.4*uLevel);                 // núcleo luminoso
    c+=vec3(spec*0.55);
    c+=mix(uRim,uMid,0.5)*fres*(1.1+1.4*uLevel);           // borde eléctrico
    float fil=pow(abs(sin(f*6.0+f2*2.5+t*1.1)),26.0)*(0.45+uEnergy+uLevel);
    c+=mix(uMid,uCore,0.6)*fil*0.6*z;
    col=mix(col,c,inside); alpha=mix(alpha,1.0,inside);
  }

  // Anillos orbitales con huecos
  for(int k=0;k<3;k++){
    float fk=float(k);
    float rr=0.335+fk*0.048+0.003*sin(t*0.8+fk);
    float w=0.0016+fk*0.0005;
    float ring=exp(-pow((d-rr)/w,2.0));
    float dir=mod(fk,2.0)<0.5?1.0:-1.0;
    float rot=t*(0.22+0.12*fk)*dir*(1.0+uSpin);
    float seg=smoothstep(-0.3,0.3,sin((3.0+fk*2.0)*(ang+rot)));
    float a=ring*seg*(0.42-fk*0.1+0.45*uEnergy);
    col+=uMid*a; alpha+=a;
  }
  // Marcas de escala
  float tr=0.478;
  float tk=exp(-pow((d-tr)/0.006,2.0))*step(0.82,fract((ang/6.28318+t*0.004)*72.0));
  col+=uMid*tk*0.22; alpha+=tk*0.22;
  // Chispas orbitando
  float ann=smoothstep(0.25,0.31,d)*smoothstep(0.49,0.40,d);
  float sn=snoise(vec3(cos(ang+t*0.08)*7.0,sin(ang+t*0.08)*7.0,d*26.0-t*0.6));
  float spark=pow(max(sn,0.0),12.0)*ann*(0.7+uEnergy+uLevel);
  col+=uCore*spark; alpha+=spark;

  alpha=clamp(alpha,0.0,1.0)*uDim; col*=uDim;
  col=min(col,vec3(max(alpha,0.0001))*1.2);
  gl_FragColor=vec4(col,alpha);
}`;

type Palette = { core: number[]; mid: number[]; rim: number[]; energy: number; spin: number; dim: number };
const PAL: Record<AgentState, Palette> = {
  idle: { core: [0.97, 0.95, 1], mid: [0.77, 0.71, 0.99], rim: [0.55, 0.36, 0.96], energy: 0.1, spin: 0, dim: 1 },
  listening: { core: [1, 0.97, 1], mid: [0.85, 0.71, 1], rim: [0.66, 0.33, 0.97], energy: 0.45, spin: 0.6, dim: 1 },
  transcribing: { core: [0.97, 0.95, 1], mid: [0.77, 0.71, 0.99], rim: [0.66, 0.33, 0.97], energy: 0.6, spin: 1.2, dim: 1 },
  thinking: { core: [0.98, 0.95, 1], mid: [0.75, 0.66, 1], rim: [0.48, 0.3, 0.95], energy: 0.75, spin: 2.2, dim: 1 },
  speaking: { core: [1, 1, 1], mid: [0.87, 0.84, 1], rim: [0.66, 0.33, 0.97], energy: 0.5, spin: 0.8, dim: 1 },
  offline: { core: [0.64, 0.6, 0.69], mid: [0.44, 0.4, 0.5], rim: [0.27, 0.23, 0.35], energy: 0, spin: 0, dim: 0.55 },
};

function compile(gl: WebGLRenderingContext, type: number, src: string) {
  const s = gl.createShader(type)!;
  gl.shaderSource(s, src);
  gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s) || "shader");
  return s;
}

export function OrbGL({ state, size = 320 }: { state: AgentState; size?: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const stateRef = useRef(state);
  stateRef.current = state;
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const canvas = ref.current!;
    const gl = canvas.getContext("webgl", { premultipliedAlpha: true, alpha: true, antialias: true });
    if (!gl) {
      setFailed(true);
      return;
    }
    let prog: WebGLProgram;
    try {
      prog = gl.createProgram()!;
      gl.attachShader(prog, compile(gl, gl.VERTEX_SHADER, VERT));
      gl.attachShader(prog, compile(gl, gl.FRAGMENT_SHADER, FRAG));
      gl.linkProgram(prog);
      if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error("link");
    } catch (e) {
      console.warn("OrbGL:", e);
      setFailed(true);
      return;
    }
    gl.useProgram(prog);
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(prog, "a");
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    const u = (n: string) => gl.getUniformLocation(prog, n);
    const U = { res: u("uRes"), time: u("uTime"), level: u("uLevel"), energy: u("uEnergy"), spin: u("uSpin"),
                dim: u("uDim"), core: u("uCore"), mid: u("uMid"), rim: u("uRim") };

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const cur = { ...PAL.idle, core: [...PAL.idle.core], mid: [...PAL.idle.mid], rim: [...PAL.idle.rim] };
    let lvl = 0;
    let t = 0;
    let last = performance.now();
    let raf = 0;

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = Math.max(1, Math.round(canvas.clientWidth * dpr));
      canvas.width = w;
      canvas.height = w;
      gl.viewport(0, 0, w, w);
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);

    const lerp = (a: number, b: number, k: number) => a + (b - a) * k;
    const frame = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const target = PAL[stateRef.current];
      const k = 1 - Math.pow(0.02, dt); // transición suave entre estados (~1 s)
      (["core", "mid", "rim"] as const).forEach((c) => {
        for (let i = 0; i < 3; i++) cur[c][i] = lerp(cur[c][i], target[c][i], k);
      });
      cur.energy = lerp(cur.energy, target.energy, k);
      cur.spin = lerp(cur.spin, target.spin, k);
      cur.dim = lerp(cur.dim, target.dim, k);
      lvl += (audioLevel() - lvl) * Math.min(1, dt * 14);
      t += dt * (reduce ? 0.15 : 1) * (1 + cur.spin * 0.25);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.uniform2f(U.res, canvas.width, canvas.height);
      gl.uniform1f(U.time, t);
      gl.uniform1f(U.level, lvl);
      gl.uniform1f(U.energy, cur.energy);
      gl.uniform1f(U.spin, cur.spin);
      gl.uniform1f(U.dim, cur.dim);
      gl.uniform3fv(U.core, cur.core);
      gl.uniform3fv(U.mid, cur.mid);
      gl.uniform3fv(U.rim, cur.rim);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    const lost = (e: Event) => {
      e.preventDefault();
      setFailed(true);
    };
    canvas.addEventListener("webglcontextlost", lost);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      canvas.removeEventListener("webglcontextlost", lost);
    };
  }, []);

  if (failed) return <Orb state={state} size={size} />;
  return (
    <canvas ref={ref} style={{ width: size, maxWidth: "100%", aspectRatio: "1 / 1" }}
      aria-label={`Núcleo de JARVIS: ${state}`} role="img" />
  );
}
