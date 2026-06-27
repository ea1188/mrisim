"""Image / protocol / report export and protocol loading (ExportMixin)."""
import os
from typing import TYPE_CHECKING, Any

from PyQt6.QtWidgets import QFileDialog

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QMainWindow as _Base
else:
    _Base = object


class ExportMixin(_Base):
    # Provided by the host window (MRISimulator); annotation-only.
    sequence_type: Any
    TR: Any
    TE: Any
    TI: Any
    flip_angle: Any
    matrix_size: Any
    FOV: Any
    fov_fraction: Any
    bandwidth: Any
    NEX: Any
    b_value: Any
    diff_direction: Any
    diff_display: Any
    angio_type: Any
    angio_mip_slab: Any
    fmri_display: Any
    fmri_volumes: Any
    fmri_threshold: Any
    compare_status: Any
    get_current_params: Any
    simulate_with_params: Any
    on_sequence_change: Any

    def export_current_image(self) -> None:
        from export import export_image
        img, _ = self.simulate_with_params(self.get_current_params())
        self.compare_status.config(text=f"Saved: {os.path.basename(export_image(img, params=self.get_current_params()))}", fg='#69db7c')

    def export_current_dicom(self) -> None:
        from export import export_dicom
        p = self.get_current_params(); img, _ = self.simulate_with_params(p)
        self.compare_status.config(text=f"Saved: {os.path.basename(export_dicom(img, params=p))}", fg='#69db7c')

    def export_current_protocol(self) -> None:
        from export import export_protocol
        self.compare_status.config(text=f"Saved: {os.path.basename(export_protocol(self.get_current_params()))}", fg='#69db7c')

    def export_current_report(self) -> None:
        from export import export_report
        p = self.get_current_params(); img, m = self.simulate_with_params(p)
        self.compare_status.config(text=f"Saved: {os.path.basename(export_report(img, p, m))}", fg='#69db7c')

    def load_protocol_file(self) -> None:
        from export import load_protocol
        fp, _ = QFileDialog.getOpenFileName(self, "Load Protocol",
                                            os.path.expanduser('~/mrisim/exports'),
                                            "JSON (*.json);;All Files (*.*)")
        if not fp:
            return
        try:
            p = load_protocol(fp)
            for k, v in [("sequence", self.sequence_type), ("TR", self.TR), ("TE", self.TE), ("TI", self.TI),
                         ("flip_angle", self.flip_angle), ("matrix_size", self.matrix_size), ("FOV", self.FOV),
                         ("fov_fraction", self.fov_fraction), ("bandwidth", self.bandwidth), ("NEX", self.NEX),
                         ("b_value", self.b_value), ("diff_direction", self.diff_direction), ("diff_display", self.diff_display),
                         ("angio_type", self.angio_type), ("angio_mip_slab", self.angio_mip_slab),
                         ("fmri_display", self.fmri_display), ("fmri_volumes", self.fmri_volumes), ("fmri_threshold", self.fmri_threshold)]:
                if k in p:
                    v.set(p[k])
            self.compare_status.config(text=f"Loaded: {os.path.basename(fp)}", fg='#69db7c'); self.on_sequence_change()
        except Exception as e:
            self.compare_status.config(text=f"Error: {str(e)[:30]}", fg='#ff6b6b')
