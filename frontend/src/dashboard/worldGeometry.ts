import { WORLD_MAP_WIDTH, WORLD_MAP_HEIGHT, type WorldMapGeometryPath } from "./WorldMap";

/**
 * GeoJSON → SVG path conversion for WorldMap.tsx. See
 * src/dashboard/data/README.md for the exact file this expects.
 *
 * Deliberately hand-rolled instead of pulling in d3-geo/topojson-client:
 * this sandbox has no npm registry access, and the projection math a
 * plain equirectangular map needs is linear (lon/lat -> x/y), so a
 * dependency isn't actually necessary. Projects into the exact same
 * WORLD_MAP_WIDTH/HEIGHT coordinate space WorldMap.tsx's own marker
 * projection uses (imported, not duplicated) so markers and country
 * shapes always align.
 */
function project(lon: number, lat: number): [number, number] {
  const x = ((lon + 180) / 360) * WORLD_MAP_WIDTH;
  const y = ((90 - lat) / 180) * WORLD_MAP_HEIGHT;
  return [x, y];
}

export interface GeoJsonFeature {
  type: "Feature";
  properties: Record<string, unknown>;
  geometry:
    | { type: "Polygon"; coordinates: number[][][] }
    | { type: "MultiPolygon"; coordinates: number[][][][] }
    | { type: string; coordinates: unknown };
}

export interface GeoJsonFeatureCollection {
  type: "FeatureCollection";
  features: GeoJsonFeature[];
}

// Checked in order - covers every common property key the well-known
// public country GeoJSON datasets (Natural Earth exports, geo-countries,
// etc.) tend to use, so this doesn't depend on which exact source you add.
const NAME_KEYS = ["name", "NAME", "ADMIN", "admin", "name_long", "sovereignt", "NAME_LONG"];

function extractCountryName(properties: Record<string, unknown>): string | null {
  for (const key of NAME_KEYS) {
    const value = properties[key];
    if (typeof value === "string" && value.trim().length > 0) return value;
  }
  return null;
}

function ringToPath(ring: number[][]): string {
  return (
    ring
      .map(([lon, lat], i) => {
        const [x, y] = project(lon, lat);
        return `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
      })
      .join(" ") + " Z"
  );
}

function polygonToPath(rings: number[][][]): string {
  return rings.map(ringToPath).join(" ");
}

/**
 * Converts a real countries GeoJSON FeatureCollection into the
 * `{id, d}[]` shape WorldMap.tsx's `geometry` prop expects. `id` is the
 * country's real name (from the dataset's own properties, matched
 * against Prospect.country strings the same way countryCentroids.ts
 * does) - never a fabricated or placeholder label. Features with an
 * unrecognized geometry type, or no matching name property, are skipped
 * rather than guessed at.
 */
export function buildGeometryPaths(collection: GeoJsonFeatureCollection): WorldMapGeometryPath[] {
  const paths: WorldMapGeometryPath[] = [];
  for (const feature of collection.features) {
    const name = extractCountryName(feature.properties);
    if (!name) continue;

    let d: string | null = null;
    if (feature.geometry.type === "Polygon") {
      d = polygonToPath(feature.geometry.coordinates as number[][][]);
    } else if (feature.geometry.type === "MultiPolygon") {
      d = (feature.geometry.coordinates as number[][][][]).map(polygonToPath).join(" ");
    }
    if (d) paths.push({ id: name, d });
  }
  return paths;
}
