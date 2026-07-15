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
        var v = (dx * dx + dy * dy) < (N * 0.24) * (N * 0.24) ? 0.8 : 0.08;
        if ((x > N * 0.30 && x < N * 0.34) || (y > N * 0.60 && y < N * 0.64)) v = 1.0;
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
    fig.appendChild(el("span", { class: "diag-glabel", text: "Matrix:" }));
    var controls = el("div", { class: "diag-controls" });
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

  var BUILDERS = { "t1-recovery": buildT1Recovery, "t2-decay": buildT2Decay, "t2-vs-t2star": buildT2vsT2star, "tr-te-weighting": buildTrTeWeighting, "ernst-angle": buildErnstAngle, "ir-nulling": buildIrNulling, "dwi-bvalue": buildDwiBvalue, "snr-tradeoff": buildSnrTradeoff, "kspace-recon": buildKspaceRecon, "kspace-trajectories": buildKspaceTrajectories, "chemical-shift": buildChemicalShift, "parallel-imaging": buildParallelImaging, "gibbs-ringing": buildGibbsRinging };

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
