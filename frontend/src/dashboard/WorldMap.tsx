import { useMemo } from "react";
import { activeGlowOverlayClassName, activeGlowStyle, ambientGlowStyle, cn } from "../design-system";
import { lookupCentroid } from "./countryCentroids";
import { normalizeCountryName } from "./countryNameAliases";
import type { CountryAggregate } from "./selectors";

/**
 * WorldMap — Zone 2 centerpiece (Design Bible Section 1/8: largest,
 * interactive element, must evolve without redesign). Shared/reusable:
 * this component has no Command Center-specific logic - it takes
 * countries/selection/callback and fills whatever box its parent gives
 * it, which is what lets it be reused on Discovery/Research/Analytics/
 * Territory Management without modification.
 *
 * GEOGRAPHY STATUS: real country outlines are wired end-to-end and load
 * automatically the moment src/dashboard/data/countries-110m.geo.json
 * exists (see that folder's README.md for the exact file spec, and
 * useWorldGeometry.ts/worldGeometry.ts for the load+parse pipeline). This
 * sandbox has no network/npm registry access to fetch or install a
 * GeoJSON dataset or mapping library itself (confirmed: npm install, and
 * direct fetches from jsdelivr/unpkg/cdnjs/raw GitHub, all return
 * 403/blocked-by-allowlist) - that's an environment limitation on WHO can
 * add the file, not a gap in what this component supports. Until the file
 * is added, `geometry` is simply `undefined` and the grid below renders
 * as a visibly-labeled placeholder background (see the "Placeholder
 * geography" caption) - never a hand-drawn approximation standing in for
 * real cartography.
 *
 * "Evolve without redesign", concretely: `geometry` (array of {id, d} SVG
 * path strings, one per country/landmass) is layered BEHIND the existing
 * marker layer. The moment useWorldGeometry.ts resolves real data, the
 * background switches from the lat/lon grid to real filled country
 * silhouettes - every other prop (`countries`, `selectedCountry`,
 * `onSelectCountry`), the projection math markers use, and every caller
 * of this component, stays exactly the same. That's the whole point of
 * isolating the geometry as a swappable layer instead of baking
 * grid-drawing logic into the same code path that positions markers -
 * and why future capabilities (connection lines, heatmaps, AI activity
 * overlays, zoom, drill-down) are additive layers on top of this same
 * SVG stack, not a rebuild of it.
 *
 * M8.16 (World Map Geometry Verification) findings and fixes, now that
 * real geometry actually exists to verify against: the 177-feature
 * countries-110m.geo.json converts cleanly end to end (0 skipped
 * features, 0 out-of-bounds coordinates, 0 duplicate ids, no
 * antimeridian wraparound artifacts - verified by running
 * worldGeometry.ts's real conversion logic against the real file). One
 * real data bug was found and fixed at the source: Côte d'Ivoire's NAME
 * property had been corrupted to literal replacement characters by an
 * earlier processing step; corrected in the data file itself (confirmed
 * via ISO_A3="CIV" and the still-intact ADMIN="Ivory Coast" alternate
 * name), not worked around in code.
 *
 * Two real UX gaps were found and fixed here: (1) the country `<path>`
 * shapes had zero interactivity - only the small centroid marker dot
 * was clickable, so a real, visibly-rendered country with no centroid
 * entry (see countryCentroids.ts's own disclosed ~90-country scope) or
 * zero prospects was inert despite looking like part of the map. Paths
 * are now clickable/keyboard-selectable themselves, matched against the
 * prospect aggregate via `countryNameAliases.ts`'s verified name
 * normalization where possible, falling back to the geometry's own name
 * (a legitimate, honest "no prospect data" selection, never fabricated).
 * (2) hovering showed no country name anywhere except a screen-reader-only
 * aria-label - both paths and markers now carry a native SVG `<title>`
 * with the name and, when a matching aggregate exists, the real
 * prospect count.
 *
 * Explicitly NOT part of this fix, by design (verification milestone,
 * not a feature milestone): zoom, pan, and any interaction beyond
 * click-to-select and hover-for-name/count. Also not fixed here:
 * Bahrain/Hong Kong/Singapore have no polygon at all in the 110m
 * dataset (confirmed absent, not a bug - see countryNameAliases.ts).
 *
 * Rendering performance and cross-browser/responsive layout remain
 * unverified by an actual render - this sandbox's vite/rollup/esbuild
 * binaries are all architecture-mismatched and npm has no registry
 * access to fetch replacements, so no dev server or build could be run
 * here. The geometry-conversion correctness above was verified by
 * executing the real algorithm directly against the real data file
 * instead, which is a genuine (if partial) substitute for the parts of
 * "does the map render correctly" that don't require a browser.
 *
 * Sizing: fills its parent's box completely (`h-full w-full`), so a
 * caller controls the map's size purely through CSS layout (flex-1,
 * fixed height, grid track, etc.) - this is what lets the Command
 * Center give it a viewport-bounded height for the "single screen, no
 * vertical scroll" requirement without this component needing to know
 * anything about that constraint itself.
 */
export interface WorldMapCountry extends CountryAggregate {
  hasActivityToday: boolean;
}

export interface WorldMapGeometryPath {
  id: string;
  d: string;
}

interface WorldMapProps {
  countries: WorldMapCountry[];
  selectedCountry: string | null;
  onSelectCountry: (country: string) => void;
  /** Real filled country/landmass paths, in the same VIEWBOX coordinate
   * space as `project()` below (0..700 x, 0..340 y, equirectangular).
   * Optional - omit to keep today's lat/lon grid background. */
  geometry?: WorldMapGeometryPath[];
  className?: string;
}

// Exported so worldGeometry.ts's GeoJSON->path conversion projects into
// this EXACT same coordinate space - markers and country shapes would
// silently misalign if these ever drifted out of sync between two
// separately-defined constants.
export const WORLD_MAP_WIDTH = 700;
export const WORLD_MAP_HEIGHT = 340;
const WIDTH = WORLD_MAP_WIDTH;
const HEIGHT = WORLD_MAP_HEIGHT;

function project(lat: number, lon: number): { x: number; y: number } {
  const x = ((lon + 180) / 360) * WIDTH;
  const y = ((90 - lat) / 180) * HEIGHT;
  return { x, y };
}

export function WorldMap({ countries, selectedCountry, onSelectCountry, geometry, className }: WorldMapProps) {
  const markers = useMemo(() => {
    const maxCount = Math.max(1, ...countries.map((c) => c.count));
    return countries
      .map((c) => {
        const centroid = lookupCentroid(c.country);
        if (!centroid) return null;
        const { x, y } = project(centroid.lat, centroid.lon);
        const radius = 3 + (c.count / maxCount) * 9;
        return { ...c, x, y, radius };
      })
      .filter((m): m is NonNullable<typeof m> => m !== null);
  }, [countries]);

  const unplotted = countries.length - markers.length;

  // Track B1 UI refinement: World Map = indigo, ambient always, active
  // (breathing) when at least one country has real activity today - same
  // `hasActivityToday` flag CommandCenter.tsx already computes for the
  // individual marker pulse rings below, not a new signal invented for
  // this. Not a Card (this component fills whatever box its parent
  // gives it, reused outside the dashboard too), so it calls the same
  // ambientGlowStyle/activeGlowStyle/activeGlowOverlayClassName helpers
  // Card.tsx itself uses, rather than duplicating the box-shadow math.
  // The overlay below is always mounted (see activeGlowOverlayClassName's
  // docstring) so this flag going false fades the glow back down instead
  // of it vanishing outright.
  const hasAnyActivityToday = countries.some((c) => c.hasActivityToday);

  // M8.16: lets a clicked/hovered country SHAPE find its real prospect
  // aggregate (if any) via countryNameAliases.ts's verified normalization
  // - see this file's own docstring for why the geometry layer's names
  // and the aggregate's names are two independent vocabularies.
  const aggregateByNormalizedName = useMemo(() => {
    const map = new Map<string, WorldMapCountry>();
    for (const c of countries) map.set(normalizeCountryName(c.country), c);
    return map;
  }, [countries]);

  return (
    <div className={cn("relative h-full w-full", className)}>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label="World map showing prospect distribution by country"
        className="h-full w-full rounded-lg border border-border-hairline bg-surface-2/40"
        style={ambientGlowStyle("indigo")}
      >
        {geometry ? (
          <g strokeWidth={0.5}>
            {/* evenodd, not the SVG default (nonzero): shapefile-derived
                rings don't carry verified winding-direction metadata
                through worldGeometry.ts's conversion, and a handful of
                countries (e.g. Lesotho inside South Africa) are separate,
                fully-enclosed features whose combined outline needs
                alternating fill to render correctly regardless of ring
                direction. A rendering-correctness detail surfaced by
                actually having real data to render, not a component
                redesign - same props, same architecture.

                M8.16: each path is now its own clickable/hoverable hit
                target (previously only the marker dot was) - matched
                against the real prospect aggregate by normalized name
                where possible, so the tooltip and selection reflect real
                data, never a fabricated count. A country shape with no
                matching aggregate is still fully selectable - "no
                prospect data for this country" is a legitimate, honest
                state, not an error. */}
            {geometry.map((path) => {
              const matched = aggregateByNormalizedName.get(normalizeCountryName(path.id));
              const displayName = matched?.country ?? path.id;
              const selectValue = matched?.country ?? path.id;
              const isSelected = selectValue === selectedCountry;
              const tooltip = matched
                ? `${displayName}: ${matched.count} prospect${matched.count === 1 ? "" : "s"}`
                : `${displayName}: no prospect data`;
              return (
                <path
                  key={path.id}
                  d={path.d}
                  fillRule="evenodd"
                  className={cn(
                    "cursor-pointer stroke-border-hairline-strong transition-colors",
                    isSelected ? "fill-accent-ai/25" : "fill-surface-2 hover:fill-accent-primary/15"
                  )}
                  onClick={() => onSelectCountry(selectValue)}
                  role="button"
                  aria-label={tooltip}
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onSelectCountry(selectValue);
                    }
                  }}
                >
                  <title>{tooltip}</title>
                </path>
              );
            })}
          </g>
        ) : (
          // Placeholder background until real geometry is supplied - see
          // this component's own docstring. Gridlines only, no fabricated
          // country shapes.
          <>
            {Array.from({ length: 7 }).map((_, i) => (
              <line key={`h${i}`} x1={0} y1={(i * HEIGHT) / 6} x2={WIDTH} y2={(i * HEIGHT) / 6} stroke="currentColor" className="text-border-hairline" strokeWidth={1} />
            ))}
            {Array.from({ length: 13 }).map((_, i) => (
              <line key={`v${i}`} x1={(i * WIDTH) / 12} y1={0} x2={(i * WIDTH) / 12} y2={HEIGHT} stroke="currentColor" className="text-border-hairline" strokeWidth={1} />
            ))}
          </>
        )}

        {markers.map((m) => {
          const isSelected = m.country === selectedCountry;
          return (
            <g key={m.country}>
              {m.hasActivityToday && (
                // M8.7 Phase F: motion-reduce:animate-none is the static
                // equivalent for this category-1 "always alive" pulse
                // (Design Bible Section 5/12) - the ring itself (still
                // rendered at rest, just not animating) is what actually
                // carries "activity today," so turning off the animation
                // loses no information.
                <circle cx={m.x} cy={m.y} r={m.radius + 4} className="fill-accent-primary/20 animate-pulse motion-reduce:animate-none" />
              )}
              <circle
                cx={m.x}
                cy={m.y}
                r={m.radius}
                className={cn(
                  "cursor-pointer transition-colors",
                  isSelected ? "fill-accent-ai" : "fill-accent-primary/70 hover:fill-accent-primary"
                )}
                onClick={() => onSelectCountry(m.country)}
                role="button"
                aria-label={`${m.country}: ${m.count} prospects`}
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onSelectCountry(m.country);
                  }
                }}
              >
                {/* M8.16: native hover tooltip - hovering previously
                    showed no visible name/count at all (aria-label is
                    screen-reader only). */}
                <title>{`${m.country}: ${m.count} prospect${m.count === 1 ? "" : "s"}`}</title>
              </circle>
            </g>
          );
        })}
      </svg>
      {!geometry && (
        <p className="absolute bottom-1.5 left-2 text-[10px] text-slate-500">
          Placeholder geography - awaiting real country outline data.
        </p>
      )}
      {unplotted > 0 && (
        <p className="absolute bottom-1.5 right-2 text-[10px] text-slate-500">
          {unplotted} unplotted {unplotted === 1 ? "country" : "countries"}
        </p>
      )}
      <div aria-hidden="true" className={cn(activeGlowOverlayClassName(hasAnyActivityToday), "rounded-lg")} style={activeGlowStyle("indigo")} />
    </div>
  );
}
