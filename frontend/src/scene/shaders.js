// GLSL shaders for the 3D research core.
// Simplex noise: "webgl-noise" by Ian McEwan & Ashima Arts (MIT License).

const SIMPLEX_NOISE = /* glsl */ `
vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec4 mod289(vec4 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec4 permute(vec4 x) { return mod289(((x * 34.0) + 1.0) * x); }
vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }

float snoise(vec3 v) {
  const vec2 C = vec2(1.0 / 6.0, 1.0 / 3.0);
  const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);

  vec3 i = floor(v + dot(v, C.yyy));
  vec3 x0 = v - i + dot(i, C.xxx);

  vec3 g = step(x0.yzx, x0.xyz);
  vec3 l = 1.0 - g;
  vec3 i1 = min(g.xyz, l.zxy);
  vec3 i2 = max(g.xyz, l.zxy);

  vec3 x1 = x0 - i1 + C.xxx;
  vec3 x2 = x0 - i2 + C.yyy;
  vec3 x3 = x0 - D.yyy;

  i = mod289(i);
  vec4 p = permute(permute(permute(
            i.z + vec4(0.0, i1.z, i2.z, 1.0))
          + i.y + vec4(0.0, i1.y, i2.y, 1.0))
          + i.x + vec4(0.0, i1.x, i2.x, 1.0));

  float n_ = 0.142857142857;
  vec3 ns = n_ * D.wyz - D.xzx;

  vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
  vec4 x_ = floor(j * ns.z);
  vec4 y_ = floor(j - 7.0 * x_);

  vec4 x = x_ * ns.x + ns.yyyy;
  vec4 y = y_ * ns.x + ns.yyyy;
  vec4 h = 1.0 - abs(x) - abs(y);

  vec4 b0 = vec4(x.xy, y.xy);
  vec4 b1 = vec4(x.zw, y.zw);
  vec4 s0 = floor(b0) * 2.0 + 1.0;
  vec4 s1 = floor(b1) * 2.0 + 1.0;
  vec4 sh = -step(h, vec4(0.0));

  vec4 a0 = b0.xzyw + s0.xzyw * sh.xxyy;
  vec4 a1 = b1.xzyw + s1.xzyw * sh.zzww;

  vec3 p0 = vec3(a0.xy, h.x);
  vec3 p1 = vec3(a0.zw, h.y);
  vec3 p2 = vec3(a1.xy, h.z);
  vec3 p3 = vec3(a1.zw, h.w);

  vec4 norm = taylorInvSqrt(vec4(dot(p0, p0), dot(p1, p1), dot(p2, p2), dot(p3, p3)));
  p0 *= norm.x;
  p1 *= norm.y;
  p2 *= norm.z;
  p3 *= norm.w;

  vec4 m = max(0.6 - vec4(dot(x0, x0), dot(x1, x1), dot(x2, x2), dot(x3, x3)), 0.0);
  m = m * m;
  return 42.0 * dot(m * m, vec4(dot(p0, x0), dot(p1, x1), dot(p2, x2), dot(p3, x3)));
}
`;

// ---------- Core: a liquid sphere with a glowing rim ----------

export const coreVertexShader = /* glsl */ `
uniform float uTime;
uniform float uAmp;
uniform float uBeat;

varying vec3 vNormal;
varying vec3 vViewDir;
varying float vNoise;

${SIMPLEX_NOISE}

void main() {
  // Two layers of noise move the surface in and out like a liquid.
  float n1 = snoise(position * 1.35 + vec3(uTime * 0.16));
  float n2 = snoise(position * 3.1 - vec3(uTime * 0.27)) * 0.35;
  float n = n1 + n2;

  vec3 displaced = position + normal * (n * uAmp + uBeat * 0.07);
  vec4 mvPosition = modelViewMatrix * vec4(displaced, 1.0);

  vNormal = normalize(normalMatrix * normal);
  vViewDir = normalize(-mvPosition.xyz);
  vNoise = n;

  gl_Position = projectionMatrix * mvPosition;
}
`;

export const coreFragmentShader = /* glsl */ `
uniform vec3 uColorA;
uniform vec3 uColorB;
uniform float uGlow;

varying vec3 vNormal;
varying vec3 vViewDir;
varying float vNoise;

void main() {
  // Fresnel: surfaces seen edge-on glow brighter (the rim light).
  float facing = max(dot(normalize(vNormal), normalize(vViewDir)), 0.0);
  float fresnel = pow(1.0 - facing, 2.4);

  vec3 base = mix(uColorA, uColorB, smoothstep(-0.7, 0.7, vNoise));
  float bands = 0.5 + 0.5 * sin(vNoise * 11.0);

  vec3 color = base * (0.07 + 0.12 * bands);
  color += base * fresnel * 1.45 * uGlow;
  color += vec3(1.0) * pow(fresnel, 7.0) * 0.12 * uGlow;

  gl_FragColor = vec4(color, 1.0);
}
`;

// ---------- Particles: the "data galaxy" ----------

export const particleVertexShader = /* glsl */ `
uniform float uTime;
uniform float uSize;
uniform float uPixelRatio;

attribute vec3 aColor;
attribute float aScale;
attribute float aPhase;

varying vec3 vColor;
varying float vTwinkle;

void main() {
  vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
  gl_Position = projectionMatrix * mvPosition;

  float twinkle = 0.55 + 0.45 * sin(uTime * 1.3 + aPhase);
  gl_PointSize = uSize * aScale * uPixelRatio * twinkle / -mvPosition.z;

  vColor = aColor;
  vTwinkle = twinkle;
}
`;

export const particleFragmentShader = /* glsl */ `
varying vec3 vColor;
varying float vTwinkle;

void main() {
  float d = length(gl_PointCoord - 0.5);
  float alpha = smoothstep(0.5, 0.0, d);
  gl_FragColor = vec4(vColor * alpha * 1.3, alpha * vTwinkle);
}
`;

// ---------- Halo behind the core ----------

export const haloVertexShader = /* glsl */ `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

export const haloFragmentShader = /* glsl */ `
uniform vec3 uColor;
uniform float uStrength;
varying vec2 vUv;
void main() {
  float d = length(vUv - 0.5) * 2.0;
  float glow = pow(max(1.0 - d, 0.0), 2.6) * uStrength;
  gl_FragColor = vec4(uColor * glow, glow);
}
`;
