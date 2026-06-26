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

APP_VERSION = "1.7.0"

C = {
    "bg": "#1e1e2e", "accent": "#89b4fa", "canvas": "#313244",
    "status": "#585b70", "text": "#cdd6f4", "dim": "#cdd6f4",
    "green": "#a6e3a1", "red": "#e64553", "yellow": "#f9e2af", "cyan": "#74c7ec",
}
SCALE = 300 / 72


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


def get_font(size_pt):
    px = max(6, int(size_pt * SCALE))
    for p in [f"/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
              f"/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
              "arial.ttf", "DejaVuSans.ttf"]:
        try: return ImageFont.truetype(p, px)
        except: pass
    return ImageFont.load_default()


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


class App:
    def __init__(self, root):
        self.root = root
        self.root.title(f"PDF-Formular Füller v{APP_VERSION}")
        try:
            mx, my = self.root.winfo_pointerx(), self.root.winfo_pointery()
            self.root.geometry(f"1200x850+{max(0,mx-600)}+{max(0,my-425)}")
        except: self.root.geometry("1200x850")
        self.root.minsize(900, 600)

        self.pdf_image = self.pdf_tk = None
        self.zoom = 0.35
        self.ox = self.oy = 0
        self.pdf_path = None
        self.fields = []
        self.selected = None
        self.template_path = self.template_name = None

        self.font_size = 11
        self.line_height = int(self.font_size * SCALE)
        self.frame_height = self.line_height  # Rahmenhöhe in Pixeln, einstellbar
        self.export_font = get_font(self.font_size)

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

        self._build()
        self._set_mode("fill")

    def _btn(self, p, t, c, bg, s=tk.LEFT, fg="#11111b"):
        b = tk.Button(p, text=t, font=("Segoe UI",9,"bold"), bg=bg, fg=fg,
                     activebackground=C["accent"], activeforeground="#11111b",
                     bd=0, pady=3, padx=6, command=c)
        b.pack(side=s, padx=1); return b

    def _build(self):
        self.root.configure(bg=C["bg"])
        mb = tk.Menu(self.root, bg=C["bg"], fg=C["text"],
                     activebackground=C["accent"], activeforeground="#11111b")
        self.root.config(menu=mb)
        fm = tk.Menu(mb, tearoff=0, bg=C["bg"], fg=C["text"],
                     activebackground=C["accent"], activeforeground="#11111b")
        mb.add_cascade(label="Datei", menu=fm)
        fm.add_command(label="📂 PDF öffnen", command=self._open_pdf)
        fm.add_command(label="📋 Vorlage laden", command=self._load_template)
        fm.add_separator()
        fm.add_command(label="💾 PDF speichern", command=self._save_pdf)
        fm.add_command(label="🖨️ Drucken", command=self._print_pdf)
        fm.add_separator()
        fm.add_command(label="Beenden", command=self.root.quit)

        tb = tk.Frame(self.root, bg=C["bg"], height=36)
        tb.pack(fill=tk.X, padx=4, pady=(4,0))
        self._btn(tb, "📂 PDF", self._open_pdf, C["accent"])
        self._btn(tb, "📋 Vorlage", self._load_template, C["cyan"])
        tk.Frame(tb, bg=C["status"], width=1).pack(side=tk.LEFT, padx=4, fill=tk.Y, pady=4)
        self.btn_fill = self._btn(tb, "📝 Ausfüllen", lambda: self._set_mode("fill"), C["green"])
        self.btn_edit = self._btn(tb, "✏️ Editor", lambda: self._set_mode("edit"), C["status"])
        tk.Frame(tb, bg=C["status"], width=1).pack(side=tk.LEFT, padx=4, fill=tk.Y, pady=4)
        self.btn_frame = self._btn(tb, "⬜ Rahmen", self._toggle_frames, C["yellow"])
        self._btn(tb, "💾 Vorlage", self._save_template, C["cyan"])
        self._btn(tb, "🖨️", self._print_pdf, C["yellow"])
        self._btn(tb, "💾 PDF", self._save_pdf, C["green"])
        tk.Frame(tb, bg=C["status"], width=1).pack(side=tk.LEFT, padx=4, fill=tk.Y, pady=4)
        self._btn(tb, "🔍−", lambda: self._do_zoom(0.8), C["status"], fg=C["text"])
        self._btn(tb, "🔍+", lambda: self._do_zoom(1.25), C["status"], fg=C["text"])
        self._btn(tb, "1:1", self._zoom_reset, C["status"], fg=C["text"])
        tk.Frame(tb, bg=C["status"], width=1).pack(side=tk.LEFT, padx=4, fill=tk.Y, pady=4)
        self._btn(tb, "⬜ Höhe", self._set_height_dialog, C["yellow"])
        self._btn(tb, "🔄", self._reset, C["red"])

        self.mf = tk.Frame(self.root, bg=C["canvas"])
        self.mf.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.cv = tk.Canvas(self.mf, bg=C["canvas"], cursor="arrow",
                           highlightthickness=0, bd=0)
        self.cv.pack(fill=tk.BOTH, expand=True)

        self.sb = tk.Label(self.root, text="", bg=C["status"], fg=C["text"],
                          anchor=tk.W, font=("Segoe UI",9))
        self.sb.pack(side=tk.BOTTOM, fill=tk.X)

        self.cv.bind("<Configure>", lambda e: self._render())
        self.cv.bind("<MouseWheel>", self._mw)
        self.cv.bind("<Button-4>", lambda e: self._do_zoom(1.1))
        self.cv.bind("<Button-5>", lambda e: self._do_zoom(0.9))
        self.cv.bind("<Button-1>", self._click)
        self.cv.bind("<B1-Motion>", self._drag)
        self.cv.bind("<ButtonRelease-1>", self._release)
        self.cv.bind("<Button-3>", self._right)
        self.cv.bind("<Key>", self._key)
        self.root.bind("<Escape>", lambda e: self._stop_typing())

    def _set_height_dialog(self):
        from tkinter import simpledialog
        val = simpledialog.askinteger("Rahmenhöhe",
            f"Aktuell: {self.frame_height} px\nNeue Höhe (10-500):",
            initialvalue=self.frame_height, minvalue=10, maxvalue=500,
            parent=self.root)
        if val is not None:
            self.frame_height = val
            for f in self.fields:
                f.y1 = f.y2 - self.frame_height  # wächst nach oben
            self._render()
            self._status()

    def _toggle_frames(self):
        self.show_frames = not self.show_frames
        self.btn_frame.configure(text="🟩 Rahmen" if self.show_frames else "⬜ Rahmen")
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
        self.export_font = get_font(self.font_size)
        try:
            pdf = pdfium.PdfDocument(path)
            bm = pdf[0].render(scale=300/72)
            self.pdf_image = bm.to_pil(); pdf.close()
            self._fit_zoom(); self._render(); self._status()
        except Exception as e: messagebox.showerror("Fehler", f"PDF: {e}")

    # ─── Vorlage ──────────────────────────────────────────────
    def _load_template(self):
        p = filedialog.askopenfilename(title="Vorlage", filetypes=[("JSON","*.json"),("*","*.*")])
        if not p: return
        try:
            with open(p, encoding='utf-8') as f: data = json.load(f)
            self.fields.clear()
            for item in data.get("fields", data.get("items", data if isinstance(data,list) else [])):
                self.fields.append(FieldRect.from_dict(item))
            self.selected = None
            self.template_path, self.template_name = p, data.get("name", os.path.basename(p))
            self._render(); self._status()
            messagebox.showinfo("Geladen", f"'{self.template_name}', {len(self.fields)} Felder")
        except Exception as e: messagebox.showerror("Fehler", f"Vorlage: {e}")

    def _save_template(self):
        if not self.fields: return messagebox.showwarning("Leer", "Keine Felder.")
        name = simpledialog.askstring("Name", "Vorlagenname:", initialvalue=self.template_name or "Neu")
        if not name: return
        p = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON","*.json")],
                                         initialfile=f"{name.lower().replace(' ','_')}.json")
        if not p: return
        with open(p, 'w', encoding='utf-8') as f:
            json.dump({"name": name, "fields": [fld.to_dict() for fld in self.fields]},
                      f, indent=2, ensure_ascii=False)
        self.template_path, self.template_name = p, name
        messagebox.showinfo("Gespeichert", f"'{name}', {len(self.fields)} Felder"); self._status()

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

            for f in self.fields: self._draw(f)

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

        # Wert anzeigen — Schrift an Feldhöhe anpassen
        if f.value and f.type == "text":
            # Gleiche Punktgröße wie im PDF-Export
            pt = max(6, min(36, f.h / SCALE * 0.7))
            fs = max(8, int(pt * SCALE * z * 0.8))
            txt = str(f.value)
            # Vertikal zentriert — einen Tick weiter unten
            y_center = y1 + fs // 2 + 5
            self.cv.create_text(x1+3, y_center, anchor=tk.W, text=txt, fill="#000",
                               font=("Segoe UI",fs), tags="f")

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
        for f in reversed(self.fields):
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
            idx = self.fields.index(self.active_field); self.active_field = None
            for i in range(1,len(self.fields)):
                nf = self.fields[(idx+i)%len(self.fields)]
                if nf.type == "text": self.active_field = nf; break
            if self.active_field: self._render(); self.cv.focus_set()
            return
        if e.keysym == "Delete": self.active_field.value = ""; self._render(); return
        if e.char and e.char.isprintable() and len(e.char)==1:
            v = str(self.active_field.value) if self.active_field.value else ""
            self.active_field.value = v + e.char; self._render(); self._status()
        self.cv.focus_set()

    def _click(self, e):
        self._stop_typing(); px, py = self._ic(e)
        if self.mode == "edit":
            f = self._find(px,py)
            if f:
                self.selected = f
                self.dragging = True
                self.drag_field = f  # Feld verschieben, nicht neu erzeugen
                self.dx, self.dy = px - f.x1, py - f.y1
                self._render(); self._status()
            else:
                self.dragging = True
                self.drag_field = None  # neues Feld aufziehen
                self.dx, self.dy = px, py
        elif self.mode == "fill":
            f = self._find(px,py)
            if f:
                if f.type == "text":
                    self.active_field = f; self.typing = True
                    self.cv.focus_set(); self._render(); self._status()
                elif f.type == "checkbox":
                    f.value = not (f.value in (True,"True","true","1"))
                    self._render(); self._status()
                elif f.type == "radio":
                    for o in self.fields:
                        if o.type=="radio" and o.group==f.group: o.value=False
                    f.value = True; self._render(); self._status()
            else:
                # Hintergrund verschieben (pan)
                self.panning = True
                self.pan_x, self.pan_y = e.x, e.y
                self.cv.configure(cursor="fleur")

    def _drag(self, e):
        if self.panning:
            dx = e.x - self.pan_x
            dy = e.y - self.pan_y
            self.pan_x, self.pan_y = e.x, e.y
            self.pan_ox += dx
            self.pan_oy += dy
            self._render()
            return
        if not self.dragging: return
        px, py = self._ic(e)
        if self.drag_field:
            # Bestehendes Feld verschieben
            f = self.drag_field
            GRID = 15
            new_x1 = int(px - self.dx) // GRID * GRID
            new_y1 = int(py - self.dy) // GRID * GRID
            w, h = f.w, f.h
            f.x1, f.y1 = new_x1, new_y1
            f.x2, f.y2 = new_x1 + w, new_y1 + h
            self.cv.delete("drag")
            z, ox, oy = self.zoom, self.ox, self.oy
            self.cv.create_rectangle(ox+int(f.x1*z),oy+int(f.y1*z),
                                     ox+int(f.x2*z),oy+int(f.y2*z),
                                     outline=C["yellow"],fill="",width=3,dash=(4,4),tags="drag")
            self._render()
            return
        # Neues Feld aufziehen
        self.cv.delete("drag")
        GRID = 15  # Einrast-Raster in Pixeln
        x1, y1 = min(self.dx,px), (min(self.dy,py)//GRID)*GRID
        x2, y2 = max(self.dx,px), y1 + self.frame_height
        z, ox, oy = self.zoom, self.ox, self.oy
        self.cv.create_rectangle(ox+int(x1*z),oy+int(y1*z),ox+int(x2*z),oy+int(y2*z),
                                outline=C["accent"],fill="#2a3040",width=2,dash=(4,4),tags="drag")

    def _release(self, e):
        if self.panning:
            self.panning = False
            self.cv.configure(cursor="hand2")
            return
        if not self.dragging: return
        self.dragging = False; self.cv.delete("drag")
        if self.drag_field:
            # Feld wurde verschoben — fertig
            self.drag_field = None
            self._render(); self._status()
            return
        px, py = self._ic(e)
        if abs(px-self.dx)<10 or abs(py-self.dy)<10: return
        GRID = 15  # Einrast-Raster in Pixeln
        y_top = min(self.dy, py)
        y1_snap = int(y_top) // GRID * GRID
        y2_snap = y1_snap + self.frame_height
        
        f = FieldRect(x1=int(min(self.dx,px)), y1=y1_snap,
                      x2=int(max(self.dx,px)), y2=y2_snap, label="", ftype="text")
        name = simpledialog.askstring("Feldname", "Feldname:", initialvalue=f"Feld {len(self.fields)+1}")
        if not name: return
        f.label = name
        typ = simpledialog.askstring("Feldtyp", "Typ: text / checkbox / radio", initialvalue="text")
        if typ and typ.lower() in ("checkbox","radio"):
            f.type = typ.lower()
            if f.type == "radio":
                grp = simpledialog.askstring("Radio-Gruppe", "Gruppenname:", initialvalue="gruppe1")
                if grp: f.group = grp
        self.fields.append(f); self.selected = f; self._render(); self._status()

    def _right(self, e):
        if self.mode != "edit": return
        px, py = self._ic(e); f = self._find(px,py)
        if f and messagebox.askyesno("Löschen", f"'{f.label}' löschen?"):
            self.fields.remove(f)
            if self.selected == f: self.selected = None
            self._render(); self._status()

    # ─── Export ───────────────────────────────────────────────
    def _build_pdf(self) -> str:
        if not self.pdf_image: raise ValueError("Kein PDF")
        img = self.pdf_image.copy()
        d = ImageDraw.Draw(img)

        for f in self.fields:
            if f.type == "text" and f.value:
                # Schrift in Punkt — direkt proportional zur Feldhöhe
                pt = max(6, min(36, f.h / SCALE * 0.7))
                font = get_font(pt)
                # PIL-Offset für korrekte y-Position
                ref_bbox = font.getbbox('Ag')
                # bbox[1] ist negativ: Abstand von draw_y bis Oberkante der Glyphen
                pil_offset = ref_bbox[1]
                # Text zentriert innerhalb des Feldes — minimalen Offset nach unten
                text_h = ref_bbox[3] - ref_bbox[1]  # effektive Höhe des Textes
                draw_y = f.y1 + (f.h - text_h) // 2 - 1 - pil_offset
                d.text((f.x1 + 2, draw_y), str(f.value), fill=(0, 0, 0), font=font)
            elif f.type == "checkbox" and f.value in (True,"True","true","1"):
                for i in range(2):
                    d.line([(f.x1+2,f.y1+8+i),(f.x1+6,f.y1+12+i),(f.x1+13,f.y1+3+i)], fill=(0,0,0), width=2)
            elif f.type == "radio" and f.value in (True,"True","true","1"):
                d.ellipse([f.x1+4,f.y1+4,f.x1+11,f.y1+11], fill=(0,0,0))

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
        for f in self.fields: f.value = ""
        self._render(); self._status()

    def _mw(self, e): self._do_zoom(1.1 if e.delta > 0 else 0.9)

    def _status(self):
        pdf = os.path.basename(self.pdf_path) if self.pdf_path else "Kein PDF"
        mt = "EDITOR" if self.mode=="edit" else "AUSFUELLEN"
        fc = len(self.fields)
        sel = f" | {self.selected.label}" if self.selected else ""
        tpl = f" | {self.template_name}" if self.template_name else ""
        akt = f" | {self.active_field.label}" if self.active_field else ""
        fr = " | Rahmen AUS" if not self.show_frames else ""
        self.sb.config(text=f"{mt} | {pdf}{tpl} | {fc} Feld(er){sel}{akt}{fr}")


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()

if __name__ == "__main__":
    main()
