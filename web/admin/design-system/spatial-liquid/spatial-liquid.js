/* FZP Design System · Spatial Liquid progressive WebGL adapter */
const DEFAULTS = {
  resolution: 1.25,
  refraction: 0.008,
  bevelDepth: 0.18,
  bevelWidth: 0.16,
  frost: 0.06,
  shadow: true,
  specular: true,
  tilt: true,
  tiltFactor: 2,
  reveal: "none",
};

let batchNumber = 0;

function hasWebGL() {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(
      canvas.getContext("webgl2") ||
        canvas.getContext("webgl") ||
        canvas.getContext("experimental-webgl"),
    );
  } catch {
    return false;
  }
}

function resolveRoot(root) {
  return typeof root === "string"
    ? document.querySelector(root)
    : root || document.querySelector(".fzp-spatial");
}

/**
 * Converts semantic Spatial panels into the structure required by liquidGL.
 *
 * Consumer markup stays simple:
 *   <section data-fzp-liquid>Visible content...</section>
 *
 * The generated .fzp-liquid-target is an empty background sibling. The WebGL
 * canvas can therefore never cover or capture the panel's interactive content.
 */
export function prepareSpatialPanels(rootInput) {
  const root = resolveRoot(rootInput);
  if (!root) {
    return { root: null, panels: [], layers: [] };
  }

  const panels = [
    ...(root.matches?.("[data-fzp-liquid]") ? [root] : []),
    ...root.querySelectorAll("[data-fzp-liquid]"),
  ];
  const layers = [];

  for (const panel of panels) {
    panel.classList.add("fzp-spatial-panel");

    let layer = [...panel.children].find((child) =>
      child.classList.contains("fzp-spatial-panel__glass"),
    );

    if (!layer) {
      layer = document.createElement("div");
      layer.className = "fzp-liquid-target fzp-spatial-panel__glass";
      layer.setAttribute("aria-hidden", "true");
      layer.setAttribute("data-liquid-ignore", "");
      panel.prepend(layer);
    }

    layers.push(layer);
  }

  return { root, panels, layers };
}

function enableCssFallback(root, layers, reason) {
  for (const layer of layers) {
    layer.style.opacity = "1";
    layer.style.pointerEvents = "none";
  }
  root.dataset.fzpWebgl = "fallback";
  root.dataset.fzpWebglReason = reason;
  const state = { active: false, status: "fallback", reason };
  return { ...state, ready: Promise.resolve(state) };
}

/**
 * Enhances [data-fzp-liquid] panels with liquidGL.
 *
 * CSS is usable immediately. The returned `ready` promise reports whether
 * WebGL actually initialized instead of assuming that renderer creation worked.
 */
export function initSpatialLiquid(options = {}) {
  const {
    root: rootInput,
    target: explicitTarget,
    timeout = 6000,
    allowMobileWebGL = false,
    on,
    ...rendererOptions
  } = options;
  const { root, layers } = prepareSpatialPanels(rootInput);

  if (!root) {
    const state = {
      active: false,
      status: "fallback",
      reason: "root-not-found",
    };
    return { ...state, ready: Promise.resolve(state) };
  }

  const pendingLayers = layers.filter(
    (layer) => layer.dataset.fzpLiquidBound !== "true",
  );

  if (pendingLayers.length === 0) {
    const active = root.dataset.fzpWebgl === "active";
    const state = {
      active,
      status: active ? "active" : "fallback",
      reason: "already-initialized",
    };
    return { ...state, ready: Promise.resolve(state) };
  }

  if (!hasWebGL()) {
    return enableCssFallback(root, pendingLayers, "webgl-unavailable");
  }

  if (
    !allowMobileWebGL &&
    window.matchMedia("(max-width: 768px), (pointer: coarse)").matches
  ) {
    return enableCssFallback(
      root,
      pendingLayers,
      "mobile-performance-policy",
    );
  }

  if (typeof window.html2canvas !== "function") {
    return enableCssFallback(
      root,
      pendingLayers,
      "snapshot-renderer-unavailable",
    );
  }

  if (typeof window.liquidGL !== "function") {
    return enableCssFallback(
      root,
      pendingLayers,
      "liquid-renderer-unavailable",
    );
  }

  const batch = `fzp-liquid-${++batchNumber}`;
  for (const layer of pendingLayers) {
    layer.dataset.fzpLiquidBatch = batch;
  }

  const target = explicitTarget || `[data-fzp-liquid-batch="${batch}"]`;
  let settled = false;
  let settleReady;
  let fallbackTimer;
  const ready = new Promise((resolve) => {
    settleReady = resolve;
  });

  const revealLayers = () => {
    for (const layer of pendingLayers) {
      layer.style.opacity = "1";
      layer.style.pointerEvents = "none";
    }
  };

  const finish = (result) => {
    if (settled) return;
    settled = true;
    window.clearTimeout(fallbackTimer);
    settleReady(result);
  };

  root.dataset.fzpWebgl = "initializing";
  revealLayers();

  fallbackTimer = window.setTimeout(() => {
    revealLayers();
    root.dataset.fzpWebgl = "fallback";
    root.dataset.fzpWebglReason = "initialization-timeout";
    finish({
      active: false,
      status: "fallback",
      reason: "initialization-timeout",
    });
  }, timeout);

  try {
    const reduceMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    let lenses;
    lenses = window.liquidGL({
      ...DEFAULTS,
      ...rendererOptions,
      tilt: reduceMotion ? false : (rendererOptions.tilt ?? DEFAULTS.tilt),
      target,
      snapshot: rendererOptions.snapshot || "body",
      on: {
        ...on,
        init(lens) {
          revealLayers();
          for (const layer of pendingLayers) {
            layer.dataset.fzpLiquidBound = "true";
          }
          root.dataset.fzpWebgl = "active";
          delete root.dataset.fzpWebglReason;
          on?.init?.(lens);
          finish({ active: true, status: "active", lenses });
        },
      },
    });

    revealLayers();
    return { active: false, status: "initializing", lenses, ready };
  } catch (error) {
    revealLayers();
    root.dataset.fzpWebgl = "fallback";
    root.dataset.fzpWebglReason = "renderer-error";
    console.warn(
      "[FZP Spatial Liquid] WebGL enhancement failed; using CSS fallback.",
      error,
    );
    const state = {
      active: false,
      status: "fallback",
      reason: "renderer-error",
      error,
    };
    finish(state);
    return { ...state, ready };
  }
}
