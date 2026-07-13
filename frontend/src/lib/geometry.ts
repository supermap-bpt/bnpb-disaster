/** Flattens GeoJSON Polygon ([ring]) or MultiPolygon ([[ring], [ring], ...])
 * coordinates down to a flat list of [lon, lat] points, regardless of
 * nesting depth. A plain `.flat()` call assumes one fixed depth and silently
 * miscomputes for whichever shape it wasn't tuned for. */
export function flattenFootprintPoints(coordinates: unknown): [number, number][] {
  const arr = coordinates as unknown[];
  if (arr.length === 0) return [];
  if (typeof (arr[0] as number[])[0] === "number") {
    return arr as [number, number][];
  }
  return (arr as unknown[][]).flatMap((child) => flattenFootprintPoints(child));
}
