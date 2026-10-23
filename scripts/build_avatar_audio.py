"""Rebuild the companion pack from pinned, credited recordings (requires ffmpeg).

Usage: python scripts/build_avatar_audio.py --source-dir /tmp/avatar-audio-input
Missing sources are downloaded from the manifest's pinned mirror URLs. Masters
stay outside the repository; only the short, edited MP3s are shipped.
"""
from __future__ import annotations

import argparse
from array import array
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1] / "static/audio/avatars"
RATE = 44100


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def build(source_dir):
    manifest = json.loads((ROOT / "manifest.json").read_text())
    source_dir.mkdir(parents=True, exist_ok=True)
    for name, source in manifest["sources"].items():
        target = source_dir / name
        if not target.exists():
            with urllib.request.urlopen(source["download"], timeout=60) as response:
                target.write_bytes(response.read())
        if sha256(target.read_bytes()) != source["sha256"]:
            raise ValueError(f"Source checksum mismatch: {name}")
    for filename, clip in manifest["clips"].items():
        command = ["ffmpeg", "-v", "error"]
        filters, labels = [], []
        for i, layer in enumerate(clip["layers"]):
            command += ["-i", str(source_dir / layer["source"])]
            chain = (f"[{i}:a]atrim=start={layer['start']}:duration={layer['duration']},"
                     f"asetpts=PTS-STARTPTS,aresample={RATE},aformat=channel_layouts=mono")
            if layer.get("filter"):
                chain += "," + layer["filter"]
            chain += f",volume={layer.get('gain', 1)}[a{i}]"
            filters.append(chain)
            labels.append(f"[a{i}]")
        filters.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0[out]")
        pcm = subprocess.check_output(command + ["-filter_complex", ";".join(filters),
                                      "-map", "[out]", "-f", "f32le", "-"])
        samples = array("f", pcm)
        if sys.byteorder != "little":
            samples.byteswap()
        # Keep 15 ms before and 60 ms after audible material; no dead lead-in.
        audible = [i for i, value in enumerate(samples) if abs(value) > 0.001]
        if not audible:
            raise ValueError(f"Silent source selection: {filename}")
        samples = samples[max(0, audible[0] - 662):min(len(samples), audible[-1] + 2646)]
        rms = math.sqrt(sum(x * x for x in samples) / len(samples))
        scale = min(0.0794 / max(rms, 1e-9), 0.5 / max(abs(x) for x in samples))
        for i in range(len(samples)):
            fade = min(1, i / 529, (len(samples) - i - 1) / 3528)
            samples[i] *= scale * fade
        duration = len(samples) / RATE
        if sys.byteorder != "little":
            samples.byteswap()
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(RATE),
                        "-ac", "1", "-i", "-", "-c:a", "libmp3lame", "-b:a", "96k",
                        "-map_metadata", "-1", str(ROOT / filename)], input=samples.tobytes(), check=True)
        clip["duration_seconds"] = round(duration, 4)
        clip["sha256"] = sha256((ROOT / filename).read_bytes())
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(f"Built {len(manifest['clips'])} clips: "
          f"{sum(p.stat().st_size for p in ROOT.glob('*.mp3')):,} bytes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    build(parser.parse_args().source_dir)
