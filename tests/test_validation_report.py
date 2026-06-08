"""The validation benchmark report (scripts/validation_report.py) doubles as a
test: every row carries a PASS/FAIL against a published reference or closed-form
result, so if the physics regresses, the report's `ok` flags flip and this fails.
"""
import importlib.util
import os

import pytest

_REPORT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts",
                       "validation_report.py")
_spec = importlib.util.spec_from_file_location("validation_report", _REPORT)
vr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vr)


@pytest.mark.parametrize("section", [
    "relaxation_section", "contrast_section", "landmarks_section", "scaling_section",
    "qmri_section", "diffusion_section",
])
def test_section_checks_pass(section):
    _md, ok = getattr(vr, section)()
    assert ok, f"{section} has a failing benchmark row"


def test_full_report_builds_and_passes():
    md, ok = vr.build_report()
    assert ok, "validation report has regressions"
    for heading in ("Tissue relaxation", "Contrast & nulling", "Analytic landmarks",
                    "scaling laws", "mapping accuracy", "Diffusion"):
        assert heading in md, f"report missing section: {heading}"
    # the report is non-trivial and self-labels its pass state
    assert "all checks pass" in md and len(md) > 1500
