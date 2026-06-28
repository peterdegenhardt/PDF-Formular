# PDF-Formular Füller & Template-Editor

Eine tkinter-Desktop-App zum Ausfüllen und Bearbeiten von PDF-Formularen sowie zum Erstellen von PDF-Template-Editoren.

## Features

- PDF-Formularfelder ausfüllen (Text, Checkbox, Auswahllisten)
- Template-Editor mit Zeichenwerkzeugen (Pfeil, Linie, Rechteck, Ellipse, Maske, Bild, Stempel)
- Datumsfeld-Werkzeug
- Mehrseiten-Navigation mit Vor-/Zurück
- Vorschau und PDF-Export
- Dunkles Design (Catppuccin Mokka)
- Farbige Symbolleisten-Icons

## Installation

1. Repo klonen:
   ```
   git clone https://github.com/peterdegenhardt/PDF-Formular.git
   cd PDF-Formular
   ```

2. Virtuelle Umgebung erstellen:
   ```
   python -m venv venv
   venv\Scripts\activate  # Windows
   source venv/bin/activate  # Linux/Mac
   ```

3. Abhängigkeiten installieren:
   ```
   pip install -r requirements.txt
   ```

4. Starten:
   ```
   python main.py
   ```

## Build (Windows EXE)

`build-exe.bat` ausführen — erzeugt eine standalone EXE mit PyInstaller.
Die Icons aus dem `icons/`-Ordner werden automatisch neben die EXE kopiert.

## Lizenz

MIT License — siehe [LICENSE](LICENSE).

---

**Haftungsausschluss (Disclaimer)**

Dieses Projekt wird als Open-Source-Software ohne jegliche Garantie bereitgestellt — weder ausdrücklich noch stillschweigend, einschließlich (aber nicht beschränkt auf) der stillschweigenden Garantie der Marktgängigkeit oder der Eignung für einen bestimmten Zweck.

Die Software wurde nicht für den Einsatz in sicherheitskritischen, regulatorisch relevanten oder qualitätssicherungspflichtigen Prozessen geprüft oder zertifiziert. Der Nutzer trägt die alleinige Verantwortung für die Prüfung der erzeugten PDF-Dokumente auf Korrektheit und Vollständigkeit sowie für die Einhaltung geltender Vorschriften (z. B. ISO 9001, FDA 21 CFR Part 11, DSGVO und andere).

Durch die Nutzung der Software erklärt sich der Nutzer damit einverstanden, dass der Autor und etwaige Mitwirkende nicht für direkte, indirekte, zufällige oder Folgeschäden haftbar gemacht werden können, die aus der Nutzung oder der Unfähigkeit zur Nutzung der Software entstehen.
