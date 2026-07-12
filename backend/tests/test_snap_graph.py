from app.services.snap_graph import (
    build_calibration_graph,
    build_db_graph,
    build_orbit_graph,
    build_speckle_graph,
    build_terrain_correction_graph,
    build_tnr_graph,
)


def test_build_orbit_graph_without_aoi_reads_directly_from_source():
    xml = build_orbit_graph("input.zip", "output.dim")

    assert "<operator>Apply-Orbit-File</operator>" in xml
    assert "<operator>Subset</operator>" not in xml
    assert "<file>input.zip</file>" in xml
    assert '<sourceProduct refid="read"/>' in xml  # orbit reads directly from Read
    assert "<file>output.dim</file>" in xml
    assert "Sentinel Precise (Auto Download)" in xml
    assert "<polyDegree>3</polyDegree>" in xml


def test_build_orbit_graph_with_aoi_inserts_subset_before_orbit():
    xml = build_orbit_graph("input.zip", "output.dim", aoi_bbox=[95.0, 4.0, 96.0, 5.0])

    assert "<operator>Subset</operator>" in xml
    assert "POLYGON ((95.0 4.0, 96.0 4.0, 96.0 5.0, 95.0 5.0, 95.0 4.0))" in xml
    # Orbit must read from the Subset node, not directly from Read, when an AOI is given.
    orbit_start = xml.index("<operator>Apply-Orbit-File</operator>")
    orbit_block = xml[orbit_start : orbit_start + 400]
    assert '<sourceProduct refid="subset"/>' in orbit_block


def test_build_tnr_graph_reads_source_dim_and_removes_thermal_noise():
    xml = build_tnr_graph("orbit.dim", "tnr.dim")

    assert "<file>orbit.dim</file>" in xml
    assert "<operator>ThermalNoiseRemoval</operator>" in xml
    assert "<removeThermalNoise>true</removeThermalNoise>" in xml
    assert "<outputNoise>false</outputNoise>" in xml
    assert "<selectedPolarisations>VH,VV</selectedPolarisations>" in xml
    assert "<file>tnr.dim</file>" in xml


def test_build_calibration_graph_outputs_sigma0_only():
    xml = build_calibration_graph("tnr.dim", "cal.dim")

    assert "<file>tnr.dim</file>" in xml
    assert "<operator>Calibration</operator>" in xml
    assert "<outputSigmaBand>true</outputSigmaBand>" in xml
    assert "<outputGammaBand>false</outputGammaBand>" in xml
    assert "<outputBetaBand>false</outputBetaBand>" in xml
    assert "<file>cal.dim</file>" in xml


def test_build_speckle_graph_uses_refined_lee():
    xml = build_speckle_graph("cal.dim", "speckle.dim")

    assert "<file>cal.dim</file>" in xml
    assert "<operator>Speckle-Filter</operator>" in xml
    assert "<filter>Refined Lee</filter>" in xml
    assert "<sourceBands>Sigma0_VH,Sigma0_VV</sourceBands>" in xml
    assert "<file>speckle.dim</file>" in xml


def test_build_terrain_correction_graph_uses_copernicus_dem_and_auto_utm():
    xml = build_terrain_correction_graph("speckle.dim", "tc.dim")

    assert "<file>speckle.dim</file>" in xml
    assert "<operator>Terrain-Correction</operator>" in xml
    assert "<demName>Copernicus 30m Global DEM</demName>" in xml
    assert "<mapProjection>AUTO:42001</mapProjection>" in xml
    assert "<pixelSpacingInMeter>10.0</pixelSpacingInMeter>" in xml
    assert "<file>tc.dim</file>" in xml


def test_build_db_graph_converts_sigma0_bands():
    xml = build_db_graph("tc.dim", "db.dim")

    assert "<file>tc.dim</file>" in xml
    assert "<operator>LinearToFromdB</operator>" in xml
    assert "<sourceBands>Sigma0_VH,Sigma0_VV</sourceBands>" in xml
    assert "<file>db.dim</file>" in xml
