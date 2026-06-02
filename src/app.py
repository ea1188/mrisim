from typing import Any
import numpy as np
import os
from psd import draw_psd
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import tkinter as tk
from tkinter import ttk

from signal_engine import spin_echo_signal, gradient_echo_signal
from phantom3d import get_slice, simulate_slice, TISSUE_PROPERTIES_3D
from kspace import simulate_acquisition, get_kspace_display
from brainweb_loader import get_brainweb_or_synthetic
from phantom3d_extended import (add_vessels_3d, add_activation_3d,
                                simulate_diffusion_3d_slice, simulate_adc_map_3d, simulate_fa_map_3d,
                                simulate_tof_3d_slice, simulate_fmri_3d_slice,
                                compute_activation_map_3d, compute_tstat_map_3d,
                                get_diffusion_properties_3d, load_real_tof_mra, simulate_tof_with_real_data)
from presets import get_preset_names, get_preset, estimate_sar
from artifacts import (add_motion_artifact, add_chemical_shift_artifact,
                       add_susceptibility_artifact, add_zipper_artifact,
                       calculate_chemical_shift_pixels)
from fse import simulate_fse_image, compute_fse_echo_train
from acceleration import apply_parallel_imaging, apply_compressed_sensing

class MRISimulator:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("MRI Simulation Platform")
        self.root.geometry("1400x850")
        self.root.configure(bg='#1e1e1e')
        
        print("Loading 3D phantom...")
        self.phantom_3d, self.phantom_source = get_brainweb_or_synthetic()
        self.phantom_3d_vessels = add_vessels_3d(self.phantom_3d)
        self.activation_3d = add_activation_3d(self.phantom_3d)
        self.real_tof = load_real_tof_mra()
        print(f"Ready. ({self.phantom_source})")
        
        self.sequence_type = tk.StringVar(value="Spin Echo")
        self.preset_name = tk.StringVar(value="")
        self.TR = tk.DoubleVar(value=500)
        self.TE = tk.DoubleVar(value=15)
        self.TI = tk.DoubleVar(value=150)
        self.flip_angle = tk.DoubleVar(value=90)
        self.NEX = tk.IntVar(value=1)
        self.matrix_size = tk.IntVar(value=256)
        self.FOV = tk.DoubleVar(value=240)
        self.fov_fraction = tk.DoubleVar(value=100)
        self.bandwidth = tk.DoubleVar(value=125)
        self.snr_level = tk.DoubleVar(value=35)
        self.show_kspace = tk.BooleanVar(value=False)
        self.slice_thickness = tk.DoubleVar(value=5)
        self.multi_slice = tk.BooleanVar(value=False)
        self.show_psd = tk.BooleanVar(value=False)
        
        self.orientation = tk.StringVar(value="axial")
        self.slice_idx = tk.IntVar(value=90)
        
        # FSE
        self.etl = tk.IntVar(value=1)
        self.echo_spacing = tk.DoubleVar(value=10)
        
        # Acceleration
        self.accel_factor = tk.IntVar(value=1)
        self.accel_method = tk.StringVar(value="SENSE")
        
        # Diffusion
        self.b_value = tk.DoubleVar(value=1000)
        self.diff_direction = tk.StringVar(value="Left-Right")
        self.diff_display = tk.StringVar(value="DWI")
        
        # MRA
        self.angio_type = tk.StringVar(value="TOF")
        self.angio_mip_slab = tk.IntVar(value=20)
        self.venc = tk.DoubleVar(value=80)
        self.flow_velocity = tk.DoubleVar(value=60)
        self.angio_display = tk.StringVar(value="Magnitude")
        
        # fMRI
        self.fmri_display = tk.StringVar(value="EPI Image")
        self.fmri_volumes = tk.IntVar(value=100)
        self.fmri_threshold = tk.DoubleVar(value=3.0)
        
        # Artifacts
        self.motion_enabled = tk.BooleanVar(value=False)
        self.motion_amplitude = tk.DoubleVar(value=3)
        self.motion_type = tk.StringVar(value="periodic")
        self.chemical_shift_enabled = tk.BooleanVar(value=False)
        self.susceptibility_enabled = tk.BooleanVar(value=False)
        self.susceptibility_strength = tk.DoubleVar(value=3)
        self.zipper_enabled = tk.BooleanVar(value=False)
        
        # Comparison
        self.compare_mode = tk.BooleanVar(value=False)
        self.compare_params: dict | None = None
        self._recalc_job: str | None = None
        
        # Window/level
        self.window_width = 1.0
        self.window_level = 0.5
        self.current_image: np.ndarray | None = None
        self.current_title = ""
        self.wl_dragging = False
        self.wl_start_x = 0
        self.wl_start_y = 0
        
        self.build_ui()
    
    def build_ui(self) -> None:
        self.left_panel = tk.Frame(self.root, bg='#2d2d2d', width=280)
        self.left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=2, pady=2)
        self.left_panel.pack_propagate(False)
        self.center_panel = tk.Frame(self.root, bg='#1e1e1e')
        self.center_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2, pady=2)
        self.right_panel = tk.Frame(self.root, bg='#2d2d2d', width=250)
        self.right_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=2, pady=2)
        self.right_panel.pack_propagate(False)
        self.build_image_display()
        self.build_metrics_panel()
        self.build_controls()
        self.recalculate()
    
    def build_image_display(self) -> None:
    # Main image figure (left side of center)
        self.img_frame = tk.Frame(self.center_panel, bg='#1e1e1e')
        self.img_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.fig, self.axes = plt.subplots(1, 2, figsize=(10, 5), facecolor='#1e1e1e')
        self.fig.subplots_adjust(wspace=0.3)
        for ax in self.axes: ax.set_facecolor('#1e1e1e')
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.img_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # PSD figure (conditionally shown)
        self.psd_frame = tk.Frame(self.center_panel, bg='#1e1e1e')
        self.psd_fig = plt.figure(figsize=(4, 5), facecolor='#1e1e1e')
        self.psd_canvas = FigureCanvasTkAgg(self.psd_fig, master=self.psd_frame)
        self.psd_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # Mouse bindings for W/L
        img_widget = self.canvas.get_tk_widget()
        img_widget.bind("<Button-2>", self.wl_mouse_down)
        img_widget.bind("<B2-Motion>", self.wl_mouse_drag)
        img_widget.bind("<ButtonRelease-2>", self.wl_mouse_up)
        img_widget.bind("<Button-3>", self.wl_mouse_down)
        img_widget.bind("<B3-Motion>", self.wl_mouse_drag)
        img_widget.bind("<ButtonRelease-3>", self.wl_mouse_up)
        img_widget.bind("<Control-Button-1>", self.wl_mouse_down)
        img_widget.bind("<Control-B1-Motion>", self.wl_mouse_drag)
        img_widget.bind("<Control-ButtonRelease-1>", self.wl_mouse_up)
        img_widget.bind("<Double-Button-1>", self.wl_reset)
    
    def _ensure_1x2_layout(self) -> None:
        """Restore the normal 1x2 subplot layout if the figure has a different configuration."""
        if len(self.fig.axes) != 2:
            self.fig.clear()
            self.axes = self.fig.subplots(1, 2)
            self.fig.subplots_adjust(wspace=0.3)
            for ax in self.axes:
                ax.set_facecolor('#1e1e1e')
    
    def wl_mouse_down(self, event: object) -> None:
        self.wl_dragging = True; self.wl_start_x = event.x; self.wl_start_y = event.y  # type: ignore[attr-defined]
    def wl_mouse_drag(self, event: object) -> None:
        if not self.wl_dragging or self.current_image is None: return
        self.window_width += (event.x - self.wl_start_x) * 0.005  # type: ignore[attr-defined]
        self.window_level -= (event.y - self.wl_start_y) * 0.003  # type: ignore[attr-defined]
        self.window_width = np.clip(self.window_width, 0.05, 3.0)
        self.window_level = np.clip(self.window_level, 0.0, 1.0)
        self.wl_start_x = event.x; self.wl_start_y = event.y  # type: ignore[attr-defined]
        self.apply_window_level()
    def wl_mouse_up(self, event: object) -> None: self.wl_dragging = False
    def wl_reset(self, event: object) -> None:
        self.window_width = 1.0; self.window_level = 0.5
        if self.current_image is not None: self.apply_window_level()
    def apply_window_level(self) -> None:
        if self.current_image is None: return
        img = self.current_image
        max_val = np.max(img) if np.max(img) > 0 else 1
        center = self.window_level * max_val; width = self.window_width * max_val
        self.axes[0].clear()
        self.axes[0].imshow(img, cmap='gray', origin='lower', vmin=center-width/2, vmax=center+width/2)
        self.axes[0].set_title(self.current_title, color='white', fontsize=10); self.axes[0].set_axis_off()
        self.axes[0].text(0.02, 0.02, f"W:{width:.3f} L:{center:.3f}", transform=self.axes[0].transAxes, color='yellow', fontsize=8, va='bottom')
        self.canvas.draw()
    
    def build_controls(self) -> None:
        ctrl_canvas = tk.Canvas(self.left_panel, bg='#2d2d2d', highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.left_panel, orient="vertical", command=ctrl_canvas.yview)
        self.scroll_frame = tk.Frame(ctrl_canvas, bg='#2d2d2d')
        self.scroll_frame.bind("<Configure>", lambda e: ctrl_canvas.configure(scrollregion=ctrl_canvas.bbox("all")))
        ctrl_canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw", width=270)
        ctrl_canvas.configure(yscrollcommand=scrollbar.set)
        ctrl_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        ctrl_canvas.bind_all("<MouseWheel>", lambda e: ctrl_canvas.yview_scroll(int(-1*e.delta), "units"))
        
        tk.Label(self.scroll_frame, text="MRI Simulator", font=('Helvetica', 14, 'bold'), bg='#2d2d2d', fg='white').pack(pady=(10,5))
        self.add_dropdown("Preset", self.preset_name, ["(Custom)"] + get_preset_names(), self.on_preset_change)
        self.add_dropdown("Sequence", self.sequence_type,
                         ["Spin Echo", "FSE / TSE", "Gradient Echo", "Inversion Recovery",
                          "Diffusion (DWI)", "MR Angiography", "fMRI (BOLD)"], self.on_sequence_change)
        self.desc_label = tk.Label(self.scroll_frame, text="", font=('Helvetica', 8), bg='#2d2d2d', fg='#888888', wraplength=250, justify='left')
        self.desc_label.pack(fill=tk.X, padx=10, pady=2)
        
        ttk.Separator(self.scroll_frame, orient='horizontal').pack(fill=tk.X, padx=10, pady=5)
        tk.Label(self.scroll_frame, text="Comparison", font=('Helvetica', 11, 'bold'), bg='#2d2d2d', fg='#aaaaaa').pack(anchor='w', padx=10)
        cf = tk.Frame(self.scroll_frame, bg='#2d2d2d'); cf.pack(fill=tk.X, padx=10, pady=2)
        tk.Button(cf, text="Set as A", command=self.set_protocol_a, bg='#4a9eff', fg='black', font=('Helvetica',9,'bold'), highlightbackground='#4a9eff', padx=8, pady=3).pack(side=tk.LEFT, padx=2)
        tk.Button(cf, text="Compare A↔B", command=self.toggle_compare, bg='#666666', fg='black', font=('Helvetica',9,'bold'), highlightbackground='#666666', padx=8, pady=3).pack(side=tk.LEFT, padx=2)
        tk.Button(cf, text="Clear", command=self.clear_compare, bg='#666666', fg='black', font=('Helvetica',9), highlightbackground='#666666', padx=8, pady=3).pack(side=tk.LEFT, padx=2)
        self.compare_status = tk.Label(self.scroll_frame, text="No comparison set", font=('Helvetica', 8), bg='#2d2d2d', fg='#666666')
        self.compare_status.pack(anchor='w', padx=10, pady=2)
        
        ttk.Separator(self.scroll_frame, orient='horizontal').pack(fill=tk.X, padx=10, pady=5)
        tk.Label(self.scroll_frame, text="3D Navigation", font=('Helvetica', 11, 'bold'), bg='#2d2d2d', fg='#aaaaaa').pack(anchor='w', padx=10)
        of = tk.Frame(self.scroll_frame, bg='#2d2d2d'); of.pack(fill=tk.X, padx=10, pady=2)
        for orient, label in [("axial","Ax"),("sagittal","Sag"),("coronal","Cor")]:
            tk.Radiobutton(of, text=label, variable=self.orientation, value=orient, bg='#2d2d2d', fg='white', selectcolor='#555555', command=self.on_orientation_change).pack(side=tk.LEFT, padx=5)
        self.add_slider("Slice", self.slice_idx, 0, 180)
        tk.Checkbutton(self.scroll_frame, text="Multi-slice (3x3 grid)", variable=self.multi_slice,
                      bg='#2d2d2d', fg='white', selectcolor='#555555', command=self.schedule_recalculate).pack(anchor='w', padx=10, pady=2)
        
        ttk.Separator(self.scroll_frame, orient='horizontal').pack(fill=tk.X, padx=10, pady=5)
        tk.Label(self.scroll_frame, text="Timing", font=('Helvetica', 11, 'bold'), bg='#2d2d2d', fg='#aaaaaa').pack(anchor='w', padx=10)
        self.tr_slider = self.add_slider("TR (ms)", self.TR, 50, 10000)
        self.te_slider = self.add_slider("TE (ms)", self.TE, 5, 300)
        self.ti_frame = self.add_slider("TI (ms)", self.TI, 50, 4000)
        self.fa_frame = self.add_slider("Flip Angle", self.flip_angle, 1, 90)
        
        # FSE controls
        self.fse_frame = tk.Frame(self.scroll_frame, bg='#2d2d2d')
        self.add_slider_to_frame(self.fse_frame, "Echo Train Length", self.etl, 1, 32)
        self.add_slider_to_frame(self.fse_frame, "Echo Spacing (ms)", self.echo_spacing, 5, 20)
        
        self.diff_frame = tk.Frame(self.scroll_frame, bg='#2d2d2d')
        self.add_slider_to_frame(self.diff_frame, "b-value (s/mm²)", self.b_value, 0, 3000)
        self.add_dropdown_to_frame(self.diff_frame, "Direction", self.diff_direction, ["Left-Right", "Up-Down", "Diagonal"])
        self.add_dropdown_to_frame(self.diff_frame, "Display", self.diff_display, ["DWI", "ADC Map", "FA Map"])
        
        self.angio_frame = tk.Frame(self.scroll_frame, bg='#2d2d2d')
        self.add_dropdown_to_frame(self.angio_frame, "MRA Type", self.angio_type, ["TOF", "Phase Contrast"])
        self.add_slider_to_frame(self.angio_frame, "MIP Slab", self.angio_mip_slab, 1, 50)
        self.add_slider_to_frame(self.angio_frame, "VENC (cm/s)", self.venc, 10, 200)
        self.add_slider_to_frame(self.angio_frame, "Flow Velocity", self.flow_velocity, 10, 150)
        self.add_dropdown_to_frame(self.angio_frame, "Display", self.angio_display, ["Magnitude", "Phase", "Speed"])
        
        self.fmri_frame = tk.Frame(self.scroll_frame, bg='#2d2d2d')
        self.add_dropdown_to_frame(self.fmri_frame, "Display", self.fmri_display, ["EPI Image", "Activation Map", "T-statistic Map"])
        self.add_slider_to_frame(self.fmri_frame, "Num Volumes", self.fmri_volumes, 20, 500)
        self.add_slider_to_frame(self.fmri_frame, "T-threshold", self.fmri_threshold, 1, 8)
        
        ttk.Separator(self.scroll_frame, orient='horizontal').pack(fill=tk.X, padx=10, pady=5)
        tk.Label(self.scroll_frame, text="Spatial / Acquisition", font=('Helvetica', 11, 'bold'), bg='#2d2d2d', fg='#aaaaaa').pack(anchor='w', padx=10)
        self.add_slider("Matrix Size", self.matrix_size, 32, 256)
        self.add_slider("FOV Coverage (%)", self.fov_fraction, 50, 100)
        self.add_slider("FOV (mm)", self.FOV, 100, 500)
        self.add_slider("Slice Thickness (mm)", self.slice_thickness, 1, 15)
        self.add_slider("Bandwidth (kHz)", self.bandwidth, 10, 500)
        self.add_slider("NEX", self.NEX, 1, 8)
        self.add_slider("Acceleration (R)", self.accel_factor, 1, 4)
        self.add_dropdown_inline("Accel Method", self.accel_method, ["SENSE", "GRAPPA", "CS"])
        
        ttk.Separator(self.scroll_frame, orient='horizontal').pack(fill=tk.X, padx=10, pady=5)
        tk.Label(self.scroll_frame, text="Artifacts", font=('Helvetica', 11, 'bold'), bg='#2d2d2d', fg='#aaaaaa').pack(anchor='w', padx=10)
        tk.Checkbutton(self.scroll_frame, text="Motion (ghosting)", variable=self.motion_enabled, bg='#2d2d2d', fg='white', selectcolor='#555555', command=self.schedule_recalculate).pack(anchor='w', padx=10, pady=1)
        self.add_slider("Motion Amplitude", self.motion_amplitude, 1, 15)
        self.add_dropdown_inline("Motion Type", self.motion_type, ["periodic", "random", "linear"])
        tk.Checkbutton(self.scroll_frame, text="Chemical Shift", variable=self.chemical_shift_enabled, bg='#2d2d2d', fg='white', selectcolor='#555555', command=self.schedule_recalculate).pack(anchor='w', padx=10, pady=1)
        tk.Checkbutton(self.scroll_frame, text="Susceptibility", variable=self.susceptibility_enabled, bg='#2d2d2d', fg='white', selectcolor='#555555', command=self.schedule_recalculate).pack(anchor='w', padx=10, pady=1)
        self.add_slider("Susceptibility Strength", self.susceptibility_strength, 1, 10)
        tk.Checkbutton(self.scroll_frame, text="Zipper (RF leak)", variable=self.zipper_enabled, bg='#2d2d2d', fg='white', selectcolor='#555555', command=self.schedule_recalculate).pack(anchor='w', padx=10, pady=1)
        
        ttk.Separator(self.scroll_frame, orient='horizontal').pack(fill=tk.X, padx=10, pady=5)
        tk.Label(self.scroll_frame, text="Display", font=('Helvetica', 11, 'bold'), bg='#2d2d2d', fg='#aaaaaa').pack(anchor='w', padx=10)
        self.add_slider("Noise Level (SNR)", self.snr_level, 5, 100)
        tk.Checkbutton(self.scroll_frame, text="Show k-space", variable=self.show_kspace, bg='#2d2d2d', fg='white', selectcolor='#555555', command=self.schedule_recalculate).pack(anchor='w', padx=10, pady=5)
        tk.Label(self.scroll_frame, text="W/L: Ctrl+drag | Reset: double-click", font=('Helvetica', 8), bg='#2d2d2d', fg='#666666').pack(anchor='w', padx=10)
        
        tk.Checkbutton(self.scroll_frame, text="Show Pulse Sequence Diagram", variable=self.show_psd,
              bg='#2d2d2d', fg='white', selectcolor='#555555',
              command=self.schedule_recalculate).pack(anchor='w', padx=10, pady=2)

        ef = tk.Frame(self.scroll_frame, bg='#2d2d2d'); ef.pack(fill=tk.X, padx=10, pady=5)
        tk.Button(ef, text="Save Img", command=self.export_current_image, bg='#666666', fg='black', font=('Helvetica',9), highlightbackground='#666666', padx=6, pady=3).pack(side=tk.LEFT, padx=2)
        tk.Button(ef, text="Save Proto", command=self.export_current_protocol, bg='#666666', fg='black', font=('Helvetica',9), highlightbackground='#666666', padx=6, pady=3).pack(side=tk.LEFT, padx=2)
        tk.Button(ef, text="PDF", command=self.export_current_report, bg='#666666', fg='black', font=('Helvetica',9), highlightbackground='#666666', padx=6, pady=3).pack(side=tk.LEFT, padx=2)
        tk.Button(ef, text="Load", command=self.load_protocol_file, bg='#666666', fg='black', font=('Helvetica',9), highlightbackground='#666666', padx=6, pady=3).pack(side=tk.LEFT, padx=2)
        
        self.on_sequence_change()
    
    def build_metrics_panel(self) -> None:
        tk.Label(self.right_panel, text="Metrics", font=('Helvetica', 14, 'bold'), bg='#2d2d2d', fg='white').pack(pady=(10,5))
        self.metrics_labels = {}
        for dn, key in [("Scan Time","scan_time"),("Resolution","resolution"),("Voxel Size","voxel_size"),
                        ("SNR (WM)","snr_wm"),("SNR (GM)","snr_gm"),("CNR","cnr"),("BW/pixel","bw_pixel"),
                        ("SAR (W/kg)","sar"),("Weighting","weighting"),("Matrix","matrix_display"),
                        ("Slice","slice_info"),("ETL / Accel","etl_accel"),("Artifacts","artifacts")]:
            f = tk.Frame(self.right_panel, bg='#2d2d2d'); f.pack(fill=tk.X, padx=10, pady=3)
            tk.Label(f, text=dn, font=('Helvetica',10), bg='#2d2d2d', fg='#aaaaaa').pack(anchor='w')
            l = tk.Label(f, text="--", font=('Helvetica',13,'bold'), bg='#2d2d2d', fg='#4a9eff'); l.pack(anchor='w')
            self.metrics_labels[key] = l
        ttk.Separator(self.right_panel, orient='horizontal').pack(fill=tk.X, padx=10, pady=5)
        self.compare_metrics_label = tk.Label(self.right_panel, text="", font=('Helvetica', 9), bg='#2d2d2d', fg='#aaaaaa', justify='left')
        self.compare_metrics_label.pack(fill=tk.X, padx=10, pady=2)
    
    # --- Core ---
    def get_current_params(self) -> dict:
        return {"sequence":self.sequence_type.get(),"TR":self.TR.get(),"TE":self.TE.get(),"TI":self.TI.get(),
                "flip_angle":self.flip_angle.get(),"matrix_size":self.matrix_size.get(),"FOV":self.FOV.get(),
                "fov_fraction":self.fov_fraction.get(),"bandwidth":self.bandwidth.get(),"NEX":self.NEX.get(),
                "etl":self.etl.get(),"echo_spacing":self.echo_spacing.get(),"accel_factor":self.accel_factor.get(),
                "accel_method":self.accel_method.get(),"b_value":self.b_value.get(),
                "diff_direction":self.diff_direction.get(),"diff_display":self.diff_display.get(),
                "angio_type":self.angio_type.get(),"angio_mip_slab":self.angio_mip_slab.get(),
                "fmri_display":self.fmri_display.get(),"fmri_volumes":self.fmri_volumes.get(),
                "fmri_threshold":self.fmri_threshold.get()}
    
    def set_protocol_a(self) -> None:
        self.compare_params = self.get_current_params()
        self.compare_status.config(text=f"A: {self.compare_params['sequence']} TR={self.compare_params['TR']:.0f}", fg='#4a9eff')
        self.compare_mode.set(True); self.recalculate()
    def toggle_compare(self) -> None:
        if not self.compare_params: self.compare_status.config(text="Set A first!", fg='#ff6b6b'); return
        self.compare_mode.set(not self.compare_mode.get()); self.recalculate()
    def clear_compare(self) -> None:
        self.compare_params = None; self.compare_mode.set(False)
        self.compare_status.config(text="No comparison set", fg='#666666')
        self.compare_metrics_label.config(text=""); self.recalculate()
    
    def _simulate_single_slice(self, params: dict, orient: str, sl_idx: int) -> np.ndarray:
        seq = params["sequence"]; TR=params["TR"]; TE=params["TE"]; TI=params["TI"]; FA=params["flip_angle"]
        if TE >= TR: TE = TR - 5
        phantom_slice = get_slice(self.phantom_3d, orient, sl_idx)
        
        if seq == "Spin Echo": return simulate_slice(phantom_slice, TR, TE, 'SE')
        elif seq == "FSE / TSE":
            return simulate_fse_image(phantom_slice, TR, TE, params["etl"], params["echo_spacing"], TISSUE_PROPERTIES_3D)
        elif seq == "Gradient Echo": return simulate_slice(phantom_slice, TR, TE, 'GRE', flip_angle=FA)
        elif seq == "Inversion Recovery": return simulate_slice(phantom_slice, TR, TE, 'IR', TI=TI)
        elif seq == "Diffusion (DWI)":
            direction: list[float] = {"Left-Right":[1.0,0.0],"Up-Down":[0.0,1.0],"Diagonal":[0.707,0.707]}[params["diff_direction"]]
            if params["diff_display"] == "DWI": return simulate_diffusion_3d_slice(phantom_slice, params["b_value"], direction, TR, TE)
            elif params["diff_display"] == "ADC Map": return simulate_adc_map_3d(phantom_slice)
            elif params["diff_display"] == "FA Map": return simulate_fa_map_3d(phantom_slice)
        elif seq == "MR Angiography":
            if self.real_tof is not None and params["angio_type"] == "TOF":
                return simulate_tof_with_real_data(self.real_tof, orient, sl_idx, TR, TE, FA, params["angio_mip_slab"])
            return simulate_tof_3d_slice(get_slice(self.phantom_3d_vessels, orient, sl_idx), TR, TE, FA)
        elif seq == "fMRI (BOLD)":
            act = get_slice(self.activation_3d, orient, sl_idx)
            if params["fmri_display"] == "EPI Image": return simulate_fmri_3d_slice(phantom_slice, act, TR, TE, FA, True)
            elif params["fmri_display"] == "Activation Map": return compute_activation_map_3d(phantom_slice, act, TR, TE, FA)
            elif params["fmri_display"] == "T-statistic Map":
                img = compute_tstat_map_3d(phantom_slice, act, TR, TE, FA, params["fmri_volumes"])
                return np.where(img > params["fmri_threshold"], img, 0)
        return np.zeros((181,181), dtype=float)
    
    def simulate_with_params(self, params: dict) -> tuple[np.ndarray, dict]:
        orient = self.orientation.get(); sl_idx = self.slice_idx.get()
        matrix = params["matrix_size"]; fov_frac = params["fov_fraction"]/100.0
        thickness = int(self.slice_thickness.get()); R = params["accel_factor"]
        max_sl = self.get_max_slice_idx()
        
        if thickness > 1 and params["sequence"] not in ["MR Angiography"]:
            start = max(0, sl_idx-thickness//2); end = min(max_sl, sl_idx+thickness//2)
            image = np.mean([self._simulate_single_slice(params, orient, s) for s in range(start, end+1)], axis=0)
        else:
            image = self._simulate_single_slice(params, orient, sl_idx)
        
        phantom_slice = get_slice(self.phantom_3d, orient, sl_idx)
        is_map = params["sequence"]=="Diffusion (DWI)" and params["diff_display"] in ["ADC Map","FA Map"]
        is_map = is_map or (params["sequence"]=="fMRI (BOLD)" and params["fmri_display"] in ["Activation Map","T-statistic Map"])
        
        if not is_map:
            if self.motion_enabled.get():
                image = add_motion_artifact(image, self.motion_type.get(), self.motion_amplitude.get(), 3)
            if self.chemical_shift_enabled.get() and phantom_slice.shape == image.shape:
                image = add_chemical_shift_artifact(image, phantom_slice, calculate_chemical_shift_pixels(params["bandwidth"]*1000/matrix))
            if self.susceptibility_enabled.get() and phantom_slice.shape == image.shape:
                image = add_susceptibility_artifact(image, phantom_slice, self.susceptibility_strength.get()/10.0)
            
            reconstructed, _ = simulate_acquisition(image, matrix, fov_frac)
            
            # Acceleration
            if R > 1:
                method = params["accel_method"]
                if method == "CS":
                    reconstructed = apply_compressed_sensing(reconstructed, R)
                else:
                    reconstructed, _ = apply_parallel_imaging(reconstructed, R, method)
            
            # Noise — FIX #2: use sqrt(R) * 1.2 penalty for more visible acceleration noise
            noise_penalty = np.sqrt(R) * 1.2 if R > 1 else 1.0
            snr = self.snr_level.get() * np.sqrt(thickness/5.0) / noise_penalty
            if snr < 100:
                max_sig = np.max(reconstructed)
                if max_sig > 0:
                    sigma = max_sig / snr
                    reconstructed = np.sqrt((reconstructed + np.random.normal(0,sigma,reconstructed.shape))**2 + np.random.normal(0,sigma,reconstructed.shape)**2)
            if self.zipper_enabled.get():
                reconstructed = add_zipper_artifact(reconstructed, 0.3, 0.12)
        else:
            reconstructed = image
        
        # Metrics
        TR, _TE, FA = params["TR"], params["TE"], params["flip_angle"]
        FOV, NEX, BW = params["FOV"], params["NEX"], params["bandwidth"]*1000
        ETL = params["etl"] if params["sequence"] == "FSE / TSE" else 1
        resolution = FOV/matrix; voxel_vol = resolution*resolution*thickness
        scan_time = TR * matrix * NEX / (ETL * R) / 1000
        seq_map = {"Spin Echo":"SE","FSE / TSE":"SE","Gradient Echo":"GRE","Inversion Recovery":"IR",
                   "Diffusion (DWI)":"Diffusion","MR Angiography":"GRE","fMRI (BOLD)":"EPI"}
        sar = estimate_sar(FA, TR, sequence=seq_map.get(params["sequence"],"SE"))
        metrics = {"scan_time":scan_time,"resolution":resolution,"snr_wm":0,"snr_gm":0,
                   "sar_head":sar["head"],"sar_exceeds":sar["exceeds_limit"]}
        if not is_map and phantom_slice.shape == reconstructed.shape:
            nf = np.sqrt(BW)/(voxel_vol*np.sqrt(NEX))
            wm = phantom_slice==3; gm = phantom_slice==2
            if np.any(wm): metrics["snr_wm"] = reconstructed[wm].mean()/nf*1000
            if np.any(gm): metrics["snr_gm"] = reconstructed[gm].mean()/nf*1000
        return reconstructed, metrics
    
    # --- Display ---
    def recalculate(self, *args: object) -> None:
        current_params = self.get_current_params()
        
        if self.multi_slice.get() and not self.compare_mode.get():
            self._display_multi_slice(current_params)
            return
        
        # FIX #1: Restore 1x2 layout if coming back from multi-slice 3x3 grid
        self._ensure_1x2_layout()
        
        image_b, metrics_b = self.simulate_with_params(current_params)
        self.axes[0].clear(); self.axes[1].clear()
        
        if self.compare_mode.get() and self.compare_params:
            image_a, metrics_a = self.simulate_with_params(self.compare_params)
            self.axes[0].imshow(image_a, cmap='gray', origin='lower')
            self.axes[0].set_title(f"A: {self.compare_params['sequence']} TR={self.compare_params['TR']:.0f}", color='white', fontsize=10); self.axes[0].set_axis_off()
            self.axes[1].imshow(image_b, cmap='gray', origin='lower')
            self.axes[1].set_title(f"B: {current_params['sequence']} TR={current_params['TR']:.0f}", color='white', fontsize=10); self.axes[1].set_axis_off()
            self.update_compare_metrics(metrics_a, metrics_b)
            self.current_image = None
        else:
            self.current_image = image_b
            orient = self.orientation.get(); sl_idx = self.slice_idx.get()
            self.current_title = f"{current_params['sequence']} | TR={current_params['TR']:.0f} TE={current_params['TE']:.0f} | {orient.capitalize()} #{sl_idx}"
            max_val = np.max(image_b) if np.max(image_b)>0 else 1
            center = self.window_level*max_val; width = self.window_width*max_val
            self.axes[0].imshow(image_b, cmap='gray', origin='lower', vmin=center-width/2, vmax=center+width/2)
            self.axes[0].set_title(self.current_title, color='white', fontsize=10); self.axes[0].set_axis_off()
            if self.show_kspace.get():
                from kspace import image_to_kspace
                self.axes[1].imshow(get_kspace_display(image_to_kspace(image_b)), cmap='hot', origin='lower')
                self.axes[1].set_title("k-Space", color='white', fontsize=11); self.axes[1].set_axis_off()
            else:
                self._plot_curves(current_params)
            self.compare_metrics_label.config(text="")
            # PSD display
        if self.show_psd.get():
            self.psd_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
            draw_psd(self.psd_fig,
                    current_params["sequence"],
                    current_params["TR"],
                    current_params["TE"],
                    TI=current_params["TI"],
                    flip_angle=current_params["flip_angle"],
                    etl=current_params["etl"],
                    echo_spacing=current_params["echo_spacing"],
                    b_value=current_params["b_value"])
            self.psd_canvas.draw()
        else:
            self.psd_frame.pack_forget()
        self.canvas.draw()
        self.update_metrics(current_params, metrics_b)
    
    def _display_multi_slice(self, params: dict) -> None:
        """Display 3x3 grid of adjacent slices."""
        self.fig.clear()
        axes = self.fig.subplots(3, 3)
        self.fig.subplots_adjust(wspace=0.05, hspace=0.15)
        
        orient = self.orientation.get()
        center_sl = self.slice_idx.get()
        max_sl = self.get_max_slice_idx()
        spacing = max(1, int(self.slice_thickness.get()))
        
        for idx, ax in enumerate(axes.flat):
            ax.set_facecolor('#1e1e1e')
            sl = center_sl + (idx - 4) * spacing
            if 0 <= sl <= max_sl:
                # Quick simulation (no artifacts for speed)
                image = self._simulate_single_slice(params, orient, sl)
                ax.imshow(image, cmap='gray', origin='lower')
                ax.set_title(f"#{sl}", color='white', fontsize=8)
            ax.set_axis_off()
        
        self.canvas.draw()
        # Update metrics with center slice
        _, metrics = self.simulate_with_params(params)
        self.update_metrics(params, metrics)
        self.current_image = None
    
    def _plot_curves(self, params: dict) -> None:
        seq, TR, TE, TI, FA = params["sequence"], params["TR"], params["TE"], params["TI"], params["flip_angle"]
        from signal_engine import TISSUES
        if seq == "FSE / TSE":
            # Show echo train decay
            for tn, color, T1, T2, PD in [("WM",'#ff6b6b',830,80,0.65),("GM",'#69db7c',1330,100,0.8),("CSF",'#74c0fc',4500,2200,1.0)]:
                te_vals, sigs = compute_fse_echo_train(T1, T2, PD, TR, params["etl"], params["echo_spacing"])
                self.axes[1].plot(te_vals, sigs, color=color, linewidth=2, label=tn, marker='o', markersize=3)
            self.axes[1].axvline(x=TE, color='yellow', linestyle='--', alpha=0.7, label=f'TE_eff={TE:.0f}')
            self.axes[1].set_xlabel('Echo Time (ms)', color='white'); self.axes[1].set_title('Echo Train Decay', color='white', fontsize=11)
        elif seq == "Diffusion (DWI)":
            b_range = np.arange(0,3001,50); dp = get_diffusion_properties_3d(None)
            for name,color,label in [("WM",'#ff6b6b',3),("GM",'#69db7c',2),("CSF",'#74c0fc',1)]:
                props = TISSUES[name.lower().replace("wm","white_matter").replace("gm","gray_matter")]
                S0 = spin_echo_signal(props["T1"],props["T2"],props["PD"],TR,TE)
                self.axes[1].plot(b_range, S0*np.exp(-b_range*dp[label]["ADC"]*1e-3), color=color, linewidth=2, label=name)
            self.axes[1].axvline(x=params["b_value"], color='yellow', linestyle='--', alpha=0.7)
            self.axes[1].set_xlabel('b-value', color='white'); self.axes[1].set_title('Signal vs b-value', color='white', fontsize=11)
        elif seq == "MR Angiography":
            fa_range = np.arange(1,91,1)
            for name,color,T1,PD in [("Brain",'#69db7c',1330,0.8),("Blood",'#ff6b6b',1930,0.9)]:
                if "Blood" in name: self.axes[1].plot(fa_range, PD*np.sin(np.radians(fa_range))*np.exp(-TE/50), color=color, linewidth=2, label=name)
                else: self.axes[1].plot(fa_range, [gradient_echo_signal(T1,50,PD,TR,TE,float(fa)) for fa in fa_range], color=color, linewidth=2, label=name)
            self.axes[1].axvline(x=FA, color='yellow', linestyle='--', alpha=0.7)
            self.axes[1].set_xlabel('FA', color='white'); self.axes[1].set_title('TOF Signal', color='white', fontsize=11)
        elif seq == "fMRI (BOLD)":
            te_range = np.arange(5, 100, 1, dtype=float); bs = te_range*np.exp(-te_range/60); bs /= bs.max()
            self.axes[1].plot(te_range, bs, color='#ff6b6b', linewidth=2, label='BOLD')
            self.axes[1].plot(te_range, np.exp(-te_range/60), color='#69db7c', linewidth=2, label='Signal')
            self.axes[1].axvline(x=TE, color='yellow', linestyle='--', alpha=0.7)
            self.axes[1].set_xlabel('TE', color='white'); self.axes[1].set_title('BOLD Sensitivity', color='white', fontsize=11)
        else:
            te_range = np.arange(5, min(300,TR), 2)
            for tn,color in [("white_matter",'#ff6b6b'),("gray_matter",'#69db7c'),("csf",'#74c0fc')]:
                props = TISSUES[tn]
                if seq=="Spin Echo": sig=props["PD"]*(1-np.exp(-TR/props["T1"]))*np.exp(-te_range/props["T2"])
                elif seq=="Gradient Echo":
                    a=np.radians(FA);E1=np.exp(-TR/props["T1"])
                    sig=props["PD"]*np.sin(a)*(1-E1)/(1-np.cos(a)*E1)*np.exp(-te_range/(props["T2"]*0.6))
                else: sig=props["PD"]*np.abs(1-2*np.exp(-TI/props["T1"])+np.exp(-TR/props["T1"]))*np.exp(-te_range/props["T2"])
                self.axes[1].plot(te_range, sig, color=color, linewidth=2, label=tn.replace("_"," ").title())
            self.axes[1].axvline(x=TE, color='yellow', linestyle='--', alpha=0.7)
            self.axes[1].set_xlabel('TE (ms)', color='white'); self.axes[1].set_title('Signal vs TE', color='white', fontsize=11)
        self.axes[1].set_ylabel('Signal', color='white')
        self.axes[1].legend(fontsize=8, facecolor='#2d2d2d', labelcolor='white')
        self.axes[1].tick_params(colors='white'); self.axes[1].set_facecolor('#1e1e1e')
    
    def update_compare_metrics(self, ma: dict, mb: dict) -> None:
        def d(a: float, b: float, u: str = "", f: str = ".1f") -> str:
            diff=b-a; pct=(diff/a*100) if a!=0 else 0
            return f"{'↑' if diff>0 else '↓' if diff<0 else '='} {abs(diff):{f}}{u} ({abs(pct):.0f}%)"
        text = f"── A vs B ──\nTime: {d(ma['scan_time'],mb['scan_time'],'s')}\nSNR: {d(ma['snr_wm'],mb['snr_wm'])}\n"
        text += f"Res: {d(ma['resolution'],mb['resolution'],'mm','.2f')}\nSAR: A={ma['sar_head']:.1f} B={mb['sar_head']:.1f}"
        self.compare_metrics_label.config(text=text, fg='#ffcc00')
    
    def update_metrics(self, params: dict, metrics: dict) -> None:
        orient=self.orientation.get(); sl_idx=self.slice_idx.get()
        matrix=params["matrix_size"]; thickness=int(self.slice_thickness.get())
        R=params["accel_factor"]; ETL=params["etl"] if params["sequence"]=="FSE / TSE" else 1
        resolution=metrics["resolution"]
        self.metrics_labels["resolution"].config(text=f"{resolution:.2f} mm")
        self.metrics_labels["voxel_size"].config(text=f"{resolution:.2f}x{resolution:.2f}x{thickness}mm")
        self.metrics_labels["matrix_display"].config(text=f"{matrix}x{matrix}")
        self.metrics_labels["slice_info"].config(text=f"{orient.capitalize()} #{sl_idx}")
        st=metrics["scan_time"]; self.metrics_labels["scan_time"].config(text=f"{int(st//60)}:{int(st%60):02d}")
        self.metrics_labels["bw_pixel"].config(text=f"{params['bandwidth']*1000/matrix:.1f}")
        self.metrics_labels["snr_wm"].config(text=f"{metrics['snr_wm']:.1f}")
        self.metrics_labels["snr_gm"].config(text=f"{metrics['snr_gm']:.1f}")
        self.metrics_labels["cnr"].config(text=f"{abs(metrics['snr_wm']-metrics['snr_gm']):.1f}")
        self.metrics_labels["sar"].config(text=f"{metrics['sar_head']:.1f}"+(" ⚠️" if metrics['sar_exceeds'] else ""),
                                          fg='#ff6b6b' if metrics['sar_exceeds'] else '#4a9eff')
        self.metrics_labels["weighting"].config(text=self.determine_weighting(params["TR"],params["TE"],params["sequence"]))
        etl_text = f"ETL={ETL}" if ETL > 1 else ""; accel_text = f"R={R}" if R > 1 else ""
        self.metrics_labels["etl_accel"].config(text=f"{etl_text} {accel_text}".strip() or "None")
        active = []
        if self.motion_enabled.get(): active.append("Motion")
        if self.chemical_shift_enabled.get(): active.append("ChemShift")
        if self.susceptibility_enabled.get(): active.append("Suscept.")
        if self.zipper_enabled.get(): active.append("Zipper")
        if params["fov_fraction"]<100: active.append("Aliasing")
        if matrix<128: active.append("Blur")
        if metrics['sar_exceeds']: active.append("SAR!")
        self.metrics_labels["artifacts"].config(text=", ".join(active) if active else "None", fg='#ff6b6b' if active else '#4a9eff')
    
    def determine_weighting(self, TR: float, TE: float, seq: str) -> str:
        if seq=="Diffusion (DWI)": return "Diffusion"
        if seq=="MR Angiography": return "Flow"
        if seq=="fMRI (BOLD)": return "T2* (BOLD)"
        if TR<800 and TE<30: return "T1-weighted"
        elif TR>2000 and TE>60: return "T2-weighted"
        elif TR>2000 and TE<30: return "PD-weighted"
        return "Mixed"
    
    # --- UI Helpers ---
    def on_preset_change(self) -> None:
        name=self.preset_name.get()
        if name in ["(Custom)",""]: self.desc_label.config(text=""); return
        p=get_preset(name)
        if not p: return
        self.sequence_type.set(p["sequence"]); self.TR.set(p["TR"]); self.TE.set(p["TE"])
        self.TI.set(p.get("TI",150)); self.flip_angle.set(p.get("flip_angle",90))
        self.matrix_size.set(p.get("matrix_size",256)); self.FOV.set(p.get("FOV",240))
        self.bandwidth.set(p.get("bandwidth",125)); self.NEX.set(p.get("NEX",1))
        for k,v in [("b_value",self.b_value),("diff_direction",self.diff_direction),("diff_display",self.diff_display),
                    ("angio_type",self.angio_type),("angio_mip_slab",self.angio_mip_slab),
                    ("fmri_display",self.fmri_display),("fmri_volumes",self.fmri_volumes),("fmri_threshold",self.fmri_threshold)]:
            if k in p: v.set(p[k])
        self.desc_label.config(text=p.get("description","")); self.on_sequence_change()
    
    def schedule_recalculate(self, *args: object) -> None:
        if self._recalc_job: self.root.after_cancel(self._recalc_job)
        self._recalc_job = self.root.after(150, self.recalculate)
    
    def add_slider(self, label: str, variable: Any, mn: float, mx: float) -> Any:
        f=tk.Frame(self.scroll_frame, bg='#2d2d2d'); f.pack(fill=tk.X, padx=10, pady=2)
        self._bsc(f, label, variable, mn, mx); return f
    def add_slider_to_frame(self, parent: Any, label: str, variable: Any, mn: float, mx: float) -> Any:
        f=tk.Frame(parent, bg='#2d2d2d'); f.pack(fill=tk.X, padx=0, pady=2)
        self._bsc(f, label, variable, mn, mx); return f
    def _bsc(self, frame: Any, label: str, variable: Any, mn: float, mx: float) -> None:
        h=tk.Frame(frame, bg='#2d2d2d'); h.pack(fill=tk.X)
        tk.Label(h, text=label, font=('Helvetica',9), bg='#2d2d2d', fg='#cccccc').pack(side=tk.LEFT)
        vl=tk.Label(h, text=str(variable.get()), font=('Helvetica',9,'bold'), bg='#2d2d2d', fg='white'); vl.pack(side=tk.RIGHT)
        tk.Scale(frame, from_=mn, to=mx, orient=tk.HORIZONTAL, variable=variable, showvalue=False, bg='#2d2d2d', fg='white', highlightthickness=0, troughcolor='#555555', length=200, command=lambda v: self.schedule_recalculate()).pack(fill=tk.X)
        def ul(*a: object) -> None: vl.config(text=f"{variable.get():.0f}" if isinstance(variable.get(),float) else str(variable.get()))
        variable.trace_add('write', ul)
    def add_dropdown(self, label: str, variable: Any, options: list, command: Any) -> None:
        f=tk.Frame(self.scroll_frame, bg='#2d2d2d'); f.pack(fill=tk.X, padx=10, pady=5)
        tk.Label(f, text=label, font=('Helvetica',9), bg='#2d2d2d', fg='#cccccc').pack(anchor='w')
        d=ttk.Combobox(f, textvariable=variable, values=options, state='readonly'); d.pack(fill=tk.X)
        d.bind('<<ComboboxSelected>>', lambda e: command())
    def add_dropdown_to_frame(self, parent: Any, label: str, variable: Any, options: list) -> None:
        f=tk.Frame(parent, bg='#2d2d2d'); f.pack(fill=tk.X, padx=0, pady=2)
        tk.Label(f, text=label, font=('Helvetica',9), bg='#2d2d2d', fg='#cccccc').pack(anchor='w')
        d=ttk.Combobox(f, textvariable=variable, values=options, state='readonly'); d.pack(fill=tk.X)
        d.bind('<<ComboboxSelected>>', lambda e: self.schedule_recalculate())
    def add_dropdown_inline(self, label: str, variable: Any, options: list) -> None:
        f=tk.Frame(self.scroll_frame, bg='#2d2d2d'); f.pack(fill=tk.X, padx=10, pady=2)
        tk.Label(f, text=label, font=('Helvetica',9), bg='#2d2d2d', fg='#cccccc').pack(side=tk.LEFT)
        d=ttk.Combobox(f, textvariable=variable, values=options, state='readonly', width=10); d.pack(side=tk.RIGHT)
        d.bind('<<ComboboxSelected>>', lambda e: self.schedule_recalculate())
    
    def on_orientation_change(self) -> None:
        dims={"axial":self.phantom_3d.shape[0],"sagittal":self.phantom_3d.shape[2],"coronal":self.phantom_3d.shape[1]}
        self.slice_idx.set(dims[self.orientation.get()]//2); self.recalculate()
    def on_sequence_change(self) -> None:
        seq=self.sequence_type.get()
        self.ti_frame.pack_forget(); self.fa_frame.pack_forget(); self.fse_frame.pack_forget()
        self.diff_frame.pack_forget(); self.angio_frame.pack_forget(); self.fmri_frame.pack_forget()
        if seq=="Inversion Recovery": self.ti_frame.pack(fill=tk.X, padx=10, pady=2)
        elif seq=="Gradient Echo": self.fa_frame.pack(fill=tk.X, padx=10, pady=2)
        elif seq=="FSE / TSE": self.fse_frame.pack(fill=tk.X, padx=10, pady=2); self.TR.set(4000); self.TE.set(80); self.etl.set(16)
        elif seq=="Diffusion (DWI)": self.diff_frame.pack(fill=tk.X, padx=10, pady=2)
        elif seq=="MR Angiography": self.angio_frame.pack(fill=tk.X, padx=10, pady=2); self.fa_frame.pack(fill=tk.X, padx=10, pady=2)
        elif seq=="fMRI (BOLD)": self.fmri_frame.pack(fill=tk.X, padx=10, pady=2)
        self.recalculate()
    def get_max_slice_idx(self) -> int:
        dims={"axial":self.phantom_3d.shape[0],"sagittal":self.phantom_3d.shape[2],"coronal":self.phantom_3d.shape[1]}
        return dims[self.orientation.get()]-1
    
    # --- Export/Import ---
    def export_current_image(self) -> None:
        from export import export_image
        img,_=self.simulate_with_params(self.get_current_params())
        self.compare_status.config(text=f"Saved: {os.path.basename(export_image(img, params=self.get_current_params()))}", fg='#69db7c')
    def export_current_protocol(self) -> None:
        from export import export_protocol
        self.compare_status.config(text=f"Saved: {os.path.basename(export_protocol(self.get_current_params()))}", fg='#69db7c')
    def export_current_report(self) -> None:
        from export import export_report
        p=self.get_current_params(); img,m=self.simulate_with_params(p)
        self.compare_status.config(text=f"Saved: {os.path.basename(export_report(img,p,m))}", fg='#69db7c')
    def load_protocol_file(self) -> None:
        from tkinter import filedialog; from export import load_protocol
        fp=filedialog.askopenfilename(initialdir=os.path.expanduser('~/mrisim/exports'), filetypes=[("JSON","*.json"),("All","*.*")])
        if not fp: return
        try:
            p=load_protocol(fp)
            for k,v in [("sequence",self.sequence_type),("TR",self.TR),("TE",self.TE),("TI",self.TI),
                        ("flip_angle",self.flip_angle),("matrix_size",self.matrix_size),("FOV",self.FOV),
                        ("fov_fraction",self.fov_fraction),("bandwidth",self.bandwidth),("NEX",self.NEX),
                        ("b_value",self.b_value),("diff_direction",self.diff_direction),("diff_display",self.diff_display),
                        ("angio_type",self.angio_type),("angio_mip_slab",self.angio_mip_slab),
                        ("fmri_display",self.fmri_display),("fmri_volumes",self.fmri_volumes),("fmri_threshold",self.fmri_threshold)]:
                if k in p: v.set(p[k])
            self.compare_status.config(text=f"Loaded: {os.path.basename(fp)}", fg='#69db7c'); self.on_sequence_change()
        except Exception as e: self.compare_status.config(text=f"Error: {str(e)[:30]}", fg='#ff6b6b')
    
    def run(self) -> None: self.root.mainloop()

if __name__ == "__main__":
    app = MRISimulator()
    app.run()