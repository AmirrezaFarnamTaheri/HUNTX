// HUNTX Interactive 3D WebGL Telemetry Globe Engine
// Cyber Neon Heatmap Edition: 1,500 Dense Fibonacci Points, 20 Global Geo-Clusters,
// Multi-Hub Cyber Mesh Telemetry Arcs with Traveling Photons, and Zero-Allocation Mathematical Transforms.

import { GLOBE_HUBS } from "./data.js";

export function initTelemetryGlobe(canvasId, onNodeSelect, customHubs = null) {
  const canvas = document.getElementById(canvasId);
  if (!canvas || typeof canvas.getContext !== "function") return { destroy: () => {} };

  const ctx = canvas.getContext("2d", { alpha: true, desynchronized: true });
  if (!ctx) return { destroy: () => {} };

  let width = 0;
  let height = 0;
  let dpr = Math.min(window.devicePixelRatio || 1, 2.0);

  let rotX = 0.28; // tilt
  let rotY = 0.0;  // spin
  let velX = 0.0;
  let velY = 0.0032;
  let isDragging = false;
  let startX = 0;
  let startY = 0;
  let lastX = 0;
  let lastY = 0;
  let lastMoveTime = 0;
  let rafId = 0;
  let isVisible = !document.hidden;
  let isIntersecting = true;
  let cachedGrad = null;
  let hoveredHub = null;

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // High-Density Fibonacci Sphere (1,500 points for dense neon cluster representation)
  const DOT_COUNT = 1500;
  const dotCoords = new Float32Array(DOT_COUNT * 3);
  const dotType = new Uint8Array(DOT_COUNT);     // 0: Ocean, 1: Land, 2: Proxy Hotspot
  const dotAlphas = new Float32Array(DOT_COUNT);
  const dotSizes = new Float32Array(DOT_COUNT);
  const rotatedPoints = new Float32Array(DOT_COUNT * 3);

  const phi = Math.PI * (3 - Math.sqrt(5)); // Golden ratio angle

  // 20 High-Density Global Strategic Geo-Clusters (Lat, Lon, Radius in deg)
  const HOTSPOTS = [
    { lat: 50.1109, lon: 8.6821, radius: 22 },   // Central Europe (Frankfurt, DE)
    { lat: 52.3702, lon: 4.8952, radius: 18 },   // Western Europe (Amsterdam, NL)
    { lat: 51.5074, lon: -0.1278, radius: 16 },  // United Kingdom (London, GB)
    { lat: 48.8566, lon: 2.3522, radius: 16 },   // France (Paris, FR)
    { lat: 60.1699, lon: 24.9384, radius: 18 },  // Northern Europe (Helsinki, FI)
    { lat: 59.3293, lon: 18.0686, radius: 16 },  // Scandinavia (Stockholm, SE)
    { lat: 47.3769, lon: 8.5417, radius: 15 },   // Alpine Hub (Zurich, CH)
    { lat: 39.0438, lon: -77.4874, radius: 25 }, // US East Core (Ashburn, VA)
    { lat: 37.3382, lon: -121.8863, radius: 22 },// US West Pacific (San Jose, CA)
    { lat: 43.6532, lon: -79.3832, radius: 18 }, // Canada East (Toronto, CA)
    { lat: 1.3521, lon: 103.8198, radius: 18 },  // SE Asia Hub (Singapore, SG)
    { lat: 35.6762, lon: 139.6503, radius: 20 }, // East Asia (Tokyo, JP)
    { lat: 37.5665, lon: 126.9780, radius: 16 }, // East Asia Speed (Seoul, KR)
    { lat: 22.3193, lon: 114.1694, radius: 16 }, // Greater China (Hong Kong, HK)
    { lat: 41.0082, lon: 28.9784, radius: 18 },  // Eurasian Crossroads (Istanbul, TR)
    { lat: 35.6892, lon: 51.3890, radius: 18 },  // Middle East Core (Tehran, IR)
    { lat: 55.7558, lon: 37.6173, radius: 20 },  // Eastern Europe / Russia (Moscow, RU)
    { lat: -33.8688, lon: 151.2093, radius: 18 },// Oceania (Sydney, AU)
    { lat: -23.5505, lon: -46.6333, radius: 20 },// Latin America (São Paulo, BR)
    { lat: -26.2041, lon: 28.0473, radius: 18 }  // Southern Africa (Johannesburg, ZA)
  ];

  // Fibonacci Sphere Generation
  for (let i = 0; i < DOT_COUNT; i++) {
    const y = 1 - (i / (DOT_COUNT - 1)) * 2; // y goes from 1 to -1
    const radiusAtY = Math.sqrt(Math.max(0, 1 - y * y));
    const theta = phi * i;

    const x = Math.cos(theta) * radiusAtY;
    const z = Math.sin(theta) * radiusAtY;

    // Convert (x, y, z) on unit sphere to spherical lat / lon in degrees
    const lat = Math.asin(Math.max(-1, Math.min(1, y))) * (180 / Math.PI);
    const lon = Math.atan2(x, z) * (180 / Math.PI);

    let type = 0; // 0: Ocean
    if (checkLand(lat, lon)) {
      type = 1; // Land
      if (checkHotspot(lat, lon)) {
        type = 2; // High-Density Proxy Hotspot
      }
    }

    const idx = i * 3;
    dotCoords[idx] = x;
    dotCoords[idx + 1] = y;
    dotCoords[idx + 2] = z;
    dotType[i] = type;

    if (type === 2) {
      dotAlphas[i] = 0.95;
      dotSizes[i] = 2.4;
    } else if (type === 1) {
      dotAlphas[i] = 0.65;
      dotSizes[i] = 1.6;
    } else {
      dotAlphas[i] = 0.18;
      dotSizes[i] = 1.0;
    }
  }

  function checkLand(lat, lon) {
    if (lat > 10 && lat < 72 && lon > -15 && lon < 65) return true; // Europe & Middle East
    if (lat > 0 && lat < 70 && lon > 65 && lon < 145) return true;  // Asia
    if (lat > 15 && lat < 70 && lon > -165 && lon < -50) return true; // North America
    if (lat > -55 && lat < 12 && lon > -80 && lon < -35) return true; // South America
    if (lat > -45 && lat < -10 && lon > 110 && lon < 155) return true; // Oceania
    if (lat > -35 && lat < 38 && lon > -20 && lon < 52) return true;  // Africa
    return false;
  }

  function checkHotspot(lat, lon) {
    for (let j = 0; j < HOTSPOTS.length; j++) {
      const h = HOTSPOTS[j];
      const dLat = lat - h.lat;
      const dLon = lon - h.lon;
      if (dLat * dLat + dLon * dLon <= h.radius * h.radius) {
        return true;
      }
    }
    return false;
  }

  // Real Output Clustered Telemetry Hubs
  const DEFAULT_HUBS = [
    { name: "Silicon Valley", lat: 37.77, lon: -122.42, count: 11, code: "US", ping: 38 },
    { name: "Moscow Hub", lat: 55.76, lon: 37.62, count: 4, code: "RU", ping: 32 },
    { name: "Frankfurt Hub", lat: 50.11, lon: 8.68, count: 3, code: "DE", ping: 26 },
    { name: "Amsterdam Hub", lat: 52.37, lon: 4.90, count: 3, code: "NL", ping: 30 },
    { name: "Helsinki Hub", lat: 60.17, lon: 24.94, count: 2, code: "FI", ping: 28 },
    { name: "Paris Hub", lat: 48.86, lon: 2.35, count: 2, code: "FR", ping: 32 },
    { name: "Tokyo Hub", lat: 35.68, lon: 139.65, count: 2, code: "JP", ping: 48 },
    { name: "Singapore Hub", lat: 1.35, lon: 103.82, count: 2, code: "SG", ping: 46 },
    { name: "London Edge", lat: 51.51, lon: -0.13, count: 2, code: "GB", ping: 34 },
    { name: "Zurich Edge", lat: 47.38, lon: 8.54, count: 1, code: "CH", ping: 32 },
    { name: "Tehran Edge", lat: 35.69, lon: 51.39, count: 1, code: "IR", ping: 20 }
  ];

  const sourceHubs = (customHubs && Array.isArray(customHubs) && customHubs.length > 0)
    ? customHubs
    : ((typeof GLOBE_HUBS !== "undefined" && Array.isArray(GLOBE_HUBS) && GLOBE_HUBS.length > 0) ? GLOBE_HUBS : DEFAULT_HUBS);

  // Pre-calculate Hub Coordinates
  const hubs = sourceHubs.map(hub => {
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

  // Global Telemetry Mesh Backbone Connections (Pairs of hub indices)
  const MESH_LINKS = [
    [0, 1],  // Frankfurt -> Amsterdam
    [0, 2],  // Frankfurt -> London
    [0, 3],  // Frankfurt -> Paris
    [0, 4],  // Frankfurt -> Helsinki
    [0, 5],  // Frankfurt -> Stockholm
    [0, 6],  // Frankfurt -> Zurich
    [0, 7],  // Frankfurt -> Ashburn (Transatlantic)
    [0, 14], // Frankfurt -> Istanbul
    [0, 15], // Frankfurt -> Dubai
    [0, 16], // Frankfurt -> Tehran
    [7, 8],  // Ashburn -> San Jose
    [7, 9],  // Ashburn -> Toronto
    [7, 18], // Ashburn -> São Paulo
    [10, 11],// Singapore -> Tokyo
    [10, 12],// Singapore -> Seoul
    [10, 13],// Singapore -> Hong Kong
    [10, 17],// Singapore -> Sydney
    [15, 10],// Dubai -> Singapore
    [15, 19] // Dubai -> Johannesburg
  ];

  // Traveling Photons along mesh links
  const photonProgress = new Float32Array(MESH_LINKS.length);
  for (let i = 0; i < MESH_LINKS.length; i++) {
    photonProgress[i] = (i * 0.17) % 1.0;
  }

  function resize() {
    const rect = canvas.getBoundingClientRect();
    width = rect.width || canvas.parentElement?.clientWidth || canvas.offsetWidth || 360;
    height = rect.height || canvas.parentElement?.clientHeight || canvas.offsetHeight || 360;
    dpr = Math.min(window.devicePixelRatio || 1, 2.0);

    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    // Recompute cached multi-stop glowing nebula atmosphere
    const centerX = width / 2;
    const centerY = height / 2;
    const radius = Math.min(width, height) * 0.42;

    cachedGrad = ctx.createRadialGradient(
      centerX - radius * 0.2,
      centerY - radius * 0.25,
      radius * 0.05,
      centerX,
      centerY,
      radius * 1.25
    );
    cachedGrad.addColorStop(0, "rgba(0, 210, 255, 0.16)");
    cachedGrad.addColorStop(0.35, "rgba(6, 182, 212, 0.08)");
    cachedGrad.addColorStop(0.75, "rgba(2, 6, 23, 0.04)");
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
    if (!isVisible) {
      rafId = requestAnimationFrame(render);
      return;
    }

    const rect = canvas.getBoundingClientRect();
    if (rect.width > 0 && (Math.abs(rect.width - width) > 1 || Math.abs(rect.height - height) > 1)) {
      resize();
    }

    if (!ctx || width === 0) {
      rafId = requestAnimationFrame(render);
      return;
    }

    ctx.clearRect(0, 0, width, height);

    const centerX = width / 2;
    const centerY = height / 2;
    const radius = Math.min(width, height) * 0.42;

    // Inertia physics & rotation
    if (!isDragging && !reduceMotion) {
      rotY += velY;
      rotX += velX;
      // Damping friction
      velX *= 0.92;
      if (Math.abs(velY - 0.0032) > 0.0001) {
        velY = velY * 0.94 + 0.0032 * 0.06;
      }
      rotX = Math.max(-0.85, Math.min(0.85, rotX));
    }

    const cosY = Math.cos(rotY);
    const sinY = Math.sin(rotY);
    const cosX = Math.cos(rotX);
    const sinX = Math.sin(rotX);

    // 1. Zero-allocation batch point rotation
    transformPointsZeroAlloc(cosY, sinY, cosX, sinX);

    // 2. Draw Cached Cyber Atmosphere & Nebula Glow
    if (cachedGrad) {
      ctx.fillStyle = cachedGrad;
      ctx.beginPath();
      ctx.arc(centerX, centerY, radius * 1.22, 0, Math.PI * 2);
      ctx.fill();
    }

    // Outer Cyber Grid Halo
    ctx.strokeStyle = "rgba(0, 210, 255, 0.22)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
    ctx.stroke();

    // 3. Draw High-Density Dots (Ocean, Land, Proxy Hotspots)
    for (let i = 0; i < DOT_COUNT; i++) {
      const idx = i * 3;
      const rx = rotatedPoints[idx];
      const ry = rotatedPoints[idx + 1];
      const rz = rotatedPoints[idx + 2];

      // Back-face culling / fade
      if (rz > -0.22) {
        const screenX = centerX + rx * radius;
        const screenY = centerY - ry * radius;
        const depthAlpha = Math.max(0.12, (rz + 0.35) / 1.35);

        const type = dotType[i];
        const baseAlpha = dotAlphas[i];
        const baseSize = dotSizes[i];

        if (type === 2) {
          // PROXY HOTSPOT: Intense Neon Cyan / Emerald Flare
          const glowAlpha = Math.min(1.0, baseAlpha * depthAlpha * 1.15);
          ctx.fillStyle = `rgba(34, 211, 238, ${glowAlpha})`;
          const dotSize = rz > 0.3 ? baseSize * 1.15 : baseSize;
          ctx.beginPath();
          ctx.arc(screenX, screenY, dotSize, 0, Math.PI * 2);
          ctx.fill();
        } else if (type === 1) {
          // GENERAL LAND: Electric Sky Blue
          ctx.fillStyle = `rgba(56, 189, 248, ${baseAlpha * depthAlpha})`;
          ctx.beginPath();
          ctx.arc(screenX, screenY, baseSize, 0, Math.PI * 2);
          ctx.fill();
        } else {
          // OCEAN: Deep Slate Grid Point
          ctx.fillStyle = `rgba(148, 163, 184, ${baseAlpha * depthAlpha * 0.45})`;
          ctx.beginPath();
          ctx.arc(screenX, screenY, baseSize, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    }

    // 4. Calculate Hub Screen Positions
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

    // 5. Draw Dynamic Multi-Hub Mesh Telemetry Flight Arcs & Traveling Photons with Trails
    for (let l = 0; l < MESH_LINKS.length; l++) {
      const [srcIdx, dstIdx] = MESH_LINKS[l];
      const src = hubs[srcIdx];
      const dst = hubs[dstIdx];

      if (src && dst && (src.screenZ > -0.35 || dst.screenZ > -0.35)) {
        const midX = (src.screenX + dst.screenX) / 2;
        const midY = (src.screenY + dst.screenY) / 2 - (radius * 0.22);

        // Glowing Arc Wire
        ctx.strokeStyle = "rgba(0, 210, 255, 0.45)";
        ctx.lineWidth = 1.3;
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(src.screenX, src.screenY);
        ctx.quadraticCurveTo(midX, midY, dst.screenX, dst.screenY);
        ctx.stroke();
        ctx.setLineDash([]);

        // Traveling Energy Photon with Decaying Trail
        if (!reduceMotion) {
          photonProgress[l] = (photonProgress[l] + 0.007) % 1.0;
          const t = photonProgress[l];
          // Quadratic Bezier interpolation
          const px = (1 - t) * (1 - t) * src.screenX + 2 * (1 - t) * t * midX + t * t * dst.screenX;
          const py = (1 - t) * (1 - t) * src.screenY + 2 * (1 - t) * t * midY + t * t * dst.screenY;

          // Photon Trail
          const trailT = Math.max(0, t - 0.04);
          const tx = (1 - trailT) * (1 - trailT) * src.screenX + 2 * (1 - trailT) * trailT * midX + trailT * trailT * dst.screenX;
          const ty = (1 - trailT) * (1 - trailT) * src.screenY + 2 * (1 - trailT) * trailT * midY + trailT * trailT * dst.screenY;

          ctx.strokeStyle = "rgba(52, 211, 153, 0.4)";
          ctx.lineWidth = 2.0;
          ctx.beginPath();
          ctx.moveTo(tx, ty);
          ctx.lineTo(px, py);
          ctx.stroke();

          // Photon Core
          ctx.fillStyle = "#34d399"; // Neon Emerald Photon
          ctx.beginPath();
          ctx.arc(px, py, 2.6, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    }

    // 6. Draw Hub Markers, Pulsing Neon Halos & Labels
    const isLight = typeof document !== "undefined" && document.documentElement && document.documentElement.classList.contains("light");

    for (let i = 0; i < hubs.length; i++) {
      const h = hubs[i];
      if (h.screenZ > -0.1) {
        h.pulse += 0.045;
        const pulseScale = (Math.sin(h.pulse) + 1) / 2;
        const ringRadius = 4.5 + pulseScale * 10;

        // Animated Outer Radiant Ring
        ctx.strokeStyle = `rgba(0, 210, 255, ${0.9 - pulseScale * 0.8})`;
        ctx.lineWidth = 1.6;
        ctx.beginPath();
        ctx.arc(h.screenX, h.screenY, ringRadius, 0, Math.PI * 2);
        ctx.stroke();

        // Secondary Harmonic Ring for Hovered Hub
        if (h === hoveredHub) {
          ctx.strokeStyle = "rgba(52, 211, 153, 0.6)";
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.arc(h.screenX, h.screenY, 8 + pulseScale * 8, 0, Math.PI * 2);
          ctx.stroke();
        }

        // Inner Solid Luminous Core
        ctx.fillStyle = h === hoveredHub ? "#34d399" : "#00d2ff";
        ctx.beginPath();
        ctx.arc(h.screenX, h.screenY, 3.5, 0, Math.PI * 2);
        ctx.fill();

        // Hub Text Tag (Render label if front-facing or hovered)
        if (h.screenZ > 0.2 || h === hoveredHub) {
          ctx.font = "bold 10px JetBrains Mono, monospace";
          ctx.fillStyle = isLight ? "#0f172a" : "#ffffff";
          ctx.fillText(h.code, h.screenX + 8, h.screenY - 4);

          ctx.font = "9px JetBrains Mono, monospace";
          ctx.fillStyle = isLight ? "#0284c7" : "#22d3ee";
          ctx.fillText(`${h.count} nodes`, h.screenX + 8, h.screenY + 7);
        }
      }
    }

    // 7. Interactive Canvas Tooltip Card when hovering a hub
    if (hoveredHub && hoveredHub.screenZ > -0.1) {
      const h = hoveredHub;
      const cardW = 124;
      const cardH = 46;
      let cardX = h.screenX + 14;
      let cardY = h.screenY - 24;

      if (cardX + cardW > width - 8) cardX = h.screenX - cardW - 14;
      if (cardY + cardH > height - 8) cardY = height - cardH - 8;
      if (cardY < 8) cardY = 8;

      // Card Background
      ctx.fillStyle = isLight ? "rgba(255, 255, 255, 0.95)" : "rgba(7, 10, 15, 0.92)";
      ctx.strokeStyle = isLight ? "#cbd5e1" : "rgba(0, 210, 255, 0.4)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      if (typeof ctx.roundRect === "function") {
        ctx.roundRect(cardX, cardY, cardW, cardH, 8);
      } else {
        ctx.rect(cardX, cardY, cardW, cardH);
      }
      ctx.fill();
      ctx.stroke();

      // Card Content
      ctx.font = "bold 11px Plus Jakarta Sans, sans-serif";
      ctx.fillStyle = isLight ? "#0f172a" : "#f1f5f9";
      ctx.fillText(h.name || h.code, cardX + 8, cardY + 16);

      ctx.font = "600 10px JetBrains Mono, monospace";
      ctx.fillStyle = "#34d399";
      ctx.fillText(`${h.count} Proxies`, cardX + 8, cardY + 34);

      if (h.ping) {
        ctx.fillStyle = isLight ? "#475569" : "#94a3b8";
        ctx.fillText(`· ${h.ping}ms`, cardX + 72, cardY + 34);
      }
    }

    rafId = requestAnimationFrame(render);
  }

  // Pointer Interaction Listeners with Inertia Physics
  function onPointerDown(e) {
    isDragging = true;
    startX = e.clientX;
    startY = e.clientY;
    lastX = e.clientX;
    lastY = e.clientY;
    lastMoveTime = performance.now();
    velX = 0;
    velY = 0;
    canvas.setPointerCapture(e.pointerId);
  }

  function onPointerMove(e) {
    if (isDragging) {
      const now = performance.now();
      const dt = Math.max(1, now - lastMoveTime);
      const deltaX = e.clientX - lastX;
      const deltaY = e.clientY - lastY;

      velY = (deltaX * 0.006) / (dt / 16);
      velX = (deltaY * 0.006) / (dt / 16);

      rotY += deltaX * 0.006;
      rotX += deltaY * 0.006;
      rotX = Math.max(-0.85, Math.min(0.85, rotX));

      lastX = e.clientX;
      lastY = e.clientY;
      lastMoveTime = now;
    } else {
      // Check hover on hubs
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      hoveredHub = null;

      for (let i = 0; i < hubs.length; i++) {
        const h = hubs[i];
        if (h.screenZ > 0) {
          const dist = Math.hypot(mx - h.screenX, my - h.screenY);
          if (dist < 20) {
            hoveredHub = h;
            canvas.style.cursor = "pointer";
            break;
          }
        }
      }
      if (!hoveredHub) {
        canvas.style.cursor = "grab";
      }
    }
  }

  function onPointerUp(e) {
    if (isDragging) {
      const moveDist = Math.hypot(e.clientX - startX, e.clientY - startY);
      isDragging = false;
      try {
        canvas.releasePointerCapture(e.pointerId);
      } catch (err) {}

      // Click Hub Detection
      if (moveDist < 6) {
        const rect = canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;

        for (let i = 0; i < hubs.length; i++) {
          const h = hubs[i];
          if (h.screenZ > 0) {
            const dist = Math.hypot(mx - h.screenX, my - h.screenY);
            if (dist < 24) {
              if (typeof onNodeSelect === "function") {
                onNodeSelect(h);
              }
              break;
            }
          }
        }
      }
    }
  }

  canvas.addEventListener("pointerdown", onPointerDown);
  canvas.addEventListener("pointermove", onPointerMove);
  canvas.addEventListener("pointerup", onPointerUp);
  canvas.addEventListener("pointercancel", onPointerUp);

  const resizeObserver = new ResizeObserver(() => resize());
  resizeObserver.observe(canvas);

  const intersectionObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      isIntersecting = entry.isIntersecting;
      if (isIntersecting && isVisible) {
        cancelAnimationFrame(rafId);
        rafId = requestAnimationFrame(render);
      }
    });
  }, { threshold: 0.1 });
  intersectionObserver.observe(canvas);

  const handleVisibility = () => {
    isVisible = !document.hidden;
    if (isVisible && isIntersecting) {
      cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(render);
    }
  };
  document.addEventListener("visibilitychange", handleVisibility);

  resize();
  rafId = requestAnimationFrame(render);

  return {
    resize: () => {
      resize();
    },
    restart: () => {
      cancelAnimationFrame(rafId);
      resize();
      rafId = requestAnimationFrame(render);
    },
    destroy: () => {
      cancelAnimationFrame(rafId);
      resizeObserver.disconnect();
      intersectionObserver.disconnect();
      document.removeEventListener("visibilitychange", handleVisibility);
      canvas.removeEventListener("pointerdown", onPointerDown);
      canvas.removeEventListener("pointermove", onPointerMove);
      canvas.removeEventListener("pointerup", onPointerUp);
      canvas.removeEventListener("pointercancel", onPointerUp);
    }
  };
}
