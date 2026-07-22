/**
 * countryNameAliases — M8.16 (World Map Geometry Verification).
 *
 * Two independent country-name vocabularies coexist in this codebase, by
 * design (see data/README.md's own note: "Country selection, prospect
 * markers... were built against country *names*, never against how the
 * background is drawn"): the real GeoJSON's official Natural Earth
 * `NAME` property (e.g. "United States of America", "Czechia",
 * "Dominican Rep."), and the common English names Discovery-sourced
 * `Prospect.country` free text and `countryCentroids.ts` actually use
 * (e.g. "united states", "czech republic", "dominican republic").
 *
 * That decoupling was fine while the geometry layer only drew a
 * background - nothing needed to match it to anything. M8.16 made the
 * real country shapes clickable, which means clicking a shape now needs
 * to find the matching prospect aggregate (if one exists) so the
 * tooltip/selection can show a real count instead of silently treating
 * every shape as "no data."
 *
 * This is a small, VERIFIED alias list, not a guess: built by diffing
 * every name in the actual 110m GeoJSON file against every key in
 * `countryCentroids.ts` (case-insensitive) and hand-checking each real
 * mismatch. Only entries confirmed to be the same country under a
 * different name are listed - this is not an attempt at exhaustive
 * ISO-code normalization (that would be a bigger, separate data-modeling
 * project; see this file's own limits below).
 *
 * Known, disclosed, NOT fixed here: Bahrain, Hong Kong, and Singapore
 * have no polygon at all in the 110m dataset (confirmed absent, not a
 * parsing bug - Natural Earth's 110m/simplified scale omits landmasses
 * too small to render meaningfully at that resolution). They still work
 * exactly as before via their centroid marker; they just can't become
 * clickable-by-shape, and switching to a higher-resolution dataset to
 * fix that would directly contradict data/README.md's own explicit
 * reason for requiring 110m (bundle size).
 */

// Keyed by the GeoJSON's own NAME property, lowercased. Value is the
// common-name form used elsewhere (countryCentroids.ts keys, and
// realistically what free-text Prospect.country data looks like).
const GEOMETRY_NAME_ALIASES: Record<string, string> = {
  "united states of america": "united states",
  czechia: "czech republic",
  "dominican rep.": "dominican republic",
};

/** Lowercases and trims, then applies the verified alias table above if
 * a match exists. Used to compare a geometry path's own name against a
 * `CountryAggregate.country` string - never used to alter what's
 * displayed to the user (the geometry's real name is always what's
 * rendered in the tooltip; this is purely a lookup key). */
export function normalizeCountryName(name: string | null | undefined): string {
  if (!name) return "";
  const lower = name.trim().toLowerCase();
  return GEOMETRY_NAME_ALIASES[lower] ?? lower;
}
