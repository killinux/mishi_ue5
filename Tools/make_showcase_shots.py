"""The check shots of a showcase slice, written from its slice.json: python Tools/make_showcase_shots.py Import/<slice>

-> Tools/shots_<slice>.json (the look of her: the stances from every side, face, chest, waist, legs, the panel) and
   Tools/shots_<slice>_fx.json (every skill at the moments its hits land - where its effects are at their fullest).
Written for a slice that has no hand-made lists yet (a08_s01's own were made by hand, shot by shot); edit the result freely.
"""
import json
import os
import sys


def main():
    d = sys.argv[1].rstrip("/\\")
    name = os.path.basename(d)
    with open(os.path.join(d, "slice.json"), encoding="utf-8") as f:
        s = json.load(f)
    phase = {p["trigger"]: i for i, p in enumerate(s["phases"])}
    parts = {p["name"]: p for p in s["parts"]}
    cues = s.get("cues", {})
    look = [
        {"name": "01_default", "phase": phase["stance"], "seconds": 2.5, "yaw": 0, "y": -1, "zoom": 1.0},
        {"name": "02_front", "seconds": 1.0, "yaw": 20, "y": 0.5, "zoom": 1.0},
        {"name": "03_back", "seconds": 1.0, "yaw": 200, "y": 0.55, "zoom": 1.0},
        {"name": "04_side", "seconds": 1.0, "yaw": 110, "y": 0.5, "zoom": 0.9},
        {"name": "05_wide", "seconds": 1.0, "yaw": 30, "y": 0.6, "zoom": 2.6},
        {"name": "06_face", "seconds": 1.0, "bone": "Bip001-Head", "offset_local": [6, -6, 0], "from": [0.25, -1, 0.3], "distance": 50},
        {"name": "07_chest", "seconds": 1.0, "bone": "Bip001-Spine2", "from": [0.3, -1, 0.25], "distance": 80},
        {"name": "08_waist", "seconds": 1.0, "bone": "Bip001-Pelvis", "from": [0.2, -1, 0.5], "distance": 90},
        {"name": "09_legs", "seconds": 1.0, "bone": "Bip001-L-Calf", "from": [0.1, -1, 0.6], "distance": 90},
    ]
    if "show" in phase:
        look += [{"name": "10_show", "phase": phase["show"], "seconds": 2.0, "yaw": -15, "y": 0.5, "zoom": 0.9},
                 {"name": "11_show_back", "seconds": 1.0, "yaw": 165, "y": 0.5, "zoom": 1.0},
                 {"name": "12_show_face", "seconds": 1.0, "bone": "Bip001-Head", "offset_local": [6, -6, 0], "from": [0.25, -1, 0.3], "distance": 50}]
    if "ur" in phase:
        look += [{"name": "13_ur", "phase": phase["ur"], "seconds": 2.5, "yaw": 15, "y": 0.5, "zoom": 1.0},
                 {"name": "14_ur_side", "seconds": 1.0, "yaw": 100, "y": 0.5, "zoom": 1.0}]
    look += [
        {"name": "15_hud", "phase": phase["stance"], "seconds": 2.5, "yaw": 0, "y": -1, "zoom": 1.0, "hud": True},
        {"name": "16_low", "seconds": 1.0, "yaw": 35, "y": 0.12, "zoom": 1.1},
        {"name": "17_left", "seconds": 1.0, "yaw": -70, "y": 0.5, "zoom": 1.0},
        {"name": "18_high", "seconds": 1.0, "yaw": 150, "y": 0.95, "zoom": 1.6},
    ]
    fx = [{"name": "_stance", "phase": phase["stance"], "seconds": 1.5, "yaw": 30, "y": 0.5, "zoom": 1.6}]
    for trigger, part in (("skill1", "skill_01"), ("skill2", "skill_02"), ("skill3", "skill_03")):
        if trigger not in phase or part not in parts:
            continue
        length = parts[part]["duration"]
        hits = sorted({round(c["time"], 2) for c in cues.get(part, []) if c.get("kind") == "hit"})
        # the moments worth a picture: a little after the start, each hit, the middle of the gaps, shortly before the end
        times = {0.35, round(length - 0.35, 2)} | set(hits) | {round(h + 0.12, 2) for h in hits}
        for a, b in zip([0.0] + hits, hits + [length]):
            if b - a > 0.7:
                times.add(round((a + b) / 2, 2))
        last = 0.0
        first = True
        for i, t in enumerate(sorted(x for x in times if 0.05 < x < length - 0.05)):
            shot = {"name": "%s_%02d_%04.2fs" % (trigger, i, t), "seconds": round(t - last, 3) if not first else round(t, 3),
                    "hold": 0.4, "yaw": 35 if trigger != "skill3" else 15, "y": 0.5, "zoom": 1.9}
            if first:
                shot["phase"] = phase[trigger]
            fx.append(shot)
            first, last = False, t
        fx.append({"name": "_%s_end" % trigger, "seconds": round(max(length - last, 0.1) + 1.2, 2), "yaw": 30, "y": 0.5, "zoom": 1.6})
    here = os.path.dirname(os.path.abspath(__file__))
    for suffix, shots in (("", look), ("_fx", fx)):
        path = os.path.join(here, "shots_%s%s.json" % (name, suffix))
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(shots, f, ensure_ascii=False, indent=1)
            f.write("\n")
        print("%s: %d shots" % (path, len(shots)))


if __name__ == "__main__":
    main()
