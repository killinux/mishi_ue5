"""Material instances that lost their parent, per slice (run in the open editor: python Tools/ue_remote.py Tools/check_parents.py).

An instance without a parent is drawn as the engine's grey default material.  It happened to a whole slice when the masters
were rebuilt by deleting them (mishi_materials.Graph now rebuilds a master in place); this is the check that it has not again.
"""
import unreal

eal = unreal.EditorAssetLibrary
for folder in sorted(eal.list_assets("/Game/Mishi", recursive=False, include_folder=True)):
    if not folder.endswith("/") or folder.rstrip("/").endswith(("/Materials", "/Maps")):
        continue
    total, orphans = 0, []
    for p in eal.list_assets(folder, recursive=True, include_folder=False):
        a = unreal.load_asset(p)
        if isinstance(a, unreal.MaterialInstanceConstant):
            total += 1
            if a.get_editor_property("parent") is None:
                orphans.append(a.get_name())
    if total:
        (unreal.log_warning if orphans else unreal.log)("[MISHI] %s: %d material instances, %d without a parent %s" % (folder.rstrip("/"), total, len(orphans), orphans[:6]))
