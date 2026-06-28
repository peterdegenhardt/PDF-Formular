@echo off
REM PDF-Formular - EXE bauen mit venv + allen Abhängigkeiten
REM Setzt voraus: Python 3.11+ installiert
REM
REM Usage: Doppelklick oder build-exe.bat

setlocal enabledelayedexpansion

echo === PDF-Formular - EXE bauen ===
echo.

REM Python prüfen
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo FEHLER: Python nicht gefunden. Bitte Python 3.11+ installieren.
    pause
    exit /b 1
)

REM venv erstellen/aktivieren
if not exist venv\Scripts\python.exe (
    echo Erstelle venv...
    python -m venv venv
    if !errorlevel! neq 0 (
        echo FEHLER: venv konnte nicht erstellt werden.
        pause
        exit /b 1
    )
    echo venv angelegt.
)

echo Aktiviere venv...
call venv\Scripts\activate.bat

REM Abhängigkeiten installieren
echo Installiere/aktualisiere Abhaengigkeiten...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo FEHLER: pip install fehlgeschlagen.
    pause
    exit /b 1
)

REM pyinstaller prüfen (ist in requirements, aber sicherheitshalber)
where pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo pyinstaller nicht gefunden - installiere...
    pip install pyinstaller
)

echo.
echo Loesche alte Build-Artefakte...
if exist build rmdir /s /q build
REM dist löschen – ggf. mit force für Permission-Konflikte
if exist dist\PDF-Formular.exe del /f /q dist\PDF-Formular.exe >nul 2>&1
if exist dist rmdir /s /q dist 2>nul
if exist *.spec del /f /q *.spec >nul 2>&1

echo Baue EXE...
pyinstaller --noconfirm --onefile --windowed ^
    --name "PDF-Formular" ^
    --add-data "Ausgabe.pdf;." ^
    --hidden-import PIL._tkinter_finder ^
    main.py

echo.
if exist "dist\PDF-Formular.exe" (
    echo Fertig! EXE liegt in: dist\PDF-Formular.exe
    echo.
    echo Kopiere Ausgabe.pdf neben die EXE...
    copy Ausgabe.pdf dist\Ausgabe.pdf >nul
    echo Kopiere Icons neben die EXE...
    if exist icons\NUL xcopy /E /I /Y icons dist\icons >nul
    echo Alles bereit.
) else (
    echo Fehler beim Bauen der EXE.
    pause
    exit /b 1
)

pause
