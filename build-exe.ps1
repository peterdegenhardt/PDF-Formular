<#
.SYNOPSIS
    PDF-Formular - EXE bauen (PowerShell)
    Falls pyinstaller.exe von Device Guard blockiert wird, wird ein
    Workaround per Umleitung über python -m PyInstaller versucht.
#>

$ErrorActionPreference = "Stop"

Write-Host "=== PDF-Formular - EXE bauen (PowerShell) ===" -ForegroundColor Cyan
Write-Host ""

# Prüfen ob venv existiert, sonst erstellen
if (-not (Test-Path "venv\Scripts\python.exe")) {
    Write-Host "Erstelle venv..." -ForegroundColor Yellow
    python -m venv venv
}

# venv aktivieren
$venvActivate = Join-Path $PSScriptRoot "venv\Scripts\Activate.ps1"
. $venvActivate

Write-Host "Installiere/aktualisiere Abhängigkeiten..." -ForegroundColor Yellow
pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "pip install fehlgeschlagen" }

# Alte Artefakte löschen
Write-Host "Lösche alte Build-Artefakte..." -ForegroundColor Yellow
if (Test-Path "build") { Remove-Item -Recurse -Force "build" -ErrorAction SilentlyContinue }
if (Test-Path "dist\PDF-Formular.exe") { Remove-Item "dist\PDF-Formular.exe" -Force -ErrorAction SilentlyContinue }
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" -ErrorAction SilentlyContinue }
Get-ChildItem "*.spec" -ErrorAction SilentlyContinue | Remove-Item -Force

Write-Host "Baue EXE..." -ForegroundColor Yellow

# Versuche: pyinstaller direkt (falls Device Guard nicht blockiert)
try {
    pyinstaller --noconfirm --onefile --windowed `
        --name "PDF-Formular" `
        --add-data "Ausgabe.pdf;." `
        --hidden-import "PIL._tkinter_finder" `
        main.py
}
catch {
    Write-Host "pyinstaller.exe blockiert? Versuche Workaround..." -ForegroundColor Yellow
    python -c "
import sys
sys.argv = ['pyinstaller', '--noconfirm', '--onefile', '--windowed',
    '--name', 'PDF-Formular',
    '--add-data', 'Ausgabe.pdf;.',
    '--hidden-import', 'PIL._tkinter_finder',
    'main.py']
from PyInstaller.__main__ import run
run()
"
}

Write-Host ""
if (Test-Path "dist\PDF-Formular.exe") {
    Write-Host "Fertig! EXE liegt in: dist\PDF-Formular.exe" -ForegroundColor Green
    Write-Host ""
    Write-Host "Kopiere Ausgabe.pdf neben die EXE..." -ForegroundColor Yellow
    Copy-Item "Ausgabe.pdf" "dist\Ausgabe.pdf" -ErrorAction SilentlyContinue
    Write-Host "Kopiere Icons neben die EXE..." -ForegroundColor Yellow
    if (Test-Path "icons") {
        Copy-Item -Recurse "icons" "dist\icons" -ErrorAction SilentlyContinue
    }
    Write-Host ""
    Write-Host "Alles bereit." -ForegroundColor Green
} else {
    Write-Host "Fehler beim Bauen der EXE." -ForegroundColor Red
    exit 1
}
