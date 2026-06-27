import numpy as np
import json
import os
from datetime import datetime

EXPORT_DIR = os.path.expanduser('~/mrisim/exports')

def ensure_export_dir() -> str:
    os.makedirs(EXPORT_DIR, exist_ok=True)
    return EXPORT_DIR

def export_image(
    image: np.ndarray,
    filename: str | None = None,
    params: dict | None = None,
) -> str:
    """Save simulated image as PNG."""
    import matplotlib.pyplot as plt
    
    export_dir = ensure_export_dir()
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"mri_sim_{timestamp}.png"
    
    filepath = os.path.join(export_dir, filename)
    
    fig, ax = plt.subplots(1, 1, figsize=(8, 8), facecolor='black')
    ax.imshow(image, cmap='gray', origin='lower')
    ax.set_axis_off()
    
    if params:
        title = f"{params.get('sequence', '')} | TR={params.get('TR', 0):.0f} TE={params.get('TE', 0):.0f}"
        ax.set_title(title, color='white', fontsize=12)
    
    # Add watermark
    fig.text(0.5, 0.02, "SIMULATED - Not for clinical use", ha='center',
             color='#666666', fontsize=8, style='italic')
    
    plt.savefig(filepath, dpi=150, bbox_inches='tight', facecolor='black')
    plt.close(fig)

    return filepath

def export_dicom(
    image: np.ndarray,
    params: dict | None = None,
    filename: str | None = None,
) -> str:
    """Save the simulated image as a DICOM (.dcm) file, carrying the acquisition
    parameters (TR/TE/TI/flip, sequence, field strength, geometry) so it loads in any
    DICOM viewer / PACS. Uses the tested dicom_export module."""
    import dicom_export

    export_dir = ensure_export_dir()
    if filename is None:
        filename = f"mri_sim_{datetime.now().strftime('%Y%m%d_%H%M%S')}.dcm"
    filepath = os.path.join(export_dir, filename)

    p = params or {}
    matrix = float(p.get("matrix_size", image.shape[0]) or image.shape[0])
    fov_mm = float(p.get("FOV", 240) or 240)
    field = str(p.get("field_strength", "3T")).rstrip("T") or "3"
    ps = fov_mm / matrix if matrix else 1.0
    return dicom_export.image_to_dicom(
        image, filepath,
        TR_ms=float(p.get("TR", 0) or 0), TE_ms=float(p.get("TE", 0) or 0),
        TI_ms=float(p.get("TI", 0) or 0), flip_angle_deg=float(p.get("flip_angle", 0) or 0),
        sequence=str(p.get("sequence", "")), field_strength_T=float(field),
        pixel_spacing_mm=(ps, ps),
        slice_thickness_mm=float(p.get("slice_thickness", 5) or 5))

def export_protocol(params: dict, filename: str | None = None) -> str:
    """Save protocol parameters as JSON."""
    export_dir = ensure_export_dir()
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"protocol_{timestamp}.json"
    
    filepath = os.path.join(export_dir, filename)
    
    protocol = {
        "exported_at": datetime.now().isoformat(),
        "software": "MRI Simulation Platform",
        "disclaimer": "SIMULATED - Not for clinical use",
        "parameters": params,
    }
    
    with open(filepath, 'w') as f:
        json.dump(protocol, f, indent=2)
    
    return filepath

def load_protocol(filepath: str) -> dict:
    """Load protocol parameters from JSON."""
    with open(filepath, 'r') as f:
        data = json.load(f)
    return data.get("parameters", data)

def export_report(
    image: np.ndarray,
    params: dict,
    metrics: dict,
    filename: str | None = None,
) -> str:
    """Save a PDF-like report with image, parameters, and metrics."""
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    
    export_dir = ensure_export_dir()
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"report_{timestamp}.pdf"
    
    filepath = os.path.join(export_dir, filename)
    
    with PdfPages(filepath) as pdf:
        fig = plt.figure(figsize=(8.5, 11), facecolor='white')
        
        # Title
        fig.text(0.5, 0.95, "MRI Simulation Report", ha='center', fontsize=16, fontweight='bold')
        fig.text(0.5, 0.92, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", 
                ha='center', fontsize=9, color='gray')
        fig.text(0.5, 0.90, "SIMULATED - Not for clinical use", 
                ha='center', fontsize=8, color='red', style='italic')
        
        # Image
        ax_img = fig.add_axes((0.15, 0.45, 0.7, 0.4))
        ax_img.imshow(image, cmap='gray', origin='lower')
        ax_img.set_axis_off()
        ax_img.set_title(f"{params.get('sequence', '')} | TR={params.get('TR', 0):.0f}ms TE={params.get('TE', 0):.0f}ms",
                        fontsize=11)
        
        # Parameters table
        param_text = "Parameters:\n"
        param_text += f"  Sequence: {params.get('sequence', 'N/A')}\n"
        param_text += f"  TR: {params.get('TR', 0):.0f} ms\n"
        param_text += f"  TE: {params.get('TE', 0):.0f} ms\n"
        if params.get('sequence') == 'Inversion Recovery':
            param_text += f"  TI: {params.get('TI', 0):.0f} ms\n"
        param_text += f"  Flip Angle: {params.get('flip_angle', 90):.0f}°\n"
        param_text += f"  Matrix: {params.get('matrix_size', 256)} x {params.get('matrix_size', 256)}\n"
        param_text += f"  FOV: {params.get('FOV', 240):.0f} mm\n"
        param_text += f"  Bandwidth: {params.get('bandwidth', 125):.0f} kHz\n"
        param_text += f"  NEX: {params.get('NEX', 1)}\n"
        
        fig.text(0.15, 0.38, param_text, fontsize=9, family='monospace', verticalalignment='top')
        
        # Metrics
        metrics_text = "Metrics:\n"
        metrics_text += f"  Scan Time: {metrics.get('scan_time', 0):.0f} s\n"
        metrics_text += f"  Resolution: {metrics.get('resolution', 0):.2f} mm\n"
        metrics_text += f"  SNR (WM): {metrics.get('snr_wm', 0):.1f}\n"
        metrics_text += f"  SNR (GM): {metrics.get('snr_gm', 0):.1f}\n"
        metrics_text += f"  SAR (head): {metrics.get('sar_head', 0):.1f} W/kg\n"
        
        fig.text(0.55, 0.38, metrics_text, fontsize=9, family='monospace', verticalalignment='top')
        
        pdf.savefig(fig)
        plt.close(fig)
    
    return filepath

if __name__ == "__main__":
    # Test export
    test_image = np.random.rand(181, 181)
    test_params = {"sequence": "Spin Echo", "TR": 500, "TE": 15, "flip_angle": 90,
                   "matrix_size": 256, "FOV": 240, "bandwidth": 125, "NEX": 1}
    test_metrics = {"scan_time": 128, "resolution": 0.94, "snr_wm": 3.0, "snr_gm": 2.7, "sar_head": 1.5}
    
    path = export_image(test_image, params=test_params)
    print(f"Image saved: {path}")
    
    path = export_protocol(test_params)
    print(f"Protocol saved: {path}")
    
    path = export_report(test_image, test_params, test_metrics)
    print(f"Report saved: {path}")
    
    print(f"\nExport directory: {EXPORT_DIR}")
    print("Export module working.")