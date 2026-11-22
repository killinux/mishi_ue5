"""The frame rates of a capture's shots (system Python):

    python Tools/bench_table.py <folder with timing.json> [<another> ...] [--all]

The game writes timing.json beside the pictures of every `shots` / `stills` / `tour` / `bench` run: each shot's name, what the
picture was made with (TSR, DLAA, DLSS quality ... + RR), every frame's own time and the engine's stop watches (game thread,
render thread, RHI thread, the card).  In a capture the scene's clock is fixed at 30 steps a second and the frames are rendered
as fast as they come, so a frame's time is the rate the picture can be made at.

Listed are the shots named _fps_<what>_<round> of Tools/shots_bench.json (`ue.ps1 bench`), pooled by what the picture was made
with; --all lists every shot on its own.  Several folders go side by side, runs of the same size into one column.

A machine that is doing something else with its card meanwhile (another program rendering: the card is shared by turns, a frame
then takes several times as long) need not spoil the numbers: the list goes four times through the upscalers, and the rate is
read from the stretches of 45 frames that were NOT disturbed - those within 1.25 x the time of the fastest one, their median.
"undisturbed" says how many of the stretches that was: near 100 % on an idle machine.  A row that is far off its neighbours
with a few percent undisturbed had no quiet stretch at all: run it again.
"""
import json
import os
import sys


def read(folder):
    with open(os.path.join(folder, "timing.json"), encoding="utf-8") as f:
        return json.load(f)


WINDOW = 45


def rate(shots):
    """fps of the undisturbed stretches of some shots (each a list of frame times), and their share of all stretches.

    A frame's own time says little (the game runs a few frames ahead of the card and then waits for it), 45 frames in a row do.
    """
    spans = []
    for f in shots:
        total = [0.0]
        for x in f:
            total.append(total[-1] + x)
        n = min(WINDOW, len(f))
        if n > 0:
            spans += [(total[i + n] - total[i]) / n for i in range(len(f) - n + 1)]
    if not spans:
        return 0.0, 0.0
    spans.sort()
    cluster = [x for x in spans if x <= spans[0] * 1.25]
    return 1000.0 / cluster[len(cluster) // 2], len(cluster) / float(len(spans))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    everything = "--all" in sys.argv
    if not args:
        print(__doc__)
        return 2
    runs = [read(a) for a in args]
    heads = ["%d x %d" % (r.get("width", 0), r.get("height", 0)) for r in runs]
    if everything:
        for r, h in zip(runs, heads):
            print(h)
            print("%-26s %-24s %6s %8s %9s %12s   %s" % ("shot", "picture", "frames", "seconds", "fps", "undisturbed", "ms a frame: game render rhi card"))
            for s in r["shots"]:
                fps, share = rate([s.get("frame_ms", [])])
                print("%-26s %-24s %6d %8.2f %9.1f %10.0f %%   %5.1f %5.1f %5.1f %5.1f" % (s["name"], s["picture"], s["frames"], s["seconds"], fps,
                    100 * share, s.get("game_ms", 0), s.get("render_ms", 0), s.get("rhi_ms", 0), s.get("gpu_ms", 0)))
        return 0
    # runs of one size are one column: more rounds to find quiet stretches in
    order = []
    sizes = []
    for h in heads:
        if h not in sizes:
            sizes.append(h)
    pooled = [dict() for _ in sizes]
    for r, h in zip(runs, heads):
        n = sizes.index(h)
        for s in r["shots"]:
            if not s["name"].startswith("_fps_"):
                continue
            if s["picture"] not in order:
                order.append(s["picture"])
            pooled[n].setdefault(s["picture"], []).append(s.get("frame_ms", []))
    if not order:
        print("no shots named _fps_* in there (--all lists every shot)")
        return 1
    w = max(len(p) for p in order) + 2
    print("%-*s" % (w, "picture") + "".join("%26s" % h for h in sizes))
    print("%-*s" % (w, "") + "".join("%26s" % "fps   x TSR  undisturbed" for _ in sizes))
    base = [rate(p.get(order[0], []))[0] for p in pooled]
    worst = 1.0
    for picture in order:
        line = "%-*s" % (w, picture)
        for n, p in enumerate(pooled):
            if picture not in p:
                line += "%26s" % "-"
                continue
            fps, share = rate(p[picture])
            worst = min(worst, share)
            line += "%9.1f %6.2f %7.0f %%  " % (fps, fps / base[n] if base[n] > 0 else 0.0, 100 * share)
        print(line)
    if worst < 0.9:
        print("(the card was shared with another program for part of the run: the rates are those of the undisturbed stretches)")
    return 0


sys.exit(main())
