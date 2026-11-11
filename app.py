from __future__ import annotations

import multiprocessing
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from contextlib import contextmanager
from pathlib import Path
from tkinter import filedialog, messagebox, font as tkfont

import customtkinter as ctk
from PIL import Image, ImageChops, ImageDraw, ImageGrab, ImageOps, ImageTk

from scripts.etc.colorpicker import ColorPicker
from scripts.etc import colors, paths, settings
from scripts.pdfcore.errors import Cancelled, describe
from scripts.pdfcore.files import IMG_EXT, PDF_EXT, human, natural_key, safe_filename
from scripts.pdfcore.images import rate_to_quality
from scripts.pdfcore.pdfium_util import count_pages
from scripts.pdfcore.tasks import TASKS
from scripts.etc.uiperf import FRAME_MS, SLOW_FRAME_MS, ResizeGovernor, ScrollableWidthLock, ease_inout

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False

DnDMixin = TkinterDnD.DnDWrapper if HAS_DND else object

SMOOTH_REDRAW = True
FADE_THEME = True
THEME_FADE_MS = 500

ICON_DIR = paths.resource_dir() / "icons"

BG = ("#F4F5F7", "#141518")
SURFACE = ("#FFFFFF", "#1C1D21")
SURFACE2 = ("#F3F4F7", "#25272C")
HOVER = ("#E8EAF0", "#2D3036")
BORDER = ("#E2E4EA", "#2C2E34")
TEXT = ("#16181D", "#E8E9EC")
MUTED = ("#6A7080", "#8A90A0")
ACCENT = ("#3B5BDB", "#5B7CFA")
ACCENT_HOVER = ("#2F4AC0", "#7490FF")
ACCENT_SOFT = ("#E7ECFF", "#252C4D")
DANGER = ("#D6393F", "#F0646A")
DANGER_HOVER = ("#BF2F35", "#E0555B")
OK = ("#1F9D63", "#3DC585")
TRACK = ("#E7E9EE", "#2A2C32")
SEG_ON = ("#FFFFFF", "#3E424B")
SEG_HOVER = ("#DCDFE6", "#33363D")

ON_ACCENT = ("#FFFFFF", "#FFFFFF")
ON_ACCENT_DISABLED = ("#C9D3FF", "#C9D3FF")

STYLES = {
    "primary": dict(fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ON_ACCENT,
                    text_color_disabled=ON_ACCENT_DISABLED, border_width=0),
    "soft": dict(fg_color=SURFACE2, hover_color=HOVER, text_color=TEXT,
                 border_width=1, border_color=BORDER),
    "ghost": dict(fg_color="transparent", hover_color=HOVER, text_color=TEXT, border_width=0),
}


def set_accent(value: str) -> None:
    global ACCENT, ACCENT_HOVER, ACCENT_SOFT, ON_ACCENT, ON_ACCENT_DISABLED
    pal = colors.derive_accent(value)
    ACCENT, ACCENT_HOVER, ACCENT_SOFT = pal.main, pal.hover, pal.soft
    ON_ACCENT, ON_ACCENT_DISABLED = pal.on, pal.on_disabled
    STYLES["primary"].update(fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ON_ACCENT,
                             text_color_disabled=ON_ACCENT_DISABLED)


ICON_FILL = 0.16
ICON_GAMMA = 0.85
ICON_TWEAKS = {"logo": {"sx": 0.92}}
ICON_ALIASES = {"arrow_down": ("arrow_up", "flip")}
FILE_ICON = {"pdf": "logo", "img": "jpg"}

MODES = {
    "pdf2png":  dict(icon="pdf_to_png", ext=PDF_EXT, ordered=False, panel="dpi"),
    "img2pdf":  dict(icon="img_to_pdf", ext=IMG_EXT, ordered=True, num="page", panel="img"),
    "merge":    dict(icon="merge", ext=PDF_EXT, ordered=True, num="doc", panel="name"),
    "split":    dict(icon="split", ext=PDF_EXT, ordered=False, panel="split"),
    "remove":   dict(icon="remove_pages", ext=PDF_EXT, ordered=False, panel="remove"),
    "compress": dict(icon="compress", ext=PDF_EXT, ordered=False, panel="compress"),
}
GROUPS = [("sec_convert", ["pdf2png", "img2pdf"]),
          ("sec_edit", ["merge", "split", "remove", "compress"])]
LEVEL_KEYS = ["light", "balanced", "strong"]
SPLIT_KEYS = ["each", "ranges", "every"]

LANGS = [("ro", "🇷🇴  Română"), ("en", "🇬🇧  English"),
         ("es", "🇪🇸  Español"), ("fr", "🇫🇷  Français")]
LANG_CODES = [c for c, _ in LANGS]

S = {
    "m_pdf2png": ("PDF → PNG",) * 4,
    "m_img2pdf": ("IMG → PDF",) * 4,
    "m_merge": ("Îmbinare PDF", "Merge PDF", "Unir PDF", "Fusionner PDF"),
    "m_split": ("Împărțire PDF", "Split PDF", "Dividir PDF", "Diviser PDF"),
    "m_remove": ("Elimină pagini", "Remove pages", "Eliminar páginas", "Supprimer des pages"),
    "m_compress": ("Comprimare", "Compress", "Comprimir", "Compresser"),
    "sec_convert": ("Conversie", "Convert", "Conversión", "Conversion"),
    "sec_edit": ("Editare", "Edit", "Edición", "Édition"),
    "h_pdf2png": ("Exportă fiecare pagină ca imagine PNG", "Export each page as a PNG image",
                  "Exporta cada página como imagen PNG", "Exporter chaque page en image PNG"),
    "h_img2pdf": ("Ordinea din listă este ordinea paginilor", "List order is the page order",
                  "El orden de la lista es el orden de las páginas",
                  "L'ordre de la liste est l'ordre des pages"),
    "h_merge": ("Documentele sunt îmbinate în ordinea din listă", "Documents are merged in list order",
                "Los documentos se unen en el orden de la lista",
                "Les documents sont fusionnés dans l'ordre de la liste"),
    "h_split": ("Împarte un PDF în mai multe fișiere", "Split a PDF into multiple files",
                "Divide un PDF en varios archivos", "Diviser un PDF en plusieurs fichiers"),
    "h_remove": ("Șterge paginile nedorite dintr-un PDF", "Delete unwanted pages from a PDF",
                 "Elimina las páginas no deseadas de un PDF",
                 "Supprimer les pages indésirables d'un PDF"),
    "h_compress": ("Reduce dimensiunea fișierelor PDF", "Reduce the size of PDF files",
                   "Reduce el tamaño de los archivos PDF", "Réduire la taille des fichiers PDF"),
    "r_pdf2png": ("Exportă PNG", "Export PNG", "Exportar PNG", "Exporter en PNG"),
    "r_img2pdf": ("Creează PDF", "Create PDF", "Crear PDF", "Créer le PDF"),
    "r_merge": ("Îmbină PDF-urile", "Merge PDFs", "Unir PDF", "Fusionner les PDF"),
    "r_split": ("Împarte PDF-ul", "Split PDF", "Dividir PDF", "Diviser le PDF"),
    "r_remove": ("Elimină paginile", "Remove pages", "Eliminar páginas", "Supprimer les pages"),
    "r_compress": ("Comprimă PDF-ul", "Compress PDF", "Comprimir PDF", "Compresser le PDF"),
    "options": ("Opțiuni", "Options", "Opciones", "Options"),
    "o_size": ("Mărime text", "Text size", "Tamaño del texto", "Taille du texte"),
    "o_dark": ("Mod întunecat", "Dark mode", "Modo oscuro", "Mode sombre"),
    "o_lang": ("Limbă", "Language", "Idioma", "Langue"),
    "select_all": ("Selectează tot", "Select all", "Seleccionar todo", "Tout sélectionner"),
    "select_none": ("Deselectează", "Deselect", "Deseleccionar", "Tout désélectionner"),
    "count": ("{n} din {t} selectate", "{n} of {t} selected",
              "{n} de {t} seleccionados", "{n} sur {t} sélectionnés"),
    "empty_t": ("Niciun fișier", "No files", "Ningún archivo", "Aucun fichier"),
    "empty_h": ("Trage fișiere sau un folder aici, ori alege un folder.",
                "Drop files or a folder here, or pick a folder.",
                "Arrastra archivos o una carpeta aquí, o elige una carpeta.",
                "Déposez des fichiers ou un dossier ici, ou choisissez un dossier."),
    "t_refresh": ("Reîmprospătează lista", "Refresh list", "Actualizar lista", "Actualiser la liste"),
    "t_browse": ("Alege folderul", "Choose folder", "Elegir carpeta", "Choisir le dossier"),
    "t_order": ("Ordinea în document", "Order in document", "Orden en el documento",
                "Ordre dans le document"),
    "t_remove": ("Elimină din listă", "Remove from list", "Quitar de la lista", "Retirer de la liste"),
    "t_open": ("Deschide folderul cu rezultate", "Open output folder",
               "Abrir carpeta de resultados", "Ouvrir le dossier de sortie"),
    "t_drag": ("Trage pentru a reordona (Ctrl = copiază)", "Drag to reorder (Ctrl = copy)",
               "Arrastra para reordenar (Ctrl = copiar)", "Glisser pour réordonner (Ctrl = copier)"),
    "t_close": ("Închide", "Close", "Cerrar", "Fermer"),
    "page": ("Pagina {n}", "Page {n}", "Página {n}", "Page {n}"),
    "doc": ("Documentul {n}", "Document {n}", "Documento {n}", "Document {n}"),
    "excl": ("Exclus", "Excluded", "Excluido", "Exclu"),
    "pages": ("{n} pagini", "{n} pages", "{n} páginas", "{n} pages"),
    "pages1": ("1 pagină", "1 page", "1 página", "1 page"),
    "o_dpi": ("Rezoluție: {n} DPI", "Resolution: {n} DPI", "Resolución: {n} DPI", "Résolution : {n} DPI"),
    "hp_dpi": ("Pagină A4 ≈ {w} × {h} px", "A4 page ≈ {w} × {h} px",
               "Página A4 ≈ {w} × {h} px", "Page A4 ≈ {w} × {h} px"),
    "o_name": ("Nume fișier", "File name", "Nombre del archivo", "Nom du fichier"),
    "hp_name": ("Se salvează ca „{name}.pdf” lângă fișierele sursă",
                "Saved as “{name}.pdf” next to the source files",
                "Se guarda como «{name}.pdf» junto a los archivos de origen",
                "Enregistré sous « {name}.pdf » à côté des fichiers source"),
    "o_level": ("Nivel", "Level", "Nivel", "Niveau"),
    "lv_light": ("Ușor", "Light", "Ligero", "Léger"),
    "lv_balanced": ("Echilibrat", "Balanced", "Equilibrado", "Équilibré"),
    "lv_strong": ("Puternic", "Strong", "Fuerte", "Fort"),
    "lvd_light": ("Calitatea rămâne aproape neschimbată", "Quality stays almost untouched",
                  "La calidad casi no cambia", "La qualité reste presque intacte"),
    "lvd_balanced": ("Cel mai bun raport dimensiune / calitate", "Best size / quality trade-off",
                     "Mejor equilibrio tamaño / calidad", "Meilleur compromis taille / qualité"),
    "lvd_strong": ("Fișier minim, imaginile pierd din detalii", "Smallest file, images lose some detail",
                   "Archivo mínimo, las imágenes pierden detalle",
                   "Fichier minimal, les images perdent en détail"),
    "o_pages": ("Pagini de eliminat", "Pages to remove", "Páginas a eliminar", "Pages à supprimer"),
    "ph_pages": ("ex: 2, 5-7, 10-", "e.g. 2, 5-7, 10-", "p. ej.: 2, 5-7, 10-", "ex. : 2, 5-7, 10-"),
    "hp_pages": ("Separă cu virgulă · „10-” înseamnă până la final",
                 "Separate with commas · “10-” means to the end",
                 "Separa con comas · «10-» significa hasta el final",
                 "Séparez par des virgules · « 10- » signifie jusqu'à la fin"),
    "o_split": ("Mod", "Mode", "Modo", "Mode"),
    "sp_each": ("Fiecare pagină", "Every page", "Cada página", "Chaque page"),
    "sp_ranges": ("Intervale", "Ranges", "Rangos", "Plages"),
    "sp_every": ("La N pagini", "Every N pages", "Cada N páginas", "Toutes les N pages"),
    "ph_ranges": ("ex: 1-3, 4-6, 7-", "e.g. 1-3, 4-6, 7-", "p. ej.: 1-3, 4-6, 7-", "ex. : 1-3, 4-6, 7-"),
    "ph_every": ("ex: 5", "e.g. 5", "p. ej.: 5", "ex. : 5"),
    "hp_each": ("Fiecare pagină devine un fișier PDF separat", "Each page becomes its own PDF file",
                "Cada página se convierte en un PDF independiente", "Chaque page devient un PDF distinct"),
    "ready": ("Gata de lucru", "Ready", "Listo", "Prêt"),
    "added": ("{n} fișiere adăugate", "{n} files added", "{n} archivos añadidos", "{n} fichiers ajoutés"),
    "wrong": ("Tip de fișier nepotrivit pentru acest mod", "File type not supported in this mode",
              "Tipo de archivo no válido para este modo", "Type de fichier non pris en charge ici"),
    "none_sel": ("Selectează cel puțin un fișier", "Select at least one file",
                 "Selecciona al menos un archivo", "Sélectionnez au moins un fichier"),
    "need2": ("Alege cel puțin 2 PDF-uri", "Select at least 2 PDFs",
              "Selecciona al menos 2 PDF", "Sélectionnez au moins 2 PDF"),
    "bad_dir": ("Folder invalid", "Invalid folder", "Carpeta no válida", "Dossier invalide"),
    "refreshed": ("Lista a fost actualizată", "List updated", "Lista actualizada", "Liste actualisée"),
    "error": ("Eroare: {e}", "Error: {e}", "Error: {e}", "Erreur : {e}"),
    "raw": ("{text}",) * 4,
    "d_move": ("Mută la poziția {n}", "Move to position {n}", "Mover a la posición {n}",
               "Déplacer à la position {n}"),
    "d_copy": ("Copiază la poziția {n}", "Copy to position {n}", "Copiar a la posición {n}",
               "Copier à la position {n}"),
    "d_same": ("Aceeași poziție", "Same position", "Misma posición", "Même position"),
    "d_no": ("Nepermis aici", "Not allowed here", "No permitido aquí", "Non autorisé ici"),
    "d_png": ("{n} pagini exportate", "{n} pages exported", "{n} páginas exportadas", "{n} pages exportées"),
    "d_file": ("Creat: {name}", "Created: {name}", "Creado: {name}", "Créé : {name}"),
    "d_compress": ("{a} → {b}  (−{p}%)",) * 4,
    "d_nogain": ("Fișierele sunt deja optimizate", "Files are already optimized",
                 "Los archivos ya están optimizados", "Les fichiers sont déjà optimisés"),
    "d_remove": ("{n} fișier(e) editate", "{n} file(s) edited", "{n} archivo(s) editados",
                 "{n} fichier(s) modifié(s)"),
    "d_split": ("{n} fișiere create", "{n} files created", "{n} archivos creados", "{n} fichiers créés"),
    "e_range": ("Interval invalid „{spec}” pentru {name}", "Invalid range “{spec}” for {name}",
                "Rango no válido «{spec}» para {name}", "Plage invalide « {spec} » pour {name}"),
    "e_empty": ("Introdu paginile dorite", "Enter the pages you want",
                "Introduce las páginas deseadas", "Saisissez les pages souhaitées"),
    "e_all": ("Nu poți elimina toate paginile din {name}", "You can't remove every page of {name}",
              "No puedes eliminar todas las páginas de {name}",
              "Impossible de supprimer toutes les pages de {name}"),
    "e_num": ("Introdu un număr valid de pagini", "Enter a valid number of pages",
              "Introduce un número de páginas válido", "Saisissez un nombre de pages valide"),
    "stop": ("Oprește", "Stop", "Detener", "Arrêter"),
    "stopping": ("Se oprește…", "Stopping…", "Deteniendo…", "Arrêt en cours…"),
    "d_cancel": ("Operație anulată", "Operation cancelled", "Operación cancelada", "Opération annulée"),
    "q_close_t": ("Închizi aplicația?", "Close the app?", "¿Cerrar la aplicación?", "Fermer l'application ?"),
    "q_close": ("O operație este în desfășurare. Dacă închizi acum, va fi oprită.",
                "An operation is in progress. If you close now, it will be stopped.",
                "Hay una operación en curso. Si cierras ahora, se detendrá.",
                "Une opération est en cours. Si vous fermez maintenant, elle sera arrêtée."),
    "o_rate": ("Rată implicită de comprimare PDF: {n}%", "Default PDF Compression Rate: {n}%",
               "Tasa de compresión PDF predeterminada: {n}%", "Taux de compression PDF par défaut : {n} %"),
    "hp_rate": ("Fișier mai mic, imagini cu mai puține detalii (calitate JPEG ≈ {q})",
                "Smaller file, images with less detail (JPEG quality ≈ {q})",
                "Archivo más pequeño, imágenes con menos detalle (calidad JPEG ≈ {q})",
                "Fichier plus petit, images moins détaillées (qualité JPEG ≈ {q})"),
    "hp_rate0": ("Fără pierderi: imaginile își păstrează datele originale",
                 "Lossless: images keep their original data",
                 "Sin pérdidas: las imágenes conservan sus datos originales",
                 "Sans perte : les images conservent leurs données d'origine"),
    "e_memory": ("Memorie insuficientă pentru această operație. Încearcă o rezoluție mai mică sau mai puține fișiere.",
                 "Not enough memory for this operation. Try a lower resolution or fewer files.",
                 "Memoria insuficiente para esta operación. Prueba una resolución menor o menos archivos.",
                 "Mémoire insuffisante pour cette opération. Essayez une résolution plus basse ou moins de fichiers."),
    "e_perm": ("Nu am permisiunea de a scrie în folderul rezultat", "No permission to write to the output folder",
               "Sin permiso para escribir en la carpeta de destino",
               "Pas d'autorisation d'écriture dans le dossier de sortie"),
    "e_missing": ("Fișierul nu mai există: {name}", "File no longer exists: {name}",
                  "El archivo ya no existe: {name}", "Le fichier n'existe plus : {name}"),
    "e_disk": ("Spațiu insuficient pe disc", "Not enough disk space",
               "No hay espacio suficiente en el disco", "Espace disque insuffisant"),
    "e_pdf": ("Nu pot citi {name}: PDF deteriorat sau invalid", "Can't read {name}: damaged or invalid PDF",
              "No se puede leer {name}: PDF dañado o no válido", "Impossible de lire {name} : PDF endommagé ou invalide"),
    "e_encrypted": ("{name} este protejat cu parolă (neacceptat)", "{name} is password-protected (not supported)",
                    "{name} está protegido con contraseña (no compatible)",
                    "{name} est protégé par mot de passe (non pris en charge)"),
    "e_toobig": ("Pagina {page} din {name} ar avea {w} × {h} px, peste limita de {mp} MP. Alege o rezoluție mai mică.",
                 "Page {page} of {name} would be {w} × {h} px, over the {mp} MP limit. Choose a lower resolution.",
                 "La página {page} de {name} tendría {w} × {h} px, por encima del límite de {mp} MP. Elige una resolución menor.",
                 "La page {page} de {name} ferait {w} × {h} px, au-delà de la limite de {mp} MP. "
                 "Choisissez une résolution plus basse."),
    "e_image": ("Nu pot citi imaginea {name}: {e}", "Can't read image {name}: {e}",
                "No se puede leer la imagen {name}: {e}", "Impossible de lire l'image {name} : {e}"),
    "o_accent": ("Culoare de accent", "Accent Colour", "Color de acento", "Couleur d'accentuation"),
    "c_bright": ("Luminozitate", "Brightness", "Brillo", "Luminosité"),
    "c_current": ("Curentă", "Current", "Actual", "Actuelle"),
    "c_new": ("Nouă", "New", "Nueva", "Nouvelle"),
    "c_hex": ("HEX", "HEX", "HEX", "HEX"),
    "c_apply": ("Aplică", "Apply", "Aplicar", "Appliquer"),
    "c_cancel": ("Anulează", "Cancel", "Cancelar", "Annuler"),
    "c_reset": ("Resetează", "Reset", "Restablecer", "Réinitialiser"),
    "c_invalid": ("Valoare invalidă", "Invalid value", "Valor no válido", "Valeur invalide"),
    "c_hint": ("HEX (#3B5BDB) sau RGB (59, 91, 219)", "HEX (#3B5BDB) or RGB (59, 91, 219)",
               "HEX (#3B5BDB) o RGB (59, 91, 219)", "HEX (#3B5BDB) ou RVB (59, 91, 219)"),
    "e_worker": ("Procesul de lucru s-a oprit neașteptat (probabil lipsă de memorie)",
                 "The worker process stopped unexpectedly (probably out of memory)",
                 "El proceso de trabajo se detuvo inesperadamente (probablemente falta de memoria)",
                 "Le processus de travail s'est arrêté de façon inattendue (probablement manque de mémoire)"),
}


def hexc(c):
    return c if isinstance(c, str) else c[1 if ctk.get_appearance_mode() == "Dark" else 0]


def mix(a: str, b: str, t: float) -> str:
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(ca, cb))


def ease_out(t):  return 1 - (1 - t) ** 3
def ease_in(t):   return t * t


def shorten(name: str, limit: int = 54) -> str:
    if len(name) <= limit:
        return name
    keep = limit - 1
    return name[: keep // 2] + "…" + name[-(keep - keep // 2):]


def open_folder(path: Path):
    if sys.platform.startswith("win"):
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def load_config() -> dict:
    return settings.load_settings(LANG_CODES)


class Icons:

    def __init__(self):
        self._mask: dict[str, Image.Image] = {}
        self._cache: dict = {}
        fill, gamma = ICON_FILL, ICON_GAMMA
        self._lut = [round(255 * min(1.0, (fill + (1 - fill) * (1 - v / 255)) ** gamma)) for v in range(256)]

    def _build_mask(self, name: str) -> Image.Image:
        src, op = ICON_ALIASES.get(name, (name, None))
        try:
            im = Image.open(ICON_DIR / f"{src}.png").convert("RGBA")
            if im.size != (64, 64):
                im = im.resize((64, 64), Image.Resampling.LANCZOS)
        except Exception:
            m = Image.new("L", (64, 64), 0)
            ImageDraw.Draw(m).rounded_rectangle((10, 10, 54, 54), radius=10, outline=255, width=5)
            return m
        sx = ICON_TWEAKS.get(name, {}).get("sx", 1.0)
        if sx != 1.0:
            w = max(1, round(64 * sx))
            squeezed = im.resize((w, 64), Image.Resampling.LANCZOS)
            im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            im.paste(squeezed, ((64 - w) // 2, 0))
        if op == "flip":
            im = ImageOps.flip(im)
        lum = im.convert("RGB").convert("L")
        alpha = im.getchannel("A").point(lambda v: 0 if v < 24 else v)
        return ImageChops.multiply(lum.point(self._lut), alpha)

    def clear(self):
        self._cache.clear()

    def mask(self, name: str) -> Image.Image:
        if name not in self._mask:
            self._mask[name] = self._build_mask(name)
        return self._mask[name]

    @staticmethod
    def _tint(mask: Image.Image, color: str) -> Image.Image:
        solid = Image.new("RGBA", mask.size, color)
        solid.putalpha(mask)
        return solid

    def get(self, name, color, size=18, angle=0.0):
        light, dark = (color, color) if isinstance(color, str) else color
        key = (name, light, dark, size, round(angle))
        if key in self._cache:
            return self._cache[key]
        m = self.mask(name)
        if angle:
            m = m.rotate(angle, resample=Image.Resampling.BICUBIC)
        img = ctk.CTkImage(self._tint(m, light), self._tint(m, dark), size=(size, size))
        if not angle:
            self._cache[key] = img
        return img

    def pil(self, name, color, size):
        return self._tint(self.mask(name), hexc(color)).resize((size, size), Image.Resampling.LANCZOS)


class _Redraw:

    def __init__(self, root):
        self.root, self.depth, self.u32, self.hwnd = root, 0, None, None
        if sys.platform == "win32" and SMOOTH_REDRAW:
            try:
                import ctypes
                from ctypes import wintypes as wt
                u32 = ctypes.WinDLL("user32")
                u32.GetAncestor.argtypes = [wt.HWND, wt.UINT]
                u32.GetAncestor.restype = wt.HWND
                u32.LockWindowUpdate.argtypes = [wt.HWND]
                u32.LockWindowUpdate.restype = wt.BOOL
                root.update_idletasks()
                self.hwnd = u32.GetAncestor(root.winfo_id(), 2)
                self.u32 = u32
            except Exception:
                self.u32 = None

    @contextmanager
    def frozen(self):
        self.depth += 1
        locked = False
        if self.depth == 1 and self.u32 and self.hwnd:
            try:
                locked = bool(self.u32.LockWindowUpdate(self.hwnd))
            except Exception:
                locked = False
        try:
            yield
            if self.depth == 1 and locked:
                self.root.update_idletasks()
        finally:
            self.depth -= 1
            if locked:
                try:
                    self.u32.LockWindowUpdate(None)
                except Exception:
                    pass


class _WinTip:

    def __init__(self, root):
        import ctypes
        from ctypes import wintypes as wt

        u32 = ctypes.windll.user32

        class ICC(ctypes.Structure):
            _fields_ = [("dwSize", wt.DWORD), ("dwICC", wt.DWORD)]

        class TOOLINFO(ctypes.Structure):
            _fields_ = [("cbSize", wt.UINT), ("uFlags", wt.UINT), ("hwnd", wt.HWND),
                        ("uId", ctypes.c_size_t), ("rect", wt.RECT), ("hinst", wt.HINSTANCE),
                        ("lpszText", wt.LPWSTR), ("lParam", wt.LPARAM)]

        ctypes.windll.comctl32.InitCommonControlsEx(ctypes.byref(ICC(8, 0xFF)))
        u32.GetAncestor.argtypes = [wt.HWND, wt.UINT]
        u32.GetAncestor.restype = wt.HWND
        u32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
                                        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                        wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID]
        u32.CreateWindowExW.restype = wt.HWND
        u32.SendMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
        u32.SendMessageW.restype = ctypes.c_ssize_t

        root.update_idletasks()
        owner = u32.GetAncestor(root.winfo_id(), 2)
        d = -0x80000000
        self.hwnd = u32.CreateWindowExW(0x8, "tooltips_class32", None, 0x80000000 | 0x3,
                                        d, d, d, d, owner, None, None, None)
        if not self.hwnd:
            raise OSError("tooltip")
        ti = TOOLINFO()
        ti.cbSize = ctypes.sizeof(TOOLINFO)
        ti.uFlags = 0x20 | 0x80
        ti.hwnd = owner
        ti.uId = 1
        ti.lpszText = " "
        self.ti, self.send, self.addr = ti, u32.SendMessageW, ctypes.addressof(ti)
        self.send(self.hwnd, 0x432, 0, self.addr)
        self.send(self.hwnd, 0x418, 0, 320)

    def show(self, text, x, y):
        self.ti.lpszText = text
        self.send(self.hwnd, 0x436, 0, self.addr)
        self.send(self.hwnd, 0x412, 0, ((y & 0xFFFF) << 16) | (x & 0xFFFF))
        self.send(self.hwnd, 0x411, 1, self.addr)

    def hide(self):
        self.send(self.hwnd, 0x411, 0, self.addr)


class Tooltips:
    DELAY = 550

    def __init__(self, root):
        self.root = root
        self.cur = None
        self.visible = False
        self._show_job = self._hide_job = None
        self._tw = self._lbl = None
        self._native = None
        if sys.platform == "win32":
            try:
                self._native = _WinTip(root)
            except Exception:
                self._native = None

    def attach(self, widget, text_fn):
        widget.bind("<Enter>", lambda e: self._enter(widget, text_fn), add="+")
        widget.bind("<Leave>", lambda e: self._leave(), add="+")
        widget.bind("<ButtonPress>", lambda e: self._hide(), add="+")

    def _cancel(self):
        for job in (self._show_job, self._hide_job):
            if job:
                try:
                    self.root.after_cancel(job)
                except tk.TclError:
                    pass
        self._show_job = self._hide_job = None

    def _enter(self, widget, fn):
        self._cancel()
        self.cur = (widget, fn)
        self._show_job = self.root.after(60 if self.visible else self.DELAY, self._show)

    def _leave(self):
        self._cancel()
        self._hide_job = self.root.after(60, self._hide)

    def _show(self):
        if not self.cur:
            return
        widget, fn = self.cur
        try:
            text = fn()
            x, y = widget.winfo_pointerx() + 14, widget.winfo_pointery() + 22
        except tk.TclError:
            return
        if self._native:
            self._native.show(text, x, y)
        else:
            self._fallback(text, x, y)
        self.visible = True

    def _hide(self):
        self._cancel()
        self.cur = None
        if self.visible:
            if self._native:
                self._native.hide()
            elif self._tw:
                self._tw.withdraw()
        self.visible = False

    def _fallback(self, text, x, y):
        if self._tw is None:
            tw = tk.Toplevel(self.root)
            tw.withdraw()
            tw.wm_overrideredirect(True)
            try:
                tw.attributes("-topmost", True)
                font = "TkTooltipFont"
                self._lbl = tk.Label(tw, justify="left", bg="#FFFFE1", fg="#000000",
                                     relief="solid", bd=1, padx=5, pady=2, font=font)
            except tk.TclError:
                self._lbl = tk.Label(tw, justify="left", bg="#FFFFE1", fg="#000000",
                                     relief="solid", bd=1, padx=5, pady=2)
            self._lbl.pack()
            self._tw = tw
        self._lbl.configure(text=text)
        self._tw.geometry(f"+{x}+{y}")
        self._tw.deiconify()


class Item:
    __slots__ = ("path", "var", "row", "name", "num", "meta", "chk", "dead")

    def __init__(self, path: Path, checked: bool = True):
        self.path = path
        self.var = ctk.BooleanVar(value=checked)
        self.row = self.name = self.num = self.meta = self.chk = None
        self.dead = False


DRAG_THRESHOLD = 5
SPRING_MS = 500
NO_CURSOR = "no" if sys.platform == "win32" else "X_cursor"


class App(ctk.CTk, DnDMixin):
    def __init__(self):
        cfg = load_config()
        set_accent(cfg["accent"])
        ctk.set_appearance_mode("dark" if cfg["dark"] else "light")
        super().__init__()
        if HAS_DND:
            self.TkdndVersion = TkinterDnD._require(self)
        self.cfg = cfg
        self.li = LANG_CODES.index(cfg["lang"])
        self.title("PyPDF Ui")
        self.geometry("1080x780")
        self.minsize(920, 660)
        self.configure(fg_color=BG)
        ico = ICON_DIR / "app.ico"
        if sys.platform == "win32" and ico.exists():
            self.after(250, lambda: self.iconbitmap(str(ico)))

        self.family = tkfont.nametofont("TkDefaultFont").actual("family")
        s = cfg["size"]
        self.f_base = ctk.CTkFont(family=self.family, size=s)
        self.f_bold = ctk.CTkFont(family=self.family, size=s, weight="bold")
        self.f_small = ctk.CTkFont(family=self.family, size=max(s - 2, 9))
        self.f_title = ctk.CTkFont(family=self.family, size=s + 8, weight="bold")

        self.update_idletasks()
        self.icons = Icons()
        self.tips = Tooltips(self)
        self.redraw = _Redraw(self)
        self.frozen = self.redraw.frozen
        self._blank = ctk.CTkImage(Image.new("RGBA", (16, 16), (0, 0, 0, 0)), size=(16, 16))

        self.mode = "pdf2png"
        self.folder = Path(cfg["folder"]) if cfg["folder"] else paths.default_folder()
        self.items: list[Item] = []
        self._pending: list[Item] = []
        self.last_out = self.folder
        self.q: queue.Queue = queue.Queue()
        self.busy = False
        self.cancel = threading.Event()
        self._worker: threading.Thread | None = None
        self._scan_gen = 0
        self.level, self.split_mode = "balanced", "each"
        self._i18n: list = []
        self._pages: dict = {}
        self._drag = None
        self._ctrl = False
        self._prog, self._prog_tok = 0.0, 0
        self._panel_open, self._panel_tok = False, 0
        self._panel_x = 0
        self._browse_active = False
        self._refresh_accent_job = None
        self._refresh_status_job = None
        self._sliders: list = []
        self._resizing = False
        self._anim_active = 0
        self._fade_overlay = None
        self._fade_tok = 0
        self._accent_dlg = None
        self._mode_cur: dict = {}
        self._st = ("ready", "info", {})
        self._save_job = self._size_job = self._limit_job = None
        self._avail: dict = {}
        self._drop_col = None
        self._spring_key, self._spring_job = None, None
        self.mode_btns: dict = {}

        self.grid_columnconfigure(2, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self._build_main()
        self._build_panel()
        self._apply_language()
        self._set_mode("pdf2png", force=True)

        self.bind("<F5>", lambda e: self._on_refresh())
        self.bind("<Escape>", self._on_escape)
        for k in ("Control_L", "Control_R"):
            self.bind(f"<KeyPress-{k}>", lambda e: self._on_ctrl(True), add="+")
            self.bind(f"<KeyRelease-{k}>", lambda e: self._on_ctrl(False), add="+")
        if HAS_DND:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop)
            self.dnd_bind("<<DropEnter>>", self._on_drop_enter)
            self.dnd_bind("<<DropPosition>>", self._on_drop_position)
            self.dnd_bind("<<DropLeave>>", self._on_drop_leave)
        self._panel_x = self._panel_w
        self._list_lock = ScrollableWidthLock(self.list)
        self._resize = ResizeGovernor(self, self._resize_begin, self._resize_end, armed=False)
        self.after(500, self._resize.arm)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(40, self._poll)
        self.after(700, self._prewarm_panel)

    def tr(self, key, **kw):
        s = S[key][self.li]
        return s.format(**kw) if kw else s

    def T(self, widget, key, prop="text"):
        self._i18n.append((widget, key, prop))
        widget.configure(**{prop: self.tr(key)})
        return widget

    def animate(self, ms, fn, on_done=None, ease=ease_out):
        t0 = time.perf_counter()
        frame_ms = FRAME_MS
        self._anim_active += 1

        def finish():
            self._anim_active = max(0, self._anim_active - 1)

        def step():
            nonlocal frame_ms
            now = time.perf_counter()
            t = min((now - t0) * 1000 / ms, 1.0)
            try:
                fn(ease(t))
            except (tk.TclError, AttributeError, ValueError):
                finish()
                return
            if t < 1.0:
                spent = (time.perf_counter() - now) * 1000
                frame_ms = SLOW_FRAME_MS if spent > FRAME_MS * 0.6 else FRAME_MS
                self.after(max(1, int(frame_ms - spent)), step)
                return
            finish()
            if on_done:
                try:
                    on_done()
                except (tk.TclError, AttributeError):
                    pass
        step()

    def _tween(self, widget, prop, c1, c2, ms=170, final=None):
        self.animate(ms, lambda t: widget.configure(**{prop: mix(c1, c2, t)}),
                     on_done=(lambda: widget.configure(**{prop: final})) if final else None)

    def _card(self, parent):
        return ctk.CTkFrame(parent, corner_radius=12, fg_color=SURFACE, border_width=1, border_color=BORDER)

    def _entry(self, parent):
        return ctk.CTkEntry(parent, height=36, corner_radius=10, border_width=1, border_color=BORDER,
                            fg_color=SURFACE2, text_color=TEXT, placeholder_text_color=MUTED,
                            font=self.f_base)

    def _segmented(self, parent, command):
        return ctk.CTkSegmentedButton(parent, height=34, corner_radius=10, font=self.f_base,
                                      fg_color=TRACK, selected_color=SEG_ON, selected_hover_color=SEG_ON,
                                      unselected_color=TRACK, unselected_hover_color=SEG_HOVER,
                                      text_color=TEXT, values=["-"], command=command)

    def _slider(self, parent, a, b, steps, command):
        sl = ctk.CTkSlider(parent, from_=a, to=b, number_of_steps=steps, command=command, height=16,
                           progress_color=ACCENT, button_color=ACCENT, button_hover_color=ACCENT_HOVER,
                           fg_color=BORDER)
        self._sliders.append(sl)
        return sl

    def _icon_button(self, parent, icon, tip, command=None, size=34, isize=18, color=MUTED, kind="ghost"):
        b = ctk.CTkButton(parent, text="", width=size, height=size, corner_radius=9, command=command,
                          image=self.icons.get(icon, color, isize), **STYLES[kind])
        self.tips.attach(b, lambda: self.tr(tip))
        return b

    def _style_action_button(self, button, icon, active, size=18, kind="soft"):
        if active:
            button.configure(
                fg_color=ACCENT_SOFT, hover_color=ACCENT_SOFT, text_color=ACCENT,
                border_width=1, border_color=ACCENT,
                image=self.icons.get(icon, ACCENT, size))
            return
        if kind == "soft":
            button.configure(
                fg_color=SURFACE2, hover_color=HOVER, text_color=TEXT,
                border_width=1, border_color=BORDER,
                image=self.icons.get(icon, TEXT, size))
        else:
            button.configure(
                fg_color="transparent", hover_color=HOVER, text_color=TEXT,
                border_width=0, image=self.icons.get(icon, MUTED, size))

    def _canvas(self):
        return getattr(self.list, "_parent_canvas", None)

    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, width=236, corner_radius=0, fg_color=SURFACE)
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_propagate(False)
        sb.grid_columnconfigure(0, weight=1)
        ctk.CTkFrame(self, width=1, corner_radius=0, fg_color=BORDER).grid(row=0, column=1, sticky="ns")

        brand = ctk.CTkFrame(sb, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=20, pady=(24, 12))
        self.logo_lbl = ctk.CTkLabel(brand, text="", image=self.icons.get("logo", ACCENT, 32))
        self.logo_lbl.pack(side="left")
        ctk.CTkLabel(brand, text="PyPDF Ui", font=self.f_bold, text_color=TEXT).pack(side="left", padx=(10, 0))

        r = 1
        for sec, keys in GROUPS:
            lbl = ctk.CTkLabel(sb, text="", font=self.f_small, text_color=MUTED, anchor="w")
            lbl.grid(row=r, column=0, sticky="w", padx=22, pady=(14, 4))
            self.T(lbl, sec)
            r += 1
            for k in keys:
                b = ctk.CTkButton(sb, text="", height=42, corner_radius=10, anchor="w", border_spacing=12,
                                  font=self.f_base, fg_color=SURFACE, hover_color=HOVER, text_color=TEXT,
                                  border_width=0, border_color=ACCENT,
                                  image=self.icons.get(MODES[k]["icon"], MUTED, 24), compound="left",
                                  command=lambda k=k: self._set_mode(k))
                b.grid(row=r, column=0, sticky="ew", padx=12, pady=2)
                self.T(b, "m_" + k)
                self.mode_btns[k] = b
                r += 1
        sb.grid_rowconfigure(r, weight=1)
        self.options_btn = ctk.CTkButton(
            sb, text="", height=42, corner_radius=10, anchor="w", border_spacing=12,
            font=self.f_base, image=self.icons.get("options", MUTED, 24), compound="left",
            command=self._toggle_options, **STYLES["ghost"])
        self.options_btn.grid(row=r + 1, column=0, sticky="ew", padx=12, pady=(0, 18))
        self.T(self.options_btn, "options")

    def _build_main(self):
        m = ctk.CTkFrame(self, fg_color="transparent")
        m.grid(row=0, column=2, sticky="nsew", padx=28, pady=24)
        m.grid_columnconfigure(0, weight=1)
        m.grid_rowconfigure(2, weight=1)

        head = ctk.CTkFrame(m, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew")
        self.title_lbl = ctk.CTkLabel(head, text="", font=self.f_title, text_color=TEXT, anchor="w")
        self.title_lbl.pack(anchor="w")
        self.hint_lbl = ctk.CTkLabel(head, text="", font=self.f_small, text_color=MUTED, anchor="w")
        self.hint_lbl.pack(anchor="w", pady=(2, 0))

        bar = self._card(m)
        bar.grid(row=1, column=0, sticky="ew", pady=(16, 12))
        bar.grid_columnconfigure(0, weight=1)
        self.folder_entry = self._entry(bar)
        self.folder_entry.grid(row=0, column=0, padx=(12, 8), pady=10, sticky="ew")
        self.folder_entry.bind("<Return>", lambda e: self._set_folder(Path(self.folder_entry.get())))
        self.browse_btn = self._icon_button(bar, "folder", "t_browse", self._browse, color=TEXT, kind="soft")
        self.browse_btn.grid(row=0, column=1, padx=(0, 6))
        self.refresh_btn = self._icon_button(bar, "refresh", "t_refresh", self._on_refresh,
                                             color=TEXT, kind="soft")
        self.refresh_btn.grid(row=0, column=2, padx=(0, 12))

        self.list_card = self._card(m)
        self.list_card.grid(row=2, column=0, sticky="nsew")
        self.list_card.grid_rowconfigure(0, weight=1)
        self.list_card.grid_columnconfigure(0, weight=1)
        self.list = ctk.CTkScrollableFrame(self.list_card, fg_color="transparent", corner_radius=0,
                                           scrollbar_button_color=BORDER, scrollbar_button_hover_color=MUTED)
        self.list.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        self.list.grid_columnconfigure(0, weight=1)

        self.empty = ctk.CTkFrame(self.list, fg_color="transparent")
        ctk.CTkLabel(self.empty, text="", image=self.icons.get("folder", MUTED, 48)).pack()
        self.empty_t = ctk.CTkLabel(self.empty, text="", font=self.f_bold, text_color=TEXT)
        self.empty_t.pack(pady=(12, 2))
        self.empty_h = ctk.CTkLabel(self.empty, text="", font=self.f_small, text_color=MUTED, wraplength=380)
        self.empty_h.pack()
        self.T(self.empty_t, "empty_t")
        self.T(self.empty_h, "empty_h")
        self._ins = ctk.CTkFrame(self.list, height=3, corner_radius=2, fg_color=ACCENT)
        self._ins_w = 0

        tb = ctk.CTkFrame(m, fg_color="transparent")
        tb.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        for key, val in (("select_all", True), ("select_none", False)):
            b = ctk.CTkButton(tb, text="", height=30, width=120, corner_radius=8, font=self.f_small,
                              command=lambda v=val: self._select_all(v), **STYLES["soft"])
            b.pack(side="left", padx=(0, 8))
            self.T(b, key)
        self.count_lbl = ctk.CTkLabel(tb, text="", font=self.f_small, text_color=MUTED)
        self.count_lbl.pack(side="right")

        self.opt = self._build_options(m)
        self.opt.grid(row=4, column=0, sticky="ew", pady=12)

        act = ctk.CTkFrame(m, fg_color="transparent")
        act.grid(row=5, column=0, sticky="ew")
        act.grid_columnconfigure(0, weight=1)
        self.run_btn = ctk.CTkButton(act, text="", height=46, corner_radius=12, font=self.f_bold,
                                     command=self._run, **STYLES["primary"])
        self.run_btn.grid(row=0, column=0, sticky="ew")
        self.open_output_btn = self._icon_button(
            act, "open_output", "t_open", lambda: open_folder(self.last_out),
            size=46, isize=22, color=TEXT, kind="soft")
        self.open_output_btn.grid(row=0, column=1, padx=(8, 0))
        self._style_action_button(self.open_output_btn, "open_output", active=True, size=22)
        self.progress = ctk.CTkProgressBar(act, height=6, corner_radius=3, progress_color=ACCENT, fg_color=BORDER)
        self.progress.set(0)
        self.progress.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(14, 8))
        self.status = ctk.CTkLabel(act, text="", image=self._blank, compound="left", anchor="w",
                                   font=self.f_small, text_color=MUTED)
        self.status.grid(row=2, column=0, columnspan=2, sticky="ew")

    def _build_options(self, parent):
        o = self._card(parent)
        o.grid_columnconfigure(0, weight=1)
        o.grid_rowconfigure(0, weight=1)
        self._panels = {}

        def panel(key):
            f = ctk.CTkFrame(o, fg_color="transparent")
            f.grid(row=0, column=0, sticky="nsew", padx=16, pady=12)
            f.grid_columnconfigure(0, minsize=176)
            f.grid_columnconfigure(1, weight=1)
            f.grid_rowconfigure(0, minsize=38)
            f.grid_rowconfigure(1, minsize=36)
            self._panels[key] = f
            return f

        def lbl(parent, key=None, hint=False):
            w = ctk.CTkLabel(parent, text="", anchor="w",
                             font=self.f_small if hint else self.f_base,
                             text_color=MUTED if hint else TEXT)
            return self.T(w, key) if key else w

        p = panel("dpi")
        self.dpi_lbl = lbl(p)
        self.dpi_lbl.grid(row=0, column=0, sticky="w")
        self.dpi_slider = self._slider(p, 72, 300, 19, self._on_dpi)
        self.dpi_slider.set(150)
        self.dpi_slider.grid(row=0, column=1, sticky="ew")
        self.dpi_hint = lbl(p, hint=True)
        self.dpi_hint.grid(row=1, column=1, sticky="w")
        p = panel("name")
        lbl(p, "o_name").grid(row=0, column=0, sticky="w")
        self.name_entry = self._entry(p)
        self.name_entry.insert(0, "merged")
        self.name_entry.grid(row=0, column=1, sticky="ew")
        self.name_entry.bind("<KeyRelease>", lambda e: self._update_hints(), add="+")
        self.name_hint = lbl(p, hint=True)
        self.name_hint.grid(row=1, column=1, sticky="w")
        p = panel("img")
        p.grid_rowconfigure(1, minsize=22)
        p.grid_rowconfigure(2, minsize=38)
        p.grid_rowconfigure(3, minsize=22)
        lbl(p, "o_name").grid(row=0, column=0, sticky="w")
        self.img_name_entry = self._entry(p)
        self.img_name_entry.insert(0, "output")
        self.img_name_entry.grid(row=0, column=1, sticky="ew")
        self.img_name_entry.bind("<KeyRelease>", lambda e: self._update_hints(), add="+")
        self.img_name_hint = lbl(p, hint=True)
        self.img_name_hint.grid(row=1, column=1, sticky="w")
        self.rate_lbl = lbl(p)
        self.rate_lbl.configure(wraplength=168, justify="left")
        self.rate_lbl.grid(row=2, column=0, sticky="w")
        self.rate_slider = self._slider(p, 0, 100, 20, self._on_rate)
        self.rate_slider.set(self.cfg["img_rate"])
        self.rate_slider.grid(row=2, column=1, sticky="ew")
        self.rate_hint = lbl(p, hint=True)
        self.rate_hint.grid(row=3, column=1, sticky="w")
        p = panel("compress")
        lbl(p, "o_level").grid(row=0, column=0, sticky="w")
        self.lvl_seg = self._segmented(p, self._on_level)
        self.lvl_seg.grid(row=0, column=1, sticky="ew")
        self.lvl_desc = lbl(p, hint=True)
        self.lvl_desc.grid(row=1, column=1, sticky="w")
        p = panel("remove")
        lbl(p, "o_pages").grid(row=0, column=0, sticky="w")
        self.pages_entry = self._entry(p)
        self.pages_entry.grid(row=0, column=1, sticky="ew")
        self.T(self.pages_entry, "ph_pages", "placeholder_text")
        lbl(p, "hp_pages", hint=True).grid(row=1, column=1, sticky="w")
        p = panel("split")
        lbl(p, "o_split").grid(row=0, column=0, sticky="w")
        self.split_seg = self._segmented(p, self._on_split_mode)
        self.split_seg.grid(row=0, column=1, sticky="ew")
        self.split_hint = lbl(p, "hp_each", hint=True)
        self.split_hint.configure(fg_color=SURFACE2, corner_radius=10, height=36,
                                  padx=12, border_width=1, border_color=BORDER)
        self.split_hint.grid(row=1, column=1, sticky="ew")
        self.split_entry = self._entry(p)
        self.split_entry.grid(row=1, column=1, sticky="ew")
        return o

    def _show_panel(self):
        self._panels[MODES[self.mode]["panel"]].tkraise()
        self._sync_split()
        self._update_hints()

    def _sync_split(self):
        (self.split_hint if self.split_mode == "each" else self.split_entry).tkraise()
        self.split_entry.configure(placeholder_text=self.tr("ph_ranges" if self.split_mode == "ranges" else "ph_every"))

    def _update_hints(self):
        dpi = int(self.dpi_slider.get())
        # self.dpi_hint.configure(text=self.tr("hp_dpi", w=round(8.27 * dpi), h=round(11.69 * dpi)))
        self.name_hint.configure(text=self.tr("hp_name", name=safe_filename(self.name_entry.get(), "merged")))
        self.img_name_hint.configure(text=self.tr("hp_name", name=safe_filename(self.img_name_entry.get(), "output")))
        rate = int(round(self.rate_slider.get()))
        quality = rate_to_quality(rate)
        self.rate_lbl.configure(text=self.tr("o_rate", n=rate))
        self.rate_hint.configure(text=self.tr("hp_rate0") if quality is None else self.tr("hp_rate", q=quality))

    def _build_panel(self):
        self._panel_w = 330
        p = ctk.CTkFrame(self, width=self._panel_w, corner_radius=0, fg_color=SURFACE,
                         border_width=1, border_color=BORDER)
        p.grid_propagate(False)
        p.grid_columnconfigure(0, weight=1)
        self.panel = p

        head = ctk.CTkFrame(p, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=22, pady=(22, 10))
        head.grid_columnconfigure(0, weight=1)
        t = ctk.CTkLabel(head, text="", font=self.f_title, text_color=TEXT, anchor="w")
        t.grid(row=0, column=0, sticky="w")
        self.T(t, "options")
        self._icon_button(head, "close", "t_close", self._close_panel, size=32).grid(row=0, column=1)

        def label(parent, key):
            w = ctk.CTkLabel(parent, text="", font=self.f_base, text_color=TEXT, anchor="w")
            return self.T(w, key)

        row = ctk.CTkFrame(p, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", padx=22, pady=(18, 0))
        row.grid_columnconfigure(0, weight=1)
        label(row, "o_size").grid(row=0, column=0, sticky="w")
        self.size_val = ctk.CTkLabel(row, text=str(self.cfg["size"]), font=self.f_small, text_color=MUTED, width=28)
        self.size_val.grid(row=0, column=1)
        sl = self._slider(p, 11, 20, 9, self._on_size)
        sl.set(self.cfg["size"])
        sl.grid(row=2, column=0, sticky="ew", padx=22, pady=(10, 0))

        row = ctk.CTkFrame(p, fg_color="transparent")
        row.grid(row=3, column=0, sticky="ew", padx=22, pady=(26, 0))
        row.grid_columnconfigure(0, weight=1)
        label(row, "o_dark").grid(row=0, column=0, sticky="w")
        self.theme_sw = ctk.CTkSwitch(row, text="", width=44, command=self._on_theme, progress_color=ACCENT,
                                      button_color="white", button_hover_color="#F0F0F0", fg_color=BORDER)
        self.theme_sw.grid(row=0, column=1)
        if self.cfg["dark"]:
            self.theme_sw.select()

        row = ctk.CTkFrame(p, fg_color="transparent")
        row.grid(row=4, column=0, sticky="ew", padx=22, pady=(26, 0))
        row.grid_columnconfigure(0, weight=1)
        label(row, "o_accent").grid(row=0, column=0, sticky="w")
        self.accent_btn = ctk.CTkButton(row, text=self._accent_text(), width=104, height=32, corner_radius=9,
                                        font=self.f_small, command=self._open_accent_dialog, border_width=1,
                                        border_color=BORDER, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                                        text_color=ON_ACCENT)
        self.accent_btn.grid(row=0, column=1)

        label(p, "o_lang").grid(row=5, column=0, sticky="w", padx=22, pady=(26, 8))
        self.lang_menu = ctk.CTkOptionMenu(
            p, values=[n for _, n in LANGS], command=self._on_lang, height=36, corner_radius=10,
            font=self.f_base, dropdown_font=self.f_base, fg_color=SURFACE2, button_color=SURFACE2,
            button_hover_color=HOVER, text_color=TEXT, dropdown_fg_color=SURFACE,
            dropdown_text_color=TEXT, dropdown_hover_color=HOVER, anchor="w")
        self.lang_menu.set(LANGS[self.li][1])
        self.lang_menu.grid(row=6, column=0, sticky="ew", padx=22)

    def _toggle_options(self):
        self._close_panel() if self._panel_open else self._open_panel()

    def _open_panel(self):
        self._panel_open = True
        self._style_action_button(self.options_btn, "options", active=True, size=24, kind="ghost")
        w = self._panel_w
        if not self.panel.winfo_ismapped():
            self._panel_x = w
            self.panel.place(relx=1.0, x=w, y=0, relheight=1.0, anchor="ne")
        self.panel.tkraise()
        self._slide_panel(0, 240, ease_out)

    def _close_panel(self):
        self._panel_open = False
        self._style_action_button(self.options_btn, "options", active=False, size=24, kind="ghost")
        self._slide_panel(self._panel_w, 180, ease_in, hide=True)

    def _slide_panel(self, target, ms, ease, hide=False):
        self._panel_tok += 1
        tok, start = self._panel_tok, self._panel_x
        span = target - start
        if span == 0:
            if hide:
                self.panel.place_forget()
            return

        def frame(t):
            if tok != self._panel_tok:
                return
            x = start + int(span * t)
            if x != self._panel_x:
                self._panel_x = x
                self.panel.place_configure(x=x)

        def done():
            if tok != self._panel_tok:
                return
            if self._panel_x != target:
                self._panel_x = target
                self.panel.place_configure(x=target)
            if hide:
                self.panel.place_forget()

        duration = max(60, ms * abs(span) // self._panel_w) if abs(span) < self._panel_w else ms
        self.animate(duration, frame, on_done=done, ease=ease)

    def _prewarm_panel(self):
        if self._panel_open or self._anim_active or self.panel.winfo_ismapped():
            return
        try:
            self.panel.place(relx=1.0, x=self._panel_w + 40, y=0, relheight=1.0, anchor="ne")
            self.update_idletasks()
        except tk.TclError:
            return
        if not self._panel_open:
            self.panel.place_forget()

    def _on_escape(self, _e=None):
        if self._drag and self._drag.get("live"):
            self._drag_finish(self._drag, cancel=True)
        elif self._panel_open:
            self._close_panel()

    def _on_size(self, v):
        v = int(round(v))
        self.cfg["size"] = v
        self.size_val.configure(text=str(v))
        if self._size_job:
            self.after_cancel(self._size_job)
        self._size_job = self.after(70, self._apply_size)
        self._save_soon()

    def _apply_size(self):
        self._size_job = None
        v = self.cfg["size"]
        with self.frozen():
            self.f_base.configure(size=v)
            self.f_bold.configure(size=v)
            self.f_small.configure(size=max(v - 2, 9))
            self.f_title.configure(size=v + 8)
            self._apply_metrics()

    def _on_theme(self):
        dark = bool(self.theme_sw.get())
        self.cfg["dark"] = dark

        def apply():
            ctk.set_appearance_mode("dark" if dark else "light")
            self._mode_cur.clear()
            self._style_modes(animate=False)

        self._crossfade(apply)
        self._save_soon()

    def _make_snapshot_overlay(self):
        if not FADE_THEME or not self.winfo_viewable() or self.state() != "normal":
            return None
        try:
            self.update_idletasks()
            x, y, w, h = self.winfo_rootx(), self.winfo_rooty(), self.winfo_width(), self.winfo_height()
            vx, vy = self.winfo_vrootx(), self.winfo_vrooty()
            if w < 64 or h < 64:
                return None
            if x < vx or y < vy or x + w > vx + self.winfo_vrootwidth() or y + h > vy + self.winfo_vrootheight():
                return None
            shot = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)
            if shot.size != (w, h):
                shot = shot.resize((w, h), Image.Resampling.BILINEAR)
            ov = tk.Toplevel(self)
            ov.withdraw()
            try:
                ov.overrideredirect(True)
                ov.attributes("-alpha", 1.0)
                ov.geometry(f"{w}x{h}+{x}+{y}")
                photo = ImageTk.PhotoImage(shot)
                lbl = tk.Label(ov, image=photo, bd=0, highlightthickness=0)
                lbl.image = photo
                lbl.pack()
                ov.transient(self)
                ov.deiconify()
                ov.update_idletasks()
                ov.update()
            except Exception:
                ov.destroy()
                return None
            return ov
        except Exception:
            return None

    def _end_fade(self):
        self._fade_tok += 1
        ov, self._fade_overlay = self._fade_overlay, None
        if ov is not None:
            try:
                ov.destroy()
            except tk.TclError:
                pass

    def _crossfade(self, apply, ms=THEME_FADE_MS):
        self._end_fade()
        overlay = self._make_snapshot_overlay()
        try:
            with self.frozen():
                apply()
        except BaseException:
            if overlay is not None:
                overlay.destroy()
            raise
        if overlay is None:
            return
        self._fade_overlay = overlay
        tok = self._fade_tok

        def frame(t):
            if tok == self._fade_tok:
                overlay.attributes("-alpha", max(0.0, 1.0 - t))

        def done():
            if tok == self._fade_tok:
                self._end_fade()

        self.update_idletasks()
        self.animate(ms, frame, on_done=done, ease=ease_inout)

    def _accent_text(self):
        return self.cfg["accent"] or colors.DEFAULT_ACCENT_LIGHT

    def _open_accent_dialog(self):
        dlg = self._accent_dlg
        if dlg is not None:
            try:
                if dlg.winfo_exists():
                    dlg.focus_force()
                    return
            except tk.TclError:
                pass
        palette = dict(surface=SURFACE, surface2=SURFACE2, border=BORDER, text=TEXT, muted=MUTED, danger=DANGER,
                       accent=ACCENT, accent_hover=ACCENT_HOVER, on_accent=ON_ACCENT, hover=HOVER)
        icon = ICON_DIR / "app.ico" if sys.platform == "win32" else None
        self._accent_dlg = ColorPicker(
            self, tr=self.tr, palette=palette, fonts=(self.f_base, self.f_small, self.f_bold, self.f_title),
            initial=self._accent_text(), on_apply=self._on_accent_pick, icon=icon)

    def _on_accent_pick(self, value):
        value = colors.canonical_accent(value)
        if value == self.cfg["accent"]:
            return
        self.cfg["accent"] = value
        set_accent(value)
        self._apply_accent()
        self._save_soon()

    def _apply_accent(self):
        with self.frozen():
            for sl in self._sliders:
                sl.configure(progress_color=ACCENT, button_color=ACCENT, button_hover_color=ACCENT_HOVER)
            self.theme_sw.configure(progress_color=ACCENT)
            self.progress.configure(progress_color=ACCENT)
            self._ins.configure(fg_color=ACCENT)
            self.icons.clear()
            self.logo_lbl.configure(image=self.icons.get("logo", ACCENT, 32))
            self._style_action_button(self.browse_btn, "folder", active=self._browse_active)
            self._style_action_button(self.open_output_btn, "open_output", active=True, size=22)
            self._style_action_button(self.options_btn, "options", active=self._panel_open, size=24, kind="ghost")
            self._style_action_button(self.refresh_btn, "refresh", active=self._refresh_accent_job is not None)
            for b in self.mode_btns.values():
                b.configure(border_color=ACCENT)
            self._mode_cur.clear()
            self._style_modes(animate=False)
            if not self.busy:
                self.run_btn.configure(**STYLES["primary"])
            self.accent_btn.configure(text=self._accent_text(), fg_color=ACCENT, hover_color=ACCENT_HOVER,
                                      text_color=ON_ACCENT)
            for it in self.items:
                if it.chk is not None:
                    it.chk.configure(fg_color=ACCENT, hover_color=ACCENT_HOVER, checkmark_color=ON_ACCENT)
            self._update_numbers()

    def _resize_begin(self):
        self._resizing = True
        if self._limit_job:
            self.after_cancel(self._limit_job)
            self._limit_job = None
        self._list_lock.lock()

    def _resize_end(self):
        self._resizing = False
        with self.frozen():
            self._list_lock.unlock()
        self._fit_names(force=True)

    def _on_lang(self, value):
        self.li = next(i for i, (_, n) in enumerate(LANGS) if n == value)
        self.cfg["lang"] = LANG_CODES[self.li]
        with self.frozen():
            self._apply_language()
        self._save_soon()

    def _save_soon(self):
        if self._save_job:
            self.after_cancel(self._save_job)
        self._save_job = self.after(400, self._save)

    def _save(self):
        self._save_job = None
        settings.save_settings(self.cfg)

    def _on_close(self):
        if self.busy:
            if not messagebox.askyesno(self.tr("q_close_t"), self.tr("q_close"), icon="warning", parent=self):
                return
            self.cancel.set()
            if self._worker is not None:
                self._worker.join(timeout=6)
        if self._save_job:
            self.after_cancel(self._save_job)
        self._save()
        self.destroy()

    def _apply_language(self):
        for w, k, p in self._i18n:
            w.configure(**{p: self.tr(k)})
        self._mode_texts()
        self.lvl_seg.configure(values=[self.tr("lv_" + k) for k in LEVEL_KEYS])
        self.lvl_seg.set(self.tr("lv_" + self.level))
        self.lvl_desc.configure(text=self.tr("lvd_" + self.level))
        self.split_seg.configure(values=[self.tr("sp_" + k) for k in SPLIT_KEYS])
        self.split_seg.set(self.tr("sp_" + self.split_mode))
        self._sync_split()
        self._on_dpi(self.dpi_slider.get())
        self._update_hints()
        self._apply_metrics()
        for it in self.items:
            self._refresh_row_texts(it)
        self._after_change()
        self._paint_status()

    def _mode_texts(self):
        self.title_lbl.configure(text=self.tr("m_" + self.mode))
        self.hint_lbl.configure(text=self.tr("h_" + self.mode))
        if self.busy:
            self.run_btn.configure(text=self.tr("stopping" if self.cancel.is_set() else "stop"))
        else:
            self.run_btn.configure(text=self.tr("r_" + self.mode))

    def _key_of(self, value, prefix, keys):
        return next((k for k in keys if self.tr(prefix + k) == value), keys[0])

    def _on_level(self, value):
        self.level = self._key_of(value, "lv_", LEVEL_KEYS)
        self.lvl_desc.configure(text=self.tr("lvd_" + self.level))

    def _on_split_mode(self, value):
        self.split_mode = self._key_of(value, "sp_", SPLIT_KEYS)
        self._sync_split()

    def _on_rate(self, v):
        self.cfg["img_rate"] = int(round(v))
        self._update_hints()
        self._save_soon()

    def _on_dpi(self, v):
        self.dpi_lbl.configure(text=self.tr("o_dpi", n=int(v)))
        self._update_hints()

    def _style_modes(self, animate=True):
        for k, b in self.mode_btns.items():
            on = k == self.mode
            b.configure(text_color=ACCENT if on else TEXT, hover_color=ACCENT_SOFT if on else HOVER,
                        image=self.icons.get(MODES[k]["icon"], ACCENT if on else MUTED, 24))
            end = hexc(ACCENT_SOFT if on else SURFACE)
            start = self._mode_cur.get(k, hexc(SURFACE))
            self._mode_cur[k] = end
            if animate and start != end:
                self._tween(b, "fg_color", start, end)
            else:
                b.configure(fg_color=end)

    def _set_mode(self, key, force=False):
        if self.busy or (key == self.mode and not force):
            return
        with self.frozen():
            self.mode = key
            self._style_modes(animate=not force)
            self._mode_texts()
            self._show_panel()
            self._set_progress(0)
            self._say("ready")
            self._load(reset=True)

    def _browse(self):
        if self.busy:
            return
        self._browse_active = True
        self._style_action_button(self.browse_btn, "folder", active=True)
        try:
            d = filedialog.askdirectory(initialdir=self.folder)
        finally:
            self._browse_active = False
            self._style_action_button(self.browse_btn, "folder", active=False)
        if d:
            self._set_folder(Path(d))

    def _set_folder(self, path: Path):
        if self.busy:
            self.folder_entry.delete(0, "end")
            self.folder_entry.insert(0, str(self.folder))
            return
        if path.is_dir():
            self.folder = path
            self.cfg["folder"] = str(path)
            self._save_soon()
            with self.frozen():
                self._load(reset=True)
        else:
            self._say("bad_dir", "error")

    def _load(self, reset=False, animate=True, checked=True):
        self.folder_entry.delete(0, "end")
        self.folder_entry.insert(0, str(self.folder))
        ext = MODES[self.mode]["ext"]
        try:
            found = sorted((p for p in self.folder.iterdir() if p.is_file() and p.suffix.lower() in ext),
                           key=natural_key)
        except OSError:
            found = []
            self._say("bad_dir", "error")
        if reset:
            self._clear_items()
            cv = self._canvas()
            if cv is not None:
                cv.yview_moveto(0)
        else:
            for it in [i for i in self.items if not i.path.exists()]:
                self._drop_item(it)
        have = {it.path for it in self.items}
        self._add_items([Item(p, checked) for p in found if p not in have], animate=animate and reset)
        self._scan_pages()

    def _on_refresh(self):
        if self.busy:
            return
        if self._refresh_accent_job:
            self.after_cancel(self._refresh_accent_job)
        self._style_action_button(self.refresh_btn, "refresh", active=True)

        def finish_refresh_accent():
            self._refresh_accent_job = None
            self._style_action_button(self.refresh_btn, "refresh", active=False)

        self._refresh_accent_job = self.after(750, finish_refresh_accent)
        self.animate(480, lambda t: self.refresh_btn.configure(
            image=self.icons.get("refresh", ACCENT, 18, -360 * t)),
                     on_done=lambda: self.refresh_btn.configure(
                         image=self.icons.get("refresh", ACCENT, 18)))
        with self.frozen():
            self._load(reset=False, animate=False)
        self._say("refreshed", "ok")
        self._refresh_status_job = self.after(750, self._expire_refresh_status)

    def _clear_items(self):
        self._pending.clear()
        for it in self.items:
            it.dead = True
            if it.row is not None:
                it.row.destroy()
        self.items = []

    def _drop_item(self, it):
        it.dead = True
        if it in self.items:
            self.items.remove(it)
        if it.row is not None:
            it.row.destroy()
            it.row = None

    def _add_items(self, new, index=None, animate=False):
        if index is None:
            self.items.extend(new)
        else:
            self.items[index:index] = new
        self._pending.extend(new)
        self._pump_rows(first=True, animate=animate)

    def _pump_rows(self, first, animate):
        budget, fade = (16 if first else 10), []
        while self._pending and budget:
            it = self._pending.pop(0)
            if it.dead or it.row is not None:
                continue
            self._create_row(it, fade=animate and first)
            if animate and first:
                fade.append(it)
            budget -= 1
        self._regrid()
        self._after_change()
        self._limit_soon()
        if fade:
            self._fade_in(fade)
        if self._pending:
            self.after(10, lambda: self._pump_rows(False, False))

    def _regrid(self):
        for i, it in enumerate(self.items):
            if it.row is not None:
                it.row.grid(row=i, column=0, sticky="ew", pady=3, padx=(2, 4))

    def _fade_in(self, batch):
        c0, c1 = hexc(SURFACE2), hexc(TEXT)
        total = 160 + 24 * len(batch)

        def frame(t):
            ms = t * total
            for j, it in enumerate(batch):
                if it.name is None:
                    continue
                k = min(1.0, max(0.0, (ms - j * 24) / 160))
                it.name.configure(text_color=mix(c0, c1, k))
        self.animate(total, frame, ease=lambda t: t,
                     on_done=lambda: [it.name.configure(text_color=TEXT) for it in batch if it.name is not None])

    def _metrics(self):
        s = self.cfg["size"]
        return int(s * 8.4), int(s * 6.2)

    def _apply_metrics(self):
        nw, mw = self._metrics()
        for it in self.items:
            if it.num is not None:
                it.num.configure(width=nw)
            if it.meta is not None:
                it.meta.configure(width=mw)
        self._fit_names(force=True)

    def _limit_soon(self):
        if self._resizing:
            return
        if self._limit_job:
            self.after_cancel(self._limit_job)
        self._limit_job = self.after(120, self._fit_when_idle)

    def _fit_when_idle(self):
        self._limit_job = None
        if self._resizing or self._anim_active:
            self._limit_job = self.after(80, self._fit_when_idle)
            return
        self._fit_names()

    def _fit_text(self, name, ordered):
        meas = self._avail.get(ordered)
        if meas is None:
            return shorten(name, 44)
        font, avail = meas
        if font.measure(name) <= avail:
            return name
        lo, hi = 4, len(name)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if font.measure(shorten(name, mid)) <= avail:
                lo = mid
            else:
                hi = mid - 1
        return shorten(name, lo)

    def _fit_names(self, force=False):
        self._limit_job = None
        ref = next((it for it in self.items if it.row is not None and it.name is not None), None)
        if ref is None:
            return
        self.update_idletasks()
        right = ref.num or ref.meta
        avail = right.winfo_x() - ref.name.winfo_x() - 18
        if avail < 60:
            return
        try:
            font = tkfont.Font(font=ref.name._label.cget("font"))
        except Exception:
            font = self.f_base
        ordered = MODES[self.mode]["ordered"]
        old = self._avail.get(ordered)
        self._avail[ordered] = (font, avail)
        if force or old is None or old[1] != avail or old[0].actual() != font.actual():
            for it in self.items:
                if it.name is not None:
                    t = self._fit_text(it.path.name, ordered)
                    if it.name.cget("text") != t:
                        it.name.configure(text=t)

    def _create_row(self, it, fade=False):
        ordered = MODES[self.mode]["ordered"]
        nw, mw = self._metrics()
        row = ctk.CTkFrame(self.list, corner_radius=10, fg_color=SURFACE2, border_width=1, border_color=BORDER)
        row.grid_columnconfigure(3, weight=1)
        row.grid_rowconfigure(0, minsize=44)
        it.row = row

        if ordered:
            grip = ctk.CTkLabel(row, text="", width=28, image=self.icons.get("grip", MUTED, 20))
            grip.grid(row=0, column=0, padx=(8, 0), pady=8)
            try:
                grip.configure(cursor="fleur")
            except tk.TclError:
                pass
            self.tips.attach(grip, lambda: self.tr("t_drag"))
            grip.bind("<ButtonPress-1>", lambda e, it=it, g=grip: self._grip_press(it, g, e), add="+")
            grip.bind("<B1-Motion>", self._grip_motion, add="+")
            grip.bind("<ButtonRelease-1>", self._grip_release, add="+")

        it.chk = ctk.CTkCheckBox(row, text="", width=26, checkbox_width=20, checkbox_height=20, corner_radius=6,
                                 border_width=2, fg_color=ACCENT, hover_color=ACCENT_HOVER, border_color=MUTED,
                                 checkmark_color=ON_ACCENT, variable=it.var, command=self._on_check)
        it.chk.grid(row=0, column=1, padx=(10, 0))
        kind = FILE_ICON["img" if it.path.suffix.lower() in IMG_EXT else "pdf"]
        ctk.CTkLabel(row, text="", image=self.icons.get(kind, MUTED, 24)).grid(row=0, column=2, padx=(8, 2))
        name = ctk.CTkLabel(row, text=self._fit_text(it.path.name, ordered), anchor="w",
                            font=self.f_base, text_color=hexc(SURFACE2) if fade else TEXT)
        name.grid(row=0, column=3, sticky="ew", padx=(6, 8))
        name.bind("<Button-1>", lambda e, v=it.var: (v.set(not v.get()), self._on_check()))
        it.name = name

        col = 4
        if ordered:
            it.num = ctk.CTkLabel(row, text="", font=self.f_small, text_color=ACCENT, width=nw, anchor="e")
            it.num.grid(row=0, column=col, padx=(0, 4))
            col += 1
        it.meta = ctk.CTkLabel(row, text=self._meta_text(it), font=self.f_small, text_color=MUTED,
                               width=mw, anchor="e")
        it.meta.grid(row=0, column=col, padx=(0, 10))
        col += 1
        if ordered:
            for icon, d in (("arrow_up", -1), ("arrow_down", 1)):
                self._icon_button(row, icon, "t_order", lambda it=it, d=d: self._move(it, d),
                                  size=28, isize=18).grid(row=0, column=col, padx=1)
                col += 1
        self._icon_button(row, "close", "t_remove", lambda it=it: self._remove(it),
                          size=28, isize=16).grid(row=0, column=col, padx=(1, 8))

    def _meta_text(self, it) -> str:
        p = it.path
        if self.mode == "compress" or p.suffix.lower() != ".pdf":
            try:
                return human(p.stat().st_size)
            except OSError:
                return ""
        c = self._pages.get(p)
        if c is None:
            return "…"
        if not c[1]:
            return ""
        return self.tr("pages1") if c[1] == 1 else self.tr("pages", n=c[1])

    def _refresh_row_texts(self, it):
        if it.meta is not None:
            it.meta.configure(text=self._meta_text(it))

    def _scan_pages(self):
        self._scan_gen += 1
        gen = self._scan_gen
        if self.mode == "compress":
            return

        def stale(p):
            c = self._pages.get(p)
            try:
                return c is None or c[0] != p.stat().st_mtime_ns
            except OSError:
                return False

        todo = list(dict.fromkeys(it.path for it in self.items if it.path.suffix.lower() == ".pdf" and stale(it.path)))
        if not todo:
            return

        def work():
            for p in todo:
                if gen != self._scan_gen:
                    return
                try:
                    mt = p.stat().st_mtime_ns
                    n = count_pages(p)
                except Exception:
                    mt, n = 0, 0
                self.q.put(("pages", p, (mt, n)))
        threading.Thread(target=work, daemon=True).start()

    def _after_change(self):
        if self.items:
            self.empty.grid_remove()
        else:
            self.empty.grid(row=0, column=0, pady=(56, 0))
        self._update_count()
        self._update_numbers()

    def _on_check(self):
        self._update_count()
        self._update_numbers()

    def _update_count(self):
        n = sum(it.var.get() for it in self.items)
        self.count_lbl.configure(text=self.tr("count", n=n, t=len(self.items)))

    def _update_numbers(self):
        if not MODES[self.mode]["ordered"]:
            return
        key, n = MODES[self.mode]["num"], 0
        for it in self.items:
            if it.num is None:
                continue
            if it.var.get():
                n += 1
                it.num.configure(text=self.tr(key, n=n), text_color=ACCENT)
            else:
                it.num.configure(text=self.tr("excl"), text_color=MUTED)

    def _select_all(self, val):
        for it in self.items:
            it.var.set(val)
        self._on_check()

    def _move(self, it, d):
        i = self.items.index(it)
        j = i + d
        if 0 <= j < len(self.items):
            self.items[i], self.items[j] = self.items[j], self.items[i]
            self._regrid()
            self._update_numbers()
            self._flash(it)
            self._scroll_to(it)

    def _remove(self, it):
        self._drop_item(it)
        self._regrid()
        self._after_change()

    def _flash(self, it):
        if it.row is not None:
            self._tween(it.row, "border_color", hexc(ACCENT), hexc(BORDER), ms=450, final=BORDER)

    def _scroll_to(self, it):
        cv = self._canvas()
        if cv is None or it.row is None:
            return
        self.update_idletasks()
        top, h = it.row.winfo_y(), it.row.winfo_height()
        total = max(1, self.list.winfo_height())
        view_top, view_h = cv.canvasy(0), cv.winfo_height()
        if top < view_top:
            cv.yview_moveto(max(0.0, (top - 8) / total))
        elif top + h > view_top + view_h:
            cv.yview_moveto(min(1.0, (top + h - view_h + 8) / total))

    def _on_ctrl(self, down):
        self._ctrl = down
        d = self._drag
        if d and d.get("live"):
            self._drag_update(d)

    def _drag_abort(self):
        d, self._drag = self._drag, None
        if not d:
            return
        if d.get("job"):
            self.after_cancel(d["job"])
        if d.get("ghost") is not None:
            try:
                d["ghost"].destroy()
            except tk.TclError:
                pass
        if d["item"].name is not None:
            d["item"].name.configure(text_color=TEXT)
        self._hide_indicator()

    def _grip_press(self, it, grip, e):
        self._drag_abort()
        self._drag = dict(item=it, grip=grip, x0=e.x_root, y0=e.y_root, last=(e.x_root, e.y_root),
                          live=False, ghost=None, ins=0, valid=True, noop=False, copy=False, job=None)

    def _grip_motion(self, e):
        d = self._drag
        if not d:
            return
        d["last"] = (e.x_root, e.y_root)
        if not d["live"]:
            if abs(e.x_root - d["x0"]) < DRAG_THRESHOLD and abs(e.y_root - d["y0"]) < DRAG_THRESHOLD:
                return
            self._drag_begin(d)
        self._ctrl = bool(e.state & 0x4)
        self._drag_update(d)

    def _grip_release(self, e):
        d = self._drag
        if not d:
            return
        if not d["live"]:
            self._drag = None
            return
        self._drag_finish(d)

    def _drag_begin(self, d):
        d["live"] = True
        self.tips._hide()
        d["ghost"] = self._make_ghost(d["item"])
        if d["item"].name is not None:
            d["item"].name.configure(text_color=MUTED)
        self._drag_tick()

    def _make_ghost(self, it):
        g = tk.Toplevel(self)
        g.withdraw()
        g.overrideredirect(True)
        for opt, val in (("-topmost", True), ("-alpha", 0.94)):
            try:
                g.attributes(opt, val)
            except tk.TclError:
                pass
        bg, ac, tx = hexc(SURFACE), hexc(ACCENT), hexc(TEXT)
        frame = tk.Frame(g, bg=bg, highlightthickness=1, highlightbackground=ac, highlightcolor=ac)
        frame.pack()
        kind = FILE_ICON["img" if it.path.suffix.lower() in IMG_EXT else "pdf"]
        photo = ImageTk.PhotoImage(self.icons.pil(kind, ACCENT, 26))
        ico = tk.Label(frame, image=photo, bg=bg)
        ico.image = photo
        ico.pack(side="left", padx=(10, 6), pady=8)
        tk.Label(frame, text=shorten(it.path.name, 34), bg=bg, fg=tx, font=self.f_base).pack(side="left", padx=(0, 12))
        badge = tk.Label(frame, text="", bg=ac, fg="white", font=self.f_small, padx=8, pady=2)
        badge.pack(side="left", padx=(0, 10))
        g._parts = (frame, badge)
        return g

    def _drop_index(self, y_root):
        for j, it in enumerate(self.items):
            r = it.row
            if r is not None and y_root < r.winfo_rooty() + r.winfo_height() / 2:
                return j
        return len(self.items)

    def _show_indicator(self, ins):
        rows = [it.row for it in self.items if it.row is not None]
        if not rows:
            y = 4
        elif ins < len(self.items) and self.items[ins].row is not None:
            y = self.items[ins].row.winfo_y() - 5
        else:
            y = rows[-1].winfo_y() + rows[-1].winfo_height() + 2
        w = max(10, self.list.winfo_width() - 10)
        if w != self._ins_w:
            self._ins.configure(width=w, height=3)
            self._ins_w = w
        self._ins.place(x=2, y=max(0, y))
        self._ins.tkraise()
        return y

    def _hide_indicator(self):
        self._ins.place_forget()

    def _inside_list(self, x, y):
        c = self.list_card
        return c.winfo_rootx() <= x <= c.winfo_rootx() + c.winfo_width() and \
            c.winfo_rooty() <= y <= c.winfo_rooty() + c.winfo_height()

    def _drag_update(self, d):
        x, y = d["last"]
        it = d["item"]
        d["copy"] = self._ctrl
        d["valid"] = self._inside_list(x, y)
        idx = self.items.index(it) if it in self.items else 0
        pos = 1
        d["noop"] = False
        if d["valid"]:
            d["ins"] = self._drop_index(y)
            if d["copy"]:
                pos = d["ins"] + 1
            else:
                d["noop"] = d["ins"] in (idx, idx + 1)
                pos = d["ins"] - (1 if d["ins"] > idx else 0) + 1
            if d["noop"]:
                self._hide_indicator()
            else:
                self._show_indicator(d["ins"])
        else:
            self._hide_indicator()
        g = d["ghost"]
        frame, badge = g._parts
        col = hexc(DANGER if not d["valid"] else ACCENT)
        frame.configure(highlightbackground=col, highlightcolor=col)
        badge.configure(bg=col, text=self.tr("d_no") if not d["valid"] else self.tr("d_same") if d["noop"]
                        else self.tr("d_copy" if d["copy"] else "d_move", n=pos))
        try:
            d["grip"].configure(cursor=NO_CURSOR if not d["valid"] else "fleur")
        except tk.TclError:
            pass
        g.geometry(f"+{x + 16}+{y + 12}")
        g.deiconify()

    def _drag_tick(self):
        d = self._drag
        if not d or not d.get("live"):
            return
        cv = self._canvas()
        x, y = d["last"]
        if cv is not None and cv.winfo_rootx() <= x <= cv.winfo_rootx() + cv.winfo_width():
            top, bot, zone = cv.winfo_rooty(), cv.winfo_rooty() + cv.winfo_height(), 40
            if top - 50 < y < top + zone:
                cv.yview_scroll(-min(3, 1 + int((top + zone - y) / 20)), "units")
                self._drag_update(d)
            elif bot - zone < y < bot + 50:
                cv.yview_scroll(min(3, 1 + int((y - (bot - zone)) / 20)), "units")
                self._drag_update(d)
        d["job"] = self.after(30, self._drag_tick)

    def _drag_finish(self, d, cancel=False):
        if d.get("done"):
            return
        d["done"] = True
        d["live"] = False
        if d["job"]:
            self.after_cancel(d["job"])
        it, g = d["item"], d["ghost"]
        commit = d["valid"] and not d["noop"] and not cancel
        self._hide_indicator()
        try:
            d["grip"].configure(cursor="fleur")
        except tk.TclError:
            pass
        if commit:
            ty = self.list.winfo_rooty() + self._show_indicator(d["ins"]) - 4
            self._hide_indicator()
        else:
            ty = it.row.winfo_rooty() if it.row is not None else g.winfo_rooty()
        tx = self.list.winfo_rootx() + 12
        x0, y0 = g.winfo_rootx(), g.winfo_rooty()

        def glide(t):
            g.geometry(f"+{round(x0 + (tx - x0) * t)}+{round(y0 + (ty - y0) * t)}")
            try:
                g.attributes("-alpha", 0.94 - 0.55 * t)
            except tk.TclError:
                pass

        def done():
            g.destroy()
            self._drag = None
            if it.name is not None:
                it.name.configure(text_color=TEXT)
            if commit:
                self._commit_drag(d)

        self.animate(150, glide, on_done=done)

    def _commit_drag(self, d):
        it, ins = d["item"], d["ins"]
        if d["copy"]:
            new = Item(it.path, it.var.get())
            self._add_items([new], index=ins)
            target = new
        else:
            idx = self.items.index(it)
            self.items.pop(idx)
            self.items.insert(ins - (1 if ins > idx else 0), it)
            self._regrid()
            self._after_change()
            target = it
        self._flash(target)
        self._scroll_to(target)

    def _dnd_paths(self, event):
        try:
            return [Path(p) for p in self.tk.splitlist(event.data)] if getattr(event, "data", None) else None
        except Exception:
            return None

    def _drop_border(self, color):
        if self._drop_col == color:
            return
        a = hexc(self._drop_col or BORDER)
        self._drop_col = color
        self._tween(self.list_card, "border_color", a, hexc(color), ms=120,
                    final=BORDER if color is BORDER else None)

    def _on_drop_enter(self, event):
        self._drop_border(ACCENT)
        return event.action

    def _on_drop_position(self, event):
        x, y = getattr(event, "x_root", 0), getattr(event, "y_root", 0)
        self._spring_check(x, y)
        paths = self._dnd_paths(event)
        ok = True if paths is None else any(p.is_dir() or p.suffix.lower() in MODES[self.mode]["ext"] for p in paths)
        self._drop_border(ACCENT if ok else DANGER)
        if ok and MODES[self.mode]["ordered"] and self._inside_list(x, y):
            self._show_indicator(self._drop_index(y))
        else:
            self._hide_indicator()
        return event.action if ok else "refuse_drop"

    def _on_drop_leave(self, event):
        self._drop_border(BORDER)
        self._hide_indicator()
        self._spring_cancel()
        return event.action

    def _on_drop(self, event):
        y = getattr(event, "y_root", 0)
        x = getattr(event, "x_root", 0)
        self._on_drop_leave(event)
        if self.busy:
            return event.action
        paths = [Path(p) for p in self.tk.splitlist(event.data)]
        for p in paths:
            if p.is_dir():
                self._set_folder(p)
                return event.action
        ext, have = MODES[self.mode]["ext"], {it.path for it in self.items}
        new = [Item(p) for p in dict.fromkeys(paths) if p.suffix.lower() in ext and p not in have]
        if new:
            index = self._drop_index(y) if MODES[self.mode]["ordered"] and self._inside_list(x, y) else None
            with self.frozen():
                self._add_items(new, index=index)
            self._scan_pages()
            self._say("added", "ok", n=len(new))
            if index is not None:
                self._flash(new[0])
        else:
            self._say("wrong", "error")
        return event.action

    def _mode_at(self, x, y):
        try:
            w = self.winfo_containing(x, y)
        except (tk.TclError, KeyError):
            return None
        while w is not None:
            for k, b in self.mode_btns.items():
                if w is b:
                    return k
            w = getattr(w, "master", None)
        return None

    def _spring_check(self, x, y):
        key = self._mode_at(x, y)
        if key == self._spring_key:
            return
        self._spring_cancel()
        if key and key != self.mode and not self.busy:
            self._spring_key = key
            self.mode_btns[key].configure(border_width=1)
            self._spring_job = self.after(SPRING_MS, lambda k=key: self._spring_fire(k))

    def _spring_cancel(self):
        if self._spring_job:
            self.after_cancel(self._spring_job)
        if self._spring_key in self.mode_btns:
            self.mode_btns[self._spring_key].configure(border_width=0)
        self._spring_key = self._spring_job = None

    def _spring_fire(self, key):
        self._spring_job = None
        self.mode_btns[key].configure(border_width=0)
        self._spring_key = None
        self._set_mode(key)

    def _say(self, key, kind="info", **kw):
        if self._refresh_status_job:
            self.after_cancel(self._refresh_status_job)
            self._refresh_status_job = None
        self._st = (key, kind, kw)
        self._paint_status()

    def _expire_refresh_status(self):
        self._refresh_status_job = None
        if self._st[0] == "refreshed":
            self.status.configure(text="", image=self._blank, text_color=MUTED)

    def _paint_status(self):
        key, kind, kw = self._st
        icon = {"ok": ("check", OK), "error": ("alert", DANGER)}.get(kind)
        self.status.configure(text=self.tr(key, **kw),
                              image=self.icons.get(*icon, 18) if icon else self._blank,
                              text_color={"ok": TEXT, "error": DANGER}.get(kind, MUTED))

    def _set_progress(self, v):
        a, self._prog = self._prog, v
        self._prog_tok += 1
        tok = self._prog_tok
        self.animate(180, lambda t: self.progress.set(a + (v - a) * t) if tok == self._prog_tok else None)

    def _set_run_button(self, busy: bool):
        if busy:
            self.run_btn.configure(state="normal", text=self.tr("stop"), command=self._cancel_run,
                                   fg_color=DANGER, hover_color=DANGER_HOVER)
        else:
            self.run_btn.configure(state="normal", text=self.tr("r_" + self.mode), command=self._run,
                                   **STYLES["primary"])

    def _cancel_run(self):
        if self.busy and not self.cancel.is_set():
            self.cancel.set()
            self.run_btn.configure(state="disabled", text=self.tr("stopping"))

    def _run(self):
        if self.busy:
            return
        sel = [it.path for it in self.items if it.var.get()]
        if not sel:
            return self._say("none_sel", "error")
        if self.mode == "merge" and len(sel) < 2:
            return self._say("need2", "error")
        entry, default = (self.img_name_entry, "output") if self.mode == "img2pdf" else (self.name_entry, "merged")
        opts = dict(dpi=int(self.dpi_slider.get()), name=safe_filename(entry.get(), default),
                    img_rate=int(round(self.rate_slider.get())),
                    level=self.level, pages=self.pages_entry.get(),
                    split_mode=self.split_mode, split_arg=self.split_entry.get())
        task = TASKS[self.mode]
        cancel = self.cancel = threading.Event()

        def worker():
            try:
                key, kw, out = task(sel, opts, lambda f, t: self.q.put(("progress", f, t)), cancel)
                self.q.put(("done", key, kw, out))
            except Cancelled:
                self.q.put(("cancelled",))
            except Exception as e:
                key, kw = describe(e)
                self.q.put(("error", key, kw))

        self.busy = True
        self._set_run_button(True)
        self._set_progress(0.02)
        self._worker = threading.Thread(target=worker, daemon=True)
        self._worker.start()

    def _finish(self):
        self.busy = False
        self._worker = None
        self._set_run_button(False)

    def _poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "progress":
                    self._set_progress(max(msg[1], 0.02))
                    self._say("raw", "info", text=msg[2])
                elif kind == "pages":
                    self._pages[msg[1]] = msg[2]
                    for it in self.items:
                        if it.path == msg[1] and it.meta is not None:
                            try:
                                it.meta.configure(text=self._meta_text(it))
                            except tk.TclError:
                                pass
                elif kind == "done":
                    self._finish()
                    self._set_progress(1.0)
                    self.last_out = msg[3]
                    self._load(reset=False, animate=False, checked=False)
                    self._say(msg[1], "ok", **msg[2])
                elif kind == "cancelled":
                    self._finish()
                    self._set_progress(0)
                    self._load(reset=False, animate=False, checked=False)
                    self._say("d_cancel", "info")
                elif kind == "error":
                    self._finish()
                    self._set_progress(0)
                    self._say(msg[1], "error", **msg[2])
        except queue.Empty:
            pass
        self.after(40, self._poll)


def main():
    multiprocessing.freeze_support()
    App().mainloop()


if __name__ == "__main__":
    main()
