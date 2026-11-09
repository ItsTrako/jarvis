// Núcleo de J.A.R.V.I.S. (WebGL) - módulo autónomo para la web del proyecto.
// createOrb(canvas) -> { setState(name), setLevel(0..1), destroy() }
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

const PAL = {
  idle:      { core: [0.97, 0.95, 1], mid: [0.77, 0.71, 0.99], rim: [0.55, 0.36, 0.96], energy: 0.1, spin: 0 },
  listening: { core: [1, 0.97, 1], mid: [0.85, 0.71, 1], rim: [0.66, 0.33, 0.97], energy: 0.45, spin: 0.6 },
  thinking:  { core: [0.98, 0.95, 1], mid: [0.75, 0.66, 1], rim: [0.48, 0.3, 0.95], energy: 0.75, spin: 2.2 },
  speaking:  { core: [1, 1, 1], mid: [0.87, 0.84, 1], rim: [0.66, 0.33, 0.97], energy: 0.5, spin: 0.8 },
};

export function createOrb(canvas, { state = "idle", reducedMotion, manual = false } = {}) {
  const gl = canvas.getContext("webgl", { premultipliedAlpha: true, alpha: true, antialias: true, preserveDrawingBuffer: true });
  if (!gl) return null;
  const sh = (t, s) => { const o = gl.createShader(t); gl.shaderSource(o, s); gl.compileShader(o);
    if (!gl.getShaderParameter(o, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(o)); return o; };
  const prog = gl.createProgram();
  gl.attachShader(prog, sh(gl.VERTEX_SHADER, VERT));
  gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, FRAG));
  gl.linkProgram(prog); gl.useProgram(prog);
  const buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
  const loc = gl.getAttribLocation(prog, "a"); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
  gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
  const U = {}; ["uRes", "uTime", "uLevel", "uEnergy", "uSpin", "uDim", "uCore", "uMid", "uRim"].forEach((n) => (U[n] = gl.getUniformLocation(prog, n)));
  const reduce = reducedMotion ?? matchMedia("(prefers-reduced-motion: reduce)").matches;
  const cur = JSON.parse(JSON.stringify(PAL[state]));
  let target = PAL[state], level = 0, lvl = 0, t = 0, last = performance.now(), raf = 0, visible = true;
  const resize = () => { const d = Math.min(devicePixelRatio || 1, 2); const w = Math.max(1, Math.round(canvas.clientWidth * d));
    canvas.width = w; canvas.height = Math.max(1, Math.round(canvas.clientHeight * d)); gl.viewport(0, 0, canvas.width, canvas.height); };
  resize(); const ro = new ResizeObserver(resize); ro.observe(canvas);
  const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; if (visible && !raf && !manual) raf = requestAnimationFrame(frame); });
  io.observe(canvas);
  const lerp = (a, b, k) => a + (b - a) * k;
  function frame(now) {
    raf = 0;
    const dt = Math.min(0.05, (now - last) / 1000); last = now;
    draw(dt);
    if (visible && !manual) raf = requestAnimationFrame(frame);
  }
  function draw(dt) {
    const k = 1 - Math.pow(0.02, dt);
    for (const c of ["core", "mid", "rim"]) for (let i = 0; i < 3; i++) cur[c][i] = lerp(cur[c][i], target[c][i], k);
    cur.energy = lerp(cur.energy, target.energy, k); cur.spin = lerp(cur.spin, target.spin, k);
    lvl += (level - lvl) * Math.min(1, dt * 14);
    t += dt * (reduce ? 0.12 : 1) * (1 + cur.spin * 0.25);
    gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT);
    gl.uniform2f(U.uRes, canvas.width, canvas.height); gl.uniform1f(U.uTime, t); gl.uniform1f(U.uLevel, lvl);
    gl.uniform1f(U.uEnergy, cur.energy); gl.uniform1f(U.uSpin, cur.spin); gl.uniform1f(U.uDim, 1);
    gl.uniform3fv(U.uCore, cur.core); gl.uniform3fv(U.uMid, cur.mid); gl.uniform3fv(U.uRim, cur.rim);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  }
  if (!manual) raf = requestAnimationFrame(frame);
  return {
    setState(s) { if (PAL[s]) target = PAL[s]; },
    setLevel(v) { level = Math.max(0, Math.min(1, v)); },
    step(dt) { draw(dt); },  // modo manual: un fotograma con un paso de tiempo exacto
    destroy() { cancelAnimationFrame(raf); ro.disconnect(); io.disconnect(); },
  };
}
