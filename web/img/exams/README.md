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

…plus **one file per sequence**. Filenames follow `<sequence>_<plane>` (e.g. `t1_sag`,
`pdfs_ax`, `t2_cor`). Each part has its **own sequence list** matching the slices that case
actually has — see the per-part list in `web/protocol.js` (`ANKLE`, `WRIST`, `SHOULDER`,
`FOOT`, `HAND`) and the `CREDITS.md` in each populated folder for the exact file map.

Currently populated: **Ankle, Wrist, Shoulder, Foot, Hand**. To add another part (e.g. a
long bone), create its folder, add a sequence list + `IMAGE_EXAMS` entry in `protocol.js`,
and drop the images in.

Images may be `.png`, `.jpg`, or `.jpeg` — the app tries each before the placeholder, so
radiology JPEGs drop straight in.

Example for the ankle:

```
web/img/exams/ankle/scout_axial.jpg
web/img/exams/ankle/scout_coronal.jpg
web/img/exams/ankle/scout_sagittal.jpg
web/img/exams/ankle/pdfs_ax.jpg
web/img/exams/ankle/pdfs_cor.jpg
web/img/exams/ankle/pdfs_sag.jpeg
```

## Adding / changing exams

The exam list and per-part sequence lists live in `web/protocol.js` (`IMAGE_EXAMS`,
`buildImageExam`, and the per-part lists like `ANKLE`/`WRIST`/`FOOT`). To add a part, add a
line to `IMAGE_EXAMS` with its sequence list and a credit string; to change a part's
sequences, edit its list. The `file:` field in each entry is the on-disk filename (sans
extension). `buildImageExam(part, list, credit)` — the credit shows as an on-page
attribution line while that exam is open.

## Licensing

Only commit images you have the right to redistribute on a public site — **Creative
Commons / public-domain / your own**. Most radiology images online are copyrighted.
Keep attribution where the licence requires it.
