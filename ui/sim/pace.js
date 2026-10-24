/* Shared pace for the dashed route and the boat.

   A few soi-widths of projected path (about 215–430 px) take 4–8 seconds.
   Shorter paths still last at least three seconds. Reset drops the trip.
*/

export const MAX_DRAW_PX_PER_S = 54;
export const MIN_TRIP_MS = 3000;

export function phaseDurationMs(projectedPx) {
  const px = Number(projectedPx);
  if (!Number.isFinite(px) || px <= 0) return MIN_TRIP_MS;
  return Math.max(MIN_TRIP_MS, (px / MAX_DRAW_PX_PER_S) * 1000);
}
