"""
annotations.py — real-time, on-image teaching annotations (Step 4).

A small, data-driven set of *annotation rules*: pure functions of the current
parameter state that return either a short, confident caption ("Fat is nulled.")
or ``None``. The render path in ``app.py`` runs every rule against the live state
and concatenates the non-``None`` results into a single line shown beneath the
scan-time caption.

Design principle: annotations are **sparse and confident, not dense and hedged**.
A rule fires only when the physics is unambiguous about the dominant teaching
point of the current parameters; otherwise it stays silent. Silence is better
than a vague label. Each rule here corresponds directly to a moment the existing
guided lessons already teach, so the annotations reinforce vocabulary the learner
has already met rather than introducing new terms.

Rules are kept in the ``RULES`` registry (a plain tuple of functions) so adding
more later is trivial: write a ``rule(ctx) -> str | None`` and append it. Each
rule is a pure comparison on a handful of numbers — sub-millisecond to evaluate.

The three Step-4 rules (intentionally no more):
  * fat null     — IR, TI within ±15 ms of ln(2)×T1(fat)  → "Fat is nulled."
  * fluid null   — IR, TI within ±15 ms of ln(2)×T1(CSF)  → "Fluid is nulled."
  * SE/FSE weighting — TR/TE classify the contrast        → "T1-weighted" / …
"""

from dataclasses import dataclass

import tissue_db
import lessons

# Sequence names as the UI spells them (must match app.SEQUENCES).
_IR = "Inversion Recovery"
_SE_SEQUENCES = ("Spin Echo", "FSE / TSE")

# tissue_db labels whose IR null we narrate.
_FAT_LABEL = 4     # Fat   — the STIR null (matches the STIR lesson's Target TI)
_FLUID_LABEL = 1   # Fluid/CSF — the FLAIR null

# How close TI must be to a tissue's null to call it nulled (ms, ± each side).
NULL_WINDOW_MS = 15.0

# SE/FSE contrast-weighting cutoffs (standard clinical thresholds, ms).
# Strict inequalities: parameters *on* a boundary fall into no region, so the
# simulator stays silent rather than committing to a label it isn't sure of.
SHORT_TR_MS = 600.0
LONG_TR_MS = 2000.0
SHORT_TE_MS = 30.0
LONG_TE_MS = 80.0


@dataclass(frozen=True)
class AnnotationContext:
    """The live parameter state a rule reasons about. Pure data; no engine."""
    sequence: str
    tr: float
    te: float
    ti: float
    field: str
    region: str


def _null_ti_for(label: int, field: str) -> float:
    """The IR null TI (ms) that nulls tissue *label* at *field* — ln(2)×T1.

    Uses the same ``lessons.null_ti`` formula (and the same tissue table) that
    produces the STIR lesson's on-screen "Target TI", so the annotation fires at
    exactly the number the lesson tells the learner to aim for.
    """
    t1 = tissue_db.properties(field)[label]["T1"]
    return lessons.null_ti(t1)


# --- Rules: each returns a short caption when its condition holds, else None --
def fat_null_rule(ctx: AnnotationContext) -> "str | None":
    """IR only: TI within ±NULL_WINDOW_MS of the fat null → fat gives no signal."""
    if ctx.sequence != _IR:
        return None
    if abs(ctx.ti - _null_ti_for(_FAT_LABEL, ctx.field)) <= NULL_WINDOW_MS:
        return "Fat is nulled."
    return None


def fluid_null_rule(ctx: AnnotationContext) -> "str | None":
    """IR only: TI within ±NULL_WINDOW_MS of the CSF null → fluid gives no signal
    (the FLAIR null — reaching it in Free Explore is itself a discovery)."""
    if ctx.sequence != _IR:
        return None
    if abs(ctx.ti - _null_ti_for(_FLUID_LABEL, ctx.field)) <= NULL_WINDOW_MS:
        return "Fluid is nulled."
    return None


def weighting_rule(ctx: AnnotationContext) -> "str | None":
    """SE/FSE only: classify the contrast from TR/TE, or stay silent.

    Short TR + short TE → T1-weighted; long TR + long TE → T2-weighted;
    long TR + short TE → proton-density weighted. Anything in between is genuine
    *mixed* weighting — a real category that deserves its own future treatment —
    so we return None rather than mislabel it.
    """
    if ctx.sequence not in _SE_SEQUENCES:
        return None
    short_tr, long_tr = ctx.tr < SHORT_TR_MS, ctx.tr > LONG_TR_MS
    short_te, long_te = ctx.te < SHORT_TE_MS, ctx.te > LONG_TE_MS
    if short_tr and short_te:
        return "T1-weighted"
    if long_tr and long_te:
        return "T2-weighted"
    if long_tr and short_te:
        return "Proton-density weighted"
    return None


# Registry — evaluated in order; extend by appending a new rule function.
RULES = (fat_null_rule, fluid_null_rule, weighting_rule)


def annotate(sequence: str, tr: float, te: float, ti: float,
             field: str, region: str) -> list[str]:
    """Run every rule against the current state; return the captions that fire.

    Returns a list (usually empty or one entry — the rules are designed not to
    overlap), in ``RULES`` order. Pure and engine-free, so it is unit-testable
    without Gradio or the simulator.
    """
    ctx = AnnotationContext(sequence=sequence, tr=float(tr), te=float(te),
                            ti=float(ti), field=field, region=region)
    out = []
    for rule in RULES:
        note = rule(ctx)
        if note is not None:
            out.append(note)
    return out


def annotation_line(sequence: str, tr: float, te: float, ti: float,
                    field: str, region: str) -> str:
    """The one-line annotation for display — fired captions joined, or ``""``."""
    return " · ".join(annotate(sequence, tr, te, ti, field, region))
