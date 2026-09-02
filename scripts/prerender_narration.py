#!/usr/bin/env python3
"""Pre-render neural narration for premium education cards.

For each kind:"education" item in data/course_content.json, synthesize the
card (title + body + key points, through the site's MRI pronunciation
dictionary in web/a11y.js) with Kokoro (af_heart) and write
web/audio/cards/<slug>.mp3 plus a manifest keyed by card title with a text
hash, so unchanged cards are skipped on re-runs.

Offline production tool (never ships): needs a venv with
    pip install kokoro soundfile
plus espeak-ng (brew install espeak-ng on macOS — the pip wheel's bundled
data path is broken there, which the loader patch below works around) and
ffmpeg on PATH for the mp3 encode. Run:
    <venv>/bin/python scripts/prerender_narration.py
"""
import hashlib
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "web", "audio", "cards")
VOICE = "af_heart"


def slug(s):
    return re.sub(r"^-+|-+$", "", re.sub(r"[^a-z0-9]+", "-", str(s).lower()))


def card_text(b):
    """Mirror the Listen button: title + body text + key points."""
    html = str(b.get("html", ""))
    t = re.sub(r"</(p|li|h[1-6]|div)>", ". ", html)
    t = re.sub(r"<br\s*/?>", ". ", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"\.\s*\.", ".", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    text = b["title"] + ". " + t
    for kp in b.get("keypoints") or []:
        text += " Key point: " + kp + "."
    return text


def speakable_all(texts):
    """Run the site's pronunciation dictionary (web/a11y.js) over all texts."""
    script = (
        "const A11y = require(process.argv[1]);"
        "const texts = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
        "process.stdout.write(JSON.stringify(texts.map(A11y.speakable)));"
    )
    r = subprocess.run(["node", "-e", script, os.path.join(ROOT, "web", "a11y.js")],
                       input=json.dumps(texts), capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def main():
    d = json.load(open(os.path.join(ROOT, "data", "course_content.json")))
    items = d if isinstance(d, list) else d["items"]
    cards = [(it.get("topic", ""), it["body"]) for it in items if it.get("kind") == "education"]
    os.makedirs(OUT, exist_ok=True)
    man_path = os.path.join(OUT, "manifest.json")
    manifest = json.load(open(man_path)) if os.path.exists(man_path) else {}

    texts = [card_text(b) for _, b in cards]
    spoken = speakable_all(texts)
    todo = []
    for (topic, b), text in zip(cards, spoken, strict=True):
        h = hashlib.sha1((VOICE + "\n" + text).encode()).hexdigest()[:12]
        key = topic + "|" + b["title"]        # titles repeat across modules
        f = slug(topic + "-" + b["title"]) + ".mp3"
        rec = manifest.get(key)
        if rec and rec.get("hash") == h and os.path.exists(os.path.join(OUT, f)):
            continue
        todo.append((key, f, h, text))
    print(f"{len(cards)} cards, {len(todo)} to synthesize")
    if not todo:
        return

    import espeakng_loader
    if sys.platform == "darwin" and os.path.exists("/opt/homebrew/share/espeak-ng-data"):
        espeakng_loader.get_data_path = lambda: "/opt/homebrew/share/espeak-ng-data"
        espeakng_loader.get_library_path = lambda: "/opt/homebrew/lib/libespeak-ng.dylib"
    from kokoro import KPipeline
    import numpy as np
    import soundfile as sf
    pipe = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")

    for i, (key, f, h, text) in enumerate(todo):
        wav = np.concatenate([a for _, _, a in pipe(text, voice=VOICE)])
        tmp = os.path.join(OUT, f + ".tmp.wav")   # per-card: concurrent runs can't race
        sf.write(tmp, wav, 24000)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp,
                        "-ac", "1", "-b:a", "48k", os.path.join(OUT, f)], check=True)
        os.remove(tmp)
        manifest[key] = {"file": f, "hash": h, "seconds": round(len(wav) / 24000, 1)}
        json.dump(manifest, open(man_path, "w"), indent=1)   # checkpoint per card
        print(f"[{i + 1}/{len(todo)}] {key} ({manifest[key]['seconds']}s)")
    print(f"done -> {OUT}")


if __name__ == "__main__":
    main()
