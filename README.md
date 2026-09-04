# Kale township flood inundation dashboard — 22 August → 3 September 2026

Sentinel-1 SAR flood mapping over **Kale Township, Sagaing Region** (MIMU adm3
`MMR005027`), 2,335 km², summarised per township, per MIMU village point and
against the MIMU town gazetteer.

**Live dashboard → https://geonet-myanmar.github.io/kale-flood-20260904/**

## Headline figures

| | |
|---|---|
| New inundation | **160 km²** (6.8 % of the township) |
| Land assessed | **100.0 %** |
| Villages with water at the settlement | **11** of 151 MIMU village points |
| Villages with water within 500 m | **60** (includes the 11 above) |
| Town points | 1 (Kale) — no new water within 500 m |
| Resolution | **10 m native**, every layer and every statistic |

The flooding follows the Myittha valley floor, confined between the Chin Hills
to the west and the eastern ridge — the pattern expected of a valley-bottom
flood rather than scattered detections. Every figure is in
[flood_stats.json](flood_stats.json).

## Imagery comes from Copernicus Data Space, not Earth Engine

This is the difference between this repository and the earlier flood dashboards,
and it changes how the numbers should be read.

Google Earth Engine never received the 2026-09-03 scene. ESA had both frames
online within the hour — the CDSE catalogue lists them at 23:38:48 and 23:39:13
UTC, matching the 22 August pair minute for minute on the same descending
track 4 — while GEE held nothing over the AOI a full day later. So the imagery
is fetched straight from CDSE.

| | |
|---|---|
| Pre-flood | 2026-08-22 — 2 IW GRDH frames |
| Post-flood | 2026-09-03 — 2 IW GRDH frames |
| Orbit | DESCENDING, relative orbit 4 — **same track on both dates**, 12 days = 1 repeat cycle |
| Source | CDSE Sentinel Hub Process API |
| Radiometry | **gamma0, terrain-corrected** against the Copernicus DEM |
| Threshold | VV drop < −3 dB |
| Speckle filter | circular focal mean, 30 m radius |
| Excluded | JRC permanent water (seasonality ≥ 4 months); slope ≥ 5° |
| Village impact | new water within 150 m (settlement) and 500 m (surroundings) |

**Both dates come from CDSE, never one from each.** Earth Engine serves sigma0
(ellipsoid); this serves gamma0 (terrain-corrected). Those differ by several dB
on sloping ground, and Kale sits against the Chin Hills. Since the product is a
*difference*, mixing sources would write that offset straight into the flood
mask — the same discipline as never mixing orbit passes.

**Consequently this figure is not directly comparable** with the earlier
GEE-based dashboards in this account. Internally consistent, different
radiometric convention.

JRC permanent water and the HydroSHEDS terrain mask still come from Earth
Engine, resampled onto the CDSE grid. They are static masks, not part of the
differenced pair, so they introduce no cross-source bias.

## Credentials are NOT in this repository

The pipeline needs a Copernicus Data Space account. Nothing about it is
committed here — no e-mail, no password, no token. Supply your own, either way:

```
# environment (checked first)
set CDSE_USER=you@example.com
set CDSE_PASSWORD=...

# or a two-line file, git-ignored
identity.dataspace.copernicus.eu_credentials/credentials.txt
  line 1: account e-mail
  line 2: password
```

Credentials are sent only to the CDSE token endpoint and are never logged. The
`.gitignore` excludes the whole credentials directory, and the staged file
contents were scanned for the account e-mail, the password and JWT-shaped
strings before the first commit.

## Read the numbers correctly

- **This is change, not total water.** 22 August is itself deep in the monsoon,
  so water already standing then is not counted. 160 km² is new inundation over
  12 days — a lower bound on standing water on 3 September.
- **Radar sees water, not damage.** Smooth dry surfaces can mimic the specular
  drop, and vegetation or buildings standing in water can hide it. Ground-truth
  before operational use.
- **Village points are locations, not outlines.** "Water at the settlement"
  means new water covering at least 5 % of the 150 m around the point — not a
  count of flooded buildings.
- **The AOI is the whole township**, so "% flooded" is of the whole township,
  nothing clipped.

## Data sources

- **Imagery** — Copernicus Sentinel-1 GRD IW (ESA) via the Copernicus Data
  Space Ecosystem Sentinel Hub Process API.
- **Permanent water** — JRC Global Surface Water v1.4 (via Earth Engine).
- **Terrain** — WWF HydroSHEDS void-filled DEM (via Earth Engine).
- **Boundaries, villages and towns** — [MIMU](https://geonode.themimu.info):
  the AOI is a township extract of `mmr_polbnda_adm3_250k_mimu_1` (adm3, 250k,
  v9.4); village points `mmr_sag_pplp2_250k_mimu` (PCode v9.7); town gazetteer
  `mmr_pplp1_mimu250k`. Joins are by **P-code, never by name**.
- **Basemaps** — Esri World Imagery / World Terrain, OpenStreetMap.

## Repository layout

```
index.html                        the dashboard — GENERATED, never hand-edit
assets/                           6 palette PNGs, 37 MB — the SAR backdrops
flood_stats.json                  every figure, machine-readable
flood_mapping_cdse.py             CDSE imagery + local numpy analysis  <- used here
cdse_source.py                    CDSE auth, catalogue and Process API client
flood_mapping.py                  the Earth Engine pipeline; supplies the AOI,
                                  MIMU loaders, palettes, PNG chunking and the
                                  whole dashboard, which this build imports
watch_and_run.py                  waits for a scene to reach GEE, then runs
Kale_Township_Boundary.geojson    the AOI
MyanmarTownshipBoundaries.geojson MIMU adm3, national
data/mimu/                        cached MIMU village and town point layers
```

At this AOI size the flood and permanent-water masks compress small enough to be
base64-embedded in the page, so `assets/` carries only the two 10 m SAR
backdrops. They are committed on purpose and hidden by default: `index.html`
references them by relative path, so publishing without `assets/` would give
dead SAR layers, while an ordinary visit downloads only the 0.6 MB page.

Nothing on the page points at an expiring tile server. Every pixel is served by
the site itself.

## Rebuilding

```
pip install earthengine-api geemap rasterio numpy scipy Pillow shapely
earthengine authenticate          # for the JRC / HydroSHEDS masks only

python flood_mapping_cdse.py --check   # does ESA have both dates?
python flood_mapping_cdse.py           # full run at 10 m
python flood_mapping.py --page-only    # re-render index.html, same numbers
```

Fetched imagery is cached in `cdse_cache/` (git-ignored), keyed by date, so a
re-run costs no further Sentinel Hub processing units.

### One Earth Engine trap worth knowing

`unmask(0)` **before** `clip()` silently empties an image whose projection is
derived rather than fixed — `ee.Terrain.slope()` over HydroSHEDS is exactly
that. Measured on this AOI: `slope.lt(5).add(1)` histograms 25,547 steep and
37,949 flat pixels, while the same expression with `.unmask(0)` ahead of
`.clip()` histograms nothing at all. The wrong order produced a confident
0 km² flood map rather than an error. Clip first, then unmask. The pipeline now
also refuses to write a product when less than half the land is assessable.

## Verification

1,739,359 flood pixels in the published rasters sum to **159.9 km²** against
the pipeline's **159.9 km²** — a 0.00 % difference, since both are computed on
the same grid. The map draws what the number says.

## Licence and attribution

Analysis and code: © 2026 GeoNet Myanmar. Contains modified Copernicus
Sentinel data (2026). Administrative boundaries, village and town points
© MIMU, used under MIMU terms. Basemap tiles © Esri and © OpenStreetMap
contributors.
