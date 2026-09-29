"""rpg_sprites.py — sprites de personajes del RPG 2D de Nerea, 100% por código.

Todo se dibuja con primitivas de pygame en un espacio de "unidades" (figura de
100 u de alto, pies en y=100, centro en x=0), supermuestreado x4 y reducido con
smoothscale. Los OJOS y el CONTORNO se pintan después, ya a resolución final,
para que se lean nítidos a 32 px.

API (todas devuelven Surfaces SRCALPHA cacheadas; NO las modifiques):
    get_overworld(cid, facing="down", frame=0, possessed=False, color=None, seed=0)
        -> 32x48. Ancla: centro-abajo; los pies tocan y=46 (sombra incluida).
    get_portrait(cid, size=64, possessed=False, color=None, seed=0, framed=True)
        -> size x size (busto con fondo y marco; framed=False -> fondo transparente)
    get_battle(cid, possessed=False, frame=0, color=None, seed=0, size=64)
        -> size x size, pose idle (frame 0/1 = respiración)
    id_for(entity) -> (cid, possessed)   # traduce dicts de rpg.py (talkers/enemies/party)
    facing admite "down/up/left/right" o la tupla (fx, fy) de rpg.py.

ids: gris, fuego (Pyra), planta (Sylva), agua (Marina), tierra (Terra),
rayo (Electra), hielo (Gélida), blanco, negro, eco, mercader,
acolito_<elem>, aldeano, anciano, nina. Cualquier otro -> figura genérica
encapuchada teñida con `color`.
"""
import math
import random

import pygame

try:
    from gfx_utils import shade, lerp
except Exception:                                   # importado como games.rpg_sprites
    try:
        from games.gfx_utils import shade, lerp
    except Exception:
        def lerp(c1, c2, t):
            t = 0.0 if t < 0 else 1.0 if t > 1 else t
            return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))

        def shade(color, factor):
            return tuple(max(0, min(255, int(v * factor))) for v in color[:3])

__all__ = ["get_overworld", "get_portrait", "get_battle", "id_for", "CHAR_IDS",
           "OW_W", "OW_H", "OW_FEET", "clear_cache"]

SS = 4                       # supermuestreo
OW_W, OW_H, OW_FEET = 32, 48, 46
OW_K = 0.44                  # px por unidad en el overworld (figura ~44 px)

ELEM_COLOR = {"fuego": (220, 70, 50), "planta": (70, 180, 90),
              "agua": (70, 130, 220), "tierra": (210, 130, 50),
              "rayo": (235, 205, 70), "hielo": (160, 110, 220),
              "luz": (240, 240, 245), "sombra": (40, 40, 55),
              "neutro": (150, 150, 160)}

OUTLINE = (22, 16, 30)
SKIN = (238, 206, 174)

_CACHE = {}


def clear_cache():
    _CACHE.clear()


# ════════════════════════════════════════════════════════════════════════
#  PINTOR en unidades
# ════════════════════════════════════════════════════════════════════════
class _P:
    def __init__(self, surf, k, cx, feet):
        self.s, self.k, self.cx, self.fy = surf, k, cx, feet

    def pt(self, x, y):
        return (self.cx + x * self.k, self.fy + (y - 100) * self.k)

    def poly(self, pts, col):
        pygame.draw.polygon(self.s, col, [self.pt(x, y) for x, y in pts])

    def circ(self, x, y, r, col):
        pygame.draw.circle(self.s, col, self.pt(x, y), max(1, r * self.k))

    def ell(self, x, y, rx, ry, col):
        px, py = self.pt(x, y)
        pygame.draw.ellipse(self.s, col, pygame.Rect(
            px - rx * self.k, py - ry * self.k, 2 * rx * self.k, 2 * ry * self.k))

    def line(self, x1, y1, x2, y2, w, col):
        pygame.draw.line(self.s, col, self.pt(x1, y1), self.pt(x2, y2),
                         max(1, int(w * self.k)))

    def lines(self, pts, w, col):
        pygame.draw.lines(self.s, col, False, [self.pt(x, y) for x, y in pts],
                          max(1, int(w * self.k)))

    def ring(self, x, y, r, w, col):
        pygame.draw.circle(self.s, col, self.pt(x, y), max(1, r * self.k),
                           max(1, int(w * self.k)))

    def arc(self, x, y, r, a0, a1, w, col):
        px, py = self.pt(x, y)
        R = r * self.k
        pygame.draw.arc(self.s, col, pygame.Rect(px - R, py - R, 2 * R, 2 * R),
                        a0, a1, max(1, int(w * self.k)))


# ════════════════════════════════════════════════════════════════════════
#  PIEZAS COMUNES  (v = "front" | "back" | "side"; side mira a la IZQUIERDA)
# ════════════════════════════════════════════════════════════════════════
def _staff_x(c, v):
    return {"front": -(c["sw"] + 6), "back": c["sw"] + 6, "side": -11}[v]


def _feet(p, c, v, f, col):
    if v == "side":
        a, b = (-6, 3) if f == 0 else (-1, -1)
        p.ell(a, 98.5, 5, 2.4, col)
        p.ell(b + 2, 98.5, 5, 2.4, shade(col, 0.8))
    else:
        l, r = (99, 97.5) if f == 0 else (97.5, 99)
        p.ell(-5, l, 4.4, 2.5, col)
        p.ell(5, r, 4.4, 2.5, col)


def _robe(p, c, v, f, col, trim=None, hem=None, jag=0, trim_w=4):
    """Túnica trapezoidal. jag>0 = bajo dentado (llamas / harapos)."""
    hem = hem or c["hem"]
    sway = (1.5 if f == 0 else -1.5)
    sh, sw, hw = c["sh"], c["sw"], c["hw"]
    if v == "side":
        sw, hw = sw * 0.8, hw * 0.75
    top = [(-sw + 3, sh - 2), (sw - 3, sh - 2), (sw, sh + 3)]
    left = [(-sw, sh + 3)]
    if jag:
        n = 5
        bottom = []
        for i in range(n + 1):
            x = hw + sway - (2 * hw) * i / n
            bottom.append((x, hem + (0 if i % 2 == 0 else -jag)))
        pts = top + bottom + left
    else:
        pts = top + [(hw + sway, hem), (-hw + sway, hem)] + left
    p.poly(pts, col)
    if trim:
        t = trim_w
        p.poly([(hw * 0.92 + sway, hem - t), (hw + sway, hem),
                (-hw + sway, hem), (-hw * 0.92 + sway, hem - t)], trim)
    # sombreado lateral (volumen)
    p.poly([(sw * 0.35, sh), (sw, sh + 3), (hw + sway, hem - (jag or 0)),
            (hw * 0.45 + sway, hem - (jag or 0))], shade(col, 0.82))


def _arms(p, c, v, sleeve, hand, staff=True, hand_y=77):
    sx = _staff_x(c, v)
    if v == "side":
        p.line(-1, c["sh"] + 3, sx + 1, hand_y - 1, 6.5, sleeve)
        p.circ(sx, hand_y, 3.2, hand)
        return
    other = -sx if staff else -(c["sw"] + 4) * (1 if sx < 0 else -1)
    for x in (sx, other):
        sgn = 1 if x > 0 else -1
        p.line(sgn * (c["sw"] - 2), c["sh"] + 2, x, hand_y - 2, 6.5, sleeve)
        p.circ(x, hand_y, 3.2, hand)


def _staff(p, c, v, f, top, wood=(126, 92, 58), w=2.6):
    x = _staff_x(c, v)
    bob = 0 if f == 0 else 1
    p.line(x, 100, x, top + bob, w, wood)
    return x, top + bob


def _head(p, c, v, skin, hair):
    hy, hr = c["hy"], c["hr"]
    if v == "back":
        p.circ(0, hy, hr, hair)
    elif v == "side":
        p.circ(0.5, hy, hr, hair)
        p.ell(-hr * 0.2, hy + hr * 0.12, hr * 0.8, hr * 0.84, skin)
        p.poly([(-hr * 0.95, hy + 1), (-hr * 1.12, hy + 4.5), (-hr * 0.9, hy + 5.5)], skin)
    else:
        p.circ(0, hy, hr, skin)
        # mejillas: leve sombra inferior
        p.ell(0, hy + hr * 0.62, hr * 0.62, hr * 0.28, shade(skin, 0.94))


def _bangs(p, c, v, col, drop=0.25, tufts=4):
    """Flequillo: casquete sobre la mitad superior de la cabeza con borde ondulado."""
    hy, hr = c["hy"], c["hr"]
    if v == "back":
        return
    r = hr + 1.2
    arc = [(math.cos(a) * r, hy + math.sin(a) * r)
           for a in [math.pi + i * math.pi / 12 for i in range(13)]]
    edge_y = hy - hr * drop
    if v == "side":
        pts = [(x, y) for x, y in arc]
        pts += [(hr * 0.9, hy + hr * 0.6), (hr * 0.2, hy + hr * 0.3),
                (-hr * 0.2, edge_y + 2), (-hr * 0.6, edge_y - 1), (-hr * 1.02, edge_y + 1)]
        p.poly(pts, col)
        return
    edge = []
    for i in range(tufts * 2 + 1):
        x = hr * 1.05 - (2.1 * hr) * i / (tufts * 2)
        edge.append((x, edge_y + (3.2 if i % 2 else 0) + (hr * 0.5 if i in (0, tufts * 2) else 0)))
    p.poly(arc + edge, col)


def _long_hair(p, c, v, col, length=80, width=None):
    hy, hr = c["hy"], c["hr"]
    w = width or hr + 2.5
    if v == "side":
        p.poly([(-2, hy - hr * 0.6), (hr + 1.5, hy - hr * 0.4), (hr * 0.9 + 3, length),
                (1, length - 3)], col)
    else:
        p.poly([(-w, hy), (w, hy), (w + 1.5, length - 3), (w * 0.4, length),
                (-w * 0.4, length), (-w - 1.5, length - 3)], col)
        p.circ(0, hy, hr + 1.5, col)


# ════════════════════════════════════════════════════════════════════════
#  PERSONAJES — cada uno es una función (stage, p, v, f, pal, c, d)
#   stages: "behind" (antes de todo) · "body" (túnica/brazos/arma) ·
#           "head" (cabeza+pelo) · "top" (sombrero/corona, lo último)
#   d = detalle: 0 overworld, 1 combate, 2 retrato
# ════════════════════════════════════════════════════════════════════════
BASE = {"hy": 44, "hr": 15, "sh": 58, "sw": 11, "hw": 18, "hem": 96, "st": 34}


def _gris(stage, p, v, f, P, c, d):
    """Mago Gris: sombrero puntiagudo con la punta doblada (su firma) y báculo
    con orbe mitad blanco / mitad negro: está entre la Luz y la Sombra."""
    if stage == "behind":
        # capa corta de viaje (hombros más anchos que la túnica)
        if v != "back":
            p.poly([(-c["sw"] - 3, c["sh"] + 1), (c["sw"] + 3, c["sh"] + 1),
                    (c["hw"] + 3, 82), (-c["hw"] - 3, 82)], P["cape"])
    elif stage == "body":
        _feet(p, c, v, f, P["boots"])
        _robe(p, c, v, f, P["robe"], P["trim"])
        if v == "back":
            p.poly([(-c["sw"] - 3, c["sh"] - 1), (c["sw"] + 3, c["sh"] - 1),
                    (c["hw"] + 2, 84), (0, 88), (-c["hw"] - 2, 84)], P["cape"])
        else:
            p.poly([(-c["sw"] - 3, c["sh"] - 1), (c["sw"] + 3, c["sh"] - 1),
                    (c["sw"] + 5, c["sh"] + 8), (0, c["sh"] + 12),
                    (-c["sw"] - 5, c["sh"] + 8)], P["cape"])          # esclavina
            if v == "front":
                p.line(-7, 74, 7, 74, 2.4, P["belt"])
        sx, top = _staff(p, c, v, f, 28)
        # orbe bicolor
        p.circ(sx, top, 5.2, P["orb_d"])
        p.poly([(sx, top - 5.2), (sx + 5.2, top), (sx, top + 5.2)] if v != "side"
               else [(sx, top - 5.2), (sx - 5.2, top), (sx, top + 5.2)], P["orb_l"])
        p.ring(sx, top, 5.4, 1.1, P["band"])
        _arms(p, c, v, P["robe_d"], P["skin"])
    elif stage == "head":
        _head(p, c, v, P["skin"], P["hair"])
        _bangs(p, c, v, P["hair"], drop=0.3, tufts=3)
    elif stage == "top":
        hy, hr = c["hy"], c["hr"]
        by = hy - hr * 0.55
        tipdir = 1 if v != "side" else 1          # la punta cae hacia atrás
        p.poly([(-hr + 0.5, by), (hr - 0.5, by), (4, 12), (0, 9)], P["hat"])
        p.poly([(4, 12), (0, 9), (9 * tipdir, 5), (16 * tipdir, 11), (11 * tipdir, 13)],
               P["hat_d"])                                        # punta doblada
        p.circ(16 * tipdir, 11.5, 2.2, P["band"])
        rx = hr + 9 if v != "side" else hr + 7
        p.ell(0, by + 0.5, rx, 4, P["hat_d"])
        p.poly([(-hr + 1.5, by - 1), (hr - 1.5, by - 1), (hr - 2.5, by - 4.5),
                (-hr + 2.5, by - 4.5)], P["band"])


def _blanco(stage, p, v, f, P, c, d):
    """Mago Blanco: mitra alta, halo dorado, barba larga — noble. Lo inquietante:
    el halo tiene una GRIETA oscura, su sombra es violeta y más grande de lo
    normal, y en el retrato sus pupilas son rendijas doradas."""
    hy, hr = c["hy"], c["hr"]
    if stage == "behind":
        if v != "back":
            hx, hyy = 0, hy - 8
            p.ring(hx, hyy, 23, 2.4, P["gold"])
            # grieta: un tajo oscuro que interrumpe el halo
            a = -0.55
            x1, y1 = math.cos(a) * 21.5, hyy + math.sin(a) * 21.5
            x2, y2 = math.cos(a) * 25, hyy + math.sin(a) * 25
            p.line(x1, y1, x2, y2, 3.4, P["crack"])
            p.line(x2, y2, x2 + 2.5, y2 - 1.5, 1.4, P["crack"])
        # manto largo que roza el suelo
        if v != "back":
            p.poly([(-c["sw"] - 4, c["sh"]), (c["sw"] + 4, c["sh"]),
                    (c["hw"] + 5, 99), (-c["hw"] - 5, 99)], P["mantle"])
    elif stage == "body":
        _feet(p, c, v, f, P["boots"])
        _robe(p, c, v, f, P["robe"], P["gold"], trim_w=3.5)
        if v == "front":
            p.poly([(-3.5, c["sh"]), (3.5, c["sh"]), (4.5, c["hem"]),
                    (-4.5, c["hem"])], P["gold"])                     # estola dorada
            p.poly([(-2, c["sh"]), (2, c["sh"]), (3, c["hem"]), (-3, c["hem"])], P["robe"])
        if v == "back":
            p.poly([(-c["sw"] - 4, c["sh"] - 1), (c["sw"] + 4, c["sh"] - 1),
                    (c["hw"] + 5, 99), (-c["hw"] - 5, 99)], P["mantle"])
            p.ring(0, hy - 8, 23, 2.4, P["gold"])
        sx, top = _staff(p, c, v, f, 22, wood=P["gold_d"], w=2.8)
        # disco solar con rayos
        for i in range(8):
            a = i * math.pi / 4
            p.line(sx, top, sx + math.cos(a) * 8.5, top + math.sin(a) * 8.5, 1.6, P["gold"])
        p.circ(sx, top, 5, P["gold"])
        p.circ(sx, top, 3, P["sun"])
        _arms(p, c, v, P["robe_d"], P["skin"])
    elif stage == "head":
        _head(p, c, v, P["skin"], P["hair"])
        if v != "back":
            # barba larga y noble
            bx = -3 if v == "side" else 0
            p.poly([(bx - hr * 0.8, hy + 3), (bx + hr * 0.8, hy + 3),
                    (bx + hr * 0.55, hy + 16), (bx, hy + 27), (bx - hr * 0.55, hy + 16)],
                   P["beard"])
            p.ell(bx, hy + 5, hr * 0.5, 2.2, P["beard_d"])            # bigote
            if v == "front":                                            # patillas
                for s in (-1, 1):
                    p.poly([(s * (hr + 0.5), hy - 3), (s * (hr - 3), hy - 3),
                            (s * (hr - 2), hy + 8), (s * (hr + 1), hy + 6)], P["hair"])
    elif stage == "top":
        by = hy - hr * 0.5
        w = hr - 1 if v != "side" else hr - 2
        p.poly([(-w, by), (w, by), (w - 1, by - 14), (0, 3), (-w + 1, by - 14)], P["robe"])
        p.poly([(-w, by), (w, by), (w, by - 3.5), (-w, by - 3.5)], P["gold"])
        if v != "back":
            p.poly([(-2, by - 3), (2, by - 3), (1.5, 8), (0, 5), (-1.5, 8)], P["gold"])
            p.circ(0, by - 11, 2.6, P["gold"])
        if v == "back":
            p.ring(0, hy - 8, 23, 2.4, P["gold"])


def _negro(stage, p, v, f, P, c, d):
    """Mago Negro: capucha con cuernos y hombreras de púas (la silueta más ancha
    del juego). Tirano trágico: en retrato y combate, hilos pálidos de títere
    le suben de las muñecas y una lágrima luminosa le cae del ojo."""
    hy, hr, sh, sw = c["hy"], c["hr"], c["sh"], c["sw"]
    if stage == "behind":
        if d >= 1 and v == "front":                # hilos de marioneta (sutiles)
            for x0, y0, x1 in ((-(sw + 6), 76, -17), (sw + 6, 76, 15), (0, 30, 2)):
                p.line(x0, y0, x1, -40, 0.5, P["string"])
        if v != "back":
            p.poly([(-sw - 4, sh), (sw + 4, sh), (c["hw"] + 6, 99), (c["hw"] - 2, 93),
                    (6, 99), (-2, 93), (-9, 99), (-c["hw"] + 1, 94),
                    (-c["hw"] - 6, 99)], P["cape"])
    elif stage == "body":
        _feet(p, c, v, f, P["boots"])
        _robe(p, c, v, f, P["robe"], None, jag=4)
        if v == "back":
            p.poly([(-sw - 5, sh - 2), (sw + 5, sh - 2), (c["hw"] + 6, 99),
                    (c["hw"] - 2, 93), (6, 99), (-2, 93), (-9, 99),
                    (-c["hw"] + 1, 94), (-c["hw"] - 6, 99)], P["cape"])
        if v == "front":
            p.poly([(-2.5, sh + 3), (2.5, sh + 3), (0, sh + 11)], P["glow"])   # gema
        _arms(p, c, v, P["robe_d"], P["hand"], staff=False, hand_y=78)
        # hombreras de púas
        if v == "side":
            p.poly([(-9, sh - 3), (8, sh - 3), (10, sh + 6), (-10, sh + 6)], P["armor"])
            p.poly([(-4, sh - 3), (1, sh - 3), (-2, sh - 13)], P["armor_l"])
        else:
            for s in (-1, 1):
                x = s * (sw + 3)
                p.ell(x, sh + 2, 9, 6, P["armor"])
                p.poly([(x - 4, sh - 1), (x + 1 * s, sh - 1), (x + 7 * s, sh - 14)],
                       P["armor_l"])
                p.poly([(x + 3 * s, sh), (x + 8 * s, sh + 1), (x + 14 * s, sh - 7)],
                       P["armor_l"])
    elif stage == "head":
        # capucha (la cabeza es sobre todo sombra)
        p.circ(0, hy - 1, hr + 3, P["hood"])
        if v != "back":
            fx = -3 if v == "side" else 0
            p.ell(fx, hy + 2, hr * 0.72, hr * 0.8, P["void"])
            p.ell(fx, hy + 5, hr * 0.55, hr * 0.5, P["face"])          # rostro demacrado
        # cuernos
        for s in ((-1, 1) if v != "side" else (1,)):
            b = s * 9 if v != "side" else 7
            p.poly([(b - 3 * s, hy - 11), (b + 3 * s, hy - 8), (b + 13 * s, hy - 22),
                    (b + 11 * s, hy - 30), (b + 8 * s, hy - 21)], P["horn"])
    elif stage == "top":
        pass


def _maga_staff_top(p, sx, top, kind, P, v):
    if kind == "torch":
        p.poly([(sx - 3, top + 3), (sx + 3, top + 3), (sx + 2, top + 6), (sx - 2, top + 6)],
               P["metal"])
        p.poly([(sx - 4, top + 3), (sx - 5, top - 4), (sx - 1, top - 1), (sx, top - 10),
                (sx + 2, top - 2), (sx + 5, top - 6), (sx + 4, top + 3)], P["flame"])
        p.poly([(sx - 2, top + 2), (sx, top - 5), (sx + 2, top + 2)], P["flame_c"])


def _pyra(stage, p, v, f, P, c, d):
    """Pyra (fuego, la que más pega, impulsiva): melena de llamas hacia arriba,
    sin sombrero; falda corta de bajo dentado y antorcha-varita."""
    hy, hr = c["hy"], c["hr"]
    if stage == "behind":
        # llamas del pelo por detrás (la silueta)
        p.poly([(-hr - 2, hy + 4), (-hr - 7, hy - 8), (-hr + 1, hy - 7),
                (-hr - 3, hy - 22), (-5, hy - 15), (-3, hy - 31), (3, hy - 17),
                (8, hy - 28), (9, hy - 14), (hr + 6, hy - 20), (hr + 1, hy - 6),
                (hr + 7, hy - 4), (hr + 2, hy + 6)], P["hair"])
        p.poly([(-5, hy - 12), (-2, hy - 25), (2, hy - 13), (7, hy - 22),
                (7, hy - 10)], P["hair_l"])
    elif stage == "body":
        # piernas visibles (falda corta)
        _feet(p, c, v, f, P["boots"])
        if v != "side":
            p.line(-5, 88, -5, 97, 4, P["legs"])
            p.line(5, 88, 5, 97, 4, P["legs"])
        else:
            p.line(-3, 88, -3, 97, 4, P["legs"])
        _robe(p, c, v, f, P["robe"], P["trim"], hem=90, jag=4)
        if v == "front":
            p.poly([(-9, 72), (9, 72), (8, 76), (-8, 76)], P["sash"])
            p.poly([(6, 74), (11, 84), (7, 85)], P["sash"])
        sx, top = _staff(p, c, v, f, 44)
        _maga_staff_top(p, sx, top, "torch", P, v)
        _arms(p, c, v, P["robe_d"], P["skin"])
    elif stage == "head":
        _head(p, c, v, P["skin"], P["hair"])
        if v == "back":
            p.poly([(-hr, hy), (hr, hy), (hr - 2, hy + 12), (0, hy + 16), (-hr + 2, hy + 12)],
                   P["hair"])
        _bangs(p, c, v, P["hair"], drop=0.18, tufts=3)
        if v == "front":
            p.poly([(-4, hy - hr - 1), (0, hy - hr - 8), (3, hy - hr)], P["hair_l"])


def _sylva(stage, p, v, f, P, c, d):
    """Sylva (planta, aguante, sanadora serena): sombrero de hoja muy ancho y
    plano con un brote, melena larga y cayado de madera enroscado."""
    hy, hr = c["hy"], c["hr"]
    if stage == "behind":
        _long_hair(p, c, v, P["hair"], length=84, width=hr + 3)
    elif stage == "body":
        _feet(p, c, v, f, P["boots"])
        _robe(p, c, v, f, P["robe"], P["trim"])
        if v == "back":
            _long_hair(p, c, v, P["hair"], length=84, width=hr + 3)
        if v == "front":
            p.lines([(-10, 71), (-4, 74), (3, 71), (10, 74)], 2, P["vine"])
            p.circ(-4, 74, 1.8, P["flower"])
        sx, top = _staff(p, c, v, f, 30, wood=P["wood"], w=3)
        s = 1 if v == "back" else -1                 # el cayado se enrosca hacia fuera
        p.arc(sx + 4 * s, top, 4.5, 0, math.pi, 2.6, P["wood"])
        p.line(sx + 8.5 * s, top, sx + 8 * s, top + 3.5, 2.4, P["wood"])
        p.ell(sx + 9 * s, top + 5, 2.2, 3.2, P["leaf"])
        _arms(p, c, v, P["robe_d"], P["skin"])
    elif stage == "head":
        _head(p, c, v, P["skin"], P["hair"])
        _bangs(p, c, v, P["hair"], drop=0.1, tufts=2)
    elif stage == "top":
        by = hy - hr * 0.55
        rx = 27 if v != "side" else 24
        p.ell(0, by + 1, rx, 6, P["hat_d"])
        p.ell(0, by - 0.5, rx - 1, 4.5, P["hat"])
        # nervios de la hoja
        p.line(-rx + 3, by, rx - 3, by, 0.9, P["hat_d"])
        p.ell(0, by - 4, 10, 6.5, P["hat"])
        p.line(0, by - 9, 0, by - 16, 1.6, P["stem"])
        p.ell(-3.5, by - 15, 3.5, 1.8, P["leaf"])
        p.ell(3.5, by - 17, 3.5, 1.8, P["leaf"])
        if v != "back":
            p.circ(9, by - 2, 2.8, P["flower"])
            p.circ(9, by - 2, 1.1, P["flower_c"])


def _marina(stage, p, v, f, P, c, d):
    """Marina (agua, ágil y sanadora): coleta alta que se enrosca como una ola
    hacia un lado, diadema de conchas y tridente."""
    hy, hr = c["hy"], c["hr"]
    side = 1 if v != "back" else -1
    if stage == "behind":
        # la OLA: coleta que sube y rompe hacia un lado
        p.poly([(2 * side, hy - hr + 1), (hr * side, hy - hr - 6),
                ((hr + 10) * side, hy - 14), ((hr + 8) * side, hy + 6),
                ((hr + 3) * side, hy + 22), ((hr - 2) * side, hy + 6), (hr * 0.6 * side, hy)],
               P["hair"])
        p.circ((hr + 5) * side, hy - 12, 8.5, P["hair"])
        p.circ((hr + 6) * side, hy - 11, 4.5, P["hair_l"])
        p.circ((hr + 7) * side, hy - 10.5, 2.2, P["hair"])
    elif stage == "body":
        _feet(p, c, v, f, P["boots"])
        _robe(p, c, v, f, P["robe"], None)
        # bajo con ondas blancas
        hem, hw = c["hem"], c["hw"] * (0.75 if v == "side" else 1)
        for i in range(4):
            x = -hw + 4 + i * (2 * hw - 8) / 3
            p.arc(x, hem - 1, 3.5, 0, math.pi, 1.4, P["foam"])
        if v == "front":
            p.poly([(-8, 71), (8, 71), (7, 74), (-7, 74)], P["trim"])
        sx, top = _staff(p, c, v, f, 28, wood=P["metal_d"], w=2.4)
        p.lines([(sx - 5, top - 3), (sx - 5, top + 3), (sx + 5, top + 3), (sx + 5, top - 3)],
                1.8, P["metal"])
        p.line(sx, top + 3, sx, top - 6, 1.8, P["metal"])
        for x in (sx - 5, sx, sx + 5):
            p.poly([(x - 1.5, top - 2 - (3 if x == sx else 0)), (x + 1.5, top - 2 - (3 if x == sx else 0)),
                    (x, top - 6 - (3 if x == sx else 0))], P["metal"])
        _arms(p, c, v, P["robe_d"], P["skin"])
    elif stage == "head":
        _head(p, c, v, P["skin"], P["hair"])
        if v == "front":        # flequillo de lado
            r = hr + 1.2
            arc = [(math.cos(a) * r, hy + math.sin(a) * r)
                   for a in [math.pi + i * math.pi / 12 for i in range(13)]]
            p.poly(arc + [(hr, hy - 2), (2, hy - hr * 0.35), (-6, hy - 1), (-hr - 1, hy + 4)],
                   P["hair"])
        else:
            _bangs(p, c, v, P["hair"], drop=0.2)
        if v != "back":         # diadema de conchas
            for i, x in enumerate((-8, 0, 8) if v == "front" else (-9, -3)):
                y = hy - hr + 3 + (0 if x == 0 else 2)
                p.circ(x, y, 2.2 if x == 0 else 1.6, P["shell"])


def _terra(stage, p, v, f, P, c, d):
    """Terra (tierra, la más resistente y lenta): cuerpo ancho y bajo, hombreras
    de roca, trenzas gruesas y un mazo de piedra enorme."""
    hy, hr, sh, sw = c["hy"], c["hr"], c["sh"], c["sw"]
    if stage == "behind":
        pass
    elif stage == "body":
        _feet(p, c, v, f, P["boots"])
        _robe(p, c, v, f, P["robe"], P["trim"], trim_w=5)
        if v == "front":
            p.poly([(-sw - 1, 73), (sw + 1, 73), (sw + 2, 78), (-sw - 2, 78)], P["belt"])
            p.poly([(-3, 73), (3, 73), (3, 78), (-3, 78)], P["gem"])
        # MAZO: mango grueso + bloque de piedra
        x = _staff_x(c, v)
        bob = 0 if f == 0 else 1
        p.line(x, 99, x, 44 + bob, 3.6, P["wood"])
        p.poly([(x - 8, 32 + bob), (x + 8, 32 + bob), (x + 9, 44 + bob),
                (x - 9, 44 + bob)], P["stone"])
        p.poly([(x - 8, 32 + bob), (x + 8, 32 + bob), (x + 6, 35 + bob),
                (x - 6, 35 + bob)], P["stone_l"])
        p.line(x - 9, 40 + bob, x + 9, 40 + bob, 1.5, P["stone_d"])
        _arms(p, c, v, P["robe_d"], P["skin"], hand_y=74)
        # hombreras de roca
        if v == "side":
            p.ell(0, sh + 1, 8, 5.5, P["stone"])
        else:
            for s in (-1, 1):
                p.ell(s * (sw + 1), sh + 1, 7.5, 5.5, P["stone"])
                p.ell(s * (sw + 0), sh - 1, 4.5, 2.5, P["stone_l"])
    elif stage == "head":
        _head(p, c, v, P["skin"], P["hair"])
        if v == "back":
            p.line(-5, hy + 6, -6, hy + 22, 5, P["hair"])
            p.line(5, hy + 6, 6, hy + 22, 5, P["hair"])
        _bangs(p, c, v, P["hair"], drop=0.35, tufts=2)
        if v != "back":         # cinta con gema
            p.poly([(-hr, hy - hr * 0.42), (hr, hy - hr * 0.42), (hr, hy - hr * 0.2),
                    (-hr, hy - hr * 0.2)] if v == "front" else
                   [(-hr, hy - hr * 0.45), (hr * 0.9, hy - hr * 0.45),
                    (hr * 0.9, hy - hr * 0.2), (-hr, hy - hr * 0.2)], P["band"])
            p.circ(0 if v == "front" else -hr + 3, hy - hr * 0.31, 1.9, P["gem"])
        if v == "front":        # trenzas gruesas por delante
            for s in (-1, 1):
                for i in range(4):
                    p.circ(s * (hr - 1), hy + 3 + i * 4.2, 3 - i * 0.2, P["hair"])
                p.circ(s * (hr - 1), hy + 19, 1.8, P["band"])


def _electra(stage, p, v, f, P, c, d):
    """Electra (rayo, la más veloz y precisa, la más frágil): figura fina,
    coletas en zigzag como relámpagos, gafas de precisión y varilla fina."""
    hy, hr = c["hy"], c["hr"]
    if stage == "behind":
        sides = (-1, 1) if v != "side" else (1,)
        for s in sides:
            x0 = s * (hr - 2) if v != "side" else 6
            pts = [(x0, hy - 9), (x0 + 9 * s, hy - 4), (x0 + 3 * s, hy + 3),
                   (x0 + 12 * s, hy + 10), (x0 + 6 * s, hy + 14),
                   (x0 + 13 * s, hy + 26), (x0 + 2 * s, hy + 13),
                   (x0 + 7 * s, hy + 10), (x0 - 1 * s, hy + 2), (x0 + 3 * s, hy - 2)]
            p.poly(pts, P["hair"])
            p.circ(x0, hy - 8, 2.4, P["tie"])
    elif stage == "body":
        _feet(p, c, v, f, P["boots"])
        _robe(p, c, v, f, P["robe"], None)
        if v == "front":        # franja de rayo
            p.lines([(-3, c["sh"] + 2), (2, c["sh"] + 12), (-2, c["sh"] + 16),
                     (3, c["hem"] - 2)], 2.4, P["stripe"])
        if v == "back":
            _electra("behind", p, "front", f, P, c, d)
        sx, top = _staff(p, c, v, f, 30, wood=P["metal"], w=1.8)
        p.poly([(sx - 1, top - 1), (sx + 4, top - 7), (sx + 1, top - 7),
                (sx + 5, top - 13), (sx - 3, top - 5), (sx, top - 5), (sx - 3, top)],
               P["bolt"])
        _arms(p, c, v, P["robe_d"], P["skin"])
    elif stage == "head":
        _head(p, c, v, P["skin"], P["hair"])
        _bangs(p, c, v, P["hair"], drop=0.3, tufts=3)
        if v != "back":         # gafas subidas sobre la frente
            if v == "front":
                p.line(-hr, hy - hr * 0.48, hr, hy - hr * 0.48, 2.4, P["goggle"])
                for s in (-1, 1):
                    p.circ(s * 5, hy - hr * 0.5, 3.4, P["goggle"])
                    p.circ(s * 5, hy - hr * 0.5, 2.2, P["lens"])
            else:
                p.line(-hr, hy - hr * 0.5, hr * 0.8, hy - hr * 0.5, 2.4, P["goggle"])
                p.circ(-hr + 3, hy - hr * 0.5, 3.2, P["goggle"])
                p.circ(-hr + 3, hy - hr * 0.5, 2, P["lens"])
        else:
            p.line(-hr, hy - hr * 0.48, hr, hy - hr * 0.48, 2.4, P["goggle"])


def _gelida(stage, p, v, f, P, c, d):
    """Gélida (hielo, la de más maná): corona de carámbanos altos y finos,
    melena lisa hasta la cintura y capa larga en triángulo; báculo con cristal."""
    hy, hr = c["hy"], c["hr"]
    if stage == "behind":
        if v != "back":
            p.poly([(-c["sw"] - 2, c["sh"] - 1), (c["sw"] + 2, c["sh"] - 1),
                    (c["hw"] + 8, 99), (-c["hw"] - 8, 99)], P["cape"])
        _long_hair(p, c, v, P["hair"], length=80, width=hr + 1.5)
    elif stage == "body":
        _feet(p, c, v, f, P["boots"])
        _robe(p, c, v, f, P["robe"], P["frost"])
        if v == "back":
            p.poly([(-c["sw"] - 3, c["sh"] - 2), (c["sw"] + 3, c["sh"] - 2),
                    (c["hw"] + 8, 99), (-c["hw"] - 8, 99)], P["cape"])
            _long_hair(p, c, v, P["hair"], length=80, width=hr + 1.5)
            for i in range(3):
                p.circ(-8 + i * 8, 92, 1.4, P["frost"])
        if v == "front":        # copo en el pecho
            cx, cy = 0, c["sh"] + 8
            for i in range(3):
                a = i * math.pi / 3
                p.line(cx - math.cos(a) * 3.5, cy - math.sin(a) * 3.5,
                       cx + math.cos(a) * 3.5, cy + math.sin(a) * 3.5, 1.2, P["frost"])
        sx, top = _staff(p, c, v, f, 24, wood=P["wood"], w=2.4)
        p.poly([(sx, top - 11), (sx + 4.5, top - 2), (sx, top + 4), (sx - 4.5, top - 2)],
               P["crystal"])
        p.poly([(sx, top - 11), (sx + 4.5, top - 2), (sx, top - 1)], P["crystal_l"])
        _arms(p, c, v, P["robe_d"], P["skin"])
    elif stage == "head":
        _head(p, c, v, P["skin"], P["hair"])
        _bangs(p, c, v, P["hair"], drop=0.2, tufts=4)
        if v == "front":
            for s in (-1, 1):
                p.poly([(s * (hr - 3), hy - 5), (s * (hr + 1.5), hy - 5),
                        (s * (hr + 1), hy + 14), (s * (hr - 3), hy + 10)], P["hair"])
    elif stage == "top":
        by = hy - hr + 2
        w = 1 if v != "side" else 0.8
        spikes = [(-9, 17), (-4.5, 10), (0, 4), (4.5, 10), (9, 17)]
        for x, t in spikes:
            x *= w
            p.poly([(x - 2.4, by + 1), (x + 2.4, by + 1), (x, t)], P["crown"])
            p.line(x - 0.6, by, x - 0.2, t + 3, 0.8, P["crown_l"])
        p.poly([(-11 * w, by + 3), (11 * w, by + 3), (10 * w, by - 1), (-10 * w, by - 1)],
               P["crown"])
        if v != "back":
            p.circ(0, by + 1, 1.6, P["crown_l"])


def _acolito(stage, p, v, f, P, c, d):
    """Acólito: esbirro encapuchado. Misma silueta para todos los elementos (el
    color los agrupa); más bajo que las magas, sin arma, cara en sombra."""
    hy, hr = c["hy"], c["hr"]
    if stage == "body":
        _feet(p, c, v, f, P["boots"])
        _robe(p, c, v, f, P["robe"], None, jag=3)
        if v == "front":
            p.ell(0, 74, 7, 4, P["robe_d"])                 # manos en las mangas
            p.poly([(0, 60), (3, 64), (0, 68), (-3, 64)], P["emblem"])
        elif v == "side":
            p.ell(-6, 73, 5, 4, P["robe_d"])
    elif stage == "head":
        tip = 9 if v != "side" else 14
        p.poly([(-hr - 1, hy + 2), (hr + 1, hy + 2), (tip, hy - hr - 9),
                (tip - 7, hy - hr - 2)], P["robe"])
        p.circ(0, hy, hr + 1.5, P["robe"])
        if v != "back":
            fx = -3 if v == "side" else 0
            p.ell(fx, hy + 2.5, hr * 0.7, hr * 0.72, P["void"])
        p.poly([(-hr - 2, hy + 8), (hr + 2, hy + 8), (hr, hy + 14), (-hr, hy + 14)],
               P["robe_d"])                                 # cuello de la capucha


def _mercader(stage, p, v, f, P, c, d):
    """Mercader: sombrero flexible de ala ancha, barriga y una mochila enorme
    que asoma por encima de los hombros. Nada de magia."""
    hy, hr = c["hy"], c["hr"]
    if stage == "behind":
        if v != "back":
            p.poly([(-17, 50), (17, 50), (18, 84), (-18, 84)], P["pack"])
            p.ell(0, 48, 17, 5.5, P["roll"])
            p.line(-14, 48, 14, 48, 1, P["roll_d"])
    elif stage == "body":
        _feet(p, c, v, f, P["boots"])
        _robe(p, c, v, f, P["robe"], P["trim"])
        if v == "front":
            p.ell(0, 76, 12, 9, P["robe_l"])                # barriga
            p.line(-12, 72, 12, 72, 2.2, P["belt"])
            p.circ(8, 78, 3, P["purse"])
        if v == "back":
            p.poly([(-17, 50), (17, 50), (18, 86), (-18, 86)], P["pack"])
            p.poly([(-12, 64), (12, 64), (12, 78), (-12, 78)], P["pack_d"])
            p.ell(0, 48, 17, 5.5, P["roll"])
        if v == "side":
            p.poly([(4, 52), (20, 52), (21, 86), (6, 86)], P["pack"])
            p.ell(12, 49, 9, 5, P["roll"])
        _arms(p, c, v, P["robe_d"], P["skin"], staff=False)
    elif stage == "head":
        _head(p, c, v, P["skin"], P["hair"])
        if v != "back":
            mx = -3 if v == "side" else 0
            p.ell(mx - 3.5, hy + 5, 4.5, 2, P["hair"])
            p.ell(mx + 3.5, hy + 5, 4.5, 2, P["hair"])
    elif stage == "top":
        by = hy - hr * 0.45
        p.ell(0, by + 1, 23, 5.5, P["hat_d"])
        p.poly([(-11, by), (11, by), (9, by - 11), (-9, by - 11)], P["hat"])
        p.ell(0, by - 11, 9, 3, P["hat"])
        p.line(-11, by - 2, 11, by - 2, 2.2, P["band"])


# ── aldeanos (variación por semilla estable) ─────────────────────────────
_VILL_CLOTH = [(150, 110, 80), (120, 130, 95), (110, 120, 140), (160, 140, 110),
               (140, 95, 95), (100, 115, 110), (170, 150, 120), (125, 105, 130)]
_VILL_SKIN = [(238, 206, 174), (222, 180, 140), (196, 150, 110), (150, 108, 78)]
_VILL_HAIR = [(70, 50, 36), (40, 32, 28), (150, 110, 60), (190, 180, 170), (110, 70, 40)]


def _aldeano(stage, p, v, f, P, c, d):
    """Aldeano: deliberadamente sencillo y apagado. Túnica corta, pantalón,
    un complemento como mucho (gorro, pañuelo o sombrero de paja)."""
    hy, hr = c["hy"], c["hr"]
    acc = c.get("acc", "none")
    if stage == "behind":
        if acc == "bun" and v != "front":
            p.circ(0, hy - hr + 1, 5, P["hair"])
        if acc == "long":
            _long_hair(p, c, v, P["hair"], length=70, width=hr + 1)
    elif stage == "body":
        _feet(p, c, v, f, P["boots"])
        if v != "side":
            p.line(-5, 86, -5, 97, 4.5, P["legs"])
            p.line(5, 86, 5, 97, 4.5, P["legs"])
        else:
            p.line(-2, 86, -2, 97, 5, P["legs"])
        _robe(p, c, v, f, P["robe"], None, hem=c.get("tunic", 88))
        if v == "front":
            p.line(-c["sw"] + 1, 74, c["sw"] - 1, 74, 2, P["belt"])
        if c.get("cane"):
            x, top = _staff(p, c, v, f, 66, wood=P["wood"], w=2.4)
            p.arc(x + 3 if v != "back" else x - 3, top, 3, 0, math.pi, 2, P["wood"])
        _arms(p, c, v, P["robe_d"], P["skin"], staff=bool(c.get("cane")))
    elif stage == "head":
        _head(p, c, v, P["skin"], P["hair"])
        if acc == "bald":
            if v != "back":
                p.ell(-hr + 1, hy - 1, 2.5, 4, P["hair"]) if v == "front" else None
                p.ell(hr - 1, hy - 1, 2.5, 4, P["hair"])
                p.poly([(-hr * 0.7, hy + 4), (hr * 0.7, hy + 4), (0, hy + 14)], P["hair"])
        elif acc == "pigtails":
            _bangs(p, c, v, P["hair"], drop=0.2, tufts=3)
            for s in ((-1, 1) if v != "side" else (1,)):
                p.circ(s * (hr + 2), hy - 2, 4, P["hair"])
                p.circ(s * (hr + 2), hy - 6, 1.6, P["tie"])
        else:
            _bangs(p, c, v, P["hair"], drop=0.35, tufts=3)
            if acc == "bun" and v == "front":
                p.circ(0, hy - hr - 1, 4.5, P["hair"])
    elif stage == "top":
        by = hy - hr * 0.5
        if acc == "straw":
            p.ell(0, by + 1, 20, 4.5, P["straw_d"])
            p.ell(0, by - 3, 10, 6, P["straw"])
            p.line(-10, by - 1, 10, by - 1, 1.6, P["band"])
        elif acc == "cap":
            p.ell(0, hy - hr * 0.55, hr + 1, hr * 0.62, P["hat"])
            if v == "front":
                p.ell(0, hy - hr * 0.3, hr * 0.8, 2.2, P["hat_d"])
            elif v == "side":
                p.ell(-hr * 0.9, hy - hr * 0.35, 5, 2, P["hat_d"])
        elif acc == "scarf":
            p.circ(0, hy - 2, hr + 1.3, P["hat"]) if v == "back" else \
                p.poly([(math.cos(a) * (hr + 1.3), hy + math.sin(a) * (hr + 1.3))
                        for a in [math.pi * 0.95 + i * math.pi * 1.1 / 12 for i in range(13)]],
                       P["hat"])
            if v != "back":
                p.poly([(hr * 0.6, hy - 6), (hr + 3, hy + 2), (hr - 1, hy + 4)], P["hat_d"])


def _generico(stage, p, v, f, P, c, d):
    """Figura genérica encapuchada para ids desconocidos (se tiñe con `color`)."""
    hy, hr = c["hy"], c["hr"]
    if stage == "body":
        _feet(p, c, v, f, P["boots"])
        _robe(p, c, v, f, P["robe"], P["robe_d"])
        _arms(p, c, v, P["robe_d"], P["skin"], staff=False)
    elif stage == "head":
        _head(p, c, v, P["skin"], P["hair"])
        if v == "back":
            p.circ(0, hy - 2, hr + 1.5, P["robe_d"])
        else:
            p.poly([(math.cos(a) * (hr + 1.5), hy - 1 + math.sin(a) * (hr + 1.5))
                    for a in [math.pi * 0.9 + i * math.pi * 1.2 / 12 for i in range(13)]],
                   P["robe_d"])


# ════════════════════════════════════════════════════════════════════════
#  FICHAS: medidas, paleta, ojos, boca, retrato
# ════════════════════════════════════════════════════════════════════════
def _c(**kw):
    d = dict(BASE)
    d.update(kw)
    return d


CHARS = {
    "gris": dict(
        name="Mago Gris", elem="neutro", fn=_gris, c=_c(),
        pal=dict(robe=(128, 130, 142), robe_d=(96, 98, 112), trim=(196, 198, 210),
                 cape=(92, 94, 108), hat=(118, 120, 134), hat_d=(84, 86, 100),
                 band=(206, 206, 216), hair=(176, 176, 186), skin=SKIN,
                 boots=(62, 54, 52), belt=(70, 66, 76), orb_l=(252, 252, 255),
                 orb_d=(34, 30, 46)),
        eyes=dict(iris=(90, 110, 140)), mouth="smile"),
    "blanco": dict(
        name="Mago Blanco", elem="luz", fn=_blanco,
        c=_c(hy=43, sw=12, hw=20, hem=97),
        pal=dict(robe=(244, 242, 236), robe_d=(214, 210, 204), mantle=(226, 222, 214),
                 gold=(226, 190, 90), gold_d=(170, 136, 60), sun=(255, 244, 190),
                 crack=(58, 30, 70), hair=(236, 234, 228), beard=(240, 238, 232),
                 beard_d=(214, 210, 204), skin=(240, 214, 188), boots=(200, 190, 170)),
        eyes=dict(iris=(214, 170, 60), style="slit"), mouth="thin",
        shadow=((50, 20, 70), 150, 1.4), portrait_bg=((250, 242, 210), (150, 130, 90))),
    "negro": dict(
        name="Mago Negro", elem="sombra", fn=_negro,
        c=_c(hy=45, sw=13, hw=19, hem=97),
        pal=dict(robe=(38, 36, 52), robe_d=(28, 26, 40), cape=(24, 22, 34),
                 armor=(60, 52, 80), armor_l=(96, 80, 124), hood=(30, 28, 44),
                 void=(12, 8, 18), face=(150, 140, 162), horn=(196, 188, 170),
                 hand=(150, 140, 162), glow=(180, 60, 220), boots=(20, 18, 26),
                 string=(210, 214, 230)),
        eyes=dict(iris=(240, 60, 70), style="glow"), mouth="sad", tear=True,
        portrait_bg=((70, 50, 100), (16, 12, 26))),
    "fuego": dict(
        name="Pyra", elem="fuego", fn=_pyra, c=_c(hy=45, sw=10, hw=16),
        pal=dict(robe=(206, 60, 44), robe_d=(160, 44, 34), trim=(250, 160, 60),
                 sash=(250, 180, 70), hair=(232, 84, 40), hair_l=(255, 176, 70),
                 skin=SKIN, legs=(70, 34, 30), boots=(90, 44, 30),
                 metal=(120, 100, 90), flame=(255, 130, 40), flame_c=(255, 230, 120)),
        eyes=dict(iris=(200, 110, 30), brow="fierce"), mouth="grin"),
    "planta": dict(
        name="Sylva", elem="planta", fn=_sylva, c=_c(sw=12, hw=19),
        pal=dict(robe=(66, 150, 80), robe_d=(48, 116, 62), trim=(170, 210, 120),
                 hair=(120, 86, 50), hat=(96, 176, 84), hat_d=(52, 120, 56),
                 stem=(80, 120, 50), leaf=(140, 210, 100), vine=(48, 110, 50),
                 flower=(240, 130, 170), flower_c=(255, 230, 120), wood=(118, 84, 52),
                 skin=SKIN, boots=(90, 66, 44)),
        eyes=dict(iris=(80, 140, 60), soft=True), mouth="smile"),
    "agua": dict(
        name="Marina", elem="agua", fn=_marina, c=_c(),
        pal=dict(robe=(60, 120, 206), robe_d=(44, 92, 170), trim=(170, 220, 240),
                 foam=(220, 244, 255), hair=(40, 90, 170), hair_l=(110, 180, 235),
                 shell=(250, 220, 210), metal=(210, 220, 230), metal_d=(150, 160, 175),
                 skin=SKIN, boots=(40, 70, 120)),
        eyes=dict(iris=(40, 130, 200)), mouth="smile"),
    "tierra": dict(
        name="Terra", elem="tierra", fn=_terra,
        c=_c(hy=48, hr=15, sh=61, sw=14, hw=22, hem=96),
        pal=dict(robe=(196, 120, 50), robe_d=(150, 88, 36), trim=(120, 78, 40),
                 belt=(96, 62, 34), gem=(100, 200, 110), hair=(110, 64, 34),
                 band=(150, 70, 40), stone=(140, 128, 112), stone_l=(176, 164, 146),
                 stone_d=(96, 86, 76), wood=(100, 70, 44), skin=(222, 178, 138),
                 boots=(80, 56, 36)),
        eyes=dict(iris=(110, 80, 40), brow="thick"), mouth="smile"),
    "rayo": dict(
        name="Electra", elem="rayo", fn=_electra,
        c=_c(hy=42, hr=14, sh=56, sw=8, hw=13, hem=96),
        pal=dict(robe=(226, 196, 60), robe_d=(180, 150, 40), stripe=(60, 54, 70),
                 hair=(250, 232, 120), tie=(80, 200, 240), goggle=(60, 54, 70),
                 lens=(120, 230, 255), metal=(170, 170, 185), bolt=(255, 250, 170),
                 skin=SKIN, boots=(60, 54, 70)),
        eyes=dict(iris=(60, 160, 210), narrow=True), mouth="flat"),
    "hielo": dict(
        name="Gélida", elem="hielo", fn=_gelida, c=_c(hy=43, sw=10, hw=17),
        pal=dict(robe=(150, 104, 212), robe_d=(118, 80, 176), frost=(230, 240, 255),
                 cape=(96, 66, 150), hair=(224, 220, 246), crown=(170, 226, 250),
                 crown_l=(245, 252, 255), crystal=(150, 220, 250),
                 crystal_l=(235, 250, 255), wood=(200, 206, 226),
                 skin=(236, 220, 226), boots=(90, 66, 130)),
        eyes=dict(iris=(120, 190, 230), cold=True), mouth="flat"),
    "mercader": dict(
        name="Mercader", elem="rayo", fn=_mercader, c=_c(hy=45, sw=12, hw=21),
        pal=dict(robe=(176, 140, 70), robe_d=(140, 108, 52), robe_l=(196, 162, 90),
                 trim=(120, 90, 44), belt=(90, 60, 36), purse=(230, 196, 80),
                 pack=(120, 84, 50), pack_d=(96, 66, 40), roll=(170, 70, 60),
                 roll_d=(120, 50, 40), hat=(120, 88, 56), hat_d=(92, 66, 42),
                 band=(230, 196, 80), hair=(90, 60, 40), skin=(226, 186, 150),
                 boots=(70, 50, 36)),
        eyes=dict(iris=(80, 60, 40), happy=True), mouth="none"),
}

for _el in ("fuego", "planta", "agua", "tierra", "rayo", "hielo", "luz", "sombra"):
    _ec = ELEM_COLOR[_el]
    CHARS["acolito_" + _el] = dict(
        name="Acólito", elem=_el, fn=_acolito, c=_c(hy=46, hr=14, sw=10, hw=17),
        scale=0.9,
        pal=dict(robe=lerp(shade(_ec, 0.62), (40, 30, 50), 0.35),
                 robe_d=lerp(shade(_ec, 0.42), (30, 22, 40), 0.35),
                 void=(14, 10, 20), emblem=shade(_ec, 1.3), boots=(30, 24, 34)),
        eyes=dict(iris=lerp(_ec, (255, 255, 255), 0.35), style="glow"), mouth="none")

CHAR_IDS = [k for k in CHARS]

_NAME_ALIAS = {
    "mago gris": "gris", "gris": "gris", "tú": "gris",
    "pyra": "fuego", "sylva": "planta", "marina": "agua", "terra": "tierra",
    "electra": "rayo", "gélida": "hielo", "gelida": "hielo",
    "mago blanco": "blanco", "mago negro": "negro", "eco del gris": "eco",
    "mercader": "mercader", "anciano": "anciano", "anciana": "anciana",
    "niña": "nina", "nina": "nina", "niño": "nino",
}


def _villager_spec(cid, seed):
    """Aldeanos: variación ESTABLE por semilla (16 variantes, paleta apagada)."""
    rng = random.Random(seed * 7919 + 17)
    cloth = _VILL_CLOTH[rng.randrange(len(_VILL_CLOTH))]
    skin = _VILL_SKIN[rng.randrange(len(_VILL_SKIN))]
    hair = _VILL_HAIR[rng.randrange(len(_VILL_HAIR))]
    acc = rng.choice(["none", "cap", "straw", "scarf", "bun", "long", "none"])
    scale = 0.84 + rng.random() * 0.1
    c = _c(sw=10 + rng.randint(0, 2), hw=15 + rng.randint(0, 3), acc=acc)
    if cid in ("anciano", "anciana"):
        hair = (206, 204, 198)
        skin = (232, 200, 170)
        acc = "bald" if cid == "anciano" else "bun"
        c.update(acc=acc, cane=True)
        scale = 0.84
    elif cid in ("nina", "nino"):
        acc = "pigtails" if cid == "nina" else "none"
        c.update(acc=acc, hy=50, hr=16, sh=64, sw=9, hw=13, tunic=90)
        scale = 0.66
    pal = dict(robe=cloth, robe_d=shade(cloth, 0.8), legs=shade(cloth, 0.55),
               belt=shade(cloth, 0.5), skin=skin, hair=hair, boots=(64, 50, 40),
               hat=lerp(cloth, (200, 190, 170), 0.4), hat_d=shade(cloth, 0.7),
               straw=(214, 186, 110), straw_d=(180, 150, 80), band=shade(cloth, 0.6),
               tie=(200, 80, 90), wood=(120, 90, 60))
    return dict(name="Aldeano", elem="luz", fn=_aldeano, c=c, pal=pal, scale=scale,
                eyes=dict(iris=(70, 60, 50)), mouth="smile", outline=(46, 40, 48),
                shadow=((20, 20, 24), 90, 0.85))


def _spec(cid, color=None, seed=0):
    if cid in CHARS:
        return CHARS[cid]
    if cid == "eco":
        s = dict(CHARS["gris"])
        s["ghost"] = True
        return s
    if cid in ("nina", "nino") or cid in _VILLAGER_NAMES:
        return _villager_spec(cid, 3 if cid in ("anciano", "anciana", "ermitaño") else seed)
    col = tuple(color or (150, 150, 160))[:3]
    return dict(name="?", elem="neutro", fn=_generico, c=_c(),
                pal=dict(robe=col, robe_d=shade(col, 0.7), skin=SKIN,
                         hair=(90, 70, 50), boots=(50, 44, 40)),
                eyes=dict(iris=(60, 60, 70)), mouth="smile")


_POSSESS_TINT = (48, 18, 66)


def _possess_pal(pal):
    out = {}
    for k, v in pal.items():
        if k in ("skin", "face", "hand"):
            out[k] = lerp(v, (150, 120, 160), 0.55)
        elif k in ("flame", "flame_c", "lens", "crystal", "crystal_l", "bolt", "orb_l",
                   "sun", "glow", "emblem"):
            out[k] = lerp(v, (220, 60, 150), 0.55)
        else:
            out[k] = shade(lerp(v, _POSSESS_TINT, 0.42), 0.78)
    return out


# ════════════════════════════════════════════════════════════════════════
#  RENDER
# ════════════════════════════════════════════════════════════════════════
def _draw_figure(surf, k, cx, feet, spec, v, f, pal, d, breath=0.0):
    c = dict(spec["c"])
    if breath:
        for key in ("hy", "sh"):
            c[key] += breath
    p = _P(surf, k, cx, feet)
    fn = spec["fn"]
    for stage in ("behind", "body", "head", "top"):
        fn(stage, p, v, f, pal, c, d)
    return c


def _mask_ring(surf, grow, color, thresh=90):
    """Anillo de `grow` px alrededor de la silueta (contorno / aura)."""
    m = pygame.mask.from_surface(surf, thresh)
    w, h = surf.get_size()
    dil = pygame.mask.Mask((w, h))
    for dx in range(-grow, grow + 1):
        for dy in range(-grow, grow + 1):
            if dx * dx + dy * dy <= grow * grow + (1 if grow == 1 else 0):
                dil.draw(m, (dx, dy))
    dil.erase(m, (0, 0))
    return dil.to_surface(setcolor=color, unsetcolor=(0, 0, 0, 0))


def _eyes(surf, k, cx, feet, spec, c, v, possessed, d):
    """Ojos a resolución FINAL (nítidos). d: 0 overworld, 1 combate, 2 retrato."""
    if v == "back":
        return
    e = spec.get("eyes", {})
    style = e.get("style", "normal")
    if possessed and style not in ("glow",):
        style = "possessed"
    hy, hr = c["hy"], c["hr"]
    ey = feet + (hy + hr * 0.18 - 100) * k
    if v == "side":
        xs = [cx + (-hr * 0.55) * k]
    else:
        xs = [cx - hr * 0.4 * k, cx + hr * 0.4 * k]
    glow_col = (255, 70, 110) if style == "possessed" else e.get("iris", (255, 80, 80))
    if style in ("glow", "possessed"):
        r = max(1.0, hr * k * 0.13)
        g = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        for x in xs:
            pygame.draw.circle(g, glow_col + (70,), (x, ey), r * 2.6)
            pygame.draw.circle(g, glow_col + (120,), (x, ey), r * 1.7)
        surf.blit(g, (0, 0))
        for x in xs:
            if d == 0:
                surf.fill(lerp(glow_col, (255, 255, 255), 0.5),
                          pygame.Rect(int(x), int(ey) - 1, 1, 2))
            else:
                pygame.draw.circle(surf, lerp(glow_col, (255, 255, 255), 0.35), (x, ey), r)
                pygame.draw.circle(surf, (255, 255, 255), (x, ey), max(1, r * 0.45))
        if spec.get("tear") and d >= 1 and v == "front":        # lágrima de luz
            x = xs[0]
            pygame.draw.line(surf, (200, 190, 255), (x, ey + r * 1.5),
                             (x - 0.5, ey + hr * k * 0.55), max(1, int(k * 1.1)))
        return
    dark = (34, 26, 36)
    if d == 0:                                  # 1x2 px: clásico y legible a 32 px
        for x in xs:
            surf.fill(dark, pygame.Rect(int(round(x)) - (1 if v == "side" else 0) + 0,
                                        int(round(ey)) - 1, 1 if v != "side" else 1, 2))
        return
    rw = hr * k * (0.16 if not e.get("narrow") else 0.15)
    rh = hr * k * (0.24 if not e.get("narrow") else 0.17)
    if e.get("happy"):
        for x in xs:
            pygame.draw.arc(surf, dark, pygame.Rect(x - rw * 1.2, ey - rh, rw * 2.4, rh * 2),
                            0.3, math.pi - 0.3, max(1, int(k * 1.4)))
        return
    for i, x in enumerate(xs):
        box = pygame.Rect(0, 0, max(2, rw * 2), max(3, rh * 2))
        box.center = (x, ey)
        pygame.draw.ellipse(surf, (250, 250, 252), box)
        ir = box.inflate(-max(0, box.w * 0.25), -max(0, box.h * 0.2))
        ir.centerx += (-1 if v == "side" else 0)
        pygame.draw.ellipse(surf, e.get("iris", (80, 80, 90)), ir)
        if style == "slit":
            pygame.draw.line(surf, (40, 20, 30), (ir.centerx, ir.top + 1),
                             (ir.centerx, ir.bottom - 2), max(1, int(k * 0.8)))
        else:
            pr = ir.inflate(-ir.w * 0.45, -ir.h * 0.45)
            pygame.draw.ellipse(surf, dark, pr)
            surf.fill((255, 255, 255), pygame.Rect(ir.x + max(1, ir.w // 4), ir.y + 1,
                                                   max(1, ir.w // 4), max(1, ir.h // 5)))
        pygame.draw.line(surf, dark, (box.left, box.top), (box.right - 1, box.top),
                         max(1, int(k * 1.1)))              # párpado
        if e.get("brow") == "fierce":
            s = -1 if (i == 0 and v != "side") else 1
            pygame.draw.line(surf, (120, 40, 30), (x - rw * 1.4, ey - rh * 1.9 - s * k),
                             (x + rw * 1.4, ey - rh * 1.9 + s * k), max(1, int(k * 1.6)))
        elif e.get("brow") == "thick":
            pygame.draw.line(surf, (90, 56, 30), (x - rw * 1.3, ey - rh * 1.8),
                             (x + rw * 1.3, ey - rh * 1.8), max(1, int(k * 2)))
        elif e.get("cold"):
            pygame.draw.line(surf, (40, 30, 60), (box.left, box.top + 1),
                             (box.right - 1, box.top + 1), max(1, int(k * 1.3)))


def _mouth(surf, k, cx, feet, spec, c, v, d, possessed):
    if d < 2 or v == "back":
        return
    m = spec.get("mouth", "smile")
    if m == "none":
        return
    hy, hr = c["hy"], c["hr"]
    my = feet + (hy + hr * 0.6 - 100) * k
    mx = cx + (-hr * 0.45 * k if v == "side" else 0)
    w = hr * k * 0.28
    col = (120, 50, 60)
    lw = max(1, int(k * 1.2))
    if possessed:
        m = "flat"
    if m == "smile":
        pygame.draw.arc(surf, col, pygame.Rect(mx - w, my - w * 0.8, 2 * w, w * 1.3),
                        math.pi + 0.4, 2 * math.pi - 0.4, lw)
    elif m == "grin":
        pygame.draw.polygon(surf, (150, 50, 50), [(mx - w, my - 1), (mx + w, my - 2),
                                                  (mx + w * 0.4, my + w * 0.6)])
        pygame.draw.line(surf, (255, 255, 255), (mx - w * 0.7, my - 1), (mx + w * 0.7, my - 2), 1)
    elif m == "sad":
        pygame.draw.arc(surf, (60, 40, 70), pygame.Rect(mx - w, my, 2 * w, w * 1.2),
                        0.4, math.pi - 0.4, lw)
    elif m == "thin":                       # sonrisa demasiado larga y fina
        pygame.draw.arc(surf, (130, 90, 80), pygame.Rect(mx - w * 1.6, my - w * 1.2,
                                                         3.2 * w, w * 1.6),
                        math.pi + 0.35, 2 * math.pi - 0.35, max(1, int(k * 0.9)))
    else:
        pygame.draw.line(surf, col, (mx - w * 0.7, my), (mx + w * 0.7, my), lw)


def _shadow(surf, cx, feet, k, spec):
    col, a, sc = spec.get("shadow", ((20, 16, 26), 110, 1.0))
    w = 30 * k * sc
    h = 7 * k * max(1.0, sc * 0.8)
    s = pygame.Surface((int(w) + 2, int(h) + 2), pygame.SRCALPHA)
    pygame.draw.ellipse(s, col + (a,), s.get_rect())
    surf.blit(s, (cx - s.get_width() / 2, feet - s.get_height() / 2))


def _compose(spec, W, H, k, cx, feet, v, f, possessed, d, breath=0.0, shadow=True):
    pal = spec["pal"]
    if possessed:
        pal = _possess_pal(pal)
    sc = spec.get("scale", 1.0)
    kk = k * sc
    big = pygame.Surface((W * SS, H * SS), pygame.SRCALPHA)
    c = _draw_figure(big, kk * SS, cx * SS, feet * SS, spec, v, f, pal, d, breath)
    fig = pygame.transform.smoothscale(big, (W, H))
    out = pygame.Surface((W, H), pygame.SRCALPHA)
    if shadow:
        _shadow(out, cx, feet - 1.5 * kk, kk, spec)
    if possessed or spec["fn"] is _negro:
        aura = _mask_ring(fig, 3 if d else 2, (170, 50, 220, 70 if not possessed else 95))
        out.blit(aura, (0, 0))
    ring = _mask_ring(fig, 1, spec.get("outline", OUTLINE) + (255,))
    out.blit(ring, (0, 0))
    out.blit(fig, (0, 0))
    _eyes(out, kk, cx, feet, spec, c, v, possessed, d)
    _mouth(out, kk, cx, feet, spec, c, v, d, possessed)
    if spec.get("ghost"):                       # Eco del Gris: espectro azulado
        tint = pygame.Surface((W, H), pygame.SRCALPHA)
        tint.fill((150, 190, 255, 255))
        out.blit(tint, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        out.fill((255, 255, 255, 150), special_flags=pygame.BLEND_RGBA_MULT)
    return out


def _norm_facing(facing):
    if isinstance(facing, (tuple, list)):
        fx, fy = facing[0], facing[1]
        if fx < 0:
            return "left"
        if fx > 0:
            return "right"
        return "up" if fy < 0 else "down"
    return {"down": "down", "up": "up", "left": "left", "right": "right",
            "s": "down", "n": "up", "w": "left", "e": "right"}.get(str(facing), "down")


def _norm_id(cid):
    cid = str(cid or "").strip()
    low = cid.lower()
    if low in CHARS or low in ("eco", "aldeano", "aldeana", "anciano", "anciana", "nina",
                               "nino", "refugiada", "refugiado", "ciudadano", "ermitaño"):
        return low
    if low in _NAME_ALIAS:
        return _NAME_ALIAS[low]
    if low.startswith("acólito ") or low.startswith("acolito "):
        el = low.split(" ", 1)[1]
        el = {"fuego": "fuego", "planta": "planta", "agua": "agua", "tierra": "tierra",
              "rayo": "rayo", "hielo": "hielo", "luz": "luz", "sombra": "sombra"}.get(el, el)
        return "acolito_" + el
    return low


def get_overworld(cid, facing="down", frame=0, possessed=False, color=None, seed=0):
    """Sprite de mapa 32x48 (ancla centro-abajo, pies en y=46)."""
    cid = _norm_id(cid)
    fac = _norm_facing(facing)
    frame = int(frame) % 2
    vseed = seed % 16
    key = ("ow", cid, fac, frame, bool(possessed), tuple(color or ())[:3], vseed)
    s = _CACHE.get(key)
    if s is not None:
        return s
    if fac == "right":
        s = pygame.transform.flip(get_overworld(cid, "left", frame, possessed, color, seed),
                                  True, False)
    else:
        spec = _spec(cid, color, vseed)
        v = {"down": "front", "up": "back", "left": "side"}[fac]
        s = _compose(spec, OW_W, OW_H, OW_K, OW_W / 2, OW_FEET, v, frame, possessed, 0)
    _CACHE[key] = s
    return s


def get_battle(cid, possessed=False, frame=0, color=None, seed=0, size=64):
    """Sprite de combate (frente, idle). frame 0/1 = respiración."""
    cid = _norm_id(cid)
    key = ("bt", cid, bool(possessed), int(frame) % 2, tuple(color or ())[:3], seed % 16, size)
    s = _CACHE.get(key)
    if s is None:
        spec = _spec(cid, color, seed % 16)
        k = size / 104.0
        s = _compose(spec, size, size, k, size / 2, size - 2, "front", 0, possessed, 1,
                     breath=0.9 if frame % 2 else 0.0)
        _CACHE[key] = s
    return s


def _portrait_bg(spec, size, possessed):
    base = ELEM_COLOR.get(spec.get("elem"), (150, 150, 160))
    top, bot = spec.get("portrait_bg", (lerp(base, (255, 255, 255), 0.35), shade(base, 0.35)))
    if possessed:
        top, bot = (120, 40, 110), (20, 8, 30)
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    for y in range(size):
        pygame.draw.line(s, lerp(top, bot, y / max(1, size - 1)), (0, y), (size, y))
    return s


def get_portrait(cid, size=64, possessed=False, color=None, seed=0, framed=True):
    """Busto (cabeza y hombros) de size x size para diálogos, Estado y level-up."""
    cid = _norm_id(cid)
    key = ("pt", cid, int(size), bool(possessed), tuple(color or ())[:3], seed % 16, framed)
    s = _CACHE.get(key)
    if s is not None:
        return s
    spec = _spec(cid, color, seed % 16)
    c = spec["c"]
    sc = spec.get("scale", 1.0)
    # encuadre: de un poco sobre la cabeza hasta el pecho
    y0, y1 = c["hy"] - 30, c["hy"] + 32
    k = size / (y1 - y0) / sc
    feet = size + (100 - y1) * k * sc
    fig = _compose(spec, size, size, k, size / 2, feet, "front", 0, possessed, 2,
                   shadow=False)
    if framed:
        s = _portrait_bg(spec, size, possessed)
        s.blit(fig, (0, 0))
        mask = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(),
                         border_radius=max(4, size // 8))
        s.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        border = (226, 190, 90) if cid in ("blanco", "negro") or possessed else (235, 235, 245)
        pygame.draw.rect(s, OUTLINE, s.get_rect(), max(2, size // 24) + 1,
                         border_radius=max(4, size // 8))
        pygame.draw.rect(s, border, s.get_rect().inflate(-2, -2), max(1, size // 32),
                         border_radius=max(4, size // 8))
    else:
        s = fig
    _CACHE[key] = s
    return s


def id_for(ent):
    """Traduce un dict de rpg.py (talker / enemy / miembro del grupo) a (cid, poseída).

    - miembros del grupo: ent["id"] ("gris", "fuego"... "blanco", "negro")
    - jefa poseída: enemy con "maga" -> (elem, True)
    - Mago Negro/Blanco como enemigo: flags prologue/subfinal/final/blanco1/secret
    - acólitos: kind == "acolito" -> "acolito_<elem>"
    - talkers: por nombre ("Mago Blanco", "Mercader", "Aldeano", ...)
    Devuelve (None, False) para criaturas de ambiente (que siga dibujándolas rpg.py).
    """
    if not isinstance(ent, dict):
        return _norm_id(ent), False
    if ent.get("maga"):
        return ent["maga"], True
    if ent.get("reposs"):                       # maga re-poseída (f5, hilos de luz)
        return ent["reposs"], True
    if ent.get("kind") == "acolito":
        return "acolito_" + ent.get("elem", "sombra"), False
    if ent.get("kind") == "ambient" or ent.get("dragon"):
        return None, False
    name = (ent.get("name") or "").lower()
    if ent.get("secret") or name.startswith("reflejo"):   # Reflejo del Gris: Gris oscuro
        return "gris", True
    if "magas" in name or name in ("narrador", "cartel"):
        return None, False
    if any(ent.get(k) for k in ("prologue", "subfinal")) or "negro" in name:
        return "negro", False
    if ent.get("final") or ent.get("blanco1") or name == "mago blanco":
        return "blanco", False
    if ent.get("shop") or name == "mercader":
        return "mercader", False
    cid = ent.get("id")
    if cid and _norm_id(cid) in CHARS:
        return _norm_id(cid), False
    if name in _NAME_ALIAS:
        return _NAME_ALIAS[name], False
    if name.startswith("eco"):
        return "eco", False
    if ent.get("side") == "enemy":
        return None, False
    return "aldeano", False


# ════════════════════════════════════════════════════════════════════════
#  PEGAMENTO para rpg.py y sus copias (llamadas de una línea desde el juego)
# ════════════════════════════════════════════════════════════════════════
_ELEM_CID = {"neutro": "gris", "luz": "blanco", "sombra": "negro"}
_SEEDS = {}          # id(ent) -> semilla fija (la 1ª posición en que se le vio)
_MOTION = {}         # id(ent) -> (x, y, facing) para deducir hacia dónde mira
_VILLAGER_NAMES = ("aldeano", "aldeana", "refugiada", "refugiado", "ciudadano",
                   "ciudadana", "anciano", "anciana", "niña", "niño", "ermitaño",
                   "granjera", "granjero", "pescador", "pescadora", "herrero")


def cid_for_elem(el):
    """Elemento de un miembro del grupo -> id de sprite (neutro=gris, luz=blanco...)."""
    return _ELEM_CID.get(el, el)


def _seed_for(ent, x, y):
    k = id(ent)
    s = _SEEDS.get(k)
    if s is None:
        s = _SEEDS[k] = (int(x) * 31 + int(y) * 17) & 0xFFFF
    return s


def blit_actor(screen, ent, px, py, bob, camx, camy, tile=32, facing=None):
    """Dibuja `ent` en la casilla (px, py) del overworld. Devuelve False si no es
    un personaje (criatura, dragón, ángel): entonces que lo dibuje draw_actor."""
    if not isinstance(ent, dict) or ent.get("angel"):
        return False
    cid, poss = id_for(ent)
    if cid is None:
        return False
    k = id(ent)
    last = _MOTION.get(k)
    if facing is None:                        # deduce la dirección del movimiento
        facing = last[2] if last else (0, 1)
        if last:
            dx, dy = px - last[0], py - last[1]
            if abs(dx) > 1e-3 or abs(dy) > 1e-3:
                facing = (1 if dx > 0 else -1, 0) if abs(dx) >= abs(dy) else \
                         (0, 1 if dy > 0 else -1)
    _MOTION[k] = (px, py, facing)
    # frame de paso ligado a la posición: cambia cada media casilla, 0 en reposo
    frame = int(round((px + py) * 2)) % 2
    s = get_overworld(cid, facing, frame, poss, ent.get("color"),
                      _seed_for(ent, ent.get("x", px), ent.get("y", py)))
    screen.blit(s, (int(px * tile + tile // 2 - camx) - OW_W // 2,
                    int(py * tile + tile + bob - camy) - OW_FEET - 1))
    return True


def blit_battle(screen, ent, x, y, flash=False):
    """Sprite de combate centrado en (x, y). Devuelve su semialtura o None."""
    cid, poss = id_for(ent)
    if cid is None:
        return None
    big = bool(ent.get("boss") or ent.get("final") or ent.get("subfinal"))
    fr = (pygame.time.get_ticks() // 520) % 2
    s = get_battle(cid, poss, fr, ent.get("color"), _seed_for(ent, 0, 0),
                   size=96 if big else 64)
    if flash:
        s = s.copy()
        s.fill((150, 150, 150, 0), special_flags=pygame.BLEND_RGBA_ADD)
    screen.blit(s, (x - s.get_width() // 2, y - s.get_height() // 2))
    return s.get_height() // 2 - 4


def blit_portrait(screen, who, center, size, dead=False):
    """Retrato centrado. `who` = dict de personaje o id/elemento."""
    if isinstance(who, dict):
        cid, poss = id_for(who)
        if who.get("side") == "hero":
            cid, poss = cid_for_elem(who.get("id") or who.get("elem")), False
    else:
        cid, poss = cid_for_elem(_norm_id(who)), False
    if cid is None:
        return False
    s = get_portrait(cid, size, poss)
    if dead:
        s = pygame.transform.grayscale(s)
        s.fill((150, 150, 150, 255), special_flags=pygame.BLEND_RGBA_MULT)
    screen.blit(s, (center[0] - size // 2, center[1] - size // 2))
    return True


def portrait_for_speaker(name, size=80):
    """Retrato para la caja de diálogo según el nombre del hablante, o None si
    no es un personaje (carteles, grupos, visiones...)."""
    low = (name or "").strip().lower()
    if not low:
        return None
    poss = "poseída" in low or "hilos de luz" in low
    base = low.split(" (")[0].strip()
    if base in _NAME_ALIAS:
        cid = _NAME_ALIAS[base]
    elif base.startswith("acólito") or base.startswith("acolito"):
        cid = _norm_id(base)
    elif base.startswith("eco"):
        cid = "eco"
    elif base.startswith("reflejo"):
        cid, poss = "gris", True
    elif base in _VILLAGER_NAMES:
        cid = {"niña": "nina", "niño": "nino"}.get(base, base)
    else:
        return None
    seed = sum(ord(ch) for ch in low)
    return get_portrait(cid, size, poss, seed=seed)
