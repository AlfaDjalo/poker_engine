# build.ps1
# Build cap_equity (and optionally poker_eval) using CMake.
# Run from the poker_engine root directory with your venv active:
#
#   cd C:\Users\David\Projects\crazy_asian_poker\poker_engine
#   .\build.ps1
#
# Prerequisites (all installable inside the venv):
#   pip install pybind11 cmake ninja
#
# The script:
#   1. Installs pybind11, cmake, ninja into the venv if missing
#   2. Runs cmake configure + build
#   3. Copies the resulting .pyd files into the poker_engine root

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── 0. Ensure we're in the poker_engine root ──────────────────────
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
Write-Host "`n==> Working directory: $root" -ForegroundColor Cyan

# ── 1. Install build deps into active venv ───────────────────────
Write-Host "`n==> Installing build dependencies..." -ForegroundColor Cyan
python -m pip install --quiet pybind11 cmake ninja

# ── 2. Locate cmake (installed into venv Scripts/) ───────────────
$cmake = python -c "import shutil,sys; c=shutil.which('cmake'); print(c or '')"
if (-not $cmake) {
    # Fallback: look in venv Scripts directly
    $venvScripts = Split-Path (python -c "import sys; print(sys.executable)") -Parent
    $cmake = Join-Path $venvScripts "cmake.exe"
}
if (-not (Test-Path $cmake)) {
    Write-Error "cmake not found. Make sure your venv is active and 'pip install cmake' succeeded."
    exit 1
}
Write-Host "    cmake: $cmake" -ForegroundColor Gray

# ── 3. Configure ─────────────────────────────────────────────────
$buildDir = Join-Path $root "_build"
Write-Host "`n==> Configuring CMake (build dir: $buildDir)..." -ForegroundColor Cyan

# Use Ninja generator for fast parallel builds; fall back to VS if not found
$ninja = python -c "import shutil; print(shutil.which('ninja') or '')"
if ($ninja) {
    $generator = "Ninja"
    Write-Host "    Generator: Ninja" -ForegroundColor Gray
} else {
    $generator = "Visual Studio 17 2022"
    Write-Host "    Generator: $generator (Ninja not found)" -ForegroundColor Yellow
}

$pythonExe = python -c "import sys; print(sys.executable)"

& $cmake -S $root -B $buildDir `
    -G $generator `
    -DCMAKE_BUILD_TYPE=Release `
    "-DPYTHON_EXECUTABLE=$pythonExe"

if ($LASTEXITCODE -ne 0) {
    Write-Error "CMake configure failed (exit $LASTEXITCODE)"
    exit $LASTEXITCODE
}

# ── 4. Build ──────────────────────────────────────────────────────
Write-Host "`n==> Building..." -ForegroundColor Cyan
& $cmake --build $buildDir --config Release --parallel

if ($LASTEXITCODE -ne 0) {
    Write-Error "CMake build failed (exit $LASTEXITCODE)"
    exit $LASTEXITCODE
}

# ── 5. Copy .pyd files into poker_engine root ────────────────────
Write-Host "`n==> Copying extension modules to $root ..." -ForegroundColor Cyan

# CMake installs to _build/ or _build/Release/ depending on generator
$searchDirs = @(
    $buildDir,
    (Join-Path $buildDir "Release"),
    (Join-Path $buildDir "lib"),
    (Join-Path $buildDir "lib\Release")
)

$copied = 0
foreach ($dir in $searchDirs) {
    if (Test-Path $dir) {
        $pyds = Get-ChildItem $dir -Filter "*.pyd" -ErrorAction SilentlyContinue
        foreach ($pyd in $pyds) {
            $dest = Join-Path $root $pyd.Name
            Copy-Item $pyd.FullName $dest -Force
            Write-Host "    Copied: $($pyd.Name)" -ForegroundColor Green
            $copied++
        }
    }
}

if ($copied -eq 0) {
    # Try cmake --install as fallback
    Write-Host "    No .pyd found by search, trying cmake --install..." -ForegroundColor Yellow
    & $cmake --install $buildDir --config Release --prefix $root
}

# ── 6. Verify ─────────────────────────────────────────────────────
Write-Host "`n==> Verifying imports..." -ForegroundColor Cyan
python -c "import poker_eval; print('  poker_eval OK')"
python -c "import cap_equity; print('  cap_equity OK')"

Write-Host "`n==> Build complete." -ForegroundColor Green
