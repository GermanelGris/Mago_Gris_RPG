"""rpg_creatures.py — criaturas NO humanoides del RPG 2D de Nerea, 100% por código.

Compañero de rpg_sprites.py (que hace magas, magos, acólitos y aldeanos). Cada
criatura se dibuja en un espacio de "unidades" (suelo en y=100, centro del cuerpo
en x=0, MIRANDO A LA IZQUIERDA), supermuestreado x4 y reducido con smoothscale.
Contorno y ojos se pintan después, ya a resolución final, para que se lean.

API (Surfaces SRCALPHA cacheadas; NO las modifiques):
    creature_id(ent)            -> id de criatura o None (no es criatura)
    get_overworld(cid, facing="left", frame=0, dark=False) -> (surf, ax, ay)
        ancla (ax, ay) = punto del suelo bajo la criatura (sus pies).
    get_battle(cid, frame=0, dark=False, size=None)         -> (surf, ax, ay)
    blit_overworld(screen, ent, px, py, bob, camx, camy, tile=32, dark=None) -> bool
    blit_battle(screen, ent, x, y, flash=False, dark=None)  -> semialtura o None
    set_dark(flag)   mundo poseído: variante corrompida (violeta, ojos emisivos)

`dark=None` usa el último set_dark() (el overworld lo fija cada fotograma y el
combate hereda el estado del mundo del que vienes).
"""
import math
import unicodedata

import pygame

try:
    from gfx_utils import shade, lerp
except Exception:
    try:
        from games.gfx_utils import shade, lerp
    except Exception:
        def lerp(c1, c2, t):
            t = 0.0 if t < 0 else 1.0 if t > 1 else t
            return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))

        def shade(color, factor):
            return tuple(max(0, min(255, int(v * factor))) for v in color[:3])

__all__ = ["creature_id", "get_overworld", "get_battle", "blit_overworld",
           "blit_battle", "set_dark", "clear_cache", "CREATURE_IDS", "battle_center",
           "portrait_for_speaker"]

SS = 4
OUTLINE = (22, 16, 30)
WHITE = (250, 250, 245)
_CACHE = {}
_DARK = False
_MOTION = {}


def clear_cache():
    _CACHE.clear()


def set_dark(flag):
    global _DARK
    _DARK = bool(flag)


# ════════════════════════════════════════════════════════════════════════
#  PINTOR en unidades
# ════════════════════════════════════════════════════════════════════════
def bz(*c, n=14):
    """Curva de Bézier (cualquier grado) -> lista de puntos."""
    out = []
    for i in range(n + 1):
        t = i / n
        pts = list(c)
        while len(pts) > 1:
            pts = [(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
                   for a, b in zip(pts, pts[1:])]
        out.append(pts[0])
    return out


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

    def tube(self, pts, r0, r1, col, step=0.7):
        """Miembro que se AFINA a lo largo de una polilínea (cuellos, colas, patas)."""
        seg = [(a, b, math.hypot(b[0] - a[0], b[1] - a[1])) for a, b in zip(pts, pts[1:])]
        tot = sum(s[2] for s in seg) or 1.0
        n = max(2, int(tot / step))
        acc, si = 0.0, 0
        for i in range(n + 1):
            d = tot * i / n
            while si < len(seg) - 1 and acc + seg[si][2] < d:
                acc += seg[si][2]
                si += 1
            a, b, L = seg[si]
            t = 0 if L == 0 else (d - acc) / L
            self.circ(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t,
                      r0 + (r1 - r0) * i / n, col)

    def tri(self, x, y, w, h, col, dx=0.0):
        """Triángulo con base centrada en (x, y) y punta a (x+dx, y-h)."""
        self.poly([(x - w, y), (x + dx, y - h), (x + w, y)], col)


def _rot(pts, ang, ox, oy):
    c, s = math.cos(ang), math.sin(ang)
    return [(ox + (x - ox) * c - (y - oy) * s, oy + (x - ox) * s + (y - oy) * c)
            for x, y in pts]


def _ring_pts(cx, cy, rx, ry, ang, n=28, ph=0.0):
    c, s = math.cos(ang), math.sin(ang)
    out = []
    for i in range(n + 1):
        t = ph + 2 * math.pi * i / n
        x, y = rx * math.cos(t), ry * math.sin(t)
        out.append((cx + x * c - y * s, cy + x * s + y * c))
    return out


# ════════════════════════════════════════════════════════════════════════
#  CRIATURAS  (fn(p, f, P) -> lista de ojos (x, y, r, estilo))
#  estilo: "dot" (color + pupila), "blank" (brillo sin pupila), "sclera" (blanco + iris)
# ════════════════════════════════════════════════════════════════════════
def _bat(p, f, P, ice=False):
    y0 = 50 if f == 0 else 53
    for s in (-1, 1):
        if f == 0:      # alas ARRIBA
            w = [(6, y0 - 4), (22, y0 - 20), (48, y0 - 32), (44, y0 - 14), (36, y0 - 16),
                 (31, y0 + 1), (22, y0 - 5), (15, y0 + 9), (8, y0 + 7)]
        else:           # alas ABAJO
            w = [(6, y0 - 4), (24, y0 - 6), (47, y0 + 10), (38, y0 + 14), (32, y0 + 6),
                 (25, y0 + 22), (18, y0 + 12), (12, y0 + 19), (8, y0 + 8)]
        if s > 0:       # un ala algo más abierta que la otra
            w = [(x * 1.06, y - (2 if f == 0 else 0)) for x, y in w]
        pts = [(s * x, y) for x, y in w]
        p.poly(pts, P["m"])
        sh = pts[0]
        for q in (pts[2], pts[4], pts[6]):
            p.line(sh[0], sh[1], q[0], q[1], 1.5, P["d"])
        p.lines(pts[0:3], 2.4, P["d"])
        if ice:         # carámbanos colgando del borde
            for q in (pts[3], pts[5], pts[7]):
                p.poly([(q[0] - 2, q[1] - 1), (q[0] + 2, q[1] - 1), (q[0] + s * 0.5, q[1] + 8)],
                       P["a"])
            p.tri(pts[2][0], pts[2][1] + 2, 2, 7, P["a2"])
        else:           # brasas en los dedos
            for q in (pts[2], pts[4]):
                p.circ(q[0], q[1], 2.4, P["a"])
                p.circ(q[0], q[1], 1.2, P["a2"])
    p.ell(0, y0 + 3, 10, 13, P["b"])
    p.ell(0, y0 + 6, 6, 8, P["l"])
    for s in (-1, 1):
        p.line(s * 3, y0 + 14, s * 4.5, y0 + 19, 1.4, P["d"])
    hy = y0 - 11
    if ice:
        p.poly([(-7, hy - 1), (-12, hy - 10), (-2, hy - 6)], P["b"])
        p.poly([(7, hy - 1), (11, hy - 8), (2, hy - 6)], P["b"])
        for x in (-8, -4, 4, 8):
            p.tri(x, hy - 5, 1.5, 5, P["a"])
    else:
        p.poly([(-7, hy - 1), (-10, hy - 17), (-2, hy - 6)], P["b"])
        p.poly([(7, hy - 1), (9, hy - 14), (2, hy - 6)], P["b"])
        p.poly([(-6, hy - 3), (-8.5, hy - 13), (-3.5, hy - 6)], P["a"])
        p.poly([(6, hy - 3), (7.5, hy - 11), (3.5, hy - 6)], P["a"])
    p.circ(0, hy, 8, P["b"])
    p.ell(0, hy + 4, 4.5, 3, P["l"])
    p.circ(0, hy + 2.5, 1.2, P["d"])
    for s in (-1, 1):
        p.poly([(s * 2.8, hy + 5.5), (s * 1.2, hy + 5.5), (s * 2, hy + 10)],
               P.get("fang", WHITE))
    return [(-3.6, hy - 1.5, 2.2, "dot"), (3.6, hy - 1.5, 2.2, "dot")]


def _bat_ice(p, f, P):
    return _bat(p, f, P, ice=True)


def _salamander(p, f, P):
    st = 3 if f else -3
    # patas del lado lejano (más oscuras)
    p.tube([(-8, 88), (-4 - st, 94), (-8 - st, 99)], 3, 2.2, P["d"])
    p.tube([(20, 88), (26 + st, 94), (28 + st, 99)], 3.4, 2.2, P["d"])
    # cola que se enrosca hacia arriba con llama en la punta
    tail = bz((22, 85), (44, 88), (58, 76), (52, 58), n=20)
    p.tube(tail, 7, 1.6, P["b"])
    tx, ty = tail[-1]
    fl = 2 if f else 0
    p.poly([(tx - 5, ty + 2), (tx - 3 + fl, ty - 10), (tx, ty - 5), (tx + 2 - fl, ty - 14),
            (tx + 5, ty + 2)], P["a"])
    p.poly([(tx - 2.5, ty + 1), (tx + fl - 1, ty - 7), (tx + 2.5, ty + 1)], P["a2"])
    # cuerpo
    p.tube([(-20, 85), (-6, 83), (10, 85), (24, 85)], 9, 7, P["b"])
    p.ell(0, 90, 20, 3.5, P["l"])
    for i, x in enumerate(range(-18, 32, 7)):          # cresta de fuego dorsal
        p.tri(x, 78 + (i % 2), 3, 6 + (i % 2) * 3 + (1 if (i + f) % 2 else 0), P["a"], dx=1.5)
    for x, y in ((-8, 80), (4, 80), (15, 81), (30, 82)):
        p.circ(x, y, 1.6, P["d"])
    # cabeza en cuña, algo levantada
    p.ell(-27, 81, 11, 7, P["b"])
    p.poly([(-22, 75), (-37, 79), (-42, 84), (-38, 88), (-24, 88)], P["b"])
    p.poly([(-24, 77), (-36, 80), (-30, 81)], P["l"])
    p.line(-41, 85, -28, 86, 1.1, P["d"])
    if f:
        p.lines([(-41, 85), (-47, 86), (-49, 84)], 0.9, P["tongue"])
        p.lines([(-47, 86), (-49, 88)], 0.9, P["tongue"])
    # patas cercanas, abiertas como las de un lagarto
    p.tube([(-12, 88), (-17 + st, 94), (-21 + st, 99)], 3.4, 2.4, P["b"])
    p.tube([(15, 88), (19 - st, 94), (13 - st, 99)], 3.8, 2.4, P["b"])
    for x in (-21 + st, 13 - st):
        p.ell(x, 99, 3, 1.3, P["d"])
    return [(-30, 79, 2.0, "dot")]


def _magma_dog(p, f, P):
    st = 4 if f else -4
    # patas lejanas
    p.tube([(-8, 70), (-10 - st, 84), (-12 - st, 98)], 5, 3.6, P["d"])
    p.tube([(21, 70), (27 + st, 84), (23 + st, 98)], 6, 3.6, P["d"])
    # cola en llama
    p.tube(bz((24, 62), (34, 58), (38, 46)), 4, 2, P["b"])
    p.poly([(34, 48), (38, 36 - (2 if f else 0)), (40, 44), (44, 38), (42, 50)], P["a"])
    # tronco pesado: pecho alto, grupa baja
    p.ell(2, 64, 22, 11, P["b"])
    p.ell(-10, 62, 15, 13, P["b"])
    p.ell(14, 66, 12, 11, P["b"])
    # grietas de lava
    p.lines([(-16, 60), (-10, 64), (-4, 60), (2, 66), (8, 62)], 1.3, P["a"])
    p.lines([(8, 70), (14, 66), (20, 70)], 1.1, P["a"])
    # crin de llamas sobre cuello y cruz
    for i, (x, y) in enumerate(((-26, 56), (-20, 52), (-13, 50), (-6, 50), (1, 52))):
        p.tri(x, y + 3, 4, 9 + (i + f) % 2 * 3, P["a"], dx=3)
        p.tri(x, y + 3, 2, 5, P["a2"], dx=2)
    # cuello y cabeza BAJOS y adelantados (amenaza)
    p.tube([(-14, 58), (-26, 63)], 9, 7, P["b"])
    p.ell(-32, 64, 10, 8, P["b"])
    p.poly([(-30, 58), (-44, 62), (-48, 67), (-44, 70), (-30, 70)], P["b"])
    p.poly([(-32, 70), (-45, 71), (-42, 77), (-30, 74)], P["d"])     # mandíbula abierta
    p.poly([(-33, 70.5), (-43, 71.5), (-40, 74.5), (-32, 73)], P["a"])  # boca de lava
    for x in (-42, -37):
        p.tri(x, 70, 1.2, -3, WHITE)
    p.circ(-47, 65, 1.4, P["d"])
    p.poly([(-28, 57), (-19, 49), (-23, 60)], P["d"])                # oreja hacia atrás
    # patas cercanas
    p.tube([(-14, 70), (-16 + st, 84), (-18 + st, 98)], 5.5, 4, P["b"])
    p.tube([(16, 70), (22 - st, 84), (18 - st, 98)], 6.5, 4, P["b"])
    for x in (-18 + st, 18 - st):
        p.ell(x - 1.5, 99, 5, 2, P["d"])
    return [(-35, 62, 1.9, "dot")]


def _wolf(p, f, P, proud=False):
    st = 4 if f else -4
    if proud:
        H, snout = (-28, 44), 14
        neck = [(-16, 58), (-22, 50), (-26, 46)]
        tail = bz((22, 60), (34, 56), (38, 44))
    else:
        H, snout = (-35, 64), 15
        neck = [(-18, 60), (-28, 64)]
        tail = bz((22, 60), (32, 66), (36, 82))
    hx, hy = H
    p.tube([(-9, 70), (-10 - st, 84), (-12 - st, 98)], 3.8, 2.4, P["d"])
    p.tube([(19, 66), (25 + st, 80), (21 + st, 90), (23 + st, 98)], 5, 2.4, P["d"])
    p.tube(tail, 5.5, 2.2, P["b"])
    p.tube(tail[len(tail) // 2:], 4.5, 1.2, P["l"])
    p.tube([(-12, 62), (2, 63), (16, 64)], 9, 7.5, P["b"])
    p.ell(-13, 65, 11, 11 if proud else 10, P["b"])
    p.ell(0, 70, 14, 3, P["d"])
    p.tube(neck, 8, 6.5, P["b"])
    # gorguera: musgo (bosque) o escarcha (pico)
    for i in range(5):
        a = -0.9 + i * 0.45
        x = neck[0][0] - 2 + math.cos(a) * 9
        y = neck[0][1] + 2 + math.sin(a) * 9
        if proud:
            p.tri(x, y, 2.4, 7, P["a"], dx=-2)
        else:
            p.circ(x, y - 2, 3.2, P["a"])
    p.ell(hx, hy, 8, 7, P["b"])
    p.poly([(hx + 2, hy - 4), (hx - snout + 2, hy - 1), (hx - snout, hy + 2),
            (hx - snout + 2, hy + 5), (hx + 2, hy + 5)], P["b"])
    p.poly([(hx + 1, hy - 3), (hx - snout + 4, hy - 0.5), (hx - 4, hy + 0.5)], P["l"])
    p.circ(hx - snout, hy + 1.5, 1.6, P["d"])
    if not proud:        # gruñido: colmillos a la vista
        p.line(hx - snout + 2, hy + 4, hx - 2, hy + 4.5, 1.2, P["d"])
        for x in (hx - snout + 4, hx - snout + 8):
            p.tri(x, hy + 3.5, 1, -2.6, WHITE)
    p.poly([(hx + 1, hy - 5), (hx + 4, hy - 15), (hx + 7, hy - 4)], P["b"])
    p.poly([(hx + 2.5, hy - 5), (hx + 4, hy - 11), (hx + 5.5, hy - 5)], P["d"])
    p.tube([(-14, 70), (-15 + st, 84), (-17 + st, 98)], 4.5, 2.8, P["b"])
    p.tube([(14, 66), (20 - st, 80), (16 - st, 90), (18 - st, 98)], 6, 2.8, P["b"])
    for x in (-17 + st, 18 - st):
        p.ell(x - 1.5, 99, 3.6, 1.6, P["d"])
    return [(hx - 3, hy - 1.5, 1.8, "dot")]


def _wolf_white(p, f, P):
    return _wolf(p, f, P, proud=True)


def _treant(p, f, P):
    sw = 2 if f else 0
    for s, x1 in ((-1, 26), (1, 24), (-1, 14), (1, 16)):          # raíces
        p.tube([(s * 8, 90), (s * (x1 - 6), 96), (s * x1, 100)], 4, 1.4, P["d"])
    p.poly([(-15, 100), (-11, 62), (-10, 40), (10, 40), (11, 62), (15, 100)], P["b"])
    p.poly([(4, 100), (8, 62), (9, 42), (10, 40), (11, 62), (15, 100)], P["d"])
    for x in (-7, -2, 6):
        p.lines([(x, 98), (x + 1, 84), (x - 1, 72)], 1.1, P["d"])
    # brazos-rama: uno ALZADO amenazando, otro bajo y adelantado
    arm = [(-9, 52), (-24, 44 - sw), (-32, 30 - sw)]
    p.tube(arm, 4.2, 2, P["b"])
    for tx, ty in ((-38, 22 - sw), (-29, 20 - sw), (-39, 33 - sw)):
        p.line(-32, 30 - sw, tx, ty, 1.5, P["b"])
    arm2 = [(9, 55), (22, 60 + sw), (29, 70 + sw)]
    p.tube(arm2, 4.2, 2, P["d"])
    for tx, ty in ((34, 76 + sw), (27, 78 + sw), (35, 68 + sw)):
        p.line(29, 70 + sw, tx, ty, 1.5, P["d"])
    # copa enfermiza
    for x, y, r, c in ((-14, 32, 12, "a"), (14, 30, 12, "a"), (0, 26, 16, "a"),
                       (-6, 16, 11, "a"), (9, 17, 10, "a"), (-5, 20, 7, "a2"),
                       (8, 24, 6, "a2"), (-14, 28, 5, "a2")):
        p.circ(x, y + (sw * 0.5 if x > 0 else 0), r, P[c])
    for x, y in ((-18, 40), (18, 38), (4, 38)):                       # hojas colgando
        p.tri(x, y, 2.5, -6, P["a"])
    # cara tallada en el tronco
    p.ell(-4.5, 51, 3.6, 3, P["hole"])
    p.ell(4.5, 51, 3.6, 3, P["hole"])
    p.poly([(-9, 46), (-1, 49), (-1, 47.5), (-8, 44)], P["d"])
    p.poly([(9, 46), (1, 49), (1, 47.5), (8, 44)], P["d"])
    p.poly([(-7, 60), (-4, 58), (-2, 61), (1, 58), (3, 61), (6, 58), (7, 61),
            (4, 67), (-4, 67)], P["hole"])
    return [(-4.5, 51, 2.0, "blank"), (4.5, 51, 2.0, "blank")]


def _vine(p, f, P):
    op = 3 if f else 0
    for pts, r in (([(8, 94), (20, 84), (27, 70), (22, 60)], 3),
                   ([(-8, 94), (-22, 88), (-32, 92), (-36, 86)], 2.6),
                   ([(14, 96), (30, 94), (36, 88)], 2.2)):
        p.tube(pts, r, 1, P["d"])
        for q in pts[1:-1]:
            p.tri(q[0], q[1] - r + 0.5, 1.2, 3.5, P["l"])
    stem = bz((0, 96), (-8, 74), (12, 56), (-4, 38), n=20)
    p.tube(stem, 5, 3.5, P["b"])
    for (x, y), s in (((-5, 76), -1), ((8, 60), 1), ((2, 86), 1)):   # hojas
        p.poly([(x, y), (x + s * 7, y - 6), (x + s * 13, y - 2), (x + s * 6, y + 2)], P["a"])
        p.line(x, y, x + s * 11, y - 2, 0.8, P["d"])
    p.ell(0, 97, 20, 5, P["a"])
    p.ell(-10, 95, 8, 3, P["l"])
    # cabeza-vaina con fauces abiertas mirando a la izquierda
    hx, hy = -6, 33
    p.ell(hx + 5, hy, 10, 9, P["b"])
    for x, y in ((hx + 8, hy - 4), (hx + 3, hy - 6), (hx + 10, hy + 2)):
        p.circ(x, y, 1.4, P["l"])
    p.poly([(hx + 2, hy - 7), (hx - 10, hy - 11 - op), (hx - 22, hy - 5 - op),
            (hx - 18, hy - 1), (hx + 2, hy - 1)], P["b"])
    p.poly([(hx + 1, hy + 2), (hx - 16, hy + 2), (hx - 20, hy + 7 + op),
            (hx - 6, hy + 10 + op * 0.5)], P["b"])
    p.poly([(hx + 1, hy - 2), (hx - 17, hy - 2 - op * 0.5), (hx - 16, hy + 2),
            (hx + 1, hy + 2)], P["mouth"])
    for x in (-19, -15, -11, -7):
        p.tri(hx + x + 2, hy - 2.5 - op * 0.3, 1.1, -3, WHITE)
        p.tri(hx + x + 3, hy + 2.5, 1.1, 3, WHITE)
    return [(hx + 1, hy - 5, 1.7, "dot")]


def _jelly(p, f, P):
    by = 44 if f == 0 else 47
    # tentáculos ondulantes
    for i, x0 in enumerate((-16, -10, -4, 4, 10, 16)):
        ph = f * 1.4 + i
        pts = [(x0 + math.sin(ph + j * 0.9) * 3.2, by + 6 + j * 7) for j in range(7)]
        p.tube(pts, 1.6, 0.6, P["d"])
    for s in (-1, 1):
        pts = [(s * 5 + math.sin(f * 1.6 + j + s) * 4, by + 6 + j * 6) for j in range(6)]
        p.tube(pts, 3.2, 1.2, P["a"])
    # campana
    dome = [(math.cos(math.pi + t * math.pi / 20) * 21,
             by + math.sin(math.pi + t * math.pi / 20) * 19) for t in range(21)]
    rim = [(21 - i * 3.5, by + 3 + (2 if i % 2 else 0)) for i in range(13)]
    p.poly(dome + rim, P["b"])
    p.ell(0, by - 6, 11, 8, P["a"])
    p.ell(0, by - 7, 7, 4, P["a2"])
    p.ell(-9, by - 12, 5, 3, P["l"])
    return [(-6, by - 2, 1.6, "blank"), (6, by - 2, 1.6, "blank")]


def _merfolk(p, f, P):
    sw = 2 if f else 0
    tail = bz((2, 66), (4, 86), (-12, 98), (18, 100), (30, 92), n=24)
    p.tube(tail, 10, 3, P["b"])
    p.tube(tail[4:18], 5, 2, P["l"])
    tx, ty = tail[-1]
    p.poly([(tx - 2, ty), (tx + 8, ty - 10 - sw), (tx + 5, ty), (tx + 10, ty + 7), (tx - 1, ty + 4)],
           P["a"])
    p.tube([(4, 48), (10, 58), (8, 65)], 3.2, 2.6, P["d"])            # brazo lejano
    p.tube([(2, 66), (0, 54), (-2, 44)], 10, 11, P["b"])
    p.ell(-4, 58, 6, 9, P["l"])
    for x, y in ((0, 50), (4, 56), (-2, 62), (3, 64), (6, 48)):
        p.circ(x, y, 1.3, P["d"])
    # aleta dorsal espinosa a lo largo de la cabeza y la espalda
    p.poly([(-2, 30), (4, 20), (5, 30), (10, 24), (9, 36), (14, 34), (11, 46), (15, 48),
            (10, 58), (6, 58), (6, 34)], P["a"])
    # cabeza de pez con boca enorme
    p.ell(-6, 36, 10, 9, P["b"])
    p.poly([(-8, 33), (-21, 35), (-19, 42), (-5, 43)], P["b"])
    p.poly([(-9, 37), (-20, 37.5), (-18, 40.5), (-8, 40)], P["mouth"])
    for x in (-18, -14, -10):
        p.tri(x, 37.2, 0.9, -2.2, WHITE)
    for x in (-1, 2):
        p.line(x, 34, x + 1, 42, 0.9, P["d"])
    # tridente de coral
    p.line(-20, 18, -18, 94, 2, P["w"])
    for dx in (-4, 0, 4):
        p.line(-20 + dx * 0.5, 20, -20 + dx, 12, 1.4, P["w"])
        p.tri(-20 + dx, 13, 1.3, 4, P["w"])
    p.line(-22, 21, -18, 20, 1.6, P["w"])
    p.tube([(-4, 48), (-12, 56 - sw), (-18, 52 - sw)], 3.6, 3, P["b"])
    p.circ(-19, 52 - sw, 3, P["d"])
    return [(-10, 33, 2.3, "dot")]


def _crab(p, f, P):
    st = 3 if f else 0
    for s in (-1, 1):                                     # patas en arco: 3 por lado
        for i, (kx, ky, fx) in enumerate(((40, 60, 46), (46, 66, 54), (38, 72, 40))):
            o = st if (i + (s > 0)) % 2 else -st
            p.tube([(s * 22, 76 + i * 2), (s * kx, ky + o), (s * fx, 99)],
                   3.8 - i * 0.3, 1.1, P["d"] if i == 1 else P["b"])
    # pinza derecha pequeña, baja
    p.tube([(20, 70), (32, 60), (34, 52)], 4, 3.6, P["b"])
    p.ell(35, 49, 7, 6, P["b"])
    p.poly([(38, 45), (44, 38 - st), (41, 47)], P["a"])
    p.poly([(39, 51), (46, 50), (40, 53)], P["a"])
    # caparazón ancho y bajo, con púas en el frente
    p.ell(0, 74, 34, 14, P["b"])
    p.ell(0, 69, 26, 7, P["l"])
    p.ell(0, 82, 24, 5, P["d"])
    for x in (-30, -22, 22, 30):
        p.tri(x, 66 + abs(x) * 0.12, 3, 6, P["b"], dx=x * 0.06)
    for x, y, r in ((-14, 68, 2.4), (-9, 71, 1.6), (12, 67, 2.2), (17, 72, 1.4)):
        p.circ(x, y, r, P["w"])
        p.circ(x, y, r * 0.45, P["d"])
    p.lines([(-6, 84), (0, 87), (6, 84)], 1.2, P["dd"])
    for s in (-1, 1):
        p.line(s * 6, 64, s * 8, 54, 2, P["b"])                    # pedúnculos
        p.circ(s * 8, 52, 3, P["b"])
    # pinza IZQUIERDA enorme, alzada al frente (asimetría del "violinista")
    p.tube([(-20, 70), (-32, 58), (-34, 48)], 6, 5.5, P["b"])
    p.ell(-36, 40, 13, 10, P["b"])
    p.ell(-37, 37, 8, 4.5, P["l"])
    p.poly([(-44, 34), (-52, 20 - st * 1.5), (-40, 30)], P["a"])   # dedo móvil
    p.poly([(-47, 40), (-60, 30), (-48, 34)], P["a"])              # dedo fijo
    return [(-8, 51, 2.4, "dot"), (8, 51, 2.4, "dot")]


def _sandman(p, f, P):
    tr = 3 if f else 0
    p.poly([(-32, 100), (-18, 84), (18, 84), (32, 100)], P["d"])
    p.ell(0, 97, 30, 5, P["b"])
    p.ell(-12, 94, 12, 3, P["l"])
    # brazo bajo y pesado
    p.tube([(-18, 54), (-27, 68), (-25, 84)], 7.5, 6.5, P["d"])
    p.circ(-25, 87, 7.5, P["d"])
    p.ell(1, 66, 19, 21, P["b"])
    for y in (60, 70, 79):
        p.lines([(-15, y), (-5, y + 2), (6, y), (16, y + 2)], 1.2, P["d"])
    for s in (-1, 1):
        p.circ(s * 16, 50, 9.5, P["b"])
    p.circ(-15, 48, 5, P["l"])
    for x, y in ((-8, 74), (10, 62), (4, 82)):
        p.poly([(x - 3, y), (x, y - 3), (x + 3, y - 1), (x + 2, y + 2)], P["a"])
    # brazo alzado, dejando caer arena
    p.tube([(18, 52), (28, 44), (30, 32)], 7.5, 7, P["b"])
    p.circ(30, 29, 7.5, P["b"])
    for i in range(4):
        p.circ(33 + (i % 2), 40 + i * 9 + tr, 1.3, P["l"])
    # cabeza-terrón, ladeada
    p.circ(-2, 38, 11, P["b"])
    p.circ(-5, 33, 6, P["l"])
    p.ell(-6.5, 39, 3.4, 3.8, P["hole"])
    p.ell(3, 39, 3.4, 3.8, P["hole"])
    p.poly([(-7, 46), (-2, 44.5), (4, 46.5), (0, 49)], P["hole"])
    return [(-6.5, 39.5, 1.9, "blank"), (3, 39.5, 1.9, "blank")]


def _scorpion(p, f, P):
    st = 2 if f else -2
    for i in range(4):                                     # patas lejanas
        bx = -12 + i * 7
        p.lines([(bx, 86), (bx - 5 + i * 3, 79), (bx - 9 + i * 4 + (st if i % 2 else -st), 99)],
                1.8, P["d"])
    p.tube([(-16, 82), (-25, 74), (-32, 73)], 2.6, 2.4, P["d"])  # pinza lejana
    p.ell(-36, 72, 5, 3.5, P["d"])
    p.poly([(-39, 70), (-46, 67), (-41, 72)], P["d"])
    # cola en arco sobre el lomo, aguijón apuntando adelante
    tail = bz((16, 84), (40, 78), (38, 44), (14, 42), (10, 54), n=22)
    for i, (x, y) in enumerate(tail):
        if i % 3 == 0:
            p.circ(x, y, 5 - i * 0.07, P["b"])
            p.circ(x - 1, y - 1.5, 2.2 - i * 0.04, P["l"])
    sx, sy = tail[-1]
    p.ell(sx + 1, sy, 4.5, 4, P["b"])
    p.poly([(sx - 1, sy + 2), (sx - 8, sy + 5), (sx - 3, sy + 8), (sx + 2, sy + 4)], P["a"])
    # cuerpo segmentado
    for x, r in ((12, 7), (3, 7.5), (-9, 8)):
        p.ell(x, 86, r + 2, 6.5, P["b"])
        p.line(x + r + 1, 81, x + r + 1, 91, 1, P["d"])
    p.ell(-6, 83, 12, 2.2, P["l"])
    for i in range(4):                                     # patas cercanas
        bx = -10 + i * 7
        p.lines([(bx, 88), (bx - 6 + i * 3, 80), (bx - 11 + i * 4 + (-st if i % 2 else st), 99)],
                2.1, P["b"])
    p.tube([(-18, 84), (-28, 78), (-35, 80)], 3.2, 3, P["b"])  # pinza cercana
    p.ell(-40, 80, 6.5, 4.5, P["b"])
    p.poly([(-44, 77), (-53, 74 - st), (-46, 80)], P["b"])
    p.poly([(-44, 82), (-52, 84), (-45, 84)], P["b"])
    return [(-16, 80.5, 1.5, "dot"), (-12.5, 80, 1.2, "dot")]


def _vulture(p, f, P):
    op = 8 if f else 0
    p.line(4, 84, 2, 99, 1.8, P["s"])
    p.line(11, 84, 11, 99, 1.8, P["s"])
    for x in (2, 11):
        p.lines([(x - 3, 100), (x, 98.5), (x + 3, 100)], 1.2, P["s"])
    p.poly([(14, 80), (30, 92), (24, 94), (12, 86)], P["d"])        # cola
    p.ell(4, 72, 15, 15, P["b"])
    # ala plegada/entreabierta con remeras dentadas
    wing = [(-6, 58), (8, 52 - op * 0.6), (26, 56 - op), (34, 66 - op), (38, 86 - op * 1.2),
            (33, 82 - op), (32, 90 - op), (27, 84 - op * 0.8), (25, 92 - op * 0.6), (20, 84),
            (8, 80)]
    p.poly(wing, P["b"])
    p.poly([(-4, 60), (8, 55 - op * 0.6), (24, 59 - op), (18, 68), (2, 70)], P["l"])
    for x in (22, 28):
        p.line(x, 70 - op * 0.8, x + 4, 84 - op, 1, P["d"])
    # gorguera clara y cuello pelado encorvado
    for x, y in ((-6, 58), (-2, 55), (-10, 61), (0, 61)):
        p.circ(x, y, 5, P["w"])
    p.tube([(-6, 56), (-12, 49), (-18, 45), (-22, 44)], 2.6, 2.2, P["s"])
    p.ell(-23, 42, 6, 5, P["s"])
    p.poly([(-27, 40), (-35, 42), (-34, 47), (-31, 45), (-27, 46)], P["a"])
    p.line(-28, 43.5, -33, 44, 0.8, P["d"])
    return [(-23, 40.5, 1.4, "dot")]


def _thunderbird(p, f, P):
    ang = 0.0 if f == 0 else 0.55
    y0 = 50 if f == 0 else 53
    for s in (-1, 1):
        w = [(8, y0 - 6), (24, y0 - 20), (44, y0 - 30), (58, y0 - 28), (51, y0 - 20),
             (56, y0 - 15), (46, y0 - 11), (50, y0 - 5), (38, y0 - 3), (38, y0 + 3),
             (26, y0 + 1), (14, y0 + 8)]
        w = _rot(w, ang, 8, y0 - 6)
        if s > 0:
            w = _rot(w, -0.12, 8, y0 - 6)
        pts = [(s * x, y) for x, y in w]
        p.poly(pts, P["b"])
        p.poly([pts[0], pts[1], pts[2], pts[3], pts[10], pts[11]], P["l"])
        p.lines([pts[1], (pts[2][0], pts[2][1] + 6), pts[4], (pts[6][0], pts[6][1] + 3)],
                1.6, P["a"])
    for dx, ln in ((-7, 28), (0, 34), (7, 28)):                  # cola en abanico
        p.poly([(dx * 0.4 - 2.5, y0 + 10), (dx - 3, y0 + ln - 6), (dx, y0 + ln),
                (dx + 3, y0 + ln - 6), (dx * 0.4 + 2.5, y0 + 10)], P["b"])
        p.line(dx * 0.5, y0 + 14, dx, y0 + ln - 3, 1, P["a"])
    p.ell(0, y0 + 1, 10, 15, P["b"])
    p.ell(0, y0 + 4, 6, 10, P["l"])
    for s in (-1, 1):
        p.lines([(s * 3, y0 + 14), (s * 4, y0 + 19), (s * 2, y0 + 21)], 1.4, P["a"])
    hy = y0 - 17
    for dx, h in ((-5, 9), (0, 13), (5, 9)):                     # cresta en zigzag
        p.poly([(dx - 2, hy - 4), (dx - 1 + dx * 0.3, hy - h), (dx + 1, hy - h + 4),
                (dx + 1.5 + dx * 0.4, hy - h - 2), (dx + 2, hy - 4)], P["a"])
    p.circ(0, hy, 7.5, P["b"])
    p.poly([(-3.5, hy + 2), (0, hy + 11), (3.5, hy + 2)], P["a"])
    p.line(0, hy + 3, 0, hy + 8, 0.8, P["d"])
    if f:                                                          # chispas
        for x, y in ((-20, y0 + 16), (22, y0 + 12), (-30, y0 - 26)):
            p.lines([(x, y), (x + 3, y + 3), (x + 1, y + 5), (x + 4, y + 8)], 1, P["a2"])
    return [(-3.2, hy - 1, 1.9, "blank"), (3.2, hy - 1, 1.9, "blank")]


def _elemental(p, f, P):
    bolts = [(-34, 32), (34, 28), (2, 14), (-24, 16), (26, 12)] if f == 0 else \
            [(-36, 40), (30, 20), (-6, 12), (18, 10), (38, 44)]
    for bx, by in bolts:
        mx, my = bx * 0.5, 52 + (by - 52) * 0.5
        p.lines([(0, 52), (mx + 4, my - 2), (mx - 3, my + 3), (bx, by)], 3.2, P["a"])
        p.lines([(0, 52), (mx + 4, my - 2), (mx - 3, my + 3), (bx, by)], 1.2, P["a2"])
    if f:
        p.lines([(2, 66), (-3, 76), (3, 82), (-2, 92), (1, 99)], 2.2, P["a2"])
    for x, y, r in ((-15, 60, 10), (15, 60, 10), (0, 64, 12), (-8, 50, 10), (9, 49, 11),
                    (-22, 66, 6), (22, 66, 6)):
        p.circ(x, y, r, P["b"])
    for x, y, r in ((-8, 46, 6), (9, 45, 6), (-17, 56, 4)):
        p.circ(x, y, r, P["l"])
    p.ell(0, 68, 16, 4, P["d"])
    p.circ(0, 53, 9, P["a"])
    p.circ(0, 53, 7, P["a2"])
    return [(-3, 52, 1.7, "dot"), (3, 52, 1.7, "dot")]


def _specter(p, f, P, sym=False):
    sw = 3 if f else -3
    y0 = 0 if f == 0 else 2
    wide = 1.35 if sym else 1.0
    if sym:                                          # capa como alas de tela
        for s in (-1, 1):
            p.poly([(s * 8, 40 + y0), (s * 34, 56 + y0 - s * 2), (s * 30, 74 + y0),
                    (s * 26, 68 + y0), (s * 22, 80 + y0), (s * 12, 70 + y0)], P["d"])
    body = [(-10, 38), (-17 * wide, 56), (-15 * wide, 72), (-10, 82), (-8 + sw, 92),
            (-4, 84), (0 + sw, 96), (4, 84), (10 + sw, 90), (11 * wide, 72), (15 * wide, 56),
            (10, 38)]
    p.poly([(x, y + y0) for x, y in body], P["b"])
    p.poly([(x, y + y0) for x, y in ((-6, 44), (-9, 64), (-4, 80), (0, 60))], P["l"])
    # brazos largos con garras hacia delante
    p.tube([(-10, 46 + y0), (-22, 52 + y0), (-31, 48 + y0 - sw * 0.5)], 3, 1.8, P["b"])
    for d in (-3, 0, 3):
        p.line(-31, 48 + y0 - sw * 0.5, -36, 46 + y0 + d - sw * 0.5, 0.9, P["l"])
    p.tube([(10, 46 + y0), (20, 56 + y0), (22, 64 + y0)], 3, 1.8, P["d"])
    top = 18 if sym else 22
    p.poly([(-10, 36 + y0), (-2, top + y0), (4, top + 3 + y0), (10, 36 + y0)], P["b"])
    p.circ(0, 34 + y0, 10, P["b"])
    p.ell(-1, 36 + y0, 6.5, 7.5, P["hole"])
    if sym:                                          # los DOS TRIÁNGULOS del emblema
        cy = 56 + y0
        p.poly([(-7, cy + 4), (0, cy - 8), (7, cy + 4)], P["a"])
        p.poly([(-7, cy - 4), (0, cy + 8), (7, cy - 4)], P["a2"])
        p.poly([(-4, cy + 1.5), (0, cy - 4), (4, cy + 1.5)], P["b"])
    else:                                            # jirones de nube de tormenta
        for x, y in ((-8, 42), (0, 44), (8, 42)):
            p.circ(x, y + y0, 4, P["a"])
        p.lines([(12, 60 + y0), (16, 64 + y0), (13, 67 + y0), (17, 72 + y0)], 1,
                P["a2"])
    return [(-4, 35 + y0, 1.8, "blank"), (2, 35 + y0, 1.8, "blank")]


def _specter2(p, f, P):
    return _specter(p, f, P, sym=True)


def _yeti(p, f, P):
    sw = 2 if f else 0
    for s in (-1, 1):
        p.tube([(s * 10, 80), (s * 12, 97)], 8, 7, P["d"] if s > 0 else P["b"])
        p.ell(s * 13, 98.5, 9, 3, P["s"])
    # brazo derecho (del bicho) ALZADO rugiendo
    p.tube([(21, 46), (33, 36 - sw), (35, 22 - sw)], 8.5, 7, P["d"])
    p.circ(36, 19 - sw, 7.5, P["s"])
    p.ell(0, 62, 24, 24, P["b"])
    p.ell(-2, 66, 14, 15, P["l"])
    for s in (-1, 1):
        p.circ(s * 18, 45, 12, P["b"])
    for x, y in ((-30, 42), (-26, 36), (28, 38), (-22, 82), (22, 82), (-12, 86), (12, 86)):
        p.tri(x, y + 3, 3, 6, P["b"], dx=(-2 if x < 0 else 2))
    # brazo izquierdo largo hasta casi el suelo
    p.tube([(-21, 48), (-32, 64 + sw), (-32, 83 + sw)], 9, 7, P["b"])
    p.circ(-32, 88 + sw, 7, P["s"])
    for x in (-36, -32, -28):
        p.line(x, 92 + sw, x - 1, 95 + sw, 1.2, P["dd"])
    # cabeza hundida entre los hombros, cuernos de hielo
    for s in (-1, 1):
        p.tube(bz((s * 6, 30), (s * 14, 28), (s * 15, 18)), 2.6, 1, P["a"])
    p.circ(0, 36, 10.5, P["b"])
    p.ell(0, 40, 7.5, 6.5, P["s"])
    p.poly([(-8, 34), (-1, 37), (1, 37), (8, 34), (6, 32), (-6, 32)], P["dd"])
    p.ell(0, 44, 4.5, 2.8, P["mouth"])
    for s in (-1, 1):
        p.tri(s * 2.5, 41.8, 1, -3.2, WHITE)
        p.tri(s * 2, 46.5, 0.9, 2.4, WHITE)
    return [(-3.6, 38.5, 1.7, "dot"), (3.6, 38.5, 1.7, "dot")]


def _shade_crawler(p, f, P):
    sw = 2 if f else 0
    p.poly([(-4, 62), (12, 70 - sw), (30, 80), (46, 84 + sw), (38, 90), (24, 94),
            (4, 98), (-14, 96), (-20, 86)], P["b"])
    for x, y, r in ((30, 88, 5), (40, 86 + sw, 3.5), (16, 94, 5)):
        p.circ(x, y, r, P["d"])
    p.tube([(-12, 78), (-26, 88), (-38, 96 - sw)], 4.2, 2, P["b"])
    for d in (-3, 0, 3):
        p.line(-38, 96 - sw, -44, 98 + d * 0.6 - sw, 0.9, P["l"])
    p.tube([(0, 82), (-10, 92), (-18, 99)], 3.4, 1.8, P["d"])
    p.circ(-10, 70, 14, P["b"])
    p.circ(-15, 65, 6, P["l"])
    p.lines([(-22, 60), (-8, 56), (6, 64), (22, 72), (40, 80)], 1.1, P["a"])
    p.ell(-13, 68, 9, 5, P["hole"])
    return [(-17, 67.5, 1.8, "blank"), (-9, 67, 1.6, "blank")]


def _fallen(p, f, P):
    sw = 2 if f else 0
    p.tube([(12, 30), (6, 50), (0, 98)], 1.4, 1.4, P["w"])        # báculo roto al hombro
    p.poly([(9, 26), (15, 22), (14, 32)], P["a"])
    p.poly([(-6, 44), (8, 46), (20, 56), (24, 76), (26, 98), (20, 94), (16, 99), (10, 94),
            (4, 99), (-2, 94), (-8, 99), (-12, 80), (-16, 62)], P["b"])
    p.poly([(-4, 50), (6, 52), (14, 62), (4, 64)], P["l"])
    p.poly([(-10, 66), (18, 62), (19, 66), (-10, 71)], P["a"])     # fajín rasgado
    p.poly([(-12, 71), (-9, 71), (-7, 80), (-10, 79)], P["a"])
    p.tube([(4, 58), (-2, 74), (-6, 90)], 2.6, 2, P["d"])
    # cabeza encapuchada, adelantada y baja
    p.ell(-12, 48, 10.5, 10, P["b"])
    p.poly([(-4, 40), (8, 36), (2, 48)], P["b"])
    p.ell(-15, 50, 6, 7, P["hole"])
    # brazo esquelético que se arrastra hasta el suelo
    p.tube([(-10, 56), (-22, 70), (-26, 88 + sw)], 2.8, 2, P["s"])
    for d in (-3, 0, 3):
        p.line(-26, 88 + sw, -30 + d, 97, 0.9, P["s"])
    return [(-17.5, 49.5, 1.5, "blank"), (-13, 49.5, 1.3, "blank")]


def _cherub(p, f, P):
    fl = 0.0 if f == 0 else 0.35
    y0 = 50 if f == 0 else 52
    for s in (-1, 1):
        for up in (True, False):
            if up:
                w = [(8, y0 - 4), (22, y0 - 20), (38, y0 - 26), (34, y0 - 18), (38, y0 - 14),
                     (30, y0 - 10), (32, y0 - 5), (20, y0 - 2)]
                w = _rot(w, fl, 8, y0 - 4)
            else:
                w = [(8, y0 + 6), (22, y0 + 12), (32, y0 + 22), (26, y0 + 20), (26, y0 + 25),
                     (18, y0 + 18), (14, y0 + 20)]
                w = _rot(w, -fl * 0.7, 8, y0 + 6)
            pts = [(s * x, y) for x, y in w]
            p.poly(pts, P["w"])
            p.lines(pts[:3], 1.2, P["wd"])
    p.circ(0, y0, 13, P["b"])
    for x, y in ((-10, y0 - 9), (-5, y0 - 12), (1, y0 - 13), (7, y0 - 11), (11, y0 - 7)):
        p.circ(x, y, 3.6, P["a"])
    p.ell(0, y0 - 25, 12, 3, P["a"])
    p.ell(0, y0 - 25.5, 9, 1.7, (0, 0, 0, 0))
    for s in (-1, 1):
        p.circ(s * 8, y0 + 4, 2.4, P["l"])
    p.ell(0, y0 + 7, 1.8, 2.2, P["hole"])
    return [(-5, y0, 2.1, "blank"), (5, y0, 2.1, "blank")]


def _guardian(p, f, P):
    op = 3 if f else 0
    p.poly([(4, 60), (22, 26 - op), (36, 14 - op), (40, 26 - op), (34, 30 - op),
            (40, 38 - op), (32, 42 - op), (36, 52), (26, 56), (28, 64)], P["d"])   # ala lejana
    p.tube(bz((24, 90), (40, 96), (44, 84)), 2.4, 1.6, P["b"])
    p.circ(44, 82, 3.4, P["a"])
    p.ell(12, 84, 15, 13, P["b"])
    p.ell(16, 97, 13, 3, P["d"])
    p.tube([(-6, 72), (-8, 98)], 5, 4.4, P["d"])
    # ala cercana alzada, plumas escalonadas
    wing = [(-2, 62), (14, 28 - op), (28, 12 - op), (32, 20 - op), (28, 26 - op),
            (34, 32 - op), (26, 38 - op), (30, 46 - op), (20, 52), (22, 62), (10, 68)]
    p.poly(wing, P["w"])
    for q in (wing[3], wing[5], wing[7]):
        p.line(4, 60, q[0], q[1], 1, P["d"])
    p.ell(-6, 68, 12, 14, P["b"])
    p.ell(-9, 70, 7, 10, P["l"])
    p.tube([(-12, 72), (-13, 98)], 5.2, 4.6, P["b"])
    p.ell(-16, 99, 6.5, 2.5, P["b"])
    # melena dorada y máscara de mármol
    for a in range(8):
        t = -2.4 + a * 0.62
        p.circ(-10 + math.cos(t) * 11, 48 + math.sin(t) * 11, 5.2, P["a"])
    p.circ(-10, 48, 10, P["a2"])
    p.ell(-14, 49, 8, 9, P["b"])
    p.poly([(-16, 48), (-25, 52), (-24, 57), (-14, 57)], P["b"])
    p.line(-24, 55, -17, 55.5, 0.9, P["d"])
    p.tri(-12, 38, 2, 8, P["a"])
    return [(-17, 46.5, 1.6, "blank")]


def _ophan(p, f, P):
    ph = 0.0 if f == 0 else 0.4
    eyes = []
    for s in (-1, 1):
        p.poly([(s * 6, 48), (s * 30, 26), (s * 38, 30), (s * 26, 42), (s * 34, 46),
                (s * 20, 54)], P["w"])
    for ang, rx, ry, n in ((0.35, 30, 11, 5), (-1.05, 28, 10, 4)):
        pts = _ring_pts(0, 52, rx, ry, ang, 36, ph)
        p.lines(pts, 4.4, P["a"])
        p.lines(pts, 1.4, P["a2"])
        for i in range(n):
            t = ph + 2 * math.pi * (i + 0.5) / n
            c, sn = math.cos(ang), math.sin(ang)
            x, y = rx * math.cos(t), ry * math.sin(t)
            eyes.append((x * c - y * sn, 52 + x * sn + y * c, 2.4, "sclera"))
    p.circ(0, 52, 7.5, P["l"])
    eyes.append((0, 52, 4.2, "sclera"))
    return eyes


def _dragon(p, f, P):
    up = -5 if f else 0
    bob = 1 if f else 0
    # ALAS: membrana TRANSLÚCIDA con dedos óseos (la derecha algo más baja)
    for s in (-1, 1):
        dy = 0 if s < 0 else 3
        sh, el = (s * 16, 50 + dy), (s * 40, 30 + up * 0.5 + dy)
        wr, tip = (s * 60, 12 + up + dy), (s * 100, 22 + up + dy)
        fing = [(s * 96, 52 + up * 0.6 + dy), (s * 80, 68 + dy), (s * 60, 74 + dy),
                (s * 38, 70 + dy)]
        memb = [sh, el, wr, tip, fing[0], (s * 88, 56 + dy), fing[1], (s * 70, 66 + dy),
                fing[2], (s * 50, 66 + dy), fing[3], (s * 26, 62 + dy)]
        p.poly(memb, P["m"])
        p.poly([sh, el, wr, (s * 76, 38 + dy), (s * 50, 54 + dy), (s * 28, 58 + dy)], P["m2"])
        for q in (tip, fing[0], fing[1], fing[2]):
            p.tube([wr, q], 2.0, 0.7, P["md"])
        p.tube([sh, el, wr], 4.2, 2.6, P["md"])
        p.tube([sh, el, wr], 2.6, 1.4, P["d"])
        p.tri(wr[0], wr[1], 2.2, 7, P["a"], dx=s * 2)
    # COLA con púas y punta de lanza
    tail = bz((8, 86), (40, 104), (72, 98), (86, 78), (78, 62), n=26)
    p.tube(tail, 10, 2, P["md"])
    p.tube(tail, 9, 1.4, P["b"])
    for q in tail[4:-3:4]:
        p.tri(q[0], q[1] - 6, 2, 5, P["a"])
    tx, ty = tail[-1]
    p.poly([(tx - 5, ty + 3), (tx - 2, ty - 10), (tx + 1, ty - 3), (tx + 6, ty + 1), (tx, ty)],
           P["a"])
    # PATAS traseras: muslo, caña y garras doradas
    for s in (-1, 1):
        p.ell(s * 20, 78, 11, 12, P["d"])
        p.tube([(s * 24, 84), (s * 28, 92), (s * 26, 98)], 6.4, 5, P["d"])
        p.ell(s * 27, 99, 7.5, 2.6, P["d"])
        for dd in (-4, 0, 4):
            p.tri(s * 27 + dd - s * 2, 100.5, 1.4, -3.4, P["a"], dx=-s * 1.2)
    # TRONCO con placas pectorales y escamas
    p.ell(0, 66 + bob, 27, 23, P["md"])
    p.ell(0, 66 + bob, 26, 22, P["b"])
    p.ell(-8, 58 + bob, 12, 8, P["l"])
    p.ell(0, 75 + bob, 14, 15, P["pl"])
    for yy in (65, 71, 77, 83):
        p.lines([(-11, yy + bob), (0, yy + 2 + bob), (11, yy + bob)], 1, P["d"])
    for x, yy in ((-18, 62), (-20, 70), (18, 60), (20, 68), (-14, 54), (14, 54)):
        p.ell(x, yy + bob, 2.2, 1.4, P["d"])
    for s in (-1, 1):                                   # brazos delanteros
        p.ell(s * 14, 70 + bob, 6.5, 7.5, P["b"])
        p.tube([(s * 14, 72), (s * 18, 86), (s * 16, 98)], 6, 4.4, P["b"])
        p.ell(s * 17, 99, 5.5, 2.2, P["b"])
        for dd in (-3, 0, 3):
            p.tri(s * 17 + dd, 100.5, 1.1, -3, P["a"])
    # TRES cuellos en S, con placas de garganta y púas dorsales
    necks = [((-10, 54), (-32, 52), (-22, 34), (-42, 28)),
             ((10, 54), (32, 58), (26, 40), (46, 36)),
             ((0, 50), (9, 40), (-8, 28), (-2, 18))]
    heads = [(-45, 25 + bob, -1), (49, 34 - bob, 1), (-2, 12 + bob * 0.5, 0)]
    eyes = []
    for nk, (hx, hy, d) in zip(necks, heads):
        pts = bz(*nk, n=20)
        p.tube(pts, 10.6, 7, P["md"])
        p.tube(pts, 9.2, 5.6, P["b"])
        thr = [(x + (0 if d == 0 else d * -1.5), y + (2.5 if d else 0)) for x, y in pts]
        p.tube(thr, 4.2, 2.4, P["pl"])
        for i, q in enumerate(pts[2:-3:3]):
            p.tri(q[0] - d * 2, q[1] - 7 + i * 0.3, 1.8, 5, P["a"])
        eyes += _dragon_head(p, hx, hy, d, P, roar=(d == 1) != bool(f))
    return eyes


def _dragon_head(p, hx, hy, d, P, roar=False):
    if d == 0:                                          # cabeza central, de frente
        for s in (-1, 1):
            p.tube(bz((hx + s * 4, hy - 4), (hx + s * 10, hy - 10), (hx + s * 8, hy - 18)),
                   2.6, 0.6, P["a"])
            p.tube([(hx + s * 7, hy - 1), (hx + s * 13, hy - 4)], 1.5, 0.5, P["a2"])
        p.ell(hx, hy, 9.4, 8.4, P["md"])
        p.ell(hx, hy, 8, 7, P["b"])
        p.ell(hx, hy + 7, 5.5, 5, P["b"])
        p.ell(hx, hy + 12, 4.4, 2.8, P["jaw"])
        p.ell(hx, hy + 10.6, 3.8, 1.6, P["a2"] if roar else P["mouth"])
        for s in (-1, 1):
            p.circ(hx + s * 2, hy + 7.5, 0.9, P["d"])
            p.tri(hx + s * 2.6, hy + 9.6, 0.8, -2.4, WHITE)
            p.poly([(hx + s * 8.5, hy - 3.5), (hx + s * 1.5, hy - 1.2), (hx + s * 2.5, hy + 0.5)],
                   P["d"])
        return [(hx - 3.6, hy + 0.8, 1.9, "blank"), (hx + 3.6, hy + 0.8, 1.9, "blank")]
    jo = 5.5 if roar else 1.2
    p.tube(bz((hx - d * 2, hy - 5), (hx - d * 9, hy - 12), (hx - d * 17, hy - 10)), 2.6, 0.6,
           P["a"])                                              # cuerno mayor, hacia atrás
    p.tube([(hx + d * 1, hy - 6), (hx - d * 4, hy - 13)], 1.5, 0.5, P["a2"])
    p.ell(hx, hy, 9.6, 8, P["md"])
    p.poly([(hx + d * 1, hy + 3), (hx + d * 16, hy + 3 + jo), (hx + d * 15, hy + 6.5 + jo),
            (hx - d * 1, hy + 7.5)], P["md"])
    p.ell(hx, hy, 8, 6.5, P["b"])
    p.poly([(hx + d * 3, hy - 4.5), (hx + d * 15, hy - 2), (hx + d * 18, hy + 0.5),
            (hx + d * 16, hy + 2.8), (hx + d * 3, hy + 2.8)], P["b"])
    p.poly([(hx + d * 2, hy + 3), (hx + d * 15, hy + 3 + jo), (hx + d * 14, hy + 5.8 + jo),
            (hx, hy + 6.6)], P["jaw"])                          # mandíbula aparte
    p.poly([(hx + d * 3, hy + 2.8), (hx + d * 16, hy + 2.8), (hx + d * 14.5, hy + 3.2 + jo),
            (hx + d * 3, hy + 3.8)], P["a2"] if roar else P["mouth"])
    for k in (7, 10.5, 14):
        p.tri(hx + d * k, hy + 2.6, 0.8, -2.2, WHITE)
        if roar:
            p.tri(hx + d * (k - 1), hy + 3.4 + jo * k / 16, 0.7, 1.8, WHITE)
    p.circ(hx + d * 16.5, hy - 0.5, 0.8, P["d"])
    p.poly([(hx - d * 1, hy - 6), (hx + d * 9, hy - 3.6), (hx + d * 2, hy - 2.4)], P["d"])
    p.tri(hx - d * 5, hy + 5, 1.6, -4, P["a"], dx=-d * 3)       # espolón de la mejilla
    return [(hx + d * 4.5, hy - 2.2, 1.8, "blank")]


def _angel(p, f, P):
    """Ángel de la Luz: sereno e INQUIETANTE (sin boca, ojos de oro, dos halos)."""
    fl = 0.0 if f == 0 else 0.10
    y0 = 0 if f == 0 else 1
    for s in (-1, 1):                                   # alas por CAPAS de plumas
        sh = (s * 8, 40 + y0)
        arm = _rot(bz(sh, (s * 20, 12 + y0), (s * 42, 4 + y0), n=16), s * fl, sh[0], sh[1])
        for t0, t1, n, l0, l1, wdt, cols in ((0.45, 1.0, 6, 34, 46, 5.2, ("w2", "w")),
                                              (0.10, 0.62, 5, 26, 32, 5.6, ("w", "w2")),
                                              (0.0, 0.92, 7, 11, 14, 4.8, ("l", "l"))):
            for i in range(n):
                t = t0 + (t1 - t0) * i / max(1, n - 1)
                j = min(len(arm) - 1, int(t * (len(arm) - 1)))
                bx, by = arm[j]
                dx, dy = s * (0.1 + 0.75 * t), 1.0
                m = math.hypot(dx, dy)
                dx, dy = dx / m, dy / m
                ln = l0 + (l1 - l0) * t
                for grow, col in ((1.25, P["wd"]), (1.0, P[cols[i % 2]])):
                    w_ = wdt * grow
                    L = ln + (1.2 if grow > 1 else 0)
                    px_, py_ = -dy * w_, dx * w_
                    pts = [(bx - px_ * 0.5, by - py_ * 0.5)]
                    for u, wd_ in ((0.45, 1.0), (0.78, 0.85), (0.93, 0.5)):
                        pts.append((bx + dx * L * u - px_ * wd_, by + dy * L * u - py_ * wd_))
                    pts.append((bx + dx * L, by + dy * L))
                    for u, wd_ in ((0.93, 0.5), (0.78, 0.85), (0.45, 1.0)):
                        pts.append((bx + dx * L * u + px_ * wd_, by + dy * L * u + py_ * wd_))
                    pts.append((bx + px_ * 0.5, by + py_ * 0.5))
                    p.poly(pts, col)
                p.line(bx, by, bx + dx * ln * 0.8, by + dy * ln * 0.8, 0.6, P["wd"])
        p.tube(arm, 3.6, 1.8, P["l"])
    # túnica larga con pliegues; flota sobre el suelo
    hem = [(19 - i * 38 / 8, 93 + (3 if i % 2 else 0) + y0) for i in range(9)]
    p.poly([(-11, 40 + y0), (-13, 60 + y0), (-17, 80 + y0)] + hem[::-1] +
           [(17, 80 + y0), (13, 60 + y0), (11, 40 + y0)], P["b"])
    p.poly([(3, 44 + y0), (13, 60 + y0), (17, 80 + y0), (19, 93 + y0), (6, 95 + y0),
            (5, 62 + y0)], P["d"])
    for x0, x1 in ((-5, -10), (-1, -2), (6, 10)):
        p.line(x0, 60 + y0, x1, 93 + y0, 1.1, P["fold"])
    p.line(-8, 62 + y0, -13, 88 + y0, 1.2, P["l"])
    p.poly([(-12, 56 + y0), (12, 56 + y0), (12.5, 60 + y0), (-12.5, 60 + y0)], P["a"])
    p.tube([(2, 60 + y0), (3, 70 + y0), (5, 80 + y0)], 1.4, 1, P["a"])
    p.lines([(-6, 40 + y0), (0, 47 + y0), (6, 40 + y0)], 1.3, P["a"])      # cuello en V
    for s in (-1, 1):                                   # mangas y manos juntas
        p.poly([(s * 11, 41 + y0), (s * 15, 49 + y0), (s * 11, 57 + y0), (s * 2, 55 + y0),
                (s * 5, 47 + y0)], P["l"] if s < 0 else P["d"])
    p.circ(0, 53 + y0, 2.8, P["s"])
    # melena, rostro de porcelana (sin boca) y DOS halos perfectos
    p.ell(0, 33 + y0, 10.4, 12.4, P["wd"])
    p.ell(0, 33 + y0, 9.4, 11.4, P["h"])
    p.poly([(-9, 30 + y0), (-12, 48 + y0), (-4, 44 + y0), (4, 44 + y0), (12, 48 + y0),
            (9, 30 + y0)], P["h"])
    p.tube([(0.5, 34 + y0), (0.5, 39 + y0)], 2.4, 2.4, P["s"])
    p.circ(0.5, 28 + y0, 8.2, P["sd"])
    p.circ(0.5, 28 + y0, 7.6, P["s"])
    p.poly([(-8, 26 + y0), (-7, 20 + y0), (0, 18 + y0), (8, 20 + y0), (9, 26 + y0),
            (4, 22.5 + y0), (-3, 23 + y0)], P["h"])
    p.line(-6, 24.8 + y0, 7, 24.8 + y0, 0.9, P["a"])
    for s in (-1, 1):
        p.line(s * 2.8 + 0.5, 30.5 + y0, s * 2.8 + 0.5, 35 + y0, 0.7, P["a"])
    p.lines(_ring_pts(0.5, 13 + y0, 12, 3.4, 0.0, 32), 2.0, P["a"])
    p.lines(_ring_pts(0.5, 7 + y0, 7, 2, 0.0, 24), 1.1, P["a2"])
    return [(-2.4, 28.5 + y0, 1.6, "blank"), (3.4, 28.5 + y0, 1.6, "blank")]


# ════════════════════════════════════════════════════════════════════════
#  ESPECIFICACIONES: paleta, extensión (x0, x1, top), escala de mapa, etc.
# ════════════════════════════════════════════════════════════════════════
def _c(fn, pal, ext, ow_k, eye, bsc=1.0, fly=False, alpha=255, shw=16, size=64,
       rate=None, glow=None):
    return {"fn": fn, "pal": pal, "ext": ext, "ow_k": ow_k, "eye": eye, "bsc": bsc,
            "fly": fly, "alpha": alpha, "shw": shw, "size": size, "rate": rate,
            "glow": glow}


SPECS = {
    # ── VOLCÁN (fuego)
    "bat_fire": _c(_bat, {"b": (74, 34, 36), "d": (40, 16, 20), "l": (120, 60, 50),
                          "m": (150, 44, 30), "a": (255, 140, 40), "a2": (255, 230, 120)},
                   (-52, 52, 14), 0.36, (255, 200, 60), bsc=0.8, fly=True, shw=10),
    "salamander": _c(_salamander, {"b": (214, 78, 40), "d": (130, 36, 24), "l": (252, 190, 90),
                                   "a": (255, 150, 40), "a2": (255, 238, 140),
                                   "tongue": (240, 60, 90)},
                     (-50, 62, 42), 0.40, (255, 230, 80), bsc=0.9, shw=26),
    "magma_dog": _c(_magma_dog, {"b": (72, 52, 50), "d": (38, 26, 28), "l": (110, 80, 70),
                                 "a": (255, 120, 30), "a2": (255, 225, 110)},
                    (-50, 46, 34), 0.44, (255, 190, 50), shw=26),
    # ── BOSQUE (planta)
    "treant": _c(_treant, {"b": (104, 76, 52), "d": (62, 44, 32), "a": (58, 96, 44),
                           "a2": (96, 134, 58), "hole": (26, 16, 12)},
                 (-42, 38, 4), 0.56, (250, 220, 70), shw=18),
    "wolf_forest": _c(_wolf, {"b": (116, 96, 70), "d": (66, 54, 42), "l": (170, 150, 120),
                              "a": (78, 112, 52)},
                      (-52, 42, 46), 0.44, (220, 236, 80), shw=24),
    "vine": _c(_vine, {"b": (66, 140, 60), "d": (36, 86, 40), "l": (150, 200, 90),
                       "a": (48, 118, 50), "mouth": (180, 40, 60)},
               (-38, 38, 18), 0.48, (255, 220, 60), bsc=0.95, shw=20),
    # ── MAR (agua)
    "jelly": _c(_jelly, {"b": (120, 190, 235), "d": (80, 130, 200), "l": (220, 245, 255),
                         "a": (235, 120, 190), "a2": (255, 200, 235)},
                (-24, 24, 22), 0.42, (230, 255, 255), bsc=0.85, fly=True, alpha=215, shw=12),
    "merfolk": _c(_merfolk, {"b": (48, 138, 150), "d": (24, 80, 96), "l": (150, 214, 200),
                             "a": (236, 110, 118), "w": (240, 200, 170),
                             "mouth": (70, 20, 40)},
                  (-26, 42, 8), 0.48, (255, 225, 80), shw=20),
    "crab": _c(_crab, {"b": (74, 98, 168), "d": (40, 50, 104), "l": (132, 164, 214),
                       "a": (240, 130, 96), "w": (224, 218, 196), "dd": (22, 26, 60)},
               (-62, 58, 18), 0.50, (255, 240, 120), shw=36),
    # ── CAÑÓN (tierra)
    "sandman": _c(_sandman, {"b": (214, 178, 112), "d": (158, 118, 70), "l": (242, 216, 160),
                             "a": (120, 86, 52), "hole": (60, 38, 20)},
                  (-36, 40, 18), 0.56, (100, 225, 255), shw=26),
    "scorpion": _c(_scorpion, {"b": (172, 104, 44), "d": (100, 56, 26), "l": (224, 162, 82),
                               "a": (210, 40, 40)},
                   (-56, 44, 34), 0.42, (255, 80, 60), shw=26),
    "vulture": _c(_vulture, {"b": (82, 62, 46), "d": (44, 32, 26), "l": (124, 98, 72),
                             "w": (232, 222, 200), "s": (210, 124, 112), "a": (230, 212, 170)},
                  (-38, 40, 34), 0.46, (220, 60, 40), shw=16),
    # ── TORMENTA (rayo)
    "thunderbird": _c(_thunderbird, {"b": (38, 50, 112), "d": (20, 24, 60), "l": (74, 96, 170),
                                     "a": (246, 214, 60), "a2": (255, 250, 190)},
                      (-60, 60, 8), 0.40, (255, 255, 170), fly=True, shw=12),
    "elemental": _c(_elemental, {"b": (92, 96, 124), "d": (54, 56, 80), "l": (140, 146, 176),
                                 "a": (246, 214, 60), "a2": (255, 252, 214)},
                    (-40, 40, 8), 0.42, (40, 30, 90), fly=True, shw=14),
    "specter": _c(_specter, {"b": (170, 182, 208), "d": (100, 104, 140), "l": (222, 230, 246),
                             "a": (96, 100, 130), "a2": (246, 222, 90), "hole": (30, 30, 52)},
                  (-38, 26, 18), 0.44, (170, 240, 255), fly=True, alpha=220, shw=12),
    # ── PICO (hielo)
    "yeti": _c(_yeti, {"b": (230, 236, 246), "d": (164, 176, 204), "l": (250, 252, 255),
                       "s": (92, 112, 152), "a": (150, 212, 246), "dd": (40, 50, 80),
                       "mouth": (60, 20, 40)},
               (-42, 44, 14), 0.60, (255, 196, 60), shw=24),
    "wolf_white": _c(_wolf_white, {"b": (226, 232, 242), "d": (150, 164, 192),
                                   "l": (250, 252, 255), "a": (170, 214, 248)},
                     (-46, 44, 26), 0.46, (110, 220, 255), shw=24),
    "bat_ice": _c(_bat_ice, {"b": (70, 84, 122), "d": (36, 44, 76), "l": (150, 170, 210),
                             "m": (120, 170, 220), "a": (200, 236, 255), "a2": (240, 250, 255),
                             "fang": (220, 245, 255)},
                  (-54, 54, 14), 0.36, (140, 240, 255), bsc=0.8, fly=True, shw=10),
    # ── CRIPTA (sombra)
    "shade": _c(_shade_crawler, {"b": (34, 28, 46), "d": (16, 12, 24), "l": (64, 54, 86),
                                 "a": (150, 70, 210), "hole": (8, 4, 12)},
                (-46, 48, 54), 0.46, (220, 120, 255), alpha=225, shw=28),
    "fallen": _c(_fallen, {"b": (62, 52, 72), "d": (28, 22, 34), "l": (96, 82, 108),
                           "s": (146, 154, 132), "a": (132, 40, 60), "w": (110, 84, 60),
                           "hole": (10, 6, 14)},
                 (-34, 28, 20), 0.46, (255, 70, 70), shw=20),
    "specter2": _c(_specter2, {"b": (44, 38, 66), "d": (22, 18, 36), "l": (84, 74, 116),
                               "a": (232, 200, 90), "a2": (176, 84, 232), "hole": (6, 4, 12)},
                   (-38, 38, 16), 0.50, (255, 236, 170), fly=True, alpha=230, shw=14),
    # ── SANTUARIO (luz)
    "cherub": _c(_cherub, {"b": (246, 236, 226), "l": (240, 190, 190), "a": (232, 196, 90),
                           "w": (250, 248, 240), "wd": (190, 186, 206), "hole": (120, 70, 80)},
                 (-40, 40, 18), 0.38, (255, 214, 90), bsc=0.8, fly=True, shw=10),
    "guardian": _c(_guardian, {"b": (240, 236, 226), "d": (178, 170, 162), "l": (255, 255, 250),
                               "w": (250, 248, 238), "a": (228, 188, 80), "a2": (250, 226, 140)},
                   (-28, 48, 10), 0.52, (120, 200, 255), shw=24),
    "ophan": _c(_ophan, {"a": (226, 186, 80), "a2": (255, 238, 160), "l": (255, 252, 230),
                         "w": (250, 248, 240)},
                (-40, 40, 18), 0.42, (70, 140, 230), fly=True, shw=12),
    # ── JEFE: Dragón de Luz (tres cabezas) — sirve al Mago Blanco
    "dragon": _c(_dragon, {"b": (240, 234, 216), "d": (176, 164, 140), "l": (255, 253, 244),
                           "pl": (252, 236, 190), "a": (226, 186, 72), "a2": (255, 236, 170),
                           "m": (246, 228, 176, 175), "m2": (255, 248, 222, 205),
                           "md": (150, 120, 76), "jaw": (206, 194, 170), "mouth": (96, 44, 40)},
                 (-102, 102, 0), 0.62, (120, 210, 255), shw=44, size=128,
                 glow=((255, 240, 180), 0, 52, 62, 70)),
    # ── NPC: Ángel de la Luz (sanador raro; su luz es la del Blanco)
    "angel": _c(_angel, {"b": (244, 242, 236), "d": (196, 196, 210), "l": (255, 255, 252),
                         "fold": (176, 176, 196), "a": (230, 190, 80), "a2": (255, 232, 150),
                         "w": (250, 249, 244), "w2": (222, 224, 236), "wd": (170, 170, 192),
                         "s": (250, 242, 234), "sd": (196, 182, 176), "h": (214, 194, 146)},
                (-62, 62, 0), 0.44, (255, 222, 120), fly=True, shw=14, size=96, rate=430,
                glow=((255, 244, 200), 0, 48, 50, 60)),
}
CREATURE_IDS = list(SPECS)

_NAMES = {
    "murcielago igneo": "bat_fire", "salamandra": "salamander", "can de magma": "magma_dog",
    "arbol maligno": "treant", "lobo del bosque": "wolf_forest", "enredadera": "vine",
    "medusa": "jelly", "sirenido": "merfolk", "cangrejo coloso": "crab",
    "hombre de arena": "sandman", "escorpion": "scorpion", "buitre": "vulture",
    "ave trueno": "thunderbird", "elemental de rayo": "elemental", "espectro": "specter",
    "yeti": "yeti", "lobo blanco": "wolf_white", "murcielago helado": "bat_ice",
    "sombra errante": "shade", "acolito caido": "fallen",
    "espectro de los dos triangulos": "specter2", "querubin palido": "cherub",
    "guardian de luz": "guardian", "vigia sagrado": "ophan", "dragon de luz": "dragon",
    "angel de la luz": "angel",
}
_ELEM_DEFAULT = {"fuego": "magma_dog", "planta": "wolf_forest", "agua": "crab",
                 "tierra": "scorpion", "rayo": "thunderbird", "hielo": "yeti",
                 "sombra": "shade", "luz": "guardian"}


def _norm(s):
    s = unicodedata.normalize("NFD", str(s or "").lower())
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return s.split(" (")[0].strip()


def creature_id(ent):
    """id de criatura para un dict de rpg.py (enemigo del mapa o del combate), o None."""
    if isinstance(ent, str):
        return ent if ent in SPECS else _NAMES.get(_norm(ent))
    if not isinstance(ent, dict):
        return None
    if ent.get("dragon"):
        return "dragon"
    if ent.get("angel"):
        return "angel"
    cid = _NAMES.get(_norm(ent.get("name")))
    if cid:
        return cid
    if ent.get("kind") == "ambient":
        return _ELEM_DEFAULT.get(ent.get("elem"), "shade")
    return None


# ════════════════════════════════════════════════════════════════════════
#  COMPOSICIÓN
# ════════════════════════════════════════════════════════════════════════
_VIOLET = (170, 50, 220)


def _corrupt(pal):
    out = {}
    for key, c in pal.items():
        if len(c) > 3:
            out[key] = c
            continue
        g = c[0] * 0.3 + c[1] * 0.59 + c[2] * 0.11
        if key in ("a", "a2"):                 # brillos -> fuego violeta
            tgt = (min(255, g * 0.8 + 70), g * 0.25 + 10, min(255, g * 0.9 + 90))
            out[key] = lerp(c, tgt, 0.85)
        else:
            tgt = (g * 0.55 + 16, g * 0.36 + 6, g * 0.72 + 28)
            out[key] = lerp(c, tgt, 0.8)
    return out


def _mask_ring(surf, grow, color, thresh=60):
    m = pygame.mask.from_surface(surf, thresh)
    w, h = surf.get_size()
    dil = pygame.mask.Mask((w, h))
    for dx in range(-grow, grow + 1):
        for dy in range(-grow, grow + 1):
            if dx * dx + dy * dy <= grow * grow + (1 if grow == 1 else 0):
                dil.draw(m, (dx, dy))
    dil.erase(m, (0, 0))
    return dil.to_surface(setcolor=color, unsetcolor=(0, 0, 0, 0))


def _eyes(out, eyes, k, cx, feet, col, dark):
    for x, y, r, st in eyes:
        X, Y = cx + x * k, feet + (y - 100) * k
        R = r * k
        if dark:
            g = pygame.Surface((int(R * 6) + 6, int(R * 6) + 6), pygame.SRCALPHA)
            gc = g.get_width() / 2
            pygame.draw.circle(g, (255, 60, 230, 70), (gc, gc), R * 2.4 + 1.5)
            pygame.draw.circle(g, (255, 90, 240, 120), (gc, gc), R * 1.5 + 0.8)
            out.blit(g, (X - gc, Y - gc))
            col2, core = (255, 110, 245), (255, 220, 255)
        else:
            col2, core = col, None
        if R < 1.25:
            ix, iy = int(X), int(Y)
            if 0 <= ix < out.get_width() and 0 <= iy < out.get_height():
                out.set_at((ix, iy), core or col2)
            continue
        if st == "sclera" and not dark:
            pygame.draw.circle(out, WHITE, (X, Y), R)
            pygame.draw.circle(out, col2, (X, Y), max(1, R * 0.6))
            pygame.draw.circle(out, (14, 10, 20), (X - R * 0.1, Y), max(1, R * 0.28))
        else:
            pygame.draw.circle(out, col2, (X, Y), R)
            if core:
                pygame.draw.circle(out, core, (X, Y), max(1, R * 0.45))
            elif st == "dot" and R >= 1.8:
                pygame.draw.circle(out, (18, 10, 12), (X - R * 0.35, Y), max(1, R * 0.45))
            elif st == "blank" and R >= 1.8:
                pygame.draw.circle(out, (255, 255, 240), (X - R * 0.3, Y - R * 0.3),
                                   max(1, R * 0.35))


def _render(cid, k, frame, dark, max_w=None):
    """Dibuja la criatura MIRANDO A LA IZQUIERDA. -> (surf, ax, ay)."""
    spec = SPECS[cid]
    x0, x1, top = spec["ext"]
    if max_w and (x1 - x0) * k + 6 > max_w:
        k = (max_w - 6) / (x1 - x0)
    W = int((x1 - x0) * k) + 6
    H = int((103 - top) * k) + 5
    cx, feet = 3 - x0 * k, H - 3
    pal = _corrupt(spec["pal"]) if dark else spec["pal"]
    big = pygame.Surface((W * SS, H * SS), pygame.SRCALPHA)
    eyes = spec["fn"](_P(big, k * SS, cx * SS, feet * SS), frame, pal) or []
    fig = pygame.transform.smoothscale(big, (W, H))
    if spec["alpha"] < 255:
        fig.fill((255, 255, 255, spec["alpha"]), special_flags=pygame.BLEND_RGBA_MULT)
    out = pygame.Surface((W, H), pygame.SRCALPHA)
    # sombra de suelo (más pequeña y tenue si vuela)
    sw = spec["shw"] * 2 * k * (0.8 if spec["fly"] and frame else 1.0)
    sh = max(3, sw * 0.24)
    s = pygame.Surface((int(sw) + 2, int(sh) + 2), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (18, 14, 24, 80 if spec["fly"] else 115), s.get_rect())
    out.blit(s, (cx - s.get_width() / 2, feet - s.get_height() / 2 - 0.5))
    if spec.get("glow"):
        gcol, gx, gy, gr, ga = spec["glow"]
        if dark:
            gcol = (190, 80, 230)
        gX, gY, gR = cx + gx * k, feet + (gy - 100) * k, gr * k
        gl = pygame.Surface((W, H), pygame.SRCALPHA)
        for i in range(8, 0, -1):
            pygame.draw.circle(gl, gcol + (int(ga * (1 - i / 9) ** 1.6),), (gX, gY), gR * i / 8)
        out.blit(gl, (0, 0))
    if dark:
        out.blit(_mask_ring(fig, 3 if k > 0.7 else 2, _VIOLET + (90,)), (0, 0))
    out.blit(_mask_ring(fig, 1, OUTLINE + (255,)), (0, 0))
    out.blit(fig, (0, 0))
    _eyes(out, eyes, k, cx, feet, spec["eye"], dark)
    return out, cx, feet


def _norm_facing(facing):
    if isinstance(facing, (tuple, list)):
        return "right" if facing[0] > 0 else "left"
    return "right" if str(facing) in ("right", "e", "east") else "left"


def get_overworld(cid, facing="left", frame=0, dark=False):
    """Sprite de mapa. -> (surf, ax, ay); (ax, ay) = suelo bajo la criatura."""
    fac = _norm_facing(facing)
    key = ("ow", cid, fac, int(frame) % 2, bool(dark))
    r = _CACHE.get(key)
    if r is None:
        if fac == "right":
            s, ax, ay = get_overworld(cid, "left", frame, dark)
            r = (pygame.transform.flip(s, True, False), s.get_width() - ax, ay)
        else:
            r = _render(cid, SPECS[cid]["ow_k"], int(frame) % 2, bool(dark))
        _CACHE[key] = r
    return r


def get_battle(cid, frame=0, dark=False, size=None):
    """Sprite de combate (idle de 2 frames). size = alto de la caja (64; 128 el dragón)."""
    spec = SPECS[cid]
    size = int(size or spec["size"])
    key = ("bt", cid, int(frame) % 2, bool(dark), size)
    r = _CACHE.get(key)
    if r is None:
        x0, x1, top = spec["ext"]
        k = (size - 8) / (103 - top) * spec["bsc"]
        r = _render(cid, k, int(frame) % 2, bool(dark), max_w=int(size * 1.75))
        _CACHE[key] = r
    return r


def _frame_for(cid, key, moving):
    t = pygame.time.get_ticks() + (key * 97) % 700
    if SPECS[cid].get("rate"):
        return (t // SPECS[cid]["rate"]) % 2
    if SPECS[cid]["fly"]:
        return (t // 170) % 2
    return (t // (200 if moving else 560)) % 2


def blit_overworld(screen, ent, px, py, bob, camx, camy, tile=32, dark=None):
    """Dibuja la criatura en la casilla (px, py). False si `ent` no es criatura."""
    cid = creature_id(ent)
    if cid is None:
        return False
    k = id(ent)
    last = _MOTION.get(k)
    facing = last[2] if last else ("right" if (k >> 4) % 2 else "left")
    moving = False
    if last:
        dx = px - last[0]
        if abs(dx) > 1e-3:
            facing = "right" if dx > 0 else "left"
        moving = abs(dx) > 1e-3 or abs(py - last[1]) > 1e-3
    _MOTION[k] = (px, py, facing)
    s, ax, ay = get_overworld(cid, facing, _frame_for(cid, k, moving),
                              _DARK if dark is None else dark)
    fly_bob = 0 if SPECS[cid]["fly"] else bob
    screen.blit(s, (int(px * tile + tile // 2 - camx - ax),
                    int(py * tile + tile + fly_bob - camy - ay - 1)))
    return True


def blit_battle(screen, ent, x, y, flash=False, dark=None):
    """Sprite de combate centrado en (x, y). Devuelve su semialtura o None."""
    cid = creature_id(ent)
    if cid is None:
        return None
    fly = SPECS[cid]["fly"]
    fr = (pygame.time.get_ticks() // (260 if fly else 520)) % 2
    s, ax, ay = get_battle(cid, fr, _DARK if dark is None else dark)
    if flash:
        s = s.copy()
        s.fill((150, 150, 150, 0), special_flags=pygame.BLEND_RGBA_ADD)
    sw = screen.get_width()                  # que las alas no se salgan de la pantalla
    bx = max(2, min(sw - s.get_width() - 2, x - s.get_width() // 2))
    screen.blit(s, (bx, y - s.get_height() // 2))
    return s.get_height() // 2 - 4


def battle_center(ent, x, screen_w=640):
    """x corregida para que el sprite de combate quepa en pantalla (el dragón es ancho).
    Úsala ANTES de dibujar barra y nombre para que queden centrados con el sprite."""
    cid = creature_id(ent)
    if cid is None:
        return x
    s = get_battle(cid, 0, False)[0]
    half = s.get_width() // 2 + 2
    return max(half, min(screen_w - half, x))


def portrait_for_speaker(name, size=80):
    """Retrato enmarcado para el diálogo si el hablante es una criatura (ángel...)."""
    cid = _NAMES.get(_norm(name))
    if cid is None:
        return None
    key = ("pt", cid, int(size))
    r = _CACHE.get(key)
    if r is not None:
        return r
    spec = SPECS[cid]
    x0, x1, top = spec["ext"]
    k = size / 40.0
    fig, ax, ay = _render(cid, k, 0, False)
    # encuadre: cabeza y hombros (ojos hacia el tercio superior)
    ey = min(e[1] for e in spec["fn"](_P(pygame.Surface((4, 4), pygame.SRCALPHA), 1, 2, 2), 0,
                                     spec["pal"]))
    cy = ay + (ey - 100) * k
    out = pygame.Surface((size, size), pygame.SRCALPHA)
    top_c, bot_c = (250, 236, 190), (70, 80, 130)
    for y in range(size):
        pygame.draw.line(out, lerp(top_c, bot_c, y / max(1, size - 1)), (0, y), (size, y))
    out.blit(fig, (size / 2 - ax, size * 0.42 - cy))
    mask = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=max(4, size // 8))
    out.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    pygame.draw.rect(out, OUTLINE, out.get_rect(), max(2, size // 24) + 1,
                     border_radius=max(4, size // 8))
    pygame.draw.rect(out, (226, 190, 90), out.get_rect().inflate(-2, -2), max(1, size // 32),
                     border_radius=max(4, size // 8))
    _CACHE[key] = out
    return out
