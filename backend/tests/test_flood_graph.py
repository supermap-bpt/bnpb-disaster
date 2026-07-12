from app.services.flood_graph import (
    build_border_noise_graph,
    build_calibration_graph,
    build_flood_mask_graph,
    build_orbit_graph,
    build_speckle_graph,
    build_subset_graph,
    build_terrain_correction_graph,
    build_tnr_graph,
)


def test_build_tnr_graph_uses_vv_only():
    xml = build_tnr_graph("input.zip", "tnr.dim")

    assert "<file>input.zip</file>" in xml
    assert "<operator>ThermalNoiseRemoval</operator>" in xml
    assert "<selectedPolarisations>VV</selectedPolarisations>" in xml
    assert "<removeThermalNoise>true</removeThermalNoise>" in xml
    assert "<file>tnr.dim</file>" in xml


def test_build_orbit_graph_reads_source_dim():
    xml = build_orbit_graph("tnr.dim", "orbit.dim")

    assert "<file>tnr.dim</file>" in xml
    assert "<operator>Apply-Orbit-File</operator>" in xml
    assert "Sentinel Precise (Auto Download)" in xml
    assert "<polyDegree>3</polyDegree>" in xml
    assert "<file>orbit.dim</file>" in xml


def test_build_border_noise_graph_uses_pdf_thresholds():
    xml = build_border_noise_graph("orbit.dim", "border.dim")

    assert "<file>orbit.dim</file>" in xml
    assert "<operator>Remove-GRD-Border-Noise</operator>" in xml
    assert "<selectedPolarisations>VV</selectedPolarisations>" in xml
    assert "<borderLimit>500</borderLimit>" in xml
    assert "<trimThreshold>0.5</trimThreshold>" in xml
    assert "<file>border.dim</file>" in xml


def test_build_calibration_graph_outputs_sigma0_vv_only():
    xml = build_calibration_graph("border.dim", "cal.dim")

    assert "<file>border.dim</file>" in xml
    assert "<operator>Calibration</operator>" in xml
    assert "<selectedPolarisations>VV</selectedPolarisations>" in xml
    assert "<outputSigmaBand>true</outputSigmaBand>" in xml
    assert "<outputGammaBand>false</outputGammaBand>" in xml
    assert "<file>cal.dim</file>" in xml


def test_build_subset_graph_without_aoi_is_a_passthrough():
    xml = build_subset_graph("cal.dim", "subset.dim")

    assert "<file>cal.dim</file>" in xml
    assert "<operator>Subset</operator>" not in xml
    assert "<file>subset.dim</file>" in xml


def test_build_subset_graph_with_aoi_crops_to_the_bbox():
    xml = build_subset_graph("cal.dim", "subset.dim", aoi_bbox=[95.0, 4.0, 96.0, 5.0])

    assert "<operator>Subset</operator>" in xml
    assert "POLYGON ((95.0 4.0, 96.0 4.0, 96.0 5.0, 95.0 5.0, 95.0 4.0))" in xml
    assert "<file>subset.dim</file>" in xml


def test_build_speckle_graph_uses_lee_sigma_pdf_params():
    xml = build_speckle_graph("subset.dim", "speckle.dim")

    assert "<file>subset.dim</file>" in xml
    assert "<operator>Speckle-Filter</operator>" in xml
    assert "<sourceBands>Sigma0_VV</sourceBands>" in xml
    assert "<filter>Lee Sigma</filter>" in xml
    assert "<numLooksStr>1</numLooksStr>" in xml
    assert "<windowSize>7x7</windowSize>" in xml
    assert "<targetWindowSizeStr>3x3</targetWindowSizeStr>" in xml
    assert "<sigmaStr>0.9</sigmaStr>" in xml
    assert "<file>speckle.dim</file>" in xml


def test_build_terrain_correction_graph_uses_copernicus_and_wgs84dd():
    xml = build_terrain_correction_graph("speckle.dim", "tc.dim")

    assert "<file>speckle.dim</file>" in xml
    assert "<operator>Terrain-Correction</operator>" in xml
    assert "<demName>Copernicus 30m Global DEM</demName>" in xml
    assert "<demResamplingMethod>NEAREST_NEIGHBOUR</demResamplingMethod>" in xml
    assert "<imgResamplingMethod>NEAREST_NEIGHBOUR</imgResamplingMethod>" in xml
    assert "<mapProjection>WGS84(DD)</mapProjection>" in xml
    assert "<pixelSpacingInMeter>10.0</pixelSpacingInMeter>" in xml
    assert "<file>tc.dim</file>" in xml


def test_build_flood_mask_graph_applies_threshold_and_writes_geotiff():
    xml = build_flood_mask_graph("tc.dim", "result.tif", threshold_sigma0=0.0137)

    assert "<file>tc.dim</file>" in xml
    assert "<operator>BandMaths</operator>" in xml
    assert "<name>water_and_flood_area</name>" in xml
    assert "Sigma0_VV &lt; 0.0137 ? 1 : NaN" in xml
    assert "<noDataValue>NaN</noDataValue>" in xml
    assert "<file>result.tif</file>" in xml
    assert "<formatName>GeoTIFF-BigTIFF</formatName>" in xml
