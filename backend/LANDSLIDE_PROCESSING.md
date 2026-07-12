# Landslide SAR Processing (SNAP)

The `/pre-disaster/landslide` page can run a Sentinel-1 backscatter change-detection
workflow over a **pre-event + post-event** product pair to produce a landslide
candidate mask. It replicates the manual "SNAP preprocessing Step by Step"
workflow as one headless ESA SNAP GPT graph.

## Pipeline (per polarisation VV & VH, both products)

Read → Apply-Orbit-File → ThermalNoiseRemoval → Calibration (Sigma0) →
Speckle-Filter (Refined Lee) → Terrain-Correction (Copernicus 30m DEM, ~10 m) →
LinearToFromdB → **Collocate** (post = master `_M`, pre = slave `_S`) →
Band Maths → GeoTIFF.

Band maths (post − pre, threshold from `LANDSLIDE_THRESHOLD_DB`, default −2 dB):

```
diff_VV       = Sigma0_VV_db_M - Sigma0_VV_db_S
diff_VH       = Sigma0_VH_db_M - Sigma0_VH_db_S
land          = Sigma0_VV_db_M > -17 && Sigma0_VV_db_S > -17   # water/shadow gate
mask_VV       = (diff_VV <= -2 && land) ? 1 : 0
mask_VH       = (diff_VH <= -2 && land) ? 1 : 0
mask_combined = ((diff_VV <= -2 || diff_VH <= -2) && land) ? 1 : 0
```

The `land` gate (`LANDSLIDE_WATER_THRESHOLD_DB`, default -17 dB) drops open water
and radar shadow — their low, noisy backscatter otherwise trips the -2 dB change
threshold as false positives (rivers/coast lighting up as "landslide").

**Input pairing matters most.** Pre/post MUST be the same relative orbit and pass
direction (both ascending or both descending, same track). Mixing an ascending
and a descending scene makes Δσ⁰ pure geometric noise everywhere — a dense
salt-and-pepper mask instead of sparse real detections.

Output: one multi-band GeoTIFF at `storage/landslide/<job_id>/result.tif` plus a
`result.kmz` (Google Earth) and a WGS84 map-overlay preview, all from the
Landslide Jobs panel (open the .tif in ArcGIS Pro / QGIS).

## Requirements

1. **Install ESA SNAP** (with the Sentinel-1 Toolbox) on the backend host:
   https://step.esa.int/main/download/snap-download/
2. Point the backend at the `gpt` binary. Default assumes `gpt` is on `PATH`;
   otherwise set in `backend/.env`:

   ```
   SNAP_GPT_PATH=/opt/snap/bin/gpt
   LANDSLIDE_THRESHOLD_DB=-2.0
   ```

3. First run auto-downloads precise orbit files and the Copernicus DEM (needs
   internet). Runs are multi-minute; progress streams into the job row and the
   Activity Log.

If `gpt` is missing the job fails fast with a clear message — no crash.

## API

- `POST /api/landslide/process` `{ preSatelliteId, postSatelliteId, aoi? }` — both
  products must have `product_file_status = completed`. Order is auto-resolved by
  sensing time (earlier = pre). `aoi` is an optional `[minLon, minLat, maxLon, maxLat]`
  crop; omit it to process the full scene (~8 GB, ~20 min). Cropping is strongly
  recommended — it inserts a Subset right after Apply-Orbit-File so the whole chain
  runs only over the AOI (tens of MB, minutes).
- `GET  /api/landslide/jobs` — list with live status/progress.
- `GET  /api/landslide/jobs/{id}/result` — download the mask GeoTIFF.
- `DELETE /api/landslide/jobs/{id}` — remove job + output files.
