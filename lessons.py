"""
lessons.py — pure-data definitions of the guided lessons.

Each lesson is data only: audience-facing text and parameter values, separated
from all rendering / Gradio logic (that lives in app.py). This keeps lessons
trivial to edit, add, or translate without touching app code.

A lesson describes:
  * which region / sequence / field to use and the per-panel parameters,
  * whether Compare mode is on (two panels) or off (single panel),
  * which controls stay unlocked (interactive) — everything else is locked,
  * optional info widgets (live target-TI readout, per-panel scan time).

``resolve(key)`` turns a lesson (or "Free Explore") into a fully-derived
``LessonView`` — a plain data structure of per-control value/interactive/visible
states — which app.py maps onto gr.update() calls. resolve() is pure and
engine-free, so the lesson mechanics are unit-testable without Gradio.
"""

from dataclasses import dataclass
import math

# The longitudinal magnetization of an inverted tissue crosses zero at
# t = ln(2) * T1. STIR places TI there to null fat.
FAT_NULL_FACTOR = math.log(2)  # ≈ 0.693

_IR = "Inversion Recovery"
FREE_EXPLORE = "Free Explore"

# The twelve lockable controls the UI exposes (region/field are shared; the
# rest are per-panel, suffixed _l / _r).
CONTROL_NAMES = (
    "region", "field",
    "sequence_l", "tr_l", "te_l", "flip_l", "ti_l",
    "sequence_r", "tr_r", "te_r", "flip_r", "ti_r",
)


@dataclass(frozen=True)
class PanelConfig:
    sequence: str
    tr: float
    te: float
    flip: float
    ti: float


@dataclass(frozen=True)
class Lesson:
    key: str
    title: str
    explanation: str
    region: str
    field: str
    compare: bool
    left: PanelConfig
    right: PanelConfig | None
    unlocked: frozenset            # control names that remain interactive
    show_target_ti: bool = False   # STIR: live "Target TI ≈ … ms" readout
    show_scan_time: bool = False   # SE vs FSE: per-panel estimated scan time


# Step-2 free-explore defaults (Panel B starts T2-weighted, as in Step 2).
DEFAULT_LEFT = PanelConfig("Spin Echo", 500.0, 15.0, 90.0, 2500.0)
DEFAULT_RIGHT = PanelConfig("Spin Echo", 4000.0, 90.0, 90.0, 2500.0)


# --- The three lessons (pure content) ---------------------------------------
LESSONS: dict[str, Lesson] = {
    "What TR does": Lesson(
        key="What TR does",
        title="What TR does",
        explanation=(
            "Repetition time (TR) is the gap between successive excitation "
            "pulses — it sets how much longitudinal magnetization each tissue "
            "recovers before the next readout. At short TR, tissues with a "
            "short T1 such as white matter recover more fully and look bright, "
            "while slow-recovering gray matter and CSF stay dark: this is T1 "
            "weighting. Lengthen TR and every tissue recovers almost "
            "completely, so the remaining signal differences reflect proton "
            "density rather than T1, and gray–white contrast fades. TE is held "
            "short here so T2 effects don't confuse the picture. **Slide TR "
            "from low to high and watch the contrast between gray and white "
            "matter flatten as the image shifts from T1-weighted to "
            "proton-density weighted.**"
        ),
        region="Brain",
        field="1.5T",
        compare=False,
        left=PanelConfig("Spin Echo", tr=500.0, te=15.0, flip=90.0, ti=2500.0),
        right=None,
        unlocked=frozenset({"tr_l"}),
    ),
    "Nulling fat with STIR": Lesson(
        key="Nulling fat with STIR",
        title="Nulling fat with STIR",
        explanation=(
            "Short-TI inversion recovery (STIR) suppresses fat by reading out "
            "at the instant fat has no longitudinal magnetization. An inversion "
            "pulse flips all magnetization negative; each tissue then recovers "
            "back through zero at a time of about 0.69 × its T1. Fat has a very "
            "short T1, so it crosses zero early — set the inversion time (TI) to "
            "that null and fat gives no signal while other tissues still do. "
            "Because fat's T1 rises with field strength, the null TI shifts too, "
            "so the target moves when you toggle 1.5T/3T. **Slide TI around the "
            "target value shown above and watch the bright subcutaneous and "
            "visceral fat darken at the null, then brighten as you move away.**"
        ),
        region="Abdomen",
        field="1.5T",
        compare=False,
        # ti start ≈ ln(2) × fat T1(1.5T)=290 ms ≈ 201 ms (see tissue_db label 4).
        left=PanelConfig(_IR, tr=5000.0, te=30.0, flip=90.0, ti=201.0),
        right=None,
        unlocked=frozenset({"ti_l", "field"}),
        show_target_ti=True,
    ),
    "SE vs FSE": Lesson(
        key="SE vs FSE",
        title="SE vs FSE",
        explanation=(
            "Conventional spin echo (SE) collects one line of k-space per TR, "
            "so a T2-weighted scan with TR=4000 ms takes many minutes per "
            "slice. Fast spin echo (FSE/TSE) fires a train of refocusing pulses "
            "after each excitation, collecting many lines per TR and cutting "
            "scan time by roughly the echo-train length. The two panels here "
            "show the same T2-weighted brain — fluid bright, white matter dark "
            "— at matched TR and effective TE. Look at the images first: the "
            "contrast is nearly identical. Then look at the scan times shown "
            "beneath each: SE takes about sixteen times longer than FSE for the "
            "same picture. This is why FSE replaced conventional SE for almost "
            "all routine T2-weighted imaging."
        ),
        region="Brain",
        field="3T",
        compare=True,
        left=PanelConfig("Spin Echo", tr=4000.0, te=90.0, flip=90.0, ti=2500.0),
        right=PanelConfig("FSE / TSE", tr=4000.0, te=90.0, flip=90.0, ti=2500.0),
        unlocked=frozenset({"field"}),   # only the shared field stays unlocked
        show_scan_time=True,
    ),
}

# Display order for the lesson buttons (Free Explore first).
LESSON_ORDER = [FREE_EXPLORE] + list(LESSONS.keys())


def keys() -> list[str]:
    """Lesson keys in display order, including 'Free Explore'."""
    return list(LESSON_ORDER)


def get(key: str) -> "Lesson | None":
    """The Lesson for *key*, or None for Free Explore / unknown keys."""
    return LESSONS.get(key)


def fat_null_ti(t1_fat_ms: float) -> float:
    """STIR null TI (ms) for a fat T1 of *t1_fat_ms* — ln(2) × T1."""
    return FAT_NULL_FACTOR * t1_fat_ms


# --- Resolved, per-control view (pure; app.py maps this to gr.update) --------
@dataclass
class ControlState:
    value: object
    interactive: bool
    visible: bool = True


@dataclass
class LessonView:
    key: str
    title: str
    explanation: str
    region: str
    field: str
    compare: bool
    show_target_ti: bool
    show_scan_time: bool
    controls: dict          # name -> ControlState, for every CONTROL_NAMES entry


def resolve(key: str) -> LessonView:
    """Derive the full per-control state for *key*.

    For a real lesson, a control is interactive iff it is in the lesson's
    ``unlocked`` set; the TI slider is visible iff that panel's sequence is
    Inversion Recovery. For Free Explore, every control is interactive at its
    Step-2 default and Compare mode is off — i.e. all locks released.
    """
    lesson = LESSONS.get(key)
    if lesson is None:  # Free Explore (or unknown) → fully unlocked defaults
        left, right = DEFAULT_LEFT, DEFAULT_RIGHT
        region, fld, compare = "Brain", "3T", False
        unlocked = frozenset(CONTROL_NAMES)
        title, explanation = FREE_EXPLORE, ""
        show_ti = show_st = False
        key = FREE_EXPLORE
    else:
        left = lesson.left
        right = lesson.right or DEFAULT_RIGHT
        region, fld, compare = lesson.region, lesson.field, lesson.compare
        unlocked = lesson.unlocked
        title, explanation = lesson.title, lesson.explanation
        show_ti, show_st = lesson.show_target_ti, lesson.show_scan_time

    def cs(name, value, *, visible=True):
        return ControlState(value=value, interactive=(name in unlocked),
                            visible=visible)

    controls = {
        "region": cs("region", region),
        "field": cs("field", fld),
        "sequence_l": cs("sequence_l", left.sequence),
        "tr_l": cs("tr_l", left.tr),
        "te_l": cs("te_l", left.te),
        "flip_l": cs("flip_l", left.flip),
        "ti_l": cs("ti_l", left.ti, visible=(left.sequence == _IR)),
        "sequence_r": cs("sequence_r", right.sequence),
        "tr_r": cs("tr_r", right.tr),
        "te_r": cs("te_r", right.te),
        "flip_r": cs("flip_r", right.flip),
        "ti_r": cs("ti_r", right.ti, visible=(right.sequence == _IR)),
    }
    return LessonView(key=key, title=title, explanation=explanation,
                      region=region, field=fld, compare=compare,
                      show_target_ti=show_ti, show_scan_time=show_st,
                      controls=controls)
