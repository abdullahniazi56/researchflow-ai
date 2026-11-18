import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import EvidenceBackground from "./EvidenceBackground";
import {
  coreFragmentShader,
  coreVertexShader,
  haloFragmentShader,
  haloVertexShader,
  particleFragmentShader,
  particleVertexShader,
} from "./shaders";

// mode: idle | busy (research running) | reading (conversation open)

const CYAN = new THREE.Color("#45e3d0");
const VIOLET = new THREE.Color("#8f7bff");
const WHITE = new THREE.Color("#e8ecff");
const BACKGROUND = 0x05070d;

const MODES = {
  idle: { amp: 0.11, speed: 1, glow: 0.85, bloom: 0.55, beatRate: 0.9 },
  reading: { amp: 0.09, speed: 0.6, glow: 0.7, bloom: 0.4, beatRate: 0.7 },
  busy: { amp: 0.22, speed: 2.8, glow: 1.2, bloom: 0.9, beatRate: 2.6 },
};

const SIDEBAR_BREAKPOINT = 800;
const SIDEBAR_SPACE = 296; // floating sidebar + gaps, in CSS pixels

function webglAvailable() {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

function buildGalaxy(count) {
  const positions = new Float32Array(count * 3);
  const colors = new Float32Array(count * 3);
  const scales = new Float32Array(count);
  const phases = new Float32Array(count);
  const color = new THREE.Color();
  const branches = 3;

  for (let i = 0; i < count; i += 1) {
    const i3 = i * 3;
    const inDisk = i < count * 0.72;

    if (inDisk) {
      // 3-arm spiral
      const radius = 2.4 + Math.pow(Math.random(), 1.7) * 7.5;
      const branch = ((i % branches) / branches) * Math.PI * 2;
      const spin = radius * 0.42;
      const spread = Math.pow(Math.random(), 2.2) * (Math.random() < 0.5 ? 1 : -1);
      const angle = branch + spin + spread * 0.9;

      positions[i3] = Math.cos(angle) * radius + spread * 0.4;
      positions[i3 + 1] = (Math.random() - 0.5) * 0.35 * (1 + radius * 0.06);
      positions[i3 + 2] = Math.sin(angle) * radius + spread * 0.4;

      color.copy(CYAN).lerp(VIOLET, Math.min((radius - 2.4) / 7.5, 1));
    } else {
      // background dust
      const r = 7 + Math.random() * 10;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      positions[i3] = r * Math.sin(phi) * Math.cos(theta);
      positions[i3 + 1] = r * Math.sin(phi) * Math.sin(theta);
      positions[i3 + 2] = r * Math.cos(phi);
      color.copy(Math.random() < 0.5 ? WHITE : VIOLET);
    }

    if (Math.random() < 0.08) color.copy(WHITE);

    colors[i3] = color.r;
    colors[i3 + 1] = color.g;
    colors[i3 + 2] = color.b;
    scales[i] = 0.4 + Math.random() * 1.2;
    phases[i] = Math.random() * Math.PI * 2;
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute("aColor", new THREE.BufferAttribute(colors, 3));
  geometry.setAttribute("aScale", new THREE.BufferAttribute(scales, 1));
  geometry.setAttribute("aPhase", new THREE.BufferAttribute(phases, 1));
  return geometry;
}

function createScene(container, modeRef) {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const isSmall = window.innerWidth < 800;
  const pixelRatio = Math.min(window.devicePixelRatio || 1, 1.5);

  const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(pixelRatio);
  renderer.setClearColor(BACKGROUND, 1);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 0.9;
  container.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(BACKGROUND, 0.035);

  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
  camera.position.set(0, 0.4, 9);

  const root = new THREE.Group(); // everything, for mouse parallax
  scene.add(root);

  const coreUniforms = {
    uTime: { value: 0 },
    uAmp: { value: MODES.idle.amp },
    uBeat: { value: 0 },
    uGlow: { value: 1 },
    uColorA: { value: CYAN.clone() },
    uColorB: { value: VIOLET.clone() },
  };
  const coreGeometry = new THREE.IcosahedronGeometry(1.0, isSmall ? 48 : 96);
  const core = new THREE.Mesh(
    coreGeometry,
    new THREE.ShaderMaterial({
      vertexShader: coreVertexShader,
      fragmentShader: coreFragmentShader,
      uniforms: coreUniforms,
    })
  );
  root.add(core);

  const shell = new THREE.Mesh(
    new THREE.IcosahedronGeometry(1.32, 2),
    new THREE.MeshBasicMaterial({
      color: CYAN,
      wireframe: true,
      transparent: true,
      opacity: 0.08,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    })
  );
  root.add(shell);

  const haloUniforms = { uColor: { value: VIOLET.clone().lerp(CYAN, 0.35) }, uStrength: { value: 0.35 } };
  const halo = new THREE.Mesh(
    new THREE.PlaneGeometry(9, 9),
    new THREE.ShaderMaterial({
      vertexShader: haloVertexShader,
      fragmentShader: haloFragmentShader,
      uniforms: haloUniforms,
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    })
  );
  halo.position.z = -1.5;
  root.add(halo);

  const particleUniforms = {
    uTime: { value: 0 },
    uSize: { value: 26 },
    uPixelRatio: { value: pixelRatio },
  };
  const galaxy = new THREE.Points(
    buildGalaxy(isSmall ? 2600 : 7000),
    new THREE.ShaderMaterial({
      vertexShader: particleVertexShader,
      fragmentShader: particleFragmentShader,
      uniforms: particleUniforms,
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    })
  );
  galaxy.rotation.x = 1.12;
  galaxy.rotation.z = 0.18;
  root.add(galaxy);

  const rings = [];
  const ringSpecs = [
    { radius: 1.85, tilt: [1.25, 0.2, 0], speed: 0.32, color: CYAN, orbiters: 3 },
    { radius: 2.4, tilt: [1.0, -0.55, 0.3], speed: -0.22, color: VIOLET, orbiters: 4 },
    { radius: 3.05, tilt: [1.45, 0.65, -0.2], speed: 0.15, color: WHITE, orbiters: 2 },
  ];

  for (const spec of ringSpecs) {
    const group = new THREE.Group();
    group.rotation.set(...spec.tilt);

    group.add(
      new THREE.Mesh(
        new THREE.TorusGeometry(spec.radius, 0.006, 8, 220),
        new THREE.MeshBasicMaterial({
          color: spec.color,
          transparent: true,
          opacity: 0.32,
          blending: THREE.AdditiveBlending,
          depthWrite: false,
        })
      )
    );

    const orbiters = [];
    for (let k = 0; k < spec.orbiters; k += 1) {
      const dot = new THREE.Mesh(
        new THREE.SphereGeometry(0.045, 16, 16),
        new THREE.MeshBasicMaterial({ color: spec.color })
      );
      dot.userData.offset = (k / spec.orbiters) * Math.PI * 2 + Math.random() * 0.4;
      group.add(dot);
      orbiters.push(dot);
    }

    root.add(group);
    rings.push({ group, orbiters, spec });
  }

  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  const bloom = new UnrealBloomPass(new THREE.Vector2(1, 1), MODES.idle.bloom, 0.5, 0.22);
  composer.addPass(bloom);
  composer.addPass(new OutputPass());

  function resize() {
    const width = container.clientWidth;
    const height = container.clientHeight;
    renderer.setSize(width, height, false);
    composer.setSize(width, height);
    bloom.setSize(width, height);
    camera.aspect = width / height;
    camera.position.z = width < 800 ? 13 : 10.5;

    // center the core in the area right of the sidebar, slightly low
    const shift = width > SIDEBAR_BREAKPOINT ? SIDEBAR_SPACE / 2 : 0;
    camera.setViewOffset(width, height, -shift, -height * 0.07, width, height);
    camera.updateProjectionMatrix();
  }
  resize();
  window.addEventListener("resize", resize);

  const pointer = { x: 0, y: 0 };
  function onPointerMove(event) {
    pointer.x = event.clientX / window.innerWidth - 0.5;
    pointer.y = event.clientY / window.innerHeight - 0.5;
  }
  window.addEventListener("pointermove", onPointerMove);

  const clock = new THREE.Clock();
  const live = { ...MODES.idle };
  let time = 0;
  let beatPhase = 0;
  let frameId = 0;
  const ease = (current, target, amount) => current + (target - current) * amount;

  function frame() {
    const delta = Math.min(clock.getDelta(), 0.05);
    const target = MODES[modeRef.current] || MODES.idle;

    for (const key of Object.keys(live)) {
      live[key] = ease(live[key], target[key], 0.04);
    }

    time += delta * live.speed;
    beatPhase += delta * live.beatRate * Math.PI * 2;

    // double-pulse heartbeat
    const beat = Math.pow(Math.max(Math.sin(beatPhase), 0), 8)
      + 0.6 * Math.pow(Math.max(Math.sin(beatPhase - 0.55), 0), 10);

    coreUniforms.uTime.value = time;
    coreUniforms.uAmp.value = live.amp;
    coreUniforms.uBeat.value = beat;
    coreUniforms.uGlow.value = live.glow;
    particleUniforms.uTime.value = time;
    haloUniforms.uStrength.value = 0.28 + beat * 0.18 * live.glow;
    bloom.strength = live.bloom + beat * 0.18;

    core.rotation.y = time * 0.12;
    shell.rotation.y = -time * 0.08;
    shell.rotation.x = time * 0.05;
    galaxy.rotation.y = time * 0.035;

    for (const { group, orbiters, spec } of rings) {
      for (const dot of orbiters) {
        const a = dot.userData.offset + time * spec.speed;
        dot.position.set(Math.cos(a) * spec.radius, Math.sin(a) * spec.radius, 0);
      }
      group.rotation.z += delta * spec.speed * 0.15 * live.speed;
    }

    root.rotation.y = ease(root.rotation.y, pointer.x * 0.35, 0.03);
    root.rotation.x = ease(root.rotation.x, pointer.y * 0.2, 0.03);
    halo.lookAt(camera.position);

    composer.render();

    if (!reduceMotion) frameId = requestAnimationFrame(frame);
  }

  if (reduceMotion) {
    frame(); // one still frame
  } else {
    frameId = requestAnimationFrame(frame);
  }

  return () => {
    cancelAnimationFrame(frameId);
    window.removeEventListener("resize", resize);
    window.removeEventListener("pointermove", onPointerMove);

    scene.traverse((object) => {
      object.geometry?.dispose();
      const materials = Array.isArray(object.material) ? object.material : [object.material];
      materials.forEach((material) => material?.dispose());
    });
    composer.dispose?.();
    renderer.dispose();
    renderer.domElement.remove();
  };
}

export default function CoreScene({ mode = "idle" }) {
  const containerRef = useRef(null);
  const modeRef = useRef(mode);
  const [supported] = useState(webglAvailable);

  useEffect(() => {
    modeRef.current = mode;
  }, [mode]);

  useEffect(() => {
    if (!supported) return undefined;
    try {
      return createScene(containerRef.current, modeRef);
    } catch (err) {
      console.error("3D scene failed to start:", err);
      return undefined;
    }
  }, [supported]);

  if (!supported) return <EvidenceBackground />;

  return (
    <div
      ref={containerRef}
      className={`core-scene core-scene--${mode}`}
      aria-hidden="true"
    />
  );
}
