"""Tests for DICOM export/import module (src/dicom_export.py)."""

import os
import numpy as np
import pytest
import pydicom

from dicom_export import (
    make_dataset,
    image_to_dicom,
    volume_to_dicom_series,
    load_dicom,
    load_dicom_series,
    read_scan_params,
    _scale_to_uint16,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def small_image():
    rng = np.random.default_rng(42)
    return rng.random((32, 32)) * 500.0


@pytest.fixture
def small_volume():
    rng = np.random.default_rng(7)
    return rng.random((5, 16, 16)) * 300.0


@pytest.fixture
def dcm_path(tmp_path, small_image):
    """Write a single DICOM file and return its path."""
    p = image_to_dicom(small_image, str(tmp_path / "test.dcm"),
                       TR_ms=500., TE_ms=15., sequence="SE")
    return p


# ---------------------------------------------------------------------------
# _scale_to_uint16
# ---------------------------------------------------------------------------

class TestScaleToUint16:

    def test_output_dtype(self, small_image):
        px, s, o = _scale_to_uint16(small_image)
        assert px.dtype == np.uint16

    def test_range(self, small_image):
        px, s, o = _scale_to_uint16(small_image)
        assert px.min() == 0
        assert px.max() <= 4095

    def test_roundtrip(self, small_image):
        px, slope, intercept = _scale_to_uint16(small_image)
        recovered = px.astype(np.float64) * slope + intercept
        np.testing.assert_allclose(recovered, small_image, atol=slope)

    def test_uniform_image(self):
        img = np.full((4, 4), 7.0)
        px, s, o = _scale_to_uint16(img)
        assert px.max() == 0      # all zeros
        assert o == 7.0           # intercept carries the value

    def test_vmax_clipping(self, small_image):
        px, s, o = _scale_to_uint16(small_image, vmax=1000.)
        # vmax larger than actual max → stored range uses fewer bits
        assert px.max() < 4095


# ---------------------------------------------------------------------------
# make_dataset
# ---------------------------------------------------------------------------

class TestMakeDataset:

    def test_returns_dataset(self, small_image):
        ds = make_dataset(small_image)
        assert isinstance(ds, pydicom.Dataset)

    def test_pixel_data_present(self, small_image):
        ds = make_dataset(small_image)
        assert len(ds.PixelData) > 0

    def test_dimensions(self, small_image):
        ds = make_dataset(small_image)
        assert ds.Rows    == small_image.shape[0]
        assert ds.Columns == small_image.shape[1]

    def test_patient_name_simulated(self, small_image):
        ds = make_dataset(small_image)
        assert "SIMULATED" in str(ds.PatientName).upper()

    def test_image_type_derived_secondary(self, small_image):
        ds = make_dataset(small_image)
        assert "DERIVED"   in ds.ImageType
        assert "SECONDARY" in ds.ImageType

    def test_modality_mr(self, small_image):
        ds = make_dataset(small_image)
        assert ds.Modality == "MR"

    def test_scan_params_stored(self, small_image):
        ds = make_dataset(small_image, TR_ms=800., TE_ms=25.,
                          flip_angle_deg=15., sequence="GRE")
        assert ds.RepetitionTime == 800.
        assert ds.EchoTime        == 25.
        assert ds.FlipAngle       == 15.
        assert "GRE" in ds.SequenceName

    def test_ti_stored_when_provided(self, small_image):
        ds = make_dataset(small_image, TI_ms=300.)
        assert hasattr(ds, "InversionTime")
        assert ds.InversionTime == 300.

    def test_ti_absent_when_none(self, small_image):
        ds = make_dataset(small_image, TI_ms=None)
        assert not hasattr(ds, "InversionTime")

    def test_rescale_tags(self, small_image):
        ds = make_dataset(small_image)
        assert hasattr(ds, "RescaleSlope")
        assert hasattr(ds, "RescaleIntercept")
        assert float(ds.RescaleSlope) > 0

    def test_custom_uids_preserved(self, small_image):
        study  = pydicom.uid.generate_uid()
        series = pydicom.uid.generate_uid()
        sop    = pydicom.uid.generate_uid()
        ds = make_dataset(small_image, study_uid=study,
                          series_uid=series, sop_instance_uid=sop)
        assert ds.StudyInstanceUID  == study
        assert ds.SeriesInstanceUID == series
        assert ds.SOPInstanceUID    == sop

    def test_pixel_spacing(self, small_image):
        ds = make_dataset(small_image, pixel_spacing_mm=(2.5, 2.5))
        assert ds.PixelSpacing[0] == 2.5

    def test_slice_location(self, small_image):
        ds = make_dataset(small_image, slice_location_mm=42.)
        assert ds.SliceLocation == 42.

    def test_window_tags(self, small_image):
        ds = make_dataset(small_image)
        assert hasattr(ds, "WindowCenter")
        assert hasattr(ds, "WindowWidth")

    def test_custom_window(self, small_image):
        ds = make_dataset(small_image, window_center=100., window_width=400.)
        assert ds.WindowCenter == 100.
        assert ds.WindowWidth  == 400.

    def test_raises_on_non_2d(self):
        with pytest.raises(ValueError, match="2-D"):
            make_dataset(np.zeros((4, 4, 4)))

    def test_bits_allocated(self, small_image):
        ds = make_dataset(small_image)
        assert ds.BitsAllocated == 16
        assert ds.BitsStored    == 16
        assert ds.HighBit       == 15

    def test_pixel_representation_unsigned(self, small_image):
        ds = make_dataset(small_image)
        assert ds.PixelRepresentation == 0


# ---------------------------------------------------------------------------
# image_to_dicom
# ---------------------------------------------------------------------------

class TestImageToDicom:

    def test_creates_file(self, tmp_path, small_image):
        p = image_to_dicom(small_image, str(tmp_path / "out.dcm"))
        assert os.path.exists(p)

    def test_returns_absolute_path(self, tmp_path, small_image):
        p = image_to_dicom(small_image, str(tmp_path / "out.dcm"))
        assert os.path.isabs(p)

    def test_creates_parent_dirs(self, tmp_path, small_image):
        nested = str(tmp_path / "a" / "b" / "c" / "out.dcm")
        p = image_to_dicom(small_image, nested)
        assert os.path.exists(p)

    def test_readable_by_pydicom(self, tmp_path, small_image):
        p = image_to_dicom(small_image, str(tmp_path / "out.dcm"))
        ds = pydicom.dcmread(p)
        assert ds.Rows == small_image.shape[0]

    def test_scan_params_forwarded(self, tmp_path, small_image):
        p = image_to_dicom(small_image, str(tmp_path / "out.dcm"),
                           TR_ms=1000., TE_ms=30., sequence="GRE")
        ds = pydicom.dcmread(p)
        assert ds.RepetitionTime == 1000.
        assert ds.EchoTime        == 30.


# ---------------------------------------------------------------------------
# load_dicom
# ---------------------------------------------------------------------------

class TestLoadDicom:

    def test_shape_preserved(self, dcm_path, small_image):
        back = load_dicom(dcm_path)
        assert back.shape == small_image.shape

    def test_dtype_float64(self, dcm_path):
        back = load_dicom(dcm_path)
        assert back.dtype == np.float64

    def test_roundtrip_accuracy(self, dcm_path, small_image):
        back = load_dicom(dcm_path)
        # Max error = 1 quantization step = (max-min)/4095
        step = (small_image.max() - small_image.min()) / 4095.
        np.testing.assert_allclose(back, small_image, atol=step * 1.01)

    def test_nonnegative(self, dcm_path):
        back = load_dicom(dcm_path)
        assert np.all(back >= 0)

    def test_applies_rescale(self, tmp_path, small_image):
        # Write with known slope/intercept then verify they're applied
        p = image_to_dicom(small_image, str(tmp_path / "ri.dcm"))
        ds_raw = pydicom.dcmread(p)
        slope     = float(ds_raw.RescaleSlope)
        intercept = float(ds_raw.RescaleIntercept)
        raw_px = ds_raw.pixel_array.astype(np.float64)
        expected = raw_px * slope + intercept
        np.testing.assert_allclose(load_dicom(p), expected, rtol=1e-10)


# ---------------------------------------------------------------------------
# volume_to_dicom_series
# ---------------------------------------------------------------------------

class TestVolumeToDicomSeries:

    def test_creates_correct_number_of_files(self, tmp_path, small_volume):
        paths = volume_to_dicom_series(small_volume, str(tmp_path / "series"))
        assert len(paths) == small_volume.shape[0]

    def test_all_files_exist(self, tmp_path, small_volume):
        out = str(tmp_path / "series")
        paths = volume_to_dicom_series(small_volume, out)
        for p in paths:
            assert os.path.exists(p)

    def test_files_are_readable(self, tmp_path, small_volume):
        out = str(tmp_path / "series")
        paths = volume_to_dicom_series(small_volume, out)
        for p in paths:
            ds = pydicom.dcmread(p)
            assert ds.Rows > 0

    def test_shared_study_uid(self, tmp_path, small_volume):
        out = str(tmp_path / "series")
        paths = volume_to_dicom_series(small_volume, out)
        study_uids = {pydicom.dcmread(p, stop_before_pixels=True).StudyInstanceUID
                      for p in paths}
        assert len(study_uids) == 1

    def test_shared_series_uid(self, tmp_path, small_volume):
        out = str(tmp_path / "series")
        paths = volume_to_dicom_series(small_volume, out)
        series_uids = {pydicom.dcmread(p, stop_before_pixels=True).SeriesInstanceUID
                       for p in paths}
        assert len(series_uids) == 1

    def test_instance_numbers_sequential(self, tmp_path, small_volume):
        out = str(tmp_path / "series")
        paths = volume_to_dicom_series(small_volume, out)
        nums = [int(pydicom.dcmread(p, stop_before_pixels=True).InstanceNumber)
                for p in paths]
        assert nums == list(range(1, len(paths) + 1))

    def test_slice_locations_increase(self, tmp_path, small_volume):
        out = str(tmp_path / "series")
        paths = volume_to_dicom_series(small_volume, out, slice_thickness_mm=3.)
        locs = [float(pydicom.dcmread(p, stop_before_pixels=True).SliceLocation)
                for p in paths]
        assert all(locs[i] < locs[i + 1] for i in range(len(locs) - 1))

    def test_raises_on_non_3d(self, tmp_path):
        with pytest.raises(ValueError, match="3-D"):
            volume_to_dicom_series(np.zeros((4, 4)), str(tmp_path))

    def test_custom_filename_prefix(self, tmp_path, small_volume):
        out = str(tmp_path / "series")
        paths = volume_to_dicom_series(small_volume, out, filename_prefix="frame")
        basenames = [os.path.basename(p) for p in paths]
        assert all(b.startswith("frame_") for b in basenames)

    def test_scan_params_forwarded(self, tmp_path, small_volume):
        out = str(tmp_path / "series")
        paths = volume_to_dicom_series(small_volume, out, TR_ms=2000., TE_ms=30.)
        ds = pydicom.dcmread(paths[0], stop_before_pixels=True)
        assert ds.RepetitionTime == 2000.


# ---------------------------------------------------------------------------
# load_dicom_series
# ---------------------------------------------------------------------------

class TestLoadDicomSeries:

    def test_roundtrip_shape(self, tmp_path, small_volume):
        out = str(tmp_path / "series")
        volume_to_dicom_series(small_volume, out)
        back = load_dicom_series(out)
        assert back.shape == small_volume.shape

    def test_roundtrip_dtype(self, tmp_path, small_volume):
        out = str(tmp_path / "series")
        volume_to_dicom_series(small_volume, out)
        back = load_dicom_series(out)
        assert back.dtype == np.float64

    def test_roundtrip_values(self, tmp_path, small_volume):
        out = str(tmp_path / "series")
        volume_to_dicom_series(small_volume, out)
        back = load_dicom_series(out)
        step = (small_volume.max() - small_volume.min()) / 4095.
        np.testing.assert_allclose(back, small_volume, atol=step * 1.01)

    def test_raises_on_empty_dir(self, tmp_path):
        empty = str(tmp_path / "empty")
        os.makedirs(empty)
        with pytest.raises(FileNotFoundError):
            load_dicom_series(empty)

    def test_ordered_by_instance_number(self, tmp_path, small_volume):
        out = str(tmp_path / "series")
        volume_to_dicom_series(small_volume, out)
        back = load_dicom_series(out)
        # First and last slices should match original
        step = (small_volume.max() - small_volume.min()) / 4095.
        np.testing.assert_allclose(back[0],  small_volume[0],  atol=step * 1.01)
        np.testing.assert_allclose(back[-1], small_volume[-1], atol=step * 1.01)


# ---------------------------------------------------------------------------
# read_scan_params
# ---------------------------------------------------------------------------

class TestReadScanParams:

    def test_tr_te(self, dcm_path):
        params = read_scan_params(dcm_path)
        assert params["TR_ms"] == 500.
        assert params["TE_ms"] == 15.

    def test_sequence(self, dcm_path):
        params = read_scan_params(dcm_path)
        assert params["sequence"] == "SE"

    def test_ti_none_when_absent(self, dcm_path):
        params = read_scan_params(dcm_path)
        assert params["TI_ms"] is None

    def test_ti_present(self, tmp_path, small_image):
        p = image_to_dicom(small_image, str(tmp_path / "ir.dcm"),
                           TR_ms=3000., TE_ms=10., TI_ms=400., sequence="IR")
        params = read_scan_params(p)
        assert params["TI_ms"] == 400.

    def test_flip_angle(self, tmp_path, small_image):
        p = image_to_dicom(small_image, str(tmp_path / "gre.dcm"),
                           flip_angle_deg=15., sequence="GRE")
        params = read_scan_params(p)
        assert params["flip_angle_deg"] == 15.

    def test_field_strength(self, tmp_path, small_image):
        p = image_to_dicom(small_image, str(tmp_path / "3t.dcm"),
                           field_strength_T=3.0)
        params = read_scan_params(p)
        assert params["field_strength_T"] == 3.0

    def test_returns_dict_with_all_keys(self, dcm_path):
        params = read_scan_params(dcm_path)
        for key in ("TR_ms", "TE_ms", "TI_ms", "flip_angle_deg",
                    "sequence", "field_strength_T"):
            assert key in params


# ---------------------------------------------------------------------------
# Branch coverage additions
# ---------------------------------------------------------------------------
class TestLoadDicomSeriesMissingInstanceNumber:
    def test_no_instance_number_falls_back_to_path(self, tmp_path, small_volume):
        """DICOM files without InstanceNumber trigger the except branch (lines 353-354)
        in _sort_key — the sort falls back to using the file path string."""
        import pydicom
        out = str(tmp_path / "series_no_inst")
        volume_to_dicom_series(small_volume, out)
        # Remove InstanceNumber from all DICOM files
        for fn in os.listdir(out):
            if fn.endswith(".dcm"):
                fp = os.path.join(out, fn)
                ds = pydicom.dcmread(fp)
                if hasattr(ds, "InstanceNumber"):
                    del ds.InstanceNumber
                ds.save_as(fp)
        back = load_dicom_series(out)
        assert back.shape == small_volume.shape
