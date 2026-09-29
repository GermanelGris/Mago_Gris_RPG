"""rpg_endings.py — una ANIMACIÓN distinta por final del RPG 2D (pygame, por código).

ENDING_ANIMS[ekey](surf, t) dibuja el fotograma en el instante t (segundos,
0..DUR). Las funciones NO guardan estado: todo (partículas incluidas) se deriva
de t y de semillas fijas, así cualquier fotograma se puede renderizar suelto y
el port a Godot puede replicarlo igual (misma línea de tiempo, mismas fases).

play(ekey, screen, clock, present) reproduce la animación (saltable con
Enter/Espacio/E/Esc o A/Start del mando) y vuelve; después rpg.py sigue con su
cinemática de frases y el epílogo de siempre.
"""
import math
import random
import sys

import pygame

try:
    import rpg_sprites as RS
except Exception:                                   # importado como games.rpg_endings
    from games import rpg_sprites as RS

DUR = 15.0
MAGAS = ["fuego", "planta", "agua", "tierra", "rayo", "hielo"]
ELEM_COL = {"fuego": (235, 95, 45), "planta": (70, 185, 85), "agua": (70, 150, 235),
            "tierra": (185, 145, 75), "rayo": (235, 225, 95), "hielo": (155, 212, 235)}
TITLES = {
    "pacto": "LOS HILOS INVISIBLES", "gris_sacrificio": "EL GRIS ENTRE DOS LUCES",
    "negro_sacrificio": "DOS HERMANOS", "blanco": "EL NUEVO ORDEN",
    "oscuro": "LA SOMBRA REINA", "feliz": "UN MUNDO LIBRE", "_": "UN MUNDO SIN AMOS",
    "fuego": "ERA DE FUEGO", "planta": "ERA DE VIDA", "agua": "ERA DE CALMA",
    "tierra": "ERA FIRME", "rayo": "ERA RADIANTE", "hielo": "ERA SERENA",
}


# ════════════════════════════════════════════════════════════════════════
#  utilidades (todas deterministas)
# ════════════════════════════════════════════════════════════════════════
def _cl(x):
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def seg(t, a, b):
    """Progreso 0..1 de la fase [a, b] con suavizado (smoothstep)."""
    x = _cl((t - a) / (b - a)) if b > a else float(t >= a)
    return x * x * (3 - 2 * x)


def lerp(a, b, x):
    return a + (b - a) * x


def lerpc(c1, c2, x):
    x = _cl(x)
    return tuple(int(a + (b - a) * x) for a, b in zip(c1, c2))


_GRAD = {}


def gradient(surf, top, bot):
    w, h = surf.get_size()
    key = (w, h, top, bot)
    g = _GRAD.get(key)
    if g is None:
        g = pygame.Surface((w, h))
        for y in range(h):
            pygame.draw.line(g, lerpc(top, bot, y / max(1, h - 1)), (0, y), (w, y))
        if len(_GRAD) > 64:
            _GRAD.clear()
        _GRAD[key] = g
    surf.blit(g, (0, 0))


_GLOW = {}


def glow(surf, x, y, r, col, a=90):
    """Halo aditivo suave (color premultiplicado; a = intensidad 0..255)."""
    r = int(max(2, r))
    a = int(_cl(a / 255) * 16) / 16                 # cuantizado para la caché
    if a <= 0:
        return
    key = (r, col, a)
    g = _GLOW.get(key)
    if g is None:
        g = pygame.Surface((r * 2, r * 2))
        g.fill((0, 0, 0))
        n = 8
        for i in range(n, 0, -1):
            f = a * 0.16 * (1 - (i - 1) / n)        # cada anillo suma: centro más brillante
            acc = [int(c * f * (n - i + 1) / 1) for c in col]
            pygame.draw.circle(g, tuple(min(255, v) for v in acc), (r, r), int(r * i / n))
        if len(_GLOW) > 300:
            _GLOW.clear()
        _GLOW[key] = g
    surf.blit(g, (int(x) - r, int(y) - r), special_flags=pygame.BLEND_RGB_ADD)


_SPR = {}


def sprite(cid, size=96, poss=False, alpha=255, gray=0.0, tint=None, frame=0):
    """Sprite de combate (frente) con alpha / desaturación / tinte, cacheado."""
    key = (cid, size, poss, int(alpha) // 8, round(gray, 1), tint, frame)
    s = _SPR.get(key)
    if s is None:
        s = RS.get_battle(cid, poss, frame, size=size).copy()
        if gray > 0:
            g = pygame.transform.grayscale(s)
            g.set_alpha(int(255 * gray))
            s = s.copy()
            s.blit(g, (0, 0))
        if tint:
            t = pygame.Surface(s.get_size(), pygame.SRCALPHA)
            t.fill(tint + (0,))
            s.blit(t, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
        if alpha < 255:
            s.fill((255, 255, 255, int(alpha)), special_flags=pygame.BLEND_RGBA_MULT)
        if len(_SPR) > 400:
            _SPR.clear()
        _SPR[key] = s
    return s


def put(surf, s, x, feet):
    """Blit anclado por los pies (centro-abajo)."""
    surf.blit(s, (int(x - s.get_width() / 2), int(feet - s.get_height() + 2)))


def particles(surf, t, n, seed, fn):
    """fn(i, rnd, t) -> (x, y, r, col, a) o None. rnd = lista de 6 aleatorios fijos."""
    rng = random.Random(seed)
    layer = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
    for i in range(n):
        rnd = [rng.random() for _ in range(6)]
        p = fn(i, rnd, t)
        if p:
            x, y, r, col, a = p
            if a > 0:
                pygame.draw.circle(layer, col + (int(_cl(a / 255) * 255),), (x, y), max(1, r))
    surf.blit(layer, (0, 0))


def veil(surf, col, a):
    if a <= 0:
        return
    v = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
    v.fill(col + (int(_cl(a / 255) * 255),))
    surf.blit(v, (0, 0))


def seal(surf, cx, cy, rx, ry, t, col, a=255):
    """Sello en el suelo: dos anillos elípticos con runas que giran."""
    lay = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
    c = col + (int(a),)
    pygame.draw.ellipse(lay, c, (cx - rx, cy - ry, 2 * rx, 2 * ry), 2)
    pygame.draw.ellipse(lay, c, (cx - rx * 0.72, cy - ry * 0.72, 1.44 * rx, 1.44 * ry), 1)
    for i in range(12):
        ang = t * 0.6 + i * math.pi / 6
        x, y = cx + math.cos(ang) * rx * 0.86, cy + math.sin(ang) * ry * 0.86
        pygame.draw.line(lay, c, (x - 3, y), (x + 3, y), 2)
    # triángulos (luz arriba, sombra abajo) inscritos
    for k, rot in ((0, -math.pi / 2), (1, math.pi / 2)):
        pts = [(cx + math.cos(rot + j * 2 * math.pi / 3 + t * 0.2 * (1 - 2 * k)) * rx * 0.7,
                cy + math.sin(rot + j * 2 * math.pi / 3 + t * 0.2 * (1 - 2 * k)) * ry * 0.7)
               for j in range(3)]
        pygame.draw.polygon(lay, c, pts, 1)
    surf.blit(lay, (0, 0))


def thread(surf, p0, p1, tension, col, a=220, w=1):
    """Hilo de marioneta: curva que cuelga (tension 0) o tensa y recta (1)."""
    sag = (1 - tension) * 70
    mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2 + sag
    pts = []
    for i in range(13):
        u = i / 12
        x = (1 - u) ** 2 * p0[0] + 2 * (1 - u) * u * mx + u * u * p1[0]
        y = (1 - u) ** 2 * p0[1] + 2 * (1 - u) * u * my + u * u * p1[1]
        pts.append((x, y))
    lay = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
    pygame.draw.lines(lay, col + (int(a),), False, pts, w)
    surf.blit(lay, (0, 0))


def ground(surf, y, col, col2=None):
    w, h = surf.get_size()
    pygame.draw.rect(surf, col, (0, y, w, h - y))
    if col2:
        pygame.draw.line(surf, col2, (0, y), (w, y), 2)


# ════════════════════════════════════════════════════════════════════════
#  LOS FINALES
# ════════════════════════════════════════════════════════════════════════
def anim_pacto(surf, t):
    """Salón dorado. El Gris se inclina ante el Blanco; las seis magas vuelven a
    su sitio y desde lo alto bajan hilos que se TENSAN sobre ellas. Al final un
    último hilo aparece sobre los hombros del Gris."""
    W, H = surf.get_size()
    gradient(surf, (60, 48, 30), (18, 14, 10))
    glow(surf, W // 2, 90, 170, (255, 220, 140), 70)
    ground(surf, 360, (40, 32, 22), (120, 96, 50))
    # trono y Blanco arriba (sonríe: se mantiene quieto, gran halo)
    pygame.draw.rect(surf, (150, 120, 60), (W // 2 - 50, 170, 100, 12))
    put(surf, sprite("blanco", 128), W // 2, 250)
    hand = (W // 2 + 30, 150)
    # el Gris se acerca e inclina (baja un poco y se oscurece)
    k = seg(t, 0.5, 4)
    gx, gf = lerp(W // 2 - 160, W // 2 - 20, k), lerp(430, 330, k)
    bow = seg(t, 4, 5.5)
    put(surf, sprite("gris", int(96 - 8 * bow)), gx, gf)
    # magas aparecen en fila
    xs = [70 + i * 100 for i in range(6)]
    for i, el in enumerate(MAGAS):
        a = seg(t, 3 + i * 0.4, 4 + i * 0.4)
        if a <= 0:
            continue
        ten = seg(t, 6 + i * 0.35, 8.5 + i * 0.35)
        lift = -6 * ten * (0.5 + 0.5 * math.sin(t * 2.2 + i))      # bailan colgadas
        feet = 460 + lift
        head = (xs[i], feet - 60)
        if ten > 0:
            thread(surf, hand, head, ten, (255, 236, 170), 200 * a)
        put(surf, sprite(el, 72, alpha=255 * a, gray=0.35 * ten), xs[i], feet)
    # último hilo: el Gris
    g = seg(t, 10.5, 13)
    if g > 0:
        thread(surf, hand, (gx, gf - 70), g, (255, 245, 200), 230)
        glow(surf, int(gx), int(gf - 66), 18, (255, 240, 190), 120 * g)
    veil(surf, (255, 240, 200), 160 * seg(t, 13.5, 15))


def anim_gris_sacrificio(surf, t):
    """El Gris flota sobre el sello y se disuelve en él (partículas grises en
    espiral). El Blanco y el Negro, a los lados, pierden su color y se funden en
    un pilar gris; seis luces de color quedan en el cielo: el mundo conserva los
    colores."""
    W, H = surf.get_size()
    gray = seg(t, 7, 12)
    gradient(surf, lerpc((20, 20, 40), (90, 90, 96), gray), lerpc((6, 6, 14), (40, 40, 44), gray))
    ground(surf, 380, (22, 22, 30))
    cx, cy = W // 2, 400
    seal(surf, cx, cy, 190, 42, t, (200, 200, 215), 200)
    # Blanco (izq) y Negro (der) se acercan y se funden
    m = seg(t, 6, 11)
    for cid, side in (("blanco", -1), ("negro", 1)):
        x = cx + side * lerp(200, 20, m)
        put(surf, sprite(cid, 104, alpha=255 * (1 - seg(t, 10, 12)), gray=round(gray, 1)), x, 400)
    # el Gris sobre el sello, se disuelve
    d = seg(t, 2, 8)
    fy = 330 - 20 * math.sin(t * 1.5) * (1 - d)
    put(surf, sprite("gris", 104, alpha=255 * (1 - d)), cx, fy + 60 * d)

    def spiral(i, r, tt):
        st = 2 + r[0] * 5
        if tt < st:
            return None
        u = _cl((tt - st) / 2.5)
        ang = r[1] * 6.28 + u * 6
        rad = (1 - u) * (30 + r[2] * 40)
        return (cx + math.cos(ang) * rad * 2.2, fy - 40 + u * 110 + math.sin(ang) * rad * 0.5,
                2, (190, 190, 205), 255 * (1 - u))
    particles(surf, t, 90, 7, spiral)
    # pilar gris
    p = seg(t, 10, 12.5)
    if p > 0:
        glow(surf, cx, 300, int(60 + 60 * p), (170, 170, 180), 110 * p)
        pygame.draw.rect(surf, (200, 200, 208), (cx - 6 * p, 0, 12 * p, 400))
    # los seis colores permanecen
    c = seg(t, 12, 14)
    for i, el in enumerate(MAGAS):
        x = 90 + i * 92
        glow(surf, x, 70 + 10 * math.sin(t + i), 26, ELEM_COL[el], 140 * c)


def anim_negro_sacrificio(surf, t):
    """El Blanco yace vencido junto al sello. El Negro camina hasta él, lo alza
    y lo abraza; los dos se hunden juntos en el sello. Luz y sombra se apagan a
    la vez y amanece un cielo gris."""
    W, H = surf.get_size()
    dawn = seg(t, 11, 14.5)
    gradient(surf, lerpc((24, 16, 34), (130, 130, 138), dawn), lerpc((8, 6, 12), (70, 70, 76), dawn))
    horizon = 380
    ground(surf, horizon, (20, 18, 26))
    cx = W // 2
    seal(surf, cx, 400, 150, 34, t, (180, 160, 220), 220 * (1 - seg(t, 10, 12)))
    walk = seg(t, 0.5, 5)
    nx = lerp(W - 60, cx + 26, walk)
    rise = seg(t, 5, 6.5)                      # el Blanco se incorpora en el abrazo
    sink = seg(t, 7.5, 11)
    clip = pygame.Rect(0, 0, W, 402)           # se hunden: se recortan bajo el sello
    lay = pygame.Surface((W, H), pygame.SRCALPHA)
    b = sprite("blanco", 104)
    if rise < 1:
        br = pygame.transform.rotate(b, 90 * (1 - rise))
        lay.blit(br, (cx - 30 - br.get_width() / 2, 402 - br.get_height() + 2 + 80 * sink))
    else:
        put(lay, b, cx - 18, 402 + 80 * sink)
    step = int(t * 3) % 2 if walk < 1 else 0
    put(lay, sprite("negro", 104, frame=step), nx, 402 + 80 * sink)
    surf.blit(lay, (0, 0), area=clip)
    # destellos: blanco y negro que se apagan a la vez
    a = seg(t, 6.5, 8) * (1 - seg(t, 10, 12))
    glow(surf, cx - 20, 340, 70, (255, 250, 230), 120 * a)
    glow(surf, cx + 20, 340, 70, (150, 90, 200), 120 * a)
    if dawn > 0:
        glow(surf, cx, horizon, int(160 * dawn), (200, 200, 205), 90 * dawn)


def anim_blanco(surf, t):
    """El Gris sube los peldaños hasta el trono de luz; al sentarse aparece la
    corona y de ella salen hilos dorados hacia el pueblo diminuto de abajo. El
    oro lo invade todo: el Orden cambió de amo."""
    W, H = surf.get_size()
    gold = seg(t, 8, 14)
    gradient(surf, lerpc((40, 36, 50), (120, 96, 40), gold), (14, 12, 16))
    cx = W // 2
    # escalinata
    for i in range(6):
        y = 380 - i * 24
        w = 420 - i * 50
        pygame.draw.rect(surf, lerpc((90, 86, 96), (200, 170, 90), gold), (cx - w // 2, y, w, 24))
        pygame.draw.line(surf, (40, 36, 44), (cx - w // 2, y), (cx + w // 2, y), 1)
    # trono
    pygame.draw.rect(surf, (230, 200, 110), (cx - 44, 150, 88, 92), border_radius=8)
    pygame.draw.rect(surf, (255, 240, 180), (cx - 34, 160, 68, 60), border_radius=6)
    glow(surf, cx, 190, 110, (255, 230, 140), 60 + 80 * gold)
    # el Gris sube
    k = seg(t, 0.5, 6)
    steps = k * 6
    fy = 404 - min(5.0, steps) * 24 - (24 if k >= 1 else 0) * 0
    gs = sprite("gris", 96, tint=(int(60 * gold), int(50 * gold), 0), frame=int(t * 3) % 2 if k < 1 else 0)
    put(surf, gs, cx, fy - 6 * math.sin(k * math.pi * 6) if k < 1 else 262)
    head = (cx, (262 if k >= 1 else fy) - 88)
    # corona
    c = seg(t, 6.5, 7.5)
    if c > 0:
        cy = head[1] - 6
        pts = [(cx - 16, cy + 8), (cx - 16, cy - 4), (cx - 8, cy + 2), (cx, cy - 10),
               (cx + 8, cy + 2), (cx + 16, cy - 4), (cx + 16, cy + 8)]
        pygame.draw.polygon(surf, lerpc((0, 0, 0), (250, 210, 90), c), pts)
        glow(surf, cx, cy, 30, (255, 230, 150), 150 * c)
    # pueblo diminuto y los hilos de la corona
    for i in range(14):
        x = 30 + i * 45
        vy = 470
        pygame.draw.rect(surf, (30, 26, 34), (x - 5, vy - 16, 10, 16))
        pygame.draw.circle(surf, (30, 26, 34), (x, vy - 20), 5)
        th = seg(t, 8 + i * 0.2, 10.5 + i * 0.2)
        if th > 0:
            thread(surf, (cx, head[1] - 10), (x, vy - 24), th, (255, 225, 130), 200)
    veil(surf, (255, 235, 170), 150 * seg(t, 13.5, 15))


def anim_oscuro(surf, t):
    """El Gris, poseído por el poder que acaparó, en el centro. Su sombra se
    expande desde los pies (borde vivo, irregular) y se traga una a una las seis
    luces de color; al final solo queda un triángulo violeta... y es gris."""
    W, H = surf.get_size()
    gradient(surf, (40, 38, 50), (16, 14, 20))
    cx, cy = W // 2, 330
    R = lerp(10, 520, seg(t, 1, 11))
    orbs = [(cx + math.cos(i * math.pi / 3 - math.pi / 2) * 220,
             cy - 80 + math.sin(i * math.pi / 3 - math.pi / 2) * 150) for i in range(6)]
    for i, (x, y) in enumerate(orbs):
        eaten = math.hypot(x - cx, (y - cy) * 1.4) < R * 0.95
        if not eaten:
            glow(surf, int(x), int(y), 28, ELEM_COL[MAGAS[i]], 170)
            pygame.draw.circle(surf, ELEM_COL[MAGAS[i]], (int(x), int(y)), 7)
    pts = []
    for i in range(48):
        a = i / 48 * 6.283
        r = R * (1 + 0.08 * math.sin(a * 5 + t * 3) + 0.05 * math.sin(a * 11 - t * 5))
        pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r * 0.72))
    lay = pygame.Surface((W, H), pygame.SRCALPHA)
    pygame.draw.polygon(lay, (14, 6, 22, 235), pts)
    pygame.draw.lines(lay, (150, 60, 200, 200), True, pts, 2)
    surf.blit(lay, (0, 0))
    put(surf, sprite("gris", 112, poss=seg(t, 2, 3) > 0.5), cx, cy + 20)
    tri = seg(t, 11, 13)
    if tri > 0:
        s = 150
        p = [(cx, 60), (cx - s, 60 + s * 1.5), (cx + s, 60 + s * 1.5)]
        lay = pygame.Surface((W, H), pygame.SRCALPHA)
        pygame.draw.polygon(lay, (170, 170, 180, int(200 * tri)), p, 3)
        surf.blit(lay, (0, 0))
    veil(surf, (0, 0, 0), 180 * seg(t, 13.5, 15))


def anim_feliz(surf, t):
    """Amanecer. El sol sale sobre una colina y, uno a uno, llegan caminando las
    seis magas, el Mago Negro redimido y el Gris; al juntarse estallan pétalos
    de todos los colores."""
    W, H = surf.get_size()
    d = seg(t, 0, 8)
    gradient(surf, lerpc((20, 24, 60), (120, 180, 240), d), lerpc((40, 30, 60), (250, 190, 130), d))
    sun_y = lerp(420, 150, d)
    glow(surf, W // 2, int(sun_y), 120, (255, 220, 150), 120)
    pygame.draw.circle(surf, (255, 236, 170), (W // 2, int(sun_y)), 36)
    pygame.draw.ellipse(surf, lerpc((20, 40, 30), (80, 150, 70), d), (-80, 360, W + 160, 260))
    order = ["gris"] + MAGAS[:3] + ["negro"] + MAGAS[3:]
    for i, cid in enumerate(order):
        st = 2 + i * 0.7
        k = seg(t, st, st + 1.6)
        if k <= 0:
            continue
        tx = 60 + i * 74
        x = lerp(-60 if i < 4 else W + 60, tx, k)
        bob = -abs(math.sin(t * 7)) * 3 * (1 - k)
        hop = -8 * seg(t, 10, 10.4) * (1 - seg(t, 10.4, 10.9))       # salto de alegría
        put(surf, sprite(cid, 80, frame=int(t * 3) % 2 if k < 1 else 0), x, 420 + bob + hop)

    def petal(i, r, tt):
        st = 10 + r[0] * 1.5
        if tt < st:
            return None
        u = tt - st
        x = 40 + r[1] * (W - 80) + math.sin(u * 2 + r[2] * 6) * 30
        y = 380 - u * (80 + r[3] * 80) + 30 * u * u
        col = list(ELEM_COL.values())[i % 6]
        return (x, y, 3, col, 255 * (1 - _cl(u / 4)))
    particles(surf, t, 140, 11, petal)


def _elem_anim(el):
    def anim(surf, t, el=el):
        """Final de maga: la maga y el Gris en su reino, y el elemento lo
        RENUEVA (cada elemento a su manera)."""
        W, H = surf.get_size()
        col = ELEM_COL[el]
        k = seg(t, 1, 11)
        sky = {"fuego": ((40, 14, 10), (120, 60, 30)), "planta": ((20, 40, 30), (120, 190, 140)),
               "agua": ((10, 30, 60), (90, 170, 220)), "tierra": ((40, 30, 20), (170, 140, 100)),
               "rayo": ((10, 10, 30), (40, 50, 90)), "hielo": ((20, 30, 50), (180, 210, 235))}[el]
        gradient(surf, lerpc((12, 12, 18), sky[0], k), lerpc((20, 20, 24), sky[1], k))
        gy = 400
        if el == "fuego":                      # grietas que brillan y un hogar cálido
            ground(surf, gy, lerpc((30, 26, 24), (70, 36, 24), k))
            for i in range(9):
                x = 40 + i * 70
                pygame.draw.line(surf, lerpc((40, 30, 30), (255, 150, 60), seg(t, 2 + i * 0.3, 4 + i * 0.3)),
                                 (x, gy + 6), (x + 20, gy + 40), 3)
            particles(surf, t, 110, 21, lambda i, r, tt: (
                r[0] * W + math.sin(tt * 2 + i) * 10, gy - ((tt * 60 * (0.5 + r[1]) + r[2] * 400) % 400),
                2, (255, int(120 + 100 * r[3]), 50), 220 * k))
            glow(surf, W // 2, gy - 20, int(200 * k), (255, 140, 60), 90)
        elif el == "planta":                   # brotes que crecen y florecen
            ground(surf, gy, lerpc((40, 36, 30), (60, 110, 50), k))
            for i in range(16):
                x = 20 + i * 40
                g = seg(t, 1.5 + (i % 5) * 0.5 + i * 0.12, 6 + i * 0.2)
                hgt = g * (40 + (i * 37) % 70)
                pygame.draw.line(surf, (60, 150, 60), (x, gy), (x, gy - hgt), 3)
                pygame.draw.ellipse(surf, (90, 190, 90), (x, gy - hgt * 0.6, 12 * g, 6 * g))
                b = seg(t, 7 + i * 0.15, 8 + i * 0.15)
                if b > 0:
                    pygame.draw.circle(surf, ((240, 130, 170), (255, 220, 110), (250, 250, 250))[i % 3],
                                       (x, int(gy - hgt)), int(5 * b))
        elif el == "agua":                     # el agua sube limpia, con reflejos
            lvl = lerp(H, gy - 40, seg(t, 1, 8))
            ground(surf, gy, (50, 44, 40))
            lay = pygame.Surface((W, H), pygame.SRCALPHA)
            pts = [(x, lvl + 6 * math.sin(x / 40 + t * 2)) for x in range(0, W + 20, 20)]
            pygame.draw.polygon(lay, (70, 150, 230, 180), pts + [(W, H), (0, H)])
            for j in range(5):
                yy = lvl + 20 + j * 16
                pygame.draw.line(lay, (220, 245, 255, 90), (((t * 40 + j * 90) % W), yy),
                                 (((t * 40 + j * 90) % W) + 50, yy), 2)
            surf.blit(lay, (0, 0))
        elif el == "tierra":                   # casas y columnas que emergen del suelo
            ground(surf, gy, lerpc((50, 40, 30), (120, 90, 60), k))
            for i in range(8):
                x = 30 + i * 80
                g = seg(t, 1.5 + i * 0.5, 4 + i * 0.5)
                hh = g * (50 + (i * 23) % 60)
                shake = math.sin(t * 40) * 2 * (0 < g < 1)
                pygame.draw.rect(surf, (150, 120, 90), (x + shake, gy - hh, 44, hh))
                pygame.draw.polygon(surf, (120, 70, 50), [(x - 4 + shake, gy - hh), (x + 48 + shake, gy - hh),
                                                          (x + 22 + shake, gy - hh - 22 * g)])
        elif el == "rayo":                     # un relámpago y las luces de la ciudad se encienden
            ground(surf, gy, (24, 24, 34))
            for i in range(12):
                x = 20 + i * 52
                hh = 40 + (i * 29) % 70
                pygame.draw.rect(surf, (30, 30, 44), (x, gy - hh, 40, hh))
                on = seg(t, 4 + i * 0.25, 4.3 + i * 0.25)
                for wy in range(gy - hh + 8, gy - 6, 14):
                    pygame.draw.rect(surf, lerpc((40, 40, 50), (255, 235, 120), on), (x + 8, wy, 8, 6))
                    pygame.draw.rect(surf, lerpc((40, 40, 50), (255, 235, 120), on), (x + 24, wy, 8, 6))
            if 2.5 < t < 3.3 or 3.5 < t < 3.7:
                x0 = W * 0.7
                pts, y = [(x0, 0)], 0
                rng = random.Random(5)
                while y < gy - 60:
                    y += 30
                    pts.append((x0 + rng.randint(-30, 30), y))
                pygame.draw.lines(surf, (255, 255, 200), False, pts, 4)
                veil(surf, (255, 255, 230), 90)
        elif el == "hielo":                    # copos que caen y una aurora serena
            ground(surf, gy, lerpc((40, 40, 50), (220, 230, 245), k))
            lay = pygame.Surface((W, H), pygame.SRCALPHA)
            for j in range(3):
                pts = [(x, 90 + j * 22 + 18 * math.sin(x / 70 + t * 0.8 + j)) for x in range(0, W + 20, 20)]
                pygame.draw.lines(lay, ((120, 230, 200), (160, 120, 230), (130, 200, 250))[j] +
                                  (int(120 * seg(t, 4, 9)),), False, pts, 8)
            surf.blit(lay, (0, 0))
            particles(surf, t, 120, 31, lambda i, r, tt: (
                (r[0] * W + math.sin(tt + i) * 14) % W, (tt * (20 + 30 * r[1]) + r[2] * H) % H,
                2, (240, 248, 255), 220))
        # la maga (y el Gris a su lado)
        put(surf, sprite(el, 112), W // 2 - 40, gy + 6)
        put(surf, sprite("gris", 96), W // 2 + 60, gy + 6)
        glow(surf, W // 2 - 40, gy - 60, int(50 + 20 * math.sin(t * 2)), col, 70)
        veil(surf, (0, 0, 0), 200 * (1 - seg(t, 0, 1)))
    anim.__doc__ = f"Final de {el}: " + (anim.__doc__ or "")
    return anim


def anim_neutro(surf, t):
    """'_' (consejo sin amos, ambiguo): las seis magas en círculo alrededor de
    una mesa; sus colores giran hacia el centro y forman un símbolo gris que
    late mitad luz, mitad sombra. El Gris mira desde fuera del círculo."""
    W, H = surf.get_size()
    gradient(surf, (30, 30, 38), (12, 12, 16))
    cx, cy = W // 2, 300
    pygame.draw.ellipse(surf, (70, 60, 50), (cx - 150, cy - 40, 300, 80))
    pygame.draw.ellipse(surf, (100, 88, 70), (cx - 150, cy - 40, 300, 80), 3)
    k = seg(t, 1, 5)
    order = sorted(range(6), key=lambda i: math.sin(i * math.pi / 3 + 0.3))
    for i in order:
        a = i * math.pi / 3 + 0.3
        x, y = cx + math.cos(a) * 200, cy + math.sin(a) * 70
        put(surf, sprite(MAGAS[i], 72, alpha=255 * k), x, y + 30)
        sw = seg(t, 5 + i * 0.3, 9)
        if sw > 0:
            ang = a + sw * 4
            rad = (1 - sw) * 180
            glow(surf, int(cx + math.cos(ang) * rad), int(cy - 60 + math.sin(ang) * rad * 0.4),
                 16, ELEM_COL[MAGAS[i]], 180 * (1 - sw * 0.6))
    s = seg(t, 9, 11)
    if s > 0:
        r = 34
        half = 0.5 + 0.5 * math.sin(t * 2)
        pygame.draw.circle(surf, (150, 150, 160), (cx, cy - 60), int(r * s))
        pygame.draw.circle(surf, lerpc((40, 40, 55), (240, 240, 245), half), (cx, cy - 60), int(r * s),
                           draw_top_left=True, draw_bottom_left=True)
        glow(surf, cx, cy - 60, int(70 * s), (170, 170, 180), 90)
    put(surf, sprite("gris", 88), 90, 440)                        # fuera del círculo


ENDING_ANIMS = {
    "pacto": anim_pacto,
    "gris_sacrificio": anim_gris_sacrificio,
    "negro_sacrificio": anim_negro_sacrificio,
    "blanco": anim_blanco,
    "oscuro": anim_oscuro,
    "feliz": anim_feliz,
    "_": anim_neutro,
}
for _el in MAGAS:
    ENDING_ANIMS[_el] = _elem_anim(_el)


def draw_frame(ekey, surf, t, font=None):
    """Fotograma completo: animación + título (aparece a los 1.5 s)."""
    fn = ENDING_ANIMS.get(ekey, anim_neutro)
    fn(surf, t)
    if font:
        a = seg(t, 1.5, 3) * (1 - seg(t, 13.5, 14.8))
        if a > 0:
            ts = font.render(TITLES.get(ekey, TITLES["_"]), True, (255, 225, 120))
            ts.set_alpha(int(255 * a))
            surf.blit(ts, (surf.get_width() // 2 - ts.get_width() // 2, 24))


def play(ekey, screen, clock, present, font=None, fps=60):
    """Reproduce la animación del final (DUR s). Enter/Espacio/E/Esc o A/Start la saltan."""
    if font is None:
        font = pygame.font.SysFont("georgia", 30, bold=True)
    t = 0.0
    while t < DUR:
        t += clock.tick(fps) / 1000.0
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if (e.type == pygame.KEYDOWN and e.key in (pygame.K_RETURN, pygame.K_SPACE,
                                                       pygame.K_e, pygame.K_ESCAPE)) or \
               (e.type == pygame.JOYBUTTONDOWN and e.button in (0, 7)):
                if t > 0.4:
                    return
        draw_frame(ekey, screen, min(t, DUR), font)
        present()
