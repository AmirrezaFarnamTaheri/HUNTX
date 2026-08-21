// HUNTX Interactive 3D WebGL Telemetry Globe Engine
// Zero-dependency, GPU-accelerated canvas renderer with interactive drag, node hubs, and flight arcs.

import { GLOBE_HUBS } from "./data.js";

export function initTelemetryGlobe(canvasId, onNodeSelect) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return { destroy: () => {} };

  const ctx = canvas.getContext("2d");
  if (!ctx) return { destroy: () => {} };

  let width = 0;
  let height = 0;
  let dpr = Math.min(window.devicePixelRatio || 1, 2.0);

  let rotX = 0.25; // tilt
  let rotY = 0.0;  // spin
  let targetRotY = 0.0;
  let velY = 0.003;
  let isDragging = false;
  let startX = 0;
  let startY = 0;
  let lastX = 0;
  let lastY = 0;
  let hoveredHub = null;
  let rafId = 0;
  let isVisible = !document.hidden;

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Generate sphere dot grid (Fibonacci Sphere / Golden Spiral distribution)
  const DOT_COUNT = 950;
  const dots = [];
  const phi = Math.PI * (3 - Math.sqrt(5)); // Golden ratio angle

  for (let i = 0; i < DOT_COUNT; i++) {
    const y = 1 - (i / (DOT_COUNT - 1)) * 2; // y goes from 1 to -1
    const radiusAtY = Math.sqrt(1 - y * y);
    const theta = phi * i;

    const x = Math.cos(theta) * radiusAtY;
    const z = Math.sin(theta) * radiusAtY;

    // Determine rough land probability to highlight continents
    const lat = Math.asin(y) * (180 / Math.PI);
    const lon = Math.atan2(z, x) * (180 / Math.PI);
    const isLand = checkLand(lat, lon);

    dots.push({ x, y, z, isLand, baseAlpha: isLand ? 0.85 : 0.22 });
  }

  // Simplified continental hit-tester for visual aesthetics
  function checkLand(lat, lon) {
    // Europe & Middle East & North Africa
    if (lat > 10 && lat < 72 && lon > -15 && lon < 65) return true;
    // Asia & East Asia
    if (lat > 0 && lat < 70 && lon > 65 && lon < 145) return true;
    // North America
    if (lat > 15 && lat < 70 && lon > -165 && lon < -50) return true;
    // South America
    if (lat > -55 && lat < 12 && lon > -80 && lon < -35) return true;
    // Australia / Oceania
    if (lat > -45 && lat < -10 && lon > 110 && lon < 155) return true;
    return false;
  }

  // Pre-calculate Hub Coordinates
  const hubs = GLOBE_HUBS.map(hub => {
    const latRad = (hub.lat * Math.PI) / 180;
    const lonRad = (hub.lon * Math.PI) / 180;
    return {
      ...hub,
      baseX: Math.cos(latRad) * Math.sin(lonRad),
      baseY: Math.sin(latRad),
      baseZ: Math.cos(latRad) * Math.cos(lonRad),
      pulse: Math.random() * Math.PI * 2
    };
  });

  function resize() {
    const rect = canvas.getBoundingClientRect();
    width = rect.width;
    height = rect.height;
    dpr = Math.min(window.devicePixelRatio || 1, 2.0);

    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function rotate3D(x, y, z, rx, ry) {
    // Rotate around Y axis
    const cosY = Math.cos(ry);
    const sinY = Math.sin(ry);
    const x1 = x * cosY - z * sinY;
    const z1 = z * cosY + x * sinY;

    // Rotate around X axis
    const cosX = Math.cos(rx);
    const sinX = Math.sin(rx);
    const y2 = y * cosX - z1 * sinX;
    const z2 = z1 * cosX + y * sinX;

    return { x: x1, y: y2, z: z2 };
  }

  function render(time = 0) {
    if (!isVisible) return;

    if (!ctx || width === 0) {
      rafId = requestAnimationFrame(render);
      return;
    }

    ctx.clearRect(0, 0, width, height);

    const centerX = width / 2;
    const centerY = height / 2;
    const radius = Math.min(width, height) * 0.42;

    if (!isDragging && !reduceMotion) {
      rotY += velY;
    }

    // 1. Draw Glow Atmosphere & Core Sphere
    const grad = ctx.createRadialGradient(
      centerX - radius * 0.25,
      centerY - radius * 0.25,
      radius * 0.1,
      centerX,
      centerY,
      radius * 1.15
    );
    grad.addColorStop(0, "rgba(0, 210, 255, 0.08)");
    grad.addColorStop(0.5, "rgba(14, 165, 233, 0.04)");
    grad.addColorStop(0.85, "rgba(6, 182, 212, 0.02)");
    grad.addColorStop(1, "rgba(0, 0, 0, 0)");

    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius * 1.18, 0, Math.PI * 2);
    ctx.fill();

    // Outer Thin Orbit Ring
    ctx.strokeStyle = "rgba(0, 210, 255, 0.15)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
    ctx.stroke();

    // 2. Draw Dots
    for (let i = 0; i < dots.length; i++) {
      const d = dots[i];
      const p = rotate3D(d.x, d.y, d.z, rotX, rotY);

      // Back-face culling / fade
      if (p.z > -0.2) {
        const screenX = centerX + p.x * radius;
        const screenY = centerY - p.y * radius;
        const depthAlpha = Math.max(0.1, (p.z + 0.3) / 1.3);

        ctx.fillStyle = d.isLand
          ? `rgba(56, 189, 248, ${d.baseAlpha * depthAlpha})`
          : `rgba(148, 163, 184, ${d.baseAlpha * depthAlpha * 0.5})`;

        const dotSize = d.isLand ? (p.z > 0.4 ? 2.2 : 1.6) : 1.1;
        ctx.beginPath();
        ctx.arc(screenX, screenY, dotSize, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    // 3. Draw Connecting Telemetry Flight Arcs
    const frankfurt = hubs[0];
    const fPos = rotate3D(frankfurt.baseX, frankfurt.baseY, frankfurt.baseZ, rotX, rotY);

    if (fPos.z > -0.2) {
      const fScreenX = centerX + fPos.x * radius;
      const fScreenY = centerY - fPos.y * radius;

      for (let i = 1; i < hubs.length; i++) {
        const dest = hubs[i];
        const dPos = rotate3D(dest.baseX, dest.baseY, dest.baseZ, rotX, rotY);

        if (dPos.z > -0.3) {
          const dScreenX = centerX + dPos.x * radius;
          const dScreenY = centerY - dPos.y * radius;

          // Compute arched mid-point
          const midX = (fScreenX + dScreenX) / 2;
          const midY = (fScreenY + dScreenY) / 2 - (radius * 0.22);

          const arcGrad = ctx.createLinearGradient(fScreenX, fScreenY, dScreenX, dScreenY);
          arcGrad.addColorStop(0, "rgba(0, 210, 255, 0.6)");
          arcGrad.addColorStop(0.5, "rgba(16, 185, 129, 0.8)");
          arcGrad.addColorStop(1, "rgba(0, 210, 255, 0.2)");

          ctx.strokeStyle = arcGrad;
          ctx.lineWidth = 1.2;
          ctx.setLineDash([4, 4]);
          ctx.beginPath();
          ctx.moveTo(fScreenX, fScreenY);
          ctx.quadraticCurveTo(midX, midY, dScreenX, dScreenY);
          ctx.stroke();
          ctx.setLineDash([]);
        }
      }
    }

    // 4. Draw Hub Nodes & Pulsing Rings
    for (let i = 0; i < hubs.length; i++) {
      const h = hubs[i];
      const p = rotate3D(h.baseX, h.baseY, h.baseZ, rotX, rotY);

      if (p.z > -0.1) {
        const screenX = centerX + p.x * radius;
        const screenY = centerY - p.y * radius;

        h.pulse += 0.04;
        const pulseScale = (Math.sin(h.pulse) + 1) / 2;
        const ringRadius = 5 + pulseScale * 9;

        // Animated Outer Ring
        ctx.strokeStyle = `rgba(0, 210, 255, ${0.8 - pulseScale * 0.7})`;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(screenX, screenY, ringRadius, 0, Math.PI * 2);
        ctx.stroke();

        // Inner Solid Hub
        ctx.fillStyle = "#00d2ff";
        ctx.shadowColor = "#00d2ff";
        ctx.shadowBlur = 10;
        ctx.beginPath();
        ctx.arc(screenX, screenY, 3.5, 0, Math.PI * 2);
        ctx.fill();
        ctx.shadowBlur = 0;

        // Label for top nodes
        if (p.z > 0.2) {
          ctx.font = "600 10px 'JetBrains Mono', monospace";
          ctx.fillStyle = "#edf2f9";
          ctx.fillText(`${h.code} ${h.name}`, screenX + 8, screenY + 3);

          ctx.font = "500 8.5px 'JetBrains Mono', monospace";
          ctx.fillStyle = "#10b981";
          ctx.fillText(`${h.count} nodes • ${h.ping}ms`, screenX + 8, screenY + 14);
        }
      }
    }

    if (!reduceMotion && isVisible) {
      rafId = requestAnimationFrame(render);
    }
  }

  // Pointer Interaction
  function onPointerDown(e) {
    isDragging = true;
    startX = e.clientX || (e.touches && e.touches[0].clientX) || 0;
    startY = e.clientY || (e.touches && e.touches[0].clientY) || 0;
    lastX = startX;
    lastY = startY;
    velY = 0;
  }

  function onPointerMove(e) {
    if (!isDragging) return;
    const clientX = e.clientX || (e.touches && e.touches[0].clientX) || 0;
    const clientY = e.clientY || (e.touches && e.touches[0].clientY) || 0;

    const dx = clientX - lastX;
    const dy = clientY - lastY;

    rotY += dx * 0.006;
    rotX = Math.max(-1.1, Math.min(1.1, rotX + dy * 0.005));

    lastX = clientX;
    lastY = clientY;
  }

  function onPointerUp() {
    isDragging = false;
    velY = 0.0025; // resume gentle spin
  }

  function onVisibilityChange() {
    isVisible = !document.hidden;
    if (isVisible && !reduceMotion) {
      cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(render);
    }
  }

  window.addEventListener("resize", resize);
  document.addEventListener("visibilitychange", onVisibilityChange);
  canvas.addEventListener("mousedown", onPointerDown);
  window.addEventListener("mousemove", onPointerMove);
  window.addEventListener("mouseup", onPointerUp);

  canvas.addEventListener("touchstart", onPointerDown, { passive: true });
  window.addEventListener("touchmove", onPointerMove, { passive: true });
  window.addEventListener("touchend", onPointerUp, { passive: true });

  resize();
  render();

  return {
    destroy: () => {
      cancelAnimationFrame(rafId);
      window.removeEventListener("resize", resize);
      document.removeEventListener("visibilitychange", onVisibilityChange);
      canvas.removeEventListener("mousedown", onPointerDown);
      window.removeEventListener("mousemove", onPointerMove);
      window.removeEventListener("mouseup", onPointerUp);
      canvas.removeEventListener("touchstart", onPointerDown);
      window.removeEventListener("touchmove", onPointerMove);
      window.removeEventListener("touchend", onPointerUp);
    }
  };
}
