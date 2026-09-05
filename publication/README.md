# Kale flood publication figure

The deliverable is `output/kale_flood_publication_600dpi.jpg`: an A4 portrait
figure, 4962 × 7014 pixels, RGB JPEG at 600 dpi, quality 98 with no chroma
subsampling. A PDF companion retains vector text and linework. The figure has
an overview, central-valley enlargement, Myanmar/Sagaing locator, geographic
graticules, true-north arrow, ground-distance scale bars, MIMU boundaries and
town location, and the post-event SAR backdrop.

## What was reproduced

Source repository: <https://github.com/geonet-myanmar/kale-flood-20260904>, commit
`8f208f3d1a41823b3cbd11b684a80ad7ca2e92cf`.

This upstream source commit is recorded separately from the current build's
Git commit, so publishing or committing this derivative project does not change
the recorded origin of the scientific inputs.

The existing **CDSE** workflow (`flood_mapping_cdse.py` and `cdse_source.py`)
was inspected, including its imported configuration and raster encoder in
`flood_mapping.py`. This build **recovers the exact published classification**
from the lossless palette PNG chunks embedded in `index.html`. It does not
claim to have rerun Sentinel-1 processing or independently validated flood
accuracy. The published mask already contains the original threshold,
water exclusion, slope exclusion and AOI clipping. No pixels were manually
drawn, smoothed, removed, filled, reclassified, or inferred from map colors.

This is possible because the original encoder saves the class arrays directly
as PNG palette indices, retaining every class pixel, and stores geographic
bounds for each chunk. The script decodes these indices and reassembles their
original grid. It never uses screenshots or thresholds the quantized SAR
background. PNG chunk placement, non-overlap, binary values, AOI containment,
flood/water mutual exclusion, and GeoTIFF write/read equality are checked.

A fresh end-to-end classification could not be run in this environment because
the original Earth Engine authentication/project access and terrain mask were
unavailable. CDSE credentials alone do not grant Earth Engine access. The
repository does not archive its continuous VV inputs, terrain mask, or full
validity mask. Downloading new VV alone would not close that gap, so no metered
imagery fetch was needed to produce this exact static reproduction.

The public CDSE catalogue was queried successfully on 5 September 2026; both
dates have two online Sentinel-1D IW GRDH frames. Their product names and sensing
start timestamps are recorded in `catalogue_check.json`. Catalogue availability
confirms the scenes, not an independent rerun of their classification.

## Retained processing method

1. AOI: whole Kale Township, MIMU P-code `MMR005027`, from the original GeoJSON.
2. Baseline: **22 August 2026**; event: **3 September 2026** (UTC day windows,
   no neighboring-date substitution). Descending relative orbit **4**.
3. CDSE Sentinel Hub Process API, Sentinel-1 IW GRD dual polarization, VV used;
   terrain-corrected gamma-zero, orthorectification and Copernicus DEM.
4. Both dates converted from positive linear VV to dB. Nonpositive/no-data
   samples excluded. A circular focal mean is applied **in dB**, ignoring
   invalid neighbors, with a nominal 30 m radius (3 grid cells).
5. Candidate inundation: smoothed post-event VV minus smoothed baseline VV
   **strictly less than −3 dB**.
6. Exclude JRC GSW v1.4 `seasonality >= 4` and HydroSHEDS-derived slopes
   `>= 5°`; require valid observations on both dates and the terrain land mask.
   Original Earth Engine ancillary masks are nearest-neighbor resampled to the
   CDSE grid. The order of `clip()` before `unmask()` is retained upstream.
7. Clip the positive class to the township. Area totals use the original
   latitude-weighted pixel-area formula without changing its approximation.

The live configuration and CDSE pipeline govern this product. Some docstrings
and comments in the shared Earth Engine file describe older locations, dates
and tracks; those stale comments were not used as analysis parameters.

## Grid, values and cartographic choices

`flood_native.tif` and `water_native.tif` are georeferenced, compressed,
tiled, single-band UInt8 GeoTIFFs in **EPSG:4326**. They retain the original
3703-column × 11945-row grid and affine transform. Both use:

| Value | Meaning |
|---|---|
| 0 | No positive class in the archived layer |
| 1 | New inundation (`flood_native`) or reference water (`water_native`) |
| 255 | Outside the study area; GeoTIFF NoData |

**Zero is not proof of assessed dry land.** It includes cells excluded by the
method and potentially unassessed cells; the original complete validity mask
is not present in the dashboard. No new validity layer was fabricated.

The repository calls its spacing “10 m.” Its actual angular spacing is
`10 / 111319.49` degrees in both directions: approximately 9.2 m east–west and
10 m north–south at Kale. It is neither a square 10 m UTM analysis grid nor a
claim of 10 m independent sensor resolving power. The nominal circular filter
is a 3-pixel disk on that angular grid. These original choices are preserved.

For cartography only, masks are nearest-neighbor reprojected to **WGS 84 / UTM
zone 46N (EPSG:32646)**, at 25 m in the overview and 10 m in the detail panel.
The post-event 8-bit display SAR, already focal-filtered and stretched from
−25 to 0 dB by the repository, uses bilinear display resampling and low opacity.
It is never used for classification or statistics. JPEG/print colors are
cartographic representations; use the supplied native GeoTIFF for analysis.

Graticules show WGS 84 longitude/latitude. The north arrow follows geodetic
true north at its location; scale-bar lengths use WGS 84 geodesic distances
projected locally into UTM. The locator is a geographic overview assembled
from the same national MIMU township boundaries, with Sagaing highlighted.
Township labels outside the AOI and the Kale town point use the original MIMU
data. No external basemap tiles or artificial terrain were introduced.

The blue class is labeled **reference water**, because `seasonality >= 4`
also includes seasonal water; the repository calls it permanent water.
This is a labeling clarification and does not change the mask.

## Numerical verification

| Class | Positive pixels | Area, km² |
|---|---:|---:|
| New inundation | 1,739,359 | 159.922617707171 |
| JRC reference water | 180,303 | 16.588836564320 |

Both totals match `flood_stats.json` to floating-point precision. New inundation
is 6.848135% of the repository's 2335.272433 km² rasterized township area.
These are **AOI-level** totals; the repository's separately rasterized township
zonal record differs slightly at the boundary and is not substituted here.
`output/validation.json` records counts, checks, software versions, source
commit, transforms, and input/output SHA-256 digests.

## Reproduce the delivered figure offline

From the repository root:

```bash
python -m venv .venv
.venv/bin/pip install -r publication/requirements.txt
.venv/bin/python publication/make_map.py
```

All data needed for this mode are already in the cloned repository. It uses
neither CDSE credentials nor Earth Engine and leaves all original files intact.
Output goes to `publication/output/`; `--output PATH` and `--dpi N` are supported.

## Optional complete rerun of the original analysis

`rerun_workflow.py` copies the unchanged upstream code and MIMU inputs into a
separate build directory, checks Earth Engine initialization before starting,
sets the authorized Cloud project and optional external CDSE credential-file
path, and invokes the original workflow with `--keep-tif`. It retains the raw
VV cache and intermediate ancillary masks. The wrapper has been syntax/CLI
checked; the authenticated remote processing path has **not** been executed.

```bash
.venv/bin/pip install -r publication/requirements-workflow.txt
.venv/bin/earthengine authenticate
.venv/bin/python publication/rerun_workflow.py \
  --earth-engine-project YOUR_ENABLED_PROJECT \
  --credentials /absolute/path/to/credentials_CDSE.txt

# Render the newly generated dashboard using exactly the same cartography:
.venv/bin/python publication/make_map.py \
  --repo publication/workflow_rerun \
  --output publication/workflow_rerun/publication_map
```

Alternatively, the upstream code accepts `CDSE_USER` and `CDSE_PASSWORD` in
the environment. Do not put credentials in source code, command arguments,
archives or publication outputs. The wrapper preserves existing cache files
for subsequent reruns. Sentinel Hub retrieval incurs its normal processing-unit
usage. Remote processing services and source data may evolve; inspect the new
validation report rather than assuming a future rerun is pixel-identical.

The original Process request filters by day, descending direction, IW and DV;
it does not explicitly pin product UUIDs or pass relative orbit into the Process
request. Relative orbit 4 is specified in the repository metadata/configuration.
The catalogue product names are provided to document the selected days without
claiming the original API did more selection than its code actually implements.

## Caption and sources

Suggested caption is in `caption.md`. This is remotely sensed new inundation
between two monsoon acquisitions, not total standing water, building damage,
or ground-validated flood extent. Water already present on 22 August is not
counted by the change threshold; vegetation, buildings and smooth dry surfaces
can affect SAR detection. These limits belong with the interpretation of the
figure in a manuscript.

- Original analysis/code: © 2026 GeoNet Myanmar, source repository and commit above.
- Contains modified Copernicus Sentinel data (2026).
- CDSE radiometry/processing definitions:
  <https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/S1GRD.html>.
- JRC GSW v1.4: <https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_4_GlobalSurfaceWater>.
  Source: EC JRC/Google. Cite Pekel, J.-F., Cottam, A., Gorelick, N. & Belward,
  A. S. (2016), *High-resolution mapping of global surface water and its
  long-term changes*, Nature 540, 418–422, <https://doi.org/10.1038/nature20584>.
- HydroSHEDS: <https://developers.google.com/earth-engine/datasets/catalog/WWF_HydroSHEDS_03VFDEM>.
- Boundaries and settlement locations: © MIMU, <https://geonode.themimu.info>;
  retain their attribution and applicable data terms. AOI/national boundaries
  are the repository's MIMU adm3 1:250,000 v9.4; town gazetteer is
  `mmr_pplp1_mimu250k`.
