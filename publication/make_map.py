#!/usr/bin/env python3
"""Recover the repository's lossless published masks and render a paper figure.

Offline by default. This reconstructs the archived classification, not a fresh
classification from quantized SAR display values. See README.md for provenance.
"""
import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess

os.environ.setdefault("MPLCONFIGDIR", "/tmp/kale-matplotlib")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Polygon as MplPolygon, Rectangle
import numpy as np
from PIL import Image
from pyproj import Geod, Transformer
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.warp import reproject, Resampling
from shapely.geometry import shape, box, LineString
from shapely.ops import transform as shapely_transform, unary_union

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_COMMIT = "8f208f3d1a41823b3cbd11b684a80ad7ca2e92cf"
STEP = 10.0 / 111319.49  # EXACT repository convention, not a 10 m UTM grid.
FLOOD = "#d63838"
WATER = "#277db6"
INK = "#25343d"
TO_UTM = Transformer.from_crs(4326, 32646, always_xy=True)
FROM_UTM = Transformer.from_crs(32646, 4326, always_xy=True)
GEOD = Geod(ellps="WGS84")


def read_dashboard(path):
    text = path.read_text(encoding="utf-8")
    start = re.search(r"const FLOOD\s*=\s*", text).end()
    return json.JSONDecoder().raw_decode(text[start:])[0]


def recover_layer(repo, pieces, grid, width, height):
    """Use PNG palette INDICES, never RGB/alpha or screenshot tracing."""
    result = np.zeros((height, width), np.uint8)
    covered = np.zeros((height, width), bool)
    for ref, bounds in pieces:
        raw = (base64.b64decode(ref.split(",", 1)[1]) if ref.startswith("data:")
               else (repo / ref).read_bytes())
        with Image.open(io.BytesIO(raw)) as img:
            assert img.mode == "P", "Expected original palette-index PNG"
            data = np.asarray(img).copy()
        (south, west), (north, east) = bounds
        row = int(round((grid.f - north) / STEP))
        col = int(round((west - grid.c) / STEP))
        h, w = data.shape
        assert np.allclose([west, north, east, south],
                           [grid.c + col * STEP, grid.f - row * STEP,
                            grid.c + (col + w) * STEP, grid.f - (row + h) * STEP],
                           rtol=0, atol=1e-10)
        assert not covered[row:row+h, col:col+w].any(), "Overlapping chunks"
        result[row:row+h, col:col+w] = data
        covered[row:row+h, col:col+w] = True
    # Missing chunks are all-zero by the original encoder's contract.
    return result


def write_tif(path, data, grid, description, **tags):
    with rasterio.open(path, "w", driver="GTiff", height=data.shape[0],
                       width=data.shape[1], count=1, dtype="uint8", crs=4326,
                       transform=grid, nodata=255, tiled=True,
                       compress="deflate", predictor=2) as dst:
        dst.write(data, 1)
        dst.set_band_description(1, description)
        dst.update_tags(**tags)
    with rasterio.open(path) as src:
        assert np.array_equal(data, src.read(1)), "GeoTIFF round-trip mismatch"


def polygons(geom):
    if geom.geom_type == "Polygon":
        yield geom
    elif hasattr(geom, "geoms"):
        for part in geom.geoms:
            yield from polygons(part)


def boundary(ax, geom, color=INK, lw=.7, fill=None, zorder=4):
    for p in polygons(geom):
        xy = np.asarray(p.exterior.coords)
        if fill:
            ax.add_patch(MplPolygon(xy, facecolor=fill, edgecolor="none", zorder=zorder))
        ax.plot(xy[:, 0], xy[:, 1], color=color, lw=lw, zorder=zorder)
        for ring in p.interiors:
            xy = np.asarray(ring.coords)
            ax.plot(xy[:, 0], xy[:, 1], color=color, lw=lw, zorder=zorder)


def graticule(ax, lons, lats, small=False):
    xmin, xmax = ax.get_xlim(); ymin, ymax = ax.get_ylim()
    top = LineString([(xmin, ymax), (xmax, ymax)])
    left = LineString([(xmin, ymin), (xmin, ymax)])
    xt, xl, yt, yl = [], [], [], []
    for is_lon, values in [(True, lons), (False, lats)]:
        for value in values:
            a = np.linspace(21, 25, 200) if is_lon else np.linspace(92, 96, 200)
            lon, lat = (np.full_like(a, value), a) if is_lon else (a, np.full_like(a, value))
            x, y = TO_UTM.transform(lon, lat)
            ax.plot(x, y, color="#687780", alpha=.24, lw=.35, zorder=6)
            point = LineString(np.column_stack([x, y])).intersection(top if is_lon else left)
            if point.geom_type == "Point":
                degree = int(value); minutes = int(round((value-degree)*60))
                label = f"{degree}°{minutes:02d}′{'E' if is_lon else 'N'}"
                if is_lon:
                    xt.append(point.x); xl.append(label)
                else:
                    yt.append(point.y); yl.append(label)
    ax.set_xticks(xt, xl); ax.set_yticks(yt, yl)
    ax.xaxis.tick_top()
    ax.tick_params(length=3, width=.5, labelsize=6 if small else 7, pad=4)
    ax.set_xlim(xmin, xmax); ax.set_ylim(ymin, ymax)


def scalebar(ax, length_km, pos=(.08, .055)):
    xmin, xmax = ax.get_xlim(); ymin, ymax = ax.get_ylim()
    x = xmin + pos[0]*(xmax-xmin); y = ymin + pos[1]*(ymax-ymin)
    lon, lat = FROM_UTM.transform(x, y)
    end_lon, end_lat, _ = GEOD.fwd(lon, lat, 90, length_km*1000)
    xx, yy = TO_UTM.transform(end_lon, end_lat)
    length = np.hypot(xx-x, yy-y)
    h = (ymax-ymin)*.006
    for i in range(2):
        ax.add_patch(Rectangle((x+i*length/2,y),length/2,h,
                              facecolor=INK if i==0 else "white",edgecolor=INK,lw=.5,zorder=12))
    for frac, label in [(0,"0"),(.5,f"{length_km/2:g}"),(1,f"{length_km:g} km")]:
        ax.text(x+frac*length,y+h*2,label,ha="center",va="bottom",fontsize=6.5,zorder=12,
                path_effects=[pe.withStroke(linewidth=2,foreground="white")])


def north_arrow(ax):
    x0,x1=ax.get_xlim(); y0,y1=ax.get_ylim()
    x=x0+.90*(x1-x0); y=y0+.88*(y1-y0)
    lon,lat=FROM_UTM.transform(x,y)
    lon2,lat2,_=GEOD.fwd(lon,lat,0,(y1-y0)*.055)
    xx,yy=TO_UTM.transform(lon2,lat2)
    ax.annotate("",xy=(xx,yy),xytext=(x,y),arrowprops=dict(facecolor=INK,width=1.8,
                headwidth=6,headlength=8),zorder=12)
    ax.text(xx,yy+(y1-y0)*.013,"N",ha="center",fontsize=8,fontweight="bold",zorder=12)


def raster_on_panel(ax, arr, grid, extent, resolution, cmap, alpha=1, continuous=False):
    xmin,xmax,ymin,ymax=extent
    width=int(np.ceil((xmax-xmin)/resolution)); height=int(np.ceil((ymax-ymin)/resolution))
    dst=np.zeros((height,width),np.uint8)
    reproject(arr,dst,src_transform=grid,src_crs=4326,
              dst_transform=from_origin(xmin,ymax,resolution,resolution),dst_crs=32646,
              src_nodata=0,dst_nodata=0,
              resampling=Resampling.bilinear if continuous else Resampling.nearest)
    ext=(xmin,xmin+width*resolution,ymax-height*resolution,ymax)
    ax.imshow(np.ma.masked_equal(dst,0),extent=ext,origin="upper",cmap=cmap,
              vmin=0,vmax=255 if continuous else 1,alpha=alpha,
              interpolation="nearest",zorder=2 if continuous else 3)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo",type=Path,default=ROOT)
    ap.add_argument("--output",type=Path,default=ROOT/"publication"/"output")
    ap.add_argument("--dpi",type=int,default=600)
    args=ap.parse_args(); repo=args.repo.resolve(); out=args.output.resolve()
    out.mkdir(parents=True,exist_ok=True)
    d=read_dashboard(repo/"index.html")
    assert (d["meta"]["pre"], d["meta"]["post"], d["meta"]["track"],
            d["meta"]["thresh"], d["meta"]["speckle"], d["meta"]["slope"]) == (
                "2026-08-22", "2026-09-03", 4, -3.0, 30, 5.0), "Unexpected source methodology"
    source=json.loads((repo/"Kale_Township_Boundary.geojson").read_text())
    aoi=unary_union([shape(f["geometry"]) for f in source["features"]])
    west,south,east,north=aoi.bounds
    width=round((east-west)/STEP); height=round((north-south)/STEP)
    grid=from_origin(west,north,STEP,STEP)
    inside=rasterize([(aoi,1)],out_shape=(height,width),transform=grid,dtype="uint8").astype(bool)
    arrays={key:recover_layer(repo,d["layers"][key],grid,width,height)
            for key in ["flood","water","post_sar"]}
    rows=north-(np.arange(height)+.5)*STEP
    row_area=100*np.cos(np.deg2rad(rows))  # original pixel_area_m2, algebraically identical
    check={}
    for key in ["flood","water"]:
        arr=arrays[key]
        assert set(np.unique(arr)) <= {0,1}
        assert not arr[~inside].any(), f"{key} outside AOI"
        area=float(np.dot(arr.sum(axis=1),row_area)/1e6)
        expected=d["stats"][key+"_km2"]
        assert abs(area-expected)<1e-9, (area,expected)
        check[key]={"pixel_count":int(arr.sum()),"area_km2":area,
                    "repository_area_km2":expected,"absolute_difference_km2":abs(area-expected)}
        data=arr.copy(); data[~inside]=255
        write_tif(out/f"{key}_native.tif",data,grid,
                  "New inundation" if key=="flood" else "JRC reference-water exclusion",
                  SOURCE="Lossless palette-index recovery from repository index.html",
                  PRE_DATE=d["meta"]["pre"],POST_DATE=d["meta"]["post"],
                  VALUES="0=no positive class (includes excluded/unassessed);1=positive class;255=outside AOI",
                  AREA_METHOD="Original repository latitude-weighted spherical approximation",
                  AREA_KM2=f"{area:.12f}")
    assert not (arrays["flood"] & arrays["water"]).any()
    print(json.dumps(check,indent=2),flush=True)
    (out/"study_area.geojson").write_text(json.dumps(source),encoding="utf-8")

    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":8,
                         "text.color":INK,"axes.edgecolor":"#65717a",
                         "axes.linewidth":.65,"xtick.color":INK,"ytick.color":INK,
                         "pdf.fonttype":42,"ps.fonttype":42})
    fig=plt.figure(figsize=(8.27,11.69),facecolor="white")
    fig.text(.08,.957,"Flood inundation in Kale Township",fontsize=18,fontweight="bold")
    fig.text(.08,.931,"Sagaing Region, Myanmar  |  22 August–3 September 2026",fontsize=10,color="#52616b")
    fig.add_artist(Line2D([.08,.94],[.912,.912],transform=fig.transFigure,color=INK,lw=.8))

    national=json.loads((repo/"MyanmarTownshipBoundaries.geojson").read_text())
    nearby=[]; regions={}
    for f in national["features"]:
        g=shape(f["geometry"])
        regions.setdefault(f["properties"]["ST"],[]).append(g)
        if g.intersects(box(93.7,22.45,94.5,23.8)):
            nearby.append((f["properties"],shapely_transform(TO_UTM.transform,g)))
    aoi_utm=shapely_transform(TO_UTM.transform,aoi)
    minx,miny,maxx,maxy=aoi_utm.bounds
    extent=(minx-9000,maxx+9000,miny-5000,maxy+5000)
    mainax=fig.add_axes([.085,.185,.475,.705])
    detail=fig.add_axes([.645,.393,.292,.275])
    # The detail window is a fixed geographic region around Kale and the valley.
    dgeom=shapely_transform(TO_UTM.transform,box(93.99,23.08,94.20,23.29))
    dx0,dy0,dx1,dy1=dgeom.bounds
    detail_extent=(dx0,dx1,dy0,dy1)
    from matplotlib.colors import ListedColormap
    for ax,ex,res in [(mainax,extent,25),(detail,detail_extent,10)]:
        ax.set_facecolor("#f6f5f1")
        for props,g in nearby:
            boundary(ax,g,color="#bdc1c2",lw=.5,zorder=1)
        raster_on_panel(ax,arrays["post_sar"],grid,ex,res,"gray",alpha=.23,continuous=True)
        raster_on_panel(ax,arrays["water"],grid,ex,res,ListedColormap([WATER,WATER]))
        raster_on_panel(ax,arrays["flood"],grid,ex,res,ListedColormap([FLOOD,FLOOD]))
        boundary(ax,aoi_utm,lw=.9)
        ax.set_xlim(ex[0],ex[1]); ax.set_ylim(ex[2],ex[3]); ax.set_aspect("equal")
        tx,ty=TO_UTM.transform(d["towns"][0][0],d["towns"][0][1])
        ax.scatter([tx],[ty],marker="s",s=17 if ax==mainax else 23,color=INK,
                   edgecolor="white",linewidth=.65,zorder=10)
        ax.annotate("Kale",(tx,ty),xytext=(-8,5),textcoords="offset points",
                    ha="right",fontsize=8,fontweight="bold",zorder=11,
                    path_effects=[pe.withStroke(linewidth=2.5,foreground="white")])
    mainax.text(.025,.982,"a   Township overview",transform=mainax.transAxes,
                va="top",fontsize=9,fontweight="bold",zorder=15,
                bbox=dict(facecolor="#f6f5f1",edgecolor="none",pad=3))
    detail.set_title("c   Central valley detail",loc="left",fontsize=9,fontweight="bold",pad=24)
    graticule(mainax,[94,94.2],np.arange(22.6,23.7,.2))
    graticule(detail,[94.05,94.15],[23.1,23.2],small=True)
    scalebar(mainax,10); scalebar(detail,5,pos=(.57,.06)); north_arrow(mainax)
    mainax.add_patch(Rectangle((dx0,dy0),dx1-dx0,dy1-dy0,facecolor="none",
                              edgecolor=INK,lw=.85,linestyle=(0,(4,3)),zorder=8))
    mainax.text(dx1+800,dy1,"c",fontsize=10,fontweight="bold",zorder=10)
    for name,lon,lat in [("Tedim",93.91,23.42),("Falam",93.92,23.02),
                         ("Kalewa",94.26,23.37),("Mingin",94.24,22.80)]:
        x,y=TO_UTM.transform(lon,lat)
        mainax.text(x,y,name,fontsize=7,color="#6e7478",rotation=90 if name in ["Falam","Tedim"] else 0,
                    ha="center",path_effects=[pe.withStroke(linewidth=2,foreground="#f6f5f1")])

    loc=fig.add_axes([.65,.711,.28,.173])
    loc.set_facecolor("#f1f5f6")
    for name,gs in regions.items():
        g=unary_union(gs)
        boundary(loc,g,color="#adb6bc",lw=.3,
                 fill="#dfd9c7" if name=="Sagaing" else "#e9e7e0",zorder=2)
    boundary(loc,aoi,color=FLOOD,lw=.75,fill=FLOOD,zorder=4)
    loc.scatter([94.11],[23.12],s=36,facecolor="none",edgecolor=FLOOD,lw=.9,zorder=5)
    loc.annotate("Kale",(94.11,23.12),xytext=(91.7,21.2),fontsize=7,color=FLOOD,
                 arrowprops=dict(arrowstyle="-",color=FLOOD,lw=.6))
    loc.text(96.9,18,"MYANMAR",fontsize=6.5,ha="center",color="#6f7679",rotation=65)
    loc.text(95.9,25.0,"Sagaing",fontsize=6.2,ha="center",color="#6f6754")
    loc.set_xlim(91,102);loc.set_ylim(9.5,28.8);loc.set_aspect(1/np.cos(np.deg2rad(20)))
    loc.set_xticks([]);loc.set_yticks([])
    loc.set_title("b   Location in Myanmar",loc="left",fontsize=9,fontweight="bold",pad=8)

    leg=fig.add_axes([.635,.174,.31,.19]);leg.axis("off")
    handles=[Patch(facecolor=FLOOD,label="New inundation"),
             Patch(facecolor=WATER,label="Reference water¹"),
             Line2D([],[],color=INK,lw=.9,label="Kale Township boundary"),
             Line2D([],[],color="#adb3b7",lw=.6,label="Other township boundaries"),
             Line2D([],[],marker="s",color="none",markerfacecolor=INK,markersize=4,label="Town location (MIMU)")]
    leg.legend(handles=handles,loc="upper left",frameon=False,fontsize=7.4,
               handlelength=1.6,labelspacing=.75,borderaxespad=0)
    leg.text(0,.27,f"{check['flood']['area_km2']:.1f} km²",fontsize=20,fontweight="bold",color=FLOOD)
    leg.text(0,.15,f"New inundation · {d['stats']['flood_pct']:.2f}% of township",fontsize=7.8)
    leg.text(0,.015,"¹ JRC seasonality ≥4 months; excluded\n   from the new-inundation class.",fontsize=6.8,linespacing=1.5,color="#52616b")

    fig.add_artist(Line2D([.08,.94],[.151,.151],transform=fig.transFigure,color="#b9c0c4",lw=.6))
    foot=("Sentinel-1D IW GRDH · VV · descending relative orbit 4 · two frames per date (UTC)\n"
          "Method: terrain-corrected γ⁰; 30 m nominal circular mean; ΔVV < −3 dB; slope <5°; JRC water excluded.\n"
          "Map: WGS 84 / UTM zone 46N; graticule: WGS 84. Background: post-event SAR (display stretch).\n"
          "Contains modified Copernicus Sentinel data (2026). Analysis: GeoNet Myanmar; boundaries/town: MIMU.\n"
          "Reference water source: EC JRC/Google; terrain exclusion: WWF HydroSHEDS.\n"
          "Static reproduction of the published classification; new water since 22 August, not total standing water.")
    fig.text(.08,.131,foot,fontsize=6.8,va="top",linespacing=1.7,color="#52616b")
    jpeg=out/f"kale_flood_publication_{args.dpi}dpi.jpg"
    fig.savefig(jpeg,dpi=args.dpi,pil_kwargs={"quality":98,"subsampling":0},facecolor="white")
    fig.savefig(out/"kale_flood_publication.pdf",dpi=450,facecolor="white")
    fig.savefig(out/"preview.png",dpi=150,facecolor="white")
    plt.close(fig)
    try:
        commit=subprocess.check_output(["git","-C",str(repo),"rev-parse","HEAD"],text=True).strip()
    except subprocess.CalledProcessError:
        commit="unavailable"
    files=["index.html","flood_stats.json","flood_mapping_cdse.py","flood_mapping.py",
           "cdse_source.py","Kale_Township_Boundary.geojson","MyanmarTownshipBoundaries.geojson"]
    files += [str(p.relative_to(repo)) for p in sorted((repo/"assets").glob("*.png"))]
    manifest={"source_commit":UPSTREAM_COMMIT,"build_commit":commit,
              "reproduction_mode":"lossless recovery of published classification",
              "fresh_sentinel1_classification_run":False,"method_changed":False,
              "source_grid":{"crs":"EPSG:4326","width":width,"height":height,
                             "transform":list(grid)[:6],"pixel_spacing_degrees":STEP},
              "validation":check,"source_metadata":d["meta"],
              "sha256_inputs":{p:hashlib.sha256((repo/p).read_bytes()).hexdigest() for p in files},
              "map_projection":"EPSG:32646", "display_resampling":{"categorical":"nearest","SAR":"bilinear"},
              "software":{m.__name__:m.__version__ for m in [matplotlib,np,rasterio]},
              "limitations":["No original continuous dB, terrain, or validity masks archived in repository.",
                             "Zero denotes no positive class and does not guarantee assessed dry land.",
                             "Published 8-bit SAR is for display only; never used to rethreshold."]}
    with Image.open(jpeg) as im:
        manifest["jpeg"]={"pixels":list(im.size),"dpi":list(im.info["dpi"]),"mode":im.mode}
    manifest["sha256_outputs"]={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in sorted(out.glob("*")) if p.suffix in [".tif",".jpg",".pdf",".geojson"]}
    (out/"validation.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    print(f"Wrote {jpeg}",flush=True)


if __name__=="__main__":
    main()
