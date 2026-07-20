/* Pure, DOM-free physics for the course diagrams. Shared by course_diagrams.js
 * (browser) and the node unit test. No DOM, no globals beyond the export.
 * UMD: attaches window.CourseDiagramsMath in the browser, module.exports under node. */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.CourseDiagramsMath = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // Longitudinal magnetization recovered by time t (fraction of equilibrium).
  function mz(t, T1) { return 1 - Math.exp(-t / T1); }

  // Transverse magnetization remaining at time t (fraction of the post-90 peak).
  function mxy(t, T2) { return Math.exp(-t / T2); }

  // Effective transverse decay including static field inhomogeneity (T2prime).
  function t2star(T2, T2prime) { return 1 / (1 / T2 + 1 / T2prime); }

  // Spin-echo signal magnitude at time t: the irreversible T2 decay times the
  // reversible inhomogeneity dephasing that a 180 pulse at TE/2 refocuses. Before
  // the pulse the reversible phase grows with t; after it, it unwinds toward TE,
  // so the echo at t=TE is fully refocused and peaks on the true-T2 envelope
  // (exp(-TE/T2)), while at TE/2 the signal sits on the faster T2* curve.
  function spinEchoSignal(t, T2, T2prime, TE) {
    var rev = t <= TE / 2 ? t : Math.abs(t - TE);
    return Math.exp(-t / T2) * Math.exp(-rev / T2prime);
  }

  // Ernst angle (radians): the flip angle that maximizes spoiled-GRE signal at a given TR/T1.
  function ernstAngle(TR, T1) { return Math.acos(Math.exp(-TR / T1)); }

  // Spoiled gradient-echo steady-state signal vs flip angle alpha (radians).
  function spoiledGreSignal(alpha, TR, T1) {
    var e1 = Math.exp(-TR / T1);
    return Math.sin(alpha) * (1 - e1) / (1 - Math.cos(alpha) * e1);
  }

  // Inversion-recovery longitudinal magnetization: starts at -1 after the 180, recovers to +1.
  function irMz(t, T1) { return 1 - 2 * Math.exp(-t / T1); }

  // Inversion time that nulls a tissue (irMz crosses zero).
  function nullTI(T1) { return T1 * Math.LN2; }

  // Diffusion-weighted signal: mono-exponential decay with b-value and ADC.
  function dwiSignal(b, ADC) { return Math.exp(-b * ADC); }

  // Phase-contrast measured velocity: true velocity wrapped into [-venc, venc]. Above
  // venc the phase exceeds +-pi and aliases, so the measured value jumps to the
  // opposite sign, mimicking reversed flow.
  function aliasedVelocity(v, venc) {
    var m = 2 * venc;
    return ((v + venc) % m + m) % m - venc;
  }

  // Time-of-flight fresh-blood signal fraction: 0 at no flow, full (1) once flow
  // velocity reaches vFull (slab thickness over TR), clamped so faster flow cannot
  // exceed full replenishment.
  function tofSignal(v, vFull) { return Math.min(1, v / vFull); }

  // Gaussian bump centered at mu with width sig.
  function gauss(t, mu, sig) { return Math.exp(-((t - mu) * (t - mu)) / (2 * sig * sig)); }

  // DSC (dynamic susceptibility contrast) signal-time curve: baseline 1, a first-pass
  // dip near t=10 s as the gadolinium bolus passes (T2* susceptibility loss), and a
  // smaller recirculation dip near t=22 s. depth scales with blood volume (CBV):
  // a deeper first-pass dip means more tumor blood volume (higher grade).
  function dscSignal(t, depth) {
    return 1 - depth * gauss(t, 10, 2.5) - 0.3 * depth * gauss(t, 22, 3);
  }

  // Combined fat+water transverse signal magnitude at echo time teMs. Fat precesses deltaFHz
  // slower than water, so the two vectors rephase (in phase) and dephase (opposed) as TE grows.
  function fatWaterSignal(teMs, fatFrac, deltaFHz) {
    var w = 1 - fatFrac, f = fatFrac, ph = 2 * Math.PI * deltaFHz * (teMs / 1000);
    var re = w + f * Math.cos(ph), im = f * Math.sin(ph);
    return Math.sqrt(re * re + im * im);
  }

  // In-place radix-2 Cooley-Tukey FFT; re/im length must be a power of 2. Inverse divides by N.
  function fft1d(re, im, inverse) {
    var n = re.length, i, j, len, s, k;
    for (i = 1, j = 0; i < n; i++) {
      var bit = n >> 1;
      for (; j & bit; bit >>= 1) j ^= bit;
      j ^= bit;
      if (i < j) {
        var tr = re[i]; re[i] = re[j]; re[j] = tr;
        var ti = im[i]; im[i] = im[j]; im[j] = ti;
      }
    }
    for (len = 2; len <= n; len <<= 1) {
      var ang = (inverse ? 2 : -2) * Math.PI / len;
      var wr = Math.cos(ang), wi = Math.sin(ang);
      for (s = 0; s < n; s += len) {
        var cwr = 1, cwi = 0;
        for (k = 0; k < (len >> 1); k++) {
          var a = s + k, b = s + k + (len >> 1);
          var vr = re[b] * cwr - im[b] * cwi, vi = re[b] * cwi + im[b] * cwr;
          re[b] = re[a] - vr; im[b] = im[a] - vi;
          re[a] = re[a] + vr; im[a] = im[a] + vi;
          var ncwr = cwr * wr - cwi * wi;
          cwi = cwr * wi + cwi * wr; cwr = ncwr;
        }
      }
    }
    if (inverse) { for (i = 0; i < n; i++) { re[i] /= n; im[i] /= n; } }
  }

  // 2D FFT of an N x N row-major complex array: transform rows then columns.
  function fft2d(re, im, N, inverse) {
    var rr = new Array(N), ri = new Array(N), x, y;
    for (y = 0; y < N; y++) {
      for (x = 0; x < N; x++) { rr[x] = re[y * N + x]; ri[x] = im[y * N + x]; }
      fft1d(rr, ri, inverse);
      for (x = 0; x < N; x++) { re[y * N + x] = rr[x]; im[y * N + x] = ri[x]; }
    }
    var cr = new Array(N), ci = new Array(N);
    for (x = 0; x < N; x++) {
      for (y = 0; y < N; y++) { cr[y] = re[y * N + x]; ci[y] = im[y * N + x]; }
      fft1d(cr, ci, inverse);
      for (y = 0; y < N; y++) { re[y * N + x] = cr[y]; im[y * N + x] = ci[y]; }
    }
  }

  // Swap diagonal quadrants of an N x N array (DC <-> center). Self-inverse for even N.
  function fftshift2d(a, N) {
    var h = N >> 1, x, y, t;
    for (y = 0; y < h; y++) {
      for (x = 0; x < h; x++) {
        var i00 = y * N + x, i11 = (y + h) * N + (x + h);
        t = a[i00]; a[i00] = a[i11]; a[i11] = t;
        var i01 = y * N + (x + h), i10 = (y + h) * N + x;
        t = a[i01]; a[i01] = a[i10]; a[i10] = t;
      }
    }
  }

  // Relative SNR and scan time vs baseline {slice:3, matrix:192, nex:1, bw:32}.
  function snrScanRel(p) {
    var snr = (p.slice / 3) * Math.pow(192 / p.matrix, 2) * Math.sqrt(p.nex / 1) * Math.sqrt(32 / p.bw);
    var time = (p.matrix / 192) * (p.nex / 1);
    return { snr: snr, time: time };
  }

  // TR/TE thresholds (ms), 1.5 T teaching values.
  var TR_SHORT = 700, TR_LONG = 1500, TE_SHORT = 35, TE_LONG = 80;

  function classifyWeighting(tr, te) {
    var trShort = tr < TR_SHORT, trLong = tr >= TR_LONG;
    var teShort = te < TE_SHORT, teLong = te >= TE_LONG;
    if (trShort && teShort) return "T1";
    if (trLong && teLong) return "T2";
    if (trLong && teShort) return "PD";
    return "mixed"; // short TR + long TE, or any mid-range combination
  }

  // Evenly sample fn over [0, tMax] into n+1 [t, v] points.
  function sample(fn, tMax, n) {
    var pts = [];
    for (var i = 0; i <= n; i++) {
      var t = (tMax * i) / n;
      pts.push([t, fn(t)]);
    }
    return pts;
  }

  // Representative 1.5 T relaxation constants (ms). Teaching approximations.
  var TISSUES = [
    { id: "fat", label: "Fat", t1: 260, t2: 80 },
    { id: "wm", label: "White matter", t1: 510, t2: 90 },
    { id: "gm", label: "Gray matter", t1: 760, t2: 100 },
    { id: "csf", label: "CSF", t1: 2400, t2: 1400 },
  ];

  // Apparent diffusion coefficients (mm^2/s), 1.5 T teaching approximations.
  var ADCS = [
    { id: "restricted", label: "Restricted (stroke)", adc: 0.0006 },
    { id: "normal", label: "Normal tissue", adc: 0.0010 },
    { id: "free", label: "Free water (CSF)", adc: 0.0030 },
  ];

  // Diagram id(s) shown inside each premium education card, keyed by exact title.
  var DIAGRAM_MAP = {
    "Relaxation: T1 spin-lattice and T2 spin-spin": ["t1-recovery", "t2-decay"],
    "Dephasing, T2 vs T2*, and the spin-echo refocusing pulse": ["t2-vs-t2star"],
    "TR, TE, TI, and flip angle: setting image contrast": ["tr-te-weighting"],
    "Flip angle: the Ernst angle and the SAR trade-off": ["ernst-angle"],
    "Fat suppression: STIR, spectral, Dixon and water excitation": ["ir-nulling", "chemical-shift"],
    "Diffusion in disease: stroke, abscess and cellular tumors": ["dwi-bvalue"],
    "Image quality: SNR, CNR, resolution & the trade-offs": ["snr-tradeoff"],
    "Data acquisition: k-space, encoding and the Fourier transform": ["kspace-recon"],
    "Acquisition parameters and k-space: matrix, FOV, NEX, and acceleration": ["parallel-imaging"],
    "Spatial encoding: slice, phase, and frequency gradients into k-space": ["kspace-trajectories"],
    "MR image quality: SNR, scan time, and spatial resolution tradeoffs": ["gibbs-ringing"],
    "Perfusion by DSC: first-pass bolus tracking": ["dsc-curve"],
    "Arterial spin labeling: perfusion without contrast": ["asl-subtraction"],
    "Phase contrast MRA and velocity encoding (VENC)": ["pc-venc"],
    "Time-of-flight MRA: inflow, saturation, and pitfalls": ["tof-inflow"],
    "The diffusion tensor and fractional anisotropy (FA)": ["fa-anisotropy"],
    "DTI tractography: mapping white matter tracts": ["tractography"],
    "Cardiac gating and triggering: ECG, VCG, and the R-wave": ["cardiac-gating"],
    "Myocardial tissue characterization: LGE and parametric mapping": ["lge-nulling"],
    "Metabolites and clinical interpretation": ["mrs-spectrum"],
    "Acquisition techniques: STEAM, PRESS, and echo time": ["mrs-te"],
    "BOLD contrast: neurovascular coupling": ["bold-hrf"],
    "Task-based fMRI: paradigms and analysis": ["fmri-design"],
    "Quantitative mapping: why measure relaxation times": ["relaxometry"],
    "T2*, R2*, and susceptibility mapping": ["r2star-iron"],
    "Dynamic contrast enhancement kinetics": ["dce-kinetics"],
    "Background parenchymal enhancement, morphology, and BI-RADS": ["bpe-cycle"],
    "Multiparametric protocol and zonal anatomy": ["prostate-zones"],
    "Diffusion, ADC, and sequence dominance": ["prostate-dwi"],
    "Metal artifact reduction": ["metal-bandwidth"],
    "Artifacts, applications, and pitfalls": ["magic-angle"],
    "MRCP technique": ["mrcp-te"],
    "Hepatobiliary contrast agents": ["hepatobiliary-phase"],
    "Making an MR signal: protons, B0, Larmor, and resonance": ["larmor-field"],
    "MRI contrast agents: gadolinium, safety and special agents": ["gad-t1"],
    "RF heating and coil safety: SAR, B1+rms, and burns": ["sar-flip"],
    "Perfusion by DCE: permeability and Ktrans": ["dce-ktrans"],
    "Contrast-enhanced MRA: bolus timing and technique": ["cemra-bolus"],
    "Pulse sequences: SE, FSE, GRE, EPI and how they are built": ["pulse-timing"],
    "MR safety: the static field, zones and projectiles": ["safety-zones"],
    "Resting-state fMRI and functional connectivity": ["rs-connectivity"],
    "Cine imaging and ventricular function": ["cardiac-ef"],
    "3D acquisition: isotropic voxels and the sequences that make them": ["iso-voxel"],
    "The image-formation pipeline: excite, encode, sample, reconstruct": ["signal-chain"],
  };

  return { mz: mz, mxy: mxy, t2star: t2star, spinEchoSignal: spinEchoSignal,
    ernstAngle: ernstAngle, spoiledGreSignal: spoiledGreSignal, irMz: irMz, nullTI: nullTI,
    dwiSignal: dwiSignal, classifyWeighting: classifyWeighting, sample: sample,
    fft1d: fft1d, fft2d: fft2d, fftshift2d: fftshift2d, snrScanRel: snrScanRel,
    fatWaterSignal: fatWaterSignal, gauss: gauss, dscSignal: dscSignal,
    aliasedVelocity: aliasedVelocity, tofSignal: tofSignal,
    TISSUES: TISSUES, ADCS: ADCS, DIAGRAM_MAP: DIAGRAM_MAP };
});
