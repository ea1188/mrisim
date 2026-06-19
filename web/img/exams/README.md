# Image-library exams — drop in your images here

The Protocol Planning page has an **"Image library (examples)"** group in the Exam
picker (a positioning / "fake scanner" trainer). Each exam shows **static scout
images** you can angle on (the angle is cosmetic/illustrative) and a **static example
image per sequence** that pops up on Acquire — it's an example, *not* simulated from
the prescription.

The images are plain files. **Drop a `.png` into the right folder and it replaces the
labelled placeholder automatically — no code change.** You can add them one at a time;
missing files just keep showing the placeholder.

## Where the files go

```
web/img/exams/<part>/<name>.png
```

`<part>` is the lower-case, underscore slug of the exam name (e.g. `Tib-Fib` → `tib_fib`).

Every part needs **three scouts**:

```
scout_axial.png
scout_coronal.png
scout_sagittal.png
```

…plus **one file per sequence** (filenames are consistent across parts, so `t1_sag.png`
is always the T1 sagittal):

| Joint parts — **Shoulder, Wrist, Hand, Ankle, Foot** | Long-bone parts — **Humerus, Forearm, Tib-Fib** |
|---|---|
| `t1_sag.png` (T1 Sagittal)    | `t1_ax.png`  (T1 Axial) |
| `pdfs_sag.png` (PD FS Sagittal) | `t1_cor.png` (T1 Coronal) |
| `pdfs_ax.png` (PD FS Axial)   | `stir_cor.png` (STIR Coronal) |
| `pdfs_cor.png` (PD FS Coronal) | `pdfs_ax.png` (PD FS Axial) |
| `t2fs_cor.png` (T2 FS Coronal) | |

Example for the ankle:

```
web/img/exams/ankle/scout_axial.png
web/img/exams/ankle/scout_coronal.png
web/img/exams/ankle/scout_sagittal.png
web/img/exams/ankle/t1_sag.png
web/img/exams/ankle/pdfs_sag.png
web/img/exams/ankle/pdfs_ax.png
web/img/exams/ankle/pdfs_cor.png
web/img/exams/ankle/t2fs_cor.png
```

## Adding / changing exams

The exam list and per-part sequence lists live in `web/protocol.js` (`IMAGE_EXAMS`,
`JOINT`, `LONGBONE`, `buildImageExam`). To add a part, add one line to `IMAGE_EXAMS`; to
change a part's sequences, give it a custom list instead of `JOINT` / `LONGBONE`. The
filenames in the table above are just the `file:` fields in those lists.

## Licensing

Only commit images you have the right to redistribute on a public site — **Creative
Commons / public-domain / your own**. Most radiology images online are copyrighted.
Keep attribution where the licence requires it.
