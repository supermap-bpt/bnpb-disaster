"""Builds an ESA SNAP GPT graph XML that replicates the manual SNAP landslide
workflow (the "SNAP preprocessing Step by Step" document) as one headless run.

Per polarisation (VV, VH) both the pre-event and post-event Sentinel-1 GRD
products go through the identical single-product chain:

    Read -> Apply-Orbit-File -> ThermalNoiseRemoval -> Calibration(Sigma0)
         -> Speckle-Filter(Refined Lee) -> Terrain-Correction -> LinearToFromdB

The two chains are then collocated onto one identical pixel grid (post = master,
so its bands get the ``_M`` suffix and pre = slave gets ``_S`` - matching the
reference doc). Band Maths then computes the backscatter difference
(post - pre) and thresholds it (<= threshold dB => candidate landslide pixel):

    diff_VV = Sigma0_VV_M - Sigma0_VV_S
    mask_VV = diff_VV <= threshold ? 1 : 0        (same for VH)
    mask_combined = (mask_VV == 1 || mask_VH == 1) ? 1 : 0

Finally everything is written to a single multi-band GeoTIFF.
"""
from __future__ import annotations

from xml.sax.saxutils import escape


def _band_maths_node(name: str, expression: str) -> str:
    return f"""
    <targetBand>
      <name>{name}</name>
      <type>float32</type>
      <expression>{escape(expression)}</expression>
      <noDataValue>NaN</noDataValue>
    </targetBand>"""


def _bbox_to_wkt(bbox: list[float]) -> str:
    """[min_lon, min_lat, max_lon, max_lat] -> a closed WKT POLYGON (lon lat order)."""
    min_lon, min_lat, max_lon, max_lat = bbox
    ring = (
        f"{min_lon} {min_lat}, {max_lon} {min_lat}, {max_lon} {max_lat}, "
        f"{min_lon} {max_lat}, {min_lon} {min_lat}"
    )
    return f"POLYGON (({ring}))"


def _read_node(node_id: str, source_file: str) -> str:
    return f"""
  <node id="{node_id}">
    <operator>Read</operator>
    <sources/>
    <parameters class="com.bc.ceres.binding.dom.XppDomElement">
      <file>{escape(source_file)}</file>
    </parameters>
  </node>"""


def _write_node(source_refid: str, output_dim: str) -> str:
    return f"""
  <node id="write">
    <operator>Write</operator>
    <sources><sourceProduct refid="{source_refid}"/></sources>
    <parameters class="com.bc.ceres.binding.dom.XppDomElement">
      <file>{escape(output_dim)}</file>
      <formatName>BEAM-DIMAP</formatName>
    </parameters>
  </node>"""


def build_orbit_graph(source_file: str, output_dim: str, aoi_bbox: list[float] | None = None) -> str:
    """Step 1/6: Read [+ Subset crop to AOI] -> Apply-Orbit-File -> Write.
    `source_file` is the original Sentinel-1 .SAFE.zip. The AOI crop (when
    given) happens here, first - so every later, more expensive operator only
    ever processes the cropped area, same as the old fused-graph ordering."""
    aoi_wkt = _bbox_to_wkt(aoi_bbox) if aoi_bbox else None
    orbit_source = "subset" if aoi_wkt else "read"
    subset_node = ""
    if aoi_wkt:
        subset_node = f"""
  <node id="subset">
    <operator>Subset</operator>
    <sources><sourceProduct refid="read"/></sources>
    <parameters class="com.bc.ceres.binding.dom.XppDomElement">
      <geoRegion>{escape(aoi_wkt)}</geoRegion>
      <copyMetadata>true</copyMetadata>
    </parameters>
  </node>"""
    return f"""<graph id="LandslideOrbit">
  <version>1.0</version>{_read_node("read", source_file)}{subset_node}
  <node id="orbit">
    <operator>Apply-Orbit-File</operator>
    <sources><sourceProduct refid="{orbit_source}"/></sources>
    <parameters class="com.bc.ceres.binding.dom.XppDomElement">
      <orbitType>Sentinel Precise (Auto Download)</orbitType>
      <polyDegree>3</polyDegree>
      <continueOnFail>true</continueOnFail>
    </parameters>
  </node>{_write_node("orbit", output_dim)}
</graph>"""


def build_tnr_graph(source_dim: str, output_dim: str) -> str:
    """Step 2/6: Read -> ThermalNoiseRemoval -> Write."""
    return f"""<graph id="LandslideTnr">
  <version>1.0</version>{_read_node("read", source_dim)}
  <node id="tnr">
    <operator>ThermalNoiseRemoval</operator>
    <sources><sourceProduct refid="read"/></sources>
    <parameters class="com.bc.ceres.binding.dom.XppDomElement">
      <selectedPolarisations>VH,VV</selectedPolarisations>
      <removeThermalNoise>true</removeThermalNoise>
      <outputNoise>false</outputNoise>
    </parameters>
  </node>{_write_node("tnr", output_dim)}
</graph>"""


def build_calibration_graph(source_dim: str, output_dim: str) -> str:
    """Step 3/6: Read -> Calibration (Sigma0 only) -> Write."""
    return f"""<graph id="LandslideCalibration">
  <version>1.0</version>{_read_node("read", source_dim)}
  <node id="cal">
    <operator>Calibration</operator>
    <sources><sourceProduct refid="read"/></sources>
    <parameters class="com.bc.ceres.binding.dom.XppDomElement">
      <selectedPolarisations>VH,VV</selectedPolarisations>
      <outputSigmaBand>true</outputSigmaBand>
      <outputGammaBand>false</outputGammaBand>
      <outputBetaBand>false</outputBetaBand>
      <outputImageInComplex>false</outputImageInComplex>
      <outputImageScaleInDb>false</outputImageScaleInDb>
    </parameters>
  </node>{_write_node("cal", output_dim)}
</graph>"""


def build_speckle_graph(source_dim: str, output_dim: str) -> str:
    """Step 4/6: Read -> Speckle-Filter (Refined Lee) -> Write."""
    return f"""<graph id="LandslideSpeckle">
  <version>1.0</version>{_read_node("read", source_dim)}
  <node id="speckle">
    <operator>Speckle-Filter</operator>
    <sources><sourceProduct refid="read"/></sources>
    <parameters class="com.bc.ceres.binding.dom.XppDomElement">
      <sourceBands>Sigma0_VH,Sigma0_VV</sourceBands>
      <filter>Refined Lee</filter>
    </parameters>
  </node>{_write_node("speckle", output_dim)}
</graph>"""


def build_terrain_correction_graph(source_dim: str, output_dim: str) -> str:
    """Step 5/6: Read -> Range-Doppler Terrain-Correction (Copernicus 30m DEM,
    auto-UTM) -> Write."""
    return f"""<graph id="LandslideTerrainCorrection">
  <version>1.0</version>{_read_node("read", source_dim)}
  <node id="tc">
    <operator>Terrain-Correction</operator>
    <sources><sourceProduct refid="read"/></sources>
    <parameters class="com.bc.ceres.binding.dom.XppDomElement">
      <sourceBands>Sigma0_VH,Sigma0_VV</sourceBands>
      <demName>Copernicus 30m Global DEM</demName>
      <demResamplingMethod>BILINEAR_INTERPOLATION</demResamplingMethod>
      <imgResamplingMethod>BILINEAR_INTERPOLATION</imgResamplingMethod>
      <pixelSpacingInMeter>10.0</pixelSpacingInMeter>
      <mapProjection>AUTO:42001</mapProjection>
      <nodataValueAtSea>false</nodataValueAtSea>
    </parameters>
  </node>{_write_node("tc", output_dim)}
</graph>"""


def build_db_graph(source_dim: str, output_dim: str) -> str:
    """Step 6/6: Read -> LinearToFromdB -> Write. Output bands
    (Sigma0_VH_db/Sigma0_VV_db) are what build_change_detection_graph's
    Collocate step consumes."""
    return f"""<graph id="LandslideDb">
  <version>1.0</version>{_read_node("read", source_dim)}
  <node id="db">
    <operator>LinearToFromdB</operator>
    <sources><sourceProduct refid="read"/></sources>
    <parameters class="com.bc.ceres.binding.dom.XppDomElement">
      <sourceBands>Sigma0_VH,Sigma0_VV</sourceBands>
    </parameters>
  </node>{_write_node("db", output_dim)}
</graph>"""


def build_preprocess_graph(
    source_file: str,
    output_dim: str,
    aoi_bbox: list[float] | None = None,
) -> str:
    """DEPRECATED: Fused single-product preprocessing graph (will be split into 6 individual
    graphs by Task 2). For backward compatibility, composes all 6 steps into one graph.

    Stage 1/2 graph: the single-product chain (Read → [Subset] → Orbit → TNR →
    Calibration → Speckle → Terrain-Correction → dB) written to a BEAM-DIMAP file.

    ``source_file`` is a Sentinel-1 GRD ``.SAFE.zip``; ``output_dim`` is the target
    ``.dim``. ``aoi_bbox`` optionally crops to [min_lon, min_lat, max_lon, max_lat].
    """
    aoi_wkt = _bbox_to_wkt(aoi_bbox) if aoi_bbox else None
    orbit_source = "subset" if aoi_wkt else "read"
    subset_node = ""
    if aoi_wkt:
        subset_node = f"""
  <node id="subset">
    <operator>Subset</operator>
    <sources><sourceProduct refid="read"/></sources>
    <parameters class="com.bc.ceres.binding.dom.XppDomElement">
      <geoRegion>{escape(aoi_wkt)}</geoRegion>
      <copyMetadata>true</copyMetadata>
    </parameters>
  </node>"""
    return f"""<graph id="LandslidePreprocess">
  <version>1.0</version>{_read_node("read", source_file)}{subset_node}
  <node id="orbit">
    <operator>Apply-Orbit-File</operator>
    <sources><sourceProduct refid="{orbit_source}"/></sources>
    <parameters class="com.bc.ceres.binding.dom.XppDomElement">
      <orbitType>Sentinel Precise (Auto Download)</orbitType>
      <polyDegree>3</polyDegree>
      <continueOnFail>true</continueOnFail>
    </parameters>
  </node>
  <node id="tnr">
    <operator>ThermalNoiseRemoval</operator>
    <sources><sourceProduct refid="orbit"/></sources>
    <parameters class="com.bc.ceres.binding.dom.XppDomElement">
      <selectedPolarisations>VH,VV</selectedPolarisations>
      <removeThermalNoise>true</removeThermalNoise>
      <outputNoise>false</outputNoise>
    </parameters>
  </node>
  <node id="cal">
    <operator>Calibration</operator>
    <sources><sourceProduct refid="tnr"/></sources>
    <parameters class="com.bc.ceres.binding.dom.XppDomElement">
      <selectedPolarisations>VH,VV</selectedPolarisations>
      <outputSigmaBand>true</outputSigmaBand>
      <outputGammaBand>false</outputGammaBand>
      <outputBetaBand>false</outputBetaBand>
      <outputImageInComplex>false</outputImageInComplex>
      <outputImageScaleInDb>false</outputImageScaleInDb>
    </parameters>
  </node>
  <node id="speckle">
    <operator>Speckle-Filter</operator>
    <sources><sourceProduct refid="cal"/></sources>
    <parameters class="com.bc.ceres.binding.dom.XppDomElement">
      <sourceBands>Sigma0_VH,Sigma0_VV</sourceBands>
      <filter>Refined Lee</filter>
    </parameters>
  </node>
  <node id="tc">
    <operator>Terrain-Correction</operator>
    <sources><sourceProduct refid="speckle"/></sources>
    <parameters class="com.bc.ceres.binding.dom.XppDomElement">
      <sourceBands>Sigma0_VH,Sigma0_VV</sourceBands>
      <demName>Copernicus 30m Global DEM</demName>
      <demResamplingMethod>BILINEAR_INTERPOLATION</demResamplingMethod>
      <imgResamplingMethod>BILINEAR_INTERPOLATION</imgResamplingMethod>
      <pixelSpacingInMeter>10.0</pixelSpacingInMeter>
      <mapProjection>AUTO:42001</mapProjection>
      <nodataValueAtSea>false</nodataValueAtSea>
    </parameters>
  </node>
  <node id="db">
    <operator>LinearToFromdB</operator>
    <sources><sourceProduct refid="tc"/></sources>
    <parameters class="com.bc.ceres.binding.dom.XppDomElement">
      <sourceBands>Sigma0_VH,Sigma0_VV</sourceBands>
    </parameters>
  </node>
  <node id="write">
    <operator>Write</operator>
    <sources><sourceProduct refid="db"/></sources>
    <parameters class="com.bc.ceres.binding.dom.XppDomElement">
      <file>{escape(output_dim)}</file>
      <formatName>BEAM-DIMAP</formatName>
    </parameters>
  </node>
</graph>"""


def build_change_detection_graph(
    pre_dim: str,
    post_dim: str,
    output_file: str,
    threshold_db: float,
    water_threshold_db: float = -17.0,
) -> str:
    """Stage 3 graph: collocate the two preprocessed products, compute Δσ⁰ and the
    binary landslide masks, and write a multi-band BigTIFF GeoTIFF.

    ``pre_dim`` / ``post_dim`` are the BEAM-DIMAP outputs of build_preprocess_graph.
    ``water_threshold_db`` gates out water / radar shadow: a pixel can only be a
    landslide candidate if BOTH epochs' VV backscatter is above this level (land).
    """
    t = threshold_db
    w = water_threshold_db
    # Bands in the .dim are Sigma0_VV_db / Sigma0_VH_db; Collocate appends _M (post,
    # reference) / _S (pre, secondary).
    diff_vv = "Sigma0_VV_db_M - Sigma0_VV_db_S"
    diff_vh = "Sigma0_VH_db_M - Sigma0_VH_db_S"
    # Land gate: both epochs must be above the water threshold in VV (open water and
    # radar shadow are dark and otherwise trip the change threshold as false positives).
    land = f"(Sigma0_VV_db_M > {w} && Sigma0_VV_db_S > {w})"
    band_maths = (
        _band_maths_node("diff_VV", diff_vv)
        + _band_maths_node("diff_VH", diff_vh)
        + _band_maths_node("mask_VV", f"(({diff_vv}) <= {t} && {land}) ? 1 : 0")
        + _band_maths_node("mask_VH", f"(({diff_vh}) <= {t} && {land}) ? 1 : 0")
        + _band_maths_node(
            "mask_combined",
            f"((({diff_vv}) <= {t} || ({diff_vh}) <= {t}) && {land}) ? 1 : 0",
        )
    )
    return f"""<graph id="LandslideChangeDetection">
  <version>1.0</version>
  <node id="read_pre">
    <operator>Read</operator>
    <sources/>
    <parameters class="com.bc.ceres.binding.dom.XppDomElement">
      <file>{escape(pre_dim)}</file>
    </parameters>
  </node>
  <node id="read_post">
    <operator>Read</operator>
    <sources/>
    <parameters class="com.bc.ceres.binding.dom.XppDomElement">
      <file>{escape(post_dim)}</file>
    </parameters>
  </node>
  <node id="collocate">
    <operator>Collocate</operator>
    <sources>
      <sourceProduct refid="read_post"/>
      <sourceProduct.1 refid="read_pre"/>
    </sources>
    <parameters class="com.bc.ceres.binding.dom.XppDomElement">
      <renameReferenceComponents>true</renameReferenceComponents>
      <renameSecondaryComponents>true</renameSecondaryComponents>
      <referenceComponentPattern>${{ORIGINAL_NAME}}_M</referenceComponentPattern>
      <secondaryComponentPattern>${{ORIGINAL_NAME}}_S</secondaryComponentPattern>
      <resamplingType>BILINEAR_INTERPOLATION</resamplingType>
    </parameters>
  </node>
  <node id="diff">
    <operator>BandMaths</operator>
    <sources><sourceProduct refid="collocate"/></sources>
    <parameters class="com.bc.ceres.binding.dom.XppDomElement">
      <targetBands>{band_maths}
      </targetBands>
    </parameters>
  </node>
  <node id="write">
    <operator>Write</operator>
    <sources><sourceProduct refid="diff"/></sources>
    <parameters class="com.bc.ceres.binding.dom.XppDomElement">
      <file>{escape(output_file)}</file>
      <formatName>GeoTIFF-BigTIFF</formatName>
    </parameters>
  </node>
</graph>"""
