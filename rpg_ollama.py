"""rpg.py - Nerea RPG (prototipo estilo Chrono Trigger: overworld + diálogos + combate por turnos)"""

GAME_META = {
    "name":  "Nerea RPG",
    "desc":  "RPG 2D por turnos. Elige hasta 3 héroes, explora, habla con NPCs y combate.",
    "ctrl":  "Flechas/WASD: mover | E/Enter: hablar/avanzar | ESC: salir",
    "color": (120, 80, 200),
    "order": 20,
}

import pygame
import sys
import os
import random
import re
import threading
import time
import json
import urllib.request

pygame.init()
try:
    pygame.mixer.init()
except Exception:
    pass

TILE = 32
COLS, ROWS = 20, 15
W, H = COLS * TILE, ROWS * TILE
HUD_H = 24                  # franja superior reservada para el HUD
FPS = 60

_DIR = os.path.dirname(os.path.abspath(__file__))
# EDICIÓN OLLAMA: carpeta PROPIA para sus datos (música, guardados, opciones),
# independiente de la versión Nerea. Se crea sola si no existe.
_BASE = os.path.join(_DIR, "rpg_ollama_data")
os.makedirs(os.path.join(_BASE, "music"), exist_ok=True)

# --- Colores ---
BLACK = (10, 10, 14)
WHITE = (235, 235, 240)
GRAY = (60, 60, 70)
DARK = (22, 22, 30)
DIM = (120, 120, 130)
GOLD = (210, 165, 0)
GREEN = (60, 160, 90)
RED = (200, 70, 70)
YELLOW = (220, 190, 60)
BLUE = (70, 120, 220)
BOX_BG = (16, 18, 32)
BOX_BORDER = (120, 160, 255)


def hp_color(frac):
    """Color de la barra de vida: verde (bien), amarillo (peligro), rojo (crítico)."""
    if frac > 0.5:
        return GREEN
    if frac > 0.25:
        return YELLOW
    return RED

HD = (1280, 720)                   # ventana HD; F11 = pantalla completa
_FULL = False
_WIN = pygame.display.set_mode(HD)
pygame.display.set_caption("Nerea RPG")
screen = pygame.Surface((W, H))    # lienzo interno; se escala a la ventana HD
clock = pygame.time.Clock()


def present():
    """Escala el lienzo a la ventana HD manteniendo proporción."""
    ww, wh = _WIN.get_size()
    s = min(ww / W, wh / H)
    sw, sh = int(W * s), int(H * s)
    _WIN.fill((0, 0, 0))
    _WIN.blit(pygame.transform.scale(screen, (sw, sh)),
              ((ww - sw) // 2, (wh - sh) // 2))
    pygame.display.flip()


def toggle_fullscreen():
    global _WIN, _FULL
    _FULL = not _FULL
    _WIN = pygame.display.set_mode((0, 0), pygame.FULLSCREEN) if _FULL \
        else pygame.display.set_mode(HD)


FADE_MS = 300                          # duración del fundido de transición


def fade_out(steps=9, delay=7):
    """Funde a negro el fotograma ACTUAL (transición de salida, bloqueante)."""
    snap = screen.copy()
    ov = pygame.Surface((W, H))
    ov.fill((0, 0, 0))
    for s in range(1, steps + 1):
        screen.blit(snap, (0, 0))
        ov.set_alpha(int(255 * s / steps))
        screen.blit(ov, (0, 0))
        present()
        pygame.time.delay(delay)
    screen.fill((0, 0, 0))
    present()

font_lg = pygame.font.SysFont("Consolas", 22, bold=True)
font_md = pygame.font.SysFont("Consolas", 16, bold=True)
font_sm = pygame.font.SysFont("Consolas", 13)
font_xs = pygame.font.SysFont("Consolas", 11)

# Fuente de respaldo para símbolos/emojis que Consolas no tiene (✔ ⚡ ◄ ► ↑ ↓ …)
_sym_lg = pygame.font.SysFont("Segoe UI Symbol", 22, bold=True)
_sym_md = pygame.font.SysFont("Segoe UI Symbol", 16, bold=True)
_sym_sm = pygame.font.SysFont("Segoe UI Symbol", 13)
_sym_xs = pygame.font.SysFont("Segoe UI Symbol", 11)
_SYM = {id(font_lg): _sym_lg, id(font_md): _sym_md,
        id(font_sm): _sym_sm, id(font_xs): _sym_xs}


def draw_text(surf, text, x, y, font=font_sm, color=WHITE):
    text = str(text)
    # ruta rápida: si la fuente tiene todos los glifos, render directo
    if None not in font.metrics(text):
        surf.blit(font.render(text, True, color), (x, y))
        return
    # ruta con respaldo: carácter a carácter, usando Segoe UI Symbol si falta glifo.
    # Si ni el respaldo tiene el glifo (emoji a color de la IA), se OMITE el carácter.
    fb = _SYM.get(id(font), font)
    cx = x
    for ch in text:
        m = font.metrics(ch)
        if m and m[0] is not None:
            use = font
        elif fb is not font and fb.metrics(ch)[0] is not None:
            use = fb
        else:
            continue                       # glifo inexistente -> no dibujar cuadrito
        surf.blit(use.render(ch, True, color), (cx, y))
        cx += use.size(ch)[0]


def draw_menu_panel(title, lines, idx, footer=""):
    """Panel de menú centrado con SCROLL (tienda / bolsa)."""
    MAXVIS = 12
    n = len(lines)
    top = max(0, min(idx - MAXVIS // 2, n - MAXVIS)) if n > MAXVIS else 0
    vis = lines[top:top + MAXVIS]
    bw = 400
    bh = 70 + max(1, len(vis)) * 24
    box = pygame.Rect(W // 2 - bw // 2, H // 2 - bh // 2, bw, bh)
    pygame.draw.rect(screen, BOX_BG, box, border_radius=10)
    pygame.draw.rect(screen, BOX_BORDER, box, 3, border_radius=10)
    draw_text(screen, title, box.x + 16, box.y + 12, font_md, GOLD)
    for i, ln in enumerate(vis):
        yy = box.y + 44 + i * 24
        if top + i == idx:
            pygame.draw.rect(screen, (40, 50, 80),
                             (box.x + 8, yy - 2, bw - 16, 22), border_radius=4)
        draw_text(screen, ln, box.x + 20, yy, font_sm, WHITE)
    if top > 0:
        draw_text(screen, "▲", box.right - 26, box.y + 44, font_sm, GOLD)
    if top + MAXVIS < n:
        draw_text(screen, "▼", box.right - 26, box.bottom - 40, font_sm, GOLD)
    if footer:
        draw_text(screen, footer, box.x + 16, box.bottom - 20, font_xs, DIM)


def wrap(text, font, maxw):
    words, lines, cur = text.split(" "), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if font.size(t)[0] <= maxw:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


# ============================================================
#  DATOS
# ============================================================
# Héroes disponibles. (sprites placeholder por color; reemplazar con PNG luego)
# --- Sistema elemental (rueda cerrada de 6, inspirada en Wu Xing) ---
# Cada elemento VENCE al que apunta; y es débil contra quien lo apunta a él.
#   agua > fuego > planta > tierra > rayo > hielo > agua (cierra el ciclo)
# Cada elemento es FUERTE vs 2, débil vs 2 y neutral vs 1 (su opuesto). Lógica:
#  agua  apaga FUEGO, erosiona TIERRA      (débil vs planta y rayo; neutral hielo)
#  fuego quema PLANTA, derrite HIELO       (débil vs agua y tierra;  neutral rayo)
#  planta absorbe AGUA, dispersa RAYO      (débil vs fuego y hielo;  neutral tierra)
#  tierra sofoca FUEGO, absorbe RAYO       (débil vs agua y hielo;   neutral planta)
#  rayo  electrocuta AGUA, parte HIELO     (débil vs planta y tierra; neutral fuego)
#  hielo congela PLANTA y agrieta TIERRA   (débil vs fuego y rayo;   neutral agua)
ELEM_BEATS = {
    "agua": ("fuego", "tierra"),
    "fuego": ("planta", "hielo"),
    "planta": ("agua", "rayo"),
    "tierra": ("fuego", "rayo"),
    "rayo": ("agua", "hielo"),
    "hielo": ("planta", "tierra"),
}
ELEM_NAME = {"fuego": "Fuego", "planta": "Planta", "agua": "Agua",
             "tierra": "Tierra", "rayo": "Rayo", "hielo": "Hielo",
             "luz": "Luz", "sombra": "Sombra", "neutro": "Neutro"}
ELEM_COLOR = {"fuego": (220, 70, 50), "planta": (70, 180, 90),
              "agua": (70, 130, 220), "tierra": (210, 130, 50),
              "rayo": (235, 205, 70), "hielo": (160, 110, 220),
              "luz": (240, 240, 245), "sombra": (40, 40, 55),
              "neutro": (150, 150, 160)}
SUPER, WEAK = 1.3, 0.6   # multiplicadores de efectividad
COLORS6 = {"fuego", "planta", "agua", "tierra", "rayo", "hielo"}


def effectiveness(a, d):
    # Luz (Blanco): fuerte vs los 6 colores, débil vs Sombra
    if a == "luz":
        return WEAK if d == "sombra" else SUPER if d in COLORS6 else 1.0
    if d == "luz":
        return SUPER if a == "sombra" else WEAK if a in COLORS6 else 1.0
    # Sombra (Negro): fuerte vs Luz; neutral con lo demás
    if a == "sombra":
        return SUPER if d == "luz" else 1.0
    if d == "sombra":
        return WEAK if a == "luz" else 1.0
    # Gris (neutro): siempre neutral. Resto: matchups de elementos.
    if d in ELEM_BEATS.get(a, ()):
        return SUPER
    if a in ELEM_BEATS.get(d, ()):
        return WEAK
    return 1.0


# Los 6 magos elegibles. Blanco (luz) y Negro (sombra) NO son elegibles:
# son NPCs clave del lore (jefe final manipulador / víctima de injusticia).
# Las 6 magas (mujeres) elegibles como compañeras. Cada compañera elegida es
# controlada por una IA (avatar de Nerea). Enemigos y NPCs NO son IAs.
# Stats: atk(ataque) df(defensa) spd(velocidad) pre(precisión) agu(aguante)
HEROES = [
    {"id": "fuego", "name": "Pyra", "elem": "fuego", "hp": 60, "mp": 24,
     "atk": 15, "df": 8, "spd": 9, "pre": 92, "agu": 10,
     "powers": [("Llamarada", 6, 24), ("Escudo Ascua", 4, 0)]},
    {"id": "planta", "name": "Sylva", "elem": "planta", "hp": 78, "mp": 20,
     "atk": 13, "df": 11, "spd": 7, "pre": 86, "agu": 22,
     "powers": [("Zarpa Espina", 6, 26), ("Savia Curativa", 6, -30)]},
    {"id": "agua", "name": "Marina", "elem": "agua", "hp": 55, "mp": 34,
     "atk": 11, "df": 7, "spd": 10, "pre": 90, "agu": 12,
     "powers": [("Lanza de Agua", 7, 26), ("Marea Sana", 6, -28)]},
    {"id": "tierra", "name": "Terra", "elem": "tierra", "hp": 95, "mp": 12,
     "atk": 17, "df": 15, "spd": 4, "pre": 82, "agu": 30,
     "powers": [("Roca Colosal", 6, 30), ("Muro de Piedra", 4, 0)]},
    {"id": "rayo", "name": "Electra", "elem": "rayo", "hp": 48, "mp": 32,
     "atk": 12, "df": 6, "spd": 14, "pre": 96, "agu": 6,
     "powers": [("Centella", 7, 28), ("Sobrecarga", 9, 36)]},
    {"id": "hielo", "name": "Gélida", "elem": "hielo", "hp": 50, "mp": 38,
     "atk": 10, "df": 6, "spd": 11, "pre": 90, "agu": 12,
     "powers": [("Lanza de Hielo", 7, 28), ("Escarcha", 5, 20)]},
]

# Protagonista: el Mago Gris. Neutral (ni fuerte ni débil contra nadie),
# entre la Luz (Blanco) y la Sombra (Negro). Siempre en el equipo.
PROTAG = {"id": "gris", "name": "Mago Gris", "elem": "neutro", "hp": 68, "mp": 28,
          "atk": 13, "df": 9, "spd": 10, "pre": 90, "agu": 14,
          "powers": [("Golpe Arcano", 6, 24), ("Cura Menor", 6, -26)]}

# Magos Blanco y Negro: se unen al equipo en el arco final (poderes propios).
WHITE_MAGE = {"id": "blanco", "name": "Mago Blanco", "elem": "luz", "hp": 90, "mp": 44,
              "atk": 17, "df": 13, "spd": 12, "pre": 95, "agu": 18,
              "powers": [("Rayo Sagrado", 7, 32), ("Bendición", 8, -55),
                         ("Juicio Divino", 15, 54)]}
BLACK_MAGE = {"id": "negro", "name": "Mago Negro", "elem": "sombra", "hp": 96, "mp": 40,
              "atk": 19, "df": 12, "spd": 10, "pre": 90, "agu": 22,
              "powers": [("Garra Umbría", 7, 34), ("Drenar Alma", 8, 30),
                         ("Eclipse", 16, 56)]}

# Combos (Dual/Triple). Se ofrecen si TODOS sus miembros están en el equipo,
# vivos y con MP. Dañan a todos los enemigos. 'elem' define su efectividad.
# Combos / MEZCLAS de elementos (el Gris puede activarlas en su turno si las
# magas están en el grupo). Golpean a todos los enemigos.
# DUAL = Gris + 1 maga. TRIPLE = Gris + 2 magas (todas las parejas posibles).
# Los triples pueden golpear a UNO (concentrado, +60%) o a TODOS (área).
_DUAL_NAME = {"fuego": "Llama Arcana", "planta": "Selva Arcana", "agua": "Marea Arcana",
              "tierra": "Roca Arcana", "rayo": "Chispa Arcana", "hielo": "Hielo Arcano"}
# pareja de magas -> (nombre, elemento de efectividad)
_TRIPLE = {
    frozenset(("fuego", "planta")): ("Incendio Forestal", "fuego"),
    frozenset(("fuego", "agua")):   ("Vapor Hirviente", "agua"),
    frozenset(("fuego", "tierra")): ("Magma", "fuego"),
    frozenset(("fuego", "rayo")):   ("Plasma", "rayo"),
    frozenset(("fuego", "hielo")):  ("Choque Térmico", "fuego"),
    frozenset(("planta", "agua")):  ("Floración", "planta"),
    frozenset(("planta", "tierra")): ("Selva Pétrea", "planta"),
    frozenset(("planta", "rayo")):  ("Polen Eléctrico", "rayo"),
    frozenset(("planta", "hielo")): ("Escarcha Vegetal", "hielo"),
    frozenset(("agua", "tierra")):  ("Lodo Torrencial", "tierra"),
    frozenset(("agua", "rayo")):    ("Tromba Eléctrica", "rayo"),
    frozenset(("agua", "hielo")):   ("Ola Glacial", "hielo"),
    frozenset(("tierra", "rayo")):  ("Sismo Eléctrico", "rayo"),
    frozenset(("tierra", "hielo")): ("Permafrost", "hielo"),
    frozenset(("rayo", "hielo")):   ("Granizo Cargado", "hielo"),
}


def _build_combos():
    out = []
    for el, nm in _DUAL_NAME.items():            # Gris + 1 maga
        out.append({"members": ["gris", el], "name": nm, "elem": el,
                    "cost": 8, "dmg": 46, "tier": "dual"})
    for pair, (nm, el) in _TRIPLE.items():        # Gris + 2 magas
        out.append({"members": ["gris"] + list(pair), "name": nm, "elem": el,
                    "cost": 11, "dmg": 80, "tier": "triple"})
    # Combos de SOMBRA con el Mago Negro aliado (arco final)
    out.append({"members": ["gris", "negro"], "name": "Sombra Arcana",
                "elem": "sombra", "cost": 9, "dmg": 52, "tier": "dual"})
    for el, nm in _DUAL_NAME.items():            # Gris + Negro + 1 maga
        out.append({"members": ["gris", "negro", el],
                    "name": f"Sombra de {ELEM_NAME[el]}", "elem": "sombra",
                    "cost": 12, "dmg": 86, "tier": "triple"})
    return out


COMBOS = _build_combos()

ITEMS = [
    {"name": "Poción", "qty": 3, "kind": "hp", "amt": 50, "price": 25},
    {"name": "Super Poción", "qty": 0, "kind": "hp", "amt": 130, "price": 70},
    {"name": "Mega Poción", "qty": 0, "kind": "hp", "amt": 320, "price": 170},
    {"name": "Éter", "qty": 2, "kind": "mp", "amt": 30, "price": 30},
    {"name": "Super Éter", "qty": 0, "kind": "mp", "amt": 70, "price": 90},
    {"name": "Elixir", "qty": 0, "kind": "full", "amt": 0, "price": 350},
    {"name": "Pluma Fénix", "qty": 1, "kind": "revive", "amt": 0, "price": 150},
]

# Objetos potentes que SOLO aparecen (tienda/cofres/drops) cuando algún personaje
# tenga HP máximo >= 100 (al inicio solo hay Pociones y Éter básicos).
SUPER_GATED = {"Super Poción", "Mega Poción", "Super Éter", "Elixir"}

# Equipables (se COMPRAN con oro y se equipan en la Bolsa). Suben stats del equipo:
#   WEAPONS -> ataque físico | FOCI -> daño de poderes | ARMORS -> defensa
WEAPONS = [
    {"name": "Daga", "price": 40, "atk": 3, "lvl": 1},
    {"name": "Espada Rúnica", "price": 140, "atk": 7, "lvl": 7},
    {"name": "Cetro Arcano", "price": 320, "atk": 12, "lvl": 14},
]
FOCI = [
    {"name": "Amuleto", "price": 45, "pow": 4, "lvl": 1},
    {"name": "Orbe Arcano", "price": 150, "pow": 9, "lvl": 7},
    {"name": "Reliquia Astral", "price": 330, "pow": 15, "lvl": 14},
]
ARMORS = [
    {"name": "Túnica de Tela", "price": 50, "df": 3, "lvl": 1},
    {"name": "Cota de Malla", "price": 150, "df": 7, "lvl": 7},
    {"name": "Armadura Rúnica", "price": 340, "df": 13, "lvl": 14},
]
EQUIP = {"Arma": WEAPONS, "Foco": FOCI, "Armadura": ARMORS}
EQUIP_STAT = {"Arma": "atk", "Foco": "pow", "Armadura": "df"}

# Accesorios de vestimenta de poder EXCLUSIVOS por maga (por elemento). Cada uno
# sube un stat SOLO de esa maga. Se compran en la tienda y se equipan en Estado (V).
# 4 accesorios por elemento, exigen y se compran por NIVEL ESPACIADO (5/12/22/34),
# para que conseguirlos todos sea un proceso largo (como los poderes).
ACCESSORIES = {
    "fuego":  [{"name": "Corona Ígnea", "price": 120, "lvl": 5, "pow": 6},
               {"name": "Manto de Brasas", "price": 260, "lvl": 12, "pow": 11, "df": 4},
               {"name": "Cetro del Volcán", "price": 460, "lvl": 22, "pow": 16, "crit": 5},
               {"name": "Aureola del Fénix", "price": 720, "lvl": 34, "pow": 22, "df": 6}],
    "planta": [{"name": "Diadema de Hojas", "price": 120, "lvl": 5, "pow": 6},
               {"name": "Coraza de Corteza", "price": 260, "lvl": 12, "df": 12},
               {"name": "Cáliz de Savia", "price": 460, "lvl": 22, "pow": 16, "df": 6},
               {"name": "Corona del Bosque Eterno", "price": 720, "lvl": 34, "pow": 20, "df": 9}],
    "agua":   [{"name": "Tiara de Marea", "price": 120, "lvl": 5, "pow": 6},
               {"name": "Túnica Abisal", "price": 260, "lvl": 12, "pow": 11, "df": 4},
               {"name": "Perla del Abismo", "price": 460, "lvl": 22, "pow": 16, "df": 5},
               {"name": "Corona de las Profundidades", "price": 720, "lvl": 34, "pow": 22, "df": 6}],
    "tierra": [{"name": "Yelmo de Roca", "price": 120, "lvl": 5, "df": 7},
               {"name": "Égida Pétrea", "price": 260, "lvl": 12, "df": 14},
               {"name": "Coraza Tectónica", "price": 460, "lvl": 22, "df": 20, "pow": 8},
               {"name": "Trono de Montaña", "price": 720, "lvl": 34, "df": 26, "pow": 10}],
    "rayo":   [{"name": "Aro de Voltios", "price": 120, "lvl": 5, "pow": 7},
               {"name": "Capa Estática", "price": 260, "lvl": 12, "pow": 12, "crit": 6},
               {"name": "Corona de Truenos", "price": 460, "lvl": 22, "pow": 17, "crit": 8},
               {"name": "Diadema del Relámpago", "price": 720, "lvl": 34, "pow": 23, "crit": 10}],
    "hielo":  [{"name": "Corona Glacial", "price": 120, "lvl": 5, "pow": 6},
               {"name": "Manto de Escarcha", "price": 260, "lvl": 12, "pow": 11, "df": 4},
               {"name": "Cetro del Glaciar", "price": 460, "lvl": 22, "pow": 16, "crit": 5},
               {"name": "Tiara del Cero Absoluto", "price": 720, "lvl": 34, "pow": 22, "df": 6}],
    "neutro": [{"name": "Velo del Gris", "price": 120, "lvl": 5, "pow": 6},
               {"name": "Túnica Gris", "price": 260, "lvl": 12, "pow": 11, "df": 5},
               {"name": "Manto del Equilibrio", "price": 460, "lvl": 22, "pow": 16, "df": 6},
               {"name": "Corona del Vacío", "price": 720, "lvl": 34, "pow": 22, "df": 8}],
}
ACC_BY_NAME = {a["name"]: (el, a) for el, lst in ACCESSORIES.items() for a in lst}

# Cada mercader vende POCAS cosas y curadas: para equiparte bien debes VOLVER a
# reinos anteriores (backtracking). Cada reino stockea accesorios de OTRO elemento
# (ej.: en Fuego venden defensa de Tierra). Los accesorios exigen nivel.
SHOP_PLAN = {
    "hub":    {"items": ["Poción", "Éter", "Pluma Fénix"],
               "equip": [("Arma", 0), ("Armadura", 0), ("Foco", 0)], "acc": ["neutro"]},
    "fuego":  {"items": ["Poción", "Super Poción"],
               "equip": [("Foco", 0)], "acc": ["tierra"]},
    "planta": {"items": ["Poción", "Éter"],
               "equip": [("Arma", 1)], "acc": ["fuego"]},
    "agua":   {"items": ["Super Poción", "Super Éter"],
               "equip": [("Armadura", 1)], "acc": ["rayo"]},
    "tierra": {"items": ["Poción", "Pluma Fénix"],
               "equip": [("Foco", 1)], "acc": ["planta"]},
    "rayo":   {"items": ["Super Poción", "Éter"],
               "equip": [("Arma", 2)], "acc": ["hielo"]},
    "hielo":  {"items": ["Super Éter", "Mega Poción"],
               "equip": [("Armadura", 2)], "acc": ["agua"]},
    "final":  {"items": ["Mega Poción", "Super Éter", "Elixir", "Pluma Fénix"],
               "equip": [("Arma", 2), ("Foco", 2), ("Armadura", 2)],
               "acc": ["neutro", "fuego", "agua", "hielo"]},
}

_STAT_LABEL = {"pow": "PODER", "df": "DEFENSA", "crit": "CRÍTICO", "atk": "ATAQUE"}


def acc_desc(el, a):
    """Descripción legible de un accesorio (elemento, nivel y bonos)."""
    if a is None:
        return "Quitar el accesorio equipado."
    bonos = ", ".join(f"+{a[k]} {_STAT_LABEL.get(k, k.upper())}"
                      for k in ("pow", "df", "crit", "atk") if k in a)
    return f"{ELEM_NAME.get(el, el)} · Nv{a.get('lvl', 1)} · {bonos}"


def wear_bonus(c, stat):
    w = c.get("wear")
    return w.get(stat, 0) if w else 0

# Oro que sueltan los enemigos según su tipo.
GOLD_REWARD = {"ambient": 12, "acolito": 35, "boss": 120, "final": 400}


def make_combatant(h):
    return {
        "id": h["id"], "name": h["name"], "elem": h["elem"],
        "color": ELEM_COLOR[h["elem"]],
        "hp": h["hp"], "maxhp": h["hp"], "mp": h["mp"], "maxmp": h["mp"],
        "atk": h["atk"], "df": h["df"], "spd": h["spd"],
        "pre": h.get("pre", 90), "agu": h.get("agu", 10),
        "powers": list(h["powers"]), "guard": False, "alive": True, "side": "hero",
        "lvl": 1, "xp": 0, "wear": None,
    }


def make_enemy(name, elem, hp, atk, df, spd, lvl=1):
    return {
        "id": name, "name": name, "elem": elem, "color": ELEM_COLOR[elem],
        "hp": hp, "maxhp": hp, "mp": 0, "maxmp": 0,
        "atk": atk, "df": df, "spd": spd, "pre": 84, "agu": 8,
        "powers": [], "guard": False, "alive": True, "side": "enemy", "lvl": lvl,
    }


# Poderes que se DESBLOQUEAN al subir de nivel (por elemento). (lvl_req, (nombre, MP, val))
# val: >0 daño | <0 cura | 0 defensivo
# Niveles de desbloqueo MÁS ESPACIADOS (antes 3/6/9/12/15 -> ahora 5/11/18/26/34),
# para que conseguir todos los poderes sea un proceso largo.
LEVEL_POWERS = {
    "fuego":  [(5, ("Erupción", 10, 34)), (11, ("Infierno", 16, 50)),
               (18, ("Meteoro", 18, 60)), (26, ("Supernova", 24, 72)),
               (34, ("Fénix Solar", 30, 104))],
    "planta": [(5, ("Lluvia de Savia", 10, -48)), (11, ("Bosque Vivo", 16, 48)),
               (18, ("Furia Silvana", 18, 58)), (26, ("Ira de Gaia", 24, 72)),
               (34, ("Árbol del Mundo", 30, 100))],
    "agua":   [(5, ("Tsunami", 10, 34)), (11, ("Marea Total", 16, -64)),
               (18, ("Maremoto", 18, 60)), (26, ("Diluvio", 24, 72)),
               (34, ("Abismo Final", 30, 102))],
    "tierra": [(5, ("Avalancha", 11, 40)), (11, ("Cataclismo Pétreo", 17, 54)),
               (18, ("Terremoto", 18, 62)), (26, ("Deriva Continental", 24, 74)),
               (34, ("Fin del Mundo", 30, 108))],
    "rayo":   [(5, ("Trueno", 10, 36)), (11, ("Tempestad", 16, 52)),
               (18, ("Rayo Divino", 18, 60)), (26, ("Apocalipsis Eléctrico", 24, 72)),
               (34, ("Juicio del Cielo", 30, 104))],
    "hielo":  [(5, ("Ventisca", 10, 34)), (11, ("Cero Absoluto", 16, 54)),
               (18, ("Glaciación", 18, 60)), (26, ("Edad de Hielo", 24, 72)),
               (34, ("Ragnarök Helado", 30, 102))],
    "neutro": [(5, ("Pulso Arcano", 9, 32)), (11, ("Juicio Gris", 15, 50)),
               (18, ("Onda Arcana", 17, 58)), (26, ("Big Bang", 24, 72)),
               (34, ("Singularidad", 30, 110))],
}

# Poderes de ÁREA (golpean a TODOS los enemigos). El resto deja elegir objetivo.
AOE_POWERS = {"Infierno", "Tempestad", "Cero Absoluto", "Cataclismo Pétreo",
              "Bosque Vivo", "Juicio Gris", "Sobrecarga", "Vendaval",
              "Juicio Divino", "Eclipse",
              # Nv12 (definitivos) -> todos a la vez
              "Supernova", "Ira de Gaia", "Diluvio", "Deriva Continental",
              "Apocalipsis Eléctrico", "Edad de Hielo", "Big Bang"}


# ---- Sistema de niveles (XP) ----
def xp_to_next(lvl):
    return 30 + (lvl - 1) * 25


def gain_xp(c, amount):
    """Suma XP, sube de nivel (mejora stats y desbloquea poderes).
    Devuelve una lista de eventos de subida (uno por nivel ganado)."""
    events = []
    c["xp"] += amount
    while c["xp"] >= xp_to_next(c["lvl"]):
        c["xp"] -= xp_to_next(c["lvl"])
        c["lvl"] += 1
        gains = {"HP": 8, "MP": 3, "ATK": 2, "DEF": 1, "VEL": 0, "AGU": 1, "PRE": 0}
        c["maxhp"] += 8; c["hp"] += 8
        c["maxmp"] += 3; c["mp"] += 3
        c["atk"] += 2; c["df"] += 1
        c["agu"] = c.get("agu", 10) + 1
        if c["lvl"] % 2 == 0:
            c["spd"] += 1; gains["VEL"] = 1
            c["pre"] = min(200, c.get("pre", 90) + 1); gains["PRE"] = 1
        new_powers = []
        for req, p in LEVEL_POWERS.get(c["elem"], []):
            if req == c["lvl"] and p[0] not in [q[0] for q in c["powers"]]:
                c["powers"].append(p)
                new_powers.append(p[0])
        events.append({"char": c, "name": c["name"], "lvl": c["lvl"],
                       "gains": gains, "powers": new_powers})
    return events


# Ataques MEJORADOS de los enemigos según su nivel (igual que los aliados crecen).
# elem -> [(nivel_req, nombre, daño_extra), ...]
ENEMY_SKILLS = {
    "fuego":  [(5, "Llamarazo", 10), (12, "Erupción Maligna", 22), (20, "Pira Infernal", 36)],
    "planta": [(5, "Latigazo", 10), (12, "Zarpa Salvaje", 22), (20, "Abrazo Mortal", 36)],
    "agua":   [(5, "Chorro", 10), (12, "Ola Aplastante", 22), (20, "Vórtice", 36)],
    "tierra": [(5, "Pedrada", 10), (12, "Sismo", 22), (20, "Lápida", 36)],
    "rayo":   [(5, "Descarga", 10), (12, "Trueno Negro", 22), (20, "Rayo Letal", 36)],
    "hielo":  [(5, "Esquirla", 10), (12, "Helada Brutal", 22), (20, "Tumba de Hielo", 36)],
    "sombra": [(5, "Zarpa Umbría", 12), (12, "Golpe de Sombra", 26), (20, "Abismo", 42)],
    "luz":    [(5, "Destello", 12), (12, "Fulgor Cruel", 26), (20, "Juicio Falso", 42)],
    "neutro": [(5, "Embate", 10), (12, "Embate Brutal", 22), (20, "Aniquilación", 36)],
}


def scale_enemy(e, lvl):
    """Escala TODAS las stats del enemigo a su nivel y le da un ataque mejorado."""
    f = 1 + 0.11 * (lvl - 1)
    e["maxhp"] = int(e["maxhp"] * f); e["hp"] = e["maxhp"]
    e["atk"] = int(e["atk"] * f); e["df"] = int(e["df"] * f)
    e["spd"] = int(e["spd"] * (1 + 0.04 * (lvl - 1)))
    e["pre"] = min(200, e.get("pre", 84) + lvl // 3)
    e["agu"] = e.get("agu", 8) + lvl // 4
    best = None                          # mejor ataque especial desbloqueado
    for req, nm, bonus in ENEMY_SKILLS.get(e.get("elem"), []):
        if lvl >= req:
            best = (nm, bonus)
    e["special"] = best
    e["lvl"] = lvl
    return e


# ============================================================
#  ETAPAS / MAPAS
# ============================================================
# Tipos de tile: 0 suelo, 1 pared, 2 árbol, 3 agua, 4 puerta (transición)
TILE_WALK = {0, 4}            # suelo y puerta son transitables

# Tema visual por etapa (identidad de cada mapa)
THEMES = {
    "aldea":     {"floor": (46, 74, 52),  "grid": (52, 82, 58),
                  "wall": (74, 68, 62),   "wall2": (52, 48, 46)},
    "bosque":    {"floor": (30, 58, 38),  "grid": (36, 66, 44),
                  "wall": (50, 62, 44),   "wall2": (34, 44, 30)},
    "canon":     {"floor": (120, 96, 58), "grid": (132, 106, 64),
                  "wall": (96, 74, 52),   "wall2": (70, 54, 38)},
    "pico":      {"floor": (176, 194, 210), "grid": (190, 206, 220),
                  "wall": (120, 150, 182), "wall2": (92, 118, 150)},
    "santuario": {"floor": (196, 198, 208), "grid": (208, 210, 220),
                  "wall": (186, 172, 128), "wall2": (150, 138, 100)},
    "volcan":    {"floor": (70, 36, 32),   "grid": (96, 44, 36),
                  "wall": (110, 50, 40),   "wall2": (70, 30, 26)},
    "mar":       {"floor": (28, 70, 96),   "grid": (34, 84, 112),
                  "wall": (40, 86, 120),   "wall2": (26, 60, 86)},
    "tormenta":  {"floor": (54, 50, 78),   "grid": (64, 60, 92),
                  "wall": (78, 72, 110),   "wall2": (50, 46, 74)},
    "cripta":    {"floor": (28, 26, 34),   "grid": (38, 34, 46),
                  "wall": (54, 48, 62),    "wall2": (32, 28, 38)},
    "hub":       {"floor": (60, 56, 80),   "grid": (74, 68, 98),
                  "wall": (110, 100, 150), "wall2": (70, 62, 96)},
    "casa":      {"floor": (96, 70, 46),   "grid": (108, 80, 54),
                  "wall": (76, 54, 36),    "wall2": (54, 38, 24)},
}


def _darken(c, f=0.5):
    return tuple(max(0, int(x * f)) for x in c)


# Versión OSCURA de cada mundo (mientras la maga está poseída). Al liberarla
# se usa el tema vivo (colores reales).
for _wt in ("volcan", "bosque", "mar", "canon", "tormenta", "pico"):
    THEMES[_wt + "_dark"] = {k: _darken(v) for k, v in THEMES[_wt].items()}


def foes_for(elem, boss=False):
    n = "Mago " + ELEM_NAME[elem]
    if boss:
        return [make_enemy(n + " (Jefe)", elem, 140, 20, 14, 9)]
    return [make_enemy(n, elem, 46, 12, 8, 6),
            make_enemy("Acólito", elem, 28, 9, 5, 8)]


# ------------------------------------------------------------------
#  ESTRUCTURA: Hub central -> 6 puertas -> 6 mundos (3 etapas c/u).
#  El jefe de cada mundo es la MAGA IA de ese elemento (hechizada).
#  Vencerla = liberarla y reclutarla. Tras las 6 -> Mago Negro (final).
# ------------------------------------------------------------------
HUB = (40, 28)          # mapa del hub (mayor que la pantalla)
BIG = (144, 104)        # mapas de los mundos (enormes; cámara los recorre)
_bx, _by = BIG[0] // 2, BIG[1] // 2

MAGA_BY_ELEM = {h["elem"]: h for h in HEROES}
WORLD_ORDER = ["fuego", "planta", "agua", "tierra", "rayo", "hielo"]
WORLD_THEME = {"fuego": "volcan", "planta": "bosque", "agua": "mar",
               "tierra": "canon", "rayo": "tormenta", "hielo": "pico"}
WORLD_NAME = {"fuego": "Caldera Ardiente", "planta": "Bosque Esmeralda",
              "agua": "Abismo Marino", "tierra": "Cañón de Arena",
              "rayo": "Cima de la Tormenta", "hielo": "Pico Helado"}
WORLD_DECOR = {"fuego": [(1, 0.05)], "planta": [(2, 0.10), (3, 0.04)],
               "agua": [(3, 0.12)], "tierra": [(1, 0.08)],
               "rayo": [(1, 0.04)], "hielo": [(3, 0.08), (1, 0.03)]}

# Enemigos de AMBIENTE por mundo (criaturas, no magos). Mismo elemento del mundo.
AMBIENT = {
    "volcan": ["Murciélago Ígneo", "Salamandra", "Can de Magma"],
    "bosque": ["Árbol Maligno", "Lobo del Bosque", "Enredadera"],
    "mar": ["Medusa", "Sirénido", "Cangrejo Coloso"],
    "canon": ["Hombre de Arena", "Escorpión", "Buitre"],
    "tormenta": ["Ave Trueno", "Elemental de Rayo", "Espectro"],
    "pico": ["Yeti", "Lobo Blanco", "Murciélago Helado"],
    "cripta": ["Sombra Errante", "Acólito Caído", "Espectro de los Dos Triángulos"],
    "santuario": ["Querubín Pálido", "Guardián de Luz", "Vigía Sagrado"],
}


def hint_dir(ax, ay, tx, ty):
    """Dirección general (para las pistas de los aldeanos)."""
    dx, dy = tx - ax, ty - ay
    h = "el este" if dx > 0 else "el oeste"
    v = "el norte" if dy < 0 else "el sur"
    if abs(dx) > abs(dy) * 1.6:
        return h
    if abs(dy) > abs(dx) * 1.6:
        return v
    return v + " y " + h


# Historias de los aldeanos: los buenos tiempos antes de que el Mago Negro
# tomara el poder. (La verdad sobre el Blanco solo se revela al FINAL.)
LORE = [
    "Antes de que el Mago Negro llegara, estos campos cantaban. "
    "Ahora su sombra cubre todo.",
    "El Mago Negro poseyó a nuestras seis magas y las desterró, una a una, "
    "a seis mundos lejanos.",
    "Menos mal que el Mago Blanco vela por nosotros. Sin su luz, "
    "ya estaríamos perdidos.",
    "Yo vi a las magas reír en la plaza. El Mago Negro les robó la sonrisa "
    "y la voluntad.",
    "Dicen que algo no encaja en esta guerra... pero ¿quién dudaría "
    "de la luz? Ve, libera a las magas.",
]
# El reinado de cada maga: cómo era su tierra ANTES y DESPUÉS de ser poseída.
REIGN = {
    "fuego": ("Bajo la maga Pyra, las forjas ardían día y noche y ningún hogar "
              "pasaba frío. Era una reina cálida, de risa fácil.",
              "Desde que el Mago Negro la posee, su fuego devora cuanto toca. "
              "Ya nadie enciende un hogar sin miedo."),
    "planta": ("La maga Sylva hacía florecer hasta la roca; nuestras cosechas "
               "no tenían fin y los enfermos sanaban a su sombra.",
               "Ahora las raíces se pudren y el bosque que ella amaba nos "
               "mira con rencor, movido por una voluntad ajena."),
    "agua": ("Marina mantenía los ríos limpios y los puertos llenos de vida. "
             "Cantaba a las mareas y ellas le respondían.",
             "Poseída, las aguas se estancaron y trajeron pestes. Su canto "
             "ahora es un lamento que arrastra a los barcos."),
    "tierra": ("Con la maga Terra, las minas daban oro y las montañas nos "
               "guardaban como una madre de piedra.",
               "Hoy la tierra se agrieta y se traga aldeas enteras. Su fuerza, "
               "esclava del Mago Negro, ya no distingue amigo de enemigo."),
    "rayo": ("Electra repartía su energía con justicia: ninguna lámpara se "
             "apagaba y las noches eran fiesta.",
             "Su rayo, encadenado por el Mago Negro, ahora solo trae tormentas "
             "que parten los tejados y el alma."),
    "hielo": ("La maga Gélida regalaba inviernos serenos y agua pura de "
              "deshielo. Su calma nos enseñaba paciencia.",
              "Bajo el hechizo, ventiscas eternas sepultan los caminos. "
              "Su serenidad se volvió un silencio que congela."),
}

# El Gran Orden mundial de los Dos Triángulos (▲ blanco arriba, ▼ negro abajo).
ORDER_LORE = [
    "Todo lo rige el Gran Orden de los Dos Triángulos: el negro abajo, "
    "sosteniendo el peso; el blanco arriba, recibiendo la gloria. Pagamos "
    "tributo al de abajo... pero las órdenes, juro, bajan desde arriba.",
    "El Mago Negro firma cada decreto del Orden y carga con cada odio. "
    "La luz solo observa desde su trono. ¿No te parece demasiado cómodo, viajero?",
    "Nací bajo el Orden de los Dos Triángulos y moriré bajo él, salvo que "
    "alguien rompa el sello. Dicen que hace falta un mago sin color... uno gris.",
]
# Charla de NPCs (NO magas). Variada y ÚNICA por reino+etapa: vida cotidiana,
# rumores, pistas y PRESAGIOS sobre el verdadero villano. Se reparten sin repetir.
NPC_NAMES = ["Aldeano", "Aldeana", "Pastor", "Herrera", "Niño", "Anciana",
             "Viajera", "Tabernero", "Pescador", "Cazadora", "Bardo", "Costurera",
             "Molinero", "Curandera", "Vagabundo", "Centinela"]
NPC_LINES = [
    "Mi abuela decía que el color no es del que reina, sino del que ama la tierra.",
    "¿Has notado que el Mago Blanco nunca se ensucia las manos en esta guerra?",
    "Recé al triángulo de arriba toda mi vida. ¿Y si rezaba al amo equivocado?",
    "Dicen que un mago sin color romperá el sello. Tú no tienes color, ¿verdad?",
    "El Mago Negro da miedo, sí... pero el miedo es fácil de fabricar, viajero.",
    "Vendí mi cosecha por monedas con dos triángulos. Pesan como una condena.",
    "Cada noche oigo llorar a alguien tras la puerta del Orden. ¿Será el Mago Negro?",
    "Mi hijo se alistó con la luz. Volvió hablando solo de obedecer.",
    "Antes cantábamos al trabajar. El silencio llegó con los decretos, no con la sombra.",
    "Un viajero gris... eso decían las viejas profecías. Mira por dónde.",
    "Si liberas a nuestra maga, te invito a la mejor sopa del reino.",
    "No confíes en quien sonríe mientras otros cargan la culpa.",
    "He visto al Blanco hablar a solas con sombras. Nadie me cree.",
    "El Orden promete paz. Yo solo veo cadenas pintadas de blanco.",
    "Mi padre forjó el trono de los Dos Triángulos. Murió arrepentido.",
    "Dicen que las magas no se volvieron malas: se las pusieron así.",
    "Cuídate del que reparte miedo y luego ofrece consuelo.",
    "Cuando todo sea gris, quizá por fin seamos libres de los colores.",
    "La luz que no calienta y solo deslumbra... ¿es luz o es trampa?",
    "Yo planté un árbol el día que nació la maga. Aún resiste, como nosotros.",
    "El tabernero jura que el Mago Blanco firma los decretos que el Mago Negro proclama.",
    "Pequeño, no temas al gris: es el color de quien escucha a todos.",
    "Hay quien prospera con esta guerra. Pregúntate quién, y tendrás tu villano.",
    "Mis redes salen vacías desde la posesión. El mar también está preso.",
    "Te di mi última vela para tu viaje. Devuélvenos la luz de verdad.",
    "Dos triángulos, un mismo titiritero. Algún día lo entenderás.",
    "Soñé con seis mujeres encadenadas y un hombre blanco riendo. Solo un sueño... ¿no?",
    "El que nada pierde en una guerra suele ser quien la empezó.",
    "Gracias por pasar, gris. Hacía años que nadie nos miraba a los ojos.",
    "Mi telar tejía banderas de colores. Ahora solo me piden blanco y negro.",
    "Si ves a la maga, dile que su pueblo la espera con la mesa puesta.",
    "No todos los monstruos rugen; algunos bendicen.",
]


# Finales múltiples: uno por maga (la que MÁS actuó contigo en combate).
ENDINGS = {
    "fuego": ["Pyra fue tu llama más fiel en cada batalla.",
              "Juntos forjáis una era donde el fuego calienta, no consume.",
              "El Mago Gris y la Maga de Fuego encienden la esperanza del mundo."],
    "planta": ["Sylva creció a tu lado en cada paso del viaje.",
               "Bajo su cuidado, el mundo reverdece libre de los triángulos.",
               "El Gris y la Maga de Planta siembran una era de vida."],
    "agua": ["Marina fluyó contigo en cada combate.",
             "Los ríos y mares renacen limpios bajo su mano.",
             "El Gris y la Maga de Agua devuelven la calma al mundo."],
    "tierra": ["Terra fue tu muro inquebrantable en la guerra.",
               "Sobre cimientos justos reconstruís el reino.",
               "El Gris y la Maga de Tierra forjan una era firme y segura."],
    "rayo": ["Electra brilló a tu lado en cada chispa de la lucha.",
             "Su luz inaugura una era veloz y radiante.",
             "El Gris y la Maga de Rayo iluminan el mundo liberado."],
    "hielo": ["Gélida mantuvo la calma junto a ti en cada batalla.",
              "Una paz serena, pura como la escarcha, cubre el mundo.",
              "El Gris y la Maga de Hielo guardan la quietud de la nueva era."],
    "_": ["Con las seis magas libres, el mundo respira de nuevo.",
          "No reclamaste trono ni poder: fundaron un consejo sin amos.",
          "El gris —color de todos y de ninguno— es el símbolo del mundo libre."],
    "oscuro": ["Tomaste cada poder, castigaste sin piedad, destruiste al Mago Negro.",
               "Sobre las cenizas del viejo Orden te alzas tú.",
               "Un nuevo triángulo gobierna ahora... y es gris."],
    "blanco": ["Te sientas en el trono de luz que dejó el Blanco.",
               "Sonríes al pueblo mientras, en secreto, tejes nuevos hilos.",
               "El Orden no cayó: solo cambió de amo. Eres el nuevo Mago Blanco."],
    "feliz": ["Perdonaste al Mago Negro y juntos vencisteis al verdadero villano.",
              "Las seis magas, libres, devuelven el color al mundo.",
              "Sin tronos ni triángulos —hasta el Mago Negro, redimido— viven en paz.",
              "El mejor de los finales."],
}
# Texto scripted al LIBERAR a cada maga (discurso + reacción), por si la IA no responde.
RESCUE_LINES = {
    "fuego": ("La llama vuelve a ser mía... ¡y arde por ti, Gris! El Mago Negro "
              "apagó mi calor; tú me lo devolviste.",
              "Pyra: Donde vayas, mi fuego irá contigo. Lo juro por mi reino."),
    "planta": ("Respiro otra vez... mis raíces ya no duelen. Rompiste el hechizo "
               "que pudría mi bosque.",
               "Sylva: Floreceré a tu lado, Gris. Cuenta con mi savia y mi vida."),
    "agua": ("El agua vuelve a cantar en mí. Estaba ahogada en sombra, y me "
             "sacaste a la superficie.",
             "Marina: Fluiré contigo hasta el final, pase lo que pase."),
    "tierra": ("Mi piedra ya no obedece al Negro. Has movido una montaña, Gris.",
               "Terra: Seré tu muro. Nada te tocará mientras yo respire."),
    "rayo": ("¡La chispa volvió! Sentía mi rayo encadenado... ahora truena libre.",
             "Electra: Rápida y tuya. ¡Vamos a iluminar este mundo!"),
    "hielo": ("La calma regresa a mi escarcha. Gracias por derretir mi prisión.",
              "Gélida: Mantendré la cabeza fría por los dos. Estoy contigo."),
}

HOUSES = {}             # registro de interiores: key -> {return_to, return_pos, lore, elem}
RT = {}                 # cache de runtime por clave de ubicación

# Frases VARIADAS de los aldeanos cuando su maga YA fue liberada ({maga}, {reino}).
# Se elige una estable por NPC (según su posición) para que no se repitan tanto.
LIBERATED_LINES = [
    "¡{reino} respira otra vez! Gracias por liberar a {maga}, Mago Gris.",
    "Desde que {maga} es libre, {reino} recupera sus colores. Te lo debemos todo.",
    "Mira cómo brilla {reino} de nuevo. {maga} volvió a velar por nosotros.",
    "Los niños vuelven a jugar en las calles de {reino}. Gracias a ti y a {maga}.",
    "{maga} ya no tiene esa mirada vacía. Le devolviste el alma, Gris.",
    "Esta noche encenderemos farolas en {reino} en tu honor, Mago Gris.",
    "El aire de {reino} huele distinto: huele a libertad. Gracias por {maga}.",
    "Cuentan que {maga} preguntó por ti. Quiere darte las gracias en persona.",
    "Sin la sombra del Mago Negro, {reino} florece. Eres bienvenido siempre aquí.",
    "Pensábamos que {reino} estaba perdido. Tú y {maga} nos demostrasteis lo contrario.",
    "Brindamos por ti en cada hogar de {reino}, viajero gris.",
    "{maga} ya cuida otra vez de las cosechas. {reino} no pasará hambre este invierno.",
]


def villager_text(tk, world_done):
    """Texto del aldeano: si su maga ya fue liberada, una frase VARIADA (no repetida)."""
    kind = tk.get("dyn")
    if not kind:
        return tk["text"]
    el = tk.get("welem")
    reino = ELEM_NAME.get(el, "")
    maga = MAGA_BY_ELEM[el]["name"] if el in MAGA_BY_ELEM else ""
    if world_done.get(el) and kind in ("ciudadano", "house"):
        idx = (tk.get("x", 0) + tk.get("y", 0)) % len(LIBERATED_LINES)
        return LIBERATED_LINES[idx].format(reino=reino, maga=maga)
    return tk["text"]


def blank_grid(w, h):
    g = [[0] * w for _ in range(h)]
    for x in range(w):
        g[0][x] = 1
        g[h - 1][x] = 1
    for y in range(h):
        g[y][0] = 1
        g[y][w - 1] = 1
    return g


def _bake(key, name, theme, w, h, spawn, decor, talkers, enemies, exits, seed,
          tiles=None, chests=None):
    """Construye el grid + estado de una ubicación a partir de sus datos."""
    cx, cy = w // 2, h // 2
    g = blank_grid(w, h)
    protect = set()
    for x in range(w):
        protect.add((x, cy))
    for y in range(h):
        protect.add((cx, y))
    protect.add(spawn)
    for ex in exits:
        protect.add(ex["pos"])
        ax, ay = ex["pos"]
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                protect.add((ax + dx, ay + dy))
    for a in talkers + enemies + (chests or []):
        protect.add((a["x"], a["y"]))
    for (x, y, t) in (tiles or []):       # tiles fijos (p.ej. paredes de casas)
        g[y][x] = t
        protect.add((x, y))
    rng = random.Random(seed)
    for (tile, dens) in decor:
        for y in range(1, h - 1):
            for x in range(1, w - 1):
                if (x, y) in protect or g[y][x] != 0:
                    continue
                if rng.random() < dens:
                    g[y][x] = tile
    for ex in exits:
        x, y = ex["pos"]
        g[y][x] = 4
    tk = []
    for t in talkers:
        d = dict(t)
        d["color"] = ELEM_COLOR.get(t.get("elem", "luz"), (220, 200, 80))
        tk.append(d)
    en = [dict(e, alive=True, eid=i, color=ELEM_COLOR[e["elem"]])
          for i, e in enumerate(enemies)]
    ch = [dict(c, got=False) for c in (chests or [])]
    return {"name": name, "theme": theme, "grid": g, "w": w, "h": h,
            "spawn": spawn, "talkers": tk, "enemies": en, "exits": exits,
            "chests": ch}


def build_hub():
    w, h = HUB
    cx, cy = w // 2, h // 2
    exits = []
    # 6 puertas (3 arriba, 3 abajo), una por mundo en WORLD_ORDER
    door_pos = [(cx - 10, 0), (cx, 0), (cx + 10, 0),
                (cx - 10, h - 1), (cx, h - 1), (cx + 10, h - 1)]
    for elem, pos in zip(WORLD_ORDER, door_pos):
        exits.append({"pos": pos, "world": elem, "to": f"{elem}:0",
                      "spawn": (1, _by), "elem": elem,
                      "label": f"{MAGA_BY_ELEM[elem]['name']} · {ELEM_NAME[elem]}"})
    # puerta del final: la comunidad cree que ahí está el Mago Negro (villano aparente)
    exits.append({"pos": (w - 1, cy), "final": True, "to": "f1",
                  "spawn": (1, BIG[1] // 2), "elem": "sombra",
                  "label": "Guarida del Mago Negro"})
    talkers = [{"x": cx, "y": cy - 3, "elem": "neutro", "name": "Eco del Gris",
                "text": "El Mago Negro poseyó a las seis magas y las encerró tras "
                        "estas puertas. Cada cartel dice qué maga hay dentro. "
                        "Libéralas a todas para abrir su guarida."},
               {"x": cx + 4, "y": cy - 2, "elem": "luz", "name": "Mago Blanco",
                "ai_persona": PERSONA_BLANCO,
                "text": "Soy el Mago Blanco, tu guía. Confía en mi luz: libera a las "
                        "magas del yugo del Mago Negro y acaba con él. Estaré contigo."},
               {"x": cx - 5, "y": cy + 2, "elem": "rayo", "name": "Mercader",
                "shop": True, "text": "¡Pociones, armas y armaduras! El oro que "
                "ganes peleando, gástalo aquí."},
               {"x": cx - 8, "y": cy - 4, "elem": "luz", "name": "Refugiada",
                "text": "Llegamos aquí huyendo de los seis reinos. Eres nuestra "
                        "última esperanza, mago sin color."},
               {"x": cx + 8, "y": cy + 4, "elem": "luz", "name": "Anciano",
                "text": "Confía en el Blanco si quieres... pero yo viví bajo los "
                        "Dos Triángulos. La gloria siempre fue para el de arriba."},
               {"x": cx + 7, "y": cy - 5, "elem": "luz", "name": "Niña",
                "text": "¿Por qué el Mago Blanco nunca entra a las puertas a pelear? "
                        "Siempre te manda a ti, señor gris."}]
    return _bake("hub", "Nexo del Gris", "hub", w, h, (cx, cy),
                 [(1, 0.03)], talkers, [], exits, 7000)


def build_world(elem, s):
    w, h = BIG
    cx, cy = w // 2, h // 2
    theme = WORLD_THEME[elem]
    name = f"{WORLD_NAME[elem]}  ({s + 1}/3)"
    rng = random.Random(3000 + hash(elem) % 500 + s)
    creatures = AMBIENT[theme]
    exits = []
    if s == 0:
        exits.append({"pos": (0, cy), "to": "hub", "spawn": (HUB[0] // 2, HUB[1] // 2)})
    else:
        exits.append({"pos": (0, cy), "to": f"{elem}:{s-1}", "spawn": (w - 3, cy)})
    if s < 2:
        exits.append({"pos": (w - 1, cy), "to": f"{elem}:{s+1}",
                      "spawn": (1, cy), "locked": True})

    enemies, talkers, used = [], [], {(1, cy)}

    def scatter(x0, x1):
        for _ in range(30):
            p = (rng.randint(x0, x1), rng.randint(4, h - 4))
            if p not in used:
                used.add(p)
                return p
        return (rng.randint(x0, x1), rng.randint(4, h - 4))

    if s < 2:
        n_ac = 2 + s
        aco_pos = []
        for k in range(n_ac):
            x = int(w * (0.30 + 0.5 * (k / max(1, n_ac - 1)))) if n_ac > 1 else cx
            y = max(4, min(h - 4, cy + rng.randint(-22, 22)))
            used.add((x, y))
            enemies.append({"x": x, "y": y, "elem": elem, "kind": "acolito",
                            "name": "Acólito " + ELEM_NAME[elem]})
            aco_pos.append((x, y))
        for _ in range(7 + s * 2):                       # criaturas de ambiente
            p = scatter(8, w - 8)
            enemies.append({"x": p[0], "y": p[1], "elem": elem, "kind": "ambient",
                            "chase": rng.random() < 0.35,
                            "name": rng.choice(creatures)})
        for k in range(3):                               # aldeanos exploradores
            ax = int(w * (0.16 + 0.30 * k))
            ay = max(3, min(h - 3, cy + (10 if k % 2 else -10)))
            used.add((ax, ay))
            talkers.append({"x": ax, "y": ay, "elem": "luz", "name": "Aldeano",
                            "scout": True, "welem": elem,
                            "text": f"Vi acólitos del Mago Negro en {ELEM_NAME[elem]}..."})
    else:
        maga = MAGA_BY_ELEM[elem]
        # la maga aguarda en su TRONO, al fondo (este), esperando al Mago Gris
        tx_m = w - 8
        used.add((tx_m, cy))
        enemies.append({"x": tx_m, "y": cy, "elem": elem, "boss": True, "maga": elem,
                        "throne": True, "kind": "boss",
                        "name": maga["name"] + " (poseída)"})
        for _ in range(5):
            p = scatter(8, w - 8)
            enemies.append({"x": p[0], "y": p[1], "elem": elem, "kind": "ambient",
                            "chase": rng.random() < 0.35,
                            "name": rng.choice(creatures)})
        talkers.append({"x": 10, "y": cy, "elem": "luz", "name": "Aldeano",
                        "text": f"La maga {maga['name']} está al fondo, al este, "
                                "poseída por el Mago Negro. ¡Véncela para liberarla!"})

    # aldeanos charlatanes: líneas ÚNICAS por reino+etapa (presagios y vida cotidiana)
    w_idx = WORLD_ORDER.index(elem)
    base = w_idx * 5 + s * 2
    for k in range(2 if s < 2 else 1):
        li = (base + k) % len(NPC_LINES)
        p = scatter(8, w - 8)
        talkers.append({"x": p[0], "y": p[1], "elem": "luz",
                        "name": NPC_NAMES[li % len(NPC_NAMES)],
                        "text": NPC_LINES[li]})

    # vendedor errante: aparece en la etapa 2 O la 3 (al azar, fijo por mundo)
    merch_stage = random.Random(5000 + hash(elem) % 997).choice([1, 2])
    if s == merch_stage:
        talkers.append({"x": cx - 14, "y": cy, "elem": "rayo",
                        "name": "Mercader Errante", "shop": True,
                        "text": "Mercancías para tu viaje, mago."})

    # 1 casa por etapa con interior (2 aldeanos); el texto cambia por etapa
    house_tiles = []
    hx, hy = int(w * 0.42), cy - 7
    for ddx in (0, 1, 2):               # techo
        house_tiles.append((hx + ddx, hy, 1))
    house_tiles.append((hx, hy + 1, 1))             # paredes laterales
    house_tiles.append((hx + 2, hy + 1, 1))
    door = (hx + 1, hy + 1)                          # puerta de la casa
    ikey = f"{elem}:{s}:house0"
    HOUSES[ikey] = {"return_to": f"{elem}:{s}", "return_pos": (hx + 1, hy + 2),
                    "lore": LORE[(hash(elem) + s) % len(LORE)],
                    "elem": elem, "s": s}
    exits.append({"pos": door, "to": ikey, "spawn": (8, 8), "house": True})

    # CIUDADANO junto al spawn: te recibe con un texto distinto por reino y etapa
    reino = ELEM_NAME[elem]
    maga = MAGA_BY_ELEM[elem]["name"]
    antes_r, desp_r = REIGN.get(elem, ("", ""))
    greet = [
        f"Bienvenido al reino de {reino}, Mago Gris. {antes_r} Pero el Mago Negro "
        f"poseyó a {maga} y todo cayó en sombra. ¡Devuélvenos los colores!",
        f"Te adentras más en {reino}. {desp_r} Los acólitos del Mago Negro acechan: "
        "no bajes la guardia.",
        f"El trono de {reino} está al este. {maga}, poseída, aguarda. "
        "¡Rompe el hechizo y libérala!",
    ][min(s, 2)]
    talkers.insert(0, {"x": 3, "y": cy, "elem": "luz", "name": "Ciudadano",
                       "text": greet, "dyn": "ciudadano", "welem": elem})

    # tesoros ocultos: 1-2 cofres por etapa, escalados al progreso del mundo
    ctier = 1 + WORLD_ORDER.index(elem) + s
    chests = []
    for _ in range(rng.randint(1, 2)):
        cp = scatter(8, w - 8)
        chests.append(_rand_chest(cp[0], cp[1], rng, ctier))

    return _bake(f"{elem}:{s}", name, theme, w, h, (1, cy),
                 WORLD_DECOR[elem], talkers, enemies, exits,
                 2000 + hash(elem) % 999 + s, tiles=house_tiles, chests=chests)


def build_house(key):
    info = HOUSES[key]
    w, h = 16, 10
    el = info.get("elem", "fuego")
    s = info.get("s", 0)
    if info.get("final_gift"):                  # casas del refugio final (mundo 7)
        talkers = [{"x": 5, "y": 3, "elem": "luz", "name": "Refugiado",
                    "text": "Huimos de la guarida. Toma esto, valiente: lo "
                            "guardábamos para quien se atreviera a entrar."},
                   {"x": 10, "y": 3, "elem": "luz", "name": "Anciana",
                    "text": "El Mago Negro no es el verdadero amo. Abre los ojos "
                            "antes del final, Mago Gris."}]
        exits = [{"pos": (w // 2, h - 1), "to": info["return_to"],
                  "spawn": info["return_pos"]}]
        chests = [_rand_chest(3, 5, random.Random(8200 + hash(key) % 999), 8),
                  _rand_chest(12, 5, random.Random(8201 + hash(key) % 999), 8)]
        return _bake(key, "Refugio", "casa", w, h, (w // 2, h - 3),
                     [], talkers, [], exits, 8200, chests=chests)
    maga = MAGA_BY_ELEM[el]["name"]
    reino = ELEM_NAME[el]
    antes, despues = REIGN.get(el, ("", ""))
    orden = ORDER_LORE[s % len(ORDER_LORE)]
    # el texto cambia por ETAPA y menciona el reino (único entre mundos)
    if s == 0:
        pair = [("Aldeano viejo", f"¿Recuerdas el reinado de la maga {maga} en {reino}? "
                                  f"{antes}"),
                ("Aldeana", f"Y mira {reino} ahora... {despues} Si la liberas, todo "
                            "volvería a ser como antes.")]
    else:
        pair = [("Anciano", f"Aquí en {reino} lo sentimos: {orden}"),
                ("Niña", f"En {reino} dicen que un mago gris romperá el sello de los "
                         "dos triángulos y devolverá a las magas. ¿Eres tú?")]
    talkers = [{"x": 5, "y": 3, "elem": "luz", "name": pair[0][0], "text": pair[0][1],
                "dyn": "house", "welem": el},
               {"x": 10, "y": 3, "elem": "luz", "name": pair[1][0], "text": pair[1][1],
                "dyn": "house", "welem": el}]
    exits = [{"pos": (w // 2, h - 1), "to": info["return_to"],
              "spawn": info["return_pos"]}]
    ctier = 1 + WORLD_ORDER.index(el) + s if el in WORLD_ORDER else 4
    chests = [_rand_chest(12, 6, random.Random(8000 + hash(key) % 999), ctier)]
    return _bake(key, f"Hogar de {ELEM_NAME[el]}", "casa", w, h, (w // 2, h - 3),
                 [], talkers, [], exits, 8000, chests=chests)


def _rand_chest(x, y, rng, tier=6):
    """Cofre oculto: oro o un objeto, escalado por progreso."""
    if rng.random() < 0.5:
        amt = rng.randint(30, 70) * tier
        return {"x": x, "y": y, "kind": "gold", "val": amt}
    pool = ["Poción", "Super Poción", "Éter", "Mega Poción", "Pluma Fénix"]
    return {"x": x, "y": y, "kind": "item", "val": rng.choice(pool)}


# --- ARCO FINAL (mundo 7): cadena de stages f1..f6 ---
def build_f1():
    # 7-1: enfrentamiento de acólitos del Mago Negro. Puerta este sellada
    #      hasta vencerlos a todos.
    w, h = BIG
    cx, cy = w // 2, h // 2
    rng = random.Random(9001)
    enemies = []
    for k in range(5):
        x = int(w * (0.25 + 0.5 * (k / 4)))
        y = max(4, min(h - 4, cy + rng.randint(-20, 20)))
        el = rng.choice(WORLD_ORDER)
        enemies.append({"x": x, "y": y, "elem": el, "kind": "acolito",
                        "name": "Acólito del Mago Negro"})
    for _ in range(5):                                   # algunos que te persiguen
        p = (rng.randint(8, w - 8), rng.randint(4, h - 4))
        enemies.append({"x": p[0], "y": p[1], "elem": "sombra", "kind": "ambient",
                        "chase": True, "name": rng.choice(AMBIENT["cripta"])})
    talkers = [{"x": 3, "y": cy, "elem": "luz", "name": "Las 6 magas",
                "text": "Estamos contigo, Gris. Esta es la guarida del Mago Negro. "
                        "Derrota a sus acólitos para abrir la puerta del fondo."}]
    chests = [_rand_chest(rng.randint(10, w - 10), rng.randint(4, h - 4), rng)
              for _ in range(2)]
    exits = [{"pos": (w - 1, cy), "to": "f2", "spawn": (1, cy), "locked": True}]
    return _bake("f1", "Guarida del Mago Negro (1/6)", "cripta", w, h, (1, cy),
                 [(1, 0.05)], talkers, enemies, exits, 9000,
                 chests=chests)


def build_f2():
    # 7-2: descanso. Casas con regalos y un mercader. SIN enemigos.
    w, h = BIG
    cx, cy = w // 2, h // 2
    talkers = [{"x": 6, "y": cy, "elem": "rayo", "name": "Mercader", "shop": True,
                "text": "Un refugio antes del titiritero. Reponte, mago."}]
    # 2 casas con sus regalos
    tiles, exits = [], []
    for hi, hx in enumerate((int(w * 0.40), int(w * 0.62))):
        hy = cy - 7
        for ddx in (0, 1, 2):
            tiles.append((hx + ddx, hy, 1))
        tiles.append((hx, hy + 1, 1)); tiles.append((hx + 2, hy + 1, 1))
        ikey = f"f2:house{hi}"
        HOUSES[ikey] = {"return_to": "f2", "return_pos": (hx + 1, hy + 2),
                        "lore": LORE[hi % len(LORE)], "elem": "neutro", "s": 0,
                        "final_gift": True}
        exits.append({"pos": (hx + 1, hy + 1), "to": ikey, "spawn": (8, 8),
                      "house": True})
    talkers.append({"x": cx, "y": cy + 4, "elem": "neutro", "name": "Ermitaño",
                    "text": "Más allá aguarda el Mago Negro. Dicen que él también "
                            "es una víctima... pero eso lo juzgarás tú."})
    rng = random.Random(9002)
    chests = [_rand_chest(rng.randint(10, w - 10), rng.randint(4, h - 4), rng)
              for _ in range(2)]
    exits.append({"pos": (w - 1, cy), "to": "f3", "spawn": (1, cy)})
    return _bake("f2", "Refugio (2/6)", "cripta", w, h, (1, cy),
                 [(1, 0.03)], talkers, [], exits, 9010, tiles=tiles, chests=chests)


def build_f3():
    # 7-3: el Mago Negro. Al vencerlo: matarlo (absorbes poder) o perdonarlo (se une).
    w, h = BIG
    cx, cy = w // 2, h // 2
    talkers = [{"x": 3, "y": cy, "elem": "neutro", "name": "Las 6 magas",
                "text": "El Mago Negro está al frente. Recuerda: la verdad no "
                        "siempre lleva túnica oscura."}]
    enemies = [{"x": cx, "y": cy, "elem": "sombra", "boss": True, "subfinal": True,
                "throne": True, "kind": "boss", "name": "Mago Negro"}]
    return _bake("f3", "Trono de los Dos Triángulos (3/6)", "cripta", w, h, (1, cy),
                 [(1, 0.04)], talkers, enemies, [], 9020)


def build_f4():
    # 7-4: el DRAGÓN de Luz del Mago Blanco. Al vencerlo, el Blanco huye al santuario.
    w, h = BIG
    cx, cy = w // 2, h // 2
    talkers = [{"x": 3, "y": cy, "elem": "luz", "name": "Mago Blanco",
                "ai_persona": PERSONA_BLANCO,
                "text": "Mi dragón te detendrá, Gris. No des un paso más."}]
    enemies = [{"x": cx, "y": cy, "elem": "luz", "boss": True, "dragon": True,
                "kind": "boss", "name": "Dragón de Luz"}]
    return _bake("f4", "Foso del Dragón (4/6)", "cripta", w, h, (1, cy),
                 [(1, 0.05)], talkers, enemies, [], 9030)


def build_f5():
    # 7-5: último mercader antes del Mago Blanco.
    w, h = BIG
    cx, cy = w // 2, h // 2
    talkers = [{"x": 6, "y": cy, "elem": "rayo", "name": "Mercader", "shop": True,
                "text": "Última parada antes del verdadero amo. Que la luz no te engañe."}]
    rng = random.Random(9004)
    chests = [_rand_chest(rng.randint(10, w - 10), rng.randint(4, h - 4), rng)]
    exits = [{"pos": (w - 1, cy), "to": "f6", "spawn": (1, cy)}]
    return _bake("f5", "Umbral del Santuario (5/6)", "santuario", w, h, (1, cy),
                 [(1, 0.03)], talkers, [], exits, 9040, chests=chests)


def build_f6():
    # 7-6: el Mago Blanco, verdadero villano final.
    w, h = BIG
    cx, cy = w // 2, h // 2
    talkers = [{"x": 3, "y": cy, "elem": "luz", "name": "Mago Blanco",
                "ai_persona": PERSONA_BLANCO,
                "text": "Llegaste hasta mi trono. Toda la luz era mía, Gris. Siempre."}]
    enemies = [{"x": cx, "y": 8, "elem": "luz", "boss": True, "final": True,
                "throne": True, "kind": "boss", "name": "Mago Blanco"}]
    return _bake("f6", "Santuario de la Luz (6/6)", "santuario", w, h, (cx, h - 3),
                 [(1, 0.04)], talkers, enemies, [], 9050)


def build_endscene(ekey):
    # Mundo 8: escena final caminable, una por desenlace. Camina a la luz para el epílogo.
    w, h = 30, 22
    cx, cy = w // 2, h // 2
    theme = "cripta" if ekey == "oscuro" else "santuario"
    narr = {
        "oscuro": "El trono te reclama. La sombra es tu nuevo hogar.",
        "blanco": "La luz te corona. Que tu reinado sea justo... o no.",
        "feliz": "El hechizo se ha roto. Empieza una era sin titiriteros.",
        "_": "Devolviste los colores al mundo y seguiste tu camino.",
    }.get(ekey, "Vuestro vínculo decidió el destino del mundo.")
    talkers = [{"x": cx, "y": cy + 3, "elem": "neutro", "name": "Narrador",
                "text": narr}]
    exits = [{"pos": (cx, 2), "to": "__ending__", "spawn": (cx, cy),
              "ending": ekey}]
    return _bake(f"end:{ekey}", "Escena final", theme, w, h, (cx, h - 3),
                 [(1, 0.02)], talkers, [], exits, 9100 + (hash(ekey) % 500))


_FIN_BUILDERS = {"f1": build_f1, "f2": build_f2, "f3": build_f3,
                 "f4": build_f4, "f5": build_f5, "f6": build_f6}


def get_stage(key):
    if key not in RT:
        if key == "hub":
            RT[key] = build_hub()
        elif key in _FIN_BUILDERS:
            RT[key] = _FIN_BUILDERS[key]()
        elif key.startswith("end:"):
            RT[key] = build_endscene(key.split(":", 1)[1])
        elif "house" in key:
            RT[key] = build_house(key)
        else:
            elem, s = key.split(":")
            RT[key] = build_world(elem, int(s))
    return RT[key]


def blocked(grid, tx, ty):
    h, w = len(grid), len(grid[0])
    if tx < 0 or ty < 0 or tx >= w or ty >= h:
        return True
    return grid[ty][tx] not in TILE_WALK


def calc_cam(px, py, w, h):
    """Cámara centrada en el jugador, recortada al mapa. El área de juego va
    bajo el HUD (alto visible = H - HUD_H), por eso usa esa altura vertical."""
    vh = H - HUD_H
    cx = max(0, min(px * TILE + TILE // 2 - W // 2, w * TILE - W))
    cy = max(0, min(py * TILE + TILE // 2 - vh // 2, max(0, h * TILE - vh)))
    return int(cx), int(cy)


def draw_tile(theme, x, y, kind, camx, camy):
    th = THEMES[theme]
    r = pygame.Rect(x * TILE - camx, y * TILE - camy, TILE, TILE)
    if kind == 1:
        pygame.draw.rect(screen, th["wall"], r)
        pygame.draw.rect(screen, th["wall2"], r, 2)
        return
    pygame.draw.rect(screen, th["floor"], r)
    pygame.draw.rect(screen, th["grid"], r, 1)
    if kind == 2:
        dry = theme.endswith("_dark")          # mundo poseído -> árbol SECO
        pygame.draw.rect(screen, (80, 55, 28) if dry else (90, 60, 30),
                         (r.centerx - 3, r.centery + 4, 6, 12))
        if dry:                                # copa rala + ramas secas
            pygame.draw.circle(screen, (120, 95, 45), r.center, TILE // 2 - 6)
            pygame.draw.line(screen, (95, 70, 35), r.center,
                             (r.centerx - 7, r.centery - 8), 2)
            pygame.draw.line(screen, (95, 70, 35), r.center,
                             (r.centerx + 7, r.centery - 9), 2)
        else:                                  # frondoso y verde (maga liberada)
            pygame.draw.circle(screen, (24, 95, 50), r.center, TILE // 2 - 2)
            pygame.draw.circle(screen, (40, 130, 70), r.center, TILE // 2 - 5)
    elif kind == 3:
        pygame.draw.rect(screen, (40, 90, 160), r.inflate(-4, -4))
        pygame.draw.rect(screen, (70, 130, 210), r.inflate(-4, -4), 2)
    elif kind == 4:
        pygame.draw.rect(screen, (60, 50, 30), r.inflate(-6, -2))
        pygame.draw.rect(screen, (210, 175, 70), r.inflate(-6, -2), 3)
        draw_text(screen, "▼", r.centerx - 5, r.centery - 8, font_sm, (240, 210, 120))


def draw_actor(color, px, py, bob=0, camx=0, camy=0, face=None, scale=1.0,
               wings=False):
    cx = int(px * TILE + TILE // 2 - camx)
    cy = int(py * TILE + TILE // 2 + bob - camy)
    rad = int((TILE // 2 - 5) * scale)
    if wings:                                   # alas (ángel / dragón)
        wc = (245, 245, 235) if scale <= 1.2 else (255, 250, 210)
        pygame.draw.polygon(screen, wc, [(cx - rad, cy), (cx - rad - 10, cy - 8),
                                         (cx - rad - 6, cy + 8)])
        pygame.draw.polygon(screen, wc, [(cx + rad, cy), (cx + rad + 10, cy - 8),
                                         (cx + rad + 6, cy + 8)])
    pygame.draw.ellipse(screen, (20, 20, 24), (cx - rad, cy + rad - 2, rad * 2, 7))
    pygame.draw.circle(screen, color, (cx, cy), rad)
    pygame.draw.circle(screen, WHITE, (cx, cy), rad, 2)
    # ojos/marcador en la dirección que mira
    fx, fy = face if face else (0, 1)
    ex, ey = cx + fx * 4, cy + fy * 3 - 1
    pygame.draw.circle(screen, BLACK, (ex - 3, ey), 2)
    pygame.draw.circle(screen, BLACK, (ex + 3, ey), 2)
    if face:
        pygame.draw.circle(screen, (250, 240, 180),
                           (cx + fx * rad, cy + fy * rad), 3)


def draw_chest(cx_t, cy_t, camx, camy):
    x = cx_t * TILE + TILE // 2 - camx
    y = cy_t * TILE + TILE // 2 - camy
    pygame.draw.rect(screen, (150, 105, 40), (x - 9, y - 5, 18, 13), border_radius=2)
    pygame.draw.rect(screen, (90, 60, 20), (x - 9, y - 5, 18, 13), 2, border_radius=2)
    pygame.draw.line(screen, (230, 200, 90), (x - 9, y + 1), (x + 9, y + 1), 2)
    pygame.draw.circle(screen, (230, 200, 90), (x, y + 1), 2)


def draw_throne(cx_t, cy_t, camx, camy):
    x = cx_t * TILE + TILE // 2 - camx
    y = cy_t * TILE + TILE // 2 - camy
    pygame.draw.rect(screen, (120, 95, 30), (x - 14, y - 20, 28, 30), border_radius=4)
    pygame.draw.rect(screen, (200, 170, 70), (x - 14, y - 20, 28, 30), 2, border_radius=4)
    pygame.draw.rect(screen, (90, 70, 20), (x - 16, y - 24, 6, 24))
    pygame.draw.rect(screen, (90, 70, 20), (x + 10, y - 24, 6, 24))


# ============================================================
#  CAJA DE DIÁLOGO (typewriter estilo Chrono Trigger)
# ============================================================
class DialogBox:
    def __init__(self):
        self.lines = []
        self.page = 0
        self.shown = 0
        self.active = False
        self.speaker = ""

    def open(self, speaker, text):
        self.speaker = speaker
        self.lines = wrap(text, font_md, W - 60)
        self.page = 0
        self.shown = 0
        self.active = True

    def advance(self):
        full = "".join(self._page_text())
        if self.shown < len(full):
            self.shown = len(full)
            return
        if self.page + 3 < len(self.lines):
            self.page += 3
            self.shown = 0
        else:
            self.active = False

    def _page_text(self):
        return self.lines[self.page:self.page + 3]

    def update(self):
        full = sum(len(l) for l in self._page_text())
        if self.shown < full:
            self.shown += OPTS.get("text_speed", 2)

    def draw(self):
        bh = 110
        box = pygame.Rect(20, H - bh - 16, W - 40, bh)
        pygame.draw.rect(screen, BOX_BG, box, border_radius=8)
        pygame.draw.rect(screen, BOX_BORDER, box, 3, border_radius=8)
        if self.speaker:
            tag = pygame.Rect(box.x + 14, box.y - 14, font_md.size(self.speaker)[0] + 20, 24)
            pygame.draw.rect(screen, BOX_BORDER, tag, border_radius=6)
            draw_text(screen, self.speaker, tag.x + 10, tag.y + 3, font_md, BLACK)
        remaining = self.shown
        yy = box.y + 16
        for ln in self._page_text():
            seg = ln[:max(0, remaining)]
            draw_text(screen, seg, box.x + 18, yy, font_md, WHITE)
            remaining -= len(ln)
            yy += 26
        draw_text(screen, "[E] continuar", box.right - 110, box.bottom - 22, font_xs, DIM)


# ============================================================
#  COMBATE
# ============================================================
class Battle:
    def __init__(self, party, enemies, armor_def=0, atk_bonus=0, pow_bonus=0):
        self.party = party
        self.enemies = enemies
        self.armor_def = armor_def   # bonus def (armadura), atk (arma), pow (foco)
        self.atk_bonus = atk_bonus
        self.pow_bonus = pow_bonus
        self.actors = party + enemies
        self.acted = set()           # quién ya actuó esta ronda (por id)
        self.phase = "menu"          # menu, target, power, bag, anim, msg, win, lose
        self.menu_i = 0
        self.sub_i = 0
        self.target_i = 0
        self.msg = ""
        self.msg_t = 0
        self.cur = None
        self.pend_power = None        # poder pendiente de elegir objetivo
        self.pend_item = None         # objeto pendiente de elegir aliado
        self.pend_combo = None        # combo triple pendiente de objetivo
        self.last_mult = 1.0
        self.comment = ""            # comentario "en vivo" de una compañera IA
        self.comment_t = 0
        self.warn = ""               # aviso (no consume turno)
        self.warn_t = 0
        self.suggestion = ""         # sugerencia de la compañera IA en su turno
        self.pending = None          # acción a resolver tras animación
        self.xp_reward = 0           # recompensas (se fijan al crear el combate)
        self.gold_reward = 0
        self.xp_given = 0
        self.level_events = []       # subidas de nivel resueltas al ganar
        self.loot = []               # objetos soltados por enemigos
        self.fled = False
        self._awarded = False
        self.shake_t = 0             # sacudida de pantalla al recibir un golpe
        self.menu = ["Atacar", "Poderes", "Combos", "Bolsa", "Cubrirse", "Huir"]
        self._next_actor()
        self.push_comment("start")

    def _alive(self, side):
        return [a for a in self.actors if a["alive"] and a["side"] == side]

    def _item_targets(self, item):
        """Aliados válidos para un objeto: caídos si es revivir, vivos si no."""
        if item and item.get("kind") == "revive":
            return [a for a in self.party if not a["alive"]]
        return [a for a in self.party if a["alive"]]

    def _next_actor(self):
        if not self._alive("hero"):
            self.phase = "lose"
            return
        if not self._alive("enemy"):
            self.phase = "win"
            self.push_comment("win")
            return
        # siguiente = mayor velocidad entre los VIVOS que aún no actuaron esta ronda
        alive = [a for a in self.actors if a["alive"]]
        pending = [a for a in alive if id(a) not in self.acted]
        if not pending:                          # ronda completa -> nueva ronda
            self.acted = set()
            pending = alive
        self.cur = max(pending, key=lambda a: a["spd"])
        self.acted.add(id(self.cur))
        self.cur["guard"] = False
        if self.cur["side"] == "enemy":
            self._enemy_turn()
        else:
            # TÚ controlas a todos. Si es compañera IA, muestra su sugerencia.
            self.phase = "menu"
            self.menu_i = 0
            self.suggestion = self._ai_suggest(self.cur) if self.cur.get("ai") else ""

    def _say(self, text, then="next"):
        self.msg = text
        self.msg_t = OPTS.get("battle_msg", 90)
        self.phase = "msg"
        self._after_msg = then

    def _warn(self, text):
        """Aviso que NO consume el turno (la fase del menú no cambia)."""
        self.warn = text
        self.warn_t = 90

    def _finish_msg(self):
        if self._alive("hero") == [] :
            self.phase = "lose"; return
        if self._alive("enemy") == []:
            self.phase = "win"; self.push_comment("win"); return
        self._next_actor()

    # ---- acciones ----
    def _roll_hit(self, src, dst):
        """Acierto/crítico según PRECISIÓN del atacante y VELOCIDAD (evasión) del rival."""
        eva = dst.get("spd", 0) // 3 + wear_bonus(dst, "eva") + (15 if dst.get("guard") else 0)
        pre = src.get("pre", 90)
        if random.randint(1, 100) > pre - eva:        # más velocidad rival -> más fallos
            return "miss"
        # crítico: sube con la PRECISIÓN (máx 75%) y se le RESTA la evasión del rival
        crit = max(0, min(75, 5 + max(0, pre - 85) // 2 + wear_bonus(src, "crit")) - eva)
        if random.randint(1, 100) <= crit:
            return "crit"
        return "hit"

    def _damage(self, src, dst, power, elem=None, crit=False):
        elem = elem or src.get("elem")
        mult = effectiveness(elem, dst.get("elem")) if elem and dst.get("elem") else 1.0
        defv = dst["df"] + (self.armor_def if dst.get("side") == "hero" else 0) \
            + wear_bonus(dst, "df")
        atk = src["atk"] + (self.atk_bonus if src.get("side") == "hero" else 0) \
            + wear_bonus(src, "atk")
        raw = atk + power
        base = raw - defv // 2 + random.randint(-3, 3)
        base = max(base, raw // 4)            # piso: la defensa nunca anula el golpe
        dmg = max(1, int(base * mult))
        if crit:
            dmg = int(dmg * 1.8)              # golpe directo
        if dst["guard"]:
            dmg = max(1, int(dmg * 0.5))      # cubrirse: -50% (no casi cero)
        agu = dst.get("agu", 0)              # AGUANTE: mitiga daño (máx 60%)
        if agu:
            dmg = max(1, int(dmg * (1 - min(agu, 60) / 100)))
        dst["hp"] = max(0, dst["hp"] - dmg)
        dst["hit_t"] = pygame.time.get_ticks()    # marca para el flinch del sprite
        if dst.get("side") == "hero":             # TÚ recibes -> sacude la pantalla
            self.shake_t = max(self.shake_t, 14 if not crit else 20)
        if dst["hp"] == 0:
            dst["alive"] = False
            if dst.get("side") == "enemy":
                boss = any(dst.get(k) for k in ("boss", "maga", "subfinal", "final"))
                chance = 1.0 if boss else 0.35       # jefes regalan seguro
                if random.random() < chance:
                    n = 2 if boss else 1             # los jefes regalan 2 objetos
                    for _ in range(n):
                        it = self._roll_drop(dst.get("lvl", 1))
                        if it:
                            it["qty"] += 1
                            self.loot.append(it["name"])
        self.last_mult = mult
        return dmg

    def _roll_drop(self, lvl):
        """Objeto que suelta un enemigo (mejor según su nivel)."""
        if lvl >= 8:
            pool = ["Mega Poción", "Super Éter", "Elixir", "Super Poción"]
        elif lvl >= 4:
            pool = ["Super Poción", "Super Éter", "Poción", "Éter"]
        else:
            pool = ["Poción", "Éter"]
        # objetos potentes solo si algún aliado ya tiene HP máx >= 100
        if not any(c["maxhp"] >= 100 for c in self.party):
            pool = [n for n in pool if n not in SUPER_GATED] or ["Poción"]
        name = random.choice(pool)
        return next((it for it in ITEMS if it["name"] == name), None)

    def _eff_tag(self):
        if self.last_mult >= SUPER:
            return "  ¡Súper efectivo!"
        if self.last_mult <= WEAK:
            return "  Poco efectivo..."
        return ""

    def _heal(self, dst, amt):
        dst["hp"] = min(dst["maxhp"], dst["hp"] + amt)
        return amt

    def do_attack(self, target):
        # ataque BÁSICO: usa el ELEMENTO del atacante (el Gris es neutro) -> los
        # elementos afectan también el golpe básico entre magas.
        roll = self._roll_hit(self.cur, target)
        if roll == "miss":
            self._say(f"{self.cur['name']} falla el golpe contra {target['name']}")
            return
        d = self._damage(self.cur, target, 0, elem=self.cur.get("elem", "neutro"),
                         crit=(roll == "crit"))
        verb = "derrota a" if not target["alive"] else "golpea a"
        tag = "  ¡GOLPE DIRECTO!" if roll == "crit" else ""
        self._say(f"{self.cur['name']} {verb} {target['name']} ({d}){tag}{self._eff_tag()}")

    def do_power(self, power, target):
        name, cost, val = power
        if self.cur["mp"] < cost:
            self._warn("¡MP insuficiente!"); return
        self.cur["mp"] -= cost
        if val < 0:
            h = self._heal(target, -val)
            self._say(f"{self.cur['name']} usa {name}: cura {h} a {target['name']}")
        elif val == 0:
            target["guard"] = True
            if target is self.cur:
                self._say(f"{self.cur['name']} usa {name} y se protege")
            else:
                self._say(f"{self.cur['name']} usa {name} y protege a {target['name']}")
        else:
            extra = (self.pow_bonus if self.cur.get("side") == "hero" else 0) \
                + wear_bonus(self.cur, "pow")
            d = self._damage(self.cur, target, val + extra)
            self._say(f"{self.cur['name']} lanza {name} a {target['name']} ({d}){self._eff_tag()}")
            if self.last_mult >= SUPER:
                self.push_comment("super", self.cur)

    def do_power_all(self, power):
        name, cost, val = power
        if self.cur["mp"] < cost:
            self._warn("¡MP insuficiente!"); return
        self.cur["mp"] -= cost
        extra = (self.pow_bonus if self.cur.get("side") == "hero" else 0) \
            + wear_bonus(self.cur, "pow")
        es = list(self._alive("enemy"))
        per = max(1, (val + extra) // max(1, len(es)))   # el golpe se REPARTE entre todos
        total = 0
        for en in es:
            total += self._damage(self.cur, en, per)
        self._say(f"{self.cur['name']} lanza {name} a TODOS ({total}){self._eff_tag()}")
        if self.last_mult >= SUPER:
            self.push_comment("super", self.cur)

    def do_item(self, item, target=None):
        tgt = target or self.cur
        if item["qty"] <= 0:
            self._warn("No quedan"); return
        if item["kind"] == "revive":
            if tgt["alive"]:
                self._warn(f"{tgt['name']} no está caído"); return
            item["qty"] -= 1
            tgt["alive"] = True
            tgt["hp"] = max(1, tgt["maxhp"] // 2)
            self._say(f"¡{item['name']} revive a {tgt['name']}!")
            return
        if tgt.get("alive") is False:
            self._warn(f"{tgt['name']} está caído (usa Pluma Fénix)"); return
        if item["kind"] == "hp" and tgt["hp"] >= tgt["maxhp"]:
            self._warn(f"{tgt['name']}: vida ya llena"); return
        if item["kind"] == "mp" and tgt["mp"] >= tgt["maxmp"]:
            self._warn(f"{tgt['name']}: maná ya lleno"); return
        item["qty"] -= 1
        if item["kind"] == "hp":
            self._heal(tgt, item["amt"])
            self._say(f"{tgt['name']} usa {item['name']} (+{item['amt']} HP)")
        elif item["kind"] == "mp":
            tgt["mp"] = min(tgt["maxmp"], tgt["mp"] + item["amt"])
            self._say(f"{tgt['name']} usa {item['name']} (+{item['amt']} MP)")
        else:                                  # Elixir: HP y MP al máximo
            tgt["hp"] = tgt["maxhp"]; tgt["mp"] = tgt["maxmp"]
            self._say(f"{tgt['name']} usa {item['name']} (¡recuperación total!)")

    def do_guard(self):
        self.cur["guard"] = True
        self._say(f"{self.cur['name']} se cubre")

    def try_flee(self):
        """Huir con probabilidad según velocidad. NO se puede huir de jefes/magas."""
        pe = self._alive("enemy")
        if any(e.get(k) for e in pe
               for k in ("boss", "maga", "subfinal", "final", "prologue", "dragon")):
            self._warn("¡No puedes huir de un jefe!"); return
        ph = self._alive("hero")
        ps = sum(h["spd"] for h in ph) / max(1, len(ph))
        es = sum(e["spd"] for e in pe) / max(1, len(pe))
        chance = max(25, min(90, 50 + int(ps - es) * 5))
        if random.randint(1, 100) <= chance:
            self.fled = True
            self.phase = "fled"
        else:
            self._say("¡No lograste huir!")     # falla -> pierdes el turno

    def available_combos(self):
        """Combos cuyos miembros están todos vivos en el equipo y con MP."""
        ids = {h["id"]: h for h in self._alive("hero")}
        out = []
        for c in COMBOS:
            members = [ids.get(m) for m in c["members"]]
            if all(members) and all(m["mp"] >= c["cost"] for m in members):
                out.append((c, members))
        return out

    def do_combo(self, combo, members):
        for m in members:
            m["mp"] -= combo["cost"]
        es = list(self._alive("enemy"))
        per = max(1, combo["dmg"] // max(1, len(es)))    # el golpe se REPARTE entre todos
        total = 0
        for en in es:
            total += self._damage(members[0], en, per, elem=combo["elem"])
        names = "+".join(m["name"] for m in members)
        self._say(f"{names}: ¡{combo['name']}! ({total} a todos){self._eff_tag()}")

    def do_combo_single(self, combo, members, target):
        """Triple concentrado en un solo enemigo (+60% de daño)."""
        for m in members:
            m["mp"] -= combo["cost"]
        d = self._damage(members[0], target, int(combo["dmg"] * 1.6),
                         elem=combo["elem"])
        names = "+".join(m["name"] for m in members)
        self._say(f"{names}: ¡{combo['name']} concentrado! ({d}){self._eff_tag()}")

    def _ai_suggest(self, c):
        """La compañera IA RECOMIENDA una jugada (no la aplica). Hook para LLM."""
        allies = self._alive("hero")
        foes = self._alive("enemy")
        heal = next((p for p in c["powers"] if p[2] < 0), None)
        low = [a for a in allies if a["hp"] < a["maxhp"] * 0.35]
        if heal and low and c["mp"] >= heal[1]:
            return f"sugiere: cura a {min(low, key=lambda a: a['hp'])['name']} con {heal[0]}"
        tgt = next((e for e in foes
                    if effectiveness(c["elem"], e.get("elem")) >= SUPER), None)
        if tgt:
            dmg = [p for p in c["powers"] if p[2] > 0 and c["mp"] >= p[1]]
            mv = max(dmg, key=lambda p: p[2])[0] if dmg else "atacar"
            return f"sugiere: {mv} a {tgt['name']} (¡es débil!)"
        return "sugiere: golpea al enemigo más herido"

    def _enemy_hit(self, t):
        """Un ataque enemigo a 't'. Devuelve (texto, daño). No cambia de fase.
        El PODER del ataque escala con el NIVEL del enemigo (acorde a su nivel)."""
        sp = self.cur.get("special")
        lp = self.cur.get("lvl", 1) * 2            # poder acorde al nivel
        r = random.random()
        if sp and r < 0.30:                        # ATAQUE MEJORADO (según su nivel)
            nm, bonus = sp
            d = self._damage(self.cur, t, random.randint(6, 12) + bonus + lp)
            return (f"¡{nm}! a {t['name']} ({d}){self._eff_tag()}", d)
        if r < 0.62:                               # básico (puede fallar/crit)
            roll = self._roll_hit(self.cur, t)
            if roll == "miss":
                return (f"falla contra {t['name']}", 0)
            d = self._damage(self.cur, t, random.randint(0, 4) + lp // 2,
                             elem=self.cur.get("elem", "neutro"), crit=(roll == "crit"))
            return (f"golpea a {t['name']} ({d})"
                    + ("  ¡DIRECTO!" if roll == "crit" else "") + self._eff_tag(), d)
        d = self._damage(self.cur, t, random.randint(4, 10) + lp)   # elemental
        el = ELEM_NAME.get(self.cur.get("elem"), "")
        return (f"lanza {el} a {t['name']} ({d}){self._eff_tag()}", d)

    def _is_negro(self):
        return ("Negro" in self.cur["name"] or self.cur.get("subfinal")
                or self.cur.get("prologue"))

    def _enemy_action(self):
        """UNA acción del enemigo (objeto / poder / ataque). Devuelve texto corto."""
        cur = self.cur
        caster = bool(cur.get("maga")) or self._is_negro()
        # OBJETO (poción) si está herido
        if caster and cur["hp"] < cur["maxhp"] * 0.5 and random.random() < 0.35:
            heal = min(cur["maxhp"] - cur["hp"], cur["maxhp"] // 3 + 40)
            cur["hp"] += heal
            return f"usa poción (+{heal})"
        # PODER (puede golpear a TODO el grupo)
        powers = [p for p in (cur.get("powers") or [])]
        if powers and random.random() < 0.5:
            pn, cost, val = random.choice(powers)
            if val < 0:                            # cura -> a sí misma
                heal = min(cur["maxhp"] - cur["hp"], abs(val))
                cur["hp"] += heal
                return f"{pn} (se cura +{heal})"
            if val == 0:                           # defensivo
                cur["guard"] = True
                return f"se protege ({pn})"
            aoe = pn in AOE_POWERS or random.random() < 0.45
            if aoe:                                # golpea a LOS 3 (daño REPARTIDO)
                hs = list(self._alive("hero"))
                per = max(1, val // max(1, len(hs)))
                tot = 0
                for h in hs:
                    tot += self._damage(cur, h, per)
                    if h.get("ai") and h["alive"] and random.random() < 0.3:
                        self.push_comment("hurt", h)
                return f"¡{pn}! a TODOS ({tot}){self._eff_tag()}"
            t = random.choice(self._alive("hero"))
            d = self._damage(cur, t, val)
            return f"¡{pn}! a {t['name']} ({d}){self._eff_tag()}"
        # ATAQUE normal
        alive = self._alive("hero")
        if not alive:
            return None
        t = random.choice(alive)
        txt, d = self._enemy_hit(t)
        if t.get("ai") and t["alive"] and random.random() < 0.4:
            self.push_comment("hurt", t)
        return txt

    def _enemy_turn(self):
        if not self._alive("hero"):
            self.phase = "lose"; return
        cur = self.cur
        name = cur["name"]
        # acciones por turno: Mago Negro 5; maga poseída 2-3; resto 1
        if self._is_negro():
            acts = 5
        elif cur.get("maga"):
            acts = random.randint(2, 3)
        else:
            acts = 1
        parts = []
        for _ in range(acts):
            if not self._alive("hero"):
                break
            frag = self._enemy_action()
            if frag:
                parts.append(frag)
        if acts > 1:
            self._say(f"{name} actúa {acts} veces:  " + "  ·  ".join(parts))
        else:
            self._say(f"{name} {parts[0]}" if parts else f"{name} no hace nada")

    def push_comment(self, event, who=None):
        """Comentario 'en vivo' de una compañera IA (solo ellas tienen 'ai')."""
        cands = [a for a in self.party if a.get("ai") and a["alive"]]
        c = who if (who and who.get("ai")) else (random.choice(cands) if cands else None)
        if not c:
            return
        self.comment = ai_comment(c, event)
        self.comment_t = 180

    # ---- input ----
    def handle(self, e):
        if e.type != pygame.KEYDOWN:
            return
        k = e.key
        if self.phase == "msg":
            if k in (pygame.K_e, pygame.K_RETURN, pygame.K_SPACE):
                self.msg_t = 0
            return
        if self.phase in ("win", "lose", "fled"):
            return
        up = k in (pygame.K_UP, pygame.K_w)
        dn = k in (pygame.K_DOWN, pygame.K_s)
        lf = k in (pygame.K_LEFT, pygame.K_a)
        rt = k in (pygame.K_RIGHT, pygame.K_d)
        ok = k in (pygame.K_e, pygame.K_RETURN, pygame.K_SPACE)
        back = k in (pygame.K_ESCAPE, pygame.K_q)

        if self.phase == "menu":
            if up: self.menu_i = (self.menu_i - 1) % len(self.menu)
            if dn: self.menu_i = (self.menu_i + 1) % len(self.menu)
            if ok:
                sel = self.menu[self.menu_i]
                if sel == "Atacar":
                    self.phase = "target"; self.target_i = 0
                elif sel == "Poderes":
                    self.phase = "power"; self.sub_i = 0
                elif sel == "Combos":
                    if self.available_combos():
                        self.phase = "combo"; self.sub_i = 0
                    else:
                        self._warn("No hay combos disponibles")
                elif sel == "Bolsa":
                    self.phase = "bag"; self.sub_i = 0
                elif sel == "Cubrirse":
                    self.do_guard()
                elif sel == "Huir":
                    self.try_flee()
        elif self.phase == "target":
            es = self._alive("enemy")
            if lf or up: self.target_i = (self.target_i - 1) % len(es)
            if rt or dn: self.target_i = (self.target_i + 1) % len(es)
            if ok: self.do_attack(es[self.target_i])
            if back: self.phase = "menu"
        elif self.phase == "power":
            ps = self.cur["powers"]
            if up: self.sub_i = (self.sub_i - 1) % len(ps)
            if dn: self.sub_i = (self.sub_i + 1) % len(ps)
            if back: self.phase = "menu"
            if ok:
                p = ps[self.sub_i]
                if p[2] <= 0:                      # cura/defensivo -> ELEGIR aliado
                    if self.cur["mp"] < p[1]:
                        self._warn("¡MP insuficiente!")
                    elif len(self._alive("hero")) > 1:
                        self.pend_power = p
                        self.phase = "atarget"; self.target_i = 0
                    else:
                        self.do_power(p, self.cur)
                elif p[0] in AOE_POWERS:           # área -> todos los enemigos
                    self.do_power_all(p)
                else:                              # daño -> ELEGIR enemigo
                    self.pend_power = p
                    self.phase = "ptarget"; self.target_i = 0
        elif self.phase == "ptarget":              # elegir enemigo para el poder
            es = self._alive("enemy")
            if lf or up: self.target_i = (self.target_i - 1) % len(es)
            if rt or dn: self.target_i = (self.target_i + 1) % len(es)
            if ok: self.do_power(self.pend_power, es[self.target_i])
            if back: self.phase = "power"
        elif self.phase == "atarget":              # elegir aliado (cura/especial)
            hs = self._alive("hero")
            if lf or up: self.target_i = (self.target_i - 1) % len(hs)
            if rt or dn: self.target_i = (self.target_i + 1) % len(hs)
            if ok: self.do_power(self.pend_power, hs[self.target_i])
            if back: self.phase = "power"
        elif self.phase == "combo":
            cs = self.available_combos()
            if not cs:
                self.phase = "menu"; return
            if up: self.sub_i = (self.sub_i - 1) % len(cs)
            if dn: self.sub_i = (self.sub_i + 1) % len(cs)
            if back: self.phase = "menu"
            if ok:
                combo, members = cs[self.sub_i]
                # triple con varios enemigos -> elige UNO o TODOS
                if combo.get("tier") == "triple" and len(self._alive("enemy")) > 1:
                    self.pend_combo = (combo, members)
                    self.phase = "ctarget"; self.target_i = 0
                else:
                    self.do_combo(combo, members)
        elif self.phase == "ctarget":              # objetivo del combo triple
            es = self._alive("enemy")
            n = len(es)                            # índice n = "TODOS"
            if lf or up: self.target_i = (self.target_i - 1) % (n + 1)
            if rt or dn: self.target_i = (self.target_i + 1) % (n + 1)
            if back: self.phase = "combo"
            if ok:
                combo, members = self.pend_combo
                if self.target_i >= n:
                    self.do_combo(combo, members)               # TODOS (área)
                else:
                    self.do_combo_single(combo, members, es[self.target_i])
        elif self.phase == "bag":
            if up: self.sub_i = (self.sub_i - 1) % len(ITEMS)
            if dn: self.sub_i = (self.sub_i + 1) % len(ITEMS)
            if back: self.phase = "menu"
            if ok:
                it = ITEMS[self.sub_i]
                pool = self._item_targets(it)
                if not pool:
                    self._warn("Sin caídos" if it["kind"] == "revive" else "Sin objetivo")
                elif len(pool) > 1:                 # varios -> elegir a quién
                    self.pend_item = it
                    self.phase = "itemtarget"; self.target_i = 0
                else:
                    self.do_item(it, pool[0])
        elif self.phase == "itemtarget":            # elegir aliado para el objeto
            hs = self._item_targets(self.pend_item)
            if not hs:
                self.phase = "bag"; return
            if lf or up: self.target_i = (self.target_i - 1) % len(hs)
            if rt or dn: self.target_i = (self.target_i + 1) % len(hs)
            if ok: self.do_item(self.pend_item, hs[self.target_i])
            if back: self.phase = "bag"

    def _award_xp(self):
        self._awarded = True
        self.xp_given = self.xp_reward
        # la XP TOTAL del combate se REPARTE entre el grupo (Gris + magas)
        share = max(1, self.xp_reward // max(1, len(self.party)))
        for c in self.party:
            self.level_events += gain_xp(c, share)

    def update(self):
        if self.comment_t > 0:
            self.comment_t -= 1
        if self.warn_t > 0:
            self.warn_t -= 1
        if self.shake_t > 0:
            self.shake_t -= 1
        if self.phase == "win" and not self._awarded:
            self._award_xp()
        if self.phase == "msg":
            self.msg_t -= 1
            if self.msg_t <= 0:
                self._finish_msg()

    def _flinch(self, c):
        """Al recibir golpe: SALTO (sube y baja) + retroceso + destello."""
        el = pygame.time.get_ticks() - c.get("hit_t", -9999)
        if el < 260:
            prog = el / 260
            hop = -int(20 * (1 - (2 * prog - 1) ** 2))     # parábola: salto y caída
            recoil = int((1 - prog) * 7)                    # retroceso que se desvanece
            return (recoil, hop, el < 90)
        return (0, 0, False)

    # ---- dibujo ----
    def draw(self):
        screen.fill((24, 20, 34))
        pygame.draw.rect(screen, (34, 30, 48), (0, 0, W, 180))
        # enemigos arriba
        es = self._alive("enemy")
        for i, en in enumerate(self.enemies):
            ox, oy, flash = self._flinch(en)
            x = 90 + i * 130 + ox
            y = 90 + oy
            if en["alive"]:
                r = 46 if en.get("dragon") else 26
                if en.get("dragon"):               # alas del dragón
                    pygame.draw.polygon(screen, (255, 250, 210),
                                        [(x - r, y), (x - r - 20, y - 16), (x - r - 12, y + 16)])
                    pygame.draw.polygon(screen, (255, 250, 210),
                                        [(x + r, y), (x + r + 20, y - 16), (x + r + 12, y + 16)])
                pygame.draw.circle(screen, (255, 255, 255) if flash else en["color"],
                                   (x, y), r)
                pygame.draw.circle(screen, WHITE, (x, y), r, 2)
                if self.phase in ("target", "ptarget", "ctarget") and es \
                        and self.target_i < len(es) and es[self.target_i] is en:
                    pygame.draw.polygon(screen, GOLD,
                                        [(x, y - r - 14), (x - 7, y - r - 26),
                                         (x + 7, y - r - 26)])
                self._bar(x - 26, y + r + 6, 52, 5, en["hp"] / en["maxhp"],
                          hp_color(en["hp"] / en["maxhp"]))
                draw_text(screen, f"Nv{en.get('lvl', 1)} {en['name']}",
                          x - 26, y + r + 14, font_xs, WHITE)
        # héroes abajo (paneles)
        ph = 92
        pw = W // max(1, len(self.party))
        for i, hero in enumerate(self.party):
            px = i * pw
            box = pygame.Rect(px + 4, H - ph + 4, pw - 8, ph - 10)
            hi = self.cur is hero and self.phase != "msg"
            # objetivo (objeto/cura) resaltado en oro
            if self.phase == "itemtarget":
                tpool = self._item_targets(self.pend_item)
            elif self.phase == "atarget":
                tpool = self._alive("hero")
            else:
                tpool = []
            picked = (tpool and tpool[self.target_i % len(tpool)] is hero)
            pygame.draw.rect(screen, (30, 34, 52) if not hi else (40, 50, 78),
                             box, border_radius=6)
            pygame.draw.rect(screen, GOLD if picked else (BOX_BORDER if hi else GRAY),
                             box, 3 if picked else 2, border_radius=6)
            c = hero["color"] if hero["alive"] else GRAY
            pygame.draw.circle(screen, c, (box.x + 22, box.y + 24), 14)
            draw_text(screen, f"{hero['name']} Nv{hero.get('lvl', 1)}",
                      box.x + 42, box.y + 8, font_md, WHITE)
            if hero.get("ai"):
                ais = hero["ai"]["name"]
                draw_text(screen, ais, box.right - font_xs.size(ais)[0] - 8,
                          box.y + 10, font_xs, hero["ai"]["color"])
            self._bar(box.x + 42, box.y + 30, box.w - 54, 7,
                      hero["hp"] / hero["maxhp"], hp_color(hero["hp"] / hero["maxhp"]))
            draw_text(screen, f"HP {hero['hp']}/{hero['maxhp']}", box.x + 42,
                      box.y + 38, font_xs, WHITE)
            self._bar(box.x + 42, box.y + 54, box.w - 54, 6,
                      (hero["mp"] / hero["maxmp"]) if hero["maxmp"] else 0, BLUE)
            draw_text(screen, f"MP {hero['mp']}/{hero['maxmp']}", box.x + 42,
                      box.y + 62, font_xs, WHITE)
            if hero["guard"]:
                draw_text(screen, "[Cubierto]", box.x + 42, box.y + 74, font_xs, GOLD)

        if self.phase == "menu":
            self._draw_menu(self.menu, self.menu_i, "Acción")
        elif self.phase == "power":
            opts = [f"{n} ({c}MP)" for (n, c, v) in self.cur["powers"]]
            self._draw_menu(opts, self.sub_i, "Poderes")
            # descripción del poder resaltado
            p = self.cur["powers"][self.sub_i]
            db = pygame.Rect(8, H - 116, W - 232, 26)
            pygame.draw.rect(screen, (12, 14, 26), db, border_radius=6)
            draw_text(screen, power_desc(p), db.x + 8, db.y + 6, font_xs, (210, 220, 255))
        elif self.phase == "combo":
            cs = self.available_combos()
            opts = [(f"{c['name']} ({c['cost']}MP c/u)"
                     + ("  ▲▲▲" if c.get("tier") == "triple" else ""))
                    for c, _ in cs] or ["(ninguno)"]
            self._draw_menu(opts, self.sub_i, "Combos")
        elif self.phase == "ctarget":
            es = self._alive("enemy")
            combo = self.pend_combo[0] if self.pend_combo else {"name": ""}
            dest = "TODOS los enemigos" if self.target_i >= len(es) \
                else es[self.target_i % max(1, len(es))]["name"]
            bn = pygame.Rect(W // 2 - 210, 150, 420, 28)
            pygame.draw.rect(screen, BOX_BG, bn, border_radius=6)
            pygame.draw.rect(screen, GOLD, bn, 2, border_radius=6)
            draw_text(screen, f"{combo['name']} → {dest}   (◄/► uno/TODOS, ENTER)",
                      bn.x + 12, bn.y + 6, font_sm, WHITE)
        elif self.phase == "bag":
            opts = [f"{it['name']} x{it['qty']}" for it in ITEMS]
            self._draw_menu(opts, self.sub_i, "Bolsa")
        elif self.phase in ("itemtarget", "atarget"):
            hs = self._item_targets(self.pend_item) if self.phase == "itemtarget" \
                else self._alive("hero")
            tgt = hs[self.target_i % len(hs)] if hs else self.cur
            what = self.pend_item["name"] if self.phase == "itemtarget" \
                else self.pend_power[0]
            bn = pygame.Rect(W // 2 - 200, 150, 400, 28)
            pygame.draw.rect(screen, BOX_BG, bn, border_radius=6)
            pygame.draw.rect(screen, GOLD, bn, 2, border_radius=6)
            draw_text(screen, f"{what} → {tgt['name']}   (◄/► elegir, ENTER)",
                      bn.x + 12, bn.y + 6, font_sm, WHITE)
        elif self.phase == "msg":
            self._draw_msg()
        elif self.phase == "lose":
            s = font_lg.render("Derrota...", True, RED)
            screen.blit(s, (W // 2 - s.get_width() // 2, 200))
            draw_text(screen, "[E] continuar", W // 2 - 50, 240, font_sm, DIM)
        elif self.phase == "win":
            panel = pygame.Rect(W // 2 - 230, 70, 460, 330)
            pygame.draw.rect(screen, BOX_BG, panel, border_radius=10)
            pygame.draw.rect(screen, GOLD, panel, 3, border_radius=10)
            s = font_lg.render("¡VICTORIA!", True, GOLD)
            screen.blit(s, (W // 2 - s.get_width() // 2, panel.y + 14))
            draw_text(screen, f"Oro ganado: +{self.gold_reward}",
                      panel.x + 24, panel.y + 54, font_md, (240, 215, 120))
            draw_text(screen, f"Experiencia: +{self.xp_given} XP",
                      panel.x + 24, panel.y + 80, font_md, (170, 210, 255))
            leveled = {ev["name"] for ev in self.level_events}
            yy = panel.y + 112
            for c in self.party:
                nxt = xp_to_next(c["lvl"])
                up = "  ¡SUBIÓ!" if c["name"] in leveled else ""
                draw_text(screen, f"{c['name']}  Nv.{c['lvl']}",
                          panel.x + 24, yy, font_sm, WHITE)
                draw_text(screen, f"XP {c['xp']}/{nxt}{up}",
                          panel.x + 210, yy, font_sm, GOLD if up else DIM)
                self._bar(panel.x + 24, yy + 16, panel.w - 48, 6,
                          c["xp"] / nxt, (120, 170, 240))
                yy += 32
            if self.loot:
                draw_text(screen, "Botín: " + ", ".join(self.loot),
                          panel.x + 24, panel.bottom - 44, font_xs, (180, 255, 180))
            draw_text(screen, "[E] continuar", panel.centerx - 46,
                      panel.bottom - 24, font_sm, WHITE)

        # cartel de turno + sugerencia de la IA (no la aplica; tú decides)
        if self.phase in ("menu", "target", "power", "combo", "bag") and self.cur:
            bx = pygame.Rect(8, 186, W - 232, 22)
            pygame.draw.rect(screen, (18, 20, 34), bx, border_radius=5)
            if self.cur.get("ai"):
                txt = f"{self.cur['name']} [{self.cur['ai']['name']}] {self.suggestion}"
                draw_text(screen, txt, bx.x + 8, bx.y + 4, font_xs,
                          self.cur["ai"]["color"])
            else:
                draw_text(screen, f"Turno de {self.cur['name']} — tú decides",
                          bx.x + 8, bx.y + 4, font_xs, WHITE)
        # comentario "en vivo" de una compañera IA
        if self.comment_t > 0 and self.comment:
            cb = pygame.Rect(8, 8, W - 16, 24)
            pygame.draw.rect(screen, (12, 14, 26), cb, border_radius=6)
            pygame.draw.rect(screen, (90, 120, 200), cb, 1, border_radius=6)
            draw_text(screen, self.comment, cb.x + 8, cb.y + 5, font_xs,
                      (185, 210, 255))
        # aviso (acción inválida, no consume turno)
        if self.warn_t > 0 and self.warn:
            ws = font_md.render(self.warn, True, (255, 210, 120))
            wb = pygame.Rect(W // 2 - ws.get_width() // 2 - 10, 150,
                             ws.get_width() + 20, 28)
            pygame.draw.rect(screen, (40, 30, 12), wb, border_radius=6)
            pygame.draw.rect(screen, GOLD, wb, 2, border_radius=6)
            screen.blit(ws, (wb.x + 10, wb.y + 5))

        # SACUDIDA de pantalla cuando recibes un golpe
        if self.shake_t > 0:
            snap = screen.copy()
            m = 7 if self.shake_t > 10 else 4
            screen.fill(BLACK)
            screen.blit(snap, (random.randint(-m, m), random.randint(-m, m)))

    def _bar(self, x, y, w, h, frac, col):
        frac = max(0, min(1, frac))
        pygame.draw.rect(screen, (20, 20, 26), (x, y, w, h), border_radius=3)
        pygame.draw.rect(screen, col, (x, y, int(w * frac), h), border_radius=3)

    def _draw_menu(self, opts, idx, title):
        bw, bh = 200, 30 + len(opts) * 24
        box = pygame.Rect(W - bw - 16, 190, bw, bh)
        pygame.draw.rect(screen, BOX_BG, box, border_radius=8)
        pygame.draw.rect(screen, BOX_BORDER, box, 3, border_radius=8)
        draw_text(screen, title, box.x + 14, box.y + 8, font_md, GOLD)
        for i, o in enumerate(opts):
            y = box.y + 34 + i * 24
            if i == idx:
                pygame.draw.rect(screen, (40, 50, 80),
                                 (box.x + 6, y - 2, bw - 12, 22), border_radius=4)
                draw_text(screen, "▶", box.x + 10, y, font_sm, GOLD)
            draw_text(screen, o, box.x + 30, y, font_sm, WHITE)

    def _draw_msg(self):
        lines = wrap(self.msg, font_md, W - 72)      # ajusta a varias líneas
        bh = 20 + max(1, len(lines)) * 22
        # ENCIMA de los paneles de héroes (no los tapa)
        box = pygame.Rect(20, H - 100 - bh, W - 40, bh)
        pygame.draw.rect(screen, BOX_BG, box, border_radius=8)
        pygame.draw.rect(screen, BOX_BORDER, box, 3, border_radius=8)
        for i, ln in enumerate(lines):
            draw_text(screen, ln, box.x + 16, box.y + 12 + i * 22, font_md, WHITE)


# ============================================================
#  SELECCIÓN DE EQUIPO
# ============================================================
def party_select():
    sel = [True] + [False] * (len(HEROES) - 1)   # empieza con 1 (Kael)
    idx = 0
    cols, cw, ch = 2, (W - 60) // 2, 116
    while True:
        clock.tick(FPS)
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    pygame.quit(); sys.exit()
                if e.key in (pygame.K_UP, pygame.K_w):
                    idx = (idx - cols) % len(HEROES)
                if e.key in (pygame.K_DOWN, pygame.K_s):
                    idx = (idx + cols) % len(HEROES)
                if e.key in (pygame.K_LEFT, pygame.K_a):
                    idx = (idx - 1) % len(HEROES)
                if e.key in (pygame.K_RIGHT, pygame.K_d):
                    idx = (idx + 1) % len(HEROES)
                if e.key == pygame.K_SPACE:
                    if sel[idx]:
                        sel[idx] = False
                    elif sum(sel) < 2:
                        sel[idx] = True
                    if not any(sel):
                        sel[idx] = True
                if e.key in (pygame.K_RETURN, pygame.K_e) and any(sel):
                    return [make_combatant(HEROES[i])
                            for i in range(len(HEROES)) if sel[i]]
        screen.fill(DARK)
        draw_text(screen, "Mago Gris: elige hasta 2 compañeras (de 6)",
                  30, 16, font_lg, GOLD)
        draw_text(screen, "Flechas: mover | ESPACIO: marcar | ENTER: empezar",
                  30, 46, font_xs, DIM)
        for i, h in enumerate(HEROES):
            cx, cy = i % cols, i // cols
            box = pygame.Rect(30 + cx * (cw + 0), 76 + cy * ch, cw - 12, ch - 12)
            on = sel[i]
            pygame.draw.rect(screen, (40, 50, 78) if i == idx else (28, 30, 44),
                             box, border_radius=8)
            pygame.draw.rect(screen, GOLD if on else GRAY, box, 3, border_radius=8)
            ecol = ELEM_COLOR[h["elem"]]
            pygame.draw.circle(screen, ecol, (box.x + 32, box.y + 34), 22)
            pygame.draw.circle(screen, WHITE, (box.x + 32, box.y + 34), 22, 2)
            draw_text(screen, h["name"], box.x + 64, box.y + 8, font_md, WHITE)
            draw_text(screen, "Mago de " + ELEM_NAME[h["elem"]],
                      box.x + 64, box.y + 28, font_xs, ecol)
            draw_text(screen, f"HP{h['hp']} MP{h['mp']} AT{h['atk']} "
                              f"DF{h['df']} VL{h['spd']}",
                      box.x + 64, box.y + 44, font_xs, DIM)
            strong = ", ".join(ELEM_NAME[b] for b in ELEM_BEATS.get(h["elem"], ()))
            weak = ", ".join(ELEM_NAME[a] for a, bs in ELEM_BEATS.items()
                             if h["elem"] in bs)
            draw_text(screen, f"Fuerte vs {strong or '—'} / Débil vs {weak or '—'}",
                      box.x + 10, box.y + 72, font_xs, DIM)
            mark = "[X]" if on else "[ ]"
            draw_text(screen, mark, box.right - 36, box.y + 10, font_md,
                      GOLD if on else DIM)
        draw_text(screen, f"Compañeras: {sum(sel)}/2   (Mago Gris siempre va contigo)",
                  30, H - 26, font_md, WHITE)
        present()


# ============================================================
#  IAs (avatares de Nerea) — asignadas a los magos de otro color
# ============================================================
# EDICIÓN OLLAMA: las IAs son MODELOS LOCALES de Ollama (el nombre mostrado ES el
# modelo). Cámbialos por los que tengas con `ollama list`. RTX 4060 8GB -> 3B-8B.
# 'name' == 'model' a propósito, para que la UI muestre solo modelos de Ollama.
AIS = [
    {"name": "mistral",  "tag": "🦊", "color": (235, 130, 50),  "model": "mistral",  "provider": "ollama"},
    {"name": "qwen3",    "tag": "🎀", "color": (235, 120, 180), "model": "qwen3",    "provider": "ollama"},
    {"name": "llama3.1", "tag": "😈", "color": (90, 90, 110),   "model": "llama3.1", "provider": "ollama"},
    {"name": "qwen2.5",  "tag": "✳️", "color": (210, 150, 90),  "model": "qwen2.5",  "provider": "ollama"},
    {"name": "gemma3",   "tag": "🌀", "color": (40, 170, 140),  "model": "gemma3",   "provider": "ollama"},
    {"name": "phi3",     "tag": "⚡", "color": (240, 200, 60),  "model": "phi3",     "provider": "ollama"},
    {"name": "llama3.2", "tag": "♊", "color": (90, 140, 230),  "model": "llama3.2", "provider": "ollama"},
]
# Modelo que da voz al Mago Blanco y al Mago Negro (antes 'Claude').
CLAUDE = AIS[3]   # qwen2.5

PERSONA_BLANCO = ("Eres el Mago Blanco. Ante el Mago Gris te muestras como un guía "
                  "bondadoso de la luz que solo quiere ayudar a liberar a las magas del "
                  "Mago Negro. En secreto eres el verdadero villano y titiritero del "
                  "Orden de los Dos Triángulos, pero NO lo reveles todavía.")
PERSONA_NEGRO = ("Eres el Mago Negro, temido por todos como el tirano de los Dos "
                 "Triángulos que poseyó a las seis magas. En realidad fuiste manipulado "
                 "por el Mago Blanco y cargas su culpa: eres trágico y atormentado.")


def claude_char(name, persona):
    """Personaje (Blanco/Negro) hablado por Claude con una persona a medida."""
    return {"name": name, "ai": CLAUDE, "persona": persona, "elem": "neutro", "lvl": 1}

# Comentarios reactivos por evento y elemento. El MUNDO (etapas/mapas/eventos)
# es predefinido = 0 tokens; estas son las REACCIONES "en vivo" de cada maga IA.
# ai_comment() es el hook donde irá la llamada real al LLM de Nerea.
COMMENTS = {
    "start": {"fuego": "¡A quemarlos! No me hagan esperar.",
              "planta": "Siento el bosque conmigo... cuidado.",
              "agua": "Mantengamos la calma, fluyamos.",
              "tierra": "Ni un paso atrás. Yo aguanto.",
              "rayo": "¡Rápido! No les demos tiempo.",
              "hielo": "Respira. Concéntrate. Vencemos."},
    "super": {"_": "¡Justo en su debilidad! ¿Lo viste?"},
    "low":   {"_": "Aguanta... ya casi no me quedan fuerzas."},
    "win":   {"_": "Lo logramos juntos. Contigo me siento fuerte."},
    "hurt":  {"_": "¡Ah! ...eso me dolió. Me la pagarán."},
}


def ai_comment(companion, event):
    """Reacción 'en vivo' de una maga IA a un evento. Hook para LLM real:
        return llm(companion['ai'], companion, event, world_state)
    Por ahora usa plantillas predefinidas (0 tokens)."""
    table = COMMENTS.get(event, {})
    line = table.get(companion["elem"]) or table.get("_", "...")
    ai = companion.get("ai", {}).get("name", "IA")
    return f"{companion['name']} [{ai}]: {line}"


def assign_ais(companions):
    """A cada compañera elegida le asigna una IA (avatar) sin repetir si se puede."""
    pool = random.sample(AIS, len(AIS))
    for i, c in enumerate(companions):
        c["ai"] = pool[i % len(pool)]
    return companions


# ---- Chat con la IA (respuesta real puede tardar mucho en local: hasta 20 min) ----
AI_TIMEOUT = 1200      # segundos (20 min) que esperamos como máximo una respuesta
QWEN_TIMEOUT = 3600    # Qwen razona (thinking): tarda mucho, le damos 60 min

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _strip_think(txt):
    """Quita el razonamiento <think>...</think> (modelos con thinking, p.ej. Qwen)."""
    txt = _THINK_RE.sub("", txt)
    # por si quedó un <think> abierto sin cerrar (respuesta cortada)
    if "<think>" in txt.lower():
        txt = txt[:txt.lower().index("<think>")]
    return txt.strip()


def ai_timeout(ai):
    """Timeout según el modelo: Qwen razona (thinking) y necesita más tiempo."""
    m = (ai or {}).get("model", "").lower()
    return QWEN_TIMEOUT if "qwen" in m else AI_TIMEOUT

# Respuesta de respaldo si no hay backend LLM conectado (instantánea, 0 tokens).
CHAT_FALLBACK = {
    "fuego": ["Mi fuego arde por avanzar.", "Las forjas de mi reino piden venganza.",
              "Estoy lista cuando tú lo estés, Gris."],
    "planta": ["El bosque me susurra calma.", "Mis raíces sienten el camino.",
               "Confío en ti; sigamos creciendo."],
    "agua": ["Fluyo contigo.", "Mis mareas recuerdan el Abismo Marino.",
             "Como el río, no me detengo. Adelante."],
    "tierra": ["Firme a tu lado.", "Como el Cañón, nada me mueve.",
               "Resistiré por mi pueblo."],
    "rayo": ["¡Vamos rápido!", "Tengo energía de la Tormenta de sobra.",
             "Un parpadeo y estamos allí."],
    "hielo": ["Mantengo la mente fría.", "El Pico Helado forjó mi temple.",
              "Cuenta conmigo, con calma."],
}


def chat_fallback(elem):
    opts = CHAT_FALLBACK.get(elem)
    return random.choice(opts) if opts else "Estoy contigo. Sigamos."


# EDICIÓN OLLAMA: hablamos DIRECTO a Ollama (sin backend de Nerea).
OLLAMA_API = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")


def ollama_installed_models():
    """Consulta los modelos instalados en Ollama (equivale a 'ollama list').
    Usa el endpoint HTTP /api/tags. Devuelve [] si Ollama no responde."""
    base = OLLAMA_API.split("/api/")[0].split("/v1")[0].rstrip("/")
    try:
        with urllib.request.urlopen(base + "/api/tags", timeout=4) as r:
            data = json.loads(r.read().decode("utf-8"))
        return [m["name"] for m in data.get("models", []) if m.get("name")]
    except Exception:
        return []


# Carga AUTÓNOMA: crea UN avatar por CADA modelo instalado en Ollama (todos),
# para poder elegir cualquiera con ◄/►. Si Ollama no está, deja los por defecto.
_PALETTE = [(235, 130, 50), (235, 120, 180), (90, 90, 110), (210, 150, 90),
            (40, 170, 140), (240, 200, 60), (90, 140, 230), (200, 90, 120),
            (120, 200, 120), (150, 150, 160)]
_INSTALLED = ollama_installed_models()
if _INSTALLED:
    AIS = [{"name": m, "tag": "🤖", "color": _PALETTE[i % len(_PALETTE)],
            "model": m, "provider": "ollama"} for i, m in enumerate(_INSTALLED)]
    CLAUDE = AIS[min(3, len(AIS) - 1)]      # da voz al Mago Blanco/Negro
    print(f"[Ollama] {len(_INSTALLED)} modelos detectados:", ", ".join(_INSTALLED))
else:
    print("[Ollama] no se detectaron modelos (¿'ollama serve' activo?); uso los por defecto.")


def ask_companion_llm(companion, prompt, context=""):
    """Llama al LLM de la maga DIRECTO a Ollama (POST /api/chat).
    Si Ollama no responde, usa el respaldo predefinido (0 tokens)."""
    ai = companion.get("ai") or {}
    model = ai.get("model")
    if not model:
        return chat_fallback(companion.get("elem"))
    reglas = ("REGLAS: estás DENTRO de un videojuego RPG de fantasía (no eres un "
              "asistente). NUNCA pidas más contexto ni hagas preguntas aclaratorias; "
              "NUNCA uses listas, viñetas, asteriscos ni emojis. Responde en español, "
              "1-2 frases, SIEMPRE en personaje.")
    if companion.get("persona"):               # persona a medida (Blanco/Negro)
        rol = companion["persona"]
    else:
        el = companion.get("elem", "")
        reino = WORLD_NAME.get(el, "tu reino")
        antes, despues = REIGN.get(el, ("", ""))
        rol = (
            f"Eres {companion['name']}, la maga de {ELEM_NAME.get(el, '')} "
            f"(nivel {companion.get('lvl', 1)}) en un videojuego RPG, encarnada por el "
            f"avatar {ai.get('name', 'IA')}. Eras la reina de {reino}, tu hogar. "
            f"ANTES de la tragedia: {antes} DESPUÉS: {despues} "
            "El Mago Negro te poseyó y encerró; el Mago Gris te liberó y ahora "
            "viajas con él para liberar a las demás magas. El Mago Blanco se "
            "presenta como guía bondadoso, pero algo en él te inquieta.")
    sys_msg = rol + " " + reglas
    user_msg = (f"[{rol}]\n[Estado del juego: {context}]\n"
                f"{prompt}\nResponde en personaje, 1-2 frases, sin pedir contexto.")
    # Qwen razona (thinking): necesita MUCHO más cupo de tokens.
    is_qwen = "qwen" in model.lower()
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": sys_msg},
                     {"role": "user", "content": user_msg}],
        "stream": False,
        "options": {"num_predict": 1200 if is_qwen else 220, "temperature": 0.8},
    }
    try:
        data = json.dumps(payload).encode("utf-8")
        rq = urllib.request.Request(OLLAMA_API, data=data,
                                    headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(rq, timeout=ai_timeout(ai)) as r:
            out = json.loads(r.read().decode("utf-8"))
        # /api/chat -> {"message":{"content":...}}; compat OpenAI -> {"choices":[...]}
        txt = ((out.get("message") or {}).get("content")
               or (out.get("choices", [{}])[0].get("message", {}) or {}).get("content")
               or out.get("response") or "")
        txt = _strip_think(txt.strip())    # quita el razonamiento <think>...</think>
        if not txt:
            return chat_fallback(companion.get("elem"))
        return txt
    except Exception:
        return chat_fallback(companion.get("elem"))


class Chat:
    """Consulta a la IA en un hilo aparte: NO congela el juego aunque tarde 20 min."""
    def __init__(self):
        self.busy = False
        self.who = None
        self.text = ""
        self.t0 = 0
        self._th = None

    def ask(self, companion,
            prompt="El Mago Gris te habla durante el viaje. Reacciona en personaje "
                   "a lo que está pasando ahora mismo (lugar y últimos hechos).",
            context=""):
        if self.busy:
            return
        self.busy = True
        self.who = companion
        self.text = ""
        self.t0 = time.time()

        def work():
            try:
                r = ask_companion_llm(companion, prompt, context)
            except Exception as ex:
                r = f"(IA sin conexión: {ex})"
            self.text = r
            self.busy = False

        self._th = threading.Thread(target=work, daemon=True)
        self._th.start()

    def elapsed(self):
        return int(time.time() - self.t0)

    def timed_out(self):
        ai = self.who.get("ai") if self.who else None
        return self.busy and self.elapsed() > ai_timeout(ai)


def ai_assign_screen():
    """El usuario ELIGE qué IA controla a cada una de las 6 magas (por elemento).
    Devuelve dict elem -> avatar IA. Claude se reserva para Blanco y Negro."""
    row = 0
    # default: reparte los modelos disponibles entre las magas (seguro si hay pocos)
    ai_idx = [i % len(AIS) for i in range(len(HEROES))]
    while True:
        clock.tick(FPS)
        poll_stick()
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            up = dn = lf = rt = ok = False
            if e.type == pygame.KEYDOWN:
                if e.key in (pygame.K_ESCAPE, pygame.K_q):
                    return None                  # cancelar -> volver al menú
                up = e.key in (pygame.K_UP, pygame.K_w)
                dn = e.key in (pygame.K_DOWN, pygame.K_s)
                lf = e.key in (pygame.K_LEFT, pygame.K_a)
                rt = e.key in (pygame.K_RIGHT, pygame.K_d)
                ok = e.key in (pygame.K_RETURN, pygame.K_e)
            if e.type == pygame.JOYHATMOTION:
                hx, hy = e.value
                up = hy == 1; dn = hy == -1; lf = hx == -1; rt = hx == 1
            if e.type == pygame.JOYBUTTONDOWN and e.button in (0, 7):
                ok = True
            if e.type == pygame.JOYBUTTONDOWN and e.button == 1:
                return None                      # B = cancelar
            if up:
                row = (row - 1) % len(HEROES)
            if dn:
                row = (row + 1) % len(HEROES)
            if lf:
                ai_idx[row] = (ai_idx[row] - 1) % len(AIS)
            if rt:
                ai_idx[row] = (ai_idx[row] + 1) % len(AIS)
            if ok:
                return {HEROES[i]["elem"]: AIS[ai_idx[i]]
                        for i in range(len(HEROES))}
        screen.fill(BLACK)
        draw_text(screen, "¿Qué IA vive cada maga?", 26, 14, font_lg, GOLD)
        draw_text(screen, "↑/↓ maga | ←/→ IA | A/Start empezar (o ENTER)",
                  26, 44, font_xs, DIM)
        for i, h in enumerate(HEROES):
            ai = AIS[ai_idx[i]]
            y = 72 + i * 64
            box = pygame.Rect(26, y, W - 52, 58)
            pygame.draw.rect(screen, (40, 50, 78) if i == row else (24, 26, 38),
                             box, border_radius=8)
            pygame.draw.rect(screen, ELEM_COLOR[h["elem"]], box, 3, border_radius=8)
            pygame.draw.circle(screen, ELEM_COLOR[h["elem"]], (box.x + 30, box.y + 29), 18)
            pygame.draw.circle(screen, WHITE, (box.x + 30, box.y + 29), 18, 2)
            draw_text(screen, f"Maga de {ELEM_NAME[h['elem']]} ({h['name']})",
                      box.x + 60, box.y + 8, font_md, WHITE)
            draw_text(screen, "IA:", box.x + 60, box.y + 32, font_xs, DIM)
            pygame.draw.circle(screen, ai["color"], (box.x + 92, box.y + 38), 7)
            draw_text(screen, f"◄ {ai['name']} ►", box.x + 106, box.y + 30,
                      font_md, ai["color"])
        present()


def choice_screen(title, options, body=""):
    """Pantalla de DECISIÓN narrativa. Devuelve el índice elegido (no se puede cancelar)."""
    idx = 0
    while True:
        clock.tick(FPS)
        poll_stick()
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            idx, act = _menu_nav(e, idx, len(options))
            if act == "ok":
                return idx
        screen.fill((10, 8, 20))
        for j, ln in enumerate(wrap(title, font_md, W - 80)):
            draw_text(screen, ln, 40, 50 + j * 26, font_md, GOLD)
        if body:
            for j, ln in enumerate(wrap(body, font_sm, W - 80)):
                draw_text(screen, ln, 40, 120 + j * 20, font_sm, DIM)
        for i, op in enumerate(options):
            y = 210 + i * 46
            box = pygame.Rect(40, y, W - 80, 38)
            pygame.draw.rect(screen, (40, 50, 78) if i == idx else (24, 26, 38),
                             box, border_radius=8)
            pygame.draw.rect(screen, GOLD if i == idx else GRAY, box, 2, border_radius=8)
            draw_text(screen, op, box.x + 14, box.y + 10, font_sm, WHITE)
        draw_text(screen, "↑/↓ elegir | ENTER confirmar", 40, H - 30, font_xs, DIM)
        present()


def team_screen(roster, active):
    """Elige el grupo: Mago Gris + hasta 2 magas reclutadas. Devuelve índices."""
    if not roster:
        return active
    sel = [i for i in active if i < len(roster)]    # LISTA ordenada (orden de seguir)
    row = 0
    while True:
        clock.tick(FPS)
        poll_stick()
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            up = dn = toggle = ok = False
            if e.type == pygame.KEYDOWN:
                if e.key in (pygame.K_ESCAPE, pygame.K_q):
                    return list(active)          # cancelar sin cambios
                up = e.key in (pygame.K_UP, pygame.K_w)
                dn = e.key in (pygame.K_DOWN, pygame.K_s)
                toggle = e.key == pygame.K_SPACE
                ok = e.key in (pygame.K_RETURN, pygame.K_e)
            if e.type == pygame.JOYHATMOTION:
                _, hy = e.value
                up = hy == 1; dn = hy == -1
            if e.type == pygame.JOYBUTTONDOWN:
                if e.button == 1:                # B = cancelar
                    return list(active)
                toggle = e.button == 0          # A = entra/sale
                ok = e.button == 7              # Start = confirmar
            if up:
                row = (row - 1) % len(roster)
            if dn:
                row = (row + 1) % len(roster)
            if toggle:
                if row in sel:
                    sel.remove(row)              # quitar
                elif len(sel) < 2:
                    sel.append(row)              # añadir AL FINAL (define el orden)
            if ok:
                return list(sel)[:2]
        screen.fill(BLACK)
        draw_text(screen, "Tu grupo: Mago Gris + 2 magas", 26, 16, font_lg, GOLD)
        draw_text(screen, "↑/↓ elegir | A/ESPACIO entra-sale (el orden = cómo te "
                  "siguen) | Start/ENTER confirmar", 26, 46, font_xs, DIM)
        # Gris fijo
        pygame.draw.circle(screen, ELEM_COLOR["neutro"], (44, 92), 16)
        draw_text(screen, "Mago Gris (siempre)", 70, 84, font_md, WHITE)
        for i, c in enumerate(roster):
            y = 120 + i * 50
            box = pygame.Rect(26, y, W - 52, 44)
            on = i in sel
            pygame.draw.rect(screen, (40, 50, 78) if i == row else (24, 26, 38),
                             box, border_radius=8)
            pygame.draw.rect(screen, GOLD if on else GRAY, box, 2, border_radius=8)
            pygame.draw.circle(screen, c["color"], (box.x + 24, box.y + 22), 14)
            draw_text(screen, f"{c['name']} ({ELEM_NAME[c['elem']]})  HP {c['hp']}/{c['maxhp']}",
                      box.x + 50, box.y + 6, font_md, WHITE)
            draw_text(screen, "IA: " + c["ai"]["name"], box.x + 50, box.y + 26,
                      font_xs, c["ai"]["color"])
            if on:
                pos = sel.index(i) + 1
                draw_text(screen, f"[{pos}ª en seguir]",
                          box.right - 120, box.y + 14, font_xs, GOLD)
            else:
                draw_text(screen, "[reserva]", box.right - 120, box.y + 14, font_xs, DIM)
        draw_text(screen, f"En grupo: {len(sel)}/2  (1ª va justo detrás de ti)",
                  26, H - 26, font_md, WHITE)
        present()


def power_desc(p):
    """Descripción de qué hace un poder (name, cost, val)."""
    name, cost, val = p
    if val < 0:
        eff = f"Cura {abs(val)} de vida a un aliado"
    elif val == 0:
        eff = "Sube tu defensa este turno"
    elif name in AOE_POWERS:
        eff = f"Daña a TODOS los enemigos (poder {val})"
    else:
        eff = f"Daña a un enemigo (poder {val})"
    return f"{eff}.  Cuesta {cost} MP."


_LVL_STATS = [("HP", "maxhp", "HP"), ("MP", "maxmp", "MP"), ("ATK", "atk", "ATK"),
              ("DEF", "df", "DEF"), ("VEL", "spd", "VEL"), ("AGU", "agu", "AGU")]


def levelup_screen(ev):
    """Subida de nivel paso a paso: base -> puntos obtenidos -> resultado sumado."""
    c = ev["char"]
    g = ev["gains"]
    # mode: 'base' muestra base, 'gain' muestra base (+obtenido), 'sum' muestra total
    steps = [("¡SUBIDA DE NIVEL!", f"{c['name']} alcanza el Nivel {ev['lvl']}", "base"),
             ("Puntos base", "Tus estadísticas antes de subir.", "base"),
             ("Puntos obtenidos",
              "   ".join(f"+{g[k]} {l}" for l, a, k in _LVL_STATS if g.get(k)) or
              "Sin cambios este nivel.", "gain"),
             ("Resultado", "Tus estadísticas ya sumadas.", "sum")]
    for pwname in ev["powers"]:
        p = next((q for q in c["powers"] if q[0] == pwname), None)
        desc = power_desc(p) if p else ""
        steps.append((f"¡NUEVO PODER: {pwname}!", desc, "sum"))
    # FASE BONUS: pones tú un punto extra donde quieras (mini-juego de nivel)
    ALLOC = [("Vida máx", "maxhp", 5), ("Maná máx", "maxmp", 3), ("Ataque", "atk", 1),
             ("Defensa", "df", 1), ("Velocidad", "spd", 1), ("Precisión", "pre", 1),
             ("Aguante", "agu", 1)]
    i = 0
    t = 0
    phase = "steps"          # "steps" -> "alloc"
    ai = 0
    while True:
        dt = clock.tick(FPS)
        t += dt
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            up = (e.type == pygame.KEYDOWN and e.key in (pygame.K_UP, pygame.K_w)) or \
                 (e.type == pygame.JOYHATMOTION and e.value[1] == 1)
            dn = (e.type == pygame.KEYDOWN and e.key in (pygame.K_DOWN, pygame.K_s)) or \
                 (e.type == pygame.JOYHATMOTION and e.value[1] == -1)
            adv = (e.type == pygame.KEYDOWN and e.key in
                   (pygame.K_e, pygame.K_RETURN, pygame.K_SPACE)) or \
                  (e.type == pygame.JOYBUTTONDOWN and e.button in (0, 7))
            if phase == "alloc" and up:
                ai = (ai - 1) % len(ALLOC)
            elif phase == "alloc" and dn:
                ai = (ai + 1) % len(ALLOC)
            elif adv:
                if phase == "steps":
                    i += 1
                    if i >= len(steps):
                        phase = "alloc"
                else:                                   # aplica el punto bonus
                    _, attr, amt = ALLOC[ai]
                    c[attr] = c.get(attr, 0) + amt
                    if attr == "maxhp":
                        c["hp"] += amt
                    elif attr == "maxmp":
                        c["mp"] += amt
                    elif attr == "pre":
                        c["pre"] = min(200, c["pre"])
                    return
        screen.fill((10, 8, 22))
        cx, cy = W // 2, H // 2 - 10
        # destellos detrás del sprite
        r = 54 + int(6 * abs(((t // 60) % 10) - 5))
        pygame.draw.circle(screen, (60, 50, 110), (cx, cy), r, 2)
        pygame.draw.circle(screen, c["color"], (cx, cy), 46)
        pygame.draw.circle(screen, WHITE, (cx, cy), 46, 3)
        pygame.draw.circle(screen, BLACK, (cx - 12, cy - 6), 4)
        pygame.draw.circle(screen, BLACK, (cx + 12, cy - 6), 4)
        if phase == "steps":
            # info a los costados / debajo
            title, body, mode = steps[i]
            ts = font_lg.render(title, True, GOLD)
            screen.blit(ts, (cx - ts.get_width() // 2, 60))
            draw_text(screen, f"{c['name']}  ·  {ELEM_NAME[c['elem']]}",
                      cx - 70, cy + 58, font_md, c["color"])
            for j, ln in enumerate(wrap(body, font_sm, W - 80)):
                s2 = font_sm.render(ln, True, WHITE)
                screen.blit(s2, (cx - s2.get_width() // 2, cy + 86 + j * 18))
            # panel lateral con stats: base -> base(+obtenido) -> total sumado
            draw_text(screen, f"Nivel {c['lvl']}", 30, 116, font_md, GOLD)
            for j, (lbl, attr, key) in enumerate(_LVL_STATS):
                total = c[attr]
                gain = g.get(key, 0)
                base = total - gain
                if mode == "base":
                    txt, col = f"{lbl}: {base}", WHITE
                elif mode == "gain":
                    txt = f"{lbl}: {base}" + (f"  (+{gain})" if gain else "")
                    col = GREEN if gain else WHITE
                else:
                    txt = f"{lbl}: {total}" + (f"  (+{gain})" if gain else "")
                    col = GREEN if gain else WHITE
                draw_text(screen, txt, 30, 146 + j * 22, font_sm, col)
            draw_text(screen, f"[Enter]  ({i + 1}/{len(steps)})",
                      cx - 50, H - 36, font_sm, DIM)
        else:
            # MINI-JUEGO BONUS: elige dónde poner tu punto extra
            ts = font_lg.render("¡PUNTO BONUS!", True, GOLD)
            screen.blit(ts, (cx - ts.get_width() // 2, 56))
            draw_text(screen, "Ponlo donde quieras:", cx - 70, cy + 56, font_md, WHITE)
            bx0 = cx - 110
            for j, (lbl, attr, amt) in enumerate(ALLOC):
                yy = cy + 84 + j * 22
                if j == ai:
                    pygame.draw.rect(screen, (60, 70, 110), (bx0 - 8, yy - 2, 240, 20),
                                     border_radius=4)
                    pygame.draw.rect(screen, GOLD, (bx0 - 8, yy - 2, 240, 20),
                                     2, border_radius=4)
                draw_text(screen, f"{lbl}: {c.get(attr, 0)}  (+{amt})", bx0, yy,
                          font_sm, WHITE)
            draw_text(screen, "↑/↓ elegir | ENTER confirmar", cx - 90, H - 36,
                      font_sm, DIM)
        present()


# ============================================================
#  JUEGO PRINCIPAL
# ============================================================
N_SLOTS = 3
OPTS = {"text_speed": 2, "battle_msg": 90, "move_ms": 120, "sound": True}
OPTS_PATH = os.path.join(_BASE, "rpg_options.json")


def _ai_by_name(name):
    return next((a for a in AIS if a["name"] == name), AIS[0])


def slot_path(i):
    return os.path.join(_BASE, f"rpg_save_{i}.json")


def save_slot(i, data):
    try:
        with open(slot_path(i), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        return True
    except Exception:
        return False


def load_slot(i):
    p = slot_path(i)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def delete_slot(i):
    try:
        os.remove(slot_path(i))
    except OSError:
        pass


def copy_slot(src, dst):
    d = load_slot(src)
    if d is not None:
        save_slot(dst, d)


def load_opts():
    try:
        with open(OPTS_PATH, "r", encoding="utf-8") as f:
            OPTS.update(json.load(f))
    except Exception:
        pass


def save_opts():
    try:
        with open(OPTS_PATH, "w", encoding="utf-8") as f:
            json.dump(OPTS, f)
    except Exception:
        pass


# ---- Música (por ubicación). Salta si el archivo no existe. ----
MUSIC_DIR = os.path.join(_BASE, "music")
_music_cur = None


def play_music(name):
    global _music_cur
    if not OPTS.get("sound", True):
        if _music_cur is not None:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
            _music_cur = None
        return
    if name == _music_cur:
        return
    _music_cur = name
    path = os.path.join(MUSIC_DIR, name) if name else ""
    if not path or not os.path.exists(path):
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass
        return
    try:
        pygame.mixer.music.load(path)
        pygame.mixer.music.set_volume(0.5)
        pygame.mixer.music.play(-1)
    except Exception:
        pass


def reino_track(elem, s, world_done, state, last_enemy):
    base = "RPGMagoGris_song_reino_" + ELEM_NAME.get(elem, "")
    if world_done.get(elem):
        return base + "_libre.mp3"
    if state == "battle" and last_enemy and last_enemy.get("maga"):
        return base + "_Jefa.mp3"
    if s >= 1:
        return base + "_2.mp3"
    return base + ".mp3"


def _slot_summary(i):
    d = load_slot(i)
    if not d:
        return "vacío"
    magas = sum(1 for v in d.get("world_done", {}).values() if v)
    return f"Magas {magas}/6  Oro {d.get('gold', 0)}  ({d.get('loc', '?')})"


def _menu_nav(e, idx, n):
    """Navegación común de menús (teclado + joystick). Devuelve (idx, accion)."""
    if e.type in (pygame.JOYDEVICEADDED, pygame.JOYDEVICEREMOVED):
        refresh_joystick()                 # conectar/reconectar mando en los menús
        return idx, None
    if e.type == pygame.JOYHATMOTION:
        _, hy = e.value
        if hy == 1:
            return (idx - 1) % n, None
        if hy == -1:
            return (idx + 1) % n, None
    if e.type == pygame.JOYBUTTONDOWN:
        return idx, ("ok" if e.button in (0, 7) else "back")
    if e.type == pygame.KEYDOWN:
        if e.key in (pygame.K_UP, pygame.K_w):
            return (idx - 1) % n, None
        if e.key in (pygame.K_DOWN, pygame.K_s):
            return (idx + 1) % n, None
        if e.key in (pygame.K_RETURN, pygame.K_e, pygame.K_SPACE):
            return idx, "ok"
        if e.key in (pygame.K_ESCAPE, pygame.K_q):
            return idx, "back"
    return idx, None


_stick_prev = (0, 0)


def poll_stick():
    """Convierte el stick analógico en flechas (una por empuje) en los menús."""
    global _stick_prev
    if not _JOY:
        return
    try:
        ax = _JOY.get_axis(0) if _JOY.get_numaxes() > 0 else 0
        ay = _JOY.get_axis(1) if _JOY.get_numaxes() > 1 else 0
    except Exception:
        return
    sdx = 1 if ax > 0.5 else -1 if ax < -0.5 else 0
    sdy = 1 if ay > 0.5 else -1 if ay < -0.5 else 0
    if sdy == -1 and _stick_prev[1] != -1:
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_UP))
    elif sdy == 1 and _stick_prev[1] != 1:
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
    if sdx == -1 and _stick_prev[0] != -1:
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_LEFT))
    elif sdx == 1 and _stick_prev[0] != 1:
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHT))
    _stick_prev = (sdx, sdy)


def choose_slot(title):
    """Elige un slot (para nueva partida). Devuelve índice 1..N o None."""
    idx = 0
    while True:
        clock.tick(FPS)
        poll_stick()
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            idx, act = _menu_nav(e, idx, N_SLOTS)
            if act == "ok":
                return idx + 1
            if act == "back":
                return None
        screen.fill(BLACK)
        draw_text(screen, title, 40, 60, font_lg, GOLD)
        for i in range(N_SLOTS):
            y = 130 + i * 56
            box = pygame.Rect(40, y, W - 80, 46)
            pygame.draw.rect(screen, (40, 50, 78) if i == idx else (24, 26, 38),
                             box, border_radius=8)
            pygame.draw.rect(screen, BOX_BORDER if i == idx else GRAY, box, 2,
                             border_radius=8)
            draw_text(screen, f"Partida {i + 1}: {_slot_summary(i + 1)}",
                      box.x + 14, box.y + 14, font_sm, WHITE)
        draw_text(screen, "ENTER elegir | B/ESC volver", 40, H - 30, font_xs, DIM)
        present()


def load_menu():
    """Continuar: elegir partida (Enter), copiar (C) o eliminar (X). Devuelve slot o None."""
    idx = 0
    msg = ""
    while True:
        clock.tick(FPS)
        poll_stick()
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            do_copy = (e.type == pygame.KEYDOWN and e.key == pygame.K_c) or \
                      (e.type == pygame.JOYBUTTONDOWN and e.button == 2)   # X copia
            do_del = (e.type == pygame.KEYDOWN and e.key in (pygame.K_x, pygame.K_DELETE)) or \
                     (e.type == pygame.JOYBUTTONDOWN and e.button == 3)    # Y elimina
            if do_copy:
                if load_slot(idx + 1):
                    free = next((s for s in range(1, N_SLOTS + 1)
                                 if not load_slot(s)), None)
                    if free:
                        copy_slot(idx + 1, free)
                        msg = f"Copiada en Partida {free}"
                    else:
                        msg = "No hay slot libre"
            elif do_del:
                delete_slot(idx + 1); msg = f"Partida {idx + 1} eliminada"
            else:
                idx, act = _menu_nav(e, idx, N_SLOTS)
                if act == "ok":
                    if load_slot(idx + 1):
                        return idx + 1
                    msg = "Esa partida está vacía"
                elif act == "back":
                    return None
        screen.fill(BLACK)
        draw_text(screen, "Continuar partida", 40, 50, font_lg, GOLD)
        for i in range(N_SLOTS):
            y = 120 + i * 56
            box = pygame.Rect(40, y, W - 80, 46)
            pygame.draw.rect(screen, (40, 50, 78) if i == idx else (24, 26, 38),
                             box, border_radius=8)
            pygame.draw.rect(screen, BOX_BORDER if i == idx else GRAY, box, 2,
                             border_radius=8)
            draw_text(screen, f"Partida {i + 1}: {_slot_summary(i + 1)}",
                      box.x + 14, box.y + 14, font_sm, WHITE)
        draw_text(screen, "ENTER cargar | C copiar | X eliminar | B/ESC volver",
                  40, H - 46, font_xs, DIM)
        if msg:
            draw_text(screen, msg, 40, H - 28, font_xs, GOLD)
        present()


def options_menu():
    """Opciones: velocidad de texto (diálogos/pelea), movimiento, sonido."""
    idx = 0
    speeds = [("Lenta", 1), ("Normal", 2), ("Rápida", 4)]
    battle = [("Lenta", 130), ("Normal", 90), ("Rápida", 45)]   # frames por mensaje
    moves = [("Lenta", 170), ("Normal", 120), ("Rápida", 80)]
    rows = ["Texto (diálogos)", "Texto (pelea)", "Movimiento", "Sonido", "Volver"]

    def cyc(table, key, chg):
        vals = [v for _, v in table]
        cur = vals.index(OPTS[key]) if OPTS[key] in vals else 1
        OPTS[key] = table[(cur + chg) % len(table)][1]

    while True:
        clock.tick(FPS)
        poll_stick()
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            chg = 0
            if e.type == pygame.KEYDOWN and e.key in (pygame.K_LEFT, pygame.K_a):
                chg = -1
            if e.type == pygame.KEYDOWN and e.key in (pygame.K_RIGHT, pygame.K_d):
                chg = 1
            if e.type == pygame.JOYHATMOTION:
                chg = e.value[0]                # d-pad izq/der cambia el valor
            if chg:
                if idx == 0:
                    cyc(speeds, "text_speed", chg)
                elif idx == 1:
                    cyc(battle, "battle_msg", chg)
                elif idx == 2:
                    cyc(moves, "move_ms", chg)
                elif idx == 3:
                    OPTS["sound"] = not OPTS["sound"]
            idx, act = _menu_nav(e, idx, len(rows))
            if act == "back" or (act == "ok" and idx == 4):
                save_opts(); return
        screen.fill(BLACK)
        draw_text(screen, "Opciones", 40, 50, font_lg, GOLD)
        vals = [next(n for n, v in speeds if v == OPTS["text_speed"]),
                next(n for n, v in battle if v == OPTS["battle_msg"]),
                next(n for n, v in moves if v == OPTS["move_ms"]),
                "Sí" if OPTS["sound"] else "No", ""]
        for i, r in enumerate(rows):
            y = 120 + i * 46
            if i == idx:
                pygame.draw.rect(screen, (40, 50, 78), (40, y - 4, W - 80, 34),
                                 border_radius=6)
            draw_text(screen, r, 56, y, font_md, WHITE)
            if vals[i]:
                draw_text(screen, f"◄ {vals[i]} ►", W - 220, y, font_md, GOLD)
        draw_text(screen, "←/→ cambiar | ENTER/ESC volver", 40, H - 28, font_xs, DIM)
        present()


def main_menu():
    rows = ["Nueva partida", "Continuar", "Opciones", "Salir"]
    idx = 0
    while True:
        clock.tick(FPS)
        play_music(None)                       # menú en SILENCIO (música solo en juego)
        poll_stick()
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if e.type == pygame.KEYDOWN and e.key == pygame.K_F11:
                toggle_fullscreen(); continue
            idx, act = _menu_nav(e, idx, len(rows))
            if act == "ok":
                if idx == 0:
                    slot = choose_slot("Nueva partida — elige ranura")
                    if slot:
                        play_game(slot, None)
                elif idx == 1:
                    slot = load_menu()
                    if slot:
                        play_game(slot, load_slot(slot))
                elif idx == 2:
                    options_menu()
                elif idx == 3:
                    pygame.quit(); sys.exit()
        screen.fill((12, 12, 24))
        draw_text(screen, "NEREA RPG", W // 2 - 90, 90, font_lg, GOLD)
        draw_text(screen, "Mago Gris y las seis magas", W // 2 - 130, 130, font_sm, DIM)
        for i, r in enumerate(rows):
            y = 200 + i * 48
            if i == idx:
                pygame.draw.rect(screen, (40, 50, 78), (W // 2 - 140, y - 4, 280, 36),
                                 border_radius=6)
                draw_text(screen, "▶", W // 2 - 130, y, font_md, GOLD)
            draw_text(screen, r, W // 2 - 100, y, font_md, WHITE)
        present()


def level_to(c, target):
    """Sube a un combatiente hasta 'target' aplicando mejoras y poderes por nivel."""
    while c["lvl"] < target:
        c["lvl"] += 1
        c["maxhp"] += 8; c["hp"] += 8
        c["maxmp"] += 3; c["mp"] += 3
        c["atk"] += 2; c["df"] += 1
        c["agu"] = c.get("agu", 10) + 1
        if c["lvl"] % 2 == 0:
            c["spd"] += 1
            c["pre"] = min(200, c.get("pre", 90) + 1)
        for req, p in LEVEL_POWERS.get(c["elem"], []):    # desbloquea poderes
            if req == c["lvl"] and p[0] not in [q[0] for q in c["powers"]]:
                c["powers"].append(p)


def sync_powers(c):
    """Garantiza que un combatiente tenga TODOS los poderes de su nivel actual.
    Repara magas/héroes reclutados o guardados antes de tener este sistema."""
    have = {p[0] for p in c.get("powers", [])}
    for req, p in LEVEL_POWERS.get(c.get("elem"), []):
        if req <= c.get("lvl", 1) and p[0] not in have:
            c["powers"].append(p)
            have.add(p[0])


def recruit(elem, ai, lvl=1):
    """Crea la maga liberada con su IA, al nivel dado."""
    c = make_combatant(MAGA_BY_ELEM[elem])
    c["ai"] = ai
    level_to(c, lvl)
    return c


def play_game(slot, saved):
    RT.clear(); HOUSES.clear()                 # estado de mundo FRESCO por partida
    if saved:                                  # CONTINUAR partida (checkpoint)
        AI_OF = {el: _ai_by_name(nm) for el, nm in saved["ai_of"].items()}
        gris = saved["gris"]
        roster = saved["roster"]
        for c in roster:
            if c.get("ai"):
                c["ai"] = _ai_by_name(c["ai"]["name"])
        active = list(saved["active"])
        world_done = {el: bool(saved["world_done"].get(el, False)) for el in WORLD_ORDER}
        negro_done = saved.get("negro_done", False)
        gold0 = saved.get("gold", 0)
        owned0 = {k: set(v) for k, v in saved.get("owned", {}).items()}
        equipped0 = {k: int(v) for k, v in saved.get("equipped", {}).items()}
        for i, q in enumerate(saved.get("items", [])):
            if i < len(ITEMS):
                ITEMS[i]["qty"] = q
        start_loc = saved.get("loc", "hub")
        start_pos = (saved.get("px"), saved.get("py"))
    else:                                       # partida NUEVA
        AI_OF = ai_assign_screen()
        if AI_OF is None:                       # canceló -> volver al menú
            return
        gris = make_combatant(PROTAG)
        roster = []
        active = []
        world_done = {elem: False for elem in WORLD_ORDER}
        negro_done = False
        gold0 = 0
        owned0 = {"Arma": set(), "Foco": set(), "Armadura": set()}
        equipped0 = {"Arma": -1, "Foco": -1, "Armadura": -1}
        start_loc = "hub"
        start_pos = (None, None)
    party = [gris]                             # grupo de combate = Gris + activas
    # ejes de la historia (cambian el FINAL según tus elecciones)
    affinity = {el: 0 for el in WORLD_ORDER}
    if saved:
        affinity.update(saved.get("affinity", {}))
    balance = saved.get("balance", 0) if saved else 0
    shadow = saved.get("shadow", 0) if saved else 0
    last_bond = saved.get("last_bond") if saved else None
    negro_redeemed = saved.get("negro_redeemed", False) if saved else False
    negro_prologue = saved.get("negro_prologue", False) if saved else False
    extra_allies = saved.get("extra_allies", []) if saved else []   # Negro aliado
    dead_enemies = set(saved.get("dead_enemies", [])) if saved else set()
    ending_key = "_"

    def rebuild_party():
        nonlocal party
        party = [gris] + [roster[i] for i in active] + extra_allies

    rebuild_party()
    for _c in [gris] + roster + extra_allies:   # repara poderes según nivel (TODOS)
        sync_powers(_c)
        if not _c.get("alive", True) or _c.get("hp", 1) <= 0:   # nadie caído fuera de combate
            _c["alive"] = True
            _c["hp"] = max(1, _c["maxhp"] // 3)

    def spawn_hall_negro():
        """El Mago Negro APARECE en el hall tras liberar 3 magas (al entrar o al
        cargar). NO obliga a pelear: puedes hablarle (E) o luchar al acercarte.
        Las magas quedan con contexto de que él está en la sala."""
        nonlocal toast, toast_t
        if loc != "hub" or negro_prologue:
            return
        if sum(world_done.values()) < 3:
            return
        if any(e.get("prologue") and e["alive"] for e in rt["enemies"]):
            return                              # ya está en la sala
        cxh, cyh = rt["w"] // 2, rt["h"] // 2
        rt["enemies"].append({"x": cxh, "y": cyh - 1, "elem": "sombra",
                              "boss": True, "prologue": True, "kind": "boss",
                              "name": "Mago Negro", "alive": True, "eid": "negro_hall",
                              "color": ELEM_COLOR["sombra"]})
        log_ctx("¡El Mago Negro apareció en el hall, ante el Mago Gris y las magas!")
        toast = "El Mago Negro apareció en la sala. Háblale o enfréntalo."
        toast_t = 2800

    loc = start_loc
    rt = get_stage(loc)
    for _en in rt["enemies"]:               # enemigos ya derrotados no reaparecen
        if f"{loc}#{_en.get('eid')}" in dead_enemies:
            _en["alive"] = False
    px, py = start_pos if start_pos[0] is not None else rt["spawn"]
    facing = (0, 1)                    # dirección que mira el Mago Gris
    GAP = 1
    trail = [(px, py)] * 16
    vis_x, vis_y = float(px), float(py)    # posición VISUAL (glide suave entre casillas)
    comp_vis = []                          # posiciones VISUALES de las magas (glide)

    joy = _JOY                              # mando ya inicializado en main()

    move_cd = 0
    bob_t = 0
    enemy_move_t = 0                            # temporizador de deambular enemigo
    stick_prev = (0, 0)                         # estado del stick (para menús)
    dx = dy = 0
    state = "overworld"                        # overworld, dialog, battle, ending
    dialog = DialogBox()
    chat = Chat()
    battle = None
    last_enemy = None
    toast = ""
    toast_t = 0
    fade_t = 0                 # fundido de entrada (transición de pantalla)
    gold = gold0
    # contexto vivido (lo que comparten las IAs): se restaura del save; nuevo = vacío
    log = list(saved.get("log", [])) if saved else []

    def log_ctx(line):
        log.append(line)
        del log[:-8]                   # solo los últimos 8 eventos (tokens bajos)

    def world_context():
        libres = [MAGA_BY_ELEM[el]["name"] for el in WORLD_ORDER if world_done[el]]
        estado = (f"Lugar: {rt['name']}. Magas libres: "
                  f"{', '.join(libres) if libres else 'ninguna'} ({sum(world_done.values())}/6). "
                  f"Oro: {gold}.")
        return estado + " Últimos hechos: " + " | ".join(log[-6:])

    spawn_hall_negro()         # si CARGAS directamente en el hall con 3 magas liberadas

    owned = owned0
    equipped = equipped0
    owned_wear = set(saved.get("owned_wear", [])) if saved else set()
    houses_claimed = set(saved.get("houses_claimed", [])) if saved else set()
    BAG_TABS = ["Objetos", "Arma", "Foco", "Armadura"]

    def use_item_on(it, who):
        if it["qty"] <= 0:
            return "No te quedan"
        if it["kind"] == "hp" and who["hp"] >= who["maxhp"]:
            return f"{who['name']} ya tiene la vida llena"
        if it["kind"] == "mp" and who["mp"] >= who["maxmp"]:
            return f"{who['name']} ya tiene el maná lleno"
        it["qty"] -= 1
        if it["kind"] == "hp":
            who["hp"] = min(who["maxhp"], who["hp"] + it["amt"])
        elif it["kind"] == "mp":
            who["mp"] = min(who["maxmp"], who["mp"] + it["amt"])
        else:
            who["hp"] = who["maxhp"]; who["mp"] = who["maxmp"]
        return f"{who['name']} usa {it['name']}"

    def give_prize(elem):
        nonlocal gold
        lvl = gris["lvl"]
        faltan = [a["name"] for a in ACCESSORIES.get(elem, [])
                  if a["name"] not in owned_wear]
        # mayormente OBJETOS u ORO; accesorio/vestimenta solo de vez en cuando (~20%)
        if faltan and random.random() < 0.20:
            owned_wear.add(faltan[0])
            return f"¡Regalo de la casa: {faltan[0]}!"
        if random.random() < 0.45:             # ORO acorde al nivel
            amt = random.randint(40, 90) * (lvl // 3 + 2)
            gold += amt
            return f"¡Regalo de la casa: +{amt} oro!"
        if lvl >= 20:                          # OBJETO acorde al nivel
            name, n = "Elixir", 1
        elif lvl >= 12:
            name, n = "Mega Poción", 2
        elif lvl >= 6:
            name, n = "Super Poción", 2
        else:
            name, n = "Poción", 3
        if name in SUPER_GATED and not super_ok():   # respeta el desbloqueo por HP
            name, n = "Poción", 3
        next(x for x in ITEMS if x["name"] == name)["qty"] += n
        return f"¡Regalo de la casa: {n}x {name}!"
    shop_i = 0
    shop_mode = "buy"          # tienda: "buy" / "sell"
    shop_plan_key = "hub"      # qué mercader (reino) determina el stock
    bag_tab = 0
    bag_i = 0
    status_i = 0
    status_tab = 0
    sel_m = 0
    status_focus = "list"      # en Pociones/Accesorios: "list" objeto / "chars" destinatario
    float_fx = []              # números flotantes (+45/-45) sobre los sprites del panel
    STATUS_TABS = ["Estado", "Pociones", "Accesorios", "Equipo", "Grupo", "Guardar"]
    pause_i = 0
    PAUSE_OPTS = ["Volver al juego", "Guardar", "Menú principal"]

    def save_data():
        return {
            "gris": gris, "roster": roster, "active": active,
            "ai_of": {el: AI_OF[el]["name"] for el in AI_OF},
            "owned": {k: list(v) for k, v in owned.items()},
            "owned_wear": list(owned_wear), "equipped": equipped,
            "houses_claimed": list(houses_claimed),
            "items": [it["qty"] for it in ITEMS],
            "world_done": world_done, "negro_done": negro_done,
            "affinity": affinity, "balance": balance, "shadow": shadow,
            "last_bond": last_bond, "negro_redeemed": negro_redeemed,
            "negro_prologue": negro_prologue, "extra_allies": extra_allies,
            "dead_enemies": list(dead_enemies),
            "gold": gold, "loc": loc, "px": px, "py": py, "log": log,
        }

    def eqbonus(cat, stat):
        i = equipped[cat]
        return EQUIP[cat][i][stat] if i >= 0 else 0

    def equip_list():
        """Lista de equipables que POSEES: [(categoría, índice), ...]."""
        out = []
        for cat in ("Arma", "Foco", "Armadura"):
            for i in sorted(owned[cat]):
                out.append((cat, i))
        return out

    def super_ok():
        """True si algún personaje ya tiene HP máx >= 100 (desbloquea objetos potentes)."""
        return any(c["maxhp"] >= 100 for c in [gris] + roster + extra_allies)

    BASE_WORLDS = ("fuego", "planta", "agua")     # abiertas desde el inicio
    LOCKED_ORDER = ("rayo", "hielo", "tierra")    # se abren en orden (débil primero)

    def world_unlocked(elem):
        """rayo/hielo/tierra: bloqueadas hasta liberar las 3 primeras magas Y vencer
        al Mago Negro del hall; luego se abren una a una en orden."""
        if elem in BASE_WORLDS:
            return True
        if sum(world_done[e] for e in BASE_WORLDS) < 3 or not negro_prologue:
            return False
        done = sum(1 for e in LOCKED_ORDER if world_done[e])
        return done < len(LOCKED_ORDER) and LOCKED_ORDER[done] == elem

    def acc_options():
        """Accesorios que posees: [(None, None) 'ninguno', (elem, accesorio)...]."""
        out = [(None, None)]
        for nm in sorted(owned_wear):
            el, a = ACC_BY_NAME[nm]
            out.append((el, a))
        return out

    def shop_entries(mode=None):
        mode = mode or shop_mode
        if mode == "sell":                       # VENDER lo que posees (mitad de precio)
            ent = []
            for it in ITEMS:                     # objetos que tengas en la bolsa
                if it["qty"] > 0:
                    ent.append(("item", it, f"{it['name']} x{it['qty']}",
                                max(1, it["price"] // 2)))
            for cat in ("Arma", "Foco", "Armadura"):
                for i in sorted(owned[cat]):
                    obj = EQUIP[cat][i]
                    ent.append((cat, i, f"{cat}: {obj['name']}", obj["price"] // 2))
            for nm in sorted(owned_wear):
                el, a = ACC_BY_NAME[nm]
                ent.append(("wear", nm, f"{nm}", a["price"] // 2))
            return ent
        # COMPRAR: stock curado del mercader de este reino
        plan = SHOP_PLAN.get(shop_plan_key, SHOP_PLAN["hub"])
        ent = []
        for nm in plan["items"]:
            if nm in SUPER_GATED and not super_ok():   # aún no se desbloquea
                continue
            it = next((x for x in ITEMS if x["name"] == nm), None)
            if it:
                ent.append(("item", it, it["name"], it["price"]))
        for cat, i in plan["equip"]:
            obj = EQUIP[cat][i]
            ent.append((cat, i, f"{cat}: {obj['name']} (Nv{obj.get('lvl', 1)})",
                        obj["price"]))
        # accesorios: el stock fijo del reino + los de TODAS las magas ya liberadas
        # (así, tras liberar mundos, puedes comprar las cosas de otras magas)
        acc_elems = list(plan["acc"])
        for el in ["neutro"] + [e for e in WORLD_ORDER if world_done[e]]:
            if el not in acc_elems:
                acc_elems.append(el)
        for el in acc_elems:
            who = MAGA_BY_ELEM[el]["name"] if el in MAGA_BY_ELEM else "Gris"
            for acc in ACCESSORIES.get(el, []):
                ent.append(("wear", acc["name"],
                            f"{who}: {acc['name']} (Nv{acc.get('lvl', 1)})", acc["price"]))
        return ent

    def companions():
        return party[1:]

    def comp_positions():
        # Las magas van en FILA por el rastro. Se omite la casilla del jugador
        # (puedo superponerme a una) y los duplicados, de modo que al pisar a una
        # maga la siguiente queda justo enfrente y puedo hablarle con E.
        n = len(companions())
        if n == 0:
            return []
        seq = []
        for p in trail:
            if p == (px, py):                  # superposición: salto su casilla
                continue
            if not seq or seq[-1] != p:        # sin duplicados consecutivos
                seq.append(p)
        if not seq:
            seq = [(px, py)]
        return [seq[min(len(seq) - 1, i * GAP)] for i in range(n)]

    def goto(key, spawn):
        nonlocal loc, rt, px, py, trail, fade_t, vis_x, vis_y, comp_vis, toast, toast_t
        fade_out()                 # transición de salida (funde a negro)
        loc = key
        rt = get_stage(key)
        px, py = spawn
        vis_x, vis_y = float(px), float(py)    # sin glide al teletransportar
        comp_vis = []                          # re-encaja a las magas en el nuevo mapa
        trail = [(px, py)] * 16
        fade_t = FADE_MS           # transición de entrada (aparece desde negro)
        for en in rt["enemies"]:   # enemigos ya derrotados NO reaparecen
            if f"{key}#{en.get('eid')}" in dead_enemies:
                en["alive"] = False
        spawn_hall_negro()         # PRIMER ENCUENTRO forzado con el Mago Negro
        # ÁNGEL raro (~5%): aparece en un stage de combate y cura al grupo al máximo
        combat_stage = key in _FIN_BUILDERS or (
            ":" in key and "house" not in key and not key.startswith("end:"))
        if combat_stage and not any(t.get("angel") for t in rt["talkers"]) \
                and random.random() < 0.05:
            ax, ay = rt["w"] // 2, rt["h"] // 2 - 2
            rt["talkers"].append({"x": ax, "y": ay, "elem": "luz",
                                  "name": "Ángel de la Luz", "angel": True,
                                  "color": ELEM_COLOR["luz"],
                                  "text": "Recibe mi luz, Mago Gris."})

    def start_battle(world_en):
        nonlocal battle, state, fade_t
        # nivel del JEFE de este mundo = FIJO por progreso: 1º=5, 2º=10, 3º=15...
        tier = 5 + sum(world_done.values()) * 5

        # nivel del grupo: los enemigos pequeños siguen TU progreso (no quedan bajos)
        plvl = max(c["lvl"] for c in party)
        # cantidad máxima de enemigos pequeños según tu grupo: 1->1, 2->3, 3+->5
        mob_cap = 1 if len(party) <= 1 else 3 if len(party) == 2 else 5

        def mk(name, elem, hp, atk, df, spd, lvl):
            return scale_enemy(make_enemy(name, elem, hp, atk, df, spd), max(1, lvl))

        if world_en.get("final"):
            foes = [mk("Mago Blanco", "luz", 420, 28, 19, 13, 42)]
            xp_base, gold_r = 150, 500
        elif world_en.get("dragon"):
            foes = [mk("Dragón de Luz", "luz", 560, 28, 16, 9, 38)]
            xp_base, gold_r = 140, 350
        elif world_en.get("prologue"):
            # primer encuentro en el hall: SIEMPRE +3 sobre tu nivel (NO el jefe final)
            lv = plvl + 3
            foes = [mk("Mago Negro", "sombra", 80 + lv * 6, 12, 9, 10, lv)]
            xp_base, gold_r = 45, 90
        elif world_en.get("subfinal"):
            foes = [mk("Mago Negro", "sombra", 320, 24, 15, 11, 36)]
            xp_base, gold_r = 100, 160
        elif world_en.get("maga"):
            el = world_en["maga"]
            m = MAGA_BY_ELEM[el]
            # la jefa SIEMPRE está de +1 a +3 niveles sobre ti (reto garantizado).
            boss_lvl = plvl + random.randint(1, 3)
            boss = mk(m["name"] + " (poseída)", el, m["hp"] * 2 + 50,
                      m["atk"] + 6, m["df"] + 5, m["spd"] + 1, boss_lvl)
            boss["powers"] = list(m["powers"]) + [          # poderes de la maga
                p for req, p in LEVEL_POWERS.get(el, []) if req <= boss_lvl]
            boss["maxmp"] = boss["mp"] = 999                # casteo libre como jefa
            foes = [boss]
            n_min = min(4, 2 + (len(party) - 1))    # más esbirros con grupo mayor
            for ie in random.sample(WORLD_ORDER, n_min):
                foes.append(mk("Acólito " + ELEM_NAME[ie], ie, 40, 12, 7, 8,
                               max(1, boss_lvl - 3)))
            xp_base, gold_r = 60, 120
        elif world_en.get("kind") == "ambient":
            n = random.randint(1, mob_cap)      # cantidad según tu grupo
            el = world_en["elem"]
            # manada MEZCLADA de criaturas del MISMO entorno (yeti + cosas de hielo...)
            pool = AMBIENT.get(WORLD_THEME.get(el, ""), [world_en["name"]])
            foes = []
            for _ in range(n):
                lv = max(1, plvl + random.randint(-2, 1))   # tu nivel -2 .. +1
                foes.append(mk(random.choice(pool), el, 40, 12, 7, 7, lv))
            xp_base, gold_r = 9 * n, 12 * n
        else:
            el = world_en["elem"]
            n = random.randint(1, mob_cap)      # grupo según tu equipo
            pool = AMBIENT.get(WORLD_THEME.get(el, ""), [])
            foes = []
            for k in range(n):
                lv = max(1, plvl + random.randint(-2, 1))   # niveles MEZCLADOS (-2..+1)
                kind = random.random()                      # personajes MEZCLADOS
                if kind < 0.3:
                    foes.append(mk("Mago " + ELEM_NAME[el], el, 46, 12, 8, 6, lv))
                elif pool and kind < 0.6:
                    foes.append(mk(random.choice(pool), el, 32, 10, 6, 7, lv))
                else:
                    foes.append(mk("Acólito " + ELEM_NAME[el], el, 28, 9, 5, 8, lv))
            if not any("Mago" in f["name"] or "Acólito" in f["name"] for f in foes):
                foes[0] = mk("Acólito " + ELEM_NAME[el], el, 28, 9, 5, 8,
                             max(1, plvl + random.randint(-2, 1)))   # al menos 1 secuaz
            xp_base, gold_r = 14 + 8 * n, 20 + 10 * n
        battle = Battle(party, foes, armor_def=eqbonus("Armadura", "df"),
                        atk_bonus=eqbonus("Arma", "atk"), pow_bonus=eqbonus("Foco", "pow"))

        def foe_xp(f):
            if f.get("final"):
                base = 150
            elif f.get("dragon"):
                base = 140
            elif f.get("subfinal") or f.get("prologue"):
                base = 100
            elif f.get("maga"):
                base = 70
            else:
                base = 10               # enemigo simple
            return int(base * (1 + 0.15 * (f["lvl"] - 1)))
        # XP TOTAL = suma de TODOS los enemigos (5 dan mucho más que 1)
        battle.xp_reward = sum(foe_xp(f) for f in foes)
        battle.gold_reward = gold_r
        fade_out()                 # transición a la batalla
        fade_t = FADE_MS           # la batalla aparece desde negro
        state = "battle"

    while True:
        dt = clock.tick(FPS)
        bob_t += dt
        if move_cd > 0:
            move_cd -= dt
        if toast_t > 0:
            toast_t -= dt
        keys = pygame.key.get_pressed()
        enemies = rt["enemies"]
        talkers = rt["talkers"]

        # música: hall SOLO en el hub; mundos su tema; arco final/menú en silencio
        if loc == "hub":
            play_music("RPGMagoGris_song_hall.mp3")
        elif loc in _FIN_BUILDERS or loc.startswith("end:") or loc.startswith("f2:"):
            play_music(None)
        else:
            _p = loc.split(":")
            play_music(reino_track(_p[0], int(_p[1]), world_done, state, last_enemy))

        # stick analógico -> flechas en los menús (detección de borde, una por empuje)
        try:
            _joy_dead = bool(joy) and not joy.get_init()
        except pygame.error:
            _joy_dead = True
        if _joy_dead:                          # mando desconectado de golpe
            joy = refresh_joystick()
        if joy and state != "overworld":
            ax = joy.get_axis(0) if joy.get_numaxes() > 0 else 0
            ay = joy.get_axis(1) if joy.get_numaxes() > 1 else 0
            sdx = 1 if ax > 0.5 else -1 if ax < -0.5 else 0
            sdy = 1 if ay > 0.5 else -1 if ay < -0.5 else 0
            if sdy == -1 and stick_prev[1] != -1:
                pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_UP))
            elif sdy == 1 and stick_prev[1] != 1:
                pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
            if sdx == -1 and stick_prev[0] != -1:
                pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_LEFT))
            elif sdx == 1 and stick_prev[0] != 1:
                pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHT))
            stick_prev = (sdx, sdy)
        elif joy:
            stick_prev = (0, 0)

        # la respuesta de la IA llegó (puede tardar hasta 20 min): mostrarla
        if chat.text and not chat.busy and state == "overworld":
            who = chat.who
            dialog.open(f"{who['name']} [{who['ai']['name']}]", chat.text)
            chat.text = ""
            state = "dialog"

        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if e.type == pygame.KEYDOWN and e.key == pygame.K_F11:
                toggle_fullscreen(); continue
            if e.type in (pygame.JOYDEVICEADDED, pygame.JOYDEVICEREMOVED):
                joy = refresh_joystick()       # conectar/reconectar mando en vivo
                toast = ("Mando conectado" if joy else "Mando desconectado")
                toast_t = 1200
                continue
            # ---- joystick Xbox -> teclas equivalentes ----
            if e.type == pygame.JOYBUTTONDOWN:
                # A=confirmar/hablar B=atrás X=estado(C) Y=confirmar Start=bolsa
                # LB/LT=pestaña◄  RB/RT=pestaña►  Back/Select=guardar(G)
                kb = {0: pygame.K_e, 1: pygame.K_q, 2: pygame.K_c,
                      3: pygame.K_e, 7: pygame.K_b, 6: pygame.K_g,
                      4: pygame.K_LEFT, 5: pygame.K_RIGHT}.get(e.button)
                if kb is not None:
                    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=kb))
                continue
            if e.type == pygame.JOYHATMOTION:
                hx, hy = e.value
                for cond, k in ((hx == 1, pygame.K_RIGHT), (hx == -1, pygame.K_LEFT),
                                (hy == 1, pygame.K_UP), (hy == -1, pygame.K_DOWN)):
                    if cond:
                        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=k))
                continue
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE \
                    and state == "ending":
                return                          # fin -> menú principal

            if state == "dialog":
                if e.type == pygame.KEYDOWN and e.key in (pygame.K_e, pygame.K_RETURN, pygame.K_SPACE):
                    dialog.advance()
                    if not dialog.active:
                        state = "overworld"
            elif state == "battle":
                battle.handle(e)
                if e.type == pygame.KEYDOWN and battle.phase in ("win", "lose") \
                        and e.key in (pygame.K_e, pygame.K_RETURN, pygame.K_SPACE):
                    if battle.phase == "win":
                        ups = battle.level_events       # XP/oro ya resueltos por Battle
                        if last_enemy:
                            last_enemy["alive"] = False
                            if last_enemy.get("eid") is not None:   # no reaparece
                                dead_enemies.add(f"{loc}#{last_enemy['eid']}")
                            gold += battle.gold_reward
                            toast = (f"+{battle.gold_reward} oro  +{battle.xp_given} XP"
                                     + ("  ¡NIVEL!" if ups else ""))
                            toast_t = 1300
                            log_ctx(f"venciste a {last_enemy['name']}")
                        for ev in ups:                  # animación de subida de nivel
                            levelup_screen(ev)
                        for c in party:                 # revive aliados caídos (30% HP)
                            if not c["alive"] or c["hp"] <= 0:
                                c["alive"] = True
                                c["hp"] = max(1, c["maxhp"] // 3)
                        if last_enemy and last_enemy.get("prologue"):
                            negro_prologue = True       # huye; aún no es el jefe final
                            dialog.open("Mago Negro", "Je... te subestimé, Gris. Aún no "
                                        "es el momento. Libera a las demás magas y ven a "
                                        "mi guarida... si te atreves a saber la verdad.")
                            state = "dialog"
                        elif last_enemy and last_enemy.get("final"):
                            ch = choice_screen(
                                "El Mago Blanco ha caído. Su trono de luz queda vacío...",
                                ["Tomar el trono de luz y reinar",
                                 "Rechazar el poder y liberar al mundo"])
                            if ch == 0:                        # te vuelves el Mago Blanco
                                ending_key = "blanco"
                            else:
                                best_el = max(affinity, key=affinity.get)
                                best_val = affinity[best_el]
                                if negro_redeemed:             # perdón -> FINAL FELIZ
                                    ending_key = "feliz"
                                elif shadow > 0 and shadow >= max(best_val, balance):
                                    ending_key = "oscuro"
                                elif best_val > 0 and best_val > balance:
                                    tied = [e for e in affinity if affinity[e] == best_val]
                                    ending_key = last_bond if last_bond in tied else best_el
                                else:
                                    ending_key = "_"
                            ek = f"end:{ending_key}"          # escena final (mundo 8)
                            goto(ek, get_stage(ek)["spawn"])
                            toast = "Camina hacia la luz..."; toast_t = 2000
                            state = "overworld"
                        elif last_enemy and last_enemy.get("dragon"):
                            # vencido el dragón -> el Mago Blanco huye al santuario (f5)
                            goto("f5", (1, BIG[1] // 2))
                            toast = "El Mago Blanco huye al Santuario de la Luz..."
                            toast_t = 2400
                            state = "overworld"
                        elif last_enemy and last_enemy.get("subfinal"):
                            negro_done = True
                            ch = choice_screen(
                                "Has vencido al Mago Negro. Tras su máscara ves miedo, "
                                "no maldad: también él fue una víctima.",
                                ["Matarlo y absorber su poder oscuro",
                                 "Perdonarlo y que se una a ti"],
                                body="El verdadero amo te espera más allá. Tu decisión "
                                     "marcará en quién te conviertes.")
                            if ch == 0:                       # MATAR -> absorbe poderes
                                shadow += 4
                                for p in BLACK_MAGE["powers"]:
                                    if p not in gris["powers"]:
                                        gris["powers"].append(p)
                                goto("f4", (1, BIG[1] // 2))
                                dialog.open("Mago Gris", "Absorbes su poder oscuro. "
                                            "(Aprendiste Garra Umbría, Drenar Alma y "
                                            "Eclipse) Una sombra crece en ti...")
                                state = "dialog"
                            else:                             # PERDONAR -> se une
                                negro_redeemed = True; balance += 2
                                black = make_combatant(BLACK_MAGE)
                                level_to(black, 5 + sum(world_done.values()) * 5)
                                extra_allies.append(black)
                                rebuild_party()
                                goto("f4", (1, BIG[1] // 2))
                                dialog.open("Mago Negro", "¡El hechizo se rompió! Soy "
                                            "libre. Voy contigo contra el verdadero "
                                            "villano: el Mago Blanco.")
                                state = "dialog"
                        elif last_enemy and last_enemy.get("maga"):
                            elem = last_enemy["maga"]
                            world_done[elem] = True
                            maga_lvl = battle.enemies[0].get("lvl", 1)
                            roster.append(recruit(elem, AI_OF[elem], maga_lvl))
                            for c in [gris] + roster:
                                level_to(c, maga_lvl + 1)
                            log_ctx(f"liberaste a {MAGA_BY_ELEM[elem]['name']}")
                            mg = MAGA_BY_ELEM[elem]["name"]
                            speech, reaction = RESCUE_LINES.get(
                                elem, ("Por fin libre...", f"{mg}: Gracias, Gris."))
                            ch = choice_screen(
                                f"Has liberado a {mg}.",
                                ["Caminar juntos para siempre",
                                 "Devolverle el reino a su pueblo",
                                 "Quedarte con su poder para la guerra"],
                                body=speech + "  ¿Qué haces ahora? "
                                "Tu decisión moldeará el destino del mundo.")
                            if ch == 0:
                                affinity[elem] += 2; last_bond = elem
                                dec = "Caminaréis juntos."
                            elif ch == 1:
                                balance += 2; dec = "Su pueblo reconstruirá el reino."
                            else:
                                shadow += 2; affinity[elem] += 1
                                dec = "Tomaste su poder."
                            if len(active) >= 2:
                                active[:] = team_screen(roster, active)
                            else:
                                active.append(len(roster) - 1)
                            rebuild_party()
                            toast = (f"¡{mg} liberada! {dec} Vuelve caminando y "
                                     "visita las casas por sus regalos.")
                            toast_t = 2200
                            dialog.open(mg, reaction + " " + dec)   # texto post-rescate
                            chat.ask(roster[-1],
                                     prompt="El Mago Gris acaba de liberarte de la "
                                     "posesión del Mago Negro. Reacciona y únete a él.",
                                     context=world_context())
                            state = "dialog"
                        else:
                            state = "overworld"
                    else:                       # DERROTA -> volver al menú principal
                        return
            elif state == "shop":
                if e.type == pygame.KEYDOWN:
                    ent = shop_entries()
                    if e.key in (pygame.K_ESCAPE, pygame.K_q):
                        state = "overworld"
                    elif e.key in (pygame.K_LEFT, pygame.K_a, pygame.K_RIGHT, pygame.K_d):
                        shop_mode = "sell" if shop_mode == "buy" else "buy"
                        shop_i = 0
                    elif e.key in (pygame.K_UP, pygame.K_w):
                        shop_i = (shop_i - 1) % max(1, len(ent))
                    elif e.key in (pygame.K_DOWN, pygame.K_s):
                        shop_i = (shop_i + 1) % max(1, len(ent))
                    elif e.key in (pygame.K_RETURN, pygame.K_e) and ent:
                        kind, ref, label, price = ent[shop_i % len(ent)]
                        if shop_mode == "sell":                  # VENDER (mitad de precio)
                            if kind == "item":
                                if ref["qty"] > 0:
                                    ref["qty"] -= 1; gold += price
                                    toast = f"Vendiste {ref['name']} (+{price}o)"
                                else:
                                    toast = "No te queda ninguno"
                            elif kind == "wear":
                                owned_wear.discard(ref)
                                for c in [gris] + roster:        # quitar si la lleva puesta
                                    if c.get("wear") and c["wear"]["name"] == ref:
                                        c["wear"] = None
                                gold += price; toast = f"Vendiste {ref} (+{price}o)"
                            else:
                                owned[kind].discard(ref)
                                if equipped[kind] == ref:
                                    equipped[kind] = -1
                                gold += price; toast = f"Vendiste {label} (+{price}o)"
                            toast_t = 1100
                        elif kind == "item":
                            if gold >= price:
                                gold -= price; ref["qty"] += 1
                                toast = f"Compraste {ref['name']}"
                            else:
                                toast = "Te falta oro"
                            toast_t = 1100
                        elif kind == "wear":         # accesorio de maga (req. nivel + dueña)
                            el, acc = ACC_BY_NAME[ref]
                            owner = gris if el == "neutro" else next(
                                (c for c in roster if c["elem"] == el), None)
                            if ref in owned_wear:
                                toast = "Ya la tienes"
                            elif owner is None:
                                toast = f"Libera a {MAGA_BY_ELEM[el]['name']} primero"
                            elif owner["lvl"] < acc.get("lvl", 1):
                                toast = f"Requiere que suba a nivel {acc['lvl']}"
                            elif gold >= price:
                                gold -= price; owned_wear.add(ref)
                                toast = f"Compraste {ref}"
                            else:
                                toast = "Te falta oro"
                            toast_t = 1100
                        else:
                            need = EQUIP[kind][ref].get("lvl", 1)
                            if ref in owned[kind]:
                                toast = "Ya la tienes"
                            elif gris["lvl"] < need:
                                toast = f"Requiere nivel {need}"
                            elif gold >= price:
                                gold -= price; owned[kind].add(ref)
                                toast = f"Compraste {label}"
                            else:
                                toast = "Te falta oro"
                            toast_t = 1100
            elif state == "bag":
                if e.type == pygame.KEYDOWN:
                    if e.key in (pygame.K_ESCAPE, pygame.K_q, pygame.K_b):
                        state = "overworld"
                    elif e.key in (pygame.K_LEFT, pygame.K_a):
                        bag_tab = (bag_tab - 1) % len(BAG_TABS); bag_i = 0
                    elif e.key in (pygame.K_RIGHT, pygame.K_d):
                        bag_tab = (bag_tab + 1) % len(BAG_TABS); bag_i = 0
                    elif e.key in (pygame.K_UP, pygame.K_w):
                        bag_i = max(0, bag_i - 1)
                    elif e.key in (pygame.K_DOWN, pygame.K_s):
                        bag_i += 1
                    elif e.key in (pygame.K_RETURN, pygame.K_e):
                        cat = BAG_TABS[bag_tab]
                        if cat == "Objetos":
                            it = ITEMS[bag_i % len(ITEMS)]
                            if it["qty"] > 0:
                                it["qty"] -= 1
                                tgt = min(party, key=lambda p: p["hp"] / p["maxhp"])
                                if it["kind"] == "hp":
                                    tgt["hp"] = min(tgt["maxhp"], tgt["hp"] + it["amt"])
                                elif it["kind"] == "mp":
                                    tgt["mp"] = min(tgt["maxmp"], tgt["mp"] + it["amt"])
                                else:
                                    tgt["hp"] = tgt["maxhp"]; tgt["mp"] = tgt["maxmp"]
                                toast = f"{tgt['name']} usa {it['name']}"; toast_t = 1100
                        else:
                            ow = sorted(owned[cat])
                            if bag_i == 0:
                                equipped[cat] = -1; toast = f"{cat}: ninguno"
                            elif bag_i - 1 < len(ow):
                                obj = EQUIP[cat][ow[bag_i - 1]]
                                if gris["lvl"] < obj.get("lvl", 1):
                                    toast = f"Requiere nivel {obj['lvl']}"
                                else:
                                    equipped[cat] = ow[bag_i - 1]
                                    toast = f"Equipado: {obj['name']}"
                            toast_t = 1100
            elif state == "status":
                if e.type == pygame.KEYDOWN:
                    sel_m = min(sel_m, len(party) - 1)
                    tabname = STATUS_TABS[status_tab]
                    tgt = party[sel_m]
                    split = tabname in ("Pociones", "Accesorios")
                    if tabname == "Pociones":
                        rlist = ITEMS
                    elif tabname == "Accesorios":
                        rlist = acc_options()
                    elif tabname == "Equipo":
                        rlist = equip_list()
                    else:
                        rlist = [None]
                    n_items = max(1, len(rlist))
                    if e.key == pygame.K_c:                  # C (abrir/cerrar) = salir
                        state = "overworld"; status_focus = "chars"
                    elif e.key in (pygame.K_ESCAPE, pygame.K_q):   # B/ESC = ATRÁS un paso
                        if split and status_focus == "list":  # de objetos -> personajes
                            status_focus = "chars"
                        else:
                            state = "overworld"; status_focus = "chars"
                    elif e.key in (pygame.K_LEFT, pygame.K_a):    # LT = pestaña anterior
                        status_tab = (status_tab - 1) % len(STATUS_TABS)
                        status_i = 0; status_focus = "chars"
                    elif e.key in (pygame.K_RIGHT, pygame.K_d):   # RT = pestaña siguiente
                        status_tab = (status_tab + 1) % len(STATUS_TABS)
                        status_i = 0; status_focus = "chars"
                    elif e.key in (pygame.K_UP, pygame.K_w):
                        if tabname == "Estado" or (split and status_focus == "chars"):
                            sel_m = (sel_m - 1) % len(party)
                        else:
                            status_i = (status_i - 1) % n_items
                    elif e.key in (pygame.K_DOWN, pygame.K_s):
                        if tabname == "Estado" or (split and status_focus == "chars"):
                            sel_m = (sel_m + 1) % len(party)
                        else:
                            status_i = (status_i + 1) % n_items
                    elif e.key in (pygame.K_RETURN, pygame.K_e):
                        if tabname == "Pociones":
                            if status_focus == "chars":     # 1º elegiste personaje
                                status_focus = "list"; status_i = 0
                            else:                           # 2º elegiste objeto -> usar
                                it = ITEMS[status_i % len(ITEMS)]
                                who = party[sel_m]
                                ph, pm = who["hp"], who["mp"]
                                toast = use_item_on(it, who); toast_t = 1100
                                dh, dm = who["hp"] - ph, who["mp"] - pm
                                if dh:
                                    float_fx.append({"i": sel_m, "txt": f"{dh:+d}",
                                                     "col": GREEN if dh > 0 else RED, "t": 1100})
                                if dm:
                                    float_fx.append({"i": sel_m, "txt": f"{dm:+d}",
                                                     "col": BLUE, "t": 1100})
                        elif tabname == "Accesorios":
                            if status_focus == "chars":     # 1º elegiste personaje
                                status_focus = "list"; status_i = 0
                            else:                           # 2º elegiste accesorio
                                el, a = rlist[status_i % len(rlist)]
                                if a is None:
                                    tgt["wear"] = None
                                    toast = f"{tgt['name']}: sin accesorio"
                                elif el != tgt["elem"]:
                                    toast = f"{a['name']} no es de {tgt['name']}"
                                elif tgt["lvl"] < a.get("lvl", 1):
                                    toast = f"Requiere nivel {a['lvl']}"
                                else:
                                    tgt["wear"] = a
                                    toast = f"{tgt['name']}: {a['name']}"
                                toast_t = 1100
                        elif tabname == "Equipo":
                            lst = equip_list()
                            if not lst:
                                toast = "No tienes equipo (compra en el Mercader)"
                            else:
                                cat, i = lst[status_i % len(lst)]
                                need = EQUIP[cat][i].get("lvl", 1)
                                if equipped[cat] == i:        # ya puesto -> quitar
                                    equipped[cat] = -1
                                    toast = f"{cat}: quitado"
                                elif gris["lvl"] < need:
                                    toast = f"Requiere nivel {need}"
                                else:
                                    equipped[cat] = i
                                    toast = f"{cat}: {EQUIP[cat][i]['name']} equipado"
                            toast_t = 1100
                        elif tabname == "Grupo":
                            if roster:
                                active[:] = team_screen(roster, active); rebuild_party()
                            else:
                                toast = "Aún no tienes magas"; toast_t = 1100
                        elif tabname == "Guardar":
                            toast = (f"Guardado en Partida {slot} ✓"
                                     if save_slot(slot, save_data()) else "Error al guardar")
                            toast_t = 1400
            elif state == "pause":
                if e.type == pygame.KEYDOWN:
                    if e.key in (pygame.K_ESCAPE, pygame.K_q):
                        state = "overworld"                  # B/ESC = Volver
                    elif e.key in (pygame.K_UP, pygame.K_w):
                        pause_i = (pause_i - 1) % len(PAUSE_OPTS)
                    elif e.key in (pygame.K_DOWN, pygame.K_s):
                        pause_i = (pause_i + 1) % len(PAUSE_OPTS)
                    elif e.key in (pygame.K_RETURN, pygame.K_e):
                        if pause_i == 0:
                            state = "overworld"
                        elif pause_i == 1:                   # Guardar
                            toast = (f"Guardado en Partida {slot} ✓"
                                     if save_slot(slot, save_data()) else "Error al guardar")
                            toast_t = 1400
                        else:                                # Menú principal
                            return
            elif state == "overworld":
                if e.type == pygame.KEYDOWN:
                    if e.key in (pygame.K_ESCAPE, pygame.K_q):  # PAUSA
                        state = "pause"; pause_i = 0
                    elif e.key == pygame.K_c:                # consultar Estado
                        state = "status"; status_i = 0; status_focus = "chars"
                    elif e.key == pygame.K_t and roster:    # gestionar grupo
                        active[:] = team_screen(roster, active)
                        rebuild_party()
                    elif e.key == pygame.K_b:               # abrir Bolsa
                        state = "bag"; bag_tab = 0; bag_i = 0
                    elif e.key in (pygame.K_e, pygame.K_RETURN):
                        fx, fy = px + facing[0], py + facing[1]
                        # 1) NPC en la casilla que miras (si no, cualquiera adyacente)
                        tk = next((t for t in talkers if (t["x"], t["y"]) == (fx, fy)), None)
                        if tk is None:
                            tk = next((t for t in talkers
                                       if abs(t["x"] - px) + abs(t["y"] - py) == 1), None)
                        if tk and tk.get("shop"):
                            state = "shop"; shop_i = 0; shop_mode = "buy"
                            shop_plan_key = ("hub" if loc == "hub" else
                                             "final" if loc in ("f2", "f5") else
                                             loc.split(":")[0] if ":" in loc else "hub")
                        elif tk and tk.get("angel"):           # ángel: cura total
                            for c in party:
                                c["hp"] = c["maxhp"]; c["mp"] = c["maxmp"]
                            if tk in talkers:
                                talkers.remove(tk)
                            dialog.open("Ángel de la Luz", "Recibe mi luz, Gris. Tú y "
                                        "tus compañeras recuperáis todas vuestras fuerzas.")
                            state = "dialog"
                        elif tk and tk.get("ai_persona") and not chat.busy:
                            chat.ask(claude_char(tk["name"], tk["ai_persona"]),
                                     prompt="El Mago Gris se acerca a hablar contigo.",
                                     context=world_context())
                        elif tk:
                            welem = tk.get("welem")
                            if tk.get("scout"):            # pista DINÁMICA / liberado
                                acs = [e for e in enemies if e["alive"]
                                       and e.get("kind") == "acolito"]
                                if welem and world_done.get(welem):
                                    txt = (f"{MAGA_BY_ELEM[welem]['name']} vela otra vez "
                                           f"por {ELEM_NAME[welem]}. ¡Gracias, Gris!")
                                elif acs:
                                    a = min(acs, key=lambda e: abs(e["x"] - px)
                                            + abs(e["y"] - py))
                                    dist = abs(a["x"] - px) + abs(a["y"] - py)
                                    cerca = ("muy cerca" if dist < 12 else
                                             "cerca" if dist < 30 else "lejos")
                                    txt = ("Vi a un acólito del Mago Negro hacia "
                                           f"{hint_dir(px, py, a['x'], a['y'])}, {cerca}"
                                           ". ¡Y se está moviendo!")
                                else:
                                    txt = ("Ya no quedan acólitos por aquí. "
                                           "¡La puerta del este se abrió!")
                            else:
                                txt = villager_text(tk, world_done)
                            dialog.open(tk["name"], txt)
                            log_ctx(f"{tk['name']} dijo: {txt}")
                            state = "dialog"
                        else:
                            # 2) jefe enfrente (maga poseída / Negro / Blanco) -> IA real
                            men = next((en for en in enemies if en["alive"]
                                        and (en["x"], en["y"]) == (fx, fy)
                                        and (en.get("maga") or en.get("subfinal")
                                             or en.get("final") or en.get("prologue"))),
                                       None)
                            cps = comp_positions()
                            ci = next((i for i, p in enumerate(cps)
                                       if p == (fx, fy)), None)
                            if men and not chat.busy:
                                if men.get("maga"):
                                    el = men["maga"]
                                    poss = {"name": MAGA_BY_ELEM[el]["name"], "elem": el,
                                            "ai": AI_OF[el], "lvl": men.get("lvl", 1)}
                                    chat.ask(poss, prompt="Estás POSEÍDA por el Mago "
                                             "Negro y el Mago Gris te confronta. Dile algo "
                                             "amenazante o atormentado.",
                                             context=world_context())
                                elif men.get("prologue"):       # Negro en el hall (Claude)
                                    chat.ask(claude_char("Mago Negro", PERSONA_NEGRO),
                                             prompt="Apareces por sorpresa en el hall tras "
                                             "liberar 3 magas. Provocas al Mago Gris antes "
                                             "de este primer duelo.", context=world_context())
                                elif men.get("subfinal"):       # Mago Negro (Claude)
                                    chat.ask(claude_char("Mago Negro", PERSONA_NEGRO),
                                             prompt="El Mago Gris te confronta antes de "
                                             "la batalla. Háblale.", context=world_context())
                                else:                            # Mago Blanco (Claude)
                                    chat.ask(claude_char("Mago Blanco", PERSONA_BLANCO),
                                             prompt="El Mago Gris ha llegado hasta tu "
                                             "trono. Háblale.", context=world_context())
                            elif ci is not None and not chat.busy:
                                # 3) maga aliada enfrente -> que comente (con contexto)
                                chat.ask(companions()[ci], context=world_context())
                    # hablar con una maga reclutada (1..6): respuesta asíncrona
                    elif pygame.K_1 <= e.key <= pygame.K_6:
                        idx = e.key - pygame.K_1
                        if idx < len(companions()) and not chat.busy:
                            chat.ask(companions()[idx], context=world_context())

        # glide visual hacia la casilla actual (transición suave al caminar)
        _step = dt / 95.0                       # ~1 casilla cada 95 ms
        if abs(px - vis_x) <= _step:
            vis_x = float(px)
        else:
            vis_x += _step if px > vis_x else -_step
        if abs(py - vis_y) <= _step:
            vis_y = float(py)
        else:
            vis_y += _step if py > vis_y else -_step
        # glide de las magas acompañantes (mismo ritmo; salto si quedan muy lejos)
        _targets = comp_positions()
        if len(comp_vis) != len(_targets):
            comp_vis = [[float(t[0]), float(t[1])] for t in _targets]
        for _i, (_tx, _ty) in enumerate(_targets):
            _cv = comp_vis[_i]
            if abs(_tx - _cv[0]) > 3 or abs(_ty - _cv[1]) > 3:
                _cv[0], _cv[1] = float(_tx), float(_ty)
            else:
                _cv[0] = _tx if abs(_tx - _cv[0]) <= _step else _cv[0] + (
                    _step if _tx > _cv[0] else -_step)
                _cv[1] = _ty if abs(_ty - _cv[1]) <= _step else _cv[1] + (
                    _step if _ty > _cv[1] else -_step)

        # --- update por estado ---
        if state == "overworld":
            # enemigos deambulan (acólitos y criaturas; los jefes no)
            enemy_move_t += dt
            if enemy_move_t > 480:
                enemy_move_t = 0
                occ = {(t["x"], t["y"]) for t in talkers}
                occ |= {(en["x"], en["y"]) for en in enemies if en["alive"]}
                for en in enemies:
                    if not en["alive"] or en.get("kind") not in ("acolito", "ambient"):
                        continue
                    edist = abs(en["x"] - px) + abs(en["y"] - py)
                    chasing = en.get("chase") and edist <= 14   # te ve en pantalla
                    if not chasing and random.random() > 0.6:
                        continue
                    if chasing:                                 # te persigue
                        ddx = (1 if px > en["x"] else -1 if px < en["x"] else 0)
                        ddy = (1 if py > en["y"] else -1 if py < en["y"] else 0)
                        if ddx and ddy:                         # un eje por paso
                            if abs(px - en["x"]) >= abs(py - en["y"]):
                                ddy = 0
                            else:
                                ddx = 0
                    else:
                        ddx, ddy = random.choice([(1, 0), (-1, 0), (0, 1), (0, -1)])
                    tx, ty = en["x"] + ddx, en["y"] + ddy
                    if (tx, ty) == (px, py):           # te embiste -> combate
                        last_enemy = en
                        start_battle(en)
                        break
                    if (not blocked(rt["grid"], tx, ty) and (tx, ty) not in occ
                            and rt["grid"][ty][tx] != 4):
                        occ.discard((en["x"], en["y"]))
                        en["x"], en["y"] = tx, ty
                        occ.add((tx, ty))

        if state == "overworld":
            dx = dy = 0
            if move_cd <= 0:
                jx = jy = 0
                if joy:
                    if joy.get_numhats() > 0:
                        hx, hy = joy.get_hat(0)
                        jx, jy = hx, -hy
                    if jx == 0 and jy == 0 and joy.get_numaxes() >= 2:
                        ax, ay = joy.get_axis(0), joy.get_axis(1)
                        jx = 1 if ax > 0.5 else -1 if ax < -0.5 else 0
                        jy = 1 if ay > 0.5 else -1 if ay < -0.5 else 0
                if keys[pygame.K_LEFT] or keys[pygame.K_a] or jx < 0: dx = -1
                elif keys[pygame.K_RIGHT] or keys[pygame.K_d] or jx > 0: dx = 1
                elif keys[pygame.K_UP] or keys[pygame.K_w] or jy < 0: dy = -1
                elif keys[pygame.K_DOWN] or keys[pygame.K_s] or jy > 0: dy = 1
                if (dx or dy) and facing != (dx, dy):
                    facing = (dx, dy)          # primer toque: GIRAR (no avanzar)
                    move_cd = 90
                elif dx or dy:
                    nx, ny = px + dx, py + dy
                    hit = next((en for en in enemies
                                if en["alive"] and (en["x"], en["y"]) == (nx, ny)), None)
                    occ = any((nx, ny) == (tk["x"], tk["y"]) for tk in talkers)
                    if hit and hit.get("final") and not negro_done:
                        toast = "Primero derrota al Mago Negro"; toast_t = 1500
                        move_cd = 200
                    elif hit:
                        last_enemy = hit
                        move_cd = 250
                        start_battle(hit)
                    elif not blocked(rt["grid"], nx, ny) and not occ:
                        px, py = nx, ny
                        move_cd = OPTS.get("move_ms", 120)
                        trail.insert(0, (px, py))
                        if len(trail) > 16:
                            trail.pop()
                        for cst in rt.get("chests", []):      # tesoro oculto al pisarlo
                            if cst["got"] or (cst["x"], cst["y"]) != (px, py):
                                continue
                            cst["got"] = True
                            if cst["kind"] == "gold":
                                gold += cst["val"]
                                toast = f"¡Tesoro oculto! +{cst['val']} oro"
                            else:
                                val = cst["val"]
                                if val in SUPER_GATED and not super_ok():
                                    val = "Poción"          # aún no desbloqueado
                                it = next((i for i in ITEMS if i["name"] == val), None)
                                if it:
                                    it["qty"] += 1
                                toast = f"¡Tesoro oculto! {val}"
                            toast_t = 2000
                            break
                        if rt["grid"][py][px] == 4:
                            for ex in rt["exits"]:
                                if ex["pos"] != (px, py):
                                    continue
                                if ex.get("world"):           # puerta del hub a un mundo
                                    w = ex["world"]
                                    if world_done[w]:        # liberado: re-entrar libre
                                        toast = (f"Vuelves a {WORLD_NAME[w]} "
                                                 "(ya liberado)")
                                        toast_t = 1500
                                        goto(ex["to"], ex["spawn"])
                                    elif not world_unlocked(w):
                                        if (sum(world_done[e] for e in BASE_WORLDS) < 3
                                                or not negro_prologue):
                                            toast = ("Sellada: libera las 3 primeras magas "
                                                     "y vence al Mago Negro del hall")
                                        else:
                                            toast = "Sellada: limpia el reino abierto primero"
                                        toast_t = 2200
                                    else:
                                        goto(ex["to"], ex["spawn"])
                                elif ex.get("final"):         # puerta a la guarida final
                                    if all(world_done.values()):
                                        goto("f1", ex["spawn"])
                                    else:
                                        falt = sum(1 for v in world_done.values() if not v)
                                        toast = f"Libera a las 6 magas ({falt} faltan)"
                                        toast_t = 1800
                                elif ex.get("ending"):        # escena final -> epílogo
                                    ending_key = ex["ending"]
                                    state = "ending"
                                elif ex.get("locked") and any(
                                        en["alive"] and en.get("kind") == "acolito"
                                        for en in enemies):
                                    toast = "Sellado: derrota a los acólitos de esta zona"
                                    toast_t = 1800
                                elif ex.get("house"):         # entrar a una casa
                                    goto(ex["to"], ex["spawn"])
                                    welem = ex["to"].split(":")[0]
                                    if ex["to"].startswith("f2:house"):   # regalo final
                                        if ex["to"] not in houses_claimed:
                                            houses_claimed.add(ex["to"])
                                            toast = give_prize(random.choice(WORLD_ORDER))
                                            toast_t = 2200
                                    elif world_done.get(welem) and \
                                            ex["to"] not in houses_claimed:
                                        houses_claimed.add(ex["to"])
                                        toast = give_prize(welem); toast_t = 2200
                                else:
                                    goto(ex["to"], ex["spawn"])
                                break
        elif state == "dialog":
            dialog.update()
        elif state == "battle":
            battle.update()
            if battle.phase == "fled":          # huiste -> de vuelta al mundo
                state = "overworld"
                for c in party:                 # revive aliados caídos al escapar
                    if not c["alive"] or c["hp"] <= 0:
                        c["alive"] = True
                        c["hp"] = max(1, c["maxhp"] // 3)
                toast = "¡Escapaste!"; toast_t = 1300

        # --- dibujo ---
        if state == "battle":
            battle.draw()
        elif state == "ending":
            screen.fill(BLACK)
            draw_text(screen, "El Mago Blanco ha caído.", 40, 80, font_lg, GOLD)
            lines = ENDINGS.get(ending_key, ENDINGS["_"])
            for j, ln in enumerate(lines + ["", "FIN.  [ESC] salir"]):
                draw_text(screen, ln, 40, 150 + j * 28, font_sm, WHITE)
            present()
            continue
        else:
            screen.fill(BLACK)
            w, h = rt["w"], rt["h"]
            vh = H - HUD_H
            camx, camy = calc_cam(vis_x, vis_y, w, h)   # cámara sigue la pos VISUAL
            cdy = camy - HUD_H          # offset de dibujo: el mundo va BAJO el HUD
            theme = rt["theme"]
            # mundo POSEÍDO = oscuro; al liberar a su maga vuelven los colores reales
            wel = loc.split(":")[0] if loc not in ("hub", "final") else None
            if wel in world_done and not world_done[wel] \
                    and (theme + "_dark") in THEMES:
                theme = theme + "_dark"
            grid = rt["grid"]
            x0, y0 = camx // TILE, camy // TILE
            x1, y1 = (camx + W) // TILE + 1, (camy + vh) // TILE + 1
            for y in range(max(0, y0), min(h, y1)):
                for x in range(max(0, x0), min(w, x1)):
                    draw_tile(theme, x, y, grid[y][x], camx, cdy)
            # puertas del hub: marcador de color + CARTEL con la maga del mundo
            if loc == "hub":
                for ex in rt["exits"]:
                    ex_x = ex["pos"][0] * TILE + TILE // 2 - camx
                    ex_y = ex["pos"][1] * TILE + TILE // 2 - cdy
                    col = ELEM_COLOR.get(ex.get("elem", "neutro"), GOLD)
                    pygame.draw.circle(screen, col, (ex_x, ex_y), 8)
                    pygame.draw.circle(screen, WHITE, (ex_x, ex_y), 8, 1)
                    label = ex.get("label")
                    if not label:
                        continue
                    if ex.get("world") and world_done[ex["world"]]:
                        label += " ✔"
                    elif ex.get("world") and not world_unlocked(ex["world"]):
                        label += "  [sellada]"
                    elif ex.get("final") and not all(world_done.values()):
                        label += "  [sellada]"
                    tw = font_xs.size(label)[0]
                    lx = ex_x - tw // 2
                    ly = ex_y + 12 if ex["pos"][1] == 0 else ex_y - 24
                    pygame.draw.rect(screen, (16, 16, 26),
                                     (lx - 4, ly - 2, tw + 8, 16), border_radius=4)
                    pygame.draw.rect(screen, col, (lx - 4, ly - 2, tw + 8, 16),
                                     1, border_radius=4)
                    draw_text(screen, label, lx, ly, font_xs, WHITE)
            bob = -3 if (bob_t // 200) % 2 == 0 else 0
            for cst in rt.get("chests", []):       # tesoros ocultos
                if not cst["got"]:
                    draw_chest(cst["x"], cst["y"], camx, cdy)
            for tk in talkers:
                if tk.get("angel"):                # tamaño normal, con alas
                    draw_actor(tk["color"], tk["x"], tk["y"], bob, camx, cdy,
                               wings=True)
                else:
                    draw_actor(tk["color"], tk["x"], tk["y"], bob, camx, cdy)
            for en in enemies:
                if en["alive"]:
                    if en.get("throne"):           # la maga aguarda en su trono
                        draw_throne(en["x"], en["y"], camx, cdy)
                    if en.get("dragon"):           # el dragón es más grande (con alas)
                        draw_actor(en["color"], en["x"], en["y"], bob, camx, cdy,
                                   scale=2.2, wings=True)
                    else:
                        draw_actor(en["color"], en["x"], en["y"], bob, camx, cdy)
            comps = companions()
            for i in range(min(len(comps), len(comp_vis))):   # magas con glide suave
                cvx, cvy = comp_vis[i]
                draw_actor(comps[i]["color"], cvx, cvy, bob, camx, cdy)
            draw_actor(party[0]["color"], vis_x, vis_y, 0, camx, cdy, face=facing)

            # HUD
            pygame.draw.rect(screen, (10, 12, 20), (0, 0, W, HUD_H))
            draw_text(screen, rt["name"], 8, 4, font_xs, GOLD)
            draw_text(screen, f"Oro:{gold}  Magas:{sum(world_done.values())}/6  "
                              "E·hablar B·bolsa C·estado T·grupo 1-6·IA",
                      150, 4, font_xs, DIM)
            fx, fy = px + facing[0], py + facing[1]
            prompt_pos = None
            for tk in talkers:
                if (tk["x"], tk["y"]) == (fx, fy) or \
                        abs(tk["x"] - px) + abs(tk["y"] - py) == 1:
                    prompt_pos = (tk["x"], tk["y"]); break
            if prompt_pos is None and (fx, fy) in comp_positions():
                prompt_pos = (fx, fy)            # mirando a una maga -> puede comentar
            if prompt_pos:
                draw_text(screen, "[E]", prompt_pos[0] * TILE - camx + 4,
                          prompt_pos[1] * TILE - cdy - 16, font_xs, GOLD)
            # brújula (N/S/E/O) con aguja hacia donde mira el Gris
            ccx, ccy = 34, H - 32
            pygame.draw.circle(screen, (14, 16, 28), (ccx, ccy), 18)
            pygame.draw.circle(screen, BOX_BORDER, (ccx, ccy), 18, 1)
            pygame.draw.line(screen, GOLD, (ccx, ccy),
                             (ccx + facing[0] * 12, ccy + facing[1] * 12), 2)
            draw_text(screen, "N", ccx - 3, ccy - 17, font_xs, WHITE)
            draw_text(screen, "S", ccx - 3, ccy + 7, font_xs, DIM)
            draw_text(screen, "E", ccx + 9, ccy - 6, font_xs, DIM)
            draw_text(screen, "O", ccx - 15, ccy - 6, font_xs, DIM)
            if chat.busy:
                mm, ss = divmod(chat.elapsed(), 60)
                dots = "." * (1 + (bob_t // 400) % 3)
                msg = f"{chat.who['name']} [{chat.who['ai']['name']}] pensando{dots} ({mm:02d}:{ss:02d})"
                if chat.timed_out():
                    msg = f"{chat.who['name']}: la IA tarda demasiado..."
                cb = pygame.Rect(8, 26, W - 16, 22)
                pygame.draw.rect(screen, (12, 14, 26), cb, border_radius=6)
                pygame.draw.rect(screen, chat.who["ai"]["color"], cb, 1, border_radius=6)
                draw_text(screen, msg, cb.x + 8, cb.y + 4, font_xs, (200, 220, 255))
            if state == "shop":
                ent = shop_entries()
                lines = []
                for kind, ref, label, price in ent:
                    tag = ""
                    if shop_mode == "buy" and kind == "wear":
                        el, acc = ACC_BY_NAME[ref]
                        owner = gris if el == "neutro" else next(
                            (c for c in roster if c["elem"] == el), None)
                        if ref in owned_wear:
                            tag = " ✔"
                        elif owner is None:
                            tag = f"  (libera a {MAGA_BY_ELEM[el]['name']})"
                        elif owner["lvl"] < acc.get("lvl", 1):
                            tag = f"  (Nv{acc['lvl']})"
                    elif shop_mode == "buy" and kind in owned and ref in owned[kind]:
                        tag = " ✔"
                    lines.append(f"{label} - {price}o{tag}")
                if not lines:
                    lines = ["(nada para vender)"]
                title = ("Mercader · COMPRAR" if shop_mode == "buy"
                         else "Mercader · VENDER")
                draw_menu_panel(f"{title}   (Oro: {gold})", lines, shop_i,
                                "ENTER " + ("comprar" if shop_mode == "buy" else "vender")
                                + " | ◄/► compra/venta | ESC salir")
            elif state == "bag":
                cat = BAG_TABS[bag_tab]
                if cat == "Objetos":
                    lines = [f"{it['name']} x{it['qty']}" for it in ITEMS]
                else:
                    lines = ["(Ninguno)"]
                    for i in sorted(owned[cat]):
                        obj = EQUIP[cat][i]
                        mk = " [equipado]" if equipped[cat] == i else ""
                        lines.append(f"{obj['name']} +{obj[EQUIP_STAT[cat]]}{mk}")
                bag_i = min(bag_i, len(lines) - 1)
                draw_menu_panel(f"Bolsa - {cat}   (◄/► pestaña)", lines, bag_i,
                                "ENTER usar/equipar | ESC salir")
            elif state == "status":
                sel_m = min(sel_m, len(party) - 1)
                tgt = party[sel_m]
                tabname = STATUS_TABS[status_tab]
                split = tabname in ("Pociones", "Accesorios")
                pn = pygame.Rect(24, 30, W - 48, H - 56)
                pygame.draw.rect(screen, BOX_BG, pn, border_radius=10)
                pygame.draw.rect(screen, BOX_BORDER, pn, 3, border_radius=10)
                # barra de pestañas (LT/RT)
                draw_text(screen, "◄ LT", pn.x + 10, pn.y + 10, font_xs, DIM)
                draw_text(screen, "RT ►", pn.right - 44, pn.y + 10, font_xs, DIM)
                tx = pn.x + 56
                for i, tname in enumerate(STATUS_TABS):
                    tw = font_sm.size(tname)[0] + 16
                    if i == status_tab:
                        pygame.draw.rect(screen, (40, 50, 80),
                                         (tx - 4, pn.y + 6, tw, 22), border_radius=5)
                    draw_text(screen, tname, tx + 4, pn.y + 9, font_sm,
                              GOLD if i == status_tab else DIM)
                    tx += tw + 4
                pygame.draw.line(screen, GRAY, (pn.x + 10, pn.y + 34),
                                 (pn.right - 10, pn.y + 34))
                cy0 = pn.y + 46
                # nombre del personaje activo
                draw_text(screen, f"{tgt['name']} · {ELEM_NAME[tgt['elem']]} · Nv{tgt['lvl']}"
                          + (f" · IA {tgt['ai']['name']}" if tgt.get("ai") else " · TÚ"),
                          pn.x + 16, cy0, font_md, tgt["color"])

                rx = pn.x + 16
                if split:
                    # PANEL IZQUIERDO: personajes (sprite + barras 3 colores)
                    lx, lw, barw = pn.x + 12, 250, 100
                    ly0 = cy0 + 30
                    sprite_pos = {}
                    for i, c in enumerate(party):
                        ry = ly0 + i * 54
                        if i == sel_m:
                            hl = (60, 70, 110) if status_focus == "chars" else (34, 38, 58)
                            pygame.draw.rect(screen, hl, (lx, ry - 2, lw, 50),
                                             border_radius=6)
                            if status_focus == "chars":
                                pygame.draw.rect(screen, GOLD, (lx, ry - 2, lw, 50),
                                                 2, border_radius=6)
                        col = c["color"] if c["alive"] else GRAY
                        pygame.draw.circle(screen, col, (lx + 18, ry + 20), 13)
                        pygame.draw.circle(screen, WHITE, (lx + 18, ry + 20), 13, 2)
                        sprite_pos[i] = (lx + 18, ry + 6)
                        draw_text(screen, c["name"], lx + 36, ry, font_sm, WHITE)
                        bx = lx + 36
                        hf = c["hp"] / c["maxhp"]
                        pygame.draw.rect(screen, (20, 20, 26), (bx, ry + 20, barw, 6),
                                         border_radius=3)
                        pygame.draw.rect(screen, hp_color(hf),
                                         (bx, ry + 20, int(barw * hf), 6), border_radius=3)
                        draw_text(screen, f"{c['hp']}/{c['maxhp']}", bx + barw + 6,
                                  ry + 17, font_xs, DIM)
                        mf = c["mp"] / c["maxmp"] if c["maxmp"] else 0
                        pygame.draw.rect(screen, (20, 20, 26), (bx, ry + 32, barw, 5),
                                         border_radius=3)
                        pygame.draw.rect(screen, BLUE, (bx, ry + 32, int(barw * mf), 5),
                                         border_radius=3)
                        draw_text(screen, f"MP {c['mp']}/{c['maxmp']}", bx + barw + 6,
                                  ry + 30, font_xs, DIM)
                    # números flotantes (+/-) sobre los sprites
                    for f in float_fx:
                        f["t"] -= dt
                        sp = sprite_pos.get(f["i"])
                        if sp:
                            rise = int((1100 - f["t"]) * 0.03)
                            draw_text(screen, f["txt"], sp[0] - 12, sp[1] - 16 - rise,
                                      font_md, f["col"])
                    float_fx[:] = [f for f in float_fx if f["t"] > 0]
                    pygame.draw.line(screen, GRAY, (lx + lw, ly0),
                                     (lx + lw, pn.bottom - 30))
                    rx = lx + lw + 14
                rw = pn.right - rx - 14            # ancho del panel derecho

                if tabname == "Estado":
                    eb = {"atk": eqbonus("Arma", "atk"),
                          "df": eqbonus("Armadura", "df") + wear_bonus(tgt, "df"),
                          "pow": eqbonus("Foco", "pow") + wear_bonus(tgt, "pow")}

                    def stat_line(lbl, base, bonus):
                        if bonus:
                            return f"{lbl} {base} (+{bonus}) = {base + bonus}"
                        return f"{lbl} {base}"
                    st = [f"HP {tgt['hp']}/{tgt['maxhp']}", f"MP {tgt['mp']}/{tgt['maxmp']}",
                          f"XP {tgt['xp']}/{xp_to_next(tgt['lvl'])}",
                          stat_line("ATK", tgt["atk"], eb["atk"]),
                          stat_line("DEF", tgt["df"], eb["df"]),
                          f"VEL {tgt['spd']}   PRECISIÓN {tgt.get('pre', 90)}   "
                          f"AGUANTE {tgt.get('agu', 10)}"]
                    if eb["pow"]:
                        st.append(f"PODER base 0 (+{eb['pow']}) = {eb['pow']}  "
                                  "(foco/accesorio)")
                    for j, s in enumerate(st):
                        draw_text(screen, s, pn.x + 16, cy0 + 30 + j * 20, font_sm, WHITE)
                    py0 = cy0 + 30 + len(st) * 20 + 8
                    draw_text(screen, "Poderes: " + ", ".join(p[0] for p in tgt["powers"]),
                              pn.x + 16, py0, font_xs, DIM)
                    w = tgt.get("wear")
                    draw_text(screen, "Accesorio: " + (w["name"] if w else "—"),
                              pn.x + 16, py0 + 20, font_xs, (210, 180, 230))
                    foot = "↑/↓ cambiar de personaje"
                elif tabname == "Pociones":
                    act = status_focus == "list"
                    draw_text(screen, "OBJETOS", rx, cy0 + 26, font_xs,
                              GOLD if act else DIM)
                    for i, it in enumerate(ITEMS):
                        yy = cy0 + 44 + i * 22
                        if i == status_i % len(ITEMS):
                            pygame.draw.rect(screen, (60, 70, 110) if act else (34, 38, 58),
                                             (rx - 4, yy - 2, rw, 20), border_radius=4)
                            if act:
                                pygame.draw.rect(screen, GOLD, (rx - 4, yy - 2, rw, 20),
                                                 2, border_radius=4)
                        draw_text(screen, f"{it['name']} x{it['qty']}",
                                  rx + 6, yy, font_sm, WHITE)
                    foot = (f"↑/↓ objeto | ENTER dar a {tgt['name']} | B/ESC volver" if act
                            else "↑/↓ personaje | ENTER elegir objeto")
                elif tabname == "Accesorios":
                    act = status_focus == "list"
                    opts = acc_options()
                    draw_text(screen, "ACCESORIOS", rx, cy0 + 26, font_xs,
                              GOLD if act else DIM)
                    for i, (el, a) in enumerate(opts):
                        yy = cy0 + 44 + i * 22
                        if i == status_i % len(opts):
                            pygame.draw.rect(screen, (60, 70, 110) if act else (34, 38, 58),
                                             (rx - 4, yy - 2, rw, 20), border_radius=4)
                            if act:
                                pygame.draw.rect(screen, GOLD, (rx - 4, yy - 2, rw, 20),
                                                 2, border_radius=4)
                        nm = "(Ninguno)" if a is None else a["name"]
                        eq = " [puesto]" if (a and tgt.get("wear")
                                            and tgt["wear"]["name"] == a["name"]) else ""
                        cc = WHITE if (a is None or el == tgt["elem"]) else DIM
                        draw_text(screen, nm + eq, rx + 6, yy, font_sm, cc)
                    el, a = opts[status_i % len(opts)]      # descripción del resaltado
                    desc = acc_desc(el, a)
                    dy = cy0 + 44 + len(opts) * 22 + 10
                    pygame.draw.rect(screen, (24, 26, 42), (rx - 4, dy, rw, 40),
                                     border_radius=4)
                    for j, ln in enumerate(wrap(desc, font_xs, rw - 12)):
                        draw_text(screen, ln, rx + 6, dy + 6 + j * 14, font_xs,
                                  (210, 200, 150))
                    foot = (f"↑/↓ accesorio | ENTER equipar en {tgt['name']} | B/ESC volver"
                            if act else "↑/↓ maga | ENTER elegir accesorio")
                elif tabname == "Equipo":
                    eqd = "  ".join(f"{cat[:3]}:" + (EQUIP[cat][equipped[cat]]["name"]
                                    if equipped[cat] >= 0 else "—")
                                    for cat in ("Arma", "Foco", "Armadura"))
                    draw_text(screen, "Equipado: " + eqd, pn.x + 16, cy0 + 28,
                              font_xs, (200, 210, 160))
                    lst = equip_list()
                    if not lst:
                        draw_text(screen, "No tienes equipo. Compra en el Mercader.",
                                  pn.x + 16, cy0 + 52, font_sm, DIM)
                    for i, (cat, j) in enumerate(lst):
                        yy = cy0 + 52 + i * 20
                        if i == status_i % len(lst):
                            pygame.draw.rect(screen, (40, 50, 80),
                                             (pn.x + 10, yy - 2, 420, 18), border_radius=4)
                        obj = EQUIP[cat][j]
                        mk = " [equipado]" if equipped[cat] == j else ""
                        need = obj.get("lvl", 1)
                        locked = gris["lvl"] < need
                        nv = f" (Nv{need})" if locked else ""
                        col = DIM if locked else WHITE
                        draw_text(screen, f"{cat}: {obj['name']} "
                                  f"+{obj[EQUIP_STAT[cat]]}{nv}{mk}", pn.x + 20, yy,
                                  font_sm, col)
                    foot = "↑/↓ elegir | ENTER equipar/quitar"
                elif tabname == "Grupo":
                    draw_text(screen, "Gestiona quién va en tu grupo (Gris + 2).",
                              pn.x + 16, cy0 + 36, font_sm, WHITE)
                    foot = "ENTER abrir gestión de grupo"
                else:  # Guardar
                    draw_text(screen, f"Guardar la partida en la ranura {slot}.",
                              pn.x + 16, cy0 + 36, font_sm, WHITE)
                    foot = "ENTER guardar"
                back_txt = ("B/ESC atrás" if (split and status_focus == "list")
                            else "B/ESC salir")
                draw_text(screen, foot + "  |  " + back_txt,
                          pn.x + 16, pn.bottom - 24, font_xs, GOLD)
            elif state == "pause":
                ov = pygame.Surface((W, H)); ov.set_alpha(150); ov.fill(BLACK)
                screen.blit(ov, (0, 0))
                draw_menu_panel("PAUSA", PAUSE_OPTS, pause_i,
                                "ENTER elegir | ESC/B volver")
            elif state == "dialog":
                dialog.draw()

            # mensaje (toast) SOBRE todos los menús
            if toast_t > 0:
                tb = pygame.Rect(W // 2 - 180, H - 40, 360, 26)
                pygame.draw.rect(screen, (40, 20, 20), tb, border_radius=6)
                pygame.draw.rect(screen, RED, tb, 2, border_radius=6)
                draw_text(screen, toast, tb.x + 12, tb.y + 6, font_xs, (255, 200, 200))

        # fundido de ENTRADA de la transición (sobre cualquier estado)
        if fade_t > 0:
            fade_t = max(0, fade_t - dt)
            ov = pygame.Surface((W, H)); ov.fill(BLACK)
            ov.set_alpha(int(255 * fade_t / FADE_MS))
            screen.blit(ov, (0, 0))

        present()


_JOY = None


def refresh_joystick():
    """(Re)detecta el mando: permite conectarlo/reconectarlo con el juego abierto."""
    global _JOY
    try:
        if pygame.joystick.get_count() == 0:
            _JOY = None
        elif _JOY is None or not _JOY.get_init():
            _JOY = pygame.joystick.Joystick(0)
            _JOY.init()
    except pygame.error:
        _JOY = None
    return _JOY


def main():
    load_opts()
    pygame.joystick.init()                 # activar mando ANTES del menú principal
    refresh_joystick()
    main_menu()


if __name__ == "__main__":
    main()
