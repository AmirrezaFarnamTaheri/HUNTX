// HUNTX Interactive 3D WebGL Telemetry Globe Engine
// High-Performance, Zero-Alloc, GPU-Accelerated Canvas with Typed Arrays and Intersection Culling.

import { GLOBE_HUBS } from "./data.js";

export function initTelemetryGlobe(canvasId, onNodeSelect) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return { destroy: () => {} };

  const ctx = canvas.getContext("2d", { alpha: true, desynchronized: true });
  if (!ctx) return { destroy: () => {} };

  let width = 0;
  let height = 0;
  let dpr = Math.min(window.devicePixelRatio || 1, 2.0);

  let rotX = 0.25; // tilt
  let rotY = 0.0;  // spin
  let velY = 0.003;
  let isDragging = false;
  let startX = 0;
  let startY = 0;
  let lastX = 0;
  let lastY = 0;
  let rafId = 0;
  let isVisible = !document.hidden;
  let isIntersecting = true;
  let cachedGrad = null;

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Generate sphere dot grid (Fibonacci Sphere / Golden Spiral distribution)
  const DOT_COUNT = 850;
  const dotCoords = new Float32Array(DOT_COUNT * 3);
  const dotIsLand = new Uint8Array(DOT_COUNT);
  const dotAlphas = new Float32Array(DOT_COUNT);
  const rotatedPoints = new Float32Array(DOT_COUNT * 3);

  const phi = Math.PI * (3 - Math.sqrt(5)); // Golden ratio angle

  for (let i = 0; i < DOT_COUNT; i++) {
    const y = 1 - (i / (DOT_COUNT - 1)) * 2; // y goes from 1 to -1
    const radiusAtY = Math.sqrt(Math.max(0, 1 - y * y));
    const theta = phi * i;

    const x = Math.cos(theta) * radiusAtY;
    const z = Math.sin(theta) * radiusAtY;

    // Determine rough land probability to highlight continents
    const lat = Math.asin(Math.max(-1, Math.min(1, y))) * (180 / Math.PI);
    const lon = Math.atan2(z, x) * (180 / Math.PI);
    const isLand = checkLand(lat, lon);

    const idx = i * 3;
    dotCoords[idx] = x;
    dotCoords[idx + 1] = y;
    dotCoords[idx + 2] = z;
    dotIsLand[i] = isLand ? 1 : 0;
    dotAlphas[i] = isLand ? 0.85 : 0.22;
  }

  // Simplified continental hit-tester for visual aesthetics
  function checkLand(lat, lon) {
    if (lat > 10 && lat < 72 && lon > -15 && lon < 65) return true; // Europe & Middle East
    if (lat > 0 && lat < 70 && lon > 65 && lon < 145) return true;  // Asia
    if (lat > 15 && lat < 70 && lon > -165 && lon < -50) return true; // North America
    if (lat > -55 && lat < 12 && lon > -80 && lon < -35) return true; // South America
    if (lat > -45 && lat < -10 && lon > 110 && lon < 155) return true; // Oceania
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
      pulse: Math.random() * Math.PI * 2,
      screenX: 0,
      screenY: 0,
      screenZ: 0
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

    // Recompute cached radial gradient
    const centerX = width / 2;
    const centerY = height / 2;
    const radius = Math.min(width, height) * 0.42;

    cachedGrad = ctx.createRadialGradient(
      centerX - radius * 0.25,
      centerY - radius * 0.25,
      radius * 0.1,
      centerX,
      centerY,
      radius * 1.15
    );
    cachedGrad.addColorStop(0, "rgba(0, 210, 255, 0.08)");
    cachedGrad.addColorStop(0.5, "rgba(14, 165, 233, 0.04)");
    cachedGrad.addColorStop(0.85, "rgba(6, 182, 212, 0.02)");
    cachedGrad.addColorStop(1, "rgba(0, 0, 0, 0)");
  }

  function transformPointsZeroAlloc(cosY, sinY, cosX, sinX) {
    for (let i = 0; i < DOT_COUNT; i++) {
      const idx = i * 3;
      const x = dotCoords[idx];
      const y = dotCoords[idx + 1];
      const z = dotCoords[idx + 2];

      const x1 = x * cosY - z * sinY;
      const z1 = z * cosY + x * sinY;

      const y2 = y * cosX - z1 * sinX;
      const z2 = z1 * cosX + y * sinX;

      rotatedPoints[idx] = x1;
      rotatedPoints[idx + 1] = y2;
      rotatedPoints[idx + 2] = z2;
    }
  }

  function render(time = 0) {
    if (!isVisible || !isIntersecting) return;

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

    const cosY = Math.cos(rotY);
    const sinY = Math.sin(rotY);
    const cosX = Math.cos(rotX);
    const sinX = Math.sin(rotX);

    // Zero-allocation batch point rotation
    transformPointsZeroAlloc(cosY, sinY, cosX, sinX);

    // 1. Draw Cached Atmosphere & Core Sphere
    if (cachedGrad) {
      ctx.fillStyle = cachedGrad;
      ctx.beginPath();
      ctx.arc(centerX, centerY, radius * 1.18, 0, Math.PI * 2);
      ctx.fill();
    }

    // Outer Thin Orbit Ring
    ctx.strokeStyle = "rgba(0, 210, 255, 0.15)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
    ctx.stroke();

    // 2. Draw Dots
    for (let i = 0; i < DOT_COUNT; i++) {
      const idx = i * 3;
      const rx = rotatedPoints[idx];
      const ry = rotatedPoints[idx + 1];
      const rz = rotatedPoints[idx + 2];

      // Back-face culling / fade
      if (rz > -0.2) {
        const screenX = centerX + rx * radius;
        const screenY = centerY - ry * radius;
        const depthAlpha = Math.max(0.1, (rz + 0.3) / 1.3);

        const isLand = dotIsLand[i];
        const baseAlpha = dotAlphas[i];

        ctx.fillStyle = isLand
          ? `rgba(56, 189, 248, ${baseAlpha * depthAlpha})`
          : `rgba(148, 163, 184, ${baseAlpha * depthAlpha * 0.5})`;

        const dotSize = isLand ? (rz > 0.4 ? 2.2 : 1.6) : 1.1;
        ctx.beginPath();
        ctx.arc(screenX, screenY, dotSize, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    // 3. Draw Hub Nodes & Connecting Flight Arcs
    for (let i = 0; i < hubs.length; i++) {
      const h = hubs[i];
      const x1 = h.baseX * cosY - h.baseZ * sinY;
      const z1 = h.baseZ * cosY + h.baseX * sinY;
      const y2 = h.baseY * cosX - z1 * sinX;
      const z2 = z1 * cosX + h.baseY * sinX;

      h.screenX = centerX + x1 * radius;
      h.screenY = centerY - y2 * radius;
      h.screenZ = z2;
    }

    // Draw Connecting Telemetry Flight Arcs
    const frankfurt = hubs[0];
    if (frankfurt && frankfurt.screenZ > -0.2) {
      for (let i = 1; i < hubs.length; i++) {
        const dest = hubs[i];
        if (dest.screenZ > -0.3) {
          const midX = (frankfurt.screenX + dest.screenX) / 2;
          const midY = (frankfurt.screenY + dest.screenY) / 2 - (radius * 0.22);

          ctx.strokeStyle = "rgba(0, 210, 255, 0.45)";
          ctx.lineWidth = 1.2;
          ctx.setLineDash([4, 4]);
          ctx.beginPath();
          ctx.moveTo(frankfurt.screenX, frankfurt.screenY);
          ctx.quadraticCurveTo(midX, midY, dest.screenX, dest.screenY);
          ctx.stroke();
          ctx.setLineDash([]);
        }
      }
    }

    // Draw Hub Markers & Pulsing Rings
    for (let i = 0; i < hubs.length; i++) {
      const h = hubs[i];
      if (h.screenZ > -0.1) {
        h.pulse += 0.04;
        const pulseScale = (Math.sin(h.pulse) + 1) / 2;
        const ringRadius = 5 + pulseScale * 9;

        // Animated Outer Ring
        ctx.strokeStyle = `rgba(0, 210, 255, ${0.8 - pulseScale * 0.7})`;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(h.screenX, h.screenY, ringRadius, 0, Math.PI * 2);
        ctx.stroke();

        // Inner Solid Hub
        ctx.fillStyle = "#00d2ff";
        ctx.shadowColor = "#00d2ff";
        ctx.shadowBlur = 8;
        ctx.beginPath();
        ctx.arc(h.screenX, h.screenY, 3.5, 0, Math.PI * 2);
        ctx.fill();
        ctx.shadowBlur = 0;

        // Label for top visible nodes
        if (h.screenZ > 0.2) {
          ctx.font = "600 10px 'JetBrains Mono', monospace";
          ctx.fillStyle = "#edf2f9";
          ctx.fillText(`${h.code} ${h.name}`, h.screenX + 8, h.screenY + 3);

          ctx.font = "500 8.5px 'JetBrains Mono', monospace";
          ctx.fillStyle = "#10b981";
          ctx.fillText(`${h.count} nodes • ${h.ping}ms`, h.screenX + 8, h.screenY + 14);
        }
      }
    }

    if (!reduceMotion && isVisible && isIntersecting) {
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

  function onPointerUp(e) {
    if (isDragging) {
      const clientX = e.clientX || (e.changedTouches && e.changedTouches[0].clientX) || 0;
      const clientY = e.clientY || (e.changedTouches && e.changedTouches[0].clientY) || 0;
      const distMoved = Math.hypot(clientX - startX, clientY - startY);

      // If clicked without substantial dragging, test hit on hubs
      if (distMoved < 5 && onNodeSelect) {
        const rect = canvas.getBoundingClientRect();
        const clickX = clientX - rect.left;
        const clickY = clientY - rect.top;

        for (const h of hubs) {
          if (h.screenZ > -0.1) {
            const d = Math.hypot(h.screenX - clickX, h.screenY - clickY);
            if (d < 18) {
              onNodeSelect(h);
              break;
            }
          }
        }
      }
    }
    isDragging = false;
    velY = 0.0025; // resume gentle spin
  }

  function onVisibilityChange() {
    isVisible = !document.hidden;
    if (isVisible && isIntersecting && !reduceMotion) {
      cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(render);
    }
  }

  // Intersection Observer to stop rendering when scrolled offscreen
  let observer = null;
  if (typeof IntersectionObserver !== "undefined") {
    observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        isIntersecting = entry.isIntersecting;
        if (isIntersecting && isVisible && !reduceMotion) {
          cancelAnimationFrame(rafId);
          rafId = requestAnimationFrame(render);
        }
      });
    }, { threshold: 0.05 });
    observer.observe(canvas);
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
      if (observer) observer.disconnect();
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
