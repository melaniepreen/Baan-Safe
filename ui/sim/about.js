/* A short Pixi picture for the About dialog. Same renderer as the town. */

import { Application, Graphics } from "./vendor/pixi.min.mjs";

let app = null;

function project(x, y, z) {
  return { x: (x - y) * 22 + 280, y: (x + y) * 11 - z * 18 + 118 };
}

function poly(g, points, color, alpha) {
  const flat = [];
  for (const point of points) flat.push(point.x, point.y);
  g.poly(flat, true).fill({ color, alpha: alpha == null ? 1 : alpha });
}

function house(g, x, y, w, d, floors, roof) {
  const z0 = 8;
  const z1 = z0 + floors * 16;
  const wall = roof === 0xc45c4a ? 0x243044 : 0x1a2433;
  poly(g, [project(x + w, y, z0), project(x + w, y + d, z0), project(x + w, y + d, z1), project(x + w, y, z1)], 0x121a28);
  poly(g, [project(x, y + d, z0), project(x + w, y + d, z0), project(x + w, y + d, z1), project(x, y + d, z1)], wall);
  const ridge = z1 + 10;
  poly(
    g,
    [project(x - 1, y + d + 1, z1), project(x + w + 1, y + d + 1, z1), project(x + w / 2, y + d / 2, ridge)],
    roof
  );
}

function water(g, level) {
  const z = 4 + level * 28;
  poly(
    g,
    [project(-2, 18, z), project(22, 18, z), project(22, -1, z), project(-2, -1, z)],
    0x1c4d63,
    0.72
  );
}

export async function mountAbout(host) {
  stopAbout();
  if (!host) return;
  host.replaceChildren();
  const next = new Application();
  try {
    await next.init({
      width: 640,
      height: 200,
      background: 0x0c1220,
      antialias: true,
      autoDensity: true,
      resolution: Math.min(window.devicePixelRatio || 1, 2),
    });
  } catch (error) {
    return;
  }
  app = next;
  host.appendChild(app.canvas);
  const picture = new Graphics();
  app.stage.addChild(picture);
  const started = performance.now();
  app.ticker.add(() => {
    const t = (performance.now() - started) / 1000;
    const level = 0.28 + 0.22 * (0.5 + 0.5 * Math.sin(t * 0.7));
    picture.clear();
    house(picture, 1, 2, 4.2, 3.2, 2, 0xc45c4a);
    house(picture, 6.2, 3.4, 3.4, 2.8, 3, 0x2f6fbf);
    house(picture, 11, 1.6, 5.2, 3.6, 2, 0x8a93a3);
    house(picture, 16.4, 3, 3.2, 2.6, 1, 0x014855);
    water(picture, level);
  });
}

export function stopAbout() {
  if (!app) return;
  const current = app;
  app = null;
  current.destroy(true);
}
