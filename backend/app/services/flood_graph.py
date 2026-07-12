"""Builds ESA SNAP GPT graph XML for the flood-extent-detection workflow (the
"SNAP Step by Step for Flood" reference document), one single-operator graph
per pipeline stage - mirrors snap_graph.py's per-operator builder pattern
from the Landslide pipeline.

Per operator, in pipeline order (matches the reference PDF's own graph
diagram exactly - note Subset sits AFTER Calibration here, not first like
Landslide's AOI crop, since this pipeline follows the reference document's
order faithfully rather than optimizing for speed):

    Read -> ThermalNoiseRemoval -> Apply-Orbit-File -> Remove-GRD-Border-Noise
         -> Calibration(Sigma0) -> Subset(AOI) -> Speckle-Filter(Lee Sigma)
         -> Terrain-Correction -> BandMaths (binary flood mask)

VV polarisation only, per every operator's parameters in the reference PDF.
"""
from __future__ import annotations

from xml.sax.saxutils import escape

from app.services.snap_graph import _band_maths_node, _bbox_to_wkt, _read_node, _write_node


def build_tnr_graph(source_file: str, output_dim: str) -> str:
    """Step 1/8: Read -> ThermalNoiseRemoval (VV) -> Write. `source_file` is
    the original Sentinel-1 .SAFE.zip."""
    return f"""<graph id="FloodTnr">
  <version>1.0</version>{_read_node("read", source_file)}
  <node id="tnr">
    <operator>ThermalNoiseRemoval</operator>
    <sources><sourceProduct refid="read"/></sources>
    <parameters class="com.bc.ceres.binding.dom.XppDomElement">
      <selectedPolarisations>VV</selectedPolarisations>
      <removeThermalNoise>true</removeThermalNoise>
      <outputNoise>false</outputNoise>
    </parameters>
  </node>{_write_node("tnr", output_dim)}
</graph>"""


def build_orbit_graph(source_dim: str, output_dim: str) -> str:
    """Step 2/8: Read -> Apply-Orbit-File -> Write."""
    return f"""<graph id="FloodOrbit">
  <version>1.0</version>{_read_node("read", source_dim)}
  <node id="orbit">
    <operator>Apply-Orbit-File</operator>
    <sources><sourceProduct refid="read"/></sources>
    <parameters class="com.bc.ceres.binding.dom.XppDomElement">
      <orbitType>Sentinel Precise (Auto Download)</orbitType>
      <polyDegree>3</polyDegree>
      <continueOnFail>true</continueOnFail>
    </parameters>
  </node>{_write_node("orbit", output_dim)}
</graph>"""


def build_border_noise_graph(source_dim: str, output_dim: str) -> str:
    """Step 3/8: Read -> Remove-GRD-Border-Noise (VV, borderLimit=500,
    trimThreshold=0.5) -> Write - the PDF's "Border margin limit"/"Threshold"
    fields."""
    return f"""<graph id="FloodBorderNoise">
  <version>1.0</version>{_read_node("read", source_dim)}
  <node id="border">
    <operator>Remove-GRD-Border-Noise</operator>
    <sources><sourceProduct refid="read"/></sources>
    <parameters class="com.bc.ceres.binding.dom.XppDomElement">
      <selectedPolarisations>VV</selectedPolarisations>
      <borderLimit>500</borderLimit>
      <trimThreshold>0.5</trimThreshold>
    </parameters>
  </node>{_write_node("border", output_dim)}
</graph>"""


def build_calibration_graph(source_dim: str, output_dim: str) -> str:
    """Step 4/8: Read -> Calibration (VV, Sigma0 only) -> Write."""
    return f"""<graph id="FloodCalibration">
  <version>1.0</version>{_read_node("read", source_dim)}
  <node id="cal">
    <operator>Calibration</operator>
    <sources><sourceProduct refid="read"/></sources>
    <parameters class="com.bc.ceres.binding.dom.XppDomElement">
      <selectedPolarisations>VV</selectedPolarisations>
      <outputSigmaBand>true</outputSigmaBand>
      <outputGammaBand>false</outputGammaBand>
      <outputBetaBand>false</outputBetaBand>
      <outputImageInComplex>false</outputImageInComplex>
      <outputImageScaleInDb>false</outputImageScaleInDb>
    </parameters>
  </node>{_write_node("cal", output_dim)}
</graph>"""


def build_subset_graph(source_dim: str, output_dim: str, aoi_bbox: list[float] | None = None) -> str:
    """Step 5/8: Read -> Subset (AOI crop, when given) -> Write. Unlike
    Landslide's early crop, this sits mid-pipeline (after Calibration),
    matching the reference PDF's own operator order exactly. When
    `aoi_bbox` is None this stage is a passthrough (Read -> Write straight
    through, no Subset node) so the pipeline keeps a uniform per-stage
    shape regardless of whether an AOI was drawn."""
    if aoi_bbox is None:
        return f"""<graph id="FloodSubset">
  <version>1.0</version>{_read_node("read", source_dim)}{_write_node("read", output_dim)}
</graph>"""
    aoi_wkt = _bbox_to_wkt(aoi_bbox)
    return f"""<graph id="FloodSubset">
  <version>1.0</version>{_read_node("read", source_dim)}
  <node id="subset">
    <operator>Subset</operator>
    <sources><sourceProduct refid="read"/></sources>
    <parameters class="com.bc.ceres.binding.dom.XppDomElement">
      <geoRegion>{escape(aoi_wkt)}</geoRegion>
      <copyMetadata>true</copyMetadata>
    </parameters>
  </node>{_write_node("subset", output_dim)}
</graph>"""


def build_speckle_graph(source_dim: str, output_dim: str) -> str:
    """Step 6/8: Read -> Speckle-Filter (Lee Sigma, 1 look, 7x7 window,
    sigma 0.9, 3x3 target window - the PDF's exact parameters) -> Write."""
    return f"""<graph id="FloodSpeckle">
  <version>1.0</version>{_read_node("read", source_dim)}
  <node id="speckle">
    <operator>Speckle-Filter</operator>
    <sources><sourceProduct refid="read"/></sources>
    <parameters class="com.bc.ceres.binding.dom.XppDomElement">
      <sourceBands>Sigma0_VV</sourceBands>
      <filter>Lee Sigma</filter>
      <numLooksStr>1</numLooksStr>
      <windowSize>7x7</windowSize>
      <targetWindowSizeStr>3x3</targetWindowSizeStr>
      <sigmaStr>0.9</sigmaStr>
    </parameters>
  </node>{_write_node("speckle", output_dim)}
</graph>"""


def build_terrain_correction_graph(source_dim: str, output_dim: str) -> str:
    """Step 7/8: Read -> Range-Doppler Terrain-Correction (Copernicus 30m DEM,
    nearest-neighbor resampling, WGS84(DD) plain lat/lon, 10m pixel spacing)
    -> Write.

    The reference PDF specifies "SRTM 3Sec (Auto Download)", but that DEM
    name is not registered in this SNAP install ("The DEM 'SRTM 3Sec (Auto
    Download)' is not supported", confirmed via a live run) - swapped to
    Copernicus 30m Global DEM, the same substitution already proven working
    in Landslide's own Terrain-Correction (snap_graph.py)."""
    return f"""<graph id="FloodTerrainCorrection">
  <version>1.0</version>{_read_node("read", source_dim)}
  <node id="tc">
    <operator>Terrain-Correction</operator>
    <sources><sourceProduct refid="read"/></sources>
    <parameters class="com.bc.ceres.binding.dom.XppDomElement">
      <sourceBands>Sigma0_VV</sourceBands>
      <demName>Copernicus 30m Global DEM</demName>
      <demResamplingMethod>NEAREST_NEIGHBOUR</demResamplingMethod>
      <imgResamplingMethod>NEAREST_NEIGHBOUR</imgResamplingMethod>
      <pixelSpacingInMeter>10.0</pixelSpacingInMeter>
      <mapProjection>WGS84(DD)</mapProjection>
      <nodataValueAtSea>true</nodataValueAtSea>
    </parameters>
  </node>{_write_node("tc", output_dim)}
</graph>"""


def build_flood_mask_graph(source_dim: str, output_file: str, threshold_sigma0: float) -> str:
    """Step 8/8: Read -> BandMaths (Sigma0_VV < threshold ? 1 : NaN, a real
    non-virtual band named `water_and_flood_area`, matching the PDF's own
    expression and band name) -> Write (GeoTIFF-BigTIFF, not BEAM-DIMAP -
    this is the job's final downloadable output).

    Unlike Landslide's binary 0/1 mask, background pixels here are genuine
    NaN/no-data (matching the PDF's own `else NaN`), not a literal 0 -
    flood_preview.py's color table relies on this distinction."""
    band_maths = _band_maths_node("water_and_flood_area", f"Sigma0_VV < {threshold_sigma0} ? 1 : NaN")
    return f"""<graph id="FloodMask">
  <version>1.0</version>{_read_node("read", source_dim)}
  <node id="mask">
    <operator>BandMaths</operator>
    <sources><sourceProduct refid="read"/></sources>
    <parameters class="com.bc.ceres.binding.dom.XppDomElement">
      <targetBands>{band_maths}
      </targetBands>
    </parameters>
  </node>
  <node id="write">
    <operator>Write</operator>
    <sources><sourceProduct refid="mask"/></sources>
    <parameters class="com.bc.ceres.binding.dom.XppDomElement">
      <file>{escape(output_file)}</file>
      <formatName>GeoTIFF-BigTIFF</formatName>
    </parameters>
  </node>
</graph>"""
