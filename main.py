"""
PDF-Formular Füller & Template-Editor
v1.7 - Korrigierte Positionierung, Editor-Rahmen, Button
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import json, os, sys, tempfile
from PIL import Image, ImageTk, ImageDraw, ImageFont
import pypdfium2 as pdfium
from collections import Counter

APP_VERSION = "1.8.0"

C = {
    "bg": "#f0f0f0", "accent": "#4a90d9", "canvas": "#f8f8fc",
    "status": "#d0d0d0", "text": "#1e1e2e", "dim": "#555555",
    "green": "#2ecc71", "red": "#e74c3c", "yellow": "#f1c40f", "cyan": "#00bcd4",
}
SCHEMA_HELL = {"bg": "#f0f0f0", "accent": "#4a90d9", "canvas": "#f8f8fc", "status": "#d0d0d0", "text": "#1e1e2e", "dim": "#555555"}
SCHEMA_DUNKEL = {"bg": "#1e1e2e", "accent": "#89b4fa", "canvas": "#313244", "status": "#585b70", "text": "#cdd6f4", "dim": "#cdd6f4"}
SCALE = 300 / 72

FONT_CHOICES = [
    ("Liberation Sans", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    ("Liberation Sans Bold", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    ("Liberation Serif", "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf"),
    ("Liberation Mono", "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf"),
    ("DejaVu Sans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ("Arial", "arial.ttf"),
    # Windows-Schriftarten
    ("Arial", "C:\\Windows\\Fonts\\arial.ttf"),
    ("Arial Bold", "C:\\Windows\\Fonts\\arialbd.ttf"),
    ("Calibri", "C:\\Windows\\Fonts\\calibri.ttf"),
    ("Calibri Bold", "C:\\Windows\\Fonts\\calibrib.ttf"),
    ("Times New Roman", "C:\\Windows\\Fonts\\times.ttf"),
    ("Times New Roman Bold", "C:\\Windows\\Fonts\\timesbd.ttf"),
    ("Segoe UI", "C:\\Windows\\Fonts\\segoeui.ttf"),
    ("Segoe UI Bold", "C:\\Windows\\Fonts\\segoeuib.ttf"),
    ("Consolas", "C:\\Windows\\Fonts\\consola.ttf"),
]

def get_font_path(name):
    for n, p in FONT_CHOICES:
        if n == name and os.path.exists(p):
            return p
    # Fallback: Direkt-Pfad
    for n, p in FONT_CHOICES:
        if os.path.exists(p):
            return p
    return None

def get_font(size_pt, name=None):
    px = max(6, int(size_pt * SCALE))
    if name:
        for n, p in FONT_CHOICES:
            if n == name and os.path.exists(p):
                try: return ImageFont.truetype(p, px)
                except: pass
    # Fallback-Kette
    for _, p in FONT_CHOICES:
        if os.path.exists(p):
            try: return ImageFont.truetype(p, px)
            except: pass
    # Letzter Fallback: System-unabhaengigen TTF suchen
    import platform
    if platform.system() == "Windows":
        win_fonts = [
            r"C:\Windows\Fonts\arial.ttf",
            r"C:\Windows\Fonts\segoeui.ttf",
            r"C:\Windows\Fonts\calibri.ttf",
            r"C:\Windows\Fonts\consola.ttf",
        ]
        for fp in win_fonts:
            if os.path.exists(fp):
                try: return ImageFont.truetype(fp, px)
                except: pass
    return ImageFont.load_default()

def detect_font_size(pdf_path):
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            page = pdf.pages[0]
            chars = page.chars
            if not chars: return 11
            sizes = [round(c.get('size', 11), 1) for c in chars if c.get('text','').strip()]
            if not sizes: return 11
            return Counter(sizes).most_common(1)[0][0]
    except: return 11


class FieldRect:
    def __init__(self, x1=0, y1=0, x2=0, y2=0, label="", ftype="text"):
        self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2
        self.label, self.type, self.value, self.group = label, ftype, "", ""
        self.font_size = 11  # Schriftgröße in Punkt — pro Feld speicherbar
    @property
    def w(self): return self.x2 - self.x1
    @property
    def h(self): return self.y2 - self.y1
    def contains(self, px, py): return self.x1 <= px <= self.x2 and self.y1 <= py <= self.y2
    def to_dict(self):
        return {"label": self.label, "type": self.type, "x": self.x1,
                "y": self.y1, "w": self.w, "h": self.h, "group": self.group,
                "font_size": self.font_size}
    @classmethod
    def from_dict(cls, d):
        pos = d.get("pos", d)
        x = pos.get("x", pos.get("x1", 0))
        y = pos.get("y", pos.get("y1", 0))
        w = pos.get("w", 100)
        h = pos.get("h", d.get("h", 20))
        obj = cls(x1=x, y1=y, x2=x+w, y2=y+h,
                   label=d.get("label", d.get("name", "")), ftype="text" if d.get("type") == "radio" else d.get("type", "text"))
        obj.font_size = d.get("font_size", 11)
        return obj


class Stamp:
    """Ein Stempel auf dem PDF (GEPRÜFT, GENEHMIGT, etc.)."""
    STANDARD_STEMPEL = [
        ("GEPRÜFT", "#2ecc71", "grün"),
        ("GENEHMIGT", "#2196F3", "blau"),
        ("FREIGEGEBEN", "#4CAF50", "grün"),
        ("ABGELEHNT", "#e74c3c", "rot"),
        ("GESPERRT", "#ff9800", "orange"),
        ("NICHT GEPRÜFT", "#9e9e9e", "grau"),
        ("GELESEN UND GELACHT", "#e91e63", "pink"),
    ]

    def __init__(self, x=0, y=0, text="GEPRÜFT", color="#e67e22", rotation=15):
        self.x, self.y = x, y
        self.text = text
        self.color = color
        self.rotation = rotation  # Grad
        self.w, self.h = 140, 50  # Standardgröße

    def contains(self, px, py):
        # Vereinfachte Prüfung (ohne Rotation)
        return self.x <= px <= self.x + self.w and self.y <= py <= self.y + self.h

    def to_dict(self):
        return {"x": self.x, "y": self.y, "text": self.text,
                "color": self.color, "rotation": self.rotation}


class Arrow:
    """Ein Pfeil auf dem PDF von (x1,y1) nach (x2,y2)."""
    def __init__(self, x1=0, y1=0, x2=0, y2=0, color="#4a90d9", width=10, head_len=60):
        self.x1, self.y1 = x1, y1
        self.x2, self.y2 = x2, y2
        self.color = color
        self.width = width
        self.head_len = head_len

    def to_dict(self):
        return {"x1": self.x1, "y1": self.y1,
                "x2": self.x2, "y2": self.y2,
                "color": self.color, "width": self.width,
                "head_len": self.head_len}


class Rect:
    """Ein Rechteck auf dem PDF."""
    def __init__(self, x1=0, y1=0, x2=0, y2=0, color="#f5a623", fill=None, width=10):
        self.x1, self.y1 = min(x1, x2), min(y1, y2)
        self.x2, self.y2 = max(x1, x2), max(y1, y2)
        self.color = color
        self.fill = fill
        self.width = width

    def to_dict(self):
        return {"x1": self.x1, "y1": self.y1,
                "x2": self.x2, "y2": self.y2,
                "color": self.color, "fill": self.fill,
                "width": self.width}


class Mask:
    """Eine Maske auf dem PDF — deckt Inhalte ab (standardmäßig weiß gefüllt)."""
    def __init__(self, x1=0, y1=0, x2=0, y2=0, color="#e74c3c", fill="#ffffff", width=10):
        self.x1, self.y1 = min(x1, x2), min(y1, y2)
        self.x2, self.y2 = max(x1, x2), max(y1, y2)
        self.color = color
        self.fill = fill
        self.width = width

    def to_dict(self):
        return {"x1": self.x1, "y1": self.y1,
                "x2": self.x2, "y2": self.y2,
                "color": self.color, "fill": self.fill,
                "width": self.width}

    def contains(self, px, py):
        return self.x1 <= px <= self.x2 and self.y1 <= py <= self.y2


class Line:
    """Eine Linie auf dem PDF von (x1,y1) nach (x2,y2)."""
    def __init__(self, x1=0, y1=0, x2=0, y2=0, color="#50c878", width=10):
        self.x1, self.y1 = x1, y1
        self.x2, self.y2 = x2, y2
        self.color = color
        self.width = width

    def to_dict(self):
        return {"x1": self.x1, "y1": self.y1,
                "x2": self.x2, "y2": self.y2,
                "color": self.color, "width": self.width}


class Ellipse:
    """Eine Ellipse auf dem PDF."""
    def __init__(self, x1=0, y1=0, x2=0, y2=0, color="#9b59b6", fill=None, width=10):
        self.x1, self.y1 = min(x1, x2), min(y1, y2)
        self.x2, self.y2 = max(x1, x2), max(y1, y2)
        self.color = color
        self.fill = fill
        self.width = width

    def to_dict(self):
        return {"x1": self.x1, "y1": self.y1,
                "x2": self.x2, "y2": self.y2,
                "color": self.color, "fill": self.fill,
                "width": self.width}

    def contains(self, px, py):
        """Prüft ob Punkt (px,py) innerhalb der Ellipse liegt (vereinfacht als Bounding-Box)."""
        return self.x1 <= px <= self.x2 and self.y1 <= py <= self.y2


class Highlighter:
    """Ein Textmarker/Marker auf dem PDF — halbtransparente farbige Fläche."""
    def __init__(self, x1=0, y1=0, x2=0, y2=0, color="#ffff00", opacity=0.3, width=10):
        self.x1, self.y1 = min(x1, x2), min(y1, y2)
        self.x2, self.y2 = max(x1, x2), max(y1, y2)
        self.color = color
        self.opacity = opacity  # 0.0 - 1.0 (Transparenz)
        self.width = width

    def to_dict(self):
        return {"x1": self.x1, "y1": self.y1,
                "x2": self.x2, "y2": self.y2,
                "color": self.color, "opacity": self.opacity,
                "width": self.width}

    def contains(self, px, py):
        return self.x1 <= px <= self.x2 and self.y1 <= py <= self.y2


class App:
    def __init__(self, root):
        self.root = root
        self.root.title(f"PDF-Formular Füller v{APP_VERSION}")
        try:
            sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            x, y = max(0, (sw - 1200) // 2), max(0, (sh - 850) // 2)
            self.root.geometry(f"1200x850+{x}+{y}")
        except: self.root.geometry("1200x850")
        self.root.minsize(900, 600)

        self.pdf_image = self.pdf_tk = None
        self.zoom = 0.35
        self.ox = self.oy = 0
        self.pdf_path = None
        self.page_count = 0
        self.current_page = 0
        self.fields = {}  # dict: {"0": [FieldRect, ...], "1": [...]}
        self.stamps = {}  # dict: {"0": [Stamp, ...], "1": [...]}
        self.arrows = {}  # dict: {"0": [Arrow, ...], "1": [...]}
        self.rects = {}   # dict: {"0": [Rect, ...], "1": [...]}
        self.lines = {}   # dict: {"0": [Line, ...], "1": [...]}
        self.ellipses = {}   # dict: {"0": [Ellipse, ...], "1": [...]}
        self.masks = {}   # dict: {"0": [Mask, ...], "1": [...]}
        self.highlighters = {}  # dict: {"0": [Highlighter, ...], "1": [...]}

        # --- Undo-History ---
        self.undo_stack = {}  # {page_key: [snapshots]}
        self.undo_max = 50     # Tiefe des Undo-Stacks
        self._undo_snapshot()  # initialen Zustand sichern

        self.selected = None
        self.template_path = self.template_name = None
        self.project_path = self.project_name = None

        self.font_size = 11
        self.line_height = int(self.font_size * SCALE)
        self.frame_height = 80  # Rahmenhöhe in Pixeln, Voreinstellung 80
        self.export_font = get_font(self.font_size)
        self.font_color = "#000000"  # Schwarz, als String
        self.font_name = "Liberation Sans"

        self.dragging = False
        self.dx = self.dy = 0
        self.drag_field = None
        self.panning = False
        self.pan_x = self.pan_y = 0
        self.pan_ox = 0  # zusätzlicher Offset durch Panning
        self.pan_oy = 0
        self.active_field = None
        self.typing = False
        self.show_frames = True  # Rahmen ein/aus
        self.show_ruler = True  # Lineal ein/aus
        self.ruler_step = 50  # Pixelabstand Lineal-Striche
        self.grid_size = 15  # Einrast-Raster, jetzt einstellbar
        self.selected_tool = None  # Werkzeug aus Toolbox
        # Werkzeug-Voreinstellungen (per Rechtsklick änderbar)
        self.tool_line_color = "#50c878"
        self.tool_line_width = 10
        self.tool_arrow_color = "#4a90d9"
        self.tool_arrow_width = 10
        self.tool_arrow_head_len = 60
        self.tool_rect_color = "#f5a623"
        self.tool_rect_width = 10
        self.tool_ellipse_color = "#9b59b6"
        self.tool_ellipse_width = 10
        self.tool_mask_color = "#e74c3c"
        self.tool_mask_width = 10
        self.tool_mask_fill = "#ffffff"
        self.tool_highlighter_color = "#ffff00"  # Gelb wie Textmarker
        self.tool_highlighter_opacity = 0.3
        self._stempel_images = {}  # PIL-Images für PDF-Export
        self._stempel_tk = {}  # tkinter-PhotoImages für Canvas

        self._build()
        self._set_mode("fill")

    def _btn(self, p, t, c, bg, s=tk.LEFT, fg="#11111b", w=0, tip=""):
        b = tk.Button(p, text=t, font=("Segoe UI",9,"bold"), bg=bg, fg=fg,
                     activebackground=C["accent"], activeforeground="#11111b",
                     relief=tk.RAISED, bd=2, pady=4, padx=6, width=w, cursor="hand2", command=c)
        b.pack(side=s, padx=1); self._tb_children.append(b)
        if tip:
            self._attach_tooltip(b, tip)
        return b

    def _attach_tooltip(self, widget, text):
        """Hängt einen Hover-Tooltip an ein Widget."""
        tip_win = None
        def enter(e):
            nonlocal tip_win
            if tip_win: return
            x = widget.winfo_rootx() + 10
            y = widget.winfo_rooty() + widget.winfo_height() + 4
            tip_win = tk.Toplevel(widget)
            tip_win.wm_overrideredirect(True)
            tip_win.wm_geometry(f"+{x}+{y}")
            tip_win.configure(bg=C["status"])
            lbl = tk.Label(tip_win, text=text, bg=C["status"], fg=C["text"],
                          font=("Segoe UI",8), padx=8, pady=3, justify=tk.LEFT)
            lbl.pack()
        def leave(e):
            nonlocal tip_win
            if tip_win:
                tip_win.destroy()
                tip_win = None
        widget.bind("<Enter>", enter, add="+")
        widget.bind("<Leave>", leave, add="+")

    def _add_sep(self):
        s = tk.Frame(self._tb, bg=C["status"], width=2)
        s.pack(side=tk.LEFT, padx=3, fill=tk.Y, pady=3)
        self._tb_children.append(s)

    def _build_menus(self):
        """Baut die Menüleiste neu (für Farbschema-Wechsel)."""
        mb = tk.Menu(self.root, bg=C["bg"], fg=C["text"],
                     activebackground=C["accent"], activeforeground="#11111b")
        self.root.config(menu=mb)
        fm = tk.Menu(mb, tearoff=0, bg=C["bg"], fg=C["text"],
                     activebackground=C["accent"], activeforeground="#11111b")
        mb.add_cascade(label="Datei", menu=fm)
        fm.add_command(label="📂 PDF öffnen", command=self._open_pdf)
        fm.add_command(label="📋 Vorlage laden", command=self._load_template)
        fm.add_command(label="🗂️ Projekt öffnen", command=self._load_project)
        fm.add_separator()
        fm.add_command(label="💾 PDF speichern", command=self._save_pdf)
        fm.add_command(label="💾 Vorlage speichern", command=self._save_template)
        fm.add_command(label="💾 Projekt speichern", command=self._save_project)
        fm.add_separator()
        fm.add_command(label="🖨️ Drucken", command=self._print_pdf)
        fm.add_separator()
        fm.add_command(label="❌ Schließen", command=self._close_all)
        fm.add_command(label="Beenden", command=self.root.quit)
        sm = tk.Menu(mb, tearoff=0, bg=C["bg"], fg=C["text"],
                     activebackground=C["accent"], activeforeground="#11111b")
        mb.add_cascade(label="Einstellungen", menu=sm)
        sm.add_command(label="🖊️ Schrift...", command=self._font_dialog)
        sm.add_command(label="🎨 Farbschema...", command=self._color_dialog)
        sm.add_command(label="⚙️ Allgemein...", command=self._general_dialog)

    def _build(self):
        self.root.configure(bg=C["bg"])
        self._build_menus()

        self._tb = tk.Frame(self.root, bg=C["bg"], height=38)
        self._tb.pack(fill=tk.X, padx=3, pady=(3,0))
        self._tb_children = []  # für apply_ui

        # --- 📂 ÖFFNEN (Dropdown) ---
        self.btn_open = tk.Button(self._tb, text="📂 ÖFFNEN", font=("Segoe UI",9,"bold"),
                                 bg=C["accent"], fg="#11111b", activebackground=C["accent"],
                                 activeforeground="#11111b", relief=tk.RAISED, bd=2,
                                 pady=4, padx=10, cursor="hand2",
                                 command=self._show_open_menu)
        self.btn_open.pack(side=tk.LEFT, padx=1)

        # --- 💾 SPEICHERN (Dropdown) ---
        self.btn_save = tk.Button(self._tb, text="💾 SPEICHERN", font=("Segoe UI",9,"bold"),
                                 bg=C["green"], fg="#11111b", activebackground=C["green"],
                                 activeforeground="#11111b", relief=tk.RAISED, bd=2,
                                 pady=4, padx=10, cursor="hand2",
                                 command=self._show_save_menu)
        self.btn_save.pack(side=tk.LEFT, padx=1)
        self._add_sep()

        # --- Modus ---
        self.btn_fill = self._btn(self._tb, "Ausfüllen", lambda: self._set_mode("fill"), C["green"])
        self.btn_edit = self._btn(self._tb, "Editor", lambda: self._set_mode("edit"), C["status"])
        self._add_sep()

        # --- Rahmen/Höhe/Raster/Lineal ---
        self.btn_frame = self._btn(self._tb, "Rahmen", self._toggle_frames, C["yellow"])
        self.btn_ruler = self._btn(self._tb, "Lineal", self._toggle_ruler, C["yellow"])
        self._btn(self._tb, "Höhe", self._set_height_dialog, C["yellow"])
        self._btn(self._tb, "Raster", self._set_grid_dialog, C["yellow"])
        self._btn(self._tb, "Schrift", self._font_dialog, C["cyan"])
        self._add_sep()

        # --- Drucken / Zoom ---
        self._btn(self._tb, "Drucken", self._print_pdf, C["yellow"])
        self._btn(self._tb, "−", lambda: self._do_zoom(0.8), C["status"], fg="#11111b")
        self._btn(self._tb, "+", lambda: self._do_zoom(1.25), C["status"], fg="#11111b")
        self._btn(self._tb, "1:1", self._zoom_reset, C["status"], fg="#11111b")
        self._add_sep()

        # --- Reset ---
        self._btn(self._tb, "Zurücksetzen", self._reset, C["red"])

        # --- Seiten-Navigation (rechtsbündig) ---
        self.page_label = tk.Label(self._tb, text="Seite ? / ?", font=("Segoe UI",9,"bold"),
                                   bg=C["bg"], fg=C["text"])
        self.page_label.pack(side=tk.RIGHT, padx=6)
        self.btn_next = self._btn(self._tb, "➡", self._next_page, C["accent"], fg="#11111b")
        self.btn_prev = self._btn(self._tb, "⬅", self._prev_page, C["accent"], fg="#11111b")

        # ─── Tooltips für alle Toolbar-Buttons ─────────────────
        TOOLTIPS = {
            "📂 ÖFFNEN": "PDF, Vorlage oder Projekt öffnen",
            "💾 SPEICHERN": "PDF, Vorlage oder Projekt speichern",
            "Ausfüllen": "Modus: Felder ausfüllen (Klick auf Textfeld)",
            "Editor": "Modus: Felder anlegen, verschieben, löschen",
            "Rahmen": "Feld-Rahmen ein-/ausblenden",
            "Lineal": "Lineal ein-/ausblenden",
            "Höhe": "Rahmenhöhe für neue Felder ändern",
            "Raster": "Einrast-Raster-Größe ändern",
            "Schrift": "Schriftart, -größe und -farbe einstellen",
            "Drucken": "PDF in externem Betrachter öffnen (drucken)",
            "−": "Verkleinern (Rauszoomen)",
            "+": "Vergrößern (Reinzoomen)",
            "1:1": "Zoom zurücksetzen (100 %)",
            "Zurücksetzen": "Alle ausgefüllten Werte löschen",
            "⬅": "Vorherige Seite",
            "➡": "Nächste Seite",
        }
        for child in self._tb_children:
            if isinstance(child, tk.Button) and child.cget("text") in TOOLTIPS:
                self._attach_tooltip(child, TOOLTIPS[child.cget("text")])
        # ─── Icons aus icons/-Ordner laden ────────────────────
        def _icon_path(name):
            """Sucht icons/<name>.png im Projekt- oder EXE-Verzeichnis."""
            icon_name = f"{name}.png"
            # 1) PyInstaller: eingebettete Dateien (--add-data)
            if hasattr(sys, '_MEIPASS'):
                p = os.path.join(sys._MEIPASS, "icons", icon_name)
                if os.path.exists(p):
                    return p
            # 2) Neben der EXE (sys.argv[0] -> dist/PDF-Formular.exe)
            base = os.path.dirname(os.path.abspath(sys.argv[0]))
            p = os.path.join(base, "icons", icon_name)
            if os.path.exists(p):
                return p
            # 3) Arbeitsverzeichnis (wenn build-exe von Projektroot aus)
            p = os.path.join(os.path.abspath(os.curdir), "icons", icon_name)
            if os.path.exists(p):
                return p
            # 4) Skript-Verzeichnis (python main.py)
            p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons", icon_name)
            if os.path.exists(p):
                return p
            return None

        self._icons_png = {}
        for iname in ("pfeil", "linie", "rechteck", "ellipse", "maske", "stempel", "marker", "foto", "datum"):
            path = _icon_path(iname)
            if path:
                self._icons_png[iname] = tk.PhotoImage(file=path)
            else:
                print(f"Icon fehlt: {iname}.png in icons/")

        # ─── Toolbox links ─────────────────────────────────────
        self.toolbox = tk.Frame(self.root, bg=C["bg"], width=48)
        self.toolbox.pack(side=tk.LEFT, fill=tk.Y, padx=(4,0), pady=4)
        self.toolbox.pack_propagate(False)

        self.toolbox_inner = tk.Frame(self.toolbox, bg=C["bg"])
        self.toolbox_inner.pack(fill=tk.X)

        werkzeuge = [
            ("pfeil", "Pfeil", "Auswahl (Default)"),
            ("linie", "Linie", "Linie zeichnen"),
            ("rechteck", "Rechteck", "Rechteck zeichnen"),
            ("ellipse", "Ellipse", "Kreis/Ellipse zeichnen"),
            ("maske", "Maske", "Bereich maskieren"),
            ("stempel", "Stempel", "Stempel aufdrücken"),
            ("marker", "Textmarker", "Textmarker (halbtransparente Fläche)"),
            ("foto", "Bild einfügen", "Foto/Bild als neue Seite einfügen"),
        ]

        self._tool_buttons = {}
        for ikey, name, tip in werkzeuge:
            img = self._icons_png.get(ikey)
            txt = {"Textmarker": "🖍️", "Bild einfügen": "🖼️"}.get(name, "")
            if img:
                btn = tk.Button(self.toolbox_inner, image=img,
                              bg=C["bg"],
                              activebackground="#89b4fa",
                              relief=tk.RAISED, bd=2, pady=4, padx=2,
                              cursor="hand2",
                              command=lambda n=name: self._set_tool(n))
            else:
                btn = tk.Button(self.toolbox_inner, text=txt or name[0],
                              bg=C["bg"],
                              activebackground="#89b4fa",
                              relief=tk.RAISED, bd=2, pady=4, padx=2,
                              cursor="hand2", font=("Segoe UI", 12),
                              command=lambda n=name: self._set_tool(n))
            btn.pack(pady=(0,2), fill=tk.X, padx=2)
            self._tool_buttons[name] = btn
            self._attach_tooltip(btn, tip)
            # Hover per Event-Binding
            def on_enter(e, b=btn):
                if b.cget("bg") != C["accent"]: b.configure(bg="#89b4fa")
            def on_leave(e, b=btn):
                if b.cget("bg") != C["accent"]: b.configure(bg=C["bg"])
            btn.bind("<Enter>", on_enter)
            btn.bind("<Leave>", on_leave)
            if name in ("Linie", "Pfeil", "Rechteck", "Ellipse", "Maske", "Textmarker"):
                btn.bind("<Button-3>", lambda e, n=name: self._tool_settings_dialog(n))

        img_datum = self._icons_png.get("datum")
        self.btn_date = tk.Button(self.toolbox_inner, image=img_datum if img_datum else "",
                                bg=C["bg"],
                                activebackground="#89b4fa",
                                relief=tk.RAISED, bd=2, pady=4, padx=2,
                                cursor="hand2",
                                command=self._insert_date)
        self.btn_date.pack(pady=(8,2), fill=tk.X, padx=2)
        self._attach_tooltip(self.btn_date, "Aktuelles Datum einfügen (TT.MM.JJJJ)")
        def dt_enter(e):
            if self.btn_date.cget("bg") != C["accent"]: self.btn_date.configure(bg="#89b4fa")
        def dt_leave(e):
            if self.btn_date.cget("bg") != C["accent"]: self.btn_date.configure(bg=C["bg"])
        self.btn_date.bind("<Enter>", dt_enter)
        self.btn_date.bind("<Leave>", dt_leave)

        self.toolbox_filler = tk.Frame(self.toolbox_inner, bg=C["bg"])
        self.toolbox_filler.pack(fill=tk.BOTH, expand=True)

        self.btn_exit = tk.Button(self.toolbox, text="❌", font=("Segoe UI",14),
                                bg=C["red"], fg="#11111b",
                                activebackground="#c0392b", activeforeground="#11111b",
                                relief=tk.RAISED, bd=2, pady=6, padx=0,
                                cursor="hand2",
                                command=self._exit_app)
        self.btn_exit.pack(side=tk.BOTTOM, pady=(0,6), fill=tk.X, padx=2)
        self._attach_tooltip(self.btn_exit, "Beenden")

        # ─── Canvas-Bereich ────────────────────────────────────
        self.mf = tk.Frame(self.root, bg=C["canvas"])
        self.mf.pack(fill=tk.BOTH, expand=True, padx=(0,4), pady=4)
        self.cv = tk.Canvas(self.mf, bg=C["canvas"], cursor="arrow",
                           highlightthickness=0, bd=0)
        self.cv.pack(fill=tk.BOTH, expand=True)

        self.sb = tk.Label(self.root, text="", bg=C["status"], fg=C["text"],
                          anchor=tk.W, font=("Segoe UI",9))
        self.sb.pack(side=tk.BOTTOM, fill=tk.X)
        self.sb_mouse = tk.Label(self.root, text="", bg=C["status"], fg=C["dim"],
                                anchor=tk.E, font=("Segoe UI",8))
        self.sb_mouse.pack(side=tk.BOTTOM, fill=tk.X)

        self.cv.bind("<Configure>", lambda e: self._render())
        self.cv.bind("<MouseWheel>", self._mw)
        self.cv.bind("<Button-4>", lambda e: self._do_zoom(1.1))
        self.cv.bind("<Button-5>", lambda e: self._do_zoom(0.9))
        self.cv.bind("<Button-1>", self._click)
        self.cv.bind("<Control-Button-1>", self._ctrlclick)
        self.cv.bind("<B1-Motion>", self._b1_motion)
        self.cv.bind("<ButtonRelease-1>", self._release_b1)
        self.cv.bind("<Button-2>", self._middle_click)
        self.cv.bind("<B2-Motion>", self._middle_drag)
        self.cv.bind("<ButtonRelease-2>", self._middle_release)
        self.cv.bind("<Button-3>", self._right)
        self.cv.bind("<B3-Motion>", self._right_drag)
        self.cv.bind("<ButtonRelease-3>", self._right_release)
        self.cv.bind("<Key>", self._key)
        self.root.bind("<Escape>", self._key_escape)
        self.root.bind("<Control-z>", self._undo)
        self.root.bind("<Control-Z>", self._undo)
        # Popup-Menüs bei Klick irgendwo schließen
        self.root.bind("<Button-1>", self._close_menus, add="+")
        self.root.bind("<Button-3>", self._close_menus, add="+")

    def _set_tool(self, name):
        """Wählt ein Werkzeug aus der Toolbox."""
        self.selected_tool = name
        # Buttons visuell hervorheben — 3D, aktiv = accent hinterlegt
        for n, btn in self._tool_buttons.items():
            if n == name:
                btn.configure(bg=C["accent"], fg="#11111b", relief=tk.RAISED)
            else:
                btn.configure(bg=C["bg"], fg=C["text"], relief=tk.RAISED)
        self._status()

    def _set_height_dialog(self):
        from tkinter import simpledialog
        val = simpledialog.askinteger("Rahmenhöhe",
            f"Aktuell: {self.frame_height} px\nNeue Höhe (10-500):",
            initialvalue=self.frame_height, minvalue=10, maxvalue=500,
            parent=self.root)
        if val is not None:
            self._undo_snapshot()
            self.frame_height = val
            for f in self._current_fields():
                f.y1 = f.y2 - self.frame_height
            self._render()
            self._status()

    def _set_grid_dialog(self):
        from tkinter import simpledialog
        val = simpledialog.askinteger("Raster-Größe",
            f"Aktuell: {self.grid_size} px\nNeues Raster (2-100 px):",
            initialvalue=self.grid_size, minvalue=2, maxvalue=100,
            parent=self.root)
        if val is not None:
            self.grid_size = val
            self._status()

    def _current_fields(self):
        """Gibt die Feld-Liste der aktuellen Seite zurück (oder leere Liste)."""
        return self.fields.get(str(self.current_page), [])

    def _goto_page(self, page):
        """Wechselt zu einer bestimmten Seite."""
        if not self.pdf_path or page < 0 or page >= self.page_count:
            return
        # Aktuelle Seite vor dem Wechsel sichern
        if self.pdf_image:
            self._undo_snapshot()
        if self.dragging:
            self._release_b1(None)
        self._stop_typing()
        self.current_page = page
        try:
            pdf = pdfium.PdfDocument(self.pdf_path)
            bm = pdf[page].render(scale=300/72)
            self.pdf_image = bm.to_pil(); pdf.close()
        except Exception as e:
            messagebox.showerror("Fehler", f"Seite {page+1}: {e}")
            return
        key = str(page)
        if key not in self.fields:
            self.fields[key] = []
        if key not in self.stamps:
            self.stamps[key] = []
        if key not in self.arrows:
            self.arrows[key] = []
        if key not in self.rects:
            self.rects[key] = []
        if key not in self.highlighters:
            self.highlighters[key] = []
        self.selected = None
        self._fit_zoom()
        self._render()
        self._status()

    def _prev_page(self):
        if self.current_page > 0:
            self._goto_page(self.current_page - 1)

    def _next_page(self):
        if self.current_page < self.page_count - 1:
            self._goto_page(self.current_page + 1)

    def _font_dialog(self):
        """Dialog für Schriftart, -größe und -farbe der Textfelder."""
        win = tk.Toplevel(self.root)
        win.title("Schrift-Einstellungen")
        win.configure(bg=C["bg"])
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)

        rx, ry = self.root.winfo_x(), self.root.winfo_y()
        rw, rh = self.root.winfo_width(), self.root.winfo_height()
        ww, wh = 340, 280
        win.geometry(f"{ww}x{wh}+{rx+rw//2-ww//2}+{ry+rh//2-wh//2}")

        # Schriftart
        tk.Label(win, text="Schriftart:", bg=C["bg"], fg=C["text"],
                font=("Segoe UI",10)).pack(pady=(12,2))
        font_var = tk.StringVar(value=self.font_name)
        font_cb = ttk.Combobox(win, textvariable=font_var,
                               values=[n for n, _ in FONT_CHOICES],
                               state="readonly", font=("Segoe UI",11))
        font_cb.pack(padx=20, fill=tk.X)

        # Schriftgröße
        tk.Label(win, text="Schriftgröße (Punkt):", bg=C["bg"], fg=C["text"],
                font=("Segoe UI",10)).pack(pady=(8,2))
        size_frame = tk.Frame(win, bg=C["bg"])
        size_frame.pack(padx=20, fill=tk.X)
        size_var = tk.IntVar(value=self.font_size)
        tk.Scale(size_frame, from_=6, to=36, orient=tk.HORIZONTAL,
                variable=size_var, bg=C["bg"], fg=C["text"],
                troughcolor=C["canvas"], highlightthickness=0,
                length=200, bd=0).pack(side=tk.LEFT)
        size_lbl = tk.Label(size_frame, textvariable=size_var, bg=C["bg"],
                           fg=C["accent"], font=("Segoe UI",12,"bold"), width=3)
        size_lbl.pack(side=tk.LEFT, padx=6)

        # Schriftfarbe
        tk.Label(win, text="Schriftfarbe:", bg=C["bg"], fg=C["text"],
                font=("Segoe UI",10)).pack(pady=(8,2))
        color_frame = tk.Frame(win, bg=C["bg"])
        color_frame.pack(padx=20, fill=tk.X)
        color_var = tk.StringVar(value=self.font_color)
        colors = ["#000000", "#333333", "#666666", "#990000", "#cc0000",
                  "#006600", "#000099", "#663300", "#800080", "#cc6600"]
        for c in colors:
            btn = tk.Button(color_frame, bg=c, width=2, bd=1, relief=tk.RAISED,
                          command=lambda cv=c: color_var.set(cv),
                          activebackground=c)
            btn.pack(side=tk.LEFT, padx=2, pady=2)
        color_et = tk.Entry(color_frame, textvariable=color_var, bg=C["canvas"],
                           fg=C["text"], font=("Segoe UI",10,"bold"),
                           relief=tk.FLAT, bd=2, width=10)
        color_et.pack(side=tk.RIGHT, padx=(0,0))

        def on_ok():
            self.font_name = font_var.get()
            self.font_size = size_var.get()
            self.font_color = color_var.get()
            self.line_height = max(10, int(self.font_size * SCALE))
            self.export_font = get_font(self.font_size, self.font_name)
            self._render()
            self._status()
            win.destroy()

        def on_cancel():
            win.destroy()

        btn_frame = tk.Frame(win, bg=C["bg"])
        btn_frame.pack(pady=(12,10))
        tk.Button(btn_frame, text="OK", command=on_ok,
                 bg=C["green"], fg="#11111b", font=("Segoe UI",10,"bold"),
                 bd=0, padx=20, pady=4, cursor="hand2").pack(side=tk.LEFT, padx=6)
        tk.Button(btn_frame, text="Abbrechen", command=on_cancel,
                 bg=C["red"], fg="#11111b", font=("Segoe UI",10,"bold"),
                 bd=0, padx=14, pady=4, cursor="hand2").pack(side=tk.LEFT, padx=6)

        win.bind("<Return>", lambda e: on_ok())
        win.bind("<Escape>", lambda e: on_cancel())

    def _close_all(self):
        """Schließt PDF, Vorlage, Projekt und setzt alles zurück."""
        self._stop_typing()
        self.pdf_path = None
        self.pdf_image = self.pdf_tk = None
        self.fields = {}
        self.stamps = {}
        self.arrows = {}
        self.rects = {}
        self.lines = {}
        self.ellipses = {}
        self.masks = {}
        self.highlighters = {}
        self._stempel_images = {}
        self._stempel_tk = {}
        self.current_page = 0
        self.page_count = 0
        self.selected = None
        self.template_path = self.template_name = None
        self.project_path = self.project_name = None
        self.undo_stack = {}
        self.cv.delete("all")
        self._status()

    def _color_dialog(self):
        """Dialog für Farben der App-Oberfläche mit Hell/Dunkel-Voreinstellungen."""
        win = tk.Toplevel(self.root)
        win.title("Farbschema")
        win.configure(bg=C["bg"])
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)

        rx, ry = self.root.winfo_x(), self.root.winfo_y()
        rw, rh = self.root.winfo_width(), self.root.winfo_height()
        ww, wh = 380, 380
        win.geometry(f"{ww}x{wh}+{rx+rw//2-ww//2}+{ry+rh//2-wh//2}")

        # --- Hell/Dunkel-Voreinstellungen ---
        theme_frame = tk.Frame(win, bg=C["bg"])
        theme_frame.pack(pady=(12,4), fill=tk.X)

        def set_hell():
            for k, v in SCHEMA_HELL.items():
                vars_[k].set(v)
                previews[k].configure(bg=v)

        def set_dunkel():
            for k, v in SCHEMA_DUNKEL.items():
                vars_[k].set(v)
                previews[k].configure(bg=v)

        tk.Button(theme_frame, text="🌙 Dunkel", font=("Segoe UI",9,"bold"),
                 bg=SCHEMA_DUNKEL["bg"], fg=SCHEMA_DUNKEL["accent"],
                 bd=1, padx=12, pady=2, cursor="hand2",
                 command=set_dunkel).pack(side=tk.LEFT, padx=3)
        tk.Button(theme_frame, text="☀️ Hell", font=("Segoe UI",9,"bold"),
                 bg=SCHEMA_HELL["bg"], fg=SCHEMA_HELL["accent"],
                 bd=1, padx=12, pady=2, cursor="hand2",
                 command=set_hell).pack(side=tk.LEFT, padx=3)

        # --- Farbfelder ---
        vars_ = {}
        previews = {}
        felder = [
            ("Hintergrund", "bg"),
            ("Canvas", "canvas"),
            ("Akzent", "accent"),
            ("Statusleiste", "status"),
            ("Textfarbe", "text"),
            ("Text (dim)", "dim"),
        ]
        inp_frame = tk.Frame(win, bg=C["bg"])
        inp_frame.pack(pady=(8,4))
        row = 0
        for label, key in felder:
            tk.Label(inp_frame, text=label, bg=C["bg"], fg=C["text"],
                    font=("Segoe UI",10), width=14, anchor=tk.W).grid(row=row, column=0, padx=6, pady=4)
            vars_[key] = tk.StringVar(value=C[key])
            def pick_color(k=key):
                import tkinter.colorchooser
                farbe = tkinter.colorchooser.askcolor(
                    title=f"Farbe für {label}", color=C[k], parent=win)
                if farbe and farbe[1]:
                    vars_[k].set(farbe[1])  # Hex-Wert
                    previews[k].configure(bg=farbe[1])
            previews[key] = tk.Label(inp_frame, bg=C[key], width=6, height=1,
                                    relief=tk.RAISED, bd=3, cursor="hand2")
            previews[key].grid(row=row, column=1, padx=4, pady=4, sticky=tk.W)
            previews[key].bind("<Button-1>", lambda e, k=key: pick_color(k))
            tk.Label(inp_frame, textvariable=vars_[key], bg=C["bg"], fg=C["dim"],
                    font=("Segoe UI",8), width=10, anchor=tk.W).grid(row=row, column=2, padx=2, pady=4, sticky=tk.W)
            row += 1

        def apply_ui():
            for key, var in vars_.items():
                C[key] = var.get().strip()
            self.root.configure(bg=C["bg"])
            self.mf.configure(bg=C["canvas"])
            self.cv.configure(bg=C["canvas"])
            self.sb.configure(bg=C["status"], fg=C["text"])
            if hasattr(self, 'sb_mouse'):
                self.sb_mouse.configure(bg=C["status"], fg=C["dim"])
            self._tb.configure(bg=C["bg"])
            # Toolbox einfärben
            if hasattr(self, 'toolbox'):
                self.toolbox.configure(bg=C["bg"])
                self.toolbox_filler.configure(bg=C["bg"])
                for n, btn in self._tool_buttons.items():
                    if n == self.selected_tool:
                        btn.configure(bg=C["accent"], fg="#11111b", relief=tk.RAISED)
                    else:
                        btn.configure(bg=C["bg"], fg=C["text"], relief=tk.RAISED)
            # Page-Label einfärben
            if hasattr(self, 'page_label'):
                self.page_label.configure(bg=C["bg"], fg=C["text"])
            # Toolbar-Trennstriche neu einfärben (Buttons bleiben unverändert)
            for w in self._tb_children:
                if isinstance(w, tk.Frame):
                    w.configure(bg=C["status"])
            # Menüleiste komplett neu
            self.root.config(menu=None)
            self._build_menus()
            self._render()
            self._status()

        def on_ok():
            apply_ui()
            win.destroy()

        def on_reset():
            set_dunkel()
            apply_ui()
            win.destroy()

        def on_cancel():
            win.destroy()

        btn_frame = tk.Frame(win, bg=C["bg"])
        btn_frame.pack(pady=(12,10))
        tk.Button(btn_frame, text="OK", command=on_ok,
                 bg=C["green"], fg="#11111b", font=("Segoe UI",10,"bold"),
                 bd=0, padx=20, pady=4, cursor="hand2").pack(side=tk.LEFT, padx=6)
        tk.Button(btn_frame, text="Zurücksetzen", command=on_reset,
                 bg=C["yellow"], fg="#11111b", font=("Segoe UI",10,"bold"),
                 bd=0, padx=14, pady=4, cursor="hand2").pack(side=tk.LEFT, padx=6)
        tk.Button(btn_frame, text="Abbrechen", command=on_cancel,
                 bg=C["red"], fg="#11111b", font=("Segoe UI",10,"bold"),
                 bd=0, padx=14, pady=4, cursor="hand2").pack(side=tk.LEFT, padx=6)

        win.bind("<Return>", lambda e: on_ok())
        win.bind("<Escape>", lambda e: on_cancel())

    def _general_dialog(self):
        """Allgemeine Einstellungen (Raster, Rahmenhöhe, Lineal)."""
        win = tk.Toplevel(self.root)
        win.title("Allgemeine Einstellungen")
        win.configure(bg=C["bg"])
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)

        rx, ry = self.root.winfo_x(), self.root.winfo_y()
        rw, rh = self.root.winfo_width(), self.root.winfo_height()
        ww, wh = 320, 200
        win.geometry(f"{ww}x{wh}+{rx+rw//2-ww//2}+{ry+rh//2-wh//2}")

        # Raster
        tk.Label(win, text="Raster (px):", bg=C["bg"], fg=C["text"],
                font=("Segoe UI",10)).pack(pady=(12,2))
        grid_var = tk.IntVar(value=self.grid_size)
        tk.Spinbox(win, from_=2, to=50, textvariable=grid_var, bg=C["canvas"],
                  fg=C["text"], buttonbackground=C["status"],
                  font=("Segoe UI",11), width=6).pack()

        # Rahmenhöhe
        tk.Label(win, text="Rahmenhöhe (px):", bg=C["bg"], fg=C["text"],
                font=("Segoe UI",10)).pack(pady=(8,2))
        height_var = tk.IntVar(value=self.frame_height)
        tk.Spinbox(win, from_=20, to=300, textvariable=height_var, bg=C["canvas"],
                  fg=C["text"], buttonbackground=C["status"],
                  font=("Segoe UI",11), width=6).pack()

        def on_ok():
            self.grid_size = grid_var.get()
            old_h = self.frame_height
            self.frame_height = height_var.get()
            for f in self._current_fields():
                f.y1 = f.y2 - self.frame_height
            self._render()
            self._status()
            win.destroy()

        def on_reset():
            grid_var.set(15)
            height_var.set(80)

        def on_cancel():
            win.destroy()

        btn_frame = tk.Frame(win, bg=C["bg"])
        btn_frame.pack(pady=(16,10))
        tk.Button(btn_frame, text="OK", command=on_ok,
                 bg=C["green"], fg="#11111b", font=("Segoe UI",10,"bold"),
                 bd=0, padx=20, pady=4, cursor="hand2").pack(side=tk.LEFT, padx=6)
        tk.Button(btn_frame, text="Zurücksetzen", command=on_reset,
                 bg=C["yellow"], fg="#11111b", font=("Segoe UI",10,"bold"),
                 bd=0, padx=14, pady=4, cursor="hand2").pack(side=tk.LEFT, padx=6)
        tk.Button(btn_frame, text="Abbrechen", command=on_cancel,
                 bg=C["red"], fg="#11111b", font=("Segoe UI",10,"bold"),
                 bd=0, padx=14, pady=4, cursor="hand2").pack(side=tk.LEFT, padx=6)

        win.bind("<Return>", lambda e: on_ok())
        win.bind("<Escape>", lambda e: on_cancel())

    def _toggle_frames(self):
        self.show_frames = not self.show_frames
        self.btn_frame.configure(bg=C["green"] if self.show_frames else C["status"])
        self._render()
        self._status()

    def _toggle_ruler(self):
        self.show_ruler = not self.show_ruler
        self.btn_ruler.configure(bg=C["green"] if self.show_ruler else C["status"])
        self._render()
        self._status()

    def _undo_snapshot(self):
        """Aktuellen Zustand für Undo sichern."""
        if not self.pdf_image:
            return
        key = str(self.current_page)
        snap = {
            "fields": [f.to_dict() for f in self._current_fields()],
            "stamps": [s.to_dict() for s in self._current_stamps()],
            "arrows": [a.to_dict() for a in self._current_arrows()],
            "rects": [r.to_dict() for r in self._current_rects()],
            "lines": [ln.to_dict() for ln in self._current_lines()],
            "ellipses": [el.to_dict() for el in self._current_ellipses()],
            "masks": [m.to_dict() for m in self._current_masks()],
            "highlighters": [h.to_dict() for h in self._current_highlighters()],
        }
        if key not in self.undo_stack:
            self.undo_stack[key] = []
        self.undo_stack[key].append(snap)
        if len(self.undo_stack[key]) > self.undo_max:
            self.undo_stack[key].pop(0)

    def _undo(self, event=None):
        """Strg+Z: letzten Zustand wiederherstellen."""
        key = str(self.current_page)
        stack = self.undo_stack.get(key, [])
        if len(stack) < 2:
            self._status_text("Nichts rückgängig zu machen")
            return
        stack.pop()
        snap = stack[-1]
        current_fields = self._current_fields()
        current_fields.clear()
        for d in snap["fields"]:
            current_fields.append(FieldRect.from_dict(d))
        key_st = str(self.current_page)
        self.stamps[key_st] = [Stamp(**s) for s in snap["stamps"]]
        self.arrows[key_st] = [Arrow(**a) for a in snap["arrows"]]
        self.rects[key_st] = [Rect(**r) for r in snap["rects"]]
        self.lines[key_st] = [Line(**l) for l in snap["lines"]]
        self.ellipses[key_st] = [Ellipse(**e) for e in snap["ellipses"]]
        self.masks[key_st] = [Mask(**m) for m in snap["masks"]]
        self.highlighters[key_st] = [Highlighter(**h) for h in snap.get("highlighters", [])]
        self._render()
        self._status()

    def _key_escape(self, event=None):
        """Escape: Werkzeug-Modus zurücksetzen + Tippen beenden."""
        self._stop_typing()
        if self.selected_tool:
            self.selected_tool = None
            for n, btn in self._tool_buttons.items():
                btn.configure(bg=C["bg"], fg=C["text"], relief=tk.RAISED)
            self._status()

    def _set_mode(self, mode):
        self._stop_typing()
        self.mode = mode
        # Werkzeug-Modus beim Modus-Wechsel zurücksetzen
        self.selected_tool = None
        for n, btn in self._tool_buttons.items():
            btn.configure(bg=C["bg"], fg=C["text"], relief=tk.RAISED)
        if mode == "fill":
            self.btn_fill.configure(bg=C["accent"], fg="#11111b")
            self.btn_edit.configure(bg=C["status"], fg=C["dim"])
            self.cv.configure(cursor="hand2")
        else:
            self.btn_fill.configure(bg=C["status"], fg=C["dim"])
            self.btn_edit.configure(bg=C["accent"], fg="#11111b")
            self.cv.configure(cursor="crosshair")
        self._render()
        self._status()

    # ─── PDF ─────────────────────────────────────────────────
    def _open_pdf(self):
        p = filedialog.askopenfilename(title="PDF öffnen", filetypes=[("PDF","*.pdf"),("*","*.*")])
        if p: self._load_pdf(p)

    def _load_pdf(self, path):
        if not os.path.exists(path): return
        self.pdf_path = path
        self.font_size = detect_font_size(path)
        self.line_height = max(10, int(self.font_size * SCALE))
        self.export_font = get_font(self.font_size, self.font_name)
        try:
            pdf = pdfium.PdfDocument(path)
            self.page_count = len(pdf)
            self.current_page = 0
            bm = pdf[self.current_page].render(scale=300/72)
            self.pdf_image = bm.to_pil(); pdf.close()
            # Felder für diese Seite initialisieren falls nicht vorhanden
            key = str(self.current_page)
            if key not in self.fields:
                self.fields[key] = []
            if key not in self.stamps:
                self.stamps[key] = []
            if key not in self.arrows:
                self.arrows[key] = []
            if key not in self.rects:
                self.rects[key] = []
            self._fit_zoom(); self._render(); self._status()
        except Exception as e: messagebox.showerror("Fehler", f"PDF: {e}")

    # ─── Vorlage ──────────────────────────────────────────────
    def _load_template(self):
        p = filedialog.askopenfilename(title="Vorlage", filetypes=[("JSON","*.json"),("*","*.*")])
        if not p: return
        try:
            with open(p, encoding='utf-8') as f: data = json.load(f)
            # PDF automatisch laden, falls referenziert
            pdf = data.get("pdf", "")
            if pdf and os.path.exists(pdf):
                self._load_pdf(pdf)
            elif pdf:
                messagebox.showwarning("PDF fehlt", f"PDF nicht gefunden:\n{pdf}\nBitte manuell öffnen.")
            raw = data.get("fields", data.get("items", data if isinstance(data,list) else []))
            if isinstance(raw, dict):
                # Neue Struktur: fields pro Seite
                self.fields = {}
                for page_key, flist in raw.items():
                    self.fields[page_key] = [FieldRect.from_dict(item) for item in flist]
            else:
                # Alte Struktur: flache Liste → aktuelle Seite
                self.fields = {str(self.current_page): [FieldRect.from_dict(item) for item in raw]}
            self.selected = None
            self.template_path, self.template_name = p, data.get("name", os.path.basename(p))
            self._render(); self._status()
            total = sum(len(v) for v in self.fields.values())
            messagebox.showinfo("Geladen", f"'{self.template_name}', {total} Felder ({len(self.fields)} Seiten)")
        except Exception as e: messagebox.showerror("Fehler", f"Vorlage: {e}")

    def _save_template(self):
        cur = self._current_fields()
        if not cur: return messagebox.showwarning("Leer", "Keine Felder auf aktueller Seite.")
        name = simpledialog.askstring("Name", "Vorlagenname:", initialvalue=self.template_name or "Neu")
        if not name: return
        p = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON","*.json")],
                                         initialfile=f"{name.lower().replace(' ','_')}.json")
        if not p: return
        with open(p, 'w', encoding='utf-8') as f:
            json.dump({"name": name, "pdf": self.pdf_path or "", "fields": {k: [fld.to_dict() for fld in v] for k, v in self.fields.items() if v}},
                      f, indent=2, ensure_ascii=False)
        self.template_path, self.template_name = p, name
        total = sum(len(v) for v in self.fields.values())
        messagebox.showinfo("Gespeichert", f"'{name}', {total} Felder"); self._status()

    # ─── Projekt ──────────────────────────────────────────────
    def _load_project(self):
        """Lädt ein Projekt-JSON mit den Feldwerten."""
        p = filedialog.askopenfilename(title="Projekt öffnen", filetypes=[("JSON", "*.json"), ("*", "*.*")])
        if not p: return
        try:
            with open(p, encoding='utf-8') as f: data = json.load(f)
            # PDF automatisch laden, falls referenziert
            pdf = data.get("pdf", "")
            if pdf and os.path.exists(pdf):
                self._load_pdf(pdf)
            elif pdf:
                messagebox.showwarning("PDF fehlt", f"PDF nicht gefunden:\n{pdf}\nBitte manuell öffnen.")
            # Vorlage laden (Felddefinitionen)
            if "fields" in data:
                raw = data["fields"]
                if isinstance(raw, dict):
                    # Neue Struktur: fields pro Seite
                    self.fields = {}
                    for page_key, flist in raw.items():
                        self.fields[page_key] = []
                        for item in flist:
                            f = FieldRect.from_dict(item)
                            val = data.get("values", {}).get(f"{page_key}:{f.label}", "")
                            if val:
                                f.value = val
                            self.fields[page_key].append(f)
                else:
                    # Alte Struktur: flache Liste → aktuelle Seite
                    self.fields = {str(self.current_page): []}
                    for item in raw:
                        f = FieldRect.from_dict(item)
                        val = data.get("values", {}).get(f.label, "")
                        if val:
                            f.value = val
                        self.fields[str(self.current_page)].append(f)
            self.selected = None
            self.project_path, self.project_name = p, data.get("name", os.path.basename(p))
            self._render(); self._status()
            total = sum(len(v) for v in self.fields.values())
            n_val = sum(1 for v in self.fields.values() for f in v if f.value)
            messagebox.showinfo("Geladen", f"Projekt '{self.project_name}', {total} Felder ({n_val} ausgefüllt)")
        except Exception as e: messagebox.showerror("Fehler", f"Projekt: {e}")

    def _save_project(self):
        """Speichert Felder + Werte als Projekt-JSON."""
        if not any(self.fields.values()):
            return messagebox.showwarning("Leer", "Keine Felder im Projekt.")
        name = simpledialog.askstring("Name", "Projektname:", initialvalue=self.project_name or "Ohne Namen")
        if not name: return
        p = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")],
                                         initialfile=f"{name.lower().replace(' ','_')}.json")
        if not p: return
        data = {
            "name": name,
            "pdf": self.pdf_path or "",
            "fields": {k: [fld.to_dict() for fld in v] for k, v in self.fields.items() if v},
            "values": {},
        }
        for page_key, flist in self.fields.items():
            for f in flist:
                if f.value:
                    data["values"][f"{page_key}:{f.label}"] = f.value
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        self.project_path, self.project_name = p, name
        total = sum(len(v) for v in self.fields.values())
        n_val = sum(1 for v in self.fields.values() for f in v if f.value)
        messagebox.showinfo("Gespeichert", f"Projekt '{name}', {n_val} Feld(er) ausgefüllt"); self._status()

    # ─── Popup-Menüs ──────────────────────────────────────────
    def _close_menus(self, event=None):
        """Schließt alle offenen Popup-Menüs."""
        if hasattr(self, '_active_menu') and self._active_menu:
            try:
                self._active_menu.unpost()
            except:
                pass
            self._active_menu = None

    def _show_open_menu(self):
        """Dropdown-Menü mit den 3 Öffnen-Optionen."""
        self._close_menus()
        menu = tk.Menu(self.root, tearoff=0, bg=C["bg"], fg=C["text"],
                       activebackground=C["accent"], activeforeground="#11111b",
                       font=("Segoe UI",10))
        menu.add_command(label="📄 PDF öffnen", command=lambda: (self._close_menus(), self._open_pdf()))
        menu.add_command(label="📋 Vorlage öffnen", command=lambda: (self._close_menus(), self._load_template()))
        menu.add_command(label="🗂️ Projekt öffnen", command=lambda: (self._close_menus(), self._load_project()))
        x = self.btn_open.winfo_rootx()
        y = self.btn_open.winfo_rooty() + self.btn_open.winfo_height()
        self._active_menu = menu
        menu.post(x, y)

    def _show_save_menu(self):
        """Dropdown-Menü mit den 3 Speichern-Optionen."""
        self._close_menus()
        menu = tk.Menu(self.root, tearoff=0, bg=C["bg"], fg=C["text"],
                       activebackground=C["green"], activeforeground="#11111b",
                       font=("Segoe UI",10))
        menu.add_command(label="📄 PDF speichern", command=lambda: (self._close_menus(), self._save_pdf()))
        menu.add_command(label="📋 Vorlage speichern", command=lambda: (self._close_menus(), self._save_template()))
        menu.add_command(label="🗂️ Projekt speichern", command=lambda: (self._close_menus(), self._save_project()))
        x = self.btn_save.winfo_rootx()
        y = self.btn_save.winfo_rooty() + self.btn_save.winfo_height()
        self._active_menu = menu
        menu.post(x, y)

    # ─── Zoom ─────────────────────────────────────────────────
    def _fit_zoom(self):
        try:
            cw, ch = max(1,self.cv.winfo_width()), max(1,self.cv.winfo_height())
            if self.pdf_image: self.zoom = min(cw/self.pdf_image.width, ch/self.pdf_image.height) * 0.95
        except: self.zoom = 0.35

    def _do_zoom(self, f):
        self._stop_typing(); self.zoom = max(0.05, min(3.0, self.zoom * f)); self._render()

    def _zoom_reset(self): self._stop_typing(); self._fit_zoom(); self._render()

    # ─── Rendern ──────────────────────────────────────────────
    def _render(self):
        if not self.pdf_image: return
        try:
            cw, ch = max(1,self.cv.winfo_width()), max(1,self.cv.winfo_height())
            nw, nh = max(1,int(self.pdf_image.width*self.zoom)), max(1,int(self.pdf_image.height*self.zoom))
            img = self.pdf_image.resize((nw,nh), Image.LANCZOS)
            self.pdf_tk = ImageTk.PhotoImage(img)
            self.cv.delete("all")
            base_ox, base_oy = (cw-nw)//2, (ch-nh)//2
            self.ox, self.oy = base_ox + self.pan_ox, base_oy + self.pan_oy
            self.cv.create_image(self.ox, self.oy, anchor=tk.NW, image=self.pdf_tk)

            # Lineal (Hilfslinien)
            if self.show_ruler and self.mode == "edit":
                rl = self.ruler_step * self.zoom
                pdf_right = self.ox + nw
                pdf_bottom = self.oy + nh
                # Vertikale Hilfslinien (alle ruler_step Pixel im PDF)
                for x0 in range(self.ox, int(pdf_right), int(rl)):
                    self.cv.create_line(x0, self.oy, x0, pdf_bottom,
                                       fill="#7f849c", width=1, dash=(1,5), tags="ruler")
                # Horizontale Hilfslinien
                for y0 in range(self.oy, int(pdf_bottom), int(rl)):
                    self.cv.create_line(self.ox, y0, pdf_right, y0,
                                       fill="#7f849c", width=1, dash=(1,5), tags="ruler")
                # Rand-Markierungen (oben und links)
                st = self.ruler_step // 5  # 10px bei step=50
                step_px = st * self.zoom
                for i in range(0, int(nw / step_px) + 1):
                    px = i * step_px
                    if i % 5 == 0:
                        self.cv.create_line(self.ox + px, self.oy, self.ox + px, self.oy + 8,
                                           fill=C["text"], width=1, tags="ruler")
                        self.cv.create_line(self.ox, self.oy + px, self.ox + 8, self.oy + px,
                                           fill=C["text"], width=1, tags="ruler")
                    elif i % 5 == 2:
                        self.cv.create_line(self.ox + px, self.oy, self.ox + px, self.oy + 4,
                                           fill=C["status"], width=1, tags="ruler")
                        self.cv.create_line(self.ox, self.oy + px, self.ox + 4, self.oy + px,
                                           fill=C["status"], width=1, tags="ruler")

            for f in self._current_fields(): self._draw(f)

            # Stempel zeichnen
            for s in self._current_stamps():
                try:
                    self._draw_stempel(s)
                except Exception as e:
                    print(f"Stempel-Fehler: {e}")

            # Pfeile zeichnen
            for a in self._current_arrows():
                try:
                    self._draw_arrow(a)
                except Exception as e:
                    print(f"Pfeil-Fehler: {e}")

            # Rechtecke zeichnen
            for r in self._current_rects():
                try:
                    self._draw_rect(r)
                except Exception as e:
                    print(f"Rechteck-Fehler: {e}")

            # Linien zeichnen
            for ln in self._current_lines():
                try:
                    self._draw_line(ln)
                except Exception as e:
                    print(f"Linien-Fehler: {e}")

            # Ellipsen zeichnen
            for el in self._current_ellipses():
                try:
                    self._draw_ellipse(el)
                except Exception as e:
                    print(f"Ellipsen-Fehler: {e}")

            # Masken zeichnen
            for m in self._current_masks():
                try:
                    self._draw_mask(m)
                except Exception as e:
                    print(f"Masken-Fehler: {e}")

            # Textmarker zeichnen
            for h in self._current_highlighters():
                try:
                    self._draw_highlighter(h)
                except Exception as e:
                    print(f"Textmarker-Fehler: {e}")

            self.cv.create_text(cw-10,10, anchor=tk.NE, text=f"{self.zoom*100:.0f}%",
                               fill="white", font=("Arial",10))
        except Exception as e: print(f"Render: {e}")

    def _draw(self, f):
        z, ox, oy = self.zoom, self.ox, self.oy
        x1, y1 = ox+int(f.x1*z), oy+int(f.y1*z)
        x2, y2 = ox+int(f.x2*z), oy+int(f.y2*z)

        # Rahmen zeichnen (nur wenn show_frames)
        if self.show_frames:
            if self.mode == "edit":
                if f == self.selected: oc, fi, w = C["yellow"], "", 3
                else: oc, fi, w = C["accent"], "", 2
            else:
                if f == self.active_field: oc, fi, w = "#000000", "", 3
                else: oc, fi, w = "#64ff64", "", 2
            self.cv.create_rectangle(x1, y1, x2, y2, outline=oc, fill=fi, width=w, tags="f")

        # Label über dem Feld
        if self.show_frames and f.label:
            fs = max(8, int(9*z))
            self.cv.create_text(x1+2, y1-fs-2, anchor=tk.SW, text=f.label,
                               fill="#89b4fa" if self.mode=="edit" else "#64ff64",
                               font=("Segoe UI",fs), tags="f")

        # Wert anzeigen — Schrift aus Einstellung / Feld-eigen
        if f.value and f.type == "text":
            pt = max(6, min(36, getattr(f, 'font_size', self.font_size) or self.font_size))
            fs = max(8, int(pt * SCALE * z * 0.8))
            txt = str(f.value)
            fc = self.font_color if self.font_color else "#000000"
            # SW-Anker = unten links, y = y2 setzt die Baseline auf Feld-Unterkante
            # So ragen Unterlängen (g,j,p,q,y) nach unten raus wie bei PIL
            y_base = y2 - 1
            # Schriftname für tkinter: Liberation Sans → Liberation Sans (tkinter kann das)
            # Fallback: wenn unbekannt, nimm "Liberation Sans"
            fn_map = {
                "Liberation Sans Bold": "Liberation Sans",
                "Liberation Serif": "Liberation Serif",
                "Liberation Mono": "Liberation Mono",
                "DejaVu Sans": "DejaVu Sans",
                "Arial": "Arial",
                "Arial Bold": "Arial",
                "Calibri": "Calibri",
                "Calibri Bold": "Calibri",
                "Times New Roman": "Times New Roman",
                "Times New Roman Bold": "Times New Roman",
                "Segoe UI": "Segoe UI",
                "Segoe UI Bold": "Segoe UI",
                "Consolas": "Consolas",
            }
            fn = fn_map.get(self.font_name, self.font_name if self.font_name else "Arial")
            self.cv.create_text(x1+3, y_base, anchor=tk.SW, text=txt, fill=fc,
                               font=(fn,fs), tags="f")

        # Checkbox
        if f.type == "checkbox" and f.value in (True,"True","true","1"):
            cx, cy = (x1+x2)//2, (y1+y2)//2
            sz = max(6, int((y2 - y1) * 0.8))
            self.cv.create_text(cx, cy, text="✓", fill="#000",
                               font=("Segoe UI",sz,"bold"), tags="f")

    # ─── Maus ─────────────────────────────────────────────────
    def _insert_date(self):
        """Fuegt heutiges Datum (TT.MM.JJJJ) in das aktive Textfeld ein."""
        if self.mode != "fill":
            self._status_text("Datum nur im Ausfuell-Modus")
            return
        if not self.active_field or self.active_field.type != "text":
            self._status_text("Kein aktives Textfeld — bitte zuerst Feld anklicken")
            return
        from datetime import date
        today = date.today().strftime("%d.%m.%Y")
        self._undo_snapshot()
        self.active_field.value = (str(self.active_field.value) if self.active_field.value else "") + today
        self._render()
        self._status()

    def _ic(self, e): return (e.x - self.ox)/self.zoom, (e.y - self.oy)/self.zoom

    def _find(self, px, py):
        for f in reversed(self._current_fields()):
            if f.contains(px, py): return f
        return None

    def _stop_typing(self):
        self.active_field = None; self.typing = False; self._render()

    def _key(self, e):
        if self.mode != "fill" or not self.active_field or self.active_field.type != "text": return
        if e.keysym in ("Return","Escape"): self._stop_typing(); return
        if e.keysym == "BackSpace":
            v = self.active_field.value
            self.active_field.value = v[:-1] if isinstance(v,str) else ""
            self._render(); return
        if e.keysym == "Tab":
            cur = self._current_fields()
            idx = cur.index(self.active_field); self.active_field = None
            for i in range(1, len(cur)):
                nf = cur[(idx + i) % len(cur)]
                if nf.type == "text": self.active_field = nf; break
            if self.active_field: self._render(); self.cv.focus_set()
            return
        if e.keysym == "Delete": self.active_field.value = ""; self._render(); return
        if e.char and e.char.isprintable() and len(e.char)==1:
            v = str(self.active_field.value) if self.active_field.value else ""
            self.active_field.value = v + e.char; self._render(); self._status()
        self.cv.focus_set()

    def _click(self, e):
        """Linksklick ohne Strg: Edit → neues Feld / Fill → auswählen / Stempel → setzen"""
        self._stop_typing()
        self._drag_mode = None  # noch kein Modus
        self.cv.delete("drag")
        px, py = self._ic(e)

        # Werkzeug aus Toolbox?
        if self.selected_tool == "Stempel":
            self._stempel_dialog(int(px), int(py))
            self.selected_tool = None
            for n, btn in self._tool_buttons.items():
                btn.configure(bg=C["bg"], fg=C["text"], relief=tk.RAISED)
            self._status()
            return

        if self.selected_tool == "Pfeil":
            # Pfeil zeichnen: Klick = Start, Drag = Ende
            self._arrow_start = (int(px), int(py))
            self._drag_mode = "arrow"
            return

        if self.selected_tool == "Rechteck":
            self._rect_start = (int(px), int(py))
            self._drag_mode = "rect"
            return

        if self.selected_tool == "Ellipse":
            self._ellipse_start = (int(px), int(py))
            self._drag_mode = "ellipse"
            return

        if self.selected_tool == "Maske":
            self._mask_start = (int(px), int(py))
            self._drag_mode = "mask"
            return

        if self.selected_tool == "Linie":
            self._line_start = (int(px), int(py))
            self._drag_mode = "line"
            return

        if self.selected_tool == "Textmarker":
            self._highlighter_start = (int(px), int(py))
            self._drag_mode = "highlighter"
            return

        if self.selected_tool == "Bild einfügen":
            self.selected_tool = None
            for n, btn in self._tool_buttons.items():
                btn.configure(bg=C["bg"], fg=C["text"], relief=tk.RAISED)
            self._scan_from_file()
            return

        if self.mode == "edit":
            self._nf_px, self._nf_py = px, py
            self._drag_mode = "newfield"
        elif self.mode == "fill":
            f = self._find(px, py)
            if f:
                if f.type == "text":
                    self.active_field = f
                    self.typing = True
                    self.cv.focus_set()
                    self._render()
                    self._status()
                elif f.type == "checkbox":
                    self._undo_snapshot()
                    f.value = not (f.value in (True, "True", "true", "1"))
                    self._render()
                    self._status()
            else:
                self._drag_mode = "pan"
                self.pan_x, self.pan_y = e.x, e.y
                self.cv.configure(cursor="fleur")

    def _ctrlclick(self, e):
        """Strg+Linksklick: Feld verschieben (Edit)"""
        if self.mode != "edit":
            return
        self._stop_typing()
        self.cv.delete("drag")
        px, py = self._ic(e)
        f = self._find(px, py)
        if f:
            self.selected = f
            self._mv_field = f
            self._mv_px, self._mv_py = px, py
            self._mv_dx, self._mv_dy = px - f.x1, py - f.y1
            self._mv_w, self._mv_h = f.w, f.h  # <-- sichern
            self._drag_mode = "move"
            self._render()
            self._status()

    def _b1_motion(self, e):
        """Button-1 Bewegung: je nach drag_mode"""
        dm = getattr(self, '_drag_mode', None)
        if dm == "pan":
            self.pan_ox += e.x - self.pan_x
            self.pan_oy += e.y - self.pan_y
            self.pan_x = e.x
            self.pan_y = e.y
            self._render()
        elif dm == "newfield":
            if self.mode != "edit":
                return
            px, py = self._ic(e)
            if abs(px - self._nf_px) < 3 and abs(py - self._nf_py) < 3:
                return
            self.cv.delete("drag")
            g = self.grid_size
            x1 = min(self._nf_px, px)
            y1 = min(self._nf_py, py) // g * g
            x2 = max(self._nf_px, px)
            y2 = y1 + self.frame_height
            z = self.zoom
            self.cv.create_rectangle(
                self.ox + int(x1 * z), self.oy + int(y1 * z),
                self.ox + int(x2 * z), self.oy + int(y2 * z),
                outline=C["accent"], fill="", width=2, dash=(4, 4), tags="drag"
            )
        elif dm == "move":
            if not hasattr(self, '_mv_field') or not self._mv_field:
                return
            px, py = self._ic(e)
            if abs(px - self._mv_px) < 2 and abs(py - self._mv_py) < 2:
                return
            f = self._mv_field
            g = self.grid_size
            nx = int(px - self._mv_dx) // g * g
            ny = int(py - self._mv_dy) // g * g
            # Breite/Höhe VOR dem Ändern sichern (Properties sind live!)
            old_w = f.x2 - f.x1
            old_h = f.y2 - f.y1
            f.x1 = nx
            f.y1 = ny
            f.x2 = nx + getattr(self, '_mv_w', old_w)
            f.y2 = ny + getattr(self, '_mv_h', old_h)
            self.cv.delete("drag")
            z = self.zoom
            self.cv.create_rectangle(
                self.ox + int(f.x1 * z), self.oy + int(f.y1 * z),
                self.ox + int(f.x2 * z), self.oy + int(f.y2 * z),
                outline=C["yellow"], fill="", width=3, dash=(4, 4), tags="drag"
            )
            self._render()
        elif dm == "arrow":
            px, py = self._ic(e)
            x1, y1 = self._arrow_start
            if abs(px - x1) < 3 and abs(py - y1) < 3:
                return
            self.cv.delete("drag")
            z = self.zoom
            # Vorschau: Linie + Pfeilspitze
            ox, oy = self.ox, self.oy
            self._draw_arrow_preview(ox + int(x1 * z), oy + int(y1 * z),
                                     ox + int(px * z), oy + int(py * z))

        elif dm == "rect":
            px, py = self._ic(e)
            x1, y1 = self._rect_start
            if abs(px - x1) < 3 and abs(py - y1) < 3:
                return
            self.cv.delete("drag")
            z = self.zoom
            ox, oy = self.ox, self.oy
            rx1 = ox + int(min(x1, px) * z)
            ry1 = oy + int(min(y1, py) * z)
            rx2 = ox + int(max(x1, px) * z)
            ry2 = oy + int(max(y1, py) * z)
            self.cv.create_rectangle(rx1, ry1, rx2, ry2,
                                     outline=C["accent"], width=2, dash=(4, 4), tags="drag")

        elif dm == "ellipse":
            px, py = self._ic(e)
            x1, y1 = self._ellipse_start
            if abs(px - x1) < 3 and abs(py - y1) < 3:
                return
            self.cv.delete("drag")
            z = self.zoom
            ox, oy = self.ox, self.oy
            ex1 = ox + int(min(x1, px) * z)
            ey1 = oy + int(min(y1, py) * z)
            ex2 = ox + int(max(x1, px) * z)
            ey2 = oy + int(max(y1, py) * z)
            self.cv.create_oval(ex1, ey1, ex2, ey2,
                                outline=C["accent"], width=2, dash=(4, 4), tags="drag")

        elif dm == "mask":
            px, py = self._ic(e)
            x1, y1 = self._mask_start
            if abs(px - x1) < 3 and abs(py - y1) < 3:
                return
            self.cv.delete("drag")
            z = self.zoom
            ox, oy = self.ox, self.oy
            mx1 = ox + int(min(x1, px) * z)
            my1 = oy + int(min(y1, py) * z)
            mx2 = ox + int(max(x1, px) * z)
            my2 = oy + int(max(y1, py) * z)
            self.cv.create_rectangle(mx1, my1, mx2, my2,
                                     outline=C["accent"], width=2, dash=(4, 4), tags="drag")

        elif dm == "highlighter":
            px, py = self._ic(e)
            x1, y1 = self._highlighter_start
            if abs(px - x1) < 3 and abs(py - y1) < 3:
                return
            self.cv.delete("drag")
            z = self.zoom
            ox, oy = self.ox, self.oy
            hx1 = ox + int(min(x1, px) * z)
            hy1 = oy + int(min(y1, py) * z)
            hx2 = ox + int(max(x1, px) * z)
            hy2 = oy + int(max(y1, py) * z)
            # Halbtransparente Vorschau
            light_color = self._lighten_color(self.tool_highlighter_color, 0.6)
            self.cv.create_rectangle(hx1, hy1, hx2, hy2,
                                     fill=light_color, outline=self.tool_highlighter_color,
                                     width=2, dash=(4, 4), tags="drag")

        elif dm == "line":
            px, py = self._ic(e)
            x1, y1 = self._line_start
            if abs(px - x1) < 3 and abs(py - y1) < 3:
                return
            self.cv.delete("drag")
            z = self.zoom
            ox, oy = self.ox, self.oy
            px2, py2 = self._snap_line(px, py, x1, y1)
            self.cv.create_line(
                ox + int(x1 * z), oy + int(y1 * z),
                ox + int(px2 * z), oy + int(py2 * z),
                fill=C["accent"], width=2, dash=(4, 4), tags="drag"
            )

    def _release_b1(self, e):
        """Button-1 loslassen: je nach drag_mode"""
        dm = getattr(self, '_drag_mode', None)
        self._drag_mode = None
        self.cv.delete("drag")
        if dm == "pan":
            self.panning = False
            self.cv.configure(cursor="hand2")
        elif dm == "newfield" and self.mode == "edit":
            px, py = self._ic(e)
            if abs(px - self._nf_px) < 8 and abs(py - self._nf_py) < 8:
                return
            g = self.grid_size
            y_top = min(self._nf_py, py)
            y1 = int(y_top) // g * g
            f = FieldRect(
                x1=int(min(self._nf_px, px)), y1=y1,
                x2=int(max(self._nf_px, px)), y2=y1 + self.frame_height,
                label="", ftype="text"
            )
            result = self._field_dialog(f)
            if result:
                self._undo_snapshot()
                f.label, f.type, f.group = result
                self._current_fields().append(f)
                self.selected = f
                self._render()
                self._status()
        elif dm == "move":
            if hasattr(self, '_mv_field') and self._mv_field:
                self._undo_snapshot()
                self._mv_field = None
                self._render()
                self._status()
        elif dm == "arrow" and e:
            px, py = self._ic(e)
            x1, y1 = self._arrow_start
            if abs(px - x1) >= 8 or abs(py - y1) >= 8:
                self._undo_snapshot()
                key = str(self.current_page)
                if key not in self.arrows:
                    self.arrows[key] = []
                self.arrows[key].append(Arrow(x1=x1, y1=y1, x2=int(px), y2=int(py),
                                              color=self.tool_arrow_color,
                                              width=self.tool_arrow_width,
                                              head_len=self.tool_arrow_head_len))
                self._render()
                self._status()
        elif dm == "rect" and e:
            px, py = self._ic(e)
            x1, y1 = self._rect_start
            if abs(px - x1) >= 8 or abs(py - y1) >= 8:
                self._undo_snapshot()
                key = str(self.current_page)
                if key not in self.rects:
                    self.rects[key] = []
                self.rects[key].append(Rect(x1=x1, y1=y1, x2=int(px), y2=int(py),
                                           color=self.tool_rect_color,
                                           width=self.tool_rect_width))
                self._render()
                self._status()
        elif dm == "ellipse" and e:
            px, py = self._ic(e)
            x1, y1 = self._ellipse_start
            if abs(px - x1) >= 8 or abs(py - y1) >= 8:
                self._undo_snapshot()
                key = str(self.current_page)
                if key not in self.ellipses:
                    self.ellipses[key] = []
                self.ellipses[key].append(Ellipse(x1=x1, y1=y1, x2=int(px), y2=int(py),
                                                  color=self.tool_ellipse_color,
                                                  width=self.tool_ellipse_width))
                self._render()
                self._status()
        elif dm == "mask" and e:
            px, py = self._ic(e)
            x1, y1 = self._mask_start
            if abs(px - x1) >= 8 or abs(py - y1) >= 8:
                self._undo_snapshot()
                key = str(self.current_page)
                if key not in self.masks:
                    self.masks[key] = []
                self.masks[key].append(Mask(x1=x1, y1=y1, x2=int(px), y2=int(py),
                                           color=self.tool_mask_color,
                                           fill=self.tool_mask_fill,
                                           width=self.tool_mask_width))
                self._render()
                self._status()
        elif dm == "highlighter" and e:
            px, py = self._ic(e)
            x1, y1 = self._highlighter_start
            if abs(px - x1) >= 8 or abs(py - y1) >= 8:
                self._undo_snapshot()
                key = str(self.current_page)
                if key not in self.highlighters:
                    self.highlighters[key] = []
                self.highlighters[key].append(Highlighter(
                    x1=x1, y1=y1, x2=int(px), y2=int(py),
                    color=self.tool_highlighter_color,
                    opacity=self.tool_highlighter_opacity))
                self._render()
                self._status()
        elif dm == "line" and e:
            px, py = self._ic(e)
            x1, y1 = self._line_start
            if abs(px - x1) >= 8 or abs(py - y1) >= 8:
                # Auf waagerecht/senkrecht einrasten
                px2, py2 = self._snap_line(px, py, x1, y1)
                self._undo_snapshot()
                key = str(self.current_page)
                if key not in self.lines:
                    self.lines[key] = []
                self.lines[key].append(Line(x1=x1, y1=y1, x2=int(px2), y2=int(py2),
                                            color=self.tool_line_color,
                                            width=self.tool_line_width))
                self._render()
                self._status()

    def _middle_click(self, e):
        """Mittlere Maustaste: Feld verschieben (Edit) oder nix"""
        px, py = self._ic(e)
        f = self._find(px, py)
        if f and self.mode == "edit":
            self.selected = f
            self._mv_field = f
            self._mv_px, self._mv_py = px, py
            self._mv_dx, self._mv_dy = px - f.x1, py - f.y1
            self._mv_w, self._mv_h = f.w, f.h  # <-- sichern vor Änderung
            self._render()
            self._status()

    def _middle_drag(self, e):
        """Mittlere Maustaste ziehen: Feld verschieben"""
        if not hasattr(self, '_mv_field') or not self._mv_field:
            return
        px, py = self._ic(e)
        if abs(px - self._mv_px) < 2 and abs(py - self._mv_py) < 2:
            return
        f = self._mv_field
        g = self.grid_size
        nx = int(px - self._mv_dx) // g * g
        ny = int(py - self._mv_dy) // g * g
        f.x1 = nx
        f.y1 = ny
        f.x2 = nx + getattr(self, '_mv_w', f.w)
        f.y2 = ny + getattr(self, '_mv_h', f.h)
        self.cv.delete("drag")
        z = self.zoom
        self.cv.create_rectangle(
            self.ox + int(f.x1 * z), self.oy + int(f.y1 * z),
            self.ox + int(f.x2 * z), self.oy + int(f.y2 * z),
            outline=C["yellow"], fill="", width=3, dash=(4, 4), tags="drag"
        )
        self._render()

    def _middle_release(self, e):
        """Mittlere Maustaste loslassen: Verschieben abschliessen"""
        if hasattr(self, '_mv_field') and self._mv_field:
            self._mv_field = None
            self.cv.delete("drag")
            self._render()
            self._status()

    def _right(self, e):
        """Rechtsklick: Loeschen von Feld/Pfeil/Stempel/Rechteck oder Panning."""
        if self.panning:
            return
        px, py = self._ic(e)
        # Feld loeschen (nur Edit-Modus)
        f = self._find(px, py)
        if f and self.mode == "edit":
            if messagebox.askyesno("Loeschen", f"Feld '{f.label}' loeschen?"):
                self._undo_snapshot()
                self._current_fields().remove(f)
                if self.selected == f:
                    self.selected = None
                self._render()
                self._status()
            return
        # Pfeil loeschen (alle Modi) - Toleranz 20 Pixel
        for a in reversed(self._current_arrows()):
            if self._point_near_line(px, py, a.x1, a.y1, a.x2, a.y2, tol=20):
                if messagebox.askyesno("Loeschen", "Diesen Pfeil loeschen?"):
                    self._undo_snapshot()
                    self._current_arrows().remove(a)
                    self._render()
                    self._status()
                return
        # Stempel loeschen
        for s in reversed(self._current_stamps()):
            if s.contains(px, py):
                if messagebox.askyesno("Loeschen", f"Stempel '{s.text}' loeschen?"):
                    self._undo_snapshot()
                    self._current_stamps().remove(s)
                    self._render()
                    self._status()
                return
        # Rechteck loeschen
        for r in reversed(self._current_rects()):
            if r.x1 <= px <= r.x2 and r.y1 <= py <= r.y2:
                if messagebox.askyesno("Loeschen", "Dieses Rechteck loeschen?"):
                    self._undo_snapshot()
                    self._current_rects().remove(r)
                    self._render()
                    self._status()
                return
        # Linie loeschen
        for ln in reversed(self._current_lines()):
            tol = 15 / self.zoom if self.zoom > 0 else 15
            if self._point_near_line(px, py, ln.x1, ln.y1, ln.x2, ln.y2, tol=tol):
                if messagebox.askyesno("Loeschen", "Diese Linie loeschen?"):
                    self._undo_snapshot()
                    self._current_lines().remove(ln)
                    self._render()
                    self._status()
                return
        # Ellipse loeschen
        for el in reversed(self._current_ellipses()):
            if el.contains(px, py):
                if messagebox.askyesno("Loeschen", "Diese Ellipse loeschen?"):
                    self._undo_snapshot()
                    self._current_ellipses().remove(el)
                    self._render()
                    self._status()
                return
        # Maske loeschen
        for m in reversed(self._current_masks()):
            if m.contains(px, py):
                if messagebox.askyesno("Loeschen", "Diese Maske loeschen?"):
                    self._undo_snapshot()
                    self._current_masks().remove(m)
                    self._render()
                    self._status()
                return
        # Textmarker loeschen
        for h in reversed(self._current_highlighters()):
            if h.contains(px, py):
                if messagebox.askyesno("Loeschen", "Diesen Textmarker loeschen?"):
                    self._undo_snapshot()
                    self._current_highlighters().remove(h)
                    self._render()
                    self._status()
                return
        # Nichts getroffen -> Panning
        self.panning = True
        self.pan_x, self.pan_y = e.x, e.y
        self.cv.configure(cursor="fleur")

    def _right_drag(self, e):
        """Rechtsklick ziehen: Panning"""
        if not self.panning:
            return
        self.pan_ox += e.x - self.pan_x
        self.pan_oy += e.y - self.pan_y
        self.pan_x = e.x
        self.pan_y = e.y
        self._render()

    def _right_release(self, e):
        """Rechtsklick loslassen: Panning beenden"""
        if self.panning:
            self.panning = False
            self.cv.configure(cursor="hand2")

    def _tool_settings_dialog(self, tool):
        """Rechtsklick-Dialog für Werkzeug-Einstellungen (Linie/Pfeil)."""
        win = tk.Toplevel(self.root)
        win.title(f"{tool} Einstellungen")
        win.configure(bg=C["bg"])
        win.resizable(False, False)
        win.transient(self.root)
        x = self.root.winfo_x() + 180
        y = self.root.winfo_y() + 200
        win.geometry(f"+{x}+{y}")
        # Fenster sichtbar machen, dann Grab — toleriert Fehler
        win.update()
        try:
            win.grab_set()
        except tk.TclError:
            pass
        win.lift()

        is_arrow = tool == "Pfeil"
        is_rect = tool == "Rechteck"
        is_ellipse = tool == "Ellipse"
        is_mask = tool == "Maske"
        is_highlighter = tool == "Textmarker"
        if is_mask:
            color_key = "tool_mask_color"
            width_key = "tool_mask_width"
            fill_key = "tool_mask_fill"
        elif is_highlighter:
            color_key = "tool_highlighter_color"
            width_key = None
            fill_key = None
        elif is_ellipse:
            color_key = "tool_mask_color"
            width_key = "tool_mask_width"
            fill_key = "tool_mask_fill"
        elif is_ellipse:
            color_key = "tool_ellipse_color"
            width_key = "tool_ellipse_width"
            fill_key = None
        elif is_rect:
            color_key = "tool_rect_color"
            width_key = "tool_rect_width"
            fill_key = None
        elif is_arrow:
            color_key = "tool_arrow_color"
            width_key = "tool_arrow_width"
            fill_key = None
        else:
            color_key = "tool_line_color"
            width_key = "tool_line_width"
            fill_key = None
        cur_color = getattr(self, color_key, "#e74c3c")
        cur_width = getattr(self, width_key, 3) if width_key else None

        # ─── Farbe ───
        color_var = tk.StringVar(value=cur_color)
        tk.Label(win, text="Farbe:", bg=C["bg"], fg=C["text"],
                 font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w", padx=10, pady=(10,4))

        def _set_color(c):
            color_var.set(c)
            # Alle Buttons aktualisieren
            for b, bc in farb_refs:
                if bc == c:
                    b.configure(text="✓", relief=tk.SUNKEN)
                else:
                    b.configure(text="  ", relief=tk.FLAT)

        farben_liste = [("#ffff00", "Gelb"), ("#e74c3c", "Rot"), ("#2ecc71", "Grün"),
                        ("#3498db", "Blau"), ("#f39c12", "Orange"), ("#9b59b6", "Lila"),
                        ("#1e1e2e", "Schwarz"), ("#555555", "Grau")]
        farb_refs = []
        for col_idx, (c, lbl) in enumerate(farben_liste):
            if c == cur_color:
                btn = tk.Button(win, text="✓", font=("Segoe UI", 8, "bold"),
                               bg=c, fg="white" if c in ("#1e1e2e","#000000") else "#11111b",
                               relief=tk.SUNKEN, bd=2, width=3, cursor="hand2")
            else:
                btn = tk.Button(win, text="  ", font=("Segoe UI", 8),
                               bg=c, fg="white" if c in ("#1e1e2e","#000000") else "#11111b",
                               relief=tk.FLAT, bd=2, width=3, cursor="hand2",
                               command=lambda cc=c: _set_color(cc))
            btn.grid(row=0, column=col_idx + 1, padx=2, pady=(10,4))
            farb_refs.append((btn, c))

        # ─── Strichstärke ───
        if width_key:
            tk.Label(win, text="Strichstärke:", bg=C["bg"], fg=C["text"],
                     font=("Segoe UI", 10, "bold")).grid(row=1, column=0, sticky="w", padx=10, pady=(6,4))
            width_var = tk.IntVar(value=cur_width)
            tk.Spinbox(win, from_=1, to=12, textvariable=width_var, width=8,
                       font=("Segoe UI", 10), bg=C["bg"], fg=C["text"],
                       buttonbackground=C["accent"]).grid(row=1, column=1, columnspan=3, sticky="w", padx=10)
        else:
            width_var = None

        head_len_var = None
        if is_arrow:
            # ─── Pfeilspitzengröße ───
            tk.Label(win, text="Spitzengröße:", bg=C["bg"], fg=C["text"],
                     font=("Segoe UI", 10, "bold")).grid(row=2, column=0, sticky="w", padx=10, pady=(6,4))
            head_len_var = tk.IntVar(value=self.tool_arrow_head_len)
            tk.Spinbox(win, from_=5, to=80, textvariable=head_len_var, width=8,
                       font=("Segoe UI", 10), bg=C["bg"], fg=C["text"],
                       buttonbackground=C["accent"]).grid(row=2, column=1, columnspan=3, sticky="w", padx=10)

        # ─── OK ───
        fill_var = None
        if is_mask:
            # ─── Füllfarbe ───
            cur_fill = getattr(self, fill_key, "#ffffff")
            fill_var = tk.StringVar(value=cur_fill)
            tk.Label(win, text="Füllfarbe:", bg=C["bg"], fg=C["text"],
                     font=("Segoe UI", 10, "bold")).grid(row=2, column=0, sticky="w", padx=10, pady=(6,4))

            def _set_fill(c):
                fill_var.set(c)
                for b, bc in fill_refs:
                    if bc == c:
                        b.configure(text="✓", relief=tk.SUNKEN)
                    else:
                        b.configure(text="  ", relief=tk.FLAT)

            fill_farben = [("#ffffff", "Weiß"), ("#cccccc", "Hellgrau"), ("#888888", "Grau"),
                          ("#000000", "Schwarz"), ("#e74c3c", "Rot"), ("#2ecc71", "Grün"),
                          ("#3498db", "Blau"), ("#f1c40f", "Gelb")]
            fill_refs = []
            for col_idx, (c, lbl) in enumerate(fill_farben):
                if c == cur_fill:
                    btn = tk.Button(win, text="✓", font=("Segoe UI", 8, "bold"),
                                   bg=c, fg="white" if c in ("#000000","#888888") else "#11111b",
                                   relief=tk.SUNKEN, bd=2, width=3, cursor="hand2")
                else:
                    btn = tk.Button(win, text="  ", font=("Segoe UI", 8),
                                   bg=c, fg="white" if c in ("#000000","#888888") else "#11111b",
                                   relief=tk.FLAT, bd=2, width=3, cursor="hand2",
                                   command=lambda cc=c: _set_fill(cc))
                btn.grid(row=2, column=col_idx + 1, padx=2, pady=(6,4))
                fill_refs.append((btn, c))

        btn_row = 4 if is_mask else (3 if is_arrow else 2)
        if is_highlighter:
            btn_row = 2
            # Opacity-Schieber für Textmarker
            tk.Label(win, text="Deckkraft:", bg=C["bg"], fg=C["text"],
                     font=("Segoe UI", 10, "bold")).grid(row=1, column=0, sticky="w", padx=10, pady=(6,4))
            opacity_var = tk.DoubleVar(value=self.tool_highlighter_opacity)
            op_scale = tk.Scale(win, from_=0.1, to=0.8, resolution=0.1,
                               orient=tk.HORIZONTAL, variable=opacity_var,
                               bg=C["bg"], fg=C["text"], troughcolor=C["canvas"],
                               highlightthickness=0, length=160, bd=0,
                               label="")
            op_scale.grid(row=1, column=1, columnspan=4, sticky="w", padx=10)
            op_lbl = tk.Label(win, textvariable=opacity_var, bg=C["bg"],
                             fg=C["accent"], font=("Segoe UI", 10, "bold"), width=3)
            op_lbl.grid(row=1, column=5, padx=2)
            btn_row = 2

        tk.Button(win, text="OK", font=("Segoe UI", 10, "bold"),
                 bg=C["green"], fg="#11111b", bd=0, padx=20, pady=4, cursor="hand2",
                 command=lambda: (
                     setattr(self, color_key, color_var.get()) if not is_highlighter else None,
                     setattr(self, width_key, width_var.get()) if (not is_highlighter and width_key and width_var is not None) else None,
                     setattr(self, "tool_highlighter_color", color_var.get()) if is_highlighter else None,
                     setattr(self, "tool_highlighter_opacity", opacity_var.get()) if is_highlighter else None,
                     setattr(self, "tool_arrow_head_len", head_len_var.get()) if is_arrow else None,
                     setattr(self, fill_key, fill_var.get()) if is_mask else None,
                     win.destroy())
                 ).grid(row=btn_row, column=0, columnspan=5, pady=(12,10))

    def _field_dialog(self, f):
        """Ein Dialog für Feldname + Typ (statt zwei hintereinander)."""
        win = tk.Toplevel(self.root)
        win.title("Feld-Eigenschaften")
        win.configure(bg=C["bg"])
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)
        
        # Zentrieren über dem Hauptfenster
        rx, ry = self.root.winfo_x(), self.root.winfo_y()
        rw, rh = self.root.winfo_width(), self.root.winfo_height()
        ww, wh = 320, 200
        win.geometry(f"{ww}x{wh}+{rx+rw//2-ww//2}+{ry+rh//2-wh//2}")
        
        result = {"name": "", "type": "text", "group": ""}
        
        tk.Label(win, text="Feldname:", bg=C["bg"], fg=C["text"],
                 font=("Segoe UI",10)).pack(pady=(12,2))
        name_var = tk.StringVar(value=f.label or f"Feld {len(self._current_fields())+1}")
        name_et = tk.Entry(win, textvariable=name_var, bg=C["canvas"], fg=C["text"],
                           font=("Segoe UI",11), insertbackground=C["text"],
                           relief=tk.FLAT, bd=4)
        name_et.pack(padx=20, pady=(0,8), fill=tk.X)
        name_et.select_range(0, tk.END)
        name_et.icursor(tk.END)
        name_et.focus_set()
        
        tk.Label(win, text="Feldtyp:", bg=C["bg"], fg=C["text"],
                 font=("Segoe UI",10)).pack(pady=(4,2))
        type_var = tk.StringVar(value="text")
        type_frame = tk.Frame(win, bg=C["bg"])
        type_frame.pack(pady=(0,4))
        for t_val, t_label in [("text", "📝 Text"), ("checkbox", "☑ Checkbox")]:
            tk.Radiobutton(type_frame, text=t_label, variable=type_var, value=t_val,
                          bg=C["bg"], fg=C["text"], selectcolor=C["canvas"],
                          activebackground=C["bg"], activeforeground=C["accent"],
                          font=("Segoe UI",10)).pack(side=tk.LEFT, padx=6)

        def on_ok():
            n = name_var.get().strip()
            if not n:
                messagebox.showwarning("Fehler", "Bitte Feldname eingeben.", parent=win)
                return
            result["name"] = n
            result["type"] = type_var.get()
            result["group"] = ""
            win.destroy()
        
        def on_cancel():
            win.destroy()
        
        btn_frame = tk.Frame(win, bg=C["bg"])
        btn_frame.pack(pady=(8,10))
        tk.Button(btn_frame, text="OK", command=on_ok,
                 bg=C["green"], fg="#11111b", font=("Segoe UI",10,"bold"),
                 bd=0, padx=20, pady=4, cursor="hand2").pack(side=tk.LEFT, padx=6)
        tk.Button(btn_frame, text="Abbrechen", command=on_cancel,
                 bg=C["red"], fg="#11111b", font=("Segoe UI",10,"bold"),
                 bd=0, padx=14, pady=4, cursor="hand2").pack(side=tk.LEFT, padx=6)
        
        win.bind("<Return>", lambda e: on_ok())
        win.bind("<Escape>", lambda e: on_cancel())
        self.root.wait_window(win)
        
        if not result["name"]: return None
        return (result["name"], result["type"], result["group"])

    # ─── Export ───────────────────────────────────────────────
    def _build_pdf(self) -> str:
        if not self.pdf_image: raise ValueError("Kein PDF")
        img = self.pdf_image.copy()

        # 1) Textmarker zuerst als Alpha-Overlay (muss vor allem anderen kommen,
        #    da es das Bild nach RGBA konvertiert)
        if self._current_highlighters():
            try:
                from PIL import Image as PILImage, ImageDraw as PILDraw, ImageColor
                pw, ph = img.width, img.height
                overlay = PILImage.new("RGBA", (pw, ph), (0, 0, 0, 0))
                od = PILDraw.Draw(overlay)
                for h in self._current_highlighters():
                    r, g, b = ImageColor.getrgb(h.color)[:3]
                    a = int(max(0, min(255, h.opacity * 255)))
                    od.rectangle([(h.x1, h.y1), (h.x2, h.y2)],
                                 fill=(r, g, b, a), width=0)
                if img.mode == "RGBA":
                    img = PILImage.alpha_composite(img, overlay)
                else:
                    img = img.convert("RGBA")
                    img = PILImage.alpha_composite(img, overlay)
            except Exception as e:
                print(f"Textmarker-PDF-Fehler: {e}")

        # Jetzt wieder ein ImageDraw aufmachen (auch auf RGBA)
        d = ImageDraw.Draw(img)

        for f in self._current_fields():
            if f.type == "text" and f.value:
                # Schrift in Punkt — aus Feld-Einstellung (sonst global)
                pt = max(6, min(36, getattr(f, 'font_size', self.font_size) or self.font_size))
                font = get_font(pt, self.font_name)
                fill_color = self.font_color if self.font_color else "#000000"
                # PIL-Offset: bbox[1] ist negativ — Abstand von draw_y bis Oberkante
                ref_bbox = font.getbbox('Ag')
                pil_offset = ref_bbox[1]
                text_h = ref_bbox[3] - ref_bbox[1]
                # Unten bündig: Unterkante Text = Unterkante Feld - 2px
                draw_y = f.y2 - text_h - 1 - pil_offset
                d.text((f.x1 + 2, draw_y), str(f.value), fill=fill_color, font=font)
            elif f.type == "checkbox" and f.value in (True,"True","true","1"):
                # ✓-Haken als Polygon — immer sichtbar, kein Font-Glyph nötig
                cx = (f.x1 + f.x2) // 2
                cy = (f.y1 + f.y2) // 2
                s = (f.y2 - f.y1) * 0.2  # Skalierung proportional zur Feldgröße
                s = max(3, min(10, s))
                # ✓ aus zwei Linien: unten-links → mitte → oben-rechts
                d.line([(cx - s*2, cy), (cx - s*0.5, cy + s*1.5), (cx + s*2, cy - s*1.5)],
                       fill=(0,0,0), width=max(2, int(s*0.6)))

        # Stempel auf PDF malen
        for s in self._current_stamps():
            try:
                stempel_img = self._stempel_bild(s, scale=1.0)
                # s.x/s.y sind bereits 300-DPI-Pixel — direkt übernehmen
                x = int(s.x)
                y = int(s.y)
                if stempel_img.mode == 'RGBA':
                    # Alpha-Kanal als Maske nutzen
                    img.paste(stempel_img, (x, y), stempel_img)
                else:
                    img.paste(stempel_img, (x, y))
            except Exception as e:
                print(f"Stempel-PDF-Fehler: {e}")

        # Pfeile auf PDF malen
        for a in self._current_arrows():
            try:
                self._draw_arrow_pdf(d, a)
            except Exception as e:
                print(f"Pfeil-PDF-Fehler: {e}")

        # Rechtecke auf PDF malen
        for r in self._current_rects():
            try:
                self._draw_rect_pdf(d, r)
            except Exception as e:
                print(f"Rechteck-PDF-Fehler: {e}")

        # Linien auf PDF malen
        for ln in self._current_lines():
            try:
                self._draw_line_pdf(d, ln)
            except Exception as e:
                print(f"Linien-PDF-Fehler: {e}")

        # Ellipsen auf PDF malen
        for el in self._current_ellipses():
            try:
                self._draw_ellipse_pdf(d, el)
            except Exception as e:
                print(f"Ellipsen-PDF-Fehler: {e}")

        # Masken auf PDF malen
        for m in self._current_masks():
            try:
                self._draw_mask_pdf(d, m)
            except Exception as e:
                print(f"Masken-PDF-Fehler: {e}")

        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        # PDF mag kein RGBA — zurück nach RGB
        if img.mode == "RGBA":
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3])
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")
        img.save(tmp.name, "PDF", resolution=300)
        return tmp.name

    def _save_pdf(self):
        if not self.pdf_image: return
        self._stop_typing()
        p = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF","*.pdf")],
                                         initialfile="ausgefuellt.pdf")
        if not p: return
        try: os.replace(self._build_pdf(), p); messagebox.showinfo("OK", f"PDF: {p}")
        except Exception as e: messagebox.showerror("Fehler", str(e))

    def _print_pdf(self):
        if not self.pdf_image: return
        self._stop_typing()
        try:
            p = self._build_pdf()
            if sys.platform == "linux": os.system(f"xdg-open '{p}' 2>/dev/null &")
            elif sys.platform == "win32": os.startfile(p)
            elif sys.platform == "darwin": os.system(f"open '{p}'")
        except Exception as e: messagebox.showerror("Fehler", str(e))

    def _scan_dialog(self):
        """Scannt ein Dokument und fügt es als neue Seite an das aktuelle PDF an."""
        if sys.platform != "linux":
            messagebox.showinfo("Scan", "Scan nur unter Linux verfügbar (SANE).\nNutze '📁 Bilddatei' als Alternative.")
            return
        # Dialog: scan oder foto?
        win = tk.Toplevel(self.root)
        win.title("Scan / Bild einfügen")
        win.configure(bg=C["bg"])
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)

        rx, ry = self.root.winfo_x(), self.root.winfo_y()
        rw, rh = self.root.winfo_width(), self.root.winfo_height()
        ww, wh = 320, 180
        win.geometry(f"{ww}x{wh}+{rx+rw//2-ww//2}+{ry+rh//2-wh//2}")

        tk.Label(win, text="Quelle auswählen:", bg=C["bg"], fg=C["text"],
                font=("Segoe UI", 11, "bold")).pack(pady=(16, 10))

        def _scan():
            win.destroy()
            self._scan_from_scanner()

        def _from_file():
            win.destroy()
            self._scan_from_file()

        btn_frame = tk.Frame(win, bg=C["bg"])
        btn_frame.pack(pady=6)
        tk.Button(btn_frame, text="📷 Scanner", command=_scan,
                 bg=C["accent"], fg="#11111b", font=("Segoe UI", 10, "bold"),
                 bd=0, padx=20, pady=6, cursor="hand2").pack(side=tk.LEFT, padx=6)
        tk.Button(btn_frame, text="📁 Bilddatei", command=_from_file,
                 bg=C["yellow"], fg="#11111b", font=("Segoe UI", 10, "bold"),
                 bd=0, padx=20, pady=6, cursor="hand2").pack(side=tk.LEFT, padx=6)

        tk.Button(win, text="Abbrechen", command=win.destroy,
                 bg=C["red"], fg="#11111b", font=("Segoe UI", 9, "bold"),
                 bd=0, padx=20, pady=4, cursor="hand2").pack(pady=(10, 0))
        win.bind("<Escape>", lambda e: win.destroy())

    def _scan_from_scanner(self):
        """Startet einen Scanvorgang und fügt das Ergebnis als neue Seite ein.
        Versucht verschiedene SANE-Backends (scanimage, python-sane, sudo)."""
        import subprocess, tempfile, os, shutil

        # Prüfen ob scanimage existiert
        scanimage_path = shutil.which("scanimage")
        if not scanimage_path:
            messagebox.showwarning("SANE fehlt",
                "Scan-Programm 'scanimage' nicht gefunden.\n"
                "Installiere: sudo apt install sane-utils\n"
                "Danach evtl.: sudo sed -i 's/^# grundlag/grundlag/' /etc/sane.d/genesys.conf\n"
                "Alternativ '📁 Bilddatei' nutzen.")
            return

        self._status_text("Scanne... bitte warten")
        self.root.update()

        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp.close()

        # Versuche 1: scanimage direkt
        try:
            r = subprocess.run(
                [scanimage_path, "--resolution", "300", "--format=png",
                 "-o", tmp.name],
                capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                scan_img = Image.open(tmp.name)
                self._add_image_as_page(scan_img)
                try: os.unlink(tmp.name)
                except: pass
                return
            error_msg = r.stderr
        except Exception as e:
            error_msg = str(e)

        # Versuche 2: mit sudo (falls Scanner keine User-Rechte hat)
        try:
            r = subprocess.run(
                ["sudo", "-n", scanimage_path, "--resolution", "300",
                 "--format=png", "-o", tmp.name],
                capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                scan_img = Image.open(tmp.name)
                self._add_image_as_page(scan_img)
                self._status_text("Scan erfolgreich (mit sudo)")
                try: os.unlink(tmp.name)
                except: pass
                return
        except:
            pass

        # Beide fehlgeschlagen
        messagebox.showerror("Scan-Fehler",
            f"Scanner reagiert nicht.\n\n"
            f"Fehler: {error_msg}\n\n"
            f"Tipps:\n"
            f"1. sudo apt install sane-utils\n"
            f"2. scanimage -L im Terminal testen\n"
            f"3. sudo scanimage -L (wenn User keine Rechte hat)\n"
            f"4. Oder nutze '📁 Bilddatei'")

    def _scan_from_file(self):
        """Öffnet einen Bild-Dateidialog und fügt das Bild als neue Seite ein."""
        p = filedialog.askopenfilename(
            title="Bild auswählen",
            filetypes=[("Bilder", "*.png *.jpg *.jpeg *.tiff *.bmp *.webp"),
                       ("Alle", "*.*")])
        if not p:
            return
        try:
            from PIL import Image
            img = Image.open(p)
            self._add_image_as_page(img)
        except Exception as e:
            messagebox.showerror("Fehler", f"Bild konnte nicht geladen werden:\n{e}")

    def _add_image_as_page(self, img):
        """Fügt ein PIL-Bild als neue Seite hinten ans aktuelle PDF an."""
        from PIL import Image
        # Auf 300 DPI skalieren (A4 ~ 2480x3508 px)
        max_w, max_h = 2480, 3508
        w, h = img.size
        scale = min(max_w / w, max_h / h, 1.0)
        if scale < 1.0:
            new_w, new_h = int(w * scale), int(h * scale)
            img = img.resize((new_w, new_h), Image.LANCZOS)

        # Bild im RGB-Format
        if img.mode != "RGB":
            img = img.convert("RGB")

        # Bisheriges PDF (Seite 0) + neue Seite als zweites Bild
        if not self.pdf_image:
            # Noch kein PDF geladen – Bild als neue Seite öffnen
            self.pdf_image = img
            self.page_count = 1
            self.current_page = 0
            self.fields = {"0": []}
            self.stamps = {"0": []}
            self.arrows = {"0": []}
            self.rects = {"0": []}
            self.lines = {"0": []}
            self.ellipses = {"0": []}
            self.masks = {"0": []}
            self.highlighters = {"0": []}
            self.pdf_path = None
            self._fit_zoom()
            self._render()
            self._status()
            self._status_text("Bild als neue Seite geladen")
            return

        # Es gibt schon ein PDF – neue Seite dranhängen
        # Aktuelle Seite merken
        old_page = self.current_page
        old_fields = dict(self.fields)
        old_stamps = dict(self.stamps)
        old_arrows = dict(self.arrows)
        old_rects = dict(self.rects)
        old_lines = dict(self.lines)
        old_ellipses = dict(self.ellipses)
        old_masks = dict(self.masks)
        old_highlighters = dict(self.highlighters)

        # Neue Seite als Index neben dem geladenen PDF
        new_idx = old_page + 1  # nach aktueller Seite einfügen

        # Verschieben: alles ab new_idx um 1 nach hinten
        def _shift(d, start):
            items = sorted(d.items(), key=lambda x: int(x[0]))
            new_d = {}
            for k, v in items:
                k_int = int(k)
                if k_int >= new_idx:
                    new_d[str(k_int + 1)] = v
                else:
                    new_d[k] = v
            return new_d

        self.fields = _shift(old_fields, new_idx)
        self.stamps = _shift(old_stamps, new_idx)
        self.arrows = _shift(old_arrows, new_idx)
        self.rects = _shift(old_rects, new_idx)
        self.lines = _shift(old_lines, new_idx)
        self.ellipses = _shift(old_ellipses, new_idx)
        self.masks = _shift(old_masks, new_idx)
        self.highlighters = _shift(old_highlighters, new_idx)

        # Neue Seite einfügen
        key = str(new_idx)
        self.fields[key] = []
        self.stamps[key] = []
        self.arrows[key] = []
        self.rects[key] = []
        self.lines[key] = []
        self.ellipses[key] = []
        self.masks[key] = []
        self.highlighters[key] = []

        self.page_count += 1

        # Alte Bilder als Liste speichern (page_images)
        if not hasattr(self, "page_images"):
            self.page_images = {str(old_page): self.pdf_image.copy()}
        self.page_images[key] = img.copy()

        # Zur neuen Seite springen
        self.current_page = new_idx
        self.pdf_image = img.copy()
        self._fit_zoom()
        self._render()
        self._status()
        self._status_text(f"Seite {new_idx + 1} hinzugefügt (Scan/Bild)")

    def _reset(self):
        self._stop_typing()
        self._undo_snapshot()
        for f in self._current_fields(): f.value = ""
        self._render(); self._status()

    def _mw(self, e): self._do_zoom(1.1 if e.delta > 0 else 0.9)

    def _current_stamps(self):
        """Gibt die Stempel-Liste der aktuellen Seite zurück."""
        return self.stamps.get(str(self.current_page), [])

    def _current_arrows(self):
        """Gibt die Pfeil-Liste der aktuellen Seite zurück."""
        return self.arrows.get(str(self.current_page), [])

    def _current_rects(self):
        """Gibt die Rechteck-Liste der aktuellen Seite zurück."""
        return self.rects.get(str(self.current_page), [])

    def _current_lines(self):
        """Gibt die Linien-Liste der aktuellen Seite zurück."""
        return self.lines.get(str(self.current_page), [])

    def _current_ellipses(self):
        """Gibt die Ellipsen-Liste der aktuellen Seite zurück."""
        return self.ellipses.get(str(self.current_page), [])

    def _current_masks(self):
        """Gibt die Masken-Liste der aktuellen Seite zurück."""
        return self.masks.get(str(self.current_page), [])

    def _current_highlighters(self):
        """Gibt die Textmarker-Liste der aktuellen Seite zurück."""
        return self.highlighters.get(str(self.current_page), [])

    @staticmethod
    def _point_near_line(px, py, x1, y1, x2, y2, tol=15.0):
        """Prueft ob Punkt (px,py) nah an der Strecke (x1,y1)->(x2,y2) liegt."""
        import math
        dx, dy = x2 - x1, y2 - y1
        if abs(dx) < 0.5 and abs(dy) < 0.5:
            return math.hypot(px - x1, py - y1) <= tol
        t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / (dx*dx + dy*dy)))
        nx = x1 + t * dx
        ny = y1 + t * dy
        return math.hypot(px - nx, py - ny) <= tol

    def _draw_rect(self, r):
        """Zeichnet ein Rechteck auf dem Canvas."""
        z, ox, oy = self.zoom, self.ox, self.oy
        x1 = ox + int(r.x1 * z)
        y1 = oy + int(r.y1 * z)
        x2 = ox + int(r.x2 * z)
        y2 = oy + int(r.y2 * z)
        line_w = max(1, int(r.width * z))
        self.cv.create_rectangle(x1, y1, x2, y2,
                                 outline=r.color, fill=r.fill or "", width=line_w, tags="f")

    def _draw_rect_pdf(self, d, r):
        """Malt ein Rechteck auf das 300-DPI-PDF-Bild (ImageDraw)."""
        d.rectangle([(r.x1, r.y1), (r.x2, r.y2)],
                    outline=r.color, fill=r.fill, width=max(1, r.width))

    @staticmethod
    def _snap_line(px, py, x1, y1, threshold=15):
        """Rastet (px,py) auf waagerecht oder senkrecht relativ zu (x1,y1) ein.
        threshold: Winkel-Toleranz in Grad (0=exakt, 45=egal).
        Gibt eingeschnapptes (px, py) zurück.
        """
        import math
        dx = px - x1
        dy = py - y1
        if abs(dx) < 2 and abs(dy) < 2:
            return int(px), int(py)
        angle = abs(math.degrees(math.atan2(dy, dx)))
        # Waagerecht: Winkel nahe 0° oder 180°
        if angle <= threshold or angle >= 180 - threshold:
            return int(px), y1  # y beibehalten → waagerecht
        # Senkrecht: Winkel nahe 90° 
        if abs(angle - 90) <= threshold:
            return x1, int(py)  # x beibehalten → senkrecht
        return int(px), int(py)

    def _draw_line(self, ln):
        """Zeichnet eine Linie auf dem Canvas."""
        z, ox, oy = self.zoom, self.ox, self.oy
        x1 = ox + int(ln.x1 * z)
        y1 = oy + int(ln.y1 * z)
        x2 = ox + int(ln.x2 * z)
        y2 = oy + int(ln.y2 * z)
        line_w = max(1, int(ln.width * z))
        self.cv.create_line(x1, y1, x2, y2,
                           fill=ln.color, width=line_w, tags="f")

    def _draw_line_pdf(self, d, ln):
        """Malt eine Linie auf das 300-DPI-PDF-Bild (ImageDraw)."""
        pw = max(1, ln.width)
        d.line([(ln.x1, ln.y1), (ln.x2, ln.y2)],
               fill=ln.color, width=pw)

    def _draw_ellipse(self, el):
        """Zeichnet eine Ellipse auf dem Canvas."""
        z, ox, oy = self.zoom, self.ox, self.oy
        x1 = ox + int(el.x1 * z)
        y1 = oy + int(el.y1 * z)
        x2 = ox + int(el.x2 * z)
        y2 = oy + int(el.y2 * z)
        line_w = max(1, int(el.width * z))
        self.cv.create_oval(x1, y1, x2, y2,
                           outline=el.color, fill=el.fill or "", width=line_w, tags="f")

    def _draw_ellipse_pdf(self, d, el):
        """Malt eine Ellipse auf das 300-DPI-PDF-Bild (ImageDraw)."""
        d.ellipse([(el.x1, el.y1), (el.x2, el.y2)],
                  outline=el.color, fill=el.fill, width=max(1, el.width))

    def _draw_mask(self, m):
        """Zeichnet eine Maske auf dem Canvas (weiß gefülltes Rechteck)."""
        z, ox, oy = self.zoom, self.ox, self.oy
        x1 = ox + int(m.x1 * z)
        y1 = oy + int(m.y1 * z)
        x2 = ox + int(m.x2 * z)
        y2 = oy + int(m.y2 * z)
        line_w = max(1, int(m.width * z))
        self.cv.create_rectangle(x1, y1, x2, y2,
                                outline="", fill=m.fill, width=0, tags="f")

    def _draw_mask_pdf(self, d, m):
        """Malt eine Maske auf das 300-DPI-PDF-Bild (ImageDraw)."""
        d.rectangle([(m.x1, m.y1), (m.x2, m.y2)],
                    outline="", fill=m.fill, width=0)

    @staticmethod
    def _lighten_color(hex_color, opacity):
        """Mischt eine hex-Farbe mit Weiß nach opacity (0=weiß, 1=pur).
        tkinter < 8.7 unterstützt kein #AARRGGBB, daher mische ich die Farbe."""
        try:
            from PIL import ImageColor
            r, g, b = ImageColor.getrgb(hex_color)[:3]
            mix = max(0.0, min(1.0, opacity))
            # opacity 0.3 = 70% Weiß + 30% Farbe
            nr = int(r * mix + 255 * (1 - mix))
            ng = int(g * mix + 255 * (1 - mix))
            nb = int(b * mix + 255 * (1 - mix))
            return f"#{nr:02x}{ng:02x}{nb:02x}"
        except:
            return hex_color

    def _draw_highlighter(self, h):
        """Zeichnet einen Textmarker auf dem Canvas — stipple-Raster lässt Hintergrund durchscheinen."""
        z, ox, oy = self.zoom, self.ox, self.oy
        x1 = ox + int(h.x1 * z)
        y1 = oy + int(h.y1 * z)
        x2 = ox + int(h.x2 * z)
        y2 = oy + int(h.y2 * z)
        fill_color = self._lighten_color(h.color, h.opacity)
        self.cv.create_rectangle(x1, y1, x2, y2,
                                 fill=fill_color, outline="",
                                 stipple="gray50", width=0, tags="f")

    def _draw_highlighter_pdf(self, d, h):
        """Malt einen Textmarker auf das 300-DPI-PDF-Bild.
        PIL ImageDraw unterstützt kein RGBA-Fill in Rechtecken direkt.
        Wir zeichnen mit fester Deckkraft auf einem separaten Layer und
        komponieren das Bild über eine Paste mit Alpha."""
        from PIL import Image, ImageDraw
        pw, ph = self.pdf_image.width, self.pdf_image.height
        # Ein semi-transparentes Overlay-Layer erzeugen
        overlay = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        try:
            from PIL import ImageColor
            r, g, b = ImageColor.getrgb(h.color)
            a = int(max(0, min(255, h.opacity * 255)))
            od.rectangle([(h.x1, h.y1), (h.x2, h.y2)],
                         fill=(r, g, b, a), width=0)
            # Overlay auf das PDF-Bild pasten
            if self.pdf_image.mode == "RGBA":
                self.pdf_image = Image.alpha_composite(self.pdf_image, overlay)
            else:
                self.pdf_image = self.pdf_image.convert("RGBA")
                self.pdf_image = Image.alpha_composite(self.pdf_image, overlay)
        except:
            # Fallback: einfaches Füllen ohne Alpha
            od.rectangle([(h.x1, h.y1), (h.x2, h.y2)],
                         fill=h.color, width=0)
            if self.pdf_image.mode == "RGBA":
                self.pdf_image = Image.alpha_composite(self.pdf_image, overlay)
            else:
                self.pdf_image = self.pdf_image.convert("RGBA")
                self.pdf_image = Image.alpha_composite(self.pdf_image, overlay)

    def _draw_arrow(self, a):
        """Zeichnet einen Pfeil auf dem Canvas — auf Seitenbereich begrenzt."""
        z, ox, oy = self.zoom, self.ox, self.oy
        x1 = ox + int(a.x1 * z)
        y1 = oy + int(a.y1 * z)
        x2 = ox + int(a.x2 * z)
        y2 = oy + int(a.y2 * z)
        head_len = max(3, int(a.head_len * z))
        line_w = max(1, int(a.width * z))
        # Auf Canvas-Seite clippen (innerhalb des PDF-Bereichs)
        if self.pdf_image:
            pw = int(self.pdf_image.width * z)
            ph = int(self.pdf_image.height * z)
            x1 = max(ox, min(ox + pw, x1))
            y1 = max(oy, min(oy + ph, y1))
            x2 = max(ox, min(ox + pw, x2))
            y2 = max(oy, min(oy + ph, y2))
        self._draw_arrow_line(self.cv, x1, y1, x2, y2, a.color, width=line_w, head_len=head_len, tags="f")

    def _draw_arrow_preview(self, x1, y1, x2, y2):
        """Zeichnet eine Pfeil-Vorschau während des Ziehens (Drag)."""
        self._draw_arrow_line(self.cv, x1, y1, x2, y2, C["accent"], width=2, head_len=18, dash=(4, 4), tags="drag")

    def _draw_arrow_pdf(self, d, a):
        """Malt einen Pfeil auf das 300-DPI-PDF-Bild (ImageDraw) — auf Seitenbereich begrenzt."""
        pw, ph = self.pdf_image.width, self.pdf_image.height
        x1 = max(0, min(pw, a.x1))
        y1 = max(0, min(ph, a.y1))
        x2 = max(0, min(pw, a.x2))
        y2 = max(0, min(ph, a.y2))
        self._draw_arrow_line_pil(d, x1, y1, x2, y2, a.color,
                                  width=max(1, a.width * 2),
                                  head_len=max(10, a.head_len * 2))

    @staticmethod
    def _draw_arrow_line(cv, x1, y1, x2, y2, color, width=2, tags="f", dash=None, head_len=18):
        """Zeichnet eine Pfeillinie + Pfeilspitze auf dem tkinter Canvas."""
        from math import atan2, cos, sin, pi
        dx, dy = x2 - x1, y2 - y1
        if abs(dx) < 2 and abs(dy) < 2:
            cv.create_line(x1, y1, x2, y2, fill=color, width=width, tags=tags)
            return
        angle = atan2(dy, dx)
        # Pfeil-Schaft — endet kurz vor der Spitze (sonst ragt die Linie durch)
        shrink = head_len * 0.4
        lx2 = x2 - shrink * cos(angle)
        ly2 = y2 - shrink * sin(angle)
        kw = {"fill": color, "width": width, "tags": tags}
        if dash:
            kw["dash"] = dash
        cv.create_line(x1, y1, lx2, ly2, **kw)
        # Pfeilspitze (Dreieck)
        head_angle = pi / 6  # 30 Grad
        p1x = x2 - head_len * cos(angle - head_angle)
        p1y = y2 - head_len * sin(angle - head_angle)
        p2x = x2 - head_len * cos(angle + head_angle)
        p2y = y2 - head_len * sin(angle + head_angle)
        cv.create_polygon(x2, y2, p1x, p1y, p2x, p2y,
                          fill=color, outline=color, width=1, tags=tags)

    @staticmethod
    def _draw_arrow_line_pil(d, x1, y1, x2, y2, color, width=4, head_len=30):
        """Malt eine Pfeillinie + Pfeilspitze auf PIL ImageDraw."""
        from math import atan2, cos, sin, pi
        dx, dy = x2 - x1, y2 - y1
        if abs(dx) < 2 and abs(dy) < 2:
            d.line([(x1, y1), (x2, y2)], fill=color, width=width)
            return
        angle = atan2(dy, dx)
        # Schaft — endet kurz vor der Spitze
        shrink = head_len * 0.4
        lx2 = x2 - shrink * cos(angle)
        ly2 = y2 - shrink * sin(angle)
        d.line([(x1, y1), (lx2, ly2)], fill=color, width=width)
        head_angle = pi / 6
        p1 = (x2 - head_len * cos(angle - head_angle),
              y2 - head_len * sin(angle - head_angle))
        p2 = (x2 - head_len * cos(angle + head_angle),
              y2 - head_len * sin(angle + head_angle))
        d.polygon([(x2, y2), p1, p2], fill=color, outline=color)

    def _stempel_bild(self, s, scale=1.0):
        """Erzeugt ein PIL-Image des Stempels (in 300-DPI-Auflösung mit optionalem Skalierungsfaktor)."""
        pt = max(12, int(48 * scale))
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", pt)
        except:
            font = ImageFont.load_default()

        # Text-Größe ermitteln
        bbox = font.getbbox(s.text)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        pad = int(12 * scale)
        w = tw + pad * 2
        h = th + pad * 2

        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        # Doppelter Rahmen
        for off, width in [(0, 3), (3, 1)]:
            d.rectangle([off, off, w - off - 1, h - off - 1],
                       outline=s.color, width=max(1, int(width * scale)))

        # Text zentriert
        tx = (w - tw) // 2
        ty = (h - th) // 2 - bbox[1]
        d.text((tx, ty), s.text, fill=s.color, font=font)

        # Linie unter dem Text
        ly = ty + th + int(4 * scale)
        d.line([pad, ly, w - pad, ly], fill=s.color, width=max(1, int(2 * scale)))

        # Rotation
        if s.rotation:
            img = img.rotate(s.rotation, expand=True, fillcolor=(0, 0, 0, 0))

        return img

    def _draw_stempel(self, s):
        """Zeichnet einen Stempel auf dem Canvas — skaliert mit Zoom."""
        z = self.zoom
        # 300-DPI-Basis-Bild erzeugen
        base = self._stempel_bild(s, scale=1.0)
        # Auf Zoom-Größe runterskalieren (wie pdf_image auch)
        bw, bh = base.size
        sw, sh = max(1, int(bw * z)), max(1, int(bh * z))
        img = base.resize((sw, sh), Image.LANCZOS)
        # Position: s.x/s.y sind 300-DPI-Koordinaten
        x = self.ox + int(s.x * z)
        y = self.oy + int(s.y * z)
        self._stempel_tk[s] = ImageTk.PhotoImage(img)
        self.cv.create_image(x, y, anchor=tk.NW, image=self._stempel_tk[s], tags="f")

    def _stempel_dialog(self, x, y):
        """Zeigt Stempel-Auswahl und platziert einen Stempel auf der aktuellen Seite."""
        win = tk.Toplevel(self.root)
        win.title("Stempel auswählen")
        win.configure(bg=C["bg"])
        win.transient(self.root)
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.update_idletasks()  # Fenster sichtbar machen
        win.grab_set()

        rx, ry = self.root.winfo_x(), self.root.winfo_y()
        rw, rh = self.root.winfo_width(), self.root.winfo_height()
        ww, wh = 340, 300
        win.geometry(f"{ww}x{wh}+{rx+rw//2-ww//2}+{ry+rh//2-wh//2}")

        tk.Label(win, text="Stempel auswählen:", bg=C["bg"], fg=C["text"],
                font=("Segoe UI",11,"bold")).pack(pady=(12,6))

        frame = tk.Frame(win, bg=C["bg"])
        frame.pack(padx=12, fill=tk.BOTH, expand=True)

        def platziere(text, color):
            self._undo_snapshot()
            key = str(self.current_page)
            if key not in self.stamps:
                self.stamps[key] = []
            self.stamps[key].append(Stamp(x=x, y=y, text=text, color=color))
            win.destroy()
            self._render()
            self._status()

        for text, color, name in Stamp.STANDARD_STEMPEL:
            btn_frame = tk.Frame(frame, bg=color, bd=1, relief=tk.RAISED, cursor="hand2")
            btn_frame.pack(fill=tk.X, pady=3)
            btn_frame.bind("<Button-1>", lambda e, t=text, c=color: platziere(t, c))

            # Vorschau-Stempel
            preview = tk.Label(btn_frame, text=f"  {text}  ", bg=color, fg="white",
                              font=("Courier",14,"bold"), padx=6, pady=4)
            preview.pack(side=tk.LEFT)
            preview.bind("<Button-1>", lambda e, t=text, c=color: platziere(t, c))

            name_lbl = tk.Label(btn_frame, text=f"({name})", bg=color, fg="white",
                               font=("Segoe UI",8))
            name_lbl.pack(side=tk.RIGHT, padx=8)
            name_lbl.bind("<Button-1>", lambda e, t=text, c=color: platziere(t, c))

        tk.Button(win, text="Abbrechen", command=win.destroy,
                 bg=C["red"], fg="#11111b", font=("Segoe UI",9,"bold"),
                 bd=0, padx=20, pady=4, cursor="hand2").pack(pady=(8,10))
        win.bind("<Escape>", lambda e: win.destroy())

    def _mouse_help(self):
        """Gibt kontextabhängige Maus-Hilfe für die untere Statusleiste."""
        if self.selected_tool and self.selected_tool != "Pfeil":
            return f"🛠️ Werkzeug: {self.selected_tool} — auf Canvas klicken und ziehen zum Zeichnen"
        if self.mode == "fill":
            return "🖱️ Linke Taste: Text eingeben oder Häkchen setzen | Rechte Taste: Bild verschieben | Mausrad: Zoom"
        else:  # edit
            return "🖱️ Links: Feld anlegen | Strg+Klick: Feld verschieben | Mitte: Feld verschieben | Rechts: Bild verschieben | Rad: Zoom | Rechts auf Feld: Löschen"

    def _exit_app(self):
        """Beendet die App sauber."""
        try:
            self.root.destroy()
        except:
            pass
        try:
            self.root.quit()
        except:
            pass

    def _status_text(self, msg):
        """Kurztext in die Statusleiste (überschreibt sich nach 3s)."""
        self.sb.config(text=msg)
        self.root.after(3000, self._status)

    def _status(self):
        pdf = os.path.basename(self.pdf_path) if self.pdf_path else "Kein PDF"
        mt = "EDITOR" if self.mode=="edit" else "AUSFUELLEN"
        cur = self._current_fields()
        fc = len(cur)
        stamps = self._current_stamps()
        sc = len(stamps)
        arrows = self._current_arrows()
        ac = len(arrows)
        rects = self._current_rects()
        rc = len(rects)
        sel = f" | {self.selected.label}" if self.selected else ""
        tpl = f" | Vorlage:{self.template_name}" if self.template_name else ""
        proj = f" | Projekt:{self.project_name}" if self.project_name else ""
        akt = f" | {self.active_field.label}" if self.active_field else ""
        fr = " | Rahmen AUS" if not self.show_frames else ""
        pages = f" | Seite {self.current_page+1}/{self.page_count}" if self.page_count > 1 else ""
        stempel = f" | {sc} Stempel" if sc else ""
        pfeile = f" | {ac} Pfeil(e)" if ac else ""
        rechtecke = f" | {rc} Rechteck(e)" if rc else ""
        self.sb.config(text=f"{mt} | {pdf}{tpl}{proj} | {fc} Feld(er){stempel}{pfeile}{rechtecke}{sel}{akt}{fr}{pages} | Raster {self.grid_size}px")
        # Maus-Hilfe aktualisieren
        if hasattr(self, 'sb_mouse'):
            self.sb_mouse.config(text=self._mouse_help())
        # Seiten-Label aktualisieren
        if hasattr(self, 'page_label'):
            if self.page_count > 1:
                self.page_label.config(text=f"Seite {self.current_page+1}/{self.page_count}")
            else:
                self.page_label.config(text="")


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()

if __name__ == "__main__":
    main()
