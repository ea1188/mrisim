import json
import os
import numpy as np
import pytest


@pytest.fixture
def export_module(tmp_path, monkeypatch):
    import export as exp
    monkeypatch.setattr(exp, "EXPORT_DIR", str(tmp_path))
    return exp


@pytest.fixture
def sample_image():
    np.random.seed(0)
    return np.random.rand(32, 32)


@pytest.fixture
def sample_params():
    return {
        "sequence": "Spin Echo",
        "TR": 500,
        "TE": 15,
        "flip_angle": 90,
        "matrix_size": 256,
        "FOV": 240,
        "bandwidth": 125,
        "NEX": 1,
    }


@pytest.fixture
def sample_metrics():
    return {
        "scan_time": 128,
        "resolution": 0.94,
        "snr_wm": 3.0,
        "snr_gm": 2.7,
        "sar_head": 1.5,
    }


class TestExportImage:
    def test_creates_file(self, export_module, sample_image, sample_params):
        path = export_module.export_image(sample_image, "test.png", sample_params)
        assert os.path.exists(path)

    def test_creates_png(self, export_module, sample_image):
        path = export_module.export_image(sample_image, "img.png")
        assert path.endswith(".png")

    def test_auto_filename(self, export_module, sample_image):
        path = export_module.export_image(sample_image)
        assert os.path.exists(path)


class TestExportProtocol:
    def test_creates_json(self, export_module, sample_params):
        path = export_module.export_protocol(sample_params, "proto.json")
        assert os.path.exists(path)
        assert path.endswith(".json")

    def test_json_content(self, export_module, sample_params):
        path = export_module.export_protocol(sample_params, "proto2.json")
        with open(path) as f:
            data = json.load(f)
        assert "parameters" in data
        assert data["parameters"]["TR"] == sample_params["TR"]

    def test_has_disclaimer(self, export_module, sample_params):
        path = export_module.export_protocol(sample_params, "proto3.json")
        with open(path) as f:
            data = json.load(f)
        assert "SIMULATED" in data.get("disclaimer", "")


class TestLoadProtocol:
    def test_roundtrip(self, export_module, sample_params):
        path = export_module.export_protocol(sample_params, "round.json")
        loaded = export_module.load_protocol(path)
        assert loaded["TR"] == sample_params["TR"]
        assert loaded["sequence"] == sample_params["sequence"]


class TestExportReport:
    def test_creates_pdf(self, export_module, sample_image, sample_params, sample_metrics):
        path = export_module.export_report(sample_image, sample_params, sample_metrics,
                                           "report.pdf")
        assert os.path.exists(path)
        assert path.endswith(".pdf")
