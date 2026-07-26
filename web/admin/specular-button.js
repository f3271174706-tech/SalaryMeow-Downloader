import { Color, Mesh, Program, Renderer, Triangle } from "/admin-assets/vendor/ogl/index.js";

const PAD = 20;

const VERTEX_SHADER = `#version 300 es
in vec2 position;

void main() {
  gl_Position = vec4(position, 0.0, 1.0);
}
`;

const FRAGMENT_SHADER = `#version 300 es
precision highp float;

uniform vec2 uCenter;
uniform vec2 uHalfSize;
uniform float uRadius;
uniform float uAngle;
uniform float uPx;
uniform vec3 uLineColor;
uniform vec3 uBaseColor;
uniform float uIntensity;
uniform float uShineSize;
uniform float uShineFade;
uniform float uThickness;
uniform float uBaseWidth;

out vec4 fragColor;

float sdRoundedRect(vec2 p, vec2 b, float r) {
  vec2 q = abs(p) - b + r;
  return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
}

float gaussianLine(float d, float sigma) {
  float x = d / (sigma + 1e-6);
  float k = mix(1.0, 1.6, smoothstep(0.0, 1.5, x));
  return exp(-k * x * x);
}

void main() {
  vec2 p = gl_FragCoord.xy - uCenter;
  float d = sdRoundedRect(p, uHalfSize, uRadius);
  vec2 light = vec2(cos(uAngle), sin(uAngle));
  float base = (1.0 - smoothstep(0.0, uBaseWidth, abs(d))) * 0.45;
  vec2 normal = normalize(p / (uHalfSize * uHalfSize) + 1e-6);
  float phi = acos(clamp(abs(dot(normal, light)), 0.0, 1.0));
  float rim = 1.0 - smoothstep(uShineSize - uShineFade, uShineSize + uShineFade + 1e-4, phi);
  float line = gaussianLine(d, uThickness);
  float edgeClamp = 1.0 - smoothstep(0.5 * uPx, 3.0 * uPx, abs(d));
  float highlight = line * rim * edgeClamp * uIntensity;
  vec3 color = uBaseColor * base + uLineColor * highlight;
  fragColor = vec4(color, clamp(base + highlight, 0.0, 1.0));
}
`;

const OPTIONS = {
  radius: 18,
  lineColor: "#ffffff",
  baseColor: "#525252",
  intensity: 1,
  shineSize: 10,
  shineFade: 40,
  thickness: 1,
  speed: 0.35,
  followMouse: true,
  proximity: 250,
  autoAnimate: false,
};

function initSpecularButton(button) {
  const effectLayer = button.querySelector(".specular-button__fx");
  if (!effectLayer || button.dataset.specularReady === "true") return;

  try {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const renderer = new Renderer({
      alpha: true,
      premultipliedAlpha: true,
      antialias: true,
      depth: false,
      dpr,
    });
    if (!renderer.isWebgl2) {
      renderer.gl.getExtension("WEBGL_lose_context")?.loseContext();
      return;
    }

    const gl = renderer.gl;
    gl.clearColor(0, 0, 0, 0);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);

    const geometry = new Triangle(gl);
    if (geometry.attributes.uv) delete geometry.attributes.uv;

    const program = new Program(gl, {
      vertex: VERTEX_SHADER,
      fragment: FRAGMENT_SHADER,
      transparent: true,
      depthTest: false,
      depthWrite: false,
      uniforms: {
        uCenter: { value: [0, 0] },
        uHalfSize: { value: [1, 1] },
        uRadius: { value: 0 },
        uAngle: { value: 2.4 },
        uPx: { value: dpr },
        uLineColor: { value: [1, 1, 1] },
        uBaseColor: { value: [0.32, 0.32, 0.32] },
        uIntensity: { value: 1 },
        uShineSize: { value: 0.17 },
        uShineFade: { value: 0.7 },
        uThickness: { value: 1 },
        uBaseWidth: { value: dpr },
      },
    });

    const mesh = new Mesh(gl, { geometry, program });
    effectLayer.append(gl.canvas);
    button.dataset.specularReady = "true";

    const size = { width: 1, height: 1 };
    const resize = () => {
      const rect = button.getBoundingClientRect();
      size.width = rect.width;
      size.height = rect.height;
      renderer.setSize(rect.width + PAD * 2, rect.height + PAD * 2);
      program.uniforms.uCenter.value = [(PAD + rect.width / 2) * dpr, (PAD + rect.height / 2) * dpr];
      program.uniforms.uHalfSize.value = [(rect.width / 2) * dpr, (rect.height / 2) * dpr];
    };
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(button);
    resize();

    let pointerAngle = null;
    let proximity = 0;
    const onPointerMove = (event) => {
      const rect = button.getBoundingClientRect();
      const centerX = rect.left + rect.width / 2;
      const centerY = rect.top + rect.height / 2;
      const deltaX = Math.max(rect.left - event.clientX, 0, event.clientX - rect.right);
      const deltaY = Math.max(rect.top - event.clientY, 0, event.clientY - rect.bottom);
      const distance = Math.hypot(deltaX, deltaY);

      if (distance === 0) {
        const normalizedX = (event.clientX - centerX) / (rect.width / 2);
        const normalizedY = (centerY - event.clientY) / (rect.height / 2);
        pointerAngle =
          Math.atan2(2 / rect.height, -2 / rect.width) + normalizedX * 0.3 + normalizedY * 0.15;
      } else {
        pointerAngle = Math.atan2(centerY - event.clientY, event.clientX - centerX);
      }

      const amount = Math.max(0, 1 - distance / OPTIONS.proximity);
      proximity = amount * amount * (3 - 2 * amount);
    };
    window.addEventListener("pointermove", onPointerMove, { passive: true });

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const lineColor = new Color();
    const baseColor = new Color();
    let angle = 2.4;
    let idleAngle = 2.4;
    let brightness = 0;
    let previousTime = performance.now();

    const render = (now) => {
      const deltaTime = Math.min((now - previousTime) / 1000, 0.05);
      previousTime = now;
      idleAngle += reduceMotion.matches ? 0 : OPTIONS.speed * deltaTime;

      const followsPointer = OPTIONS.followMouse && pointerAngle !== null && (!OPTIONS.autoAnimate || proximity > 0);
      const targetAngle = followsPointer ? pointerAngle : idleAngle;
      const angleDifference = ((targetAngle - angle + Math.PI * 3) % (Math.PI * 2)) - Math.PI;
      angle += angleDifference * (1 - Math.exp(-deltaTime * 7));

      const targetBrightness = OPTIONS.autoAnimate ? 1 : proximity;
      brightness += (targetBrightness - brightness) * (1 - Math.exp(-deltaTime * 8));

      lineColor.set(OPTIONS.lineColor);
      baseColor.set(OPTIONS.baseColor);
      program.uniforms.uAngle.value = angle;
      program.uniforms.uRadius.value =
        Math.min(OPTIONS.radius, Math.min(size.width, size.height) / 2) * dpr;
      program.uniforms.uLineColor.value = [lineColor.r, lineColor.g, lineColor.b];
      program.uniforms.uBaseColor.value = [baseColor.r, baseColor.g, baseColor.b];
      program.uniforms.uIntensity.value = OPTIONS.intensity * brightness;
      program.uniforms.uShineSize.value = (OPTIONS.shineSize * Math.PI) / 180;
      program.uniforms.uShineFade.value = (OPTIONS.shineFade * Math.PI) / 180;
      program.uniforms.uThickness.value = OPTIONS.thickness * dpr;
      renderer.render({ scene: mesh });
      requestAnimationFrame(render);
    };
    requestAnimationFrame(render);
  } catch (error) {
    button.dataset.specularReady = "fallback";
    console.warn("SpecularButton WebGL effect unavailable.", error);
  }
}

document.querySelectorAll("[data-specular-button]").forEach(initSpecularButton);
