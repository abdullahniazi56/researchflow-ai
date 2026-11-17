import { useEffect, useRef } from "react";

/*
  A slowly rotating 3D "evidence graph" drawn on a canvas.
  Nodes are sources, lines are the links between them, and small
  pulses travel along the links like evidence flowing to an answer.
  No libraries: plain 3D maths + perspective projection.
*/

const NODE_COUNT = 150;
const LINKS_PER_NODE = 2;
const PULSE_COUNT = 7;
const ACCENT = "94, 200, 190"; // teal, as "r, g, b"

function createGraph() {
  // Fibonacci sphere: spreads points evenly over a sphere,
  // then a little random depth makes it feel organic.
  const nodes = Array.from({ length: NODE_COUNT }, (_, i) => {
    const y = 1 - (i / (NODE_COUNT - 1)) * 2;
    const radius = Math.sqrt(1 - y * y);
    const angle = i * 2.399963; // golden angle
    const jitter = 0.8 + Math.random() * 0.35;

    return {
      x: Math.cos(angle) * radius * jitter,
      y: y * jitter,
      z: Math.sin(angle) * radius * jitter,
      bright: i % 19 === 0,
    };
  });

  // Connect every node to its nearest neighbours.
  const seen = new Set();
  const links = [];

  nodes.forEach((a, i) => {
    nodes
      .map((b, j) => ({
        j,
        d: (a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2,
      }))
      .filter(({ j }) => j !== i)
      .sort((p, q) => p.d - q.d)
      .slice(0, LINKS_PER_NODE)
      .forEach(({ j }) => {
        const key = i < j ? `${i}-${j}` : `${j}-${i}`;
        if (!seen.has(key)) {
          seen.add(key);
          links.push([i, j]);
        }
      });
  });

  return { nodes, links };
}

export default function EvidenceBackground() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    const reduceMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)"
    ).matches;

    const { nodes, links } = createGraph();
    const randomLink = () =>
      links[Math.floor(Math.random() * links.length)];

    const pulses = Array.from({ length: PULSE_COUNT }, () => ({
      link: randomLink(),
      progress: Math.random(),
      speed: 0.004 + Math.random() * 0.004,
    }));

    let width = 0;
    let height = 0;
    let frameId = 0;

    function resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = canvas.clientWidth;
      height = canvas.clientHeight;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function project(node, cosY, sinY, cosX, sinX) {
      // Rotate around the Y axis, then tilt around the X axis.
      const x1 = node.x * cosY - node.z * sinY;
      const z1 = node.x * sinY + node.z * cosY;
      const y1 = node.y * cosX - z1 * sinX;
      const z2 = node.y * sinX + z1 * cosX;

      // Perspective: things further away (bigger z) get smaller.
      const perspective = 2.8 / (2.8 + z2);
      const scale = Math.min(width, height) * 0.46;
      const isWide = width > 900;

      return {
        x: width * (isWide ? 0.64 : 0.5) + x1 * scale * perspective,
        y: height * 0.5 + y1 * scale * perspective,
        depth: (1 - z2) / 2, // 0 = far, 1 = near
      };
    }

    function draw(time) {
      const angleY = time * 0.00005;
      const angleX = 0.38 + Math.sin(time * 0.00002) * 0.12;
      const cosY = Math.cos(angleY);
      const sinY = Math.sin(angleY);
      const cosX = Math.cos(angleX);
      const sinX = Math.sin(angleX);

      const points = nodes.map((n) => project(n, cosY, sinY, cosX, sinX));

      ctx.clearRect(0, 0, width, height);

      // Links
      ctx.lineWidth = 1;
      for (const [i, j] of links) {
        const a = points[i];
        const b = points[j];
        const alpha = 0.03 + 0.13 * ((a.depth + b.depth) / 2);
        ctx.strokeStyle = `rgba(${ACCENT}, ${alpha})`;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
      }

      // Nodes
      points.forEach((p, i) => {
        const node = nodes[i];
        const radius = (node.bright ? 2.2 : 1.1) + p.depth * 1.4;
        const alpha = node.bright ? 0.9 : 0.2 + p.depth * 0.5;

        ctx.fillStyle = node.bright
          ? `rgba(${ACCENT}, ${alpha})`
          : `rgba(205, 214, 235, ${alpha})`;
        ctx.beginPath();
        ctx.arc(p.x, p.y, radius, 0, Math.PI * 2);
        ctx.fill();
      });

      // Pulses travelling along links
      for (const pulse of pulses) {
        const a = points[pulse.link[0]];
        const b = points[pulse.link[1]];
        const x = a.x + (b.x - a.x) * pulse.progress;
        const y = a.y + (b.y - a.y) * pulse.progress;

        const glow = ctx.createRadialGradient(x, y, 0, x, y, 9);
        glow.addColorStop(0, `rgba(${ACCENT}, 0.85)`);
        glow.addColorStop(1, `rgba(${ACCENT}, 0)`);
        ctx.fillStyle = glow;
        ctx.beginPath();
        ctx.arc(x, y, 9, 0, Math.PI * 2);
        ctx.fill();

        if (!reduceMotion) {
          pulse.progress += pulse.speed;
          if (pulse.progress >= 1) {
            pulse.link = randomLink();
            pulse.progress = 0;
          }
        }
      }

      if (!reduceMotion) {
        frameId = requestAnimationFrame(draw);
      }
    }

    function handleResize() {
      resize();
      if (reduceMotion) draw(0);
    }

    resize();
    if (reduceMotion) {
      draw(0); // one still frame, no animation
    } else {
      frameId = requestAnimationFrame(draw);
    }

    window.addEventListener("resize", handleResize);

    return () => {
      cancelAnimationFrame(frameId);
      window.removeEventListener("resize", handleResize);
    };
  }, []);

  return (
    <div className="evidence-bg" aria-hidden="true">
      <canvas ref={canvasRef} />
    </div>
  );
}
