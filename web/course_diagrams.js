/* Interactive SVG physics diagrams for the guided course. Classic browser script;
 * defines window.CourseDiagrams. Pure math comes from window.CourseDiagramsMath.
 * attach(card, eduTitle) drops the mapped widget(s) into an education card. */
(function () {
  "use strict";

  var M = window.CourseDiagramsMath;
  var SVGNS = "http://www.w3.org/2000/svg";
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function svgEl(name, attrs) {
    var e = document.createElementNS(SVGNS, name);
    if (attrs) for (var k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  }
  function el(tag, attrs, kids) {
    var e = document.createElement(tag);
    if (attrs) for (var k in attrs) {
      if (k === "text") e.textContent = attrs[k];
      else e.setAttribute(k, attrs[k]);
    }
    (kids || []).forEach(function (c) { e.appendChild(c); });
    return e;
  }

  // A padded plot area with axes. Returns coordinate mappers and draw helpers.
  // opts: { xMax, yMax (default 1), yMin (default 0), xLabel, yLabel, xTicks, yTicks, title }
  function makePlot(opts) {
    var W = 320, H = 180, padL = 40, padB = 30, padT = 8, padR = 10;
    var x0 = padL, x1 = W - padR, y0 = H - padB, y1 = padT;
    var svg = svgEl("svg", { class: "diag-svg", viewBox: "0 0 " + W + " " + H,
      role: "img", "aria-label": opts.title });
    var t = svgEl("title", {}); t.textContent = opts.title; svg.appendChild(t);
    function toX(tv) { return x0 + (x1 - x0) * (tv / opts.xMax); }
    var yMin = opts.yMin || 0, yMax = opts.yMax || 1;
    function toY(v) { return y0 - (y0 - y1) * ((v - yMin) / (yMax - yMin)); }
    function addAxes() {
      svg.appendChild(svgEl("line", { class: "diag-axis", x1: x0, y1: y0, x2: x1, y2: y0 }));
      svg.appendChild(svgEl("line", { class: "diag-axis", x1: x0, y1: y0, x2: x0, y2: y1 }));
      if (yMin < 0) {
        svg.appendChild(svgEl("line", { class: "diag-axis", x1: x0, y1: toY(0), x2: x1, y2: toY(0) }));
      }
      // y-axis numeric ticks (fraction of full scale)
      (opts.yTicks || [0, 0.5, 1]).forEach(function (v) {
        var y = toY(v);
        svg.appendChild(svgEl("line", { class: "diag-axis", x1: x0 - 3, y1: y, x2: x0, y2: y }));
        var yt = svgEl("text", { class: "diag-axtext", x: x0 - 5, y: y + 3, "text-anchor": "end" });
        yt.textContent = String(v); svg.appendChild(yt);
      });
      // x-axis numeric ticks (ms); edge labels anchored inward so they stay in view
      (opts.xTicks || []).forEach(function (tv) {
        var x = toX(tv);
        svg.appendChild(svgEl("line", { class: "diag-axis", x1: x, y1: y0, x2: x, y2: y0 + 3 }));
        var anc = x <= x0 + 6 ? "start" : (x >= x1 - 6 ? "end" : "middle");
        var xt = svgEl("text", { class: "diag-axtext", x: x, y: y0 + 12, "text-anchor": anc });
        xt.textContent = String(tv); svg.appendChild(xt);
      });
      // rotated y-axis unit label, clear of the tick numbers
      var mid = (y0 + y1) / 2;
      var yl = svgEl("text", { class: "diag-axtext", x: 10, y: mid,
        "text-anchor": "middle", transform: "rotate(-90 10 " + mid + ")" });
      yl.textContent = opts.yLabel; svg.appendChild(yl);
      // centered x-axis unit label below the tick numbers
      var xl = svgEl("text", { class: "diag-axtext", x: (x0 + x1) / 2, y: y0 + 24, "text-anchor": "middle" });
      xl.textContent = opts.xLabel; svg.appendChild(xl);
    }
    function pathData(points) {
      return points.map(function (p, i) {
        return (i ? "L" : "M") + toX(p[0]).toFixed(1) + " " + toY(p[1]).toFixed(1);
      }).join(" ");
    }
    // points: Array<[t,v]>. Returns the <path> so callers can animate it.
    function addCurve(points, cls) {
      var path = svgEl("path", { class: "diag-curve " + (cls || ""), d: pathData(points) });
      svg.appendChild(path);
      return path;
    }
    // Animate a curve drawing from left to right by growing its point set.
    function animateCurve(path, points) {
      if (reduceMotion) return; // final curve already drawn by addCurve
      var start = null, dur = 650;
      if (typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches) {
        path.setAttribute("d", pathData(points));   // final frame, no animation
        return;
      }
      path.setAttribute("d", pathData(points.slice(0, 1)));
      function frame(ts) {
        if (start === null) start = ts;
        var k = Math.min(1, (ts - start) / dur);
        var n = Math.max(1, Math.round(k * (points.length - 1)));
        path.setAttribute("d", pathData(points.slice(0, n + 1)));
        if (k < 1) requestAnimationFrame(frame);
      }
      requestAnimationFrame(frame);
    }
    function addLabel(tv, text) {
      var tx = svgEl("text", { class: "diag-axtext", x: toX(tv), y: y1 + 8, "text-anchor": "middle" });
      tx.textContent = text; svg.appendChild(tx);
      return tx;
    }
    function addMarker(tv, cls, label) {
      var g = svgEl("g", {});
      g.appendChild(svgEl("line", { class: "diag-marker " + (cls || ""),
        x1: toX(tv), y1: y0, x2: toX(tv), y2: y1 }));
      if (label) {
        var tx = svgEl("text", { class: "diag-axtext", x: toX(tv), y: y1 + 8, "text-anchor": "middle" });
        tx.textContent = label; g.appendChild(tx);
      }
      svg.appendChild(g);
      return g;
    }
    function addDot(tv, v, cls) {
      var c = svgEl("circle", { class: "diag-dot " + (cls || ""), cx: toX(tv), cy: toY(v), r: 3 });
      svg.appendChild(c);
      return c;
    }
    return { svg: svg, toX: toX, toY: toY, addAxes: addAxes, addCurve: addCurve,
      animateCurve: animateCurve, addMarker: addMarker, addLabel: addLabel, addDot: addDot };
  }

  // A labeled figure shell shared by every widget.
  function figure(title, caption) {
    var fig = el("figure", { class: "diagram", "aria-label": title });
    fig.appendChild(el("figcaption", { class: "diag-cap", text: caption }));
    return fig;
  }

  // ---- shared canvas helpers for the FFT widgets ---- //
  // 64x64 teaching phantom: a bright disc (contrast) plus two sharp bars (detail/edges).
  function phantom(N) {
    var img = new Array(N * N), x, y;
    for (y = 0; y < N; y++) {
      for (x = 0; x < N; x++) {
        var dx = x - N / 2, dy = y - N / 2;
        var v = (dx * dx + dy * dy) < (N * 0.28) * (N * 0.28) ? 0.8 : 0.08;
        if ((x > N * 0.30 && x < N * 0.34) || (y > N * 0.62 && y < N * 0.66)) v = 1.0;
        img[y * N + x] = v;
      }
    }
    return img;
  }
  // Forward-transform a real image to a DC-centered complex spectrum { re, im }.
  function centeredSpectrum(img, N) {
    var re = img.slice(), im = new Array(N * N), i;
    for (i = 0; i < N * N; i++) im[i] = 0;
    M.fft2d(re, im, N, false); M.fftshift2d(re, N); M.fftshift2d(im, N);
    return { re: re, im: im };
  }
  // Draw log-magnitude of a centered complex spectrum (grayscale) to a 2D context.
  function drawKMag(ctx, re, im, N) {
    var d = ctx.createImageData(N, N), mag = new Array(N * N), mx = 0, p;
    for (p = 0; p < N * N; p++) { mag[p] = Math.log(1 + Math.sqrt(re[p] * re[p] + im[p] * im[p])); if (mag[p] > mx) mx = mag[p]; }
    for (p = 0; p < N * N; p++) { var g = Math.round(255 * mag[p] / (mx || 1)); d.data[p * 4] = g; d.data[p * 4 + 1] = g; d.data[p * 4 + 2] = g; d.data[p * 4 + 3] = 255; }
    ctx.putImageData(d, 0, 0);
  }
  // Draw a real-valued grayscale array (non-negative), scaled by its own max, to a 2D context.
  function drawGray(ctx, arr, N) {
    var d = ctx.createImageData(N, N), mx = 0, p;
    for (p = 0; p < N * N; p++) { if (arr[p] > mx) mx = arr[p]; }
    for (p = 0; p < N * N; p++) { var g = Math.round(255 * arr[p] / (mx || 1)); d.data[p * 4] = g; d.data[p * 4 + 1] = g; d.data[p * 4 + 2] = g; d.data[p * 4 + 3] = 255; }
    ctx.putImageData(d, 0, 0);
  }
  // Draw magnitude of a complex image (grayscale) to a 2D context.
  function drawIMag(ctx, re, im, N) {
    var d = ctx.createImageData(N, N), mag = new Array(N * N), mx = 0, p;
    for (p = 0; p < N * N; p++) { mag[p] = Math.sqrt(re[p] * re[p] + im[p] * im[p]); if (mag[p] > mx) mx = mag[p]; }
    for (p = 0; p < N * N; p++) { var g = Math.round(255 * mag[p] / (mx || 1)); d.data[p * 4] = g; d.data[p * 4 + 1] = g; d.data[p * 4 + 2] = g; d.data[p * 4 + 3] = 255; }
    ctx.putImageData(d, 0, 0);
  }
  // Inverse-transform a centered masked spectrum (copies) and draw its magnitude image.
  function reconMag(ctx, mre, mim, N) {
    var sre = mre.slice(), sim = mim.slice();
    M.fftshift2d(sre, N); M.fftshift2d(sim, N); M.fft2d(sre, sim, N, true);
    drawIMag(ctx, sre, sim, N);
  }

  // ---- Widget: T1 longitudinal recovery ---- //
  function buildT1Recovery() {
    var fig = figure("T1 recovery", "T1 recovery: Mz rebuilds along B0 (1.5 T, approximate).");
    var state = { tissue: M.TISSUES[1], tr: null };
    var xMax = 3000;
    var plot = makePlot({ xMax: xMax, yMax: 1, xLabel: "t (ms)", yLabel: "Mz",
      xTicks: [0, 1000, 2000, 3000], title: "T1 longitudinal recovery curve" });
    plot.addAxes();
    var curve = null, marker = null;
    var readout = el("div", { class: "diag-readout" });
    function redraw(animate) {
      if (curve) curve.remove(); if (marker) marker.remove();
      var pts = M.sample(function (t) { return M.mz(t, state.tissue.t1); }, xMax, 60);
      curve = plot.addCurve(pts, "");
      if (animate) plot.animateCurve(curve, pts);
      readout.textContent = state.tr === null ? "Pick a TR to see recovery at that time."
        : "At TR " + state.tr + " ms, " + state.tissue.label + " has recovered "
          + Math.round(M.mz(state.tr, state.tissue.t1) * 100) + "% of Mz.";
      if (state.tr !== null) marker = plot.addMarker(state.tr, "");
    }
    fig.appendChild(plot.svg);

    var controls = el("div", { class: "diag-controls" });
    var sel = el("select", { class: "diag-select", "aria-label": "Tissue" });
    M.TISSUES.forEach(function (ti, i) {
      var o = el("option", { value: ti.id, text: ti.label });
      if (i === 1) o.setAttribute("selected", "selected");
      sel.appendChild(o);
    });
    sel.addEventListener("change", function () {
      state.tissue = M.TISSUES.filter(function (t) { return t.id === sel.value; })[0];
      redraw(false);
    });
    controls.appendChild(sel);

    [["Short", 400], ["Medium", 1200], ["Long", 2500]].forEach(function (p) {
      var b = el("button", { type: "button", class: "diag-btn", text: "TR " + p[0] });
      b.addEventListener("click", function () {
        state.tr = p[1];
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (x) { x.classList.remove("on"); });
        b.classList.add("on");
        redraw(false);
      });
      controls.appendChild(b);
    });
    if (!reduceMotion) {
      var play = el("button", { type: "button", class: "diag-btn diag-play", text: "▸ Play" });
      play.addEventListener("click", function () { redraw(true); });
      controls.appendChild(play);
    }
    fig.appendChild(controls);
    fig.appendChild(readout);

    redraw(false);
    return fig;
  }

  // ---- Widget: T2 transverse decay ---- //
  function buildT2Decay() {
    var fig = figure("T2 decay", "T2 decay: Mxy dephases in the transverse plane (1.5 T, approximate).");
    var state = { tissue: M.TISSUES[1], te: null };
    var xMax = 400;
    var plot = makePlot({ xMax: xMax, yMax: 1, xLabel: "t (ms)", yLabel: "Mxy",
      xTicks: [0, 100, 200, 300, 400], title: "T2 transverse decay curve" });
    plot.addAxes();
    var curve = null, marker = null;
    var readout = el("div", { class: "diag-readout" });
    function redraw(animate) {
      if (curve) curve.remove(); if (marker) marker.remove();
      var pts = M.sample(function (t) { return M.mxy(t, state.tissue.t2); }, xMax, 60);
      curve = plot.addCurve(pts, "");
      if (animate) plot.animateCurve(curve, pts);
      readout.textContent = state.te === null ? "Pick a TE to see signal remaining at that echo time."
        : "At TE " + state.te + " ms, " + state.tissue.label + " retains "
          + Math.round(M.mxy(state.te, state.tissue.t2) * 100) + "% of Mxy.";
      if (state.te !== null) marker = plot.addMarker(state.te, "");
    }
    fig.appendChild(plot.svg);
    var controls = el("div", { class: "diag-controls" });
    var sel = el("select", { class: "diag-select", "aria-label": "Tissue" });
    M.TISSUES.forEach(function (ti, i) {
      var o = el("option", { value: ti.id, text: ti.label });
      if (i === 1) o.setAttribute("selected", "selected");
      sel.appendChild(o);
    });
    sel.addEventListener("change", function () {
      state.tissue = M.TISSUES.filter(function (t) { return t.id === sel.value; })[0];
      redraw(false);
    });
    controls.appendChild(sel);
    [["Short", 15], ["Medium", 40], ["Long", 90]].forEach(function (p) {
      var b = el("button", { type: "button", class: "diag-btn", text: "TE " + p[0] });
      b.addEventListener("click", function () {
        state.te = p[1];
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (x) { x.classList.remove("on"); });
        b.classList.add("on");
        redraw(false);
      });
      controls.appendChild(b);
    });
    if (!reduceMotion) {
      var play = el("button", { type: "button", class: "diag-btn diag-play", text: "▸ Play" });
      play.addEventListener("click", function () { redraw(true); });
      controls.appendChild(play);
    }
    fig.appendChild(controls);
    fig.appendChild(readout);
    redraw(false);
    return fig;
  }

  // ---- Widget: T2 vs T2* (the spin-echo refocusing story) ---- //
  function buildT2vsT2star() {
    var fig = figure("T2 vs T2*", "After the 90 pulse the signal falls fast along T2* (what a gradient echo sees). A 180 pulse at TE/2 refocuses the field-inhomogeneity dephasing, so a spin echo rebuilds at TE up to the true-T2 envelope, recovering what the gradient echo lost. Pick an echo time (1.5 T, approximate).");
    var T2 = 100, T2prime = 30;   // ms; fixed tissue T2 and field inhomogeneity
    var xMax = 200;
    var state = { te: 80 };
    var plot = makePlot({ xMax: xMax, yMax: 1, xLabel: "t (ms)", yLabel: "Signal",
      xTicks: [0, 50, 100, 150, 200], title: "Spin-echo refocusing: T2* decay and the echo at TE" });
    plot.addAxes();
    // True-T2 envelope: the ceiling the echo reaches (dashed). Drawn once.
    plot.addCurve(M.sample(function (t) { return M.mxy(t, T2); }, xMax, 80), "env");
    plot.addLabel(0, "90");
    var sig = null, m180 = null, mTE = null, dot = null;
    var readout = el("div", { class: "diag-readout" });
    function redraw() {
      if (sig) sig.remove();
      if (m180) m180.remove();
      if (mTE) mTE.remove();
      if (dot) dot.remove();
      sig = plot.addCurve(M.sample(function (t) {
        return M.spinEchoSignal(t, T2, T2prime, state.te); }, xMax, 120), "");
      m180 = plot.addMarker(state.te / 2, "", "180");
      mTE = plot.addMarker(state.te, "", "TE");
      dot = plot.addDot(state.te, M.mxy(state.te, T2), "");
      var se = Math.round(M.mxy(state.te, T2) * 100);
      var ge = Math.round(M.mxy(state.te, M.t2star(T2, T2prime)) * 100);
      readout.textContent = "At TE " + state.te + " ms the spin echo reaches " + se
        + "% (true T2); a gradient echo would read only " + ge + "% (T2*). The 180 recovers "
        + (se - ge) + " points.";
    }
    fig.appendChild(plot.svg);
    var controls = el("div", { class: "diag-controls" });
    controls.appendChild(el("span", { class: "diag-glabel", text: "Echo time TE:" }));
    [["Short", 40], ["Medium", 80], ["Long", 120]].forEach(function (p) {
      var b = el("button", { type: "button", class: "diag-btn" + (p[1] === state.te ? " on" : ""), text: p[0] });
      b.addEventListener("click", function () {
        state.te = p[1];
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (x) { x.classList.remove("on"); });
        b.classList.add("on");
        redraw();
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls);
    fig.appendChild(readout);
    redraw();
    return fig;
  }

  // ---- Widget: TR/TE -> weighting ---- //
  function buildTrTeWeighting() {
    var fig = figure("TR/TE and weighting", "TR/TE and weighting: long TR undoes T1 differences; long TE reveals T2 differences (1.5 T, approximate).");
    var state = { tr: 400, te: 15 };
    var trMax = 3000, teMax = 200;
    var wm = M.TISSUES[1], csf = M.TISSUES[3]; // contrast pair: white matter vs CSF

    var recov = makePlot({ xMax: trMax, yMax: 1, xLabel: "TR (ms)", yLabel: "Mz",
      xTicks: [0, 1000, 2000, 3000], title: "Longitudinal recovery vs TR" });
    recov.addAxes();
    recov.addCurve(M.sample(function (t) { return M.mz(t, wm.t1); }, trMax, 60), "");
    recov.addCurve(M.sample(function (t) { return M.mz(t, csf.t1); }, trMax, 60), "pd");
    var trMark = null;

    var decay = makePlot({ xMax: teMax, yMax: 1, xLabel: "TE (ms)", yLabel: "Mxy",
      xTicks: [0, 50, 100, 150, 200], title: "Transverse decay vs TE" });
    decay.addAxes();
    decay.addCurve(M.sample(function (t) { return M.mxy(t, wm.t2); }, teMax, 60), "");
    decay.addCurve(M.sample(function (t) { return M.mxy(t, csf.t2); }, teMax, 60), "pd");
    var teMark = null;

    var readout = el("div", { class: "diag-readout" });
    function redraw() {
      if (trMark) trMark.remove();
      if (teMark) teMark.remove();
      trMark = recov.addMarker(state.tr, "");
      teMark = decay.addMarker(state.te, "");
      var w = M.classifyWeighting(state.tr, state.te);
      var name = { T1: "T1-weighted", T2: "T2-weighted", PD: "proton-density", mixed: "mixed (rarely used)" }[w];
      readout.textContent = "TR " + state.tr + " / TE " + state.te + " ms → " + name
        + ". (Accent = white matter, gray = CSF.)";
    }
    var wrap = el("div", { class: "diag-dual" });
    wrap.appendChild(recov.svg);
    wrap.appendChild(decay.svg);
    fig.appendChild(wrap);

    var controls = el("div", { class: "diag-controls" });
    function group(labelTxt, key, presets) {
      controls.appendChild(el("span", { class: "diag-glabel", text: labelTxt }));
      presets.forEach(function (p) {
        var b = el("button", { type: "button", class: "diag-btn diag-" + key, text: p[0] });
        b.addEventListener("click", function () {
          state[key] = p[1];
          [].forEach.call(controls.querySelectorAll(".diag-" + key), function (x) { x.classList.remove("on"); });
          b.classList.add("on");
          redraw();
        });
        controls.appendChild(b);
      });
    }
    group("TR:", "tr", [["Short", 400], ["Long", 2500]]);
    group("TE:", "te", [["Short", 15], ["Long", 90]]);
    fig.appendChild(controls);
    fig.appendChild(readout);
    redraw();
    return fig;
  }

  // ---- Widget: Ernst angle ---- //
  function buildErnstAngle() {
    var fig = figure("Ernst angle", "Ernst angle: for a given TR, one flip angle gives the most spoiled-GRE signal. Going higher adds SAR for little gain (1.5 T, approximate).");
    var state = { tissue: M.TISSUES[1], tr: 500 };
    var xMax = 90;
    var plot = makePlot({ xMax: xMax, yMax: 1, xLabel: "flip angle (deg)", yLabel: "signal",
      xTicks: [0, 30, 60, 90], title: "Spoiled gradient-echo signal versus flip angle" });
    plot.addAxes();
    var curve = null, marker = null;
    var readout = el("div", { class: "diag-readout" });
    function redraw(animate) {
      if (curve) curve.remove(); if (marker) marker.remove();
      var pts = M.sample(function (deg) {
        return M.spoiledGreSignal(deg * Math.PI / 180, state.tr, state.tissue.t1); }, xMax, 90);
      curve = plot.addCurve(pts, "");
      if (animate) plot.animateCurve(curve, pts);
      var aeDeg = M.ernstAngle(state.tr, state.tissue.t1) * 180 / Math.PI;
      marker = plot.addMarker(aeDeg, "", Math.round(aeDeg) + "°");
      readout.textContent = "Ernst angle " + Math.round(aeDeg) + "° for TR " + state.tr
        + " ms, " + state.tissue.label + " (T1 " + state.tissue.t1 + " ms). Above it, more flip angle costs SAR for little extra signal.";
    }
    fig.appendChild(plot.svg);
    var controls = el("div", { class: "diag-controls" });
    var sel = el("select", { class: "diag-select", "aria-label": "Tissue" });
    M.TISSUES.forEach(function (ti, i) {
      var o = el("option", { value: ti.id, text: ti.label });
      if (i === 1) o.setAttribute("selected", "selected");
      sel.appendChild(o);
    });
    sel.addEventListener("change", function () {
      state.tissue = M.TISSUES.filter(function (t) { return t.id === sel.value; })[0];
      redraw(false);
    });
    controls.appendChild(sel);
    [["Short", 150], ["Medium", 500], ["Long", 1500]].forEach(function (p) {
      var b = el("button", { type: "button", class: "diag-btn" + (p[1] === state.tr ? " on" : ""), text: "TR " + p[0] });
      b.addEventListener("click", function () {
        state.tr = p[1];
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (x) { x.classList.remove("on"); });
        b.classList.add("on");
        redraw(false);
      });
      controls.appendChild(b);
    });
    if (!reduceMotion) {
      var play = el("button", { type: "button", class: "diag-btn diag-play", text: "▸ Play" });
      play.addEventListener("click", function () { redraw(true); });
      controls.appendChild(play);
    }
    fig.appendChild(controls);
    fig.appendChild(readout);
    redraw(false);
    return fig;
  }

  // ---- Widget: inversion-recovery nulling (STIR / FLAIR) ---- //
  function buildIrNulling() {
    var fig = figure("Inversion recovery", "After a 180 pulse Mz starts at -1 and recovers. At a tissue's null time TI its signal crosses zero: STIR nulls fat, FLAIR nulls CSF. Fat blue, white matter grey, CSF red (1.5 T, approximate).");
    var fat = M.TISSUES[0], wm = M.TISSUES[1], csf = M.TISSUES[3];
    var xMax = 3000;
    var state = { ti: Math.round(M.nullTI(fat.t1)) };
    var plot = makePlot({ xMax: xMax, yMin: -1, yMax: 1, xLabel: "TI (ms)", yLabel: "Mz",
      xTicks: [0, 1000, 2000, 3000], yTicks: [-1, -0.5, 0, 0.5, 1],
      title: "Inversion-recovery curves and the null time" });
    plot.addAxes();
    plot.addCurve(M.sample(function (t) { return M.irMz(t, fat.t1); }, xMax, 80), "");
    plot.addCurve(M.sample(function (t) { return M.irMz(t, wm.t1); }, xMax, 80), "pd");
    plot.addCurve(M.sample(function (t) { return M.irMz(t, csf.t1); }, xMax, 80), "alt");
    var marker = null;
    var readout = el("div", { class: "diag-readout" });
    function nulled(ti) {
      var best = null, bestAbs = Infinity;
      [fat, wm, csf].forEach(function (t) {
        var a = Math.abs(M.irMz(ti, t.t1));
        if (a < bestAbs) { bestAbs = a; best = t; }
      });
      return best;
    }
    function redraw() {
      if (marker) marker.remove();
      marker = plot.addMarker(state.ti, "", "TI");
      readout.textContent = "At TI " + state.ti + " ms, " + nulled(state.ti).label + " is nulled (its curve crosses zero).";
    }
    fig.appendChild(plot.svg);
    var controls = el("div", { class: "diag-controls" });
    controls.appendChild(el("span", { class: "diag-glabel", text: "TI:" }));
    [["STIR (null fat)", Math.round(M.nullTI(fat.t1))], ["FLAIR (null CSF)", Math.round(M.nullTI(csf.t1))]].forEach(function (p) {
      var b = el("button", { type: "button", class: "diag-btn" + (p[1] === state.ti ? " on" : ""), text: p[0] });
      b.addEventListener("click", function () {
        state.ti = p[1];
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (x) { x.classList.remove("on"); });
        b.classList.add("on");
        redraw();
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls);
    fig.appendChild(readout);
    redraw();
    return fig;
  }

  // ---- Widget: DWI signal vs b-value ---- //
  function buildDwiBvalue() {
    var fig = figure("DWI and b-value", "Diffusion weighting: signal falls as e to the minus b times ADC. Restricted diffusion (low ADC, e.g. acute stroke) stays bright at high b while free water darkens. Restricted blue, normal grey, free water red (1.5 T, approximate).");
    var xMax = 1000;
    var state = { b: 1000 };
    var plot = makePlot({ xMax: xMax, yMax: 1, xLabel: "b-value (s/mm2)", yLabel: "signal",
      xTicks: [0, 250, 500, 750, 1000], title: "Diffusion signal versus b-value" });
    plot.addAxes();
    M.ADCS.forEach(function (a, i) {
      plot.addCurve(M.sample(function (b) { return M.dwiSignal(b, a.adc); }, xMax, 80),
        i === 0 ? "" : (i === 1 ? "pd" : "alt"));
    });
    var marker = null;
    var readout = el("div", { class: "diag-readout" });
    function redraw() {
      if (marker) marker.remove();
      marker = plot.addMarker(state.b, "", "b");
      var parts = M.ADCS.map(function (a) {
        return a.label + " " + Math.round(M.dwiSignal(state.b, a.adc) * 100) + "%"; });
      readout.textContent = "At b " + state.b + " s/mm2: " + parts.join(", ") + ". Restricted diffusion stays brightest.";
    }
    fig.appendChild(plot.svg);
    var controls = el("div", { class: "diag-controls" });
    controls.appendChild(el("span", { class: "diag-glabel", text: "b-value:" }));
    [0, 500, 1000].forEach(function (bv) {
      var b = el("button", { type: "button", class: "diag-btn" + (bv === state.b ? " on" : ""), text: String(bv) });
      b.addEventListener("click", function () {
        state.b = bv;
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (x) { x.classList.remove("on"); });
        b.classList.add("on");
        redraw();
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls);
    fig.appendChild(readout);
    redraw();
    return fig;
  }

  // ---- Widget: SNR / scan-time trade-offs ---- //
  function buildSnrTradeoff() {
    var fig = figure("SNR trade-offs", "Signal-to-noise, resolution and scan time pull against each other. Change a parameter and watch relative SNR and scan time move against the baseline (1.5 T, approximate).");
    var state = { slice: 3, matrix: 192, nex: 1, bw: 32 };
    function bar(label) {
      var fill = el("div", { class: "diag-bar-fill" });
      var track = el("div", { class: "diag-bar-track" }, [fill, el("i", { class: "diag-bar-base" })]);
      var num = el("span", { class: "diag-bar-num" });
      var row = el("div", { class: "diag-bar-row" }, [el("span", { class: "diag-bar-label", text: label }), track, num]);
      return { node: row, set: function (v) {
        var cap = 3;
        fill.style.width = (Math.min(v, cap) / cap * 100) + "%";
        num.textContent = (Math.round(v * 100) / 100) + "x";
        if (v < 1) fill.classList.add("low"); else fill.classList.remove("low");
      } };
    }
    var snrBar = bar("Relative SNR"), timeBar = bar("Relative scan time");
    var readout = el("div", { class: "diag-readout" });
    function redraw() {
      var r = M.snrScanRel(state);
      snrBar.set(r.snr); timeBar.set(r.time);
      readout.textContent = "SNR " + (Math.round(r.snr * 100) / 100) + "x, scan time " + (Math.round(r.time * 100) / 100)
        + "x versus baseline (thin slice, coarse matrix, NEX 1, low bandwidth). Bigger voxels and more averages raise SNR; a finer matrix and higher bandwidth lower it.";
    }
    fig.appendChild(snrBar.node);
    fig.appendChild(timeBar.node);
    var controls = el("div", { class: "diag-controls" });
    function group(labelTxt, key, presets) {
      controls.appendChild(el("span", { class: "diag-glabel", text: labelTxt }));
      presets.forEach(function (p) {
        var b = el("button", { type: "button", class: "diag-btn diag-" + key + (p[1] === state[key] ? " on" : ""), text: p[0] });
        b.addEventListener("click", function () {
          state[key] = p[1];
          [].forEach.call(controls.querySelectorAll(".diag-" + key), function (x) { x.classList.remove("on"); });
          b.classList.add("on");
          redraw();
        });
        controls.appendChild(b);
      });
    }
    group("Slice:", "slice", [["Thin", 3], ["Thick", 6]]);
    group("Matrix:", "matrix", [["Coarse", 192], ["Fine", 384]]);
    group("NEX:", "nex", [["1", 1], ["2", 2], ["4", 4]]);
    group("BW:", "bw", [["Low", 32], ["High", 64]]);
    fig.appendChild(controls);
    fig.appendChild(readout);
    redraw();
    return fig;
  }

  // ---- Widget: k-space center vs periphery (real reconstruction) ---- //
  function buildKspaceRecon() {
    var fig = figure("k-space", "k-space holds the image's spatial frequencies. The center is low frequency: overall contrast and brightness. The edges are high frequency: fine detail and sharp borders. Keep only part of k-space, inverse-transform, and see what each region carries.");
    var N = 64, sp = centeredSpectrum(phantom(N), N), kre = sp.re, kim = sp.im;
    var R = N * 0.12;
    var kCanvas = document.createElement("canvas"); kCanvas.width = N; kCanvas.height = N; kCanvas.className = "diag-canvas";
    var iCanvas = document.createElement("canvas"); iCanvas.width = N; iCanvas.height = N; iCanvas.className = "diag-canvas";
    var kctx = kCanvas.getContext("2d"), ictx = iCanvas.getContext("2d");
    var readout = el("div", { class: "diag-readout" });
    function render(mode) {
      var mre = kre.slice(), mim = kim.slice(), gx, gy;
      for (gy = 0; gy < N; gy++) {
        for (gx = 0; gx < N; gx++) {
          var rx = gx - N / 2, ry = gy - N / 2, inC = (rx * rx + ry * ry) <= R * R;
          var keep = mode === "full" || (mode === "center" && inC) || (mode === "edges" && !inC);
          if (!keep) { mre[gy * N + gx] = 0; mim[gy * N + gx] = 0; }
        }
      }
      drawKMag(kctx, mre, mim, N);
      if (mode !== "full") { kctx.strokeStyle = "#5db0ef"; kctx.lineWidth = 1; kctx.beginPath(); kctx.arc(N / 2, N / 2, R, 0, 2 * Math.PI); kctx.stroke(); }
      reconMag(ictx, mre, mim, N);
      readout.textContent = mode === "center" ? "Center only (low-pass): full contrast returns but the image is blurred, fine detail is gone."
        : mode === "edges" ? "Edges only (high-pass): only sharp borders survive, overall contrast is gone."
        : "Full k-space: the complete image.";
    }
    var stage = el("div", { class: "diag-kspace" });
    stage.appendChild(el("figure", { class: "diag-canvas-wrap" }, [kCanvas, el("figcaption", { class: "diag-canvas-cap", text: "k-space" })]));
    stage.appendChild(el("figure", { class: "diag-canvas-wrap" }, [iCanvas, el("figcaption", { class: "diag-canvas-cap", text: "image" })]));
    fig.appendChild(stage);
    var controls = el("div", { class: "diag-controls" });
    [["Center (low-pass)", "center"], ["Edges (high-pass)", "edges"], ["Full", "full"]].forEach(function (pr) {
      var b = el("button", { type: "button", class: "diag-btn" + (pr[1] === "full" ? " on" : ""), text: pr[0] });
      b.addEventListener("click", function () {
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (z) { z.classList.remove("on"); });
        b.classList.add("on");
        render(pr[1]);
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls);
    fig.appendChild(readout);
    render("full");
    return fig;
  }

  // ---- Widget: k-space sampling trajectories ---- //
  function buildKspaceTrajectories() {
    var fig = figure("k-space sampling", "How k-space gets filled. Cartesian scans one line at a time (the standard). Radial and spiral sweep through the center on every readout, so they oversample low frequencies and tolerate motion (non-Cartesian).");
    var W = 220, H = 220, cx = W / 2, cy = H / 2, Rmax = 96;
    var svg = svgEl("svg", { class: "diag-svg", viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": "k-space sampling pattern" });
    svg.style.maxWidth = "240px";
    svg.appendChild(svgEl("line", { class: "diag-axis", x1: cx, y1: 8, x2: cx, y2: H - 8 }));
    svg.appendChild(svgEl("line", { class: "diag-axis", x1: 8, y1: cy, x2: W - 8, y2: cy }));
    var g = svgEl("g", {});
    svg.appendChild(g);
    var readout = el("div", { class: "diag-readout" });
    function draw(mode) {
      while (g.firstChild) g.removeChild(g.firstChild);
      var pts = [], a, r, rr, t, ang, rad, kx, ky;
      if (mode === "cartesian") {
        for (ky = -11; ky <= 11; ky++) { for (kx = -22; kx <= 22; kx++) { pts.push([kx / 22 * Rmax, ky / 11 * Rmax]); } }
      } else if (mode === "radial") {
        for (var s = 0; s < 16; s++) { a = Math.PI * s / 16; for (r = -22; r <= 22; r++) { rr = r / 22 * Rmax; pts.push([rr * Math.cos(a), rr * Math.sin(a)]); } }
      } else {
        for (t = 0; t <= 1.0001; t += 0.006) { ang = t * 2 * Math.PI * 6; rad = t * Rmax; pts.push([rad * Math.cos(ang), rad * Math.sin(ang)]); }
      }
      pts.forEach(function (p) { g.appendChild(svgEl("circle", { class: "diag-kpt", cx: (cx + p[0]).toFixed(1), cy: (cy + p[1]).toFixed(1), r: "1.1" })); });
      readout.textContent = mode === "cartesian" ? "Cartesian: parallel lines, one phase-encode step per TR. Simple and robust, but slower."
        : mode === "radial" ? "Radial: spokes through the center. Every spoke resamples low frequencies, so motion averages out."
          : "Spiral: one winding readout from the center outward. Very fast coverage, sensitive to off-resonance.";
    }
    fig.appendChild(svg);
    var controls = el("div", { class: "diag-controls" });
    [["Cartesian", "cartesian"], ["Radial", "radial"], ["Spiral", "spiral"]].forEach(function (p) {
      var b = el("button", { type: "button", class: "diag-btn" + (p[1] === "cartesian" ? " on" : ""), text: p[0] });
      b.addEventListener("click", function () {
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (z) { z.classList.remove("on"); });
        b.classList.add("on"); draw(p[1]);
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls); fig.appendChild(readout);
    draw("cartesian");
    return fig;
  }

  // ---- Widget: chemical shift and the Dixon method ---- //
  function buildChemicalShift() {
    var fig = figure("Chemical shift and Dixon", "Fat precesses about 220 Hz slower than water at 1.5 T, so as TE grows the two signals drift in and out of phase. Acquiring an in-phase and an opposed-phase echo is how the Dixon method separates fat from water (1.5 T, approximate).");
    var dF = 220, xMax = 10, state = { fatFrac: 0.5 };
    var opp = 1000 / (2 * dF), inph = 1000 / dF;
    var plot = makePlot({ xMax: xMax, yMax: 1, xLabel: "TE (ms)", yLabel: "signal", xTicks: [0, 2.5, 5, 7.5, 10], title: "Combined fat and water signal versus echo time" });
    plot.addAxes();
    var curve = null, mO = null, mI = null;
    var readout = el("div", { class: "diag-readout" });
    function redraw() {
      if (curve) curve.remove(); if (mO) mO.remove(); if (mI) mI.remove();
      var pts = M.sample(function (te) { return M.fatWaterSignal(te, state.fatFrac, dF); }, xMax, 100);
      curve = plot.addCurve(pts, "");
      mO = plot.addMarker(opp, "", "opp"); mI = plot.addMarker(inph, "", "in");
      readout.textContent = "Opposed-phase at " + opp.toFixed(1) + " ms (fat and water subtract), in-phase at " + inph.toFixed(1) + " ms (they add). Fat fraction " + Math.round(state.fatFrac * 100) + "%.";
    }
    fig.appendChild(plot.svg);
    var controls = el("div", { class: "diag-controls" });
    controls.appendChild(el("span", { class: "diag-glabel", text: "Fat fraction:" }));
    [["10%", 0.1], ["30%", 0.3], ["50%", 0.5]].forEach(function (p) {
      var b = el("button", { type: "button", class: "diag-btn" + (p[1] === state.fatFrac ? " on" : ""), text: p[0] });
      b.addEventListener("click", function () {
        state.fatFrac = p[1];
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (z) { z.classList.remove("on"); });
        b.classList.add("on"); redraw();
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls); fig.appendChild(readout);
    redraw();
    return fig;
  }

  // ---- Widget: parallel imaging (undersampling and aliasing) ---- //
  function buildParallelImaging() {
    var fig = figure("Parallel imaging", "Skipping k-space lines shortens the scan but shrinks the phase field of view, so the image aliases and wraps onto itself. Parallel imaging (SENSE, GRAPPA) uses several receive coils to unfold that wrap. Acceleration R is how many phase-encode lines are skipped (unfolding is not simulated here).");
    var N = 64, sp = centeredSpectrum(phantom(N), N), kre = sp.re, kim = sp.im;
    var kC = document.createElement("canvas"); kC.width = N; kC.height = N; kC.className = "diag-canvas";
    var iC = document.createElement("canvas"); iC.width = N; iC.height = N; iC.className = "diag-canvas";
    var kctx = kC.getContext("2d"), ictx = iC.getContext("2d");
    var readout = el("div", { class: "diag-readout" });
    function render(R) {
      var mre = kre.slice(), mim = kim.slice(), ky, kx;
      for (ky = 0; ky < N; ky++) {
        if (((ky - N / 2) % R + R) % R !== 0) { for (kx = 0; kx < N; kx++) { mre[ky * N + kx] = 0; mim[ky * N + kx] = 0; } }
      }
      drawKMag(kctx, mre, mim, N);
      reconMag(ictx, mre, mim, N);
      readout.textContent = R === 1 ? "Full sampling: no acceleration, the complete image."
        : "R = " + R + ": every " + (R === 2 ? "2nd" : "3rd") + " line kept, scan " + R + "x faster. The phase field of view drops to 1/" + R + ", so the image wraps.";
    }
    var stage = el("div", { class: "diag-kspace" });
    stage.appendChild(el("figure", { class: "diag-canvas-wrap" }, [kC, el("figcaption", { class: "diag-canvas-cap", text: "k-space" })]));
    stage.appendChild(el("figure", { class: "diag-canvas-wrap" }, [iC, el("figcaption", { class: "diag-canvas-cap", text: "image" })]));
    fig.appendChild(stage);
    var controls = el("div", { class: "diag-controls" });
    [["Full", 1], ["R = 2", 2], ["R = 3", 3]].forEach(function (p) {
      var b = el("button", { type: "button", class: "diag-btn" + (p[1] === 1 ? " on" : ""), text: p[0] });
      b.addEventListener("click", function () {
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (z) { z.classList.remove("on"); });
        b.classList.add("on"); render(p[1]);
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls); fig.appendChild(readout);
    render(1);
    return fig;
  }

  // ---- Widget: Gibbs (truncation) ringing ---- //
  function buildGibbsRinging() {
    var fig = figure("Gibbs ringing", "An image is built from a finite patch of k-space. Truncating the high frequencies (a smaller matrix) blurs sharp borders and adds faint ringing lines parallel to them, the Gibbs or truncation artifact.");
    var N = 64, sp = centeredSpectrum(phantom(N), N), kre = sp.re, kim = sp.im;
    var kC = document.createElement("canvas"); kC.width = N; kC.height = N; kC.className = "diag-canvas";
    var iC = document.createElement("canvas"); iC.width = N; iC.height = N; iC.className = "diag-canvas";
    var kctx = kC.getContext("2d"), ictx = iC.getContext("2d");
    var readout = el("div", { class: "diag-readout" });
    function render(keep) {
      var mre = kre.slice(), mim = kim.slice(), ky, kx, half = keep / 2;
      for (ky = 0; ky < N; ky++) {
        for (kx = 0; kx < N; kx++) {
          if (Math.abs(ky - N / 2) >= half || Math.abs(kx - N / 2) >= half) { mre[ky * N + kx] = 0; mim[ky * N + kx] = 0; }
        }
      }
      drawKMag(kctx, mre, mim, N);
      reconMag(ictx, mre, mim, N);
      readout.textContent = keep === N ? "Full matrix (" + N + "): sharp edges, no ringing."
        : "Matrix " + keep + ": only the central " + keep + "x" + keep + " of k-space is kept. Edges blur and ringing appears alongside them.";
    }
    var stage = el("div", { class: "diag-kspace" });
    stage.appendChild(el("figure", { class: "diag-canvas-wrap" }, [kC, el("figcaption", { class: "diag-canvas-cap", text: "k-space" })]));
    stage.appendChild(el("figure", { class: "diag-canvas-wrap" }, [iC, el("figcaption", { class: "diag-canvas-cap", text: "image" })]));
    fig.appendChild(stage);
    var controls = el("div", { class: "diag-controls" });
    controls.appendChild(el("span", { class: "diag-glabel", text: "Matrix:" }));
    [["64", 64], ["32", 32], ["16", 16]].forEach(function (p) {
      var b = el("button", { type: "button", class: "diag-btn" + (p[1] === 64 ? " on" : ""), text: p[0] });
      b.addEventListener("click", function () {
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (z) { z.classList.remove("on"); });
        b.classList.add("on"); render(p[1]);
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls); fig.appendChild(readout);
    render(64);
    return fig;
  }

  // ---- Widget: DSC signal-time curve (first-pass bolus tracking) ---- //
  function buildDscCurve() {
    var fig = figure("DSC signal-time curve", "DSC watches signal drop as the gadolinium bolus passes (T2* susceptibility), then recover; a second smaller dip is recirculation (1.5 T, approximate).");
    var xMax = 40;
    var state = { depth: 0.4 };
    var plot = makePlot({ xMax: xMax, yMax: 1, xLabel: "t (s)", yLabel: "signal",
      xTicks: [0, 10, 20, 30, 40], title: "DSC signal-time curve: first-pass bolus and recirculation" });
    plot.addAxes();
    plot.addMarker(10, "", "1st pass");
    var curve = null;
    var readout = el("div", { class: "diag-readout" });
    function redraw() {
      if (curve) curve.remove();
      var pts = M.sample(function (t) { return M.dscSignal(t, state.depth); }, xMax, 80);
      curve = plot.addCurve(pts, "");
      var nadir = Math.round(M.dscSignal(10, state.depth) * 100);
      readout.textContent = "Nadir signal at first pass: " + nadir + "% of baseline. A deeper drop means more blood volume (higher CBV), consistent with higher tumor grade.";
    }
    fig.appendChild(plot.svg);
    var controls = el("div", { class: "diag-controls" });
    controls.appendChild(el("span", { class: "diag-glabel", text: "Tissue:" }));
    [["Normal", 0.4], ["High-grade tumor", 0.85]].forEach(function (p) {
      var b = el("button", { type: "button", class: "diag-btn" + (p[1] === state.depth ? " on" : ""), text: p[0] });
      b.addEventListener("click", function () {
        state.depth = p[1];
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (x) { x.classList.remove("on"); });
        b.classList.add("on");
        redraw();
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls);
    fig.appendChild(readout);
    redraw();
    return fig;
  }

  // ---- Widget: ASL label minus control (perfusion without contrast) ---- //
  // Builds the three teaching images: control (base), label (base with a small
  // perfusion-related drop in the cortical rim), and their difference (the
  // perfusion signal that subtraction recovers).
  function aslImages(N) {
    var control = new Array(N * N), label = new Array(N * N), diff = new Array(N * N);
    var cx = N / 2, cy = N / 2, discR = N * 0.34, rimInner = N * 0.26, perf = 0.06;
    var x, y;
    for (y = 0; y < N; y++) {
      for (x = 0; x < N; x++) {
        var dx = x - cx, dy = y - cy, r = Math.sqrt(dx * dx + dy * dy);
        var inDisc = r < discR, inRim = inDisc && r >= rimInner;
        var v = inDisc ? 0.5 : 0.05;
        if (inRim) v = 0.6;
        var idx = y * N + x;
        control[idx] = v;
        label[idx] = inRim ? v - perf : v;
        diff[idx] = control[idx] - label[idx];
      }
    }
    return { control: control, label: label, diff: diff };
  }
  function buildAslSubtraction() {
    var fig = figure("ASL control minus label", "ASL subtracts the labeled image from the control image; static tissue cancels and only blood delivered to tissue (perfusion) remains, so no contrast agent is needed.");
    var N = 64, imgs = aslImages(N);
    function panel(arr, caption) {
      var c = document.createElement("canvas"); c.width = N; c.height = N; c.className = "diag-canvas";
      drawGray(c.getContext("2d"), arr, N);
      return el("figure", { class: "diag-canvas-wrap" }, [c, el("figcaption", { class: "diag-canvas-cap", text: caption })]);
    }
    var stage = el("div", { class: "diag-kspace" });
    stage.appendChild(panel(imgs.label, "label"));
    stage.appendChild(panel(imgs.control, "control"));
    stage.appendChild(panel(imgs.diff, "control - label"));
    fig.appendChild(stage);
    return fig;
  }

  // ---- Widget: phase-contrast VENC and velocity aliasing ---- //
  function buildPcVenc() {
    var fig = figure("PC VENC and aliasing", "PC measures velocity by phase; above the VENC the phase wraps, so fast flow aliases and reads reversed (1.5 T, approximate).");
    var xMax = 300, truePeak = 220;
    var state = { venc: 150 };
    var plot = makePlot({ xMax: xMax, yMin: -300, yMax: 300, xLabel: "true velocity (cm/s)", yLabel: "measured",
      xTicks: [0, 100, 200, 300], yTicks: [-300, -150, 0, 150, 300], title: "PC velocity aliasing versus VENC" });
    plot.addAxes();
    var curve = null, marker = null, dot = null;
    var readout = el("div", { class: "diag-readout" });
    function redraw() {
      if (curve) curve.remove(); if (marker) marker.remove(); if (dot) dot.remove();
      var pts = M.sample(function (v) { return M.aliasedVelocity(v, state.venc); }, xMax, 120);
      curve = plot.addCurve(pts, "");
      marker = plot.addMarker(truePeak, "", "peak");
      var measured = M.aliasedVelocity(truePeak, state.venc);
      dot = plot.addDot(truePeak, measured, "");
      readout.textContent = truePeak > state.venc
        ? "True peak " + truePeak + " cm/s exceeds VENC " + state.venc + " cm/s: phase wraps, so the measured value reads " + Math.round(measured) + " cm/s, a reversed (negative) reading that mimics reversed flow. Raise the VENC to fix it."
        : "True peak " + truePeak + " cm/s is within VENC " + state.venc + " cm/s: it reads correctly at " + Math.round(measured) + " cm/s.";
    }
    fig.appendChild(plot.svg);
    var controls = el("div", { class: "diag-controls" });
    controls.appendChild(el("span", { class: "diag-glabel", text: "VENC:" }));
    [["100", 100], ["150", 150], ["200", 200]].forEach(function (p) {
      var b = el("button", { type: "button", class: "diag-btn" + (p[1] === state.venc ? " on" : ""), text: p[0] + " cm/s" });
      b.addEventListener("click", function () {
        state.venc = p[1];
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (x) { x.classList.remove("on"); });
        b.classList.add("on");
        redraw();
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls);
    fig.appendChild(readout);
    redraw();
    return fig;
  }

  // ---- Widget: TOF inflow and saturation ---- //
  function buildTofInflow() {
    var fig = figure("TOF inflow and saturation", "TOF brightness comes from fresh unsaturated blood replacing saturated spins; slow flow saturates (1.5 T, approximate).");
    var xMax = 30, slowFlow = 5;
    var state = { vFull: 8 };
    var plot = makePlot({ xMax: xMax, yMax: 1, xLabel: "flow velocity (cm/s)", yLabel: "TOF signal",
      xTicks: [0, 10, 20, 30], title: "Time-of-flight signal versus flow velocity" });
    plot.addAxes();
    var curve = null, marker = null, dot = null;
    var readout = el("div", { class: "diag-readout" });
    function redraw() {
      if (curve) curve.remove(); if (marker) marker.remove(); if (dot) dot.remove();
      var pts = M.sample(function (v) { return M.tofSignal(v, state.vFull); }, xMax, 120);
      curve = plot.addCurve(pts, "");
      marker = plot.addMarker(slowFlow, "", "slow");
      var sig = M.tofSignal(slowFlow, state.vFull);
      dot = plot.addDot(slowFlow, sig, "");
      readout.textContent = "Slow or in-plane flow at " + slowFlow + " cm/s stays in the slab and saturates, so it reads dark ("
        + Math.round(sig * 100) + "% signal) and can mimic stenosis. A thinner slab recovers slow flow, reaching full signal at a lower velocity.";
    }
    fig.appendChild(plot.svg);
    var controls = el("div", { class: "diag-controls" });
    controls.appendChild(el("span", { class: "diag-glabel", text: "Slab:" }));
    [["Thin", 8], ["Thick", 20]].forEach(function (p) {
      var b = el("button", { type: "button", class: "diag-btn" + (p[1] === state.vFull ? " on" : ""), text: p[0] });
      b.addEventListener("click", function () {
        state.vFull = p[1];
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (x) { x.classList.remove("on"); });
        b.classList.add("on");
        redraw();
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls);
    fig.appendChild(readout);
    redraw();
    return fig;
  }

  // ---- Widget: FA / diffusion ellipsoid ---- //
  function buildFaAnisotropy() {
    var fig = figure("FA anisotropy", "The diffusion tensor per voxel, summarized by fractional anisotropy (FA): the ellipsoid is round when diffusion is isotropic and stretched along the fiber when anisotropic.");
    var W = 200, H = 160, cx = W / 2, cy = H / 2, R = 34;
    var svg = svgEl("svg", { class: "diag-svg", viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": "Diffusion ellipsoid cross section" });
    svg.style.maxWidth = "240px";
    var ellipse = null;
    var state = { fa: 0 };
    var readout = el("div", { class: "diag-readout" });
    function draw() {
      if (ellipse) ellipse.remove();
      var rx = R * (1 + 1.4 * state.fa), ry = R * (1 - 0.7 * state.fa);
      ellipse = svgEl("ellipse", { cx: cx, cy: cy, rx: rx.toFixed(1), ry: ry.toFixed(1),
        fill: "#5db0ef", "fill-opacity": "0.5", stroke: "#5db0ef" });
      svg.appendChild(ellipse);
      var shape = state.fa === 0 ? "round: diffusion is isotropic, equal in every direction."
        : "stretched along one axis: diffusion is anisotropic.";
      readout.textContent = "FA " + state.fa.toFixed(1) + ": the cross section is " + shape
        + " FA measures how directional water diffusion is: 0 is isotropic (equal in all directions, like CSF), near 1 is strongly one-directional (a dense, coherent tract).";
    }
    fig.appendChild(svg);
    var controls = el("div", { class: "diag-controls" });
    [["CSF (FA 0)", 0], ["Gray matter (FA 0.2)", 0.2], ["White matter (FA 0.8)", 0.8]].forEach(function (p, i) {
      var b = el("button", { type: "button", class: "diag-btn" + (i === 0 ? " on" : ""), text: p[0] });
      b.addEventListener("click", function () {
        state.fa = p[1];
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (x) { x.classList.remove("on"); });
        b.classList.add("on");
        draw();
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls);
    fig.appendChild(readout);
    draw();
    return fig;
  }

  // ---- Widget: DTI tractography streamlines ---- //
  function buildTractography() {
    var fig = figure("Tractography streamlines", "Streamlines follow the principal diffusion direction voxel to voxel; they are a model, not a photograph, and crossing fibers can mislead them.");
    var W = 260, H = 180, bow = 36;
    var svg = svgEl("svg", { class: "diag-svg", viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": "Tractography streamlines" });
    svg.style.maxWidth = "280px";
    var g = svgEl("g", {});
    svg.appendChild(g);
    var SEEDS = [20, 48, 76, 104, 132, 160];
    // Small spread of endpoint jitter for the probabilistic fan around each seed's core path.
    var FAN_OFFSETS = [[-12, -16, -10], [-6, -8, -5], [0, 2, 1], [6, 8, 5], [12, 16, 10]];
    var state = { mode: "deterministic" };
    var readout = el("div", { class: "diag-readout" });
    function pathD(y0, dyStart, dyMid, dyEnd) {
      return "M 12 " + (y0 + dyStart) + " C 90 " + (y0 - bow + dyMid) + ", 170 " + (y0 - bow + dyMid) + ", 248 " + (y0 + dyEnd);
    }
    function draw() {
      while (g.firstChild) g.removeChild(g.firstChild);
      SEEDS.forEach(function (y0) {
        if (state.mode === "deterministic") {
          g.appendChild(svgEl("path", { d: pathD(y0, 0, 0, 0), fill: "none", stroke: "#5db0ef", "stroke-width": "2" }));
        } else {
          FAN_OFFSETS.forEach(function (o) {
            g.appendChild(svgEl("path", { d: pathD(y0, o[0], o[1], o[2]), fill: "none",
              stroke: "#5db0ef", "stroke-width": "1.2", "stroke-opacity": "0.35" }));
          });
        }
      });
      readout.textContent = state.mode === "deterministic"
        ? "Deterministic tractography follows a single best direction per voxel: one path per seed."
        : "Probabilistic tractography samples many possible directions and shows confidence as streamline density.";
    }
    fig.appendChild(svg);
    var controls = el("div", { class: "diag-controls" });
    [["Deterministic", "deterministic"], ["Probabilistic", "probabilistic"]].forEach(function (p) {
      var b = el("button", { type: "button", class: "diag-btn" + (p[1] === state.mode ? " on" : ""), text: p[0] });
      b.addEventListener("click", function () {
        state.mode = p[1];
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (z) { z.classList.remove("on"); });
        b.classList.add("on");
        draw();
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls);
    fig.appendChild(readout);
    draw();
    return fig;
  }

  // ---- Widget: LGE inversion-time nulling ---- //
  function buildLgeNulling() {
    var fig = figure("LGE nulling", "Late gadolinium enhancement uses an inversion pulse, with TI set to null normal myocardium so it goes dark. Scar retains gadolinium, has a shorter T1, recovers faster and stays bright. Normal myocardium grey, scar red. Post-contrast, approximate.");
    var normalT1 = 400, scarT1 = 260;   // post-gadolinium T1 (ms), teaching approximations
    var xMax = 800;
    var goodTI = Math.round(M.nullTI(normalT1));
    var state = { ti: goodTI };
    var plot = makePlot({ xMax: xMax, yMin: -1, yMax: 1, xLabel: "TI (ms)", yLabel: "Mz",
      xTicks: [0, 200, 400, 600, 800], yTicks: [-1, -0.5, 0, 0.5, 1],
      title: "Inversion-recovery nulling of normal myocardium versus scar" });
    plot.addAxes();
    plot.addCurve(M.sample(function (t) { return M.irMz(t, normalT1); }, xMax, 80), "pd");
    plot.addCurve(M.sample(function (t) { return M.irMz(t, scarT1); }, xMax, 80), "alt");
    var marker = null;
    var readout = el("div", { class: "diag-readout" });
    function pct(t1) { return Math.round(Math.abs(M.irMz(state.ti, t1)) * 100); }
    function redraw() {
      if (marker) marker.remove();
      marker = plot.addMarker(state.ti, "", "TI");
      var msg;
      if (state.ti === goodTI) msg = "Normal myocardium is nulled (dark) and scar stays bright: maximum contrast.";
      else if (state.ti < goodTI) msg = "TI too short: normal myocardium is not yet nulled, and scar can approach its own null, so a real scar may disappear.";
      else msg = "TI too long: normal myocardium has recovered and is no longer dark, so scar stands out less.";
      readout.textContent = "At TI " + state.ti + " ms the displayed signal is normal myocardium " + pct(normalT1) + "%, scar " + pct(scarT1) + "%. " + msg;
    }
    fig.appendChild(plot.svg);
    var controls = el("div", { class: "diag-controls" });
    controls.appendChild(el("span", { class: "diag-glabel", text: "TI:" }));
    [["Null normal", goodTI], ["Too short", 180], ["Too long", 500]].forEach(function (p) {
      var b = el("button", { type: "button", class: "diag-btn" + (p[1] === state.ti ? " on" : ""), text: p[0] });
      b.addEventListener("click", function () {
        state.ti = p[1];
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (x) { x.classList.remove("on"); });
        b.classList.add("on");
        redraw();
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls);
    fig.appendChild(readout);
    redraw();
    return fig;
  }

  // ---- Widget: cardiac gating timeline ---- //
  function buildCardiacGating() {
    var fig = figure("Cardiac gating", "Data are synchronized to the ECG R-wave. Prospective triggering acquires a fixed window after each R-wave and leaves a gap at end-diastole; retrospective gating samples the whole R-R interval and sorts the data by cardiac phase afterward.");
    var W = 320, H = 150;
    var svg = svgEl("svg", { class: "diag-svg", viewBox: "0 0 " + W + " " + H,
      role: "img", "aria-label": "ECG-gated acquisition timeline" });
    var RS = [25, 110, 195, 280], RR = 85, baseY = 46, spikeY = 20, barY = 78, barH = 24;
    svg.appendChild(svgEl("line", { class: "diag-axis", x1: 10, y1: baseY, x2: 310, y2: baseY }));
    RS.forEach(function (rx) {
      svg.appendChild(svgEl("polyline", { class: "diag-curve", fill: "none",
        points: (rx - 5) + "," + baseY + " " + rx + "," + spikeY + " " + (rx + 5) + "," + baseY }));
      var t = svgEl("text", { class: "diag-axtext", x: rx, y: spikeY - 4, "text-anchor": "middle" });
      t.textContent = "R"; svg.appendChild(t);
    });
    var g = svgEl("g", {});
    svg.appendChild(g);
    var state = { mode: "prospective" };
    var readout = el("div", { class: "diag-readout" });
    function draw() {
      while (g.firstChild) g.removeChild(g.firstChild);
      for (var i = 0; i < 3; i++) {
        var x0 = RS[i], x1 = RS[i + 1];
        if (state.mode === "prospective") {
          var accW = RR * 0.72;
          g.appendChild(svgEl("rect", { x: x0 + 2, y: barY, width: accW.toFixed(1), height: barH,
            fill: "#5db0ef", "fill-opacity": "0.55", stroke: "#5db0ef" }));
          g.appendChild(svgEl("rect", { x: (x0 + 2 + accW).toFixed(1), y: barY,
            width: (x1 - x0 - 2 - accW).toFixed(1), height: barH,
            fill: "none", stroke: "#e0554e", "stroke-dasharray": "3 2" }));
        } else {
          g.appendChild(svgEl("rect", { x: x0, y: barY, width: RR, height: barH,
            fill: "#5db0ef", "fill-opacity": "0.55", stroke: "#5db0ef" }));
        }
      }
      var lbl = svgEl("text", { class: "diag-axtext", x: 160, y: barY + barH + 16, "text-anchor": "middle" });
      lbl.textContent = state.mode === "prospective"
        ? "Blue = acquired. Red dashed = end-diastole, not sampled."
        : "Blue = acquired: the entire cardiac cycle.";
      g.appendChild(lbl);
      readout.textContent = state.mode === "prospective"
        ? "Prospective triggering fires a fixed acquisition window after each R-wave, then waits for the next trigger. The gap at end-diastole is not imaged, so it can miss true end-diastole."
        : "Retrospective gating acquires continuously across every R-R interval and tags each line by its cardiac phase, reconstructing the full cycle including end-diastole. It also tolerates mild arrhythmia by rejecting outlier beats.";
    }
    fig.appendChild(svg);
    var controls = el("div", { class: "diag-controls" });
    [["Prospective", "prospective"], ["Retrospective", "retrospective"]].forEach(function (p) {
      var b = el("button", { type: "button", class: "diag-btn" + (p[1] === state.mode ? " on" : ""), text: p[0] });
      b.addEventListener("click", function () {
        state.mode = p[1];
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (x) { x.classList.remove("on"); });
        b.classList.add("on");
        draw();
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls);
    fig.appendChild(readout);
    draw();
    return fig;
  }

  // ---- shared: draw a proton spectrum (reversed ppm axis) from a peak list ---- //
  // peaks: [{ ppm, amp (signed, ~ -0.5..1), label? }]. Returns nothing; draws into g.
  function drawSpectrum(g, peaks, opts) {
    while (g.firstChild) g.removeChild(g.firstChild);
    var x0 = 30, x1 = 305, baseY = opts.baseY, hScale = opts.hScale, PMAX = 4.0, sig = 0.07;
    function xOf(ppm) { return x0 + (x1 - x0) * ((PMAX - ppm) / PMAX); }
    // baseline
    g.appendChild(svgEl("line", { class: "diag-axis", x1: x0, y1: baseY, x2: x1, y2: baseY }));
    [4, 3, 2, 1, 0].forEach(function (p) {
      var t = svgEl("text", { class: "diag-axtext", x: xOf(p), y: baseY + 13, "text-anchor": "middle" });
      t.textContent = String(p); g.appendChild(t);
    });
    g.appendChild((function () {
      var t = svgEl("text", { class: "diag-axtext", x: (x0 + x1) / 2, y: baseY + 25, "text-anchor": "middle" });
      t.textContent = "chemical shift (ppm)"; return t;
    })());
    // sampled spectrum curve: sum of gaussians, amplitudes signed
    var pts = [];
    for (var i = 0; i <= 140; i++) {
      var ppm = PMAX - (PMAX * i) / 140;
      var amp = 0;
      peaks.forEach(function (pk) {
        var d = (ppm - pk.ppm) / sig;
        amp += pk.amp * Math.exp(-0.5 * d * d);
      });
      pts.push(xOf(ppm).toFixed(1) + " " + (baseY - amp * hScale).toFixed(1));
    }
    g.appendChild(svgEl("path", { class: "diag-curve", fill: "none", d: "M" + pts.join(" L") }));
    // peak labels
    peaks.forEach(function (pk) {
      if (!pk.label) return;
      var y = baseY - pk.amp * hScale + (pk.amp < 0 ? 12 : -4);
      var t = svgEl("text", { class: "diag-axtext", x: xOf(pk.ppm), y: y, "text-anchor": "middle" });
      t.textContent = pk.label; g.appendChild(t);
    });
  }

  // ---- Widget: MRS proton spectrum, normal vs tumor ---- //
  function buildMrsSpectrum() {
    var fig = figure("MR spectrum", "A proton spectrum plots signal against chemical shift in ppm, high ppm on the left. In tumor the choline peak (3.2) rises above NAA (2.0), NAA falls, and a lactate peak (1.3) can appear: the raised Cho/NAA ratio is the key sign.");
    var svg = svgEl("svg", { class: "diag-svg", viewBox: "0 0 320 180", role: "img", "aria-label": "Normal versus tumor MR spectrum" });
    var g = svgEl("g", {}); svg.appendChild(g);
    var NORMAL = [
      { ppm: 3.5, amp: 0.30 }, { ppm: 3.2, amp: 0.38, label: "Cho" }, { ppm: 3.0, amp: 0.52, label: "Cr" },
      { ppm: 2.0, amp: 0.90, label: "NAA" },
    ];
    var TUMOR = [
      { ppm: 3.5, amp: 0.35 }, { ppm: 3.2, amp: 0.90, label: "Cho" }, { ppm: 3.0, amp: 0.46, label: "Cr" },
      { ppm: 2.0, amp: 0.32, label: "NAA" }, { ppm: 1.3, amp: 0.42, label: "Lac" },
    ];
    var state = { mode: "normal" };
    var readout = el("div", { class: "diag-readout" });
    function redraw() {
      drawSpectrum(g, state.mode === "normal" ? NORMAL : TUMOR, { baseY: 120, hScale: 92 });
      readout.textContent = state.mode === "normal"
        ? "Normal brain: NAA at 2.0 ppm is the tallest peak, with moderate creatine (3.0) and choline (3.2) and no lactate."
        : "Tumor pattern: choline rises above NAA, NAA falls, and a lactate peak appears at 1.3 ppm. The elevated Cho/NAA ratio is the classic spectroscopic sign of neoplasm.";
    }
    fig.appendChild(svg);
    var controls = el("div", { class: "diag-controls" });
    [["Normal", "normal"], ["Tumor", "tumor"]].forEach(function (p) {
      var b = el("button", { type: "button", class: "diag-btn" + (p[1] === state.mode ? " on" : ""), text: p[0] });
      b.addEventListener("click", function () {
        state.mode = p[1];
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (x) { x.classList.remove("on"); });
        b.classList.add("on");
        redraw();
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls);
    fig.appendChild(readout);
    redraw();
    return fig;
  }

  // ---- Widget: lactate doublet inversion versus echo time ---- //
  function buildMrsTe() {
    var fig = figure("Lactate and TE", "The lactate doublet at 1.3 ppm is J-coupled, so its phase depends on echo time. It points up at short TE, inverts below the baseline at TE around 135 to 144 ms, and returns upright at 288 ms. This inversion confirms lactate rather than overlapping lipid.");
    var svg = svgEl("svg", { class: "diag-svg", viewBox: "0 0 320 180", role: "img", "aria-label": "Lactate inversion with echo time" });
    var g = svgEl("g", {}); svg.appendChild(g);
    var FIXED = [{ ppm: 3.2, amp: 0.42, label: "Cho" }, { ppm: 3.0, amp: 0.5, label: "Cr" }, { ppm: 2.0, amp: 0.7, label: "NAA" }];
    var LAC = { 35: 0.45, 144: -0.45, 288: 0.35 };
    var state = { te: 144 };
    var readout = el("div", { class: "diag-readout" });
    function redraw() {
      var peaks = FIXED.concat([{ ppm: 1.3, amp: LAC[state.te], label: "Lac" }]);
      drawSpectrum(g, peaks, { baseY: 95, hScale: 78 });
      readout.textContent = state.te === 35
        ? "Short TE (35 ms): the lactate doublet points up, alongside more metabolites and a rolling baseline."
        : state.te === 144
          ? "TE 135 to 144 ms: J-coupling inverts the lactate doublet below the baseline. A peak that inverts here is lactate, not lipid."
          : "TE 288 ms: the lactate doublet has rephased and points up again above the baseline.";
    }
    fig.appendChild(svg);
    var controls = el("div", { class: "diag-controls" });
    controls.appendChild(el("span", { class: "diag-glabel", text: "TE:" }));
    [["Short 35", 35], ["144 ms", 144], ["288 ms", 288]].forEach(function (p) {
      var b = el("button", { type: "button", class: "diag-btn" + (p[1] === state.te ? " on" : ""), text: p[0] });
      b.addEventListener("click", function () {
        state.te = p[1];
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (x) { x.classList.remove("on"); });
        b.classList.add("on");
        redraw();
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls);
    fig.appendChild(readout);
    redraw();
    return fig;
  }

  // ---- shared: canonical double-gamma hemodynamic response + convolution ---- //
  function hrf(t) {
    if (t <= 0) return 0;
    var N1 = Math.pow(5, 5) * Math.exp(-5), N2 = Math.pow(15, 15) * Math.exp(-15);
    return Math.pow(t, 5) * Math.exp(-t) / N1 - 0.15 * Math.pow(t, 15) * Math.exp(-t) / N2;
  }
  // Convolve a 0/1 stimulus (stimOn(t)) with the HRF over [0, tMax]. Returns [[t, v], ...].
  function convolveHrf(stimOn, tMax, dt) {
    var n = Math.round(tMax / dt), s = [], i, j;
    for (i = 0; i <= n; i++) s.push(stimOn(i * dt));
    var pts = [];
    for (j = 0; j <= n; j++) {
      var v = 0;
      for (i = 0; i <= j; i++) v += s[i] * hrf((j - i) * dt) * dt;
      pts.push([j * dt, v]);
    }
    return pts;
  }
  function maxV(pts) { return pts.reduce(function (m, p) { return Math.max(m, p[1]); }, 0); }
  function scalePts(pts, k) { return pts.map(function (p) { return [p[0], p[1] * k]; }); }

  // ---- Widget: BOLD hemodynamic response, brief event vs sustained block ---- //
  function buildBoldHrf() {
    var fig = figure("Hemodynamic response", "The BOLD signal follows neuronal activity with a delay: after a brief event it rises to a peak about 4 to 6 seconds later, then dips below baseline. A sustained block holds a plateau while the task is on. Each curve is scaled to its own peak.");
    var xMax = 30, dt = 0.5;
    var brief = convolveHrf(function (t) { return t >= 0 && t < 1 ? 1 : 0; }, xMax, dt);
    var block = convolveHrf(function (t) { return t >= 0 && t < 20 ? 1 : 0; }, xMax, dt);
    var curves = { brief: scalePts(brief, 1 / maxV(brief)), block: scalePts(block, 1 / maxV(block)) };
    var state = { mode: "brief" };
    var plot = makePlot({ xMax: xMax, yMin: -0.3, yMax: 1, xLabel: "time (s)", yLabel: "BOLD (rel.)",
      xTicks: [0, 5, 10, 15, 20, 25, 30], yTicks: [0, 0.5, 1], title: "Hemodynamic response versus time" });
    plot.addAxes();
    var curve = null, marker = null, readout = el("div", { class: "diag-readout" });
    function redraw() {
      if (curve) curve.remove();
      if (marker) marker.remove();
      curve = plot.addCurve(curves[state.mode], "");
      if (state.mode === "brief") {
        marker = plot.addMarker(5, "", "~5 s");
        readout.textContent = "Brief event: the response peaks about 5 seconds after the stimulus, then falls through baseline into a post-stimulus undershoot. The lag is why BOLD cannot resolve fast neural timing.";
      } else {
        marker = plot.addMarker(20, "", "task off");
        readout.textContent = "Sustained block: the response rises and holds a plateau while the task is on, then decays after it ends. The larger, steadier signal is why block designs give higher SNR for clinical mapping.";
      }
    }
    fig.appendChild(plot.svg);
    var controls = el("div", { class: "diag-controls" });
    [["Brief event", "brief"], ["Sustained block", "block"]].forEach(function (p) {
      var b = el("button", { type: "button", class: "diag-btn" + (p[1] === state.mode ? " on" : ""), text: p[0] });
      b.addEventListener("click", function () {
        state.mode = p[1];
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (x) { x.classList.remove("on"); });
        b.classList.add("on");
        redraw();
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls);
    fig.appendChild(readout);
    redraw();
    return fig;
  }

  // ---- Widget: block vs event-related design (predicted BOLD) ---- //
  function buildFmriDesign() {
    var fig = figure("Task designs", "The predicted BOLD signal is the task timing convolved with the hemodynamic response. A block design gives large, sustained responses; an event-related design gives smaller, separate responses but allows flexible trial sorting. Both scaled to the block peak.");
    var xMax = 60, dt = 0.5;
    function inAny(t, epochs) { for (var i = 0; i < epochs.length; i++) if (t >= epochs[i][0] && t < epochs[i][1]) return 1; return 0; }
    var BLOCK = [[5, 20], [35, 50]];
    var EVENTS = [6, 14, 22, 31, 39, 47, 54].map(function (s) { return [s, s + 1]; });
    var blockPts = convolveHrf(function (t) { return inAny(t, BLOCK); }, xMax, dt);
    var eventPts = convolveHrf(function (t) { return inAny(t, EVENTS); }, xMax, dt);
    var k = 1 / maxV(blockPts);
    var curves = { block: scalePts(blockPts, k), event: scalePts(eventPts, k) };
    var stim = { block: BLOCK, event: EVENTS };
    var state = { mode: "block" };
    var plot = makePlot({ xMax: xMax, yMin: -0.3, yMax: 1.1, xLabel: "time (s)", yLabel: "predicted BOLD",
      xTicks: [0, 15, 30, 45, 60], yTicks: [0, 0.5, 1], title: "Predicted BOLD for block versus event-related design" });
    plot.addAxes();
    var curve = null, boxes = null, readout = el("div", { class: "diag-readout" });
    function redraw() {
      if (curve) curve.remove();
      if (boxes) boxes.remove();
      boxes = svgEl("g", {});
      stim[state.mode].forEach(function (e) {
        boxes.appendChild(svgEl("rect", { x: plot.toX(e[0]).toFixed(1), y: plot.toY(-0.05).toFixed(1),
          width: (plot.toX(e[1]) - plot.toX(e[0])).toFixed(1), height: 8, fill: "#8a8f98", "fill-opacity": "0.5" }));
      });
      plot.svg.appendChild(boxes);
      curve = plot.addCurve(curves[state.mode], "");
      readout.textContent = state.mode === "block"
        ? "Block design: sustained task epochs (grey bars) produce large, well-separated BOLD responses with high statistical power, the robust choice for presurgical mapping."
        : "Event-related design: brief scattered events give smaller, overlapping responses. Power per event is lower, but trials can be sorted after the fact, such as by correct versus incorrect.";
    }
    fig.appendChild(plot.svg);
    var controls = el("div", { class: "diag-controls" });
    [["Block", "block"], ["Event-related", "event"]].forEach(function (p) {
      var b = el("button", { type: "button", class: "diag-btn" + (p[1] === state.mode ? " on" : ""), text: p[0] });
      b.addEventListener("click", function () {
        state.mode = p[1];
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (x) { x.classList.remove("on"); });
        b.classList.add("on");
        redraw();
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls);
    fig.appendChild(readout);
    redraw();
    return fig;
  }

  // ---- Widget: T2 relaxometry (multi-echo samples fit to a T2 value) ---- //
  function buildRelaxometry() {
    var fig = figure("T2 relaxometry", "A quantitative T2 map fits the signal measured at several echo times to an exponential decay. The fitted time constant is the tissue's T2 in milliseconds, an absolute value stored per pixel, not a brightness.");
    var TISSUES = [{ label: "Cartilage", t2: 40 }, { label: "Fluid / edema", t2: 200 }];
    var TES = [20, 60, 100, 150, 200];
    var xMax = 250, state = { i: 0 };
    var plot = makePlot({ xMax: xMax, yMax: 1, xLabel: "echo time TE (ms)", yLabel: "signal",
      xTicks: [0, 50, 100, 150, 200, 250], title: "Multi-echo decay fit to a T2 value" });
    plot.addAxes();
    var curve = null, dots = null, readout = el("div", { class: "diag-readout" });
    function redraw() {
      if (curve) curve.remove();
      if (dots) dots.remove();
      var t2 = TISSUES[state.i].t2;
      curve = plot.addCurve(M.sample(function (te) { return M.mxy(te, t2); }, xMax, 80), state.i === 0 ? "" : "alt");
      dots = svgEl("g", {});
      TES.forEach(function (te) {
        dots.appendChild(svgEl("circle", { class: "diag-dot", cx: plot.toX(te).toFixed(1),
          cy: plot.toY(M.mxy(te, t2)).toFixed(1), r: 3 }));
      });
      plot.svg.appendChild(dots);
      readout.textContent = "Fitting the sampled echoes (dots) to an exponential gives T2 = " + t2 + " ms for " + TISSUES[state.i].label
        + ". That number is the map's pixel value; a healthy and a degenerating tissue differ by their measured T2, not by window settings.";
    }
    fig.appendChild(plot.svg);
    var controls = el("div", { class: "diag-controls" });
    controls.appendChild(el("span", { class: "diag-glabel", text: "Tissue:" }));
    TISSUES.forEach(function (t, i) {
      var b = el("button", { type: "button", class: "diag-btn" + (i === state.i ? " on" : ""), text: t.label });
      b.addEventListener("click", function () {
        state.i = i;
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (x) { x.classList.remove("on"); });
        b.classList.add("on");
        redraw();
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls);
    fig.appendChild(readout);
    redraw();
    return fig;
  }

  // ---- Widget: R2* and iron loading ---- //
  function buildR2starIron() {
    var fig = figure("R2* and iron", "Iron is paramagnetic, so it distorts the local field and shortens T2*. R2* (equal to 1000/T2* in units per second) rises with iron, which is the basis of noninvasive liver iron quantification. Faster decay means a higher R2*.");
    var LEVELS = [{ label: "Normal", t2s: 25 }, { label: "Moderate iron", t2s: 12 }, { label: "Heavy iron", t2s: 5 }];
    var xMax = 40, state = { i: 0 };
    var plot = makePlot({ xMax: xMax, yMax: 1, xLabel: "echo time TE (ms)", yLabel: "signal",
      xTicks: [0, 10, 20, 30, 40], title: "T2* decay and R2* versus iron loading" });
    plot.addAxes();
    var curve = null, readout = el("div", { class: "diag-readout" });
    function redraw() {
      if (curve) curve.remove();
      var t2s = LEVELS[state.i].t2s;
      curve = plot.addCurve(M.sample(function (te) { return M.mxy(te, t2s); }, xMax, 80), state.i === 0 ? "" : (state.i === 1 ? "pd" : "alt"));
      var r2s = Math.round(1000 / t2s);
      readout.textContent = LEVELS[state.i].label + ": T2* = " + t2s + " ms, so R2* = " + r2s
        + " per second. More iron shortens T2* and raises R2*, so a high R2* means a heavier iron burden.";
    }
    fig.appendChild(plot.svg);
    var controls = el("div", { class: "diag-controls" });
    controls.appendChild(el("span", { class: "diag-glabel", text: "Iron:" }));
    LEVELS.forEach(function (lv, i) {
      var b = el("button", { type: "button", class: "diag-btn" + (i === state.i ? " on" : ""), text: lv.label });
      b.addEventListener("click", function () {
        state.i = i;
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (x) { x.classList.remove("on"); });
        b.classList.add("on");
        redraw();
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls);
    fig.appendChild(readout);
    redraw();
    return fig;
  }

  // ---- Widget: breast DCE kinetic curve types (BI-RADS) ---- //
  function buildDceKinetics() {
    var fig = figure("DCE kinetic curves", "Dynamic contrast-enhanced signal versus time after gadolinium. Type 1 (persistent) keeps climbing; type 2 (plateau) rises then flattens; type 3 (washout) rises fast then declines. Type 1 accent, type 2 grey, type 3 orange.");
    var xMax = 8;
    function type1(t) { return 0.1 + 0.5 * (1 - Math.exp(-t / 6)); }
    function type2(t) { var tp = Math.min(t, 2); return 0.85 * (1 - Math.exp(-tp / 0.9)); }
    function type3(t) { return Math.max(0.05, 0.95 * (1 - Math.exp(-t / 0.5)) - 0.09 * t); }
    var plot = makePlot({ xMax: xMax, yMax: 1, xLabel: "time (min)", yLabel: "signal",
      xTicks: [0, 2, 4, 6, 8], title: "Breast DCE kinetic curve types" });
    plot.addAxes();
    plot.addCurve(M.sample(type1, xMax, 80), "");
    plot.addCurve(M.sample(type2, xMax, 80), "pd");
    plot.addCurve(M.sample(type3, xMax, 80), "alt");
    var g = svgEl("g", {});
    [[7, type1(7), "Type 1"], [4, type2(4) + 0.06, "Type 2"], [2.6, type3(2.6) - 0.09, "Type 3"]].forEach(function (p) {
      var t = svgEl("text", { class: "diag-axtext", x: plot.toX(p[0]).toFixed(1), y: plot.toY(p[1]).toFixed(1), "text-anchor": "middle" });
      t.textContent = p[2]; g.appendChild(t);
    });
    plot.svg.appendChild(g);
    fig.appendChild(plot.svg);
    var readout = el("div", { class: "diag-readout",
      text: "Type 1 (persistent, steady rise) is typically benign. Type 2 (plateau) is indeterminate and often needs biopsy. Type 3 (washout, rise then decline) is suspicious for malignancy." });
    fig.appendChild(readout);
    return fig;
  }

  // ---- Widget: background parenchymal enhancement across the menstrual cycle ---- //
  function buildBpeCycle() {
    var fig = figure("BPE across the cycle", "Background parenchymal enhancement (BPE) rises and falls with hormonal state across the menstrual cycle, lowest in the second week and highest premenstrually.");
    var xMax = 28;
    function bpeLevel(day) {
      var base = 0.55;
      var dip = 0.35 * Math.exp(-Math.pow((day - 10.5) / 5, 2));
      var premenstrual = 0.35 * Math.exp(-Math.pow((day - 26) / 4, 2));
      return Math.min(1, Math.max(0.1, base - dip + premenstrual));
    }
    var plot = makePlot({ xMax: xMax, yMax: 1, xLabel: "cycle day", yLabel: "BPE level",
      xTicks: [0, 7, 14, 21, 28], title: "Background parenchymal enhancement versus cycle day" });
    plot.addAxes();
    plot.addCurve(M.sample(bpeLevel, xMax, 80), "");
    plot.addMarker(10, "", "week 2");
    fig.appendChild(plot.svg);
    var readout = el("div", { class: "diag-readout",
      text: "BPE is lowest in the second week of the cycle (about days 7 to 14) and rises again premenstrually. Screening breast MRI is best scheduled in week 2, when background enhancement is least likely to obscure or mimic a lesion." });
    fig.appendChild(readout);
    return fig;
  }

  // ---- Widget: prostate zonal anatomy (axial schematic) ---- //
  function buildProstateZones() {
    var fig = figure("Prostate zonal anatomy", "Axial schematic of prostate zonal anatomy: the peripheral zone (PZ) forms the posterior rim, the transition zone (TZ) surrounds the urethra centrally. Toggle a zone to see its extent and clinical relevance.");
    var W = 260, H = 180, cx = 130, cy = 95;
    var svg = svgEl("svg", { class: "diag-svg", viewBox: "0 0 " + W + " " + H,
      role: "img", "aria-label": "Axial prostate zonal anatomy schematic" });
    svg.style.maxWidth = "280px";
    var pz = svgEl("ellipse", { cx: cx, cy: cy, rx: 72, ry: 52, "fill-opacity": "0.25" });
    var tz = svgEl("ellipse", { cx: cx, cy: cy - 10, rx: 34, ry: 30, "fill-opacity": "0.25" });
    var capsule = svgEl("ellipse", { class: "diag-axis", cx: cx, cy: cy, rx: 72, ry: 52, fill: "none" });
    var urethra = svgEl("circle", { cx: cx, cy: cy - 10, r: 3, fill: "#e6edf3" });
    svg.appendChild(pz); svg.appendChild(tz); svg.appendChild(capsule); svg.appendChild(urethra);
    var lblPZ = svgEl("text", { class: "diag-axtext", x: cx, y: cy + 42, "text-anchor": "middle" });
    lblPZ.textContent = "PZ"; svg.appendChild(lblPZ);
    var lblTZ = svgEl("text", { class: "diag-axtext", x: cx, y: cy + 6, "text-anchor": "middle" });
    lblTZ.textContent = "TZ"; svg.appendChild(lblTZ);
    var state = { zone: "pz" };
    var readout = el("div", { class: "diag-readout" });
    function redraw() {
      var onFill = "#5db0ef", onOp = "0.55", offFill = "#8a8f98", offOp = "0.2";
      pz.setAttribute("fill", state.zone === "pz" ? onFill : offFill);
      pz.setAttribute("fill-opacity", state.zone === "pz" ? onOp : offOp);
      pz.setAttribute("stroke", state.zone === "pz" ? onFill : offFill);
      tz.setAttribute("fill", state.zone === "tz" ? onFill : offFill);
      tz.setAttribute("fill-opacity", state.zone === "tz" ? onOp : offOp);
      tz.setAttribute("stroke", state.zone === "tz" ? onFill : offFill);
      readout.textContent = state.zone === "pz"
        ? "Peripheral zone (PZ): the posterior rim, about 70% of gland volume. Most prostate cancers arise here. It is T2-bright, and diffusion-weighted imaging is the dominant sequence for detection."
        : "Transition zone (TZ): surrounds the urethra centrally and enlarges with benign prostatic hyperplasia (BPH). T2-weighted imaging is the dominant sequence here, since BPH nodules produce heterogeneous signal that diffusion alone cannot reliably sort out.";
    }
    fig.appendChild(svg);
    var controls = el("div", { class: "diag-controls" });
    [["Peripheral zone", "pz"], ["Transition zone", "tz"]].forEach(function (p) {
      var b = el("button", { type: "button", class: "diag-btn" + (p[1] === state.zone ? " on" : ""), text: p[0] });
      b.addEventListener("click", function () {
        state.zone = p[1];
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (x) { x.classList.remove("on"); });
        b.classList.add("on");
        redraw();
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls);
    fig.appendChild(readout);
    redraw();
    return fig;
  }

  // ---- Widget: prostate DWI signal by tissue/ADC ---- //
  function buildProstateDwi() {
    var fig = figure("Prostate DWI and ADC", "Diffusion-weighted signal versus b-value in the prostate. Restricted diffusion (low ADC) in tumor stays brightest at high b-value while free fluid darkens fastest. Tumor orange, normal peripheral zone accent, urine/cyst grey.");
    var xMax = 1400;
    var TISSUES = [
      { label: "Tumor", adc: 0.0007, cls: "alt" },
      { label: "Normal PZ", adc: 0.0015, cls: "" },
      { label: "Urine/cyst", adc: 0.0030, cls: "pd" },
    ];
    var state = { b: 1400 };
    var plot = makePlot({ xMax: xMax, yMax: 1, xLabel: "b-value (s/mm2)", yLabel: "signal",
      xTicks: [0, 350, 700, 1050, 1400], title: "Prostate diffusion signal versus b-value" });
    plot.addAxes();
    TISSUES.forEach(function (t) {
      plot.addCurve(M.sample(function (b) { return M.dwiSignal(b, t.adc); }, xMax, 80), t.cls);
    });
    var marker = null;
    var readout = el("div", { class: "diag-readout" });
    function redraw() {
      if (marker) marker.remove();
      marker = plot.addMarker(state.b, "", "b");
      var parts = TISSUES.map(function (t) {
        return t.label + " " + Math.round(M.dwiSignal(state.b, t.adc) * 100) + "%"; });
      readout.textContent = "At b " + state.b + " s/mm2: " + parts.join(", ")
        + ". Restricted diffusion (low ADC) stays bright at high b-value, the signature of clinically significant prostate cancer.";
    }
    fig.appendChild(plot.svg);
    var controls = el("div", { class: "diag-controls" });
    controls.appendChild(el("span", { class: "diag-glabel", text: "b-value:" }));
    [0, 700, 1400].forEach(function (bv) {
      var b = el("button", { type: "button", class: "diag-btn" + (bv === state.b ? " on" : ""), text: String(bv) });
      b.addEventListener("click", function () {
        state.b = bv;
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (x) { x.classList.remove("on"); });
        b.classList.add("on");
        redraw();
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls);
    fig.appendChild(readout);
    redraw();
    return fig;
  }

  // ---- Widget: metal artifact width versus receiver bandwidth ---- //
  function buildMetalBandwidth() {
    var fig = figure("Bandwidth and metal artifact", "Metal distorts the local field, which misregisters signal along the frequency-encode direction. Raising receiver bandwidth narrows the frequency range each pixel covers, shrinking that misregistration and the resulting artifact.");
    var xMax = 600;
    function artifactWidth(bw) { return 1 / (1 + bw / 150); }
    var plot = makePlot({ xMax: xMax, yMax: 1, xLabel: "receiver bandwidth (Hz/px)", yLabel: "relative artifact width",
      xTicks: [0, 150, 300, 450, 600], title: "Metal artifact width versus receiver bandwidth" });
    plot.addAxes();
    plot.addCurve(M.sample(artifactWidth, xMax, 80), "");
    var state = { bw: 150 };
    var marker = null, dot = null;
    var readout = el("div", { class: "diag-readout" });
    function redraw() {
      if (marker) marker.remove(); if (dot) dot.remove();
      marker = plot.addMarker(state.bw, "", state.bw + " Hz/px");
      dot = plot.addDot(state.bw, artifactWidth(state.bw), "");
      readout.textContent = state.bw === 150
        ? "Low bandwidth spreads each metal-distorted voxel across a wider frequency range, producing more frequency misregistration and a larger geometric artifact."
        : "Higher bandwidth narrows the frequency range per pixel, so the same field distortion shifts protons a smaller distance and the metal artifact shrinks, at some cost in SNR.";
    }
    fig.appendChild(plot.svg);
    var controls = el("div", { class: "diag-controls" });
    [["Low BW", 150], ["High BW", 500]].forEach(function (p) {
      var b = el("button", { type: "button", class: "diag-btn" + (p[1] === state.bw ? " on" : ""), text: p[0] });
      b.addEventListener("click", function () {
        state.bw = p[1];
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (x) { x.classList.remove("on"); });
        b.classList.add("on");
        redraw();
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls);
    fig.appendChild(readout);
    redraw();
    return fig;
  }

  // ---- Widget: magic angle effect versus tendon fiber angle and TE ---- //
  function buildMagicAngle() {
    var fig = figure("Magic angle effect", "Near 55 degrees to B0, the dipolar coupling term in tendon and ligament collagen vanishes, T2 lengthens, and normally dark fibers falsely brighten on short-TE sequences. At long TE the artifact resolves.");
    var xMax = 90, magicDeg = 54.7;
    var state = { te: "short" };
    function sig(theta) {
      var bump = M.gauss(theta, magicDeg, 10);
      return state.te === "short" ? 0.15 + 0.75 * bump : 0.05 + 0.05 * bump;
    }
    var plot = makePlot({ xMax: xMax, yMax: 1, xLabel: "fiber angle to B0 (deg)", yLabel: "signal",
      xTicks: [0, 30, 55, 90], title: "Magic angle signal versus tendon fiber angle" });
    plot.addAxes();
    var curve = null, marker = null;
    var readout = el("div", { class: "diag-readout" });
    function redraw() {
      if (curve) curve.remove(); if (marker) marker.remove();
      curve = plot.addCurve(M.sample(sig, xMax, 90), "");
      marker = plot.addMarker(magicDeg, "", "55°");
      readout.textContent = state.te === "short"
        ? "Short TE: at the magic angle (about 55 degrees) collagen fibers falsely brighten, mimicking tendinosis or a partial tear."
        : "Long TE: tendon signal has decayed regardless of fiber angle, so the false bright focus at 55 degrees resolves. A finding that persists at long TE is real pathology, not the magic angle artifact.";
    }
    fig.appendChild(plot.svg);
    var controls = el("div", { class: "diag-controls" });
    [["Short TE", "short"], ["Long TE", "long"]].forEach(function (p) {
      var b = el("button", { type: "button", class: "diag-btn" + (p[1] === state.te ? " on" : ""), text: p[0] });
      b.addEventListener("click", function () {
        state.te = p[1];
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (x) { x.classList.remove("on"); });
        b.classList.add("on");
        redraw();
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls);
    fig.appendChild(readout);
    redraw();
    return fig;
  }

  // ---- Widget: MRCP heavily T2-weighted signal versus TE ---- //
  function buildMrcpTe() {
    var fig = figure("MRCP and echo time", "MRCP uses a very long TE. Bile and pancreatic-duct fluid have a long T2 and stay bright; solid liver and background tissue have a short T2 and have fully decayed, so only static fluid remains visible. Fluid accent, tissue orange.");
    var xMax = 1000, teMrcp = 800;
    var plot = makePlot({ xMax: xMax, yMax: 1, xLabel: "TE (ms)", yLabel: "signal",
      xTicks: [0, 250, 500, 750, 1000], title: "MRCP signal versus echo time" });
    plot.addAxes();
    plot.addCurve(M.sample(function (te) { return M.mxy(te, 1200); }, xMax, 80), "");
    plot.addCurve(M.sample(function (te) { return M.mxy(te, 45); }, xMax, 80), "alt");
    plot.addMarker(teMrcp, "", "MRCP");
    fig.appendChild(plot.svg);
    var readout = el("div", { class: "diag-readout",
      text: "At TE " + teMrcp + " ms, bile and duct fluid (T2 about 1200 ms) retain " + Math.round(M.mxy(teMrcp, 1200) * 100)
        + "% signal while solid tissue (T2 about 45 ms) has decayed to near zero. This very long TE is why heavily T2-weighted MRCP isolates bile and pancreatic-duct fluid and suppresses everything else." });
    fig.appendChild(readout);
    return fig;
  }

  // ---- Widget: hepatobiliary-phase gadoxetate uptake ---- //
  function buildHepatobiliaryPhase() {
    var fig = figure("Hepatobiliary phase uptake", "Gadoxetate is taken up by functioning hepatocytes through the OATP transporter, so normal liver and FNH gradually brighten toward a plateau by about 20 minutes, the hepatobiliary phase. Most metastases lack that transporter and stay dark.");
    var xMax = 25, hbpTime = 20;
    function liverSignal(t) { var tp = Math.min(t, hbpTime); return 0.85 * (1 - Math.exp(-tp / 6)); }
    function metSignal(t) { return 0.1 + 0.05 * (1 - Math.exp(-t / 10)); }
    var plot = makePlot({ xMax: xMax, yMax: 1, xLabel: "time (min)", yLabel: "signal",
      xTicks: [0, 5, 10, 15, 20, 25], title: "Hepatobiliary phase signal versus time" });
    plot.addAxes();
    plot.addCurve(M.sample(liverSignal, xMax, 80), "");
    plot.addCurve(M.sample(metSignal, xMax, 80), "alt");
    plot.addMarker(hbpTime, "", "HBP");
    fig.appendChild(plot.svg);
    var readout = el("div", { class: "diag-readout",
      text: "By about 20 minutes (the hepatobiliary phase), normal liver and FNH have taken up gadoxetate and brightened toward a plateau, while most metastases stay dark, giving strong lesion-to-liver contrast." });
    fig.appendChild(readout);
    return fig;
  }

  // ---- Widget: Larmor frequency versus field strength ---- //
  function buildLarmorField() {
    var fig = figure("Larmor frequency", "The Larmor frequency is the resonant frequency of a proton in a magnetic field: f = 42.58 MHz per tesla times B0. Every field strength has its own tuned RF frequency.");
    var GYRO = 42.58; // MHz per tesla, hydrogen
    function larmorFreq(b0) { return GYRO * b0; }
    var xMax = 7, yMax = 300;
    var plot = makePlot({ xMax: xMax, yMax: yMax, xLabel: "B0 (T)", yLabel: "frequency (MHz)",
      xTicks: [0, 1.5, 3, 7], yTicks: [0, 100, 200, 300], title: "Larmor frequency versus field strength" });
    plot.addAxes();
    plot.addCurve(M.sample(larmorFreq, xMax, 60), "");
    var state = { b0: 1.5 };
    var marker = null, dot = null;
    var readout = el("div", { class: "diag-readout" });
    function redraw() {
      if (marker) marker.remove(); if (dot) dot.remove();
      var f = larmorFreq(state.b0);
      marker = plot.addMarker(state.b0, "", state.b0 + "T");
      dot = plot.addDot(state.b0, f, "");
      readout.textContent = "At " + state.b0 + " T, protons resonate at " + f.toFixed(1)
        + " MHz. Larmor frequency scales linearly with field strength at 42.58 MHz per tesla.";
    }
    fig.appendChild(plot.svg);
    var controls = el("div", { class: "diag-controls" });
    [["1.5T", 1.5], ["3T", 3], ["7T", 7]].forEach(function (p) {
      var b = el("button", { type: "button", class: "diag-btn" + (p[1] === state.b0 ? " on" : ""), text: p[0] });
      b.addEventListener("click", function () {
        state.b0 = p[1];
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (x) { x.classList.remove("on"); });
        b.classList.add("on");
        redraw();
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls);
    fig.appendChild(readout);
    redraw();
    return fig;
  }

  // ---- Widget: gadolinium T1 shortening ---- //
  function buildGadT1() {
    var fig = figure("Gadolinium T1 shortening", "Gadolinium chelates shorten the T1 of nearby tissue. On a T1-weighted image, tissue whose Mz recovers faster appears brighter, which is why enhancing tissue lights up after contrast.");
    var xMax = 2000, nativeT1 = 1000, gadT1 = 300, tr = 500;
    var plot = makePlot({ xMax: xMax, yMax: 1, xLabel: "t (ms)", yLabel: "Mz",
      xTicks: [0, 500, 1000, 1500, 2000], title: "T1 recovery before and after gadolinium" });
    plot.addAxes();
    plot.addCurve(M.sample(function (t) { return M.mz(t, nativeT1); }, xMax, 60), "");
    plot.addCurve(M.sample(function (t) { return M.mz(t, gadT1); }, xMax, 60), "alt");
    plot.addMarker(tr, "", "TR");
    fig.appendChild(plot.svg);
    var native = Math.round(M.mz(tr, nativeT1) * 100);
    var post = Math.round(M.mz(tr, gadT1) * 100);
    var readout = el("div", { class: "diag-readout",
      text: "At TR " + tr + " ms, native tissue (T1 " + nativeT1 + " ms, accent curve) has recovered " + native
        + "% of Mz, while post-gadolinium tissue (T1 " + gadT1 + " ms, orange curve) has recovered " + post
        + "%. Gadolinium shortens T1 so enhanced tissue recovers faster and is brighter on T1-weighted images." });
    fig.appendChild(readout);
    return fig;
  }

  // ---- Widget: SAR versus flip angle and field strength ---- //
  function buildSarFlip() {
    var fig = figure("SAR and flip angle", "Specific absorption rate rises with the square of flip angle and the square of field strength, so small changes in either add up fast.");
    var xMax = 180, yMax = 4, flip = 90;
    var FIELDS = { "1.5T": 1, "3T": 4 };
    function sar(deg, factor) { return Math.pow(deg / 180, 2) * factor; }
    var plot = makePlot({ xMax: xMax, yMax: yMax, xLabel: "flip angle (deg)", yLabel: "relative SAR",
      xTicks: [0, 45, 90, 135, 180], yTicks: [0, 1, 2, 3, 4], title: "Relative SAR versus flip angle" });
    plot.addAxes();
    var state = { field: "1.5T" };
    var curve = null, marker = null, dot = null;
    var readout = el("div", { class: "diag-readout" });
    function redraw() {
      if (curve) curve.remove(); if (marker) marker.remove(); if (dot) dot.remove();
      var factor = FIELDS[state.field];
      curve = plot.addCurve(M.sample(function (deg) { return sar(deg, factor); }, xMax, 60), state.field === "3T" ? "alt" : "");
      marker = plot.addMarker(flip, "", flip + "°");
      dot = plot.addDot(flip, sar(flip, factor), "");
      readout.textContent = "At " + flip + " degrees flip angle on " + state.field + ", relative SAR is "
        + sar(flip, factor).toFixed(2) + ". SAR rises with the square of flip angle and the square of field strength, so 3T deposits about four times the RF power of 1.5T at the same flip.";
    }
    fig.appendChild(plot.svg);
    var controls = el("div", { class: "diag-controls" });
    [["1.5T", "1.5T"], ["3T", "3T"]].forEach(function (p) {
      var b = el("button", { type: "button", class: "diag-btn" + (p[1] === state.field ? " on" : ""), text: p[0] });
      b.addEventListener("click", function () {
        state.field = p[1];
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (x) { x.classList.remove("on"); });
        b.classList.add("on");
        redraw();
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls);
    fig.appendChild(readout);
    redraw();
    return fig;
  }

  // ---- Widget: DCE Ktrans, tissue permeability curves ---- //
  function buildDceKtrans() {
    var fig = figure("DCE and Ktrans", "Ktrans is the volume transfer constant describing how fast gadolinium leaks out of blood vessels into tissue. A leaky, high-permeability tumor has a high Ktrans and fills quickly; normal tissue fills slowly.");
    var xMax = 300, lowK = 0.006, highK = 0.03, tMark = 60;
    function conc(t, k) { return 1 - Math.exp(-k * t); }
    var plot = makePlot({ xMax: xMax, yMax: 1, xLabel: "t (s)", yLabel: "contrast concentration",
      xTicks: [0, 60, 120, 180, 240, 300], title: "Tissue contrast concentration versus time" });
    plot.addAxes();
    plot.addCurve(M.sample(function (t) { return conc(t, lowK); }, xMax, 80), "");
    plot.addCurve(M.sample(function (t) { return conc(t, highK); }, xMax, 80), "alt");
    plot.addMarker(tMark, "", tMark + "s");
    fig.appendChild(plot.svg);
    var lowPct = Math.round(conc(tMark, lowK) * 100), highPct = Math.round(conc(tMark, highK) * 100);
    var readout = el("div", { class: "diag-readout",
      text: "By " + tMark + " s, the low-Ktrans tissue (normal, accent curve) has filled to " + lowPct
        + "%, while the high-Ktrans tissue (leaky tumor, orange curve) has filled to " + highPct
        + "%. Ktrans is the volume transfer constant: a leaky tumor has a high Ktrans and fills faster, while normal tissue fills slowly." });
    fig.appendChild(readout);
    return fig;
  }

  // ---- Widget: CE-MRA bolus timing and the center of k-space ---- //
  function buildCemraBolus() {
    var fig = figure("CE-MRA bolus timing", "Contrast-enhanced MRA depends on the center of k-space being acquired while gadolinium concentration peaks in the artery. Toggle the acquisition window against the bolus curve to see what timing does to the scan.");
    var xMax = 40, peak = 18, sig = 4, winW = 6;
    function bolus(t) { return M.gauss(t, peak, sig); }
    var plot = makePlot({ xMax: xMax, yMax: 1, xLabel: "t (s)", yLabel: "arterial Gd concentration",
      xTicks: [0, 10, 20, 30, 40], title: "Arterial gadolinium bolus and the k-space acquisition window" });
    plot.addAxes();
    plot.addCurve(M.sample(bolus, xMax, 100), "");
    var WINDOWS = { well: peak - winW / 2, early: peak - 12 - winW / 2, late: peak + 12 - winW / 2 };
    var state = { mode: "well" };
    var band = null;
    var readout = el("div", { class: "diag-readout" });
    function redraw() {
      if (band) band.remove();
      var x0 = WINDOWS[state.mode];
      band = svgEl("rect", { x: plot.toX(x0).toFixed(1), y: plot.toY(1).toFixed(1),
        width: (plot.toX(x0 + winW) - plot.toX(x0)).toFixed(1), height: (plot.toY(0) - plot.toY(1)).toFixed(1),
        fill: "#5db0ef", "fill-opacity": "0.25", stroke: "#5db0ef" });
      plot.svg.appendChild(band);
      readout.textContent = state.mode === "well"
        ? "Well timed: the acquisition window covers the bolus peak, so the center of k-space is filled with maximum arterial signal and the artery is sharply bright."
        : state.mode === "early"
          ? "Too early: the window falls before the peak, so the center of k-space is acquired with low arterial concentration, giving weak arterial signal and ringing artifact."
          : "Too late: the window falls after the arterial peak, by which time contrast has recirculated into veins, giving venous contamination alongside the artery.";
    }
    fig.appendChild(plot.svg);
    var controls = el("div", { class: "diag-controls" });
    [["Well timed", "well"], ["Too early", "early"], ["Too late", "late"]].forEach(function (p) {
      var b = el("button", { type: "button", class: "diag-btn" + (p[1] === state.mode ? " on" : ""), text: p[0] });
      b.addEventListener("click", function () {
        state.mode = p[1];
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (x) { x.classList.remove("on"); });
        b.classList.add("on");
        redraw();
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls);
    fig.appendChild(readout);
    redraw();
    return fig;
  }

  // ---- Widget: pulse-sequence timing, spin echo versus gradient echo ---- //
  function buildPulseTiming() {
    var fig = figure("Pulse sequence timing", "A schematic timing diagram: RF, slice-select, phase-encode, and frequency-encode (readout) gradients, and the signal they produce, on a shared time axis. Spin echo uses a 180 degree refocusing pulse; gradient echo uses gradient reversal instead.");
    var W = 320, H = 200;
    var svg = svgEl("svg", { class: "diag-svg", viewBox: "0 0 " + W + " " + H,
      role: "img", "aria-label": "Pulse sequence timing diagram, spin echo versus gradient echo" });
    var X0 = 42, X1 = 312, TEND = 100;
    var RF = 26, GSL = 60, GPH = 94, GFR = 128, SIG = 172;
    function xOf(t) { return X0 + (X1 - X0) * (t / TEND); }
    [["RF", RF], ["Gslice", GSL], ["Gphase", GPH], ["Gfreq", GFR], ["Signal", SIG]].forEach(function (r) {
      svg.appendChild(svgEl("line", { class: "diag-axis", x1: X0 - 6, y1: r[1], x2: X1, y2: r[1] }));
      var t = svgEl("text", { class: "diag-axtext", x: 4, y: r[1] + 3, "text-anchor": "start" });
      t.textContent = r[0]; svg.appendChild(t);
    });
    var g = svgEl("g", {});
    svg.appendChild(g);
    function tri(cx, halfW, h, base) {
      return (cx - halfW).toFixed(1) + "," + base + " " + cx.toFixed(1) + "," + (base - h).toFixed(1)
        + " " + (cx + halfW).toFixed(1) + "," + base;
    }
    function label(x, y, txt) {
      var t = svgEl("text", { class: "diag-axtext", x: x.toFixed(1), y: y.toFixed(1), "text-anchor": "middle" });
      t.textContent = txt; return t;
    }
    function lobe(cx, halfW, h, base, cls) {
      return svgEl("rect", { x: (cx - halfW).toFixed(1), y: (base - h).toFixed(1),
        width: (2 * halfW).toFixed(1), height: h.toFixed(1), class: "diag-curve " + (cls || "") });
    }
    var state = { mode: "se" };
    var readout = el("div", { class: "diag-readout" });
    function draw() {
      while (g.firstChild) g.removeChild(g.firstChild);
      if (state.mode === "se") {
        var t90 = 6, t180 = 40, te = 80;
        g.appendChild(svgEl("polyline", { class: "diag-curve", fill: "none", points: tri(xOf(t90), 4, 14, RF) }));
        g.appendChild(label(xOf(t90), RF - 18, "90°"));
        g.appendChild(svgEl("polyline", { class: "diag-curve alt", fill: "none", points: tri(xOf(t180), 6, 20, RF) }));
        g.appendChild(label(xOf(t180), RF - 24, "180°"));
        g.appendChild(lobe(xOf(t90), 4, 10, GSL, ""));
        g.appendChild(lobe(xOf(t180), 5, 10, GSL, ""));
        g.appendChild(lobe(xOf(54), 5, 8, GPH, ""));
        g.appendChild(lobe(xOf(te), 11, 12, GFR, ""));
        g.appendChild(svgEl("polyline", { class: "diag-curve", fill: "none", points: tri(xOf(te), 9, 16, SIG) }));
        g.appendChild(label(xOf(te), SIG + 14, "TE"));
        readout.textContent = "Spin echo: a 90 degree pulse tips magnetization into the transverse plane, then a 180 degree pulse at TE/2 refocuses static field inhomogeneity, producing a true echo at TE under a single readout lobe. The 180 refocuses static dephasing, so spin echo signal reflects true T2.";
      } else {
        var tf = 6, teg = 34;
        g.appendChild(svgEl("polyline", { class: "diag-curve", fill: "none", points: tri(xOf(tf), 3, 7, RF) }));
        g.appendChild(label(xOf(tf), RF - 12, "α"));
        g.appendChild(lobe(xOf(tf), 3, 10, GSL, ""));
        g.appendChild(lobe(xOf(16), 5, 8, GPH, ""));
        g.appendChild(svgEl("rect", { x: xOf(10).toFixed(1), y: GFR.toFixed(1),
          width: (xOf(22) - xOf(10)).toFixed(1), height: "10", class: "diag-curve alt" }));
        g.appendChild(lobe(xOf(31), 9, 12, GFR, ""));
        g.appendChild(svgEl("polyline", { class: "diag-curve", fill: "none", points: tri(xOf(teg), 8, 16, SIG) }));
        g.appendChild(label(xOf(teg), SIG + 14, "TE"));
        readout.textContent = "Gradient echo: a single sub-90 degree flip excites the tissue, with no 180 degree refocusing pulse. The readout gradient reverses polarity, negative then positive (orange then accent), and that reversal itself forms the echo. Because static field inhomogeneity is never refocused, gradient echo signal reflects the faster T2*, not true T2.";
      }
    }
    fig.appendChild(svg);
    var controls = el("div", { class: "diag-controls" });
    [["Spin echo", "se"], ["Gradient echo", "gre"]].forEach(function (p) {
      var b = el("button", { type: "button", class: "diag-btn" + (p[1] === state.mode ? " on" : ""), text: p[0] });
      b.addEventListener("click", function () {
        state.mode = p[1];
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (x) { x.classList.remove("on"); });
        b.classList.add("on");
        draw();
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls);
    fig.appendChild(readout);
    draw();
    return fig;
  }

  // ---- Widget: MR safety, the ACR four-zone system ---- //
  function buildSafetyZones() {
    var fig = figure("MR safety zones", "The ACR four-zone system nests the public (Zone I) inward to the magnet room (Zone IV); each step tightens who may enter. The dashed 5-gauss line is the static fringe-field contour around the magnet, which on a shielded magnet stays within the magnet room.");
    var W = 320, H = 210, cx = W / 2, cy = H / 2;
    var svg = svgEl("svg", { class: "diag-svg", viewBox: "0 0 " + W + " " + H,
      role: "img", "aria-label": "ACR four-zone MRI safety diagram" });
    var ZONES = [
      { id: "I", w: 310, h: 196,
        text: "Zone I is the freely accessible public area outside the facility, such as the waiting room and parking area. Anyone may enter without screening." },
      { id: "II", w: 250, h: 158,
        text: "Zone II is the reception and screening interface between the public area and the controlled zones. Unscreened patients and visitors may be present here, but only under staff supervision while screening is completed." },
      { id: "III", w: 186, h: 118,
        text: "Zone III is the access-restricted controlled area next to the magnet room. Only MRI-screened staff and screened, prepped patients may enter, and ferromagnetic objects are kept out." },
      { id: "IV", w: 120, h: 84,
        text: "Zone IV is the magnet room itself, the highest hazard zone because the static field is always on. Only screened staff and the screened patient being imaged may enter, along with pre-screened MRI-safe or MRI-conditional equipment. The dashed 5-gauss line marks where the fringe field falls to 5 gauss (0.5 mT), the safety threshold for the public and for implants, and it must stay within this controlled area." },
    ];
    var rects = {};
    ZONES.forEach(function (z) {
      var r = svgEl("rect", { x: (cx - z.w / 2).toFixed(1), y: (cy - z.h / 2).toFixed(1),
        width: z.w, height: z.h, rx: 8, fill: "none", stroke: "#8a8f98", "stroke-width": "1.5" });
      svg.appendChild(r);
      rects[z.id] = r;
      var lbl = svgEl("text", { class: "diag-axtext", x: (cx - z.w / 2 + 4).toFixed(1),
        y: (cy - z.h / 2 + 10).toFixed(1), "text-anchor": "start" });
      lbl.textContent = "Zone " + z.id;
      svg.appendChild(lbl);
    });
    // 5-gauss line: dashed fringe-field contour hugging the magnet, contained within Zone IV.
    svg.appendChild(svgEl("ellipse", { cx: cx, cy: cy, rx: 40, ry: 28, fill: "none",
      stroke: "#e0554e", "stroke-width": "1", "stroke-dasharray": "4 3" }));
    var gaussLbl = svgEl("text", { class: "diag-axtext", x: cx, y: (cy + 39).toFixed(1), "text-anchor": "middle" });
    gaussLbl.textContent = "5-gauss line";
    svg.appendChild(gaussLbl);
    // magnet symbol at the center of Zone IV
    var magnet = svgEl("g", {});
    magnet.appendChild(svgEl("rect", { x: (cx - 20).toFixed(1), y: (cy - 9).toFixed(1),
      width: 40, height: 18, rx: 6, fill: "#5db0ef", "fill-opacity": "0.3", stroke: "#5db0ef" }));
    magnet.appendChild(svgEl("circle", { cx: cx, cy: cy, r: 8, fill: "none", stroke: "#5db0ef" }));
    var b0 = svgEl("text", { class: "diag-axtext", x: cx, y: (cy - 17).toFixed(1), "text-anchor": "middle" });
    b0.textContent = "B0 magnet";
    magnet.appendChild(b0);
    svg.appendChild(magnet);
    var state = { zone: "IV" };
    var readout = el("div", { class: "diag-readout" });
    function redraw() {
      ZONES.forEach(function (z) {
        var on = z.id === state.zone;
        rects[z.id].setAttribute("stroke", on ? "#5db0ef" : "#8a8f98");
        rects[z.id].setAttribute("stroke-width", on ? "2.5" : "1.5");
        rects[z.id].setAttribute("fill", on ? "#5db0ef" : "none");
        rects[z.id].setAttribute("fill-opacity", on ? "0.12" : "0");
      });
      readout.textContent = ZONES.filter(function (z) { return z.id === state.zone; })[0].text;
    }
    fig.appendChild(svg);
    var controls = el("div", { class: "diag-controls" });
    ["I", "II", "III", "IV"].forEach(function (id) {
      var b = el("button", { type: "button", class: "diag-btn" + (id === state.zone ? " on" : ""), text: "Zone " + id });
      b.addEventListener("click", function () {
        state.zone = id;
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (x) { x.classList.remove("on"); });
        b.classList.add("on");
        redraw();
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls);
    fig.appendChild(readout);
    redraw();
    return fig;
  }

  // ---- Widget: resting-state functional connectivity ---- //
  function buildRsConnectivity() {
    var fig = figure("Resting-state functional connectivity", "Spontaneous low-frequency BOLD fluctuations that rise and fall together across distant brain regions define functional connectivity, the basis of networks such as the default mode network.");
    var xMax = 60;
    var state = { mode: "connected" };
    var plot = makePlot({ xMax: xMax, yMin: -1, yMax: 1, xLabel: "time (s)", yLabel: "BOLD",
      xTicks: [0, 15, 30, 45, 60], yTicks: [-1, -0.5, 0, 0.5, 1], title: "Resting-state BOLD time series for two regions" });
    plot.addAxes();
    function regionA(t) {
      return 0.5 * Math.sin(2 * Math.PI * 0.03 * t) + 0.3 * Math.sin(2 * Math.PI * 0.06 * t + 0.4)
        + 0.2 * Math.sin(2 * Math.PI * 0.08 * t + 1.1);
    }
    function regionBConnected(t) { return 0.9 * regionA(t - 1.5); }
    function regionBUnconnected(t) {
      return 0.45 * Math.sin(2 * Math.PI * 0.045 * t + 2.1) + 0.35 * Math.sin(2 * Math.PI * 0.075 * t + 0.2)
        + 0.2 * Math.sin(2 * Math.PI * 0.035 * t + 3.0);
    }
    var curveA = null, curveB = null;
    var readout = el("div", { class: "diag-readout" });
    function redraw() {
      if (curveA) curveA.remove();
      if (curveB) curveB.remove();
      curveA = plot.addCurve(M.sample(regionA, xMax, 120), "");
      var bFn = state.mode === "connected" ? regionBConnected : regionBUnconnected;
      curveB = plot.addCurve(M.sample(bFn, xMax, 120), "alt");
      readout.textContent = state.mode === "connected"
        ? "Connected: region A (accent) and region B (orange) rise and fall together. Correlated spontaneous low-frequency fluctuations between distant regions define functional connectivity, such as the default mode network."
        : "Not connected: region A (accent) and region B (orange) drift independently, out of phase with each other. Uncorrelated or anticorrelated time courses between regions are not considered functionally connected.";
    }
    fig.appendChild(plot.svg);
    var controls = el("div", { class: "diag-controls" });
    [["Connected", "connected"], ["Not connected", "not"]].forEach(function (p) {
      var b = el("button", { type: "button", class: "diag-btn" + (p[1] === state.mode ? " on" : ""), text: p[0] });
      b.addEventListener("click", function () {
        state.mode = p[1];
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (x) { x.classList.remove("on"); });
        b.classList.add("on");
        redraw();
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls);
    fig.appendChild(readout);
    redraw();
    return fig;
  }

  // ---- Widget: cine ejection fraction by the Simpson stack-of-discs method ---- //
  function buildCardiacEf() {
    var fig = figure("Ejection fraction by Simpson's method", "Summing the left-ventricular short-axis discs from base to apex, the Simpson method, gives end-diastolic and end-systolic volume; their difference over EDV is the ejection fraction.");
    var W = 260, H = 180, cx = W / 2;
    var svg = svgEl("svg", { class: "diag-svg", viewBox: "0 0 " + W + " " + H,
      role: "img", "aria-label": "Short-axis disc stack for ejection fraction" });
    var DISC_Y = [18, 44, 70, 96, 122, 148];
    var ED_RX = [58, 52, 44, 34, 24, 12];
    var ES_RX = [37, 34, 28, 22, 16, 8];
    var RY = 9;
    var VOL_K = 120 / ED_RX.reduce(function (s, r) { return s + r * r; }, 0);
    function discVolume(rxArr) { return rxArr.reduce(function (s, r) { return s + r * r; }, 0) * VOL_K; }
    var g = svgEl("g", {});
    svg.appendChild(g);
    var state = { mode: "ed" };
    var readout = el("div", { class: "diag-readout" });
    function draw() {
      while (g.firstChild) g.removeChild(g.firstChild);
      var rxArr = state.mode === "ed" ? ED_RX : ES_RX;
      DISC_Y.forEach(function (y, i) {
        g.appendChild(svgEl("ellipse", { cx: cx, cy: y, rx: rxArr[i], ry: RY,
          fill: "#5db0ef", "fill-opacity": "0.22", stroke: "#5db0ef" }));
      });
      var lblBase = svgEl("text", { class: "diag-axtext", x: (cx - rxArr[0] - 4).toFixed(1), y: DISC_Y[0] + 3, "text-anchor": "end" });
      lblBase.textContent = "base"; g.appendChild(lblBase);
      var lblApex = svgEl("text", { class: "diag-axtext", x: (cx - rxArr[5] - 4).toFixed(1), y: DISC_Y[5] + 3, "text-anchor": "end" });
      lblApex.textContent = "apex"; g.appendChild(lblApex);
      var stateLbl = svgEl("text", { class: "diag-axtext", x: cx, y: H - 6, "text-anchor": "middle" });
      stateLbl.textContent = state.mode === "ed" ? "End-diastole: cavity at its largest" : "End-systole: cavity at its smallest";
      g.appendChild(stateLbl);
      var edv = Math.round(discVolume(ED_RX)), esv = Math.round(discVolume(ES_RX));
      var sv = edv - esv, ef = Math.round((sv / edv) * 100);
      readout.textContent = "EDV " + edv + " mL, ESV " + esv + " mL, stroke volume " + sv
        + " mL, ejection fraction " + ef + "%. Summing the traced short-axis discs from base to apex gives EDV and ESV; ejection fraction is EDV minus ESV, divided by EDV, and a normal left ventricle is over 50 percent.";
    }
    fig.appendChild(svg);
    var controls = el("div", { class: "diag-controls" });
    [["End-diastole", "ed"], ["End-systole", "es"]].forEach(function (p) {
      var b = el("button", { type: "button", class: "diag-btn" + (p[1] === state.mode ? " on" : ""), text: p[0] });
      b.addEventListener("click", function () {
        state.mode = p[1];
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (x) { x.classList.remove("on"); });
        b.classList.add("on");
        draw();
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls);
    fig.appendChild(readout);
    draw();
    return fig;
  }

  // ---- Widget: isotropic 3D voxels and reformatting ---- //
  function buildIsoVoxel() {
    var fig = figure("Isotropic voxels", "A 3D acquisition's voxel shape decides how well it reformats: a cube reformats cleanly into any plane, a flat slab does not.");
    var W = 260, H = 180;
    var svg = svgEl("svg", { class: "diag-svg", viewBox: "0 0 " + W + " " + H,
      role: "img", "aria-label": "Isotropic versus anisotropic voxel and reformatting" });
    var g = svgEl("g", {});
    svg.appendChild(g);
    var state = { mode: "iso" };
    var readout = el("div", { class: "diag-readout" });
    function box(x, y, w, h, dx, dy) {
      var grp = svgEl("g", {});
      grp.appendChild(svgEl("polygon", { points:
        x + "," + y + " " + (x + w) + "," + y + " " + (x + w + dx) + "," + (y - dy) + " " + (x + dx) + "," + (y - dy),
        fill: "#5db0ef", "fill-opacity": "0.55", stroke: "#5db0ef" }));
      grp.appendChild(svgEl("polygon", { points:
        (x + w) + "," + y + " " + (x + w) + "," + (y + h) + " " + (x + w + dx) + "," + (y + h - dy) + " " + (x + w + dx) + "," + (y - dy),
        fill: "#5db0ef", "fill-opacity": "0.18", stroke: "#5db0ef" }));
      grp.appendChild(svgEl("rect", { x: x, y: y, width: w, height: h, fill: "#5db0ef", "fill-opacity": "0.32", stroke: "#5db0ef" }));
      return grp;
    }
    function reformatPreview(x, y, w, h, blocky) {
      var grp = svgEl("g", {});
      grp.appendChild(svgEl("rect", { x: x, y: y, width: w, height: h, fill: "none", stroke: "#8a8f98" }));
      if (blocky) {
        var steps = 5, sw = w / steps, i;
        for (i = 0; i < steps; i++) {
          var stepH = (h * (i + 1)) / steps;
          grp.appendChild(svgEl("rect", { x: x + i * sw, y: y + h - stepH, width: sw, height: stepH,
            fill: "#e0554e", "fill-opacity": "0.5" }));
        }
      } else {
        grp.appendChild(svgEl("line", { x1: x, y1: y + h, x2: x + w, y2: y, stroke: "#5db0ef", "stroke-width": "2" }));
      }
      return grp;
    }
    function draw() {
      while (g.firstChild) g.removeChild(g.firstChild);
      var w = 64, h = 64, dx, dy;
      if (state.mode === "iso") { dx = 26; dy = 17; } else { dx = 92; dy = 56; }
      g.appendChild(box(28, 66, w, h, dx, dy));
      g.appendChild(reformatPreview(196, 120, 48, 40, state.mode !== "iso"));
      var capLbl = svgEl("text", { class: "diag-axtext", x: 220, y: 168, "text-anchor": "middle" });
      capLbl.textContent = "reformat"; g.appendChild(capLbl);
      var voxLbl = svgEl("text", { class: "diag-axtext", x: 6, y: 148, "text-anchor": "start" });
      voxLbl.textContent = state.mode === "iso" ? "cube: equal x, y, z" : "slab: thin in-plane, thick through-plane";
      g.appendChild(voxLbl);
      readout.textContent = state.mode === "iso"
        ? "Isotropic voxels have equal dimensions in x, y and z, so a single 3D acquisition can be reformatted into any plane, axial, sagittal, coronal or oblique, or projected as a MIP, without losing resolution."
        : "Anisotropic voxels are thin in-plane but thick through-plane. In-plane images look sharp, but reformatting across the thick dimension looks blocky and stair-stepped because there is not enough data along that axis.";
    }
    fig.appendChild(svg);
    var controls = el("div", { class: "diag-controls" });
    [["Isotropic", "iso"], ["Anisotropic", "aniso"]].forEach(function (p) {
      var b = el("button", { type: "button", class: "diag-btn" + (p[1] === state.mode ? " on" : ""), text: p[0] });
      b.addEventListener("click", function () {
        state.mode = p[1];
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (x) { x.classList.remove("on"); });
        b.classList.add("on");
        draw();
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls);
    fig.appendChild(readout);
    draw();
    return fig;
  }

  // ---- Widget: the full signal chain, excite through reconstruct ---- //
  // A 9-stage step-through animation: protons align, net M0, RF flip, FID,
  // coil detection, spatial encoding, k-space fill, FFT, final image. Stages
  // 1-6 draw into a shared SVG group; stages 7-9 draw into a shared canvas,
  // reusing the module-scope FFT/phantom helpers. One rAF loop draws only the
  // current stage and is restarted (after canceling any prior chain) on every
  // stage change, so only one loop is ever running.
  function buildSignalChain() {
    var W = 340, H = 200, N = 64;
    var ACCENT = "#5db0ef", WARN = "#e0554e", FAINT = "#3a3f4a";
    var WOBBLE_PERIOD = 2.2, GROW_DUR = 1.3, FLIP_DUR = 1.3, ROT_PERIOD = 1.6,
      DECAY_PERIOD = 3.0, KFILL_DUR = 2.4, FFT_DUR = 1.6;
    var DWELL_MS = 3500;

    function clamp01(x) { return x < 0 ? 0 : (x > 1 ? 1 : x); }

    function drawArrow(g, x1, y1, x2, y2, color) {
      g.appendChild(svgEl("line", { x1: x1.toFixed(1), y1: y1.toFixed(1), x2: x2.toFixed(1), y2: y2.toFixed(1),
        stroke: color, "stroke-width": "1.8" }));
      var ang = Math.atan2(y2 - y1, x2 - x1), a1 = ang + 2.6, a2 = ang - 2.6, size = 5;
      var p1x = x2 + size * Math.cos(a1), p1y = y2 + size * Math.sin(a1);
      var p2x = x2 + size * Math.cos(a2), p2y = y2 + size * Math.sin(a2);
      g.appendChild(svgEl("polygon", { fill: color, points: x2.toFixed(1) + "," + y2.toFixed(1) + " "
        + p1x.toFixed(1) + "," + p1y.toFixed(1) + " " + p2x.toFixed(1) + "," + p2y.toFixed(1) }));
    }
    function drawSpin(g, x, y, up, t, phase, opacity) {
      var L = 11, wob = 2.0 * Math.sin(2 * Math.PI * t / WOBBLE_PERIOD + phase);
      var y1 = up ? y + L / 2 : y - L / 2, y2 = up ? y - L / 2 : y + L / 2;
      var wrap = svgEl("g", { opacity: String(opacity) });
      drawArrow(wrap, x, y1, x + wob, y2, up ? ACCENT : "#8a8f98");
      g.appendChild(wrap);
    }
    function spinGrid(g, t, opacity) {
      var cols = 5, rows = 4, gx0 = 95, gx1 = 300, gy0 = 40, gy1 = 150, r, c;
      for (r = 0; r < rows; r++) {
        for (c = 0; c < cols; c++) {
          var x = gx0 + (gx1 - gx0) * c / (cols - 1), y = gy0 + (gy1 - gy0) * r / (rows - 1);
          drawSpin(g, x, y, ((r + c) % 5) < 3, t, (r * cols + c) * 0.37, opacity);
        }
      }
    }
    function drawB0(g) {
      drawArrow(g, 25, 172, 25, 30, ACCENT);
      var lbl = svgEl("text", { class: "diag-axtext", x: 25, y: 22, "text-anchor": "middle" });
      lbl.textContent = "B0"; g.appendChild(lbl);
    }
    function drawRfBurst(g, x, y, t, on) {
      var pts = [], i;
      for (i = 0; i <= 20; i++) {
        var xx = x + i * 2.4, yy = y + 8 * Math.sin(i * 0.9 + t * 10);
        pts.push(xx.toFixed(1) + " " + yy.toFixed(1));
      }
      g.appendChild(svgEl("path", { d: "M" + pts.join(" L"), fill: "none", stroke: WARN,
        "stroke-width": "1.3", opacity: on ? "1" : "0.25" }));
      var lbl = svgEl("text", { class: "diag-axtext", x: x + 24, y: y - 12, "text-anchor": "middle" });
      lbl.textContent = "RF"; g.appendChild(lbl);
    }

    // ---- stage 1: protons align in B0 ---- //
    function drawStage1(g, t) {
      drawB0(g);
      spinGrid(g, t, 1);
    }
    // Shared frame for stages 2-6 so the same vector and signal carry across stages:
    // one pivot with a transverse-plane ellipse, and one fixed signal-trace region on the right.
    var PX = 112, PY = 104, ERX = 52, ERY = 15, MLEN = 74;
    var SX0 = 190, SX1 = 330, SY = 96, SAMP = 30;
    function transversePlane(g, opacity) {
      g.appendChild(svgEl("ellipse", { cx: PX, cy: PY, rx: ERX, ry: ERY, fill: "none",
        stroke: FAINT, opacity: String(opacity) }));
    }
    function signalAxis(g) {
      g.appendChild(svgEl("line", { class: "diag-axis", x1: SX0, y1: SY, x2: SX1, y2: SY }));
    }
    function sigAt(tau, decay) {
      var env = decay ? Math.exp(-3 * tau / DECAY_PERIOD) : 1;
      return env * Math.cos(2 * Math.PI * tau / ROT_PERIOD);
    }

    // ---- stage 2: individual spins fade, net M0 grows along +z at the pivot ---- //
    function drawStage2(g, t) {
      var p = clamp01(t / GROW_DUR);
      spinGrid(g, t, Math.max(0.1, 1 - p * 0.9));
      transversePlane(g, 0.35);
      drawArrow(g, PX, PY, PX, PY - p * MLEN, ACCENT);
      var lbl = svgEl("text", { class: "diag-axtext", x: PX + 8, y: (PY - p * MLEN - 4).toFixed(1) });
      lbl.textContent = "M0"; g.appendChild(lbl);
    }
    // ---- stage 3: RF pulse tips M0 from +z down into the transverse plane ---- //
    function drawStage3(g, t) {
      var p = clamp01(t / FLIP_DUR), phi = p * (Math.PI / 2);
      transversePlane(g, 0.9);
      var steps = 22, pts = [], k;
      for (k = 0; k <= steps; k++) {
        var pk = phi * k / steps;
        pts.push((PX + ERX * Math.sin(pk)).toFixed(1) + " " + (PY - MLEN * Math.cos(pk)).toFixed(1));
      }
      g.appendChild(svgEl("path", { d: "M" + pts.join(" L"), fill: "none", stroke: ACCENT,
        "stroke-width": "1.1", "stroke-dasharray": "2 2" }));
      drawArrow(g, PX, PY, PX + ERX * Math.sin(phi), PY - MLEN * Math.cos(phi), ACCENT);
      drawRfBurst(g, 40, 52, t, t < FLIP_DUR);
      var lbl = svgEl("text", { class: "diag-axtext", x: PX, y: PY + 36, "text-anchor": "middle" });
      lbl.textContent = "90 degree flip"; g.appendChild(lbl);
    }
    // ---- stage 4: after the flip, two relaxations run at once. The transverse part precesses and
    //      decays (T2*), tracing the FID the coil detects as voltage; the longitudinal part recovers
    //      back up to M0 (T1). The vector spirals from the plane back up to M0. ---- //
    function drawStage4(g, t) {
      var T1P = DECAY_PERIOD * 1.7, tLoop = t % T1P;
      var Mxy = Math.exp(-3 * tLoop / DECAY_PERIOD), Mz = 1 - Math.exp(-2.4 * tLoop / T1P);
      var az = 2 * Math.PI * t / ROT_PERIOD;
      // longitudinal axis and the M0 target the vector recovers toward
      g.appendChild(svgEl("line", { class: "diag-axis", x1: PX, y1: PY, x2: PX, y2: PY - MLEN }));
      g.appendChild(svgEl("circle", { cx: PX, cy: PY - MLEN, r: "2.5", fill: "none", stroke: FAINT }));
      etag(g, PX + 7, PY - MLEN + 2, "M0");
      // transverse plane with a faint receiver coil around it
      transversePlane(g, 0.7);
      g.appendChild(svgEl("ellipse", { cx: PX, cy: PY, rx: ERX + 13, ry: ERY + 10, fill: "none",
        stroke: WARN, "stroke-width": "1.2", opacity: "0.5" }));
      // faint trail of the vector spiralling from the plane back up to M0
      var tr = [], s, ss = 30, tl, mx, mz, a2;
      for (s = 0; s <= ss; s++) {
        tl = tLoop * s / ss; mx = Math.exp(-3 * tl / DECAY_PERIOD); mz = 1 - Math.exp(-2.4 * tl / T1P);
        a2 = 2 * Math.PI * (t - tLoop + tl) / ROT_PERIOD;
        tr.push((PX + ERX * mx * Math.cos(a2)).toFixed(1) + " " + (PY + ERY * mx * Math.sin(a2) - MLEN * mz).toFixed(1));
      }
      g.appendChild(svgEl("path", { d: "M" + tr.join(" L"), fill: "none", stroke: ACCENT, "stroke-width": "0.8", opacity: "0.3" }));
      // the 3D magnetization vector: transverse part precesses+decays, longitudinal part grows to M0
      drawArrow(g, PX, PY, PX + ERX * Mxy * Math.cos(az), PY + ERY * Mxy * Math.sin(az) - MLEN * Mz, ACCENT);
      etag(g, PX - ERX - 2, PY + 30, "Mxy decays (T2*)");
      etag(g, PX + 10, PY - MLEN * 0.5, "Mz -> M0 (T1)");
      // the FID (from the transverse part) that the coil detects as an induced voltage
      signalAxis(g);
      var reveal = clamp01(tLoop / DECAY_PERIOD), steps = 90, n = Math.max(1, Math.round(reveal * steps)), pts = [], i;
      for (i = 0; i <= n; i++) {
        var tau = DECAY_PERIOD * i / steps;
        pts.push((SX0 + (SX1 - SX0) * i / steps).toFixed(1) + " " + (SY - sigAt(tau, true) * SAMP).toFixed(1));
      }
      g.appendChild(svgEl("path", { d: "M" + pts.join(" L"), fill: "none", stroke: ACCENT, "stroke-width": "1.4" }));
      etag(g, (SX0 + SX1) / 2, SY + 40, "FID = induced voltage", "middle");
    }
    // ---- stages 5-8 (the encode block) run on the SAME real little picture as the rest of the chain,
    //      so encoding is never abstract: show the object, a gradient labels each position with its own
    //      frequency, the coil sums the whole object into one signal, and that signal is one line of the
    //      object's k-space. The object and its k-space are built once here and reused by stages 9-11. ---- //
    var OBJ = (function () {
      var c = document.createElement("canvas"); c.width = N; c.height = N;
      var cx = c.getContext("2d");
      cx.fillStyle = "#000"; cx.fillRect(0, 0, N, N);
      cx.fillStyle = "#fff";
      cx.beginPath(); cx.arc(N / 2, N / 2, N * 0.34, 0, 2 * Math.PI); cx.fill();
      cx.fillStyle = "#000";
      cx.beginPath(); cx.arc(N * 0.40, N * 0.43, N * 0.055, 0, 2 * Math.PI); cx.fill();
      cx.beginPath(); cx.arc(N * 0.60, N * 0.43, N * 0.055, 0, 2 * Math.PI); cx.fill();
      cx.strokeStyle = "#000"; cx.lineWidth = N * 0.05; cx.lineCap = "round";
      cx.beginPath(); cx.arc(N / 2, N * 0.52, N * 0.17, 0.18 * Math.PI, 0.82 * Math.PI); cx.stroke();
      var d = cx.getImageData(0, 0, N, N).data, img = new Array(N * N), i;
      for (i = 0; i < N * N; i++) img[i] = d[i * 4] / 255;
      return { img: img, url: c.toDataURL() };
    })();
    var spec = centeredSpectrum(OBJ.img, N), kre = spec.re, kim = spec.im;
    var lineMag = [], lineRe = [];
    (function () {
      var cyk = Math.floor(N / 2), lx, re, im, mm = 0, mr = 0;
      for (lx = 0; lx < N; lx++) {
        re = kre[cyk * N + lx]; im = kim[cyk * N + lx];
        lineMag.push(Math.sqrt(re * re + im * im)); lineRe.push(re);
        if (lineMag[lx] > mm) mm = lineMag[lx];
        if (Math.abs(re) > mr) mr = Math.abs(re);
      }
      for (lx = 0; lx < N; lx++) { lineMag[lx] /= (mm || 1); lineRe[lx] /= (mr || 1); }
    })();
    function etag(g, x, y, txt, anchor) {
      var l = svgEl("text", { class: "diag-axtext", x: x, y: y, "text-anchor": anchor || "start" });
      l.textContent = txt; g.appendChild(l);
    }
    function encClock(g, cx, cy, r, phi, col) {
      g.appendChild(svgEl("circle", { cx: cx, cy: cy, r: r, fill: "none", stroke: FAINT, opacity: "0.7" }));
      var hx = cx + r * Math.sin(phi), hy = cy - r * Math.cos(phi);
      g.appendChild(svgEl("line", { x1: cx, y1: cy, x2: hx.toFixed(1), y2: hy.toFixed(1), stroke: col, "stroke-width": "1.8" }));
      g.appendChild(svgEl("circle", { cx: hx.toFixed(1), cy: hy.toFixed(1), r: "2", fill: col }));
    }
    function objImage(g, x, y, w) {
      g.appendChild(svgEl("image", { href: OBJ.url, x: x, y: y, width: w, height: w,
        "image-rendering": "pixelated", preserveAspectRatio: "none" }));
    }
    // Stage 5: the object is a 3D body - millions of voxels, each doing steps 1-4.
    function drawSources(g) {
      var i;
      for (i = 4; i >= 1; i--) {
        g.appendChild(svgEl("image", { href: OBJ.url, x: 124 + i * 7, y: 38 - i * 7, width: 76, height: 76,
          "image-rendering": "pixelated", preserveAspectRatio: "none", opacity: "0.22" }));
      }
      objImage(g, 124, 38, 76);
      etag(g, 162, 128, "the object: a 3D body", "middle");
      etag(g, 162, 146, "millions of voxels, each one doing steps 1-4", "middle");
    }
    // Stage 6: the RF pulse plus a slice-select gradient (Gz) excite just one 2D slice of the body.
    function drawSliceSelect(g) {
      var i;
      for (i = 4; i >= 1; i--) {
        g.appendChild(svgEl("image", { href: OBJ.url, x: 62 + i * 6, y: 50 - i * 8, width: 54, height: 54,
          "image-rendering": "pixelated", preserveAspectRatio: "none", opacity: "0.2" }));
      }
      g.appendChild(svgEl("line", { x1: 42, y1: 108, x2: 42, y2: 42, stroke: WARN, "stroke-width": "1.4" }));
      g.appendChild(svgEl("path", { d: "M38 48 L42 42 L46 48", fill: "none", stroke: WARN, "stroke-width": "1.4" }));
      etag(g, 42, 122, "Gz", "middle");
      objImage(g, 62, 50, 54);
      g.appendChild(svgEl("rect", { x: 62, y: 50, width: 54, height: 54, fill: "none", stroke: ACCENT, "stroke-width": "2" }));
      etag(g, 89, 118, "one excited slice", "middle");
      g.appendChild(svgEl("path", { d: "M152 77 L178 77 M172 73 L179 77 L172 81", fill: "none", stroke: FAINT, "stroke-width": "1.3" }));
      objImage(g, 192, 48, 58);
      etag(g, 221, 118, "the slice we image", "middle");
    }
    function kspaceImage(g, x, y, w) {
      g.appendChild(svgEl("image", { href: kOffURL, x: x, y: y, width: w, height: w,
        "image-rendering": "pixelated", preserveAspectRatio: "none" }));
    }
    // Stage 6: a gradient makes each column of the object precess at its own frequency.
    function drawEncode(g, t) {
      var ox = 128, oy = 36, ow = 80;
      g.appendChild(svgEl("path", { d: "M" + ox + " " + (oy - 6) + " L" + (ox + ow) + " " + (oy - 6) + " L" + (ox + ow) + " " + (oy - 18) + " Z", fill: WARN, "fill-opacity": "0.16", stroke: WARN, "stroke-width": "1.1" }));
      etag(g, ox, oy - 22, "gradient across the object: weak -> strong");
      objImage(g, ox, oy, ow);
      var n = 3, i;
      for (i = 0; i < n; i++) {
        var col = ox + ow * (i + 0.5) / n, rate = 0.4 + 1.7 * i / (n - 1);
        g.appendChild(svgEl("line", { x1: col, y1: oy + ow, x2: col, y2: oy + ow + 13, stroke: FAINT, "stroke-width": "0.8", "stroke-dasharray": "2 2" }));
        encClock(g, col, oy + ow + 26, 12, 2 * Math.PI * rate * t, i === 1 ? ACCENT : "#7fb4dd");
      }
      etag(g, ox + ow / 2, oy + ow + 48, "each column of the object precesses at its own frequency", "middle");
    }
    // Stage 7: the signal comes from the WHOLE excited slice at once - every pixel of the object feeds
    // the single coil, adding into one signal. Where from? Everywhere, simultaneously.
    function drawSignal(g) {
      objImage(g, 22, 38, 62);
      etag(g, 53, 112, "the excited slice", "middle");
      var src = [[40, 58], [66, 58], [53, 74], [42, 88], [64, 88]], coil = [118, 74], i;
      for (i = 0; i < src.length; i++) {
        g.appendChild(svgEl("line", { x1: src[i][0], y1: src[i][1], x2: coil[0], y2: coil[1], stroke: ACCENT, "stroke-width": "0.8", opacity: "0.4" }));
        g.appendChild(svgEl("circle", { cx: src[i][0], cy: src[i][1], r: "1.7", fill: ACCENT }));
      }
      g.appendChild(svgEl("circle", { cx: coil[0], cy: coil[1], r: "6", fill: "none", stroke: WARN, "stroke-width": "1.4" }));
      etag(g, coil[0], coil[1] + 19, "coil", "middle");
      g.appendChild(svgEl("path", { d: "M128 74 L148 74 M142 70 L149 74 L142 78", fill: "none", stroke: FAINT, "stroke-width": "1.3" }));
      etag(g, 154, 50, "one recorded signal:");
      var sx0 = 154, sx1 = 324, sy = 92, pts = [];
      g.appendChild(svgEl("line", { class: "diag-axis", x1: sx0, y1: sy, x2: sx1, y2: sy }));
      for (i = 0; i < lineRe.length; i++) {
        pts.push((sx0 + (sx1 - sx0) * i / (lineRe.length - 1)).toFixed(1) + " " + (sy - lineRe[i] * 28).toFixed(1));
      }
      g.appendChild(svgEl("path", { d: "M" + pts.join(" L"), fill: "none", stroke: "#cfe4f5", "stroke-width": "1.5" }));
      etag(g, 171, 148, "every position in the slice adds into this one signal, all at once", "middle");
    }
    // Stage 8: readout - while the x-gradient is on, sampling the signal over time sweeps across one
    // horizontal line of k-space (kx, edge to edge), filling it in point by point.
    function drawKline(g, t) {
      objImage(g, 26, 30, 56);
      etag(g, 54, 96, "the object", "middle");
      kspaceImage(g, 118, 30, 56);
      etag(g, 146, 96, "its k-space", "middle");
      var p = clamp01((t % 3.4) / 2.7);
      g.appendChild(svgEl("rect", { x: 118, y: 30 + 26, width: 56, height: 3, fill: ACCENT, "fill-opacity": "0.55" }));
      g.appendChild(svgEl("circle", { cx: (118 + 56 * p).toFixed(1), cy: 30 + 27.5, r: "2", fill: ACCENT }));
      var sx0 = 30, sx1 = 322, sy = 138, cols = lineMag.length, cw = (sx1 - sx0) / cols, swept = Math.round(p * (cols - 1)), i, lum;
      for (i = 0; i < cols; i++) {
        lum = i <= swept ? Math.round(14 + 226 * clamp01(lineMag[i])) : 11;
        g.appendChild(svgEl("rect", { x: (sx0 + i * cw).toFixed(1), y: sy - 9, width: (cw + 0.6).toFixed(1), height: 18, fill: "rgb(" + lum + "," + lum + "," + lum + ")" }));
      }
      g.appendChild(svgEl("rect", { x: sx0, y: sy - 9, width: (sx1 - sx0), height: 18, fill: "none", stroke: ACCENT, "stroke-width": "1" }));
      var cx = sx0 + p * (sx1 - sx0);
      g.appendChild(svgEl("line", { x1: cx.toFixed(1), y1: sy - 13, x2: cx.toFixed(1), y2: sy + 13, stroke: ACCENT, "stroke-width": "1.2" }));
      etag(g, sx0, sy + 30, "-kx", "start");
      etag(g, sx1, sy + 30, "+kx", "end");
      etag(g, (sx0 + sx1) / 2, sy - 15, "bright center (k=0) = contrast, faint edges = detail", "middle");
      etag(g, (sx0 + sx1) / 2, sy + 30, "one horizontal line of k-space, filled point by point", "middle");
    }
    // Stage 9: a second gradient (phase encode, along y) picks WHICH horizontal line each readout fills.
    function drawPhaseEncode(g, t) {
      objImage(g, 32, 40, 56);
      etag(g, 60, 106, "the object", "middle");
      g.appendChild(svgEl("path", { d: "M24 40 L24 96 L15 96 Z", fill: WARN, "fill-opacity": "0.18", stroke: WARN, "stroke-width": "1" }));
      etag(g, 14, 34, "gradient along y");
      g.appendChild(svgEl("path", { d: "M94 68 L118 68 M112 64 L119 68 L112 72", fill: "none", stroke: FAINT, "stroke-width": "1.3" }));
      kspaceImage(g, 136, 40, 56);
      etag(g, 164, 106, "its k-space", "middle");
      var ky = 40 + (0.5 + 0.42 * Math.sin(2 * Math.PI * t / 3.2)) * 56;
      g.appendChild(svgEl("rect", { x: 136, y: ky.toFixed(1), width: 56, height: 3, fill: ACCENT, "fill-opacity": "0.8" }));
      g.appendChild(svgEl("path", { d: "M228 " + ky.toFixed(1) + " L200 " + ky.toFixed(1), stroke: ACCENT, "stroke-width": "1", opacity: "0.6" }));
      etag(g, 232, ky.toFixed(1), "this line", "start");
      etag(g, 171, 130, "phase encode picks which line; step through all values to fill k-space", "middle");
    }

    // ---- stages 9-11: k-space fill + live reconstruction, center/edge, final image (canvas). Uses the
    //      same OBJ / kre / kim built for the encode block, so the picture that goes in comes back out. ---- //
    var kOff = document.createElement("canvas"); kOff.width = N; kOff.height = N;
    drawKMag(kOff.getContext("2d"), kre, kim, N);
    var kOffURL = kOff.toDataURL();
    var iOff = document.createElement("canvas"); iOff.width = N; iOff.height = N;
    reconMag(iOff.getContext("2d"), kre, kim, N);
    var rowOrder = [], ry;
    for (ry = 0; ry < N; ry++) rowOrder.push(ry);
    rowOrder.sort(function (a, b) { return Math.abs(a - N / 2) - Math.abs(b - N / 2); });
    // center-only and edge-only reconstructions to show what each part of k-space carries
    function maskK(re, im, low) {
      var mre = re.slice(), mim = im.slice(), x, y, dx, dy, keep;
      for (y = 0; y < N; y++) {
        for (x = 0; x < N; x++) {
          dx = x - N / 2; dy = y - N / 2; keep = Math.sqrt(dx * dx + dy * dy) <= N * 0.14;
          if (low !== keep) { mre[y * N + x] = 0; mim[y * N + x] = 0; }
        }
      }
      return { re: mre, im: mim };
    }
    var cImg = document.createElement("canvas"); cImg.width = N; cImg.height = N;
    var cM = maskK(kre, kim, true); reconMag(cImg.getContext("2d"), cM.re, cM.im, N);
    var eImg = document.createElement("canvas"); eImg.width = N; eImg.height = N;
    var eM = maskK(kre, kim, false); reconMag(eImg.getContext("2d"), eM.re, eM.im, N);

    // Stage 9: k-space fills center-out on the left; on the right the image is reconstructed from
    // whatever has been acquired so far, so it appears as a blurry contrast blob (center only) and
    // sharpens into edges and fine detail as the outer lines come in.
    function drawStage7(ctx, t) {
      var revealed = Math.max(1, Math.min(N, Math.round(clamp01(t / KFILL_DUR) * N)));
      var keep = new Array(N), i, x, y;
      for (i = 0; i < N; i++) keep[i] = false;
      for (i = 0; i < revealed; i++) keep[rowOrder[i]] = true;
      var mre = kre.slice(), mim = kim.slice();
      for (y = 0; y < N; y++) {
        if (!keep[y]) { for (x = 0; x < N; x++) { mre[y * N + x] = 0; mim[y * N + x] = 0; } }
      }
      drawKMag(ctx, mre, mim, N);
      reconMag(reconCtx, mre, mim, N);
    }
    // Stage 10: why center and edges differ - reconstruct from the center of k-space alone (a blurry,
    // all-contrast image) versus from the edges alone (only outlines and fine detail).
    function drawStage8(ctx) {
      ctx.clearRect(0, 0, N, N); ctx.drawImage(cImg, 0, 0);
      reconCtx.clearRect(0, 0, N, N); reconCtx.drawImage(eImg, 0, 0);
    }
    // Stage 11: the finished k-space and its image, side by side.
    function drawStage9(ctx) {
      ctx.clearRect(0, 0, N, N); ctx.drawImage(kOff, 0, 0);
      reconCtx.clearRect(0, 0, N, N); reconCtx.drawImage(iOff, 0, 0);
    }

    var STAGES = [
      { chip: "1 Align", caption: "Protons align with or against B0; slightly more line up parallel (lower energy).", kind: "svg", draw: drawStage1 },
      { chip: "2 Net M", caption: "The small parallel excess sums to a net longitudinal magnetization M0 along B0.", kind: "svg", draw: drawStage2 },
      { chip: "3 RF", caption: "An RF pulse at the Larmor frequency tips M into the transverse plane where it can be detected.", kind: "svg", draw: drawStage3 },
      { chip: "4 FID", caption: "Two relaxations run at once. The transverse part precesses and decays (T2*), tracing the FID the coil measures as voltage; the longitudinal part recovers back up to M0 (T1). The vector spirals from the plane up to M0.", kind: "svg", draw: drawStage4 },
      { chip: "5 Object", caption: "The object is a 3D body, millions of tiny voxels, and every voxel is doing steps 1-4 at once. To make a picture we have to work out how much signal comes from each one.", kind: "svg", draw: drawSources },
      { chip: "6 Slice", caption: "First we narrow it down. The RF pulse combined with a slice-select gradient (Gz) excites just one thin 2D slice; only that slice gives signal, the rest stays silent. This smiley is our slice.", kind: "svg", draw: drawSliceSelect },
      { chip: "7 Encode", caption: "A gradient along x makes each column of the slice precess at its own frequency. Position across the slice is now frequency.", kind: "svg", draw: drawEncode },
      { chip: "8 Signal", caption: "The signal comes from the whole slice at once: every pixel feeds the single coil, adding into one signal. This is the FID from step 4, now with the readout gradient on, so it mixes every position together by frequency.", kind: "svg", draw: drawSignal },
      { chip: "9 Readout", caption: "Readout: while the x-gradient is on, the coil is sampled over time. As the gradient's effect builds, each sample lands at the next point along one horizontal line of k-space, sweeping edge to edge (kx). The bright center (k=0) holds contrast, the faint edges hold fine detail.", kind: "svg", draw: drawKline },
      { chip: "10 Phase", caption: "One readout gives just one line. A second gradient along y, the phase encode, shifts which horizontal line you land on. Step it through every value and you fill all the lines.", kind: "svg", draw: drawPhaseEncode },
      { chip: "11 k-space", caption: "Repeating readout for every phase-encode step fills the whole 2D grid, the slice's k-space. The image (its Fourier transform) reconstructs live: the center gives a blurry contrast blob, the outer lines add edges and fine detail.", kind: "canvas", draw: drawStage7 },
      { chip: "12 Detail", caption: "Why the center and edges differ: reconstruct from the center of k-space alone and you get a blurry image, all overall contrast; from the edges alone you get only outlines and fine detail. The full image needs both.", kind: "canvas", draw: drawStage8 },
      { chip: "13 Image", caption: "One chain, start to finish: aligned protons to one slice's signal to k-space to image.", kind: "canvas", draw: drawStage9 },
    ];
    var REP_T = [0, GROW_DUR + 0.1, FLIP_DUR + 0.1, DECAY_PERIOD * 0.35,
      0.4, 0, 0.8, 0.5, 0.5, 1.0, KFILL_DUR + 0.1, FFT_DUR + 0.1, 0];

    var fig = figure("Signal chain", "The full signal chain from aligned protons to the reconstructed image, one stage at a time.");
    var svg = svgEl("svg", { class: "diag-svg", viewBox: "0 0 " + W + " " + H,
      role: "img", "aria-label": "MRI signal chain animation" });
    var svgG = svgEl("g", {});
    svg.appendChild(svgG);
    fig.appendChild(svg);

    var mainCanvas = document.createElement("canvas");
    mainCanvas.width = N; mainCanvas.height = N; mainCanvas.className = "diag-canvas";
    var mainCtx = mainCanvas.getContext("2d");
    var mainCap = el("figcaption", { class: "diag-canvas-cap", text: "k-space" });
    var reconCanvas = document.createElement("canvas");
    reconCanvas.width = N; reconCanvas.height = N; reconCanvas.className = "diag-canvas";
    var reconCtx = reconCanvas.getContext("2d");
    var reconCap = el("figcaption", { class: "diag-canvas-cap", text: "image so far" });
    var canvasStage = el("div", { class: "diag-kspace" }, [
      el("figure", { class: "diag-canvas-wrap" }, [mainCanvas, mainCap]),
      el("figure", { class: "diag-canvas-wrap" }, [reconCanvas, reconCap]),
    ]);
    fig.appendChild(canvasStage);

    var readout = el("div", { class: "diag-readout" });

    var state = { i: 0, playing: false };
    var rafId = null;

    function render(t) {
      var s = STAGES[state.i];
      if (s.kind === "svg") {
        while (svgG.firstChild) svgG.removeChild(svgG.firstChild);
        s.draw(svgG, t);
      } else {
        s.draw(mainCtx, t);
      }
    }
    function updateChips() {
      [].forEach.call(chipsRow.querySelectorAll(".diag-btn"), function (b, idx) {
        if (idx === state.i) b.classList.add("on"); else b.classList.remove("on");
      });
    }
    function updateStageLabel() { stageLabel.textContent = "Stage " + (state.i + 1) + " of " + STAGES.length; }
    function updateReadout() { readout.textContent = STAGES[state.i].caption; }
    function updateVisibility() {
      var kind = STAGES[state.i].kind;
      svg.style.display = kind === "svg" ? "" : "none";
      canvasStage.style.display = kind === "canvas" ? "" : "none";
      if (kind === "canvas") {
        if (state.i === 10) { mainCap.textContent = "k-space (filling)"; reconCap.textContent = "image so far"; }
        else if (state.i === 11) { mainCap.textContent = "center of k-space only"; reconCap.textContent = "edges of k-space only"; }
        else { mainCap.textContent = "k-space"; reconCap.textContent = "final image"; }
      }
    }
    function updatePlayBtn() {
      if (!playBtn) return;
      playBtn.textContent = state.playing ? "⏸ Pause" : "▸ Play";
      playBtn.classList.toggle("on", state.playing);
    }
    function startLoop() {
      if (rafId !== null) { cancelAnimationFrame(rafId); rafId = null; }
      var startTs = null;
      function frame(ts) {
        if (startTs === null) startTs = ts;
        var t = (ts - startTs) / 1000;
        render(t);
        if (state.playing && t * 1000 >= DWELL_MS) {
          if (state.i < STAGES.length - 1) { goTo(state.i + 1); return; }
          state.playing = false;
          updatePlayBtn();
        }
        rafId = requestAnimationFrame(frame);
      }
      rafId = requestAnimationFrame(frame);
    }
    function goTo(i) {
      state.i = Math.max(0, Math.min(STAGES.length - 1, i));
      updateChips();
      updateStageLabel();
      updateReadout();
      updateVisibility();
      if (reduceMotion) render(REP_T[state.i]);
      else startLoop();
    }

    var chipsRow = el("div", { class: "diag-controls" });
    STAGES.forEach(function (s, i) {
      var b = el("button", { type: "button", class: "diag-btn" + (i === 0 ? " on" : ""), text: s.chip });
      b.addEventListener("click", function () { state.playing = false; updatePlayBtn(); goTo(i); });
      chipsRow.appendChild(b);
    });

    var navRow = el("div", { class: "diag-controls" });
    var prevBtn = el("button", { type: "button", class: "diag-btn", text: "< Prev" });
    var stageLabel = el("span", { class: "diag-glabel", text: "Stage 1 of " + STAGES.length });
    var nextBtn = el("button", { type: "button", class: "diag-btn", text: "Next >" });
    prevBtn.addEventListener("click", function () { state.playing = false; updatePlayBtn(); goTo(state.i - 1); });
    nextBtn.addEventListener("click", function () { state.playing = false; updatePlayBtn(); goTo(state.i + 1); });
    navRow.appendChild(prevBtn);
    navRow.appendChild(stageLabel);
    navRow.appendChild(nextBtn);
    var playBtn = null;
    if (!reduceMotion) {
      playBtn = el("button", { type: "button", class: "diag-btn diag-play", text: "▸ Play" });
      playBtn.addEventListener("click", function () { state.playing = !state.playing; updatePlayBtn(); });
      navRow.appendChild(playBtn);
    }

    fig.appendChild(chipsRow);
    fig.appendChild(navRow);
    fig.appendChild(readout);

    goTo(0);
    return fig;
  }

  var BUILDERS = { "t1-recovery": buildT1Recovery, "t2-decay": buildT2Decay, "t2-vs-t2star": buildT2vsT2star, "tr-te-weighting": buildTrTeWeighting, "ernst-angle": buildErnstAngle, "ir-nulling": buildIrNulling, "dwi-bvalue": buildDwiBvalue, "snr-tradeoff": buildSnrTradeoff, "kspace-recon": buildKspaceRecon, "kspace-trajectories": buildKspaceTrajectories, "chemical-shift": buildChemicalShift, "parallel-imaging": buildParallelImaging, "gibbs-ringing": buildGibbsRinging, "dsc-curve": buildDscCurve, "asl-subtraction": buildAslSubtraction, "pc-venc": buildPcVenc, "tof-inflow": buildTofInflow, "fa-anisotropy": buildFaAnisotropy, "tractography": buildTractography, "lge-nulling": buildLgeNulling, "cardiac-gating": buildCardiacGating, "mrs-spectrum": buildMrsSpectrum, "mrs-te": buildMrsTe, "bold-hrf": buildBoldHrf, "fmri-design": buildFmriDesign, "relaxometry": buildRelaxometry, "r2star-iron": buildR2starIron,
    "dce-kinetics": buildDceKinetics, "bpe-cycle": buildBpeCycle, "prostate-zones": buildProstateZones,
    "prostate-dwi": buildProstateDwi, "metal-bandwidth": buildMetalBandwidth, "magic-angle": buildMagicAngle,
    "mrcp-te": buildMrcpTe, "hepatobiliary-phase": buildHepatobiliaryPhase,
    "larmor-field": buildLarmorField, "gad-t1": buildGadT1, "sar-flip": buildSarFlip,
    "dce-ktrans": buildDceKtrans, "cemra-bolus": buildCemraBolus, "pulse-timing": buildPulseTiming,
    "safety-zones": buildSafetyZones, "rs-connectivity": buildRsConnectivity,
    "cardiac-ef": buildCardiacEf, "iso-voxel": buildIsoVoxel, "signal-chain": buildSignalChain };

  function attach(card, eduTitle) {
    if (!M || !card) return;
    var ids = M.DIAGRAM_MAP[eduTitle];
    if (!ids) return;
    ids.forEach(function (id) {
      var fn = BUILDERS[id];
      if (fn) card.appendChild(fn());
    });
  }

  // Expose the API plus internals so later widget tasks extend BUILDERS in place.
  window.CourseDiagrams = { attach: attach, _BUILDERS: BUILDERS,
    _makePlot: makePlot, _figure: figure, _el: el, _reduceMotion: reduceMotion };
})();
