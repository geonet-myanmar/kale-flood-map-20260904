#!/usr/bin/env python3
"""Run the unchanged upstream CDSE workflow in a separate build directory.

Requires authenticated Earth Engine access and a permitted Cloud project.
Credentials are read only by cdse_source.py; no secrets are copied into build.
This wrapper is supplied for a future full rerun, not claimed as executed.
"""
import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--earth-engine-project", required=True)
    ap.add_argument("--credentials", type=Path,
                    help="CDSE two-line credentials file; alternatively set CDSE_USER/CDSE_PASSWORD")
    ap.add_argument("--build-dir", type=Path, default=root / "publication" / "workflow_rerun")
    ap.add_argument("--check", action="store_true", help="Run original availability check only")
    args = ap.parse_args()
    missing = [m for m in ["ee", "geemap", "rasterio", "numpy", "scipy", "PIL", "shapely"]
               if importlib.util.find_spec(m) is None]
    if missing:
        raise SystemExit("Missing modules: " + ", ".join(missing) +
                         ". Install publication/requirements-workflow.txt.")
    credentials = args.credentials.resolve() if args.credentials else None
    if credentials and not credentials.is_file():
        raise SystemExit("Specified CDSE credentials file is missing.")
    build = args.build_dir.resolve()
    if build == root or root in build.parents and build == root / "publication":
        raise SystemExit("Use a separate build directory, not the source or publication directory.")
    if credentials and (credentials == build or build in credentials.parents):
        raise SystemExit("Keep the credentials file outside the build directory.")
    import ee
    try:
        ee.Initialize(project=args.earth_engine_project)
    except Exception as exc:
        raise SystemExit("Earth Engine initialization failed. Authenticate with `earthengine authenticate` "
                         "and supply an enabled project. No processing was started. "
                         f"Error type: {type(exc).__name__}") from None
    build.mkdir(parents=True, exist_ok=True)
    for name in ["flood_mapping.py", "flood_mapping_cdse.py", "cdse_source.py",
                 "Kale_Township_Boundary.geojson", "MyanmarTownshipBoundaries.geojson"]:
        destination = build / name
        if destination.exists() and destination.read_bytes() != (root / name).read_bytes():
            raise SystemExit(f"Refusing to overwrite a different existing file: {destination}")
        shutil.copy2(root / name, destination)
    shutil.copytree(root / "data", build / "data", dirs_exist_ok=True)
    os.chdir(build)
    sys.path.insert(0, str(build))
    import cdse_source as CD
    import flood_mapping as F
    if credentials:
        CD.CRED_FILE = str(credentials)
    F.GEE_PROJECT = args.earth_engine_project
    import flood_mapping_cdse as workflow
    sys.argv = ["flood_mapping_cdse.py", "--check" if args.check else "--keep-tif"]
    workflow.main()
    if not args.check:
        print("Original continuous VV: ", build / "cdse_cache")
        print("Original intermediate masks: ", build / "_gee_tmp")
        print("Render the rerun with:")
        print(f"python {root / 'publication' / 'make_map.py'} --repo {build} "
              f"--output {build / 'publication_map'}")


if __name__ == "__main__":
    main()
