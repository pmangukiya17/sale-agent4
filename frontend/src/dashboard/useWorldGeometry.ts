import { useEffect, useState } from "react";
import { buildGeometryPaths, type GeoJsonFeatureCollection } from "./worldGeometry";
import type { WorldMapGeometryPath } from "./WorldMap";

/**
 * Loads real country geometry from src/dashboard/data/countries-110m.geo.json
 * IF that file exists - see data/README.md for the exact spec.
 *
 * `import.meta.glob` (a Vite build-time feature) matches files against a
 * literal path pattern and simply returns an empty object when nothing
 * matches - it does NOT fail to compile just because the target file
 * isn't in the repo yet. That's the whole mechanism this hook relies on:
 * today, with no file present, this resolves to `geometry: null` and
 * WorldMap.tsx falls back to its placeholder grid (see that component's
 * own docstring). The moment the real file is added at that exact path,
 * this starts resolving real data on the next dev-server reload/build -
 * with NO code change anywhere in this file, WorldMap.tsx, or any of its
 * callers. This is the concrete mechanism behind "only the data source
 * changes, the component is never redesigned."
 */
const geometryModules = import.meta.glob<GeoJsonFeatureCollection>("./data/countries-110m.geo.json", {
  import: "default",
});

export function useWorldGeometry() {
  const [geometry, setGeometry] = useState<WorldMapGeometryPath[] | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loaders = Object.values(geometryModules);
    if (loaders.length === 0) {
      setGeometry(null);
      setIsLoading(false);
      return;
    }
    let cancelled = false;
    loaders[0]()
      .then((data) => {
        if (cancelled) return;
        const paths = buildGeometryPaths(data);
        setGeometry(paths.length > 0 ? paths : null);
        if (paths.length === 0) {
          setError("countries-110m.geo.json was found but produced no usable paths - check its property names/geometry types against data/README.md.");
        }
      })
      .catch(() => {
        if (!cancelled) setError("Found countries-110m.geo.json but couldn't parse it as GeoJSON.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { geometry, isLoading, error };
}
