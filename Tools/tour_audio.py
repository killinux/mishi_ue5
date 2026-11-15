"""The sound track of a recorded tour.

The game process records without a sound device and writes down what the scene played and when (<frames>/timeline.json, by
frame).  This puts the same sounds together with ffmpeg: a voice line is cut off by the next one, a part's loop runs until the
next part's starts, the room's music loops under it all - at the volumes the game uses.

    python Tools/tour_audio.py --frames Saved/MishiTour/eros15_07 --slice Import/eros15_07 --out Saved/MishiTour/eros15_07/tour.m4a

System Python; ffmpeg at D:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe or on the PATH (--ffmpeg).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

FFMPEG = r"D:\Program Files\ffmpeg\bin\ffmpeg.exe"


def sound_file(slice_dir, name):
    """The .wav made for Unreal's import when there is one (it loops without a gap), the game's .ogg otherwise."""
    stem = os.path.splitext(name)[0]
    for path in (os.path.join(slice_dir, "_wav", stem + ".wav"), os.path.join(slice_dir, "audio", name)):
        if os.path.isfile(path):
            return path
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--frames", required=True, help="the folder of the recorded frames (holds timeline.json)")
    ap.add_argument("--slice", required=True, help="Import/<slice> (slice.json, audio/, _wav/)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--ffmpeg", default=FFMPEG if os.path.isfile(FFMPEG) else (shutil.which("ffmpeg") or "ffmpeg"))
    args = ap.parse_args()

    with open(os.path.join(args.frames, "timeline.json"), encoding="utf-8") as f:
        timeline = json.load(f)
    with open(os.path.join(args.slice, "slice.json"), encoding="utf-8") as f:
        slice_data = json.load(f)
    total = timeline["frames"] / args.fps
    events = sorted(timeline.get("sounds", []), key=lambda e: e["frame"])

    inputs, chains, labels = [], [], []

    def add(path, start, length, volume, loop):
        if length <= 0.02 or volume <= 0.0:
            return
        i = len(inputs)
        inputs.append((path, loop))
        fade = min(0.05, length / 2)
        chain = "[%d:a]atrim=0:%.3f,afade=t=out:st=%.3f:d=%.3f,volume=%.3f" % (i, length, length - fade, fade, volume)
        if start > 0.0:
            chain += ",adelay=%d:all=1" % round(start * 1000)
        chains.append(chain + "[a%d]" % i)
        labels.append("[a%d]" % i)

    music = slice_data.get("music") or {}
    path = sound_file(args.slice, music.get("file", "")) if music.get("file") else None
    if path:
        add(path, 0.0, total, float(music.get("volume", 0.35)), True)
    missing = []
    for kind, loop in (("voice", False), ("sfx", True)):
        mine = [e for e in events if e["kind"] == kind]
        for n, e in enumerate(mine):
            if not e.get("file"):
                continue                        # that kind stops here
            start = e["frame"] / args.fps
            end = mine[n + 1]["frame"] / args.fps if n + 1 < len(mine) else total
            path = sound_file(args.slice, e["file"])
            if not path:
                missing.append(e["file"])
                continue
            add(path, start, end - start, float(e.get("volume", 1.0)), loop)
    if not inputs:
        sys.exit("no sounds in the timeline")

    cmd = [args.ffmpeg, "-y", "-loglevel", "error"]
    for path, loop in inputs:
        if loop:
            cmd += ["-stream_loop", "-1"]
        cmd += ["-i", path]
    graph = ";".join(chains) + ";" + "".join(labels) + "amix=inputs=%d:normalize=0:duration=longest,atrim=0:%.3f,alimiter=limit=0.95[out]" % (
        len(labels), total)
    script = os.path.join(args.frames, "tour_audio_filter.txt")
    with open(script, "w", encoding="utf-8") as f:
        f.write(graph)
    cmd += ["-filter_complex_script", script, "-map", "[out]", "-c:a", "aac", "-b:a", "192k", args.out]
    r = subprocess.run(cmd)
    print("tour audio: %.1f s, %d sounds (%d voice, %d loops)%s -> %s" % (
        total, len(inputs), sum(1 for e in events if e["kind"] == "voice" and e.get("file")),
        sum(1 for e in events if e["kind"] == "sfx" and e.get("file")), ", missing %s" % sorted(set(missing)) if missing else "", args.out))
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
