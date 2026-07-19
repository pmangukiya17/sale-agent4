# World Map geography data

`WorldMap.tsx` renders real country outlines the moment a file matching
this exact spec exists here. Nothing else needs to change — no code,
no rebuild step beyond the normal dev server / build.

## Exact file

```
frontend/src/dashboard/data/countries-110m.geo.json
```

That path, that filename, exactly. `useWorldGeometry.ts` looks for it via
a Vite glob match on this literal path.

## Required format

- **GeoJSON**, not TopoJSON — a plain `FeatureCollection` of `Polygon`/
  `MultiPolygon` features. TopoJSON (arc-encoded, needs a decode step) is
  deliberately not supported, to keep the parsing code
  (`worldGeometry.ts`) simple and dependency-free.
- Coordinates in standard GeoJSON `[longitude, latitude]` order.
- Each feature's `properties` must include a country name under one of:
  `name`, `NAME`, `ADMIN`, `admin`, `name_long`, `sovereignt`, `NAME_LONG`
  (checked in that order — matches what the common public datasets below
  actually use, so you don't need to rename anything).
- **Low resolution (110m / "simplified")**, not the full-detail 10m
  version. A 110m countries file is typically 100KB–2MB; the 10m version
  can be tens of MB, which would bloat the bundle and slow down rendering
  for no visible benefit on a compact dashboard map.

## Suggested sources (any of these work as-is)

- **Natural Earth** — "Admin 0 – Countries", 1:110m scale, public domain,
  no attribution required. The canonical source most other datasets
  below are themselves derived from.
- **`world-atlas` npm package's source data**, converted to GeoJSON (the
  package itself ships TopoJSON — if you have it installed elsewhere,
  run it through `topojson-client`'s `feature()` once, outside this
  project, and save the GeoJSON result here).
- Any pre-converted "countries-110m.geo.json" / "ne_110m_admin_0_countries.geojson"
  mirror of the above — several exist on GitHub under public-domain/ODC
  licenses.

## What happens once it's here

`useWorldGeometry.ts` picks it up automatically, converts each feature's
rings into SVG path strings (`worldGeometry.ts`, same equirectangular
projection `WorldMap.tsx`'s prospect markers already use, so both stay
aligned), and `CommandCenter.tsx` passes the result into `WorldMap`'s
`geometry` prop. Country selection, prospect markers, and the Country
Intelligence drawer all continue working unchanged — they were built
against country *names*, never against how the background is drawn.
