"""gfx_utils.py — helpers de dibujo 2D con anti-aliasing y efectos, compartidos
por los juegos de Nerea (monopoly, catan, ludo, escoba, uno, battleship, …).

Todo pygame puro; sin dependencias extra. Las funciones aceptan floats y los
redondean a int donde pygame lo exige. Colores como (r,g,b) o (r,g,b,a).
"""
import math
import pygame
import pygame.gfxdraw as _gfx

__all__ = [
    "filled_circle", "ring", "token", "drop_shadow_circle",
    "aa_polygon", "filled_ellipse", "vgradient", "vgradient_surf", "lerp", "shade",
    "rounded_rect", "soft_shadow_rect",
]


# ── color ─────────────────────────────────────────────────────────────────
def lerp(c1, c2, t):
    """Interpola dos colores RGB(A). t en [0,1]."""
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def shade(color, factor):
    """factor>1 aclara, <1 oscurece. Mantiene alpha si lo hay."""
    r, g, b = color[:3]
    f = lambda v: max(0, min(255, int(v * factor)))
    out = (f(r), f(g), f(b))
    return out + tuple(color[3:]) if len(color) > 3 else out


# ── círculos con AA ─────────────────────────────────────────────────────────
def filled_circle(surf, cx, cy, r, color, border=None, border_w=1):
    """Círculo relleno con borde anti-aliased."""
    cx, cy, r = int(cx), int(cy), int(r)
    if r < 1:
        return
    _gfx.filled_circle(surf, cx, cy, r, color)
    _gfx.aacircle(surf, cx, cy, r, color)
    if border is not None:
        for i in range(border_w):
            _gfx.aacircle(surf, cx, cy, r - i, border)


def ring(surf, cx, cy, r, color, width=2):
    """Anillo (borde) anti-aliased de grosor `width`."""
    cx, cy, r = int(cx), int(cy), int(r)
    for i in range(max(1, width)):
        _gfx.aacircle(surf, cx, cy, r - i, color)


_SHADOW_CACHE = {}
def drop_shadow_circle(surf, cx, cy, r, alpha=90, blur=2):
    """Sombra circular translúcida REAL (draw.circle ignora el alpha sobre la
    superficie principal; esto sí lo respeta)."""
    r = int(r)
    if r < 1:
        return
    key = (r, alpha, blur)
    sh = _SHADOW_CACHE.get(key)
    if sh is None:
        pad = blur + 1
        size = (r + pad) * 2
        sh = pygame.Surface((size, size), pygame.SRCALPHA)
        c = size // 2
        for i in range(blur + 1):          # capas concéntricas → borde difuso
            a = int(alpha * (1 - i / (blur + 1)))
            _gfx.filled_circle(sh, c, c, r + i - blur // 2, (0, 0, 0, a))
        _SHADOW_CACHE[key] = sh
    surf.blit(sh, (int(cx) - sh.get_width() // 2, int(cy) - sh.get_height() // 2))


def token(surf, cx, cy, r, color, ring_col=None, ring_w=2):
    """Ficha con volumen: sombra + relleno AA + degradado sutil + brillo especular."""
    cx, cy, r = int(cx), int(cy), int(r)
    drop_shadow_circle(surf, cx, cy + max(1, r // 3), r, alpha=70, blur=2)
    # cuerpo con leve degradado radial (borde más oscuro)
    filled_circle(surf, cx, cy, r, color, border=shade(color, 0.6), border_w=1)
    if r >= 5:                              # brillo especular arriba-izquierda
        hi = pygame.Surface((r, r), pygame.SRCALPHA)
        _gfx.filled_circle(hi, r // 3, r // 3, max(1, r // 3),
                           (255, 255, 255, 90))
        surf.blit(hi, (cx - r // 2, cy - r // 2))
    if ring_col is not None:
        ring(surf, cx, cy, r + 2, ring_col, ring_w)


# ── polígonos con AA ────────────────────────────────────────────────────────
def aa_polygon(surf, points, color, border=None, border_w=1):
    """Polígono relleno anti-aliased, con borde opcional."""
    pts = [(int(x), int(y)) for x, y in points]
    _gfx.filled_polygon(surf, pts, color)
    _gfx.aapolygon(surf, pts, color)
    if border is not None:
        _gfx.aapolygon(surf, pts, border)
        if border_w > 1:
            pygame.draw.polygon(surf, border, pts, border_w)


# ── elipses con AA ──────────────────────────────────────────────────────────
def filled_ellipse(surf, cx, cy, rx, ry, color, border=None):
    """Elipse rellena anti-aliased (rx/ry = semiejes)."""
    cx, cy, rx, ry = int(cx), int(cy), int(rx), int(ry)
    if rx < 1 or ry < 1:
        return
    _gfx.filled_ellipse(surf, cx, cy, rx, ry, color)
    _gfx.aaellipse(surf, cx, cy, rx, ry, color)
    if border is not None:
        _gfx.aaellipse(surf, cx, cy, rx, ry, border)


# ── degradados ──────────────────────────────────────────────────────────────
def vgradient(surf, rect, top_col, bottom_col):
    """Pinta un degradado vertical dentro de `rect` (sobre surf)."""
    rect = pygame.Rect(rect)
    if rect.height <= 0:
        return
    for i in range(rect.height):
        t = i / (rect.height - 1) if rect.height > 1 else 0
        pygame.draw.line(surf, lerp(top_col, bottom_col, t),
                         (rect.x, rect.y + i), (rect.right - 1, rect.y + i))


def vgradient_surf(w, h, top_col, bottom_col):
    """Devuelve una Surface con un degradado vertical (útil para cachear)."""
    s = pygame.Surface((w, h))
    vgradient(s, pygame.Rect(0, 0, w, h), top_col, bottom_col)
    return s


# ── rectángulos ─────────────────────────────────────────────────────────────
def rounded_rect(surf, rect, color, radius=8, border=None, border_w=1):
    rect = pygame.Rect(rect)
    pygame.draw.rect(surf, color, rect, border_radius=radius)
    if border is not None:
        pygame.draw.rect(surf, border, rect, border_w, border_radius=radius)


_RSHADOW_CACHE = {}
def soft_shadow_rect(surf, rect, radius=8, alpha=80, spread=4):
    """Sombra difusa bajo un rect redondeado."""
    rect = pygame.Rect(rect)
    key = (rect.w, rect.h, radius, alpha, spread)
    sh = _RSHADOW_CACHE.get(key)
    if sh is None:
        sh = pygame.Surface((rect.w + spread * 2, rect.h + spread * 2),
                            pygame.SRCALPHA)
        for i in range(spread, 0, -1):
            a = int(alpha * (1 - i / (spread + 1)))
            r2 = pygame.Rect(spread - i, spread - i,
                             rect.w + i * 2, rect.h + i * 2)
            pygame.draw.rect(sh, (0, 0, 0, a), r2, border_radius=radius + i)
        _RSHADOW_CACHE[key] = sh
    surf.blit(sh, (rect.x - spread, rect.y - spread + 2))
