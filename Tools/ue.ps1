# Mishi UE5 in one place: find the engine, build the editor module, import a slice, play it, record the tour.
#   powershell -File Tools\ue.ps1 find
#   powershell -File Tools\ue.ps1 build
#   powershell -File Tools\ue.ps1 cpp                           (after a C++ change: quit the open editor, build, start it again)
#   powershell -File Tools\ue.ps1 import [-Slice eros15_07] [-Force]
#   powershell -File Tools\ue.ps1 play   [-Slice eros15_07]
#   powershell -File Tools\ue.ps1 tour   [-Slice eros15_07] [-Shots <file>] [-Tag <x>]   (Tools\tour.json frame by frame -> out\<slice>_tour.mp4, with sound)
#   powershell -File Tools\ue.ps1 shots  [-Slice eros15_07] [-Shots <file>] [-Tag <x>]   (look-dev stills -> Saved\MishiShots\<slice>_<tag>)
#   powershell -File Tools\ue.ps1 stills [-Slice eros15_07] [-Shots <file>] [-Tag <x>]   (path-traced stills: Tools\shots_stills.json -> out\stills\<slice>, 2560x1440 offscreen)
#   powershell -File Tools\ue.ps1 bench  [-Slice eros15_07] [-ResX 1920 -ResY 1080]      (the frame rate of every upscaler: Tools\shots_bench.json, offscreen)
#   powershell -File Tools\ue.ps1 editor
# Without -Shots, a slice's own list is used when there is one: Tools\tour_<slice>.json, shots_<slice>.json, stills_<slice>.json.
# -Upscale tsr|dlaa|quality|balanced|performance and -RR (ray reconstruction) pick what the picture is made with (play, tour, shots, stills).
param(
    [ValidateSet('find', 'build', 'cpp', 'import', 'play', 'tour', 'shots', 'stills', 'bench', 'editor')] [string]$Do = 'find',
    [string]$Slice = 'eros15_07',
    [switch]$Force,
    [string]$Shots = '',
    [string]$Tag = '',
    [int]$ResX = 1600,
    [int]$ResY = 900,
    [switch]$KeepFrames,
    [ValidateSet('', 'tsr', 'dlaa', 'quality', 'balanced', 'performance')] [string]$Upscale = '',
    [switch]$RR
)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Project = Join-Path $Root 'MishiUE.uproject'
$Ffmpeg = 'D:\Program Files\ffmpeg\bin\ffmpeg.exe'
# the game reads the shots file from its own working folder (the engine's): a full path, from here or from the project
if ($Shots -and -not [IO.Path]::IsPathRooted($Shots)) {
    $Shots = if (Test-Path $Shots) { (Resolve-Path $Shots).Path } else { Join-Path $Root $Shots }
}
# a slice's own shot list (Tools\tour_<slice>.json, stills_<slice>.json, shots_<slice>.json) before the eros slice's
function Get-ShotList([string]$kind, [string]$fallback) {
    $own = Join-Path $Root "Tools\${kind}_$Slice.json"
    if (Test-Path $own) { return $own }
    return (Join-Path $Root "Tools\$fallback")
}

function Get-EngineVersion([string]$dir) {
    $bv = Join-Path $dir 'Engine\Build\Build.version'
    if (-not (Test-Path $bv)) { return $null }
    $j = Get-Content $bv -Raw | ConvertFrom-Json
    return "$($j.MajorVersion).$($j.MinorVersion)"
}

function Find-Engine {
    $roots = New-Object System.Collections.Generic.List[string]
    $dat = 'C:\ProgramData\Epic\UnrealEngineLauncher\LauncherInstalled.dat'
    if (Test-Path $dat) {
        foreach ($i in (Get-Content $dat -Raw | ConvertFrom-Json).InstallationList) {
            if ($i.AppName -like 'UE_*') { $roots.Add($i.InstallLocation) }
        }
    }
    foreach ($k in Get-ChildItem 'HKLM:\SOFTWARE\EpicGames\Unreal Engine' -ErrorAction SilentlyContinue) {
        $d = (Get-ItemProperty $k.PSPath -ErrorAction SilentlyContinue).InstalledDirectory
        if ($d) { $roots.Add($d) }
    }
    foreach ($base in 'D:\Program Files\Epic Games', 'C:\Program Files\Epic Games', 'D:\Epic Games', 'E:\Epic Games') {
        foreach ($d in Get-ChildItem $base -Directory -Filter 'UE_5*' -ErrorAction SilentlyContinue) { $roots.Add($d.FullName) }
    }
    $found = $roots | Where-Object { $_ -and (Test-Path (Join-Path $_ 'Engine\Binaries\Win64\UnrealEditor.exe')) } | Sort-Object -Unique
    if (-not $found) { return $null }
    return $found | Sort-Object { [version](Get-EngineVersion $_) } -Descending | Select-Object -First 1
}

$Engine = Find-Engine
if (-not $Engine) {
    Write-Host 'No Unreal Engine 5 with UnrealEditor.exe found (Epic launcher: Unreal Engine > Library > Engine Versions > + > Install, to D:\Program Files\Epic Games).'
    exit 2
}
$Version = Get-EngineVersion $Engine
$Editor = Join-Path $Engine 'Engine\Binaries\Win64\UnrealEditor.exe'
Write-Host "engine $Version at $Engine"

# the project names the engine it was made for: the installed one
$text = [IO.File]::ReadAllText($Project)
$want = '"EngineAssociation": "' + $Version + '"'
if ($text -notmatch [regex]::Escape($want)) {
    $text = $text -replace '"EngineAssociation":\s*"[^"]*"', $want
    [IO.File]::WriteAllText($Project, $text, (New-Object Text.UTF8Encoding $false))
    Write-Host "MishiUE.uproject: EngineAssociation -> $Version"
}

# for shots and the tour: every ray tracing hit shader is there before the first frame (built in the background, the missing ones
# are a black stand-in material - black reflections, a black path-traced picture), the picture is rendered at its full size,
# and a mesh is drawn from the frame it appears in (the engine otherwise holds it back until its pipeline states are compiled:
# a shot that jumps into the middle of a skill had none of the skill's effects in it)
$Capture = '-dpcvars=r.RayTracing.NonBlockingPipelineCreation=0,r.ScreenPercentage=100,r.PSOPrecache.ProxyCreationStrategy=0,r.AsyncPipelineCompile=0'
# the picture's upscaler: -Upscale dlaa | quality | balanced | performance (NVIDIA's DLSS, Tools/install_dlss.py) or tsr; -RR = ray reconstruction
$Picture = "$(if ($Upscale) { " -MishiUpscale=$Upscale" })$(if ($RR) { ' -MishiRR' })"


function Invoke-Editor([string]$arguments, [string]$label) {
    Write-Host "$label ..."
    # (not -Wait: that waits for every process the engine started as well - with NVIDIA's DLSS plugin loaded the driver's
    # nvngx_update.exe helpers, which look for new DLSS models over the network and can sit there for good)
    $p = Start-Process -FilePath $Editor -ArgumentList $arguments -PassThru
    $null = $p.Handle
    $p.WaitForExit()
    $helpers = @(Get-CimInstance Win32_Process -Filter "Name='nvngx_update.exe'" -ErrorAction SilentlyContinue)
    $ours = @($p.Id)
    for ($round = 0; $round -lt 3; $round++) { $ours += @($helpers | Where-Object { $ours -contains $_.ParentProcessId } | ForEach-Object { $_.ProcessId }) }
    $helpers | Where-Object { $ours -contains $_.ProcessId } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Write-Host "$label exit code $($p.ExitCode); log $Root\Saved\Logs\MishiUE.log"
    return $p.ExitCode
}

switch ($Do) {
    'find' { }
    'build' {
        $bat = Join-Path $Engine 'Engine\Build\BatchFiles\Build.bat'
        & $bat MishiUEEditor Win64 Development "-Project=$Project" -WaitMutex -NoHotReloadFromIDE
        exit $LASTEXITCODE
    }
    'cpp' {
        # the editor holds the module's DLL: save and quit it, build, start it again and wait until it answers remote Python
        $remote = Join-Path $Root 'Tools\ue_remote.py'
        if (Get-Process UnrealEditor -ErrorAction SilentlyContinue) {
            & python $remote -c "import unreal; unreal.EditorAssetLibrary.save_directory('/Game/Mishi', only_if_is_dirty=True, recursive=True); unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level(); unreal.SystemLibrary.quit_editor()" | Out-Null
            $n = 0
            while ((Get-Process UnrealEditor -ErrorAction SilentlyContinue) -and $n -lt 60) { Start-Sleep -Seconds 2; $n++ }
        }
        $bat = Join-Path $Engine 'Engine\Build\BatchFiles\Build.bat'
        $log = Join-Path $Root '_work\build.log'
        New-Item -ItemType Directory -Force (Join-Path $Root '_work') | Out-Null
        & $bat MishiUEEditor Win64 Development "-Project=$Project" -WaitMutex -NoHotReloadFromIDE *> $log
        $code = $LASTEXITCODE
        Select-String -Path $log -Pattern 'error|Result:' | Select-Object -First 30 | ForEach-Object { $_.Line }
        Start-Process -FilePath $Editor -ArgumentList "`"$Project`" -nosplash"
        $n = 0
        do { Start-Sleep -Seconds 5; $n++; $r = & python $remote -c "print('up')" 2>&1 | Select-Object -Last 1 } while ($r -notmatch '^up' -and $n -lt 40)
        Write-Host "editor: $r after $($n * 5) s; build exit $code"
        exit $code
    }
    'import' {
        $env:MISHI_SLICE = $Slice
        $env:MISHI_QUIT = '1'
        $env:MISHI_FORCE = $(if ($Force) { '1' } else { '0' })
        $script = (Join-Path $Root 'Tools\import_slice.py') -replace '\\', '/'
        $code = Invoke-Editor "`"$Project`" -ExecutePythonScript=`"$script`" -unattended -nosplash -nopause" 'import'
        $rep = Join-Path $Root "Import\$Slice\ue_import_report.json"
        if (Test-Path $rep) { Get-Content $rep -Raw | Write-Host }
        exit $code
    }
    'play' {
        Start-Process -FilePath $Editor -ArgumentList "`"$Project`" /Game/Mishi/Maps/$Slice -game -windowed -ResX=$ResX -ResY=$ResY$Picture"
    }
    'tour' {
        # the film: Tools\tour.json (or -Shots <file>), every frame of every shot -> out\<slice>_tour[_<tag>].mp4.  The game
        # records without sound and writes down what it played (timeline.json); Tools\tour_audio.py mixes the track from that.
        if (-not $Shots) { $Shots = Get-ShotList 'tour' 'tour.json' }
        $frames = Join-Path $Root "Saved\MishiTour\$Slice"
        if (Test-Path $frames) { Remove-Item -Recurse -Force $frames }
        $code = Invoke-Editor "`"$Project`" /Game/Mishi/Maps/$Slice -game -RenderOffscreen -ForceRes -ResX=$ResX -ResY=$ResY -benchmark -fps=30 $Capture -MishiTour -MishiShots=`"$Shots`" -MishiShotsDir=`"$frames`" -nosound -nosplash -unattended$Picture" 'tour'
        $out = Join-Path $Root 'out'
        New-Item -ItemType Directory -Force $out | Out-Null
        $mp4 = Join-Path $out "${Slice}_tour$(if ($Tag) { '_' + $Tag }).mp4"
        $pattern = Join-Path $frames 'frame_%05d.bmp'
        $track = Join-Path $frames 'tour.m4a'
        & python (Join-Path $Root 'Tools\tour_audio.py') --frames $frames --slice (Join-Path $Root "Import\$Slice") --out $track --ffmpeg $Ffmpeg
        if ($LASTEXITCODE -eq 0 -and (Test-Path $track)) {
            & $Ffmpeg -y -loglevel error -framerate 30 -i $pattern -i $track -c:v libx264 -pix_fmt yuv420p -crf 16 -preset slow -c:a copy -shortest -movflags +faststart $mp4
        } else {
            & $Ffmpeg -y -loglevel error -framerate 30 -i $pattern -c:v libx264 -pix_fmt yuv420p -crf 16 -preset slow -movflags +faststart $mp4
        }
        $count = (Get-ChildItem $frames -Filter 'frame_*.bmp').Count
        Write-Host "tour -> $mp4 ($count frames)"
        # the frames are 8 MB each (uncompressed): gone once the film is there, unless -KeepFrames
        if (-not $KeepFrames -and (Test-Path $mp4) -and (Get-Item $mp4).Length -gt 0) { Remove-Item (Join-Path $frames 'frame_*.bmp') -Force }
        exit $code
    }
    'stills' {
        # path-traced stills of held poses: Tools\shots_stills.json (or -Shots <file>) -> out\stills\<slice>[_<tag>]\<name>.png,
        # rendered offscreen (2560x1440 unless -ResX / -ResY say otherwise); about two minutes a still at 512 samples
        if (-not $Shots) { $Shots = Get-ShotList 'stills' 'shots_stills.json' }
        if (-not $PSBoundParameters.ContainsKey('ResX')) { $ResX = 2560 }
        if (-not $PSBoundParameters.ContainsKey('ResY')) { $ResY = 1440 }
        $dir = Join-Path $Root "out\stills\$Slice$(if ($Tag) { '_' + $Tag })"
        New-Item -ItemType Directory -Force $dir | Out-Null
        $code = Invoke-Editor "`"$Project`" /Game/Mishi/Maps/$Slice -game -RenderOffscreen -ForceRes -ResX=$ResX -ResY=$ResY -benchmark -fps=30 $Capture -MishiShots=`"$Shots`" -MishiShotsDir=`"$dir`" -nosound -nosplash -unattended$Picture" 'stills'
        & python (Join-Path $Root 'Tools\sheet.py') $dir --cols 3 --width 853
        Get-ChildItem $dir -Filter *.png | ForEach-Object { $_.FullName }
        exit $code
    }
    'shots' {
        # look-dev stills: Tools\shots_lookdev.json (or -Shots <file>) -> Saved\MishiShots\<slice>[_<tag>]\<name>.png
        if (-not $Shots) { $Shots = Get-ShotList 'shots' 'shots_lookdev.json' }
        $dir = Join-Path $Root "Saved\MishiShots\$Slice$(if ($Tag) { '_' + $Tag })"
        if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
        $code = Invoke-Editor "`"$Project`" /Game/Mishi/Maps/$Slice -game -windowed -ResX=$ResX -ResY=$ResY -benchmark -fps=30 $Capture -MishiShots=`"$Shots`" -MishiShotsDir=`"$dir`" -nosound -nosplash -unattended$Picture" 'shots'
        Get-ChildItem $dir -Filter *.png -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName }
        exit $code
    }
    'bench' {
        # how fast the picture comes with each upscaler: Tools\shots_bench.json switches through them in ONE run (the same six
        # seconds of the scene each time, after a second to settle) -> Saved\MishiShots\<slice>_bench[_<tag>]\timing.json and a
        # picture of each.  Offscreen like the film, so any size can be asked for; nothing else should be using the card.
        if (-not $Shots) { $Shots = Get-ShotList 'bench' 'shots_bench.json' }
        if (-not $PSBoundParameters.ContainsKey('ResX')) { $ResX = 1920 }
        if (-not $PSBoundParameters.ContainsKey('ResY')) { $ResY = 1080 }
        $dir = Join-Path $Root "Saved\MishiShots\${Slice}_bench$(if ($Tag) { '_' + $Tag })"
        if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
        $code = Invoke-Editor "`"$Project`" /Game/Mishi/Maps/$Slice -game -RenderOffscreen -ForceRes -ResX=$ResX -ResY=$ResY -benchmark -fps=30 $Capture -MishiShots=`"$Shots`" -MishiShotsDir=`"$dir`" -nosound -nosplash -unattended" 'bench'
        if (Test-Path (Join-Path $dir 'timing.json')) { & python (Join-Path $Root 'Tools\bench_table.py') $dir }
        exit $code
    }
    'editor' {
        Start-Process -FilePath $Editor -ArgumentList "`"$Project`""
    }
}
