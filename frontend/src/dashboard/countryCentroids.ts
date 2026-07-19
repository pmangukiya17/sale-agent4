/**
 * Real, approximate country centroid coordinates (lat, lon), used only to
 * POSITION a marker on WorldMap.tsx - not a fabricated dataset. Keyed by
 * common English country name (lowercased) because Prospect.country is a
 * free-text field populated by Discovery providers (see backend
 * app/models/prospect.py), not an ISO code column - there is no reference
 * FK to the `countries` table on Prospect today, so a name-based lookup is
 * the only thing that can work without a backend/schema change.
 *
 * Deliberately not exhaustive (~90 entries covering the countries that
 * actually show up in cross-border B2B trade/discovery data) rather than
 * the full ~195-country ISO list - WorldMap.tsx treats a country with
 * prospect data but no centroid match as a known, real gap (it still
 * counts everywhere aggregate totals are shown - see selectors.ts's
 * aggregateByCountry - it just can't be plotted as a dot yet). Extending
 * this list is a data change, not a redesign, exactly like the backend's
 * own `countries` reference table docstring describes for itself.
 */
export interface CountryCentroid {
  lat: number;
  lon: number;
}

export const COUNTRY_CENTROIDS: Record<string, CountryCentroid> = {
  "united states": { lat: 39.8, lon: -98.6 },
  usa: { lat: 39.8, lon: -98.6 },
  canada: { lat: 56.1, lon: -106.3 },
  mexico: { lat: 23.6, lon: -102.5 },
  brazil: { lat: -14.2, lon: -51.9 },
  argentina: { lat: -38.4, lon: -63.6 },
  chile: { lat: -35.7, lon: -71.5 },
  colombia: { lat: 4.6, lon: -74.3 },
  peru: { lat: -9.2, lon: -75.0 },
  "united kingdom": { lat: 55.4, lon: -3.4 },
  uk: { lat: 55.4, lon: -3.4 },
  ireland: { lat: 53.4, lon: -8.2 },
  france: { lat: 46.6, lon: 2.2 },
  germany: { lat: 51.2, lon: 10.4 },
  spain: { lat: 40.5, lon: -3.7 },
  portugal: { lat: 39.4, lon: -8.2 },
  italy: { lat: 41.9, lon: 12.6 },
  netherlands: { lat: 52.1, lon: 5.3 },
  belgium: { lat: 50.5, lon: 4.5 },
  switzerland: { lat: 46.8, lon: 8.2 },
  austria: { lat: 47.5, lon: 14.6 },
  poland: { lat: 51.9, lon: 19.1 },
  sweden: { lat: 60.1, lon: 18.6 },
  norway: { lat: 60.5, lon: 8.5 },
  denmark: { lat: 56.3, lon: 9.5 },
  finland: { lat: 61.9, lon: 25.7 },
  "czech republic": { lat: 49.8, lon: 15.5 },
  greece: { lat: 39.1, lon: 21.8 },
  turkey: { lat: 38.9, lon: 35.2 },
  ukraine: { lat: 48.4, lon: 31.2 },
  russia: { lat: 61.5, lon: 105.3 },
  romania: { lat: 45.9, lon: 24.9 },
  hungary: { lat: 47.2, lon: 19.5 },
  "saudi arabia": { lat: 23.9, lon: 45.1 },
  "united arab emirates": { lat: 23.4, lon: 53.8 },
  uae: { lat: 23.4, lon: 53.8 },
  qatar: { lat: 25.4, lon: 51.2 },
  israel: { lat: 31.0, lon: 34.9 },
  egypt: { lat: 26.8, lon: 30.8 },
  "south africa": { lat: -30.6, lon: 22.9 },
  nigeria: { lat: 9.1, lon: 8.7 },
  kenya: { lat: -0.02, lon: 37.9 },
  morocco: { lat: 31.8, lon: -7.1 },
  china: { lat: 35.9, lon: 104.2 },
  japan: { lat: 36.2, lon: 138.3 },
  "south korea": { lat: 35.9, lon: 127.8 },
  "hong kong": { lat: 22.3, lon: 114.2 },
  taiwan: { lat: 23.7, lon: 121.0 },
  india: { lat: 20.6, lon: 79.0 },
  pakistan: { lat: 30.4, lon: 69.3 },
  bangladesh: { lat: 23.7, lon: 90.4 },
  vietnam: { lat: 14.1, lon: 108.3 },
  thailand: { lat: 15.9, lon: 101.0 },
  indonesia: { lat: -0.8, lon: 113.9 },
  malaysia: { lat: 4.2, lon: 101.9 },
  singapore: { lat: 1.35, lon: 103.8 },
  philippines: { lat: 12.9, lon: 121.8 },
  cambodia: { lat: 12.6, lon: 105.0 },
  myanmar: { lat: 21.9, lon: 95.9 },
  australia: { lat: -25.3, lon: 133.8 },
  "new zealand": { lat: -40.9, lon: 174.9 },
  netherlands_antilles: { lat: 12.2, lon: -68.9 },
  "sri lanka": { lat: 7.9, lon: 80.7 },
  nepal: { lat: 28.4, lon: 84.1 },
  kazakhstan: { lat: 48.0, lon: 66.9 },
  uzbekistan: { lat: 41.4, lon: 64.6 },
  jordan: { lat: 30.6, lon: 36.2 },
  lebanon: { lat: 33.9, lon: 35.9 },
  kuwait: { lat: 29.3, lon: 47.5 },
  oman: { lat: 21.5, lon: 55.9 },
  bahrain: { lat: 26.0, lon: 50.6 },
  iraq: { lat: 33.2, lon: 43.7 },
  iran: { lat: 32.4, lon: 53.7 },
  ghana: { lat: 7.9, lon: -1.0 },
  ethiopia: { lat: 9.1, lon: 40.5 },
  tanzania: { lat: -6.4, lon: 34.9 },
  uganda: { lat: 1.4, lon: 32.3 },
  algeria: { lat: 28.0, lon: 1.7 },
  tunisia: { lat: 33.9, lon: 9.5 },
  serbia: { lat: 44.0, lon: 21.0 },
  croatia: { lat: 45.1, lon: 15.2 },
  slovakia: { lat: 48.7, lon: 19.7 },
  slovenia: { lat: 46.1, lon: 14.8 },
  bulgaria: { lat: 42.7, lon: 25.5 },
  "dominican republic": { lat: 18.7, lon: -70.2 },
  ecuador: { lat: -1.8, lon: -78.2 },
  venezuela: { lat: 6.4, lon: -66.6 },
  uruguay: { lat: -32.5, lon: -55.8 },
  paraguay: { lat: -23.4, lon: -58.4 },
  bolivia: { lat: -16.3, lon: -63.6 },
  panama: { lat: 8.5, lon: -80.8 },
  "costa rica": { lat: 9.7, lon: -83.8 },
  guatemala: { lat: 15.8, lon: -90.2 },
};

export function lookupCentroid(countryName: string | null | undefined): CountryCentroid | null {
  if (!countryName) return null;
  return COUNTRY_CENTROIDS[countryName.trim().toLowerCase()] ?? null;
}
