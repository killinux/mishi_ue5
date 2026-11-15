"""slice.json of a showcase scene: one character on a battle stage, her battle motions on buttons.

Unity's MishiUeExport.ExportShowcase writes the raw facts (Import/<char>_<stage>/showcase.json, skill_sheet.json - the game's
own timelines: per action its body clip, hit times, sounds and voices with their start times, camera shakes).  This turns them
into the slice.json the game module reads (the eros slices' format plus "kind", phase labels, timed "cues", an "auto" playlist):

    python Tools/make_showcase.py Import/a08_s01

  parts   = her clips: loops (the battle stance, the showcase idle, the lying pose) and one-shots that go back to a loop
  phases  = the panel's buttons, one per action; phase_rules lead each button straight to its part
  cues    = per part, what the game's timeline does at which second: a sound, a voice line (jp / en), a camera shake, the
            unit's move (the dash to the one it attacks, the way back), the skill's own camera
  target  = where the one she fights stands (the stage's first enemy slot), in her space
  camera  = an orbit round her (the eros rig's numbers, made here: the game's battle camera is a fixed side view)
  anchor  = where she stands on the stage: the first player slot of the stage's formation, facing the enemy line

Also bakes the sky (Tools/mishi_sky.py; without the game's fog band unless --fog-band).  System Python.
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mishi_sky  # noqa: E402

# the buttons, in order: (trigger, label, part, what follows a one-shot, seconds the auto mode stays when the part loops)
ACTIONS = [
    ("stance", "战斗站姿", "idle_01", None, (3.0, 4.0)),          # battle stance
    ("show", "展示", "idle_02", None, (5.0, 5.0)),                          # showcase idle
    ("react1", "互动 1", "react_01", "idle_02", None),
    ("react2", "互动 2", "react_02", "idle_02", None),
    ("skill1", "技能 1", "skill_01", "idle_01", None),
    ("skill2", "技能 2", "skill_02", "idle_01", None),
    ("skill3", "大招", "skill_03", "idle_01", None),                        # the super
    ("hurt", "受击", "hurt", "idle_01", None),
    ("down", "倒下", "die", "rip", (2.5, 3.0)),
]
# the skill sheet's actions that drive each part
SHEET_ACTION = {"skill_01": "skill1", "skill_02": "skill2", "skill_03": "skill3", "hurt": "hurt", "die": "die"}
# the auto mode's round: the buttons by trigger
AUTO = ["show", "react1", "show", "react2", "stance", "skill1", "stance", "skill2", "stance", "skill3", "stance", "hurt", "stance"]


# The game's timeline of the super has no camera of its own (the battle's far side view stays).  Its finish is made to be seen
# from behind her as the other skills' are - she ends with her back to the one she struck - so it gets their camera.
SKILL_CAMERA = {"skill_03": {"time": 0.0, "duration": 4.2, "fov": 40.0, "position": [0.0, 1.42, -4.27], "rotation": [0.025736, 0.0, 0.0, 0.999669]}}


def quat_rotate(q, v):
    x, y, z, w = q
    ux, uy, uz = v
    tx, ty, tz = 2 * (y * uz - z * uy), 2 * (z * ux - x * uz), 2 * (x * uy - y * ux)
    return (ux + w * tx + y * tz - z * ty, uy + w * ty + z * tx - x * tz, uz + w * tz + x * ty - y * tx)


def quat_mul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx, aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


def chain_place(nodes):
    """A chain of nodes (each with its local position / rotation / scale, the first one the unit's pivot) -> the last one's
    place and turn in the unit's space."""
    pos, rot = (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0)
    for n in nodes:
        p, r, s = n.get("position", {}), n.get("rotation", {}), n.get("scale", {})
        lp = (p.get("x", 0.0), p.get("y", 0.0), p.get("z", 0.0))
        lr = (r.get("x", 0.0), r.get("y", 0.0), r.get("z", 0.0), r.get("w", 1.0))
        step = quat_rotate(rot, lp)
        pos = (pos[0] + step[0], pos[1] + step[1], pos[2] + step[2])
        rot = quat_mul(rot, lr)
    return pos, rot


def camera_cue(cam):
    """A camera track of the game's timeline: the virtual camera follows a node of the unit (its place), turned as the camera's
    own node is."""
    follow = (cam.get("follow") or {}).get("nodes") or []
    own = (cam.get("node") or {}).get("nodes") or []
    if not follow and not own:
        return None
    pos, _ = chain_place(follow or own)
    _, rot = chain_place(own or follow)
    return {"time": round(cam["start"], 4), "kind": "camera", "duration": round(cam["end"] - cam["start"], 4), "fov": cam.get("fov", 40.0),
            "position": [round(v, 4) for v in pos], "rotation": [round(v, 6) for v in rot]}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("slice_dir")
    ap.add_argument("--sky-width", type=int, default=4096)
    ap.add_argument("--no-sky", action="store_true", help="do not bake the sky again (the last bake stays)")
    ap.add_argument("--fog-band", action="store_true", help="the sky with the game's band of fog colour over its lower part")
    args = ap.parse_args()
    d = args.slice_dir
    with open(os.path.join(d, "showcase.json"), encoding="utf-8") as f:
        show = json.load(f)
    sheet = {}
    if show.get("sheet") and os.path.isfile(os.path.join(d, show["sheet"])):
        with open(os.path.join(d, show["sheet"]), encoding="utf-8") as f:
            sheet = {a["name"]: a for a in json.load(f).get("actions", [])}
    clips = {c["name"]: c for c in show["clips"]}
    sounds = show.get("sounds", {})

    phases, rules, parts, cues, seen = [], [], [], {}, set()

    def add_part(name, loop, nxt, phase):
        if name in seen or name not in clips:
            return
        seen.add(name)
        parts.append({"name": name, "female_clip": name, "male_clip": None, "loop": loop, "speed": 1.0, "duration": clips[name]["length"],
                      "next": nxt or "", "exit_time": 1.0 if loop else 0.97, "blend": 0.25, "phase": phase, "female_fx": None, "male_fx": None})
        action = sheet.get(SHEET_ACTION.get(name, ""))
        marks = []
        if action:
            for s in action.get("sounds", []):
                if not s.get("muted") and s.get("clip") in sounds:
                    marks.append({"time": round(s["start"], 4), "kind": "sfx", "file": sounds[s["clip"]], "volume": s.get("volume", 1.0)})
            for v in action.get("voices", []):
                if v.get("muted"):
                    continue
                by_lang = {c["language"]: sounds.get(c["clip"]) for c in v.get("clips", [])}
                jp = by_lang.get("2") or next((f for n, f in sounds.items() if n == v["name"] + "_jp"), None)
                en = by_lang.get("1") or next((f for n, f in sounds.items() if n == v["name"] + "_en"), None)
                if jp or en:
                    marks.append({"time": round(v["start"], 4), "kind": "voice", "jp": jp, "en": en, "volume": 1.0})
            for s in action.get("shakes", []):
                marks.append({"time": round(s["time"], 4), "kind": "shake", "duration": s.get("duration", 0.5), "amplitude": s.get("amplitude", 0.5),
                              "frequency": s.get("frequency", 0.0)})
            for h in action.get("hits", []):
                marks.append({"time": round(h["time"], 4), "kind": "hit", "what": h.get("what"), "ratio": h.get("ratio", 1.0)})
            # the unit's own way across the stage: the dash to the one it attacks, the way back.  The clip is made for it - it
            # steps back by what the unit goes forward - so without the move she would slide where the game has her arrive.
            for mv in action.get("moves", []):
                marks.append({"time": round(mv["start"], 4), "kind": "move", "move": mv.get("kind"),
                              "duration": round(mv["end"] - mv["start"], 4), "radius": mv.get("radius", 1.0)})
            # the skill's own camera: a virtual camera at a place of the unit (behind it: she dashes off and turns to it)
            cams = [camera_cue(c) for c in action.get("cameras", [])]
            if not cams and name in SKILL_CAMERA:
                cams = [dict(SKILL_CAMERA[name], kind="camera", ours=True)]
            marks.extend(c for c in cams if c)
        if marks:
            cues[name] = sorted(marks, key=lambda m: m["time"])

    for i, (trigger, label, part, nxt, stay) in enumerate(ACTIONS):
        if part not in clips:
            continue
        index = len(phases)
        phases.append({"trigger": trigger, "label": label, "timer": list(stay or (1.0, 1.0))})
        rules.append({"trigger": trigger, "to": part, "duration": 0.25, "phase_equals": [], "phase_not_equals": []})
        add_part(part, nxt is None, nxt, index)
    # the loops the one-shots return to that have no button of their own (the lying pose): they stay in their one-shot's phase
    for trigger, label, part, nxt, stay in ACTIONS:
        if nxt and nxt not in seen and nxt in clips:
            add_part(nxt, True, None, next(i for i, p in enumerate(phases) if p["trigger"] == trigger))
    # her two showcase lines go with the two reactions
    for part, voice in zip(("react_01", "react_02"), show.get("showcase_voices", [])):
        if part in seen:
            cues.setdefault(part, []).insert(0, {"time": 0.15, "kind": "voice", "jp": voice, "en": voice, "volume": 1.0})
    index_of = {p["trigger"]: i for i, p in enumerate(phases)}
    auto = [index_of[t] for t in AUTO if t in index_of]

    # where she stands: the first slot of the player's formation (the stage's ArenaCenter when there is none), facing the enemy
    places = show.get("anchors", [])
    slot = next((a for a in places if a["path"].endswith("FormationSetting/Player1/1/Anchor1")), None)
    enemy = next((a for a in places if a["path"].endswith("FormationSetting/Player2/1/Anchor1")), None)
    centre = next((a for a in places if a["name"] == "ArenaCenter"), None)
    stand = slot or centre or {"position": [0, 0, 0], "rotation": [0, 0, 0, 1]}
    pos = stand["position"]
    rot = [0, 0, 0, 1]
    target = [0.0, 0.0, 6.0]                # where the one she fights stands, in her own space: straight ahead
    if enemy:
        yaw = math.atan2(enemy["position"][0] - pos[0], enemy["position"][2] - pos[2])
        rot = [0, round(math.sin(yaw / 2), 6), 0, round(math.cos(yaw / 2), 6)]
        target = [0.0, 0.0, round(math.hypot(enemy["position"][0] - pos[0], enemy["position"][2] - pos[2]), 4)]
    sun = next((L for L in show.get("lights", []) if L["type"] == "Directional" and L.get("enabled", True)), None)
    sun_note = None
    if sun:
        f = quat_rotate(sun["rotation"], (0.0, 0.0, 1.0))             # the way the light travels
        sun_note = {"travels": [round(v, 4) for v in f], "elevation": round(math.degrees(math.asin(-f[1])), 1),
                    "from_azimuth": round(math.degrees(math.atan2(-f[0], -f[2])), 1)}

    sky = None
    if show.get("sky"):
        if not args.no_sky:
            sky = mishi_sky.bake(d, args.sky_width, args.fog_band)
        elif os.path.isfile(os.path.join(d, "sky.json")):
            with open(os.path.join(d, "sky.json"), encoding="utf-8") as f:
                sky = json.load(f)                  # --no-sky: the last bake stays

    out = {
        "kind": "showcase",
        "posture": "%s_%s" % (show["character"], show["stage"]), "title": "Inase %s" % show["character"], "outfit": show["character"],
        "scene": show["character"], "room": show["stage"],
        "space": show.get("space"),
        "female": dict(show["female"], character=show["character"]),
        "male": {"fbx": None, "root": None, "ok": False, "offset": None},
        "room_fbx": show.get("room_fbx"), "room_meshes_fbx": show.get("room_meshes_fbx"), "room_instances": show.get("room_instances"),
        "materials": show.get("materials"),
        "anchor": {"position": pos, "rotation": rot, "name": stand.get("name")},
        "target": target,
        "posture_anchor": {"position": [0, 0, 0], "rotation": [0, 0, 0, 1]},
        # an orbit round her chest: level at 3.3 m, from above at 1.6 m out and 1.9 m up, from near the ground at 2.9 m; she faces
        # the anchor's +Z and the orbit starts behind her, so the view starts half a turn round, a little to her right
        "camera": {"fov": 30.0, "top": [1.9, 1.6], "middle": [0.0, 3.3], "bottom": [-0.85, 2.9], "y_axis": 0.5, "x_axis": 160.0,
                   "zoom": 1.0, "zoom_min": 0.2, "zoom_max": 3.0, "target": [0.0, 1.0, 0.0], "box_center": [0.0, 1.0, 0.0],
                   "box_extent": [1.2, 0.95, 1.2]},
        "phases": phases, "phase_rules": rules, "parts": parts, "cues": cues, "auto": auto,
        "shape_tracks": {}, "voices": [], "lines": [], "sfx": [],
        "music": {"file": show.get("music"), "volume": 0.22},
        "lights": show.get("lights", []), "sun": sun_note,
        "render_settings": show.get("render_settings"),
        "sky": sky,
        # the stage's post volume is in a scene of its own; these are its numbers (the stage survey of 10-02)
        "post": {"bloom": True, "bloom_threshold": 0.8, "bloom_intensity": 0.8, "dof": False, "dof_focus": 32.0, "dof_transition": 0.5,
                 "vignette": 0.4, "chromatic": 0.1},
        "audio": sorted(set(list(sounds.values()) + show.get("showcase_voices", []) + ([show["music"]] if show.get("music") else []))),
    }
    with open(os.path.join(d, "slice.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("slice.json: %d buttons, %d parts, cues for %s, auto %s, stands at %s (%s), sun %s" % (
        len(phases), len(parts), {k: len(v) for k, v in cues.items()}, auto, pos, stand.get("name"), sun_note))


if __name__ == "__main__":
    main()
