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

    def test_auto_filename_timestamp(self, export_module, sample_params):
        """Calling without explicit filename uses a timestamp-based name."""
        path = export_module.export_protocol(sample_params)
        assert os.path.exists(path)
        assert path.endswith(".json")
        # The auto-generated name includes "protocol_"
        assert "protocol_" in os.path.basename(path)


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

    def test_auto_filename(self, export_module, sample_image, sample_params, sample_metrics):
        path = export_module.export_report(sample_image, sample_params, sample_metrics)
        assert os.path.exists(path)

    def test_ir_sequence_params(self, export_module, sample_image, sample_metrics):
        ir_params = {
            "sequence": "Inversion Recovery",
            "TR": 3000, "TE": 15, "TI": 150,
            "flip_angle": 90, "matrix_size": 256,
            "FOV": 240, "bandwidth": 125, "NEX": 1,
        }
        path = export_module.export_report(sample_image, ir_params, sample_metrics,
                                           "ir_report.pdf")
        assert os.path.exists(path)


class TestLoadProtocolEdgeCases:
    def test_load_bare_json(self, export_module, tmp_path):
        """load_protocol falls back gracefully when 'parameters' key is absent."""
        bare = {"TR": 500, "TE": 15, "sequence": "SE"}
        p = str(tmp_path / "bare.json")
        with open(p, "w") as f:
            json.dump(bare, f)
        loaded = export_module.load_protocol(p)
        assert loaded["TR"] == 500

    def test_ensure_export_dir_returns_string(self, export_module):
        result = export_module.ensure_export_dir()
        assert isinstance(result, str)
