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
    @property
    def w(self): return self.x2 - self.x1
    @property
    def h(self): return self.y2 - self.y1
    def contains(self, px, py): return self.x1 <= px <= self.x2 and self.y1 <= py <= self.y2
    def to_dict(self):
        return {"label": self.label, "type": self.type, "x": self.x1,
                "y": self.y1, "w": self.w, "h": self.h, "group": self.group}
    @classmethod
    def from_dict(cls, d):
        pos = d.get("pos", d)
        x = pos.get("x", pos.get("x1", 0))
        y = pos.get("y", pos.get("y1", 0))
        w = pos.get("w", 100)
        h = pos.get("h", d.get("h", 20))
        return cls(x1=x, y1=y, x2=x+w, y2=y+h,
                   label=d.get("label", d.get("name", "")), ftype=d.get("type", "text"))


class Stamp:
    """Ein Stempel auf dem PDF (GEPRÜFT, GENEHMIGT, etc.)."""
    STANDARD_STEMPEL = [
        ("GEPRÜFT", "#2ecc71", "grün"),
        ("GENEHMIGT", "#2196F3", "blau"),
        ("FREIGEGEBEN", "#4CAF50", "grün"),
        ("ABGELEHNT", "#e74c3c", "rot"),
        ("GESPERRT", "#ff9800", "orange"),
        ("NICHT GEPRÜFT", "#9e9e9e", "grau"),
    ]

    def __init__(self, x=0, y=0, text="GEPRÜFT", color="#2ecc71", rotation=15):
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

        # ─── Toolbox links ─────────────────────────────────────
        self.toolbox = tk.Frame(self.root, bg=C["bg"], width=58)
        self.toolbox.pack(side=tk.LEFT, fill=tk.Y, padx=(4,0), pady=4)
        self.toolbox.pack_propagate(False)

        werkzeuge = [
            ("⬆️", "Pfeil", "Auswahl (Default)"),
            ("╱", "Linie", "Linie zeichnen"),
            ("▭", "Rechteck", "Rechteck zeichnen"),
            ("◯", "Ellipse", "Kreis/Ellipse zeichnen"),
            ("▣", "Maske", "Bereich maskieren"),
            ("🖼️", "Bild", "Bild einfügen"),
            ("🕹️", "Stempel", "Stempel aufdrücken"),
        ]
        self._tool_buttons = {}
        for icon, name, tip in werkzeuge:
            btn = tk.Button(self.toolbox, text=icon, font=("Segoe UI",14),
                          bg=C["bg"], fg=C["text"],
                          activebackground=C["accent"], activeforeground="#11111b",
                          relief=tk.FLAT, bd=1, pady=4, padx=2,
                          cursor="hand2", width=3,
                          command=lambda n=name: self._set_tool(n))
            btn.pack(pady=1, padx=2, fill=tk.X)
            self._tool_buttons[name] = btn
            self._attach_tooltip(btn, tip)

        # Toolbox: Beenden-Button ganz unten
        self.toolbox_padding = tk.Frame(self.toolbox, bg=C["bg"])
        self.toolbox_padding.pack(fill=tk.BOTH, expand=True)
        self.btn_exit = tk.Button(self.toolbox, text="❌", font=("Segoe UI",14),
                                bg=C["red"], fg="#11111b",
                                activebackground=C["red"], activeforeground="#11111b",
                                relief=tk.RAISED, bd=2, pady=4, padx=2,
                                cursor="hand2", width=3, command=self.root.quit)
        self.btn_exit.pack(side=tk.BOTTOM, pady=(0,4), padx=2)
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
        self.root.bind("<Escape>", lambda e: self._stop_typing())
        # Popup-Menüs bei Klick irgendwo schließen
        self.root.bind("<Button-1>", self._close_menus, add="+")
        self.root.bind("<Button-3>", self._close_menus, add="+")

    def _set_tool(self, name):
        """Wählt ein Werkzeug aus der Toolbox."""
        self.selected_tool = name
        # Buttons visuell hervorheben
        for n, btn in self._tool_buttons.items():
            if n == name:
                btn.configure(bg=C["accent"], fg="#11111b", relief=tk.RAISED)
            else:
                btn.configure(bg=C["bg"], fg=C["text"], relief=tk.FLAT)
        self._status()

    def _set_height_dialog(self):
        from tkinter import simpledialog
        val = simpledialog.askinteger("Rahmenhöhe",
            f"Aktuell: {self.frame_height} px\nNeue Höhe (10-500):",
            initialvalue=self.frame_height, minvalue=10, maxvalue=500,
            parent=self.root)
        if val is not None:
            old_h = self.frame_height
            self.frame_height = val
            # Änderungsdelta für jedes Feld: Oberkante wandert nach oben/unten
            for f in self._current_fields():
                f.y1 = f.y2 - self.frame_height  # wächst nach oben
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
        self._stempel_images = {}
        self._stempel_tk = {}
        self.current_page = 0
        self.page_count = 0
        self.selected = None
        self.template_path = self.template_name = None
        self.project_path = self.project_name = None
        self._render()
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
                self.toolbox_padding.configure(bg=C["bg"])
                for n, btn in self._tool_buttons.items():
                    if n == self.selected_tool:
                        btn.configure(bg=C["accent"], fg="#11111b")
                    else:
                        btn.configure(bg=C["bg"], fg=C["text"])
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

    def _set_mode(self, mode):
        self._stop_typing()
        self.mode = mode
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
            self._fit_zoom(); self._render(); self._status()
        except Exception as e: messagebox.showerror("Fehler", f"PDF: {e}")

    # ─── Vorlage ──────────────────────────────────────────────
    def _load_template(self):
        p = filedialog.askopenfilename(title="Vorlage", filetypes=[("JSON","*.json"),("*","*.*")])
        if not p: return
        try:
            with open(p, encoding='utf-8') as f: data = json.load(f)
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
            json.dump({"name": name, "fields": {k: [fld.to_dict() for fld in v] for k, v in self.fields.items() if v}},
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

        # Wert anzeigen — Schrift aus Einstellung
        if f.value and f.type == "text":
            pt = max(6, min(36, self.font_size))
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
            }
            fn = fn_map.get(self.font_name, "Liberation Sans")
            self.cv.create_text(x1+3, y_base, anchor=tk.SW, text=txt, fill=fc,
                               font=(fn,fs), tags="f")

        # Checkbox/Radio
        if f.type == "checkbox" and f.value in (True,"True","true","1"):
            cx, cy = (x1+x2)//2, (y1+y2)//2
            sz = max(6, int((y2 - y1) * 0.8))
            self.cv.create_text(cx, cy, text="✓", fill="#000",
                               font=("Segoe UI",sz,"bold"), tags="f")
        if f.type == "radio" and f.value in (True,"True","true","1"):
            cx, cy = (x1+x2)//2, (y1+y2)//2
            r = max(2, int(self.font_size * z * 0.4))
            self.cv.create_oval(cx-r, cy-r, cx+r, cy+r, fill="#000", tags="f")

    # ─── Maus ─────────────────────────────────────────────────
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
            self._set_tool("Pfeil")  # zurück zu Pfeil
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
                    f.value = not (f.value in (True, "True", "true", "1"))
                    self._render()
                    self._status()
                elif f.type == "radio":
                    for o in self._current_fields():
                        if o.type == "radio" and o.group == f.group:
                            o.value = False
                    f.value = True
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
                f.label, f.type, f.group = result
                self._current_fields().append(f)
                self.selected = f
                self._render()
                self._status()
        elif dm == "move":
            if hasattr(self, '_mv_field') and self._mv_field:
                self._mv_field = None
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
        """Rechtsklick: Löschen (Edit auf Feld) oder Panning starten"""
        if self.panning:
            return
        px, py = self._ic(e)
        f = self._find(px, py)
        if self.mode == "edit" and f:
            if messagebox.askyesno("Löschen", f"'{f.label}' löschen?"):
                self._current_fields().remove(f)
                if self.selected == f:
                    self.selected = None
                self._render()
                self._status()
        else:
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
        for t_val, t_label in [("text", "📝 Text"), ("checkbox", "☑ Checkbox"), ("radio", "◉ Radio")]:
            tk.Radiobutton(type_frame, text=t_label, variable=type_var, value=t_val,
                          bg=C["bg"], fg=C["text"], selectcolor=C["canvas"],
                          activebackground=C["bg"], activeforeground=C["accent"],
                          font=("Segoe UI",10)).pack(side=tk.LEFT, padx=6)
        
        # Gruppenname (nur für radio)
        group_frame = tk.Frame(win, bg=C["bg"])
        group_lbl = tk.Label(group_frame, text="Gruppe:", bg=C["bg"], fg=C["text"],
                             font=("Segoe UI",10))
        group_lbl.pack(side=tk.LEFT, padx=(20,4))
        group_var = tk.StringVar(value="gruppe1")
        group_et = tk.Entry(group_frame, textvariable=group_var, bg=C["canvas"], fg=C["text"],
                            font=("Segoe UI",11), insertbackground=C["text"],
                            relief=tk.FLAT, bd=4)
        group_et.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,20))
        group_frame.pack(fill=tk.X, pady=(0,8))
        group_frame.pack_forget()  # erstmal versteckt
        
        def on_type_change(*args):
            if type_var.get() == "radio":
                group_frame.pack(fill=tk.X, pady=(0,8), before=btn_frame)
            else:
                group_frame.pack_forget()
        type_var.trace_add("write", on_type_change)
        
        def on_ok():
            n = name_var.get().strip()
            if not n:
                messagebox.showwarning("Fehler", "Bitte Feldname eingeben.", parent=win)
                return
            result["name"] = n
            result["type"] = type_var.get()
            result["group"] = group_var.get().strip() if type_var.get() == "radio" else ""
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
        d = ImageDraw.Draw(img)

        for f in self._current_fields():
            if f.type == "text" and f.value:
                # Schrift in Punkt — aus Einstellung
                pt = max(6, min(36, self.font_size))
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
                for i in range(2):
                    d.line([(f.x1+2,f.y1+8+i),(f.x1+6,f.y1+12+i),(f.x1+13,f.y1+3+i)], fill=(0,0,0), width=2)
            elif f.type == "radio" and f.value in (True,"True","true","1"):
                d.ellipse([f.x1+4,f.y1+4,f.x1+11,f.y1+11], fill=(0,0,0))

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

        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
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

    def _reset(self):
        self._stop_typing()
        for f in self._current_fields(): f.value = ""
        self._render(); self._status()

    def _mw(self, e): self._do_zoom(1.1 if e.delta > 0 else 0.9)

    def _current_stamps(self):
        """Gibt die Stempel-Liste der aktuellen Seite zurück."""
        return self.stamps.get(str(self.current_page), [])

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

    def _status(self):
        pdf = os.path.basename(self.pdf_path) if self.pdf_path else "Kein PDF"
        mt = "EDITOR" if self.mode=="edit" else "AUSFUELLEN"
        cur = self._current_fields()
        fc = len(cur)
        stamps = self._current_stamps()
        sc = len(stamps)
        sel = f" | {self.selected.label}" if self.selected else ""
        tpl = f" | Vorlage:{self.template_name}" if self.template_name else ""
        proj = f" | Projekt:{self.project_name}" if self.project_name else ""
        akt = f" | {self.active_field.label}" if self.active_field else ""
        fr = " | Rahmen AUS" if not self.show_frames else ""
        pages = f" | Seite {self.current_page+1}/{self.page_count}" if self.page_count > 1 else ""
        stempel = f" | {sc} Stempel" if sc else ""
        self.sb.config(text=f"{mt} | {pdf}{tpl}{proj} | {fc} Feld(er){stempel}{sel}{akt}{fr}{pages} | Raster {self.grid_size}px")
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
