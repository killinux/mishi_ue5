# Mishi UE5 in one place: find the engine, build the editor module, import a slice, play it, record the tour.
#   powershell -File Tools\ue.ps1 find
#   powershell -File Tools\ue.ps1 build
#   powershell -File Tools\ue.ps1 cpp                           (after a C++ change: quit the open editor, build, start it again)
#   powershell -File Tools\ue.ps1 import [-Slice eros15_07] [-Force]
#   powershell -File Tools\ue.ps1 play   [-Slice eros15_07]
#   powershell -File Tools\ue.ps1 tour   [-Slice eros15_07] [-Shots <file>] [-Tag <x>]   (Tools\tour.json frame by frame -> out\<slice>_tour.mp4, with sound)
#   powershell -File Tools\ue.ps1 shots  [-Slice eros15_07] [-Shots <file>] [-Tag <x>]   (look-dev stills -> Saved\MishiShots\<slice>_<tag>)
#   powershell -File Tools\ue.ps1 editor
param(
    [ValidateSet('find', 'build', 'cpp', 'import', 'play', 'tour', 'shots', 'editor')] [string]$Do = 'find',
    [string]$Slice = 'eros15_07',
    [switch]$Force,
    [string]$Shots = '',
    [string]$Tag = '',
    [int]$ResX = 1600,
    [int]$ResY = 900,
    [switch]$KeepFrames
)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Project = Join-Path $Root 'MishiUE.uproject'
$Ffmpeg = 'D:\Program Files\ffmpeg\bin\ffmpeg.exe'

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

function Invoke-Editor([string]$arguments, [string]$label) {
    Write-Host "$label ..."
    $p = Start-Process -FilePath $Editor -ArgumentList $arguments -PassThru -Wait
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
        Start-Process -FilePath $Editor -ArgumentList "`"$Project`" /Game/Mishi/Maps/$Slice -game -windowed -ResX=$ResX -ResY=$ResY -log"
    }
    'tour' {
        # the film: Tools\tour.json (or -Shots <file>), every frame of every shot -> out\<slice>_tour[_<tag>].mp4.  The game
        # records without sound and writes down what it played (timeline.json); Tools\tour_audio.py mixes the track from that.
        if (-not $Shots) { $Shots = Join-Path $Root 'Tools\tour.json' }
        $frames = Join-Path $Root "Saved\MishiTour\$Slice"
        if (Test-Path $frames) { Remove-Item -Recurse -Force $frames }
        $code = Invoke-Editor "`"$Project`" /Game/Mishi/Maps/$Slice -game -RenderOffscreen -ForceRes -ResX=$ResX -ResY=$ResY -benchmark -fps=30 -MishiTour -MishiShots=`"$Shots`" -MishiShotsDir=`"$frames`" -nosound -nosplash -unattended -log" 'tour'
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
    'shots' {
        # look-dev stills: Tools\shots_lookdev.json (or -Shots <file>) -> Saved\MishiShots\<slice>[_<tag>]\<name>.png
        if (-not $Shots) { $Shots = Join-Path $Root 'Tools\shots_lookdev.json' }
        $dir = Join-Path $Root "Saved\MishiShots\$Slice$(if ($Tag) { '_' + $Tag })"
        if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
        $code = Invoke-Editor "`"$Project`" /Game/Mishi/Maps/$Slice -game -windowed -ResX=$ResX -ResY=$ResY -benchmark -fps=30 -MishiShots=`"$Shots`" -MishiShotsDir=`"$dir`" -nosound -nosplash -unattended -log" 'shots'
        Get-ChildItem $dir -Filter *.png -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName }
        exit $code
    }
    'editor' {
        Start-Process -FilePath $Editor -ArgumentList "`"$Project`""
    }
}
