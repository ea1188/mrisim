"""DICOM export and import for simulated MR images.

Produces standard-compliant DICOM files clearly marked as simulated data
(ImageType = DERIVED\\SECONDARY, PatientName = SIMULATED^PHANTOM).

Key functions
-------------
image_to_dicom       — write a single 2-D float image as a DICOM file
volume_to_dicom_series — write a 3-D volume as a numbered DICOM series
load_dicom           — read a DICOM file back to a float64 array
load_dicom_series    — load and z-stack all DICOM files in a directory
make_dataset         — build a minimal pydicom Dataset (usable as a template)
"""

import os
import numpy as np

import pydicom
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import (
    ExplicitVRLittleEndian,
    UID,
    generate_uid,
    MRImageStorage,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_SIMULATED_NAME  = "SIMULATED^PHANTOM"
_SIMULATED_ID    = "SIMULATED001"
_STUDY_DESCR     = "MRI Simulation Platform"
_DISCLAIMER      = "SIMULATED - Not for clinical use"

_MAX_STORED = 4095          # 12-bit dynamic range stored in 16-bit pixels
_BITS_ALLOCATED = 16
_BITS_STORED    = 16
_HIGH_BIT       = 15


def _scale_to_uint16(image: np.ndarray,
                     vmax: float | None = None) -> tuple[np.ndarray, float, float]:
    """Linearly scale a float array to uint16 in [0, _MAX_STORED].

    Returns
    -------
    pixels : ndarray uint16
    scale : float   multiply stored pixels by this to recover original values
    offset : float  add this after multiplying (always 0 for non-negative data)
    """
    img = np.asarray(image, dtype=np.float64)
    img_min = float(img.min())
    img_max = float(img.max()) if vmax is None else float(vmax)

    if img_max == img_min:
        return np.zeros(img.shape, dtype=np.uint16), 1.0, img_min

    scale = (img_max - img_min) / _MAX_STORED
    pixels = np.round((img - img_min) / scale).astype(np.uint16)
    return pixels, scale, img_min


def _make_file_meta(sop_class_uid: str | None = None,
                    sop_instance_uid: str | None = None) -> FileMetaDataset:
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID    = UID(sop_class_uid or MRImageStorage)
    meta.MediaStorageSOPInstanceUID = UID(sop_instance_uid or generate_uid())
    meta.TransferSyntaxUID          = ExplicitVRLittleEndian
    return meta


# ---------------------------------------------------------------------------
# make_dataset
# ---------------------------------------------------------------------------

def make_dataset(
    image: np.ndarray,
    TR_ms: float = 0.,
    TE_ms: float = 0.,
    TI_ms: float | None = None,
    flip_angle_deg: float = 90.,
    sequence: str = "SE",
    field_strength_T: float = 1.5,
    pixel_spacing_mm: tuple[float, float] = (1.0, 1.0),
    slice_thickness_mm: float = 5.0,
    slice_location_mm: float = 0.0,
    instance_number: int = 1,
    study_uid: str | None = None,
    series_uid: str | None = None,
    sop_instance_uid: str | None = None,
    window_center: float | None = None,
    window_width: float | None = None,
) -> Dataset:
    """Build a minimal MR DICOM Dataset for a single 2-D float image.

    The returned Dataset is ready for ``pydicom.dcmwrite``.  Pixel data are
    stored as uint16 with RescaleSlope/RescaleIntercept so that the original
    float values can be recovered via ``load_dicom``.

    Parameters
    ----------
    image : (rows, cols) float array
    TR_ms, TE_ms : float  repetition/echo time in ms
    TI_ms : float or None  inversion time (IR only)
    flip_angle_deg : float
    sequence : str  label stored in SequenceName ("SE", "GRE", "IR", …)
    field_strength_T : float  stored in MagneticFieldStrength
    pixel_spacing_mm : (row_spacing, col_spacing) in mm
    slice_thickness_mm, slice_location_mm : float  in mm
    instance_number : int  InstanceNumber tag (used for series ordering)
    study_uid, series_uid, sop_instance_uid : str or None  auto-generated if None
    window_center, window_width : float or None  auto-computed if None

    Returns
    -------
    ds : pydicom.Dataset  complete, writable DICOM dataset
    """
    img2d = np.asarray(image, dtype=np.float64)
    if img2d.ndim != 2:
        raise ValueError(f"image must be 2-D, got shape {img2d.shape}")

    rows, cols = img2d.shape
    pixels, slope, intercept = _scale_to_uint16(img2d)

    sop_uid   = sop_instance_uid or generate_uid()
    study_uid = study_uid        or generate_uid()
    ser_uid   = series_uid       or generate_uid()

    # --- File meta ---
    ds = Dataset()
    ds.file_meta = _make_file_meta(MRImageStorage, sop_uid)
    ds.preamble  = b"\x00" * 128

    # --- Patient module ---
    ds.PatientName = _SIMULATED_NAME
    ds.PatientID   = _SIMULATED_ID
    ds.PatientBirthDate = ""
    ds.PatientSex  = ""

    # --- General study ---
    ds.StudyInstanceUID = study_uid
    ds.StudyDate        = ""
    ds.StudyTime        = ""
    ds.StudyDescription = _STUDY_DESCR
    ds.AccessionNumber  = ""
    ds.ReferringPhysicianName = ""

    # --- General series ---
    ds.Modality          = "MR"
    ds.SeriesInstanceUID = ser_uid
    ds.SeriesNumber      = 1
    ds.SeriesDescription = f"{sequence} TR{TR_ms:.0f}/TE{TE_ms:.0f}"

    # --- General equipment ---
    ds.Manufacturer      = _DISCLAIMER
    ds.ManufacturerModelName = "MRI Simulation Platform"

    # --- General image ---
    ds.InstanceNumber = instance_number
    ds.ImageType      = ["DERIVED", "SECONDARY"]
    ds.ContentDate    = ""
    ds.ContentTime    = ""
    ds.SOPClassUID    = MRImageStorage
    ds.SOPInstanceUID = sop_uid

    # --- Image plane ---
    ds.PixelSpacing        = list(pixel_spacing_mm)
    ds.SliceThickness      = slice_thickness_mm
    ds.SliceLocation       = slice_location_mm
    ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    ds.ImagePositionPatient    = [0., 0., float(slice_location_mm)]

    # --- MR image module ---
    ds.MagneticFieldStrength  = field_strength_T
    ds.RepetitionTime         = TR_ms
    ds.EchoTime               = TE_ms
    ds.FlipAngle              = flip_angle_deg
    ds.SequenceName           = sequence.upper()
    ds.EchoPulseSequence      = "SPIN" if sequence.upper() == "SE" else "GRADIENT"
    if TI_ms is not None:
        ds.InversionTime = TI_ms

    # --- Pixel data ---
    ds.SamplesPerPixel          = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.Rows                     = rows
    ds.Columns                  = cols
    ds.BitsAllocated            = _BITS_ALLOCATED
    ds.BitsStored               = _BITS_STORED
    ds.HighBit                  = _HIGH_BIT
    ds.PixelRepresentation      = 0          # unsigned
    ds.RescaleSlope             = slope
    ds.RescaleIntercept         = intercept
    ds.RescaleType              = "US"       # unspecified (simulation units)
    ds.PixelData                = pixels.tobytes()

    # --- Window level (display) ---
    img_range = float(img2d.max() - img2d.min())
    ds.WindowCenter = window_center if window_center is not None else float(img2d.mean())
    ds.WindowWidth  = window_width  if window_width  is not None else max(img_range, 1e-6)

    return ds


# ---------------------------------------------------------------------------
# image_to_dicom
# ---------------------------------------------------------------------------

def image_to_dicom(
    image: np.ndarray,
    filepath: str,
    **kwargs: float | str | int | None,
) -> str:
    """Write a 2-D simulated MR image to a DICOM file.

    Parameters
    ----------
    image : (rows, cols) float array
    filepath : str  destination path (created including parent dirs)
    **kwargs : forwarded to :func:`make_dataset`
        TR_ms, TE_ms, TI_ms, flip_angle_deg, sequence, field_strength_T,
        pixel_spacing_mm, slice_thickness_mm, slice_location_mm,
        instance_number, study_uid, series_uid, sop_instance_uid,
        window_center, window_width

    Returns
    -------
    filepath : str  absolute path of the written file
    """
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    ds = make_dataset(image, **kwargs)  # type: ignore[arg-type]
    pydicom.dcmwrite(filepath, ds)
    return os.path.abspath(filepath)


# ---------------------------------------------------------------------------
# volume_to_dicom_series
# ---------------------------------------------------------------------------

def volume_to_dicom_series(
    volume: np.ndarray,
    output_dir: str,
    slice_axis: int = 0,
    slice_thickness_mm: float = 5.0,
    pixel_spacing_mm: tuple[float, float] = (1.0, 1.0),
    filename_prefix: str = "slice",
    study_uid: str | None = None,
    series_uid: str | None = None,
    **kwargs: float | str | int | None,
) -> list[str]:
    """Write a 3-D volume as a numbered DICOM series.

    Slices are extracted along ``slice_axis`` (default 0 = z-axis).  All
    slices share the same StudyInstanceUID and SeriesInstanceUID so that
    DICOM viewers group them into a single series.

    Parameters
    ----------
    volume : (nz, ny, nx) or any 3-D float array
    output_dir : str  directory that will receive the DICOM files
    slice_axis : int  axis to iterate over (default 0)
    slice_thickness_mm : float
    pixel_spacing_mm : (row, col) spacing in mm
    filename_prefix : str  each file is named "{prefix}_{i:04d}.dcm"
    study_uid, series_uid : str or None  shared across all slices
    **kwargs : forwarded to :func:`make_dataset` for every slice
        (TR_ms, TE_ms, sequence, flip_angle_deg, …)

    Returns
    -------
    paths : list[str]  absolute paths of written files, ordered by slice index
    """
    vol = np.asarray(volume, dtype=np.float64)
    if vol.ndim != 3:
        raise ValueError(f"volume must be 3-D, got shape {vol.shape}")

    os.makedirs(output_dir, exist_ok=True)
    shared_study  = study_uid  or generate_uid()
    shared_series = series_uid or generate_uid()

    n_slices = vol.shape[slice_axis]
    paths = []

    for i in range(n_slices):
        slc = np.take(vol, i, axis=slice_axis)
        loc = i * slice_thickness_mm
        fname = os.path.join(output_dir, f"{filename_prefix}_{i:04d}.dcm")
        image_to_dicom(
            slc,
            fname,
            slice_location_mm=loc,
            slice_thickness_mm=slice_thickness_mm,
            pixel_spacing_mm=pixel_spacing_mm,  # type: ignore[arg-type]
            instance_number=i + 1,
            study_uid=shared_study,
            series_uid=shared_series,
            **kwargs,
        )
        paths.append(os.path.abspath(fname))

    return paths


# ---------------------------------------------------------------------------
# load_dicom
# ---------------------------------------------------------------------------

def load_dicom(filepath: str) -> np.ndarray:
    """Load a DICOM file and return the pixel array as float64.

    Applies RescaleSlope and RescaleIntercept when present so that the
    returned values are in the original simulation units.

    Returns
    -------
    image : (rows, cols) float64
    """
    ds = pydicom.dcmread(filepath)
    pixels = ds.pixel_array.astype(np.float64)
    slope     = float(getattr(ds, "RescaleSlope",     1.0))
    intercept = float(getattr(ds, "RescaleIntercept", 0.0))
    return pixels * slope + intercept


# ---------------------------------------------------------------------------
# load_dicom_series
# ---------------------------------------------------------------------------

def load_dicom_series(directory: str) -> np.ndarray:
    """Load all DICOM files in a directory and stack them along axis 0.

    Files are sorted by InstanceNumber (or alphabetically if that tag is
    absent).  All slices must have the same Rows × Columns.

    Returns
    -------
    volume : (n_slices, rows, cols) float64
    """
    dcm_files = [
        os.path.join(directory, f)
        for f in os.listdir(directory)
        if f.lower().endswith(".dcm")
    ]
    if not dcm_files:
        raise FileNotFoundError(f"No .dcm files found in {directory!r}")

    def _sort_key(path: str) -> int | str:
        try:
            return int(pydicom.dcmread(path, stop_before_pixels=True).InstanceNumber)
        except Exception:
            return path

    dcm_files.sort(key=_sort_key)

    slices = [load_dicom(f) for f in dcm_files]
    return np.stack(slices, axis=0)


# ---------------------------------------------------------------------------
# Convenience: get scan parameters from a DICOM file
# ---------------------------------------------------------------------------

def read_scan_params(filepath: str) -> dict:
    """Read MR scan parameters from a DICOM header.

    Returns a dict with keys: TR_ms, TE_ms, TI_ms (None if absent),
    flip_angle_deg, sequence, field_strength_T.
    """
    ds = pydicom.dcmread(filepath, stop_before_pixels=True)
    return {
        "TR_ms":           float(getattr(ds, "RepetitionTime",       0.)),
        "TE_ms":           float(getattr(ds, "EchoTime",             0.)),
        "TI_ms":           float(ds.InversionTime) if hasattr(ds, "InversionTime") else None,
        "flip_angle_deg":  float(getattr(ds, "FlipAngle",           90.)),
        "sequence":        str(getattr(ds,   "SequenceName",         "")),
        "field_strength_T": float(getattr(ds, "MagneticFieldStrength", 1.5)),
    }
