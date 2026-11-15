# Mishi UE5 in one place: find the engine, build the editor module, import a slice, play it, record the tour.
#   powershell -File Tools\ue.ps1 find
#   powershell -File Tools\ue.ps1 build
#   powershell -File Tools\ue.ps1 import [-Slice eros15_07] [-Force]
#   powershell -File Tools\ue.ps1 play   [-Slice eros15_07]
#   powershell -File Tools\ue.ps1 tour   [-Slice eros15_07]      (frames -> out\<slice>_tour.mp4, with the room's music)
#   powershell -File Tools\ue.ps1 editor
param(
    [ValidateSet('find', 'build', 'import', 'play', 'tour', 'shots', 'editor')] [string]$Do = 'find',
    [string]$Slice = 'eros15_07',
    [switch]$Force,
    [string]$Shots = '',
    [string]$Tag = '',
    [int]$ResX = 1600,
    [int]$ResY = 900
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
        $frames = Join-Path $Root "Saved\MishiTour\$Slice"
        if (Test-Path $frames) { Remove-Item -Recurse -Force $frames }
        $code = Invoke-Editor "`"$Project`" /Game/Mishi/Maps/$Slice -game -windowed -ResX=$ResX -ResY=$ResY -benchmark -fps=30 -MishiTour -MishiTourDir=`"$frames`" -nosound -log" 'tour'
        $out = Join-Path $Root 'out'
        New-Item -ItemType Directory -Force $out | Out-Null
        $mp4 = Join-Path $out "${Slice}_tour.mp4"
        $music = Get-ChildItem (Join-Path $Root "Import\$Slice\audio") -Filter 'bgm_*' -ErrorAction SilentlyContinue | Select-Object -First 1
        $pattern = Join-Path $frames 'frame_%05d.png'
        if ($music) {
            & $Ffmpeg -y -loglevel error -framerate 30 -i $pattern -i $music.FullName -filter:a 'volume=0.6' -shortest -c:v libx264 -pix_fmt yuv420p -crf 18 -c:a aac $mp4
        } else {
            & $Ffmpeg -y -loglevel error -framerate 30 -i $pattern -c:v libx264 -pix_fmt yuv420p -crf 18 $mp4
        }
        Write-Host "tour -> $mp4"
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
