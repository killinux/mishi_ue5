"""Run Python inside the open Unreal editor (the Python plugin's Remote Execution, enabled in Config/DefaultEngine.ini) and print
what it logged - the fast loop for materials, lights and levels: no editor restart.

    python Tools/ue_remote.py Tools/import_slice.py eros15_07        a script file with its arguments
    python Tools/ue_remote.py -c "import unreal; print(unreal.SystemLibrary.get_engine_version())"

Exit code 0 when the command ran without a Python error, 1 on an error, 2 when no editor answers.
"""
import glob
import os
import sys
import time


def engine_python_dir():
    for base in (r"D:\Program Files\Epic Games", r"C:\Program Files\Epic Games"):
        for d in sorted(glob.glob(os.path.join(base, "UE_5*")), reverse=True):
            p = os.path.join(d, "Engine", "Plugins", "Experimental", "PythonScriptPlugin", "Content", "Python")
            if os.path.isfile(os.path.join(p, "remote_execution.py")):
                return p
    raise SystemExit("no Unreal Engine with the Python plugin found")


sys.path.insert(0, engine_python_dir())
import remote_execution as remote  # noqa: E402


def run(command, mode, wait=15.0):
    r = remote.RemoteExecution()
    r.start()
    try:
        t0 = time.time()
        while not r.remote_nodes and time.time() - t0 < wait:
            time.sleep(0.2)
        if not r.remote_nodes:
            print("no Unreal editor answers (is it open with this project? remote execution is in Config/DefaultEngine.ini)")
            return 2
        r.open_command_connection(r.remote_nodes[0]["node_id"])
        res = r.run_command(command, unattended=True, exec_mode=mode, raise_on_failure=False)
        for o in res.get("output", []):
            text = o.get("output", "").rstrip()
            kind = o.get("type", "")
            print(text if kind == "Info" else "[%s] %s" % (kind, text))
        if not res.get("success"):
            print("FAILED:", res.get("result"))
        return 0 if res.get("success") else 1
    finally:
        r.stop()


def main():
    args = sys.argv[1:]
    if not args:
        raise SystemExit(__doc__)
    if args[0] == "-c":
        return run(args[1], remote.MODE_EXEC_STATEMENT if "\n" not in args[1] and ";" not in args[1] else remote.MODE_EXEC_FILE)
    script = os.path.abspath(args[0]).replace("\\", "/")
    command = '"%s"' % script + "".join(" " + a for a in args[1:])
    return run(command, remote.MODE_EXEC_FILE)


if __name__ == "__main__":
    sys.exit(main())
