# -*- coding: utf-8 -*-
# ============================================================
#  MINI-JUEGOS del RPG Mago Gris — un juego por mundo.
#  Archivo SEPARADO para no engordar rpg.py.
#
#  API (lo único que usa rpg.py):
#      import minigames
#      oro, resumen = minigames.play(elem, ctx)
#
#  - elem: "fuego" | "planta" | "agua" | "tierra" | "rayo" | "hielo"
#  - ctx:  dict con referencias de rpg.py (pantalla, fuentes, sonido...):
#          screen, present, clock, FPS, draw_text, wrap,
#          font_xs, font_sm, font_md, font_lg,
#          WHITE, GOLD, DIM, W, H, sfx
#  - Devuelve (oro_ganado:int, resumen:str). ESC sale en cualquier momento
#    conservando lo ganado hasta ese punto.
#
#  Controles comunes:
#      Teclado: E/Enter/Espacio = acción · Flechas/WASD = mover · ESC = salir
#      Mando Xbox: A/Start/gatillos = acción · D-pad o stick izq. = mover · B/Back = salir
#      El mando se detecta al entrar y también si lo conectas a mitad de partida.
# ============================================================
import math
import random

import pygame

# --- Colores propios del módulo (los del juego llegan por ctx) ---
BG = (12, 14, 24)
PANEL = (16, 18, 32)
BORDER = (120, 160, 255)
GREEN = (80, 190, 110)
RED = (210, 80, 70)
CYAN = (100, 210, 220)
PURPLE = (170, 110, 230)
BROWN = (150, 105, 60)

# --- Mando Xbox: se detecta al entrar a un mini-juego y en caliente ---
_JOY = None      # mando activo (o None)
_AXP = None      # última dirección del stick (para disparar por FLANCO, no repetido)
_GAT = {}        # último valor de cada gatillo (para disparar por FLANCO)

DEADZONE = 0.5         # umbral del stick para contar como dirección
B_ACCION = (0, 7)       # A, Start
B_SALIR = (1, 6)        # B, Back/View
AX_GATILLOS = (4, 5)    # LT, RT (reposo -1.0 en el mapeo estándar de pygame)


def _init_joy():
    """Detecta el primer mando conectado (Xbox u otro). Llamar al entrar a un juego."""
    global _JOY, _AXP
    _AXP = None
    _GAT.clear()
    try:
        if not pygame.joystick.get_init():
            pygame.joystick.init()
        _JOY = pygame.joystick.Joystick(0) if pygame.joystick.get_count() else None
        if _JOY and not _JOY.get_init():
            _JOY.init()
    except Exception:
        _JOY = None


def _axis(i, default=0.0):
    """Lee un eje del mando, o `default` si no existe / falla."""
    try:
        return _JOY.get_axis(i) if _JOY.get_numaxes() > i else default
    except Exception:
        return default


def _boton_accion():
    """True si A, Start o cualquier gatillo está PULSADO ahora mismo."""
    if not _JOY:
        return False
    try:
        nb = _JOY.get_numbuttons()
        if any(b < nb and _JOY.get_button(b) for b in B_ACCION):
            return True
    except Exception:
        return False
    return any(_axis(a, -1.0) > 0.0 for a in AX_GATILLOS)


def _held():
    """Estado SOSTENIDO del mando: (izq, der, arriba, abajo, accion). D-pad + stick izq."""
    if not _JOY:
        return False, False, False, False, False
    ax, ay = _axis(0), _axis(1)
    try:
        hat = _JOY.get_hat(0) if _JOY.get_numhats() > 0 else (0, 0)
    except Exception:
        hat = (0, 0)
    return (hat[0] < 0 or ax < -DEADZONE, hat[0] > 0 or ax > DEADZONE,
            hat[1] > 0 or ay < -DEADZONE, hat[1] < 0 or ay > DEADZONE,
            _boton_accion())


# ============================================================
#  Utilidades compartidas
# ============================================================
def _poll():
    """Lee eventos y devuelve (salir, accion, dir) — dir en {'up','down','left','right',None}.
    accion = E/Enter/Espacio o A/Start del mando. salir = ESC, cerrar, o B/Back del mando."""
    global _AXP
    salir, accion, d = False, False, None
    for e in pygame.event.get():
        if e.type == pygame.QUIT:
            salir = True
        elif e.type in (pygame.JOYDEVICEADDED, pygame.JOYDEVICEREMOVED):
            _init_joy()                       # conectar/reconectar el mando en vivo
        elif e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                salir = True
            elif e.key in (pygame.K_e, pygame.K_RETURN, pygame.K_SPACE):
                accion = True
            elif e.key in (pygame.K_UP, pygame.K_w):
                d = "up"
            elif e.key in (pygame.K_DOWN, pygame.K_s):
                d = "down"
            elif e.key in (pygame.K_LEFT, pygame.K_a):
                d = "left"
            elif e.key in (pygame.K_RIGHT, pygame.K_d):
                d = "right"
        elif e.type == pygame.JOYBUTTONDOWN:      # Xbox: A/Start = acción · B/Back = salir
            if e.button in B_ACCION:
                accion = True
            elif e.button in B_SALIR:
                salir = True
        elif e.type == pygame.JOYAXISMOTION:      # gatillos LT/RT = acción (flanco)
            if e.axis in AX_GATILLOS and e.value > 0.0 and _GAT.get(e.axis, 0.0) <= 0.0:
                accion = True
            if e.axis in AX_GATILLOS:
                _GAT[e.axis] = e.value
        elif e.type == pygame.JOYHATMOTION:       # cruceta (D-pad)
            hx, hy = e.value
            d = ("left" if hx < 0 else "right" if hx > 0 else
                 "up" if hy > 0 else "down" if hy < 0 else d)
    # stick analógico como dirección: dispara SOLO al cruzar el umbral (flanco de entrada)
    if _JOY:
        ax, ay = _axis(0), _axis(1)
        nd = ("left" if ax < -DEADZONE else "right" if ax > DEADZONE else
              "up" if ay < -DEADZONE else "down" if ay > DEADZONE else None)
        if nd and nd != _AXP:
            d = d or nd
        _AXP = nd
    return salir, accion, d


def _frame(g, titulo, oro, sub=""):
    """Fondo + marco + cabecera común de todos los mini-juegos."""
    scr = g["screen"]
    scr.fill(BG)
    pygame.draw.rect(scr, PANEL, (10, 10, g["W"] - 20, g["H"] - 20), border_radius=10)
    pygame.draw.rect(scr, BORDER, (10, 10, g["W"] - 20, g["H"] - 20), 2, border_radius=10)
    g["draw_text"](scr, titulo, 26, 20, g["font_lg"], g["GOLD"])
    g["draw_text"](scr, f"Oro de la sesión: {oro}", g["W"] - 240, 24,
                   g["font_sm"], g["GOLD"])
    if sub:
        g["draw_text"](scr, sub, 26, 46, g["font_xs"], g["DIM"])


def _center(g, texto, y, font=None, color=None):
    scr, f = g["screen"], font or g["font_md"]
    surf = f.render(texto, True, color or g["WHITE"])
    scr.blit(surf, (g["W"] // 2 - surf.get_width() // 2, y))


def _espera_tecla(g, dibujar, ms=0):
    """Bucle simple: dibuja y espera acción (o timeout ms>0). Devuelve False si ESC."""
    t = 0
    while True:
        dt = g["clock"].tick(g["FPS"])
        t += dt
        salir, accion, _ = _poll()
        if salir:
            return False
        if accion or (ms and t >= ms):
            return True
        dibujar()
        g["present"]()


# ============================================================
#  AGUA — "Pesca del Abismo"
#  Lanza (E), espera la picada, y al reel: MANTÉN E para subir el anzuelo y
#  suéltalo para bajarlo, siguiendo al pez. Dentro de la zona se llena la
#  captura; fuera, sube la tensión (si llega al tope, el pez escapa).
#  El aldeano paga por PESO y TAMAÑO de cada pez.
# ============================================================
PECES = [
    #  nombre               rareza  largo(cm)  kg base  oro/kg  dificultad
    ("Sardina Gris",           32,      16,      0.06,     7,     0.55),
    ("Trucha del Abismo",      24,      34,      0.45,     8,     0.75),
    ("Perca Azul",             17,      46,      1.00,     9,     0.95),
    ("Anguila Sombría",        11,      80,      1.70,    11,     1.20),
    ("Pez Farol",               7,      52,      1.50,    16,     1.35),
    ("Rey del Abismo",          3,     115,      9.50,    24,     1.65),
    ("Bota Vieja",              6,      30,      0.80,     0,     0.40),
]


def _rueda_pez():
    total = sum(p[1] for p in PECES)
    r = random.uniform(0, total)
    for p in PECES:
        r -= p[1]
        if r <= 0:
            return p
    return PECES[0]


def _medidas(pez):
    """Largo y peso aleatorios alrededor de la base (peces grandes pesan MUCHO más)."""
    nombre, _, lbase, kbase, oro_kg, dif = pez
    largo = lbase * random.uniform(0.72, 1.38)
    kg = kbase * (largo / lbase) ** 2.6 * random.uniform(0.9, 1.1)
    precio = max(1, int(kg * oro_kg + largo * 0.30)) if oro_kg else 1
    return nombre, largo, kg, precio, dif


def _pesca(g):
    oro, capturas = 0, 0
    fase, t = "lanzar", 0            # lanzar -> espera -> pica -> reel -> ficha
    pez = None
    anzuelo, vel = 0.5, 0.0          # posición 0..1 del anzuelo en la barra
    objetivo, destino = 0.5, 0.5     # posición y destino del pez
    zona = 0.16                      # media-altura de la zona del pez
    progreso, tension = 0.0, 0.0
    ficha = None                     # (nombre, largo, kg, precio) del último pez
    pica_ms = 0

    while True:
        dt = g["clock"].tick(g["FPS"])
        s = dt / 1000.0
        salir, accion, _ = _poll()
        if salir:
            return oro, (f"Pescaste {capturas} pez(es)." if capturas
                         else "Hoy no picó nada...")
        sostiene = pygame.key.get_pressed()
        sostiene = sostiene[pygame.K_e] or sostiene[pygame.K_SPACE] \
            or sostiene[pygame.K_RETURN] or _held()[4]   # o gatillo/A del mando

        if fase == "lanzar":
            if accion:
                fase, t = "espera", random.randint(900, 3600)
                g["sfx"]("menu")
        elif fase == "espera":
            t -= dt
            if accion:                       # recoger antes de tiempo: nada
                fase = "lanzar"
            elif t <= 0:
                fase, pica_ms = "pica", 850  # ¡ventana para clavar!
                g["sfx"]("confirm")
        elif fase == "pica":
            pica_ms -= dt
            if accion:                       # clavado -> pelea
                pez = _rueda_pez()
                nombre, largo, kg, precio, dif = _medidas(pez)
                ficha = (nombre, largo, kg, precio)
                zona = max(0.07, 0.17 - dif * 0.05)
                anzuelo, vel = 0.5, 0.0
                objetivo = destino = 0.5
                progreso, tension = 0.25, 0.0
                fase = "reel"
                g["sfx"]("hit")
            elif pica_ms <= 0:               # tarde: se fue
                fase = "lanzar"
                g["sfx"]("miss")
        elif fase == "reel":
            _, _, _, _, dif = pez[0], 0, 0, 0, _medidas(pez)[4]  # dif estable
            dif = pez[5]
            # anzuelo: sube al sostener, cae solo
            vel += (1.9 if sostiene else -1.6) * s
            vel = max(-1.4, min(1.4, vel))
            anzuelo = max(0.0, min(1.0, anzuelo + vel * s))
            if anzuelo in (0.0, 1.0):
                vel = 0.0
            # el pez deambula hacia destinos aleatorios (más rápido si es difícil)
            if random.random() < s * (0.8 + dif):
                destino = random.uniform(0.06, 0.94)
            objetivo += (destino - objetivo) * min(1.0, s * (1.1 + dif * 1.4))
            dentro = abs(anzuelo - objetivo) < zona
            progreso += (0.22 if dentro else -0.13) * s * (1.6 - dif * 0.35)
            tension += (-0.25 if dentro else 0.20 * (0.8 + dif)) * s
            tension = max(0.0, tension)
            if progreso >= 1.0:              # ¡capturado!
                oro += ficha[3]
                capturas += 1
                fase = "ficha"
                g["sfx"]("gold" if ficha[3] > 1 else "cancel")
            elif tension >= 1.0 or progreso <= 0.0:
                fase = "ficha"
                ficha = None                 # escapó
                g["sfx"]("flee")

        # ---------- dibujo ----------
        _frame(g, "PESCA DEL ABISMO", oro,
               "E/A: lanzar/clavar · MANTÉN E o el gatillo para subir el anzuelo · ESC/B: terminar")
        scr = g["screen"]
        # laguna
        pygame.draw.ellipse(scr, (24, 46, 92), (60, 150, g["W"] - 260, 190))
        pygame.draw.ellipse(scr, (60, 110, 200), (60, 150, g["W"] - 260, 190), 2)
        if fase == "lanzar":
            _center(g, "Pulsa E para lanzar el sedal", 230, g["font_md"])
        elif fase == "espera":
            _center(g, "..." * (1 + (t // 400) % 3), 230, g["font_lg"], g["DIM"])
        elif fase == "pica":
            _center(g, "¡PICA!  ¡Pulsa E!", 220, g["font_lg"], g["GOLD"])
        elif fase == "reel":
            # barra vertical de pelea
            bx, by, bh = g["W"] - 150, 90, 300
            pygame.draw.rect(scr, (30, 34, 52), (bx, by, 26, bh), border_radius=6)
            zy = by + int((1 - objetivo - zona) * bh)
            zh = max(8, int(zona * 2 * bh))
            pygame.draw.rect(scr, (40, 120, 80), (bx, zy, 26, zh), border_radius=6)
            hy = by + int((1 - anzuelo) * bh)
            pygame.draw.rect(scr, g["GOLD"], (bx - 3, hy - 4, 32, 8), border_radius=3)
            # captura y tensión
            pygame.draw.rect(scr, (30, 34, 52), (70, 380, 220, 12), border_radius=5)
            pygame.draw.rect(scr, GREEN, (70, 380, int(220 * progreso), 12),
                             border_radius=5)
            g["draw_text"](scr, "Captura", 70, 362, g["font_xs"], GREEN)
            pygame.draw.rect(scr, (30, 34, 52), (320, 380, 220, 12), border_radius=5)
            pygame.draw.rect(scr, RED, (320, 380, int(220 * tension), 12),
                             border_radius=5)
            g["draw_text"](scr, "Tensión del sedal", 320, 362, g["font_xs"], RED)
            g["draw_text"](scr, f"Pelea: {ficha[0]}", 70, 120, g["font_sm"], CYAN)
        elif fase == "ficha":
            if ficha:
                nombre, largo, kg, precio = ficha
                _center(g, f"¡Capturaste: {nombre}!", 180, g["font_lg"], g["GOLD"])
                _center(g, f"Largo: {largo:.1f} cm    Peso: {kg:.2f} kg", 215)
                _center(g, f"El aldeano paga {precio} oro por él", 245,
                        g["font_md"], GREEN)
            else:
                _center(g, "¡El pez escapó!", 200, g["font_lg"], RED)
            _center(g, "E: seguir pescando · ESC: terminar", 300,
                    g["font_xs"], g["DIM"])
            if accion:
                fase = "lanzar"
        g["present"]()


# ============================================================
#  FUEGO — "Templa la Hoja"
#  El martillo oscila sobre la barra: golpea (E) en la zona al rojo. 6 golpes;
#  cada uno más rápido y con la zona más angosta. La calidad fija la paga.
# ============================================================
def _forja(g):
    oro_total = 0
    while True:                                 # una PIEZA por vuelta
        golpes, calidad, fallos, t = 0, 0, 0, 0.0
        vel, ancho = 1.6, 0.30
        msj, msj_t = "", 0
        while golpes < 6:
            dt = g["clock"].tick(g["FPS"])
            t += dt / 1000.0
            salir, accion, _ = _poll()
            if salir:
                return oro_total, "La forja queda encendida, vuelve cuando quieras."
            pos = 0.5 + 0.5 * math.sin(t * vel * 2.2)
            if accion:
                d = abs(pos - 0.5)
                if d < ancho * 0.30:
                    calidad += 3; msj = "¡PERFECTO!"; g["sfx"]("crit")
                elif d < ancho:
                    calidad += 2; msj = "Buen golpe"; g["sfx"]("hit")
                elif d < ancho * 1.8:
                    calidad += 1; msj = "Rozado..."; g["sfx"]("guard")
                else:
                    fallos += 1; msj = "¡Grieta!"; g["sfx"]("miss")
                msj_t = 600
                golpes += 1
                vel *= 1.17
                ancho = max(0.10, ancho * 0.88)
            msj_t = max(0, msj_t - dt)

            _frame(g, "TEMPLA LA HOJA", oro_total,
                   "E/A: golpe de martillo en la zona AL ROJO · ESC/B: salir")
            scr = g["screen"]
            bx, bw = 80, g["W"] - 160
            pygame.draw.rect(scr, (30, 34, 52), (bx, 220, bw, 26), border_radius=8)
            zx = bx + int((0.5 - ancho) * bw)
            pygame.draw.rect(scr, (200, 80, 40),
                             (zx, 220, max(10, int(ancho * 2 * bw)), 26),
                             border_radius=8)
            mx = bx + int(pos * bw)
            pygame.draw.rect(scr, g["GOLD"], (mx - 4, 210, 8, 46), border_radius=3)
            _center(g, f"Golpe {golpes + 1 if golpes < 6 else 6}/6   "
                       f"Calidad: {calidad}", 160)
            if msj_t:
                _center(g, msj, 290, g["font_lg"],
                        g["GOLD"] if "PERFECTO" in msj else g["WHITE"])
            g["present"]()
        # pieza terminada
        pago = calidad * 7 + (30 if fallos == 0 else 0)
        oro_total += pago
        g["sfx"]("gold" if pago else "lose")

        def fin():
            _frame(g, "TEMPLA LA HOJA", oro_total)
            _center(g, f"Pieza terminada: calidad {calidad}/18"
                       + ("  ¡SIN GRIETAS!" if fallos == 0 else ""), 190,
                    g["font_lg"], g["GOLD"])
            _center(g, f"El forjador paga {pago} oro", 230, g["font_md"], GREEN)
            _center(g, "E: otra pieza · ESC: salir", 300, g["font_xs"], g["DIM"])
        if not _espera_tecla(g, fin):
            return oro_total, "Buen trabajo en la forja."


# ============================================================
#  PLANTA — "Cosecha del Bosque"
#  30 segundos: mueve el canasto (←/→) y atrapa fruta buena; la podrida resta.
# ============================================================
def _cosecha(g):
    dur, t = 30000, 0
    cx = g["W"] // 2
    frutas = []                    # [x, y, vel, buena]
    spawn_t, buenos, podridos = 0, 0, 0
    while t < dur:
        dt = g["clock"].tick(g["FPS"])
        t += dt
        salir, _, _ = _poll()
        if salir:
            break
        keys = pygame.key.get_pressed()
        hl, hr, _hu, _hd, _ha = _held()          # D-pad / stick del mando
        if keys[pygame.K_LEFT] or keys[pygame.K_a] or hl:
            cx -= int(0.42 * dt)
        if keys[pygame.K_RIGHT] or keys[pygame.K_d] or hr:
            cx += int(0.42 * dt)
        cx = max(70, min(g["W"] - 70, cx))
        spawn_t -= dt
        if spawn_t <= 0:
            spawn_t = max(260, 700 - t // 90)          # cada vez llueve más
            frutas.append([random.randint(70, g["W"] - 70), 70,
                           random.uniform(0.16, 0.24) + t / 90000.0,
                           random.random() > 0.28])
        for f in frutas:
            f[1] += f[2] * dt
        vivos = []
        for f in frutas:
            if f[1] >= g["H"] - 96 and abs(f[0] - cx) < 42:   # al canasto
                if f[3]:
                    buenos += 1; g["sfx"]("item")
                else:
                    podridos += 1; g["sfx"]("miss")
            elif f[1] < g["H"] - 40:
                vivos.append(f)
        frutas = vivos

        _frame(g, "COSECHA DEL BOSQUE", max(0, buenos * 6 - podridos * 6),
               "←/→ o stick: mover el canasto · atrapa la fruta CLARA, esquiva la oscura")
        scr = g["screen"]
        _center(g, f"Tiempo: {max(0, (dur - t) // 1000)} s   "
                   f"Buenas: {buenos}  Podridas: {podridos}", 60, g["font_sm"])
        for f in frutas:
            col = (110, 210, 90) if f[3] else (70, 60, 50)
            pygame.draw.circle(scr, col, (int(f[0]), int(f[1])), 9)
        pygame.draw.rect(scr, BROWN, (cx - 42, g["H"] - 92, 84, 26),
                         border_radius=8)
        pygame.draw.rect(scr, (95, 65, 35), (cx - 42, g["H"] - 92, 84, 26), 2,
                         border_radius=8)
        g["present"]()
    oro = max(0, buenos * 6 - podridos * 6) + (25 if buenos >= 18 else 0)
    g["sfx"]("gold" if oro else "lose")
    return oro, (f"Cosecha: {buenos} frutas buenas, {podridos} podridas. "
                 f"Te pagan {oro} oro.")


# ============================================================
#  TIERRA — "Vetas del Cañón"
#  3x3 rocas: pica (E) la que brilla antes de que se apague. La DORADA suma,
#  la GEMA púrpura vale x3 y la ROJA es trampa (ignórala o resta).
# ============================================================
def _vetas(g):
    dur, t = 30000, 0
    cur = [1, 1]
    activa, tipo, luz_t = None, "oro", 0
    puntos = 0
    while t < dur:
        dt = g["clock"].tick(g["FPS"])
        t += dt
        salir, accion, d = _poll()
        if salir:
            break
        if d == "up":
            cur[1] = max(0, cur[1] - 1)
        elif d == "down":
            cur[1] = min(2, cur[1] + 1)
        elif d == "left":
            cur[0] = max(0, cur[0] - 1)
        elif d == "right":
            cur[0] = min(2, cur[0] + 1)
        luz_t -= dt
        if activa is None or luz_t <= 0:
            activa = (random.randint(0, 2), random.randint(0, 2))
            r = random.random()
            tipo = "gema" if r < 0.15 else "roja" if r < 0.30 else "oro"
            luz_t = max(500, 950 - t // 45)
        if accion:
            if tuple(cur) == activa:
                if tipo == "oro":
                    puntos += 1; g["sfx"]("hit")
                elif tipo == "gema":
                    puntos += 3; g["sfx"]("crit")
                else:
                    puntos = max(0, puntos - 2); g["sfx"]("miss")
                activa, luz_t = None, 0
            else:
                g["sfx"]("guard")

        _frame(g, "VETAS DEL CAÑÓN", puntos * 8,
               "Flechas/stick: elegir roca · E/A: picar la que BRILLA (púrpura x3, roja NO)")
        scr = g["screen"]
        _center(g, f"Tiempo: {max(0, (dur - t) // 1000)} s   Puntos: {puntos}",
                60, g["font_sm"])
        ox, oy, cs = g["W"] // 2 - 150, 120, 100
        for yy in range(3):
            for xx in range(3):
                r = pygame.Rect(ox + xx * cs, oy + yy * cs, cs - 12, cs - 12)
                col = (52, 44, 38)
                if activa == (xx, yy):
                    col = ((225, 180, 60) if tipo == "oro" else
                           PURPLE if tipo == "gema" else (200, 70, 60))
                pygame.draw.rect(scr, col, r, border_radius=10)
                if cur == [xx, yy]:
                    pygame.draw.rect(scr, g["WHITE"], r, 3, border_radius=10)
        g["present"]()
    oro = puntos * 8
    g["sfx"]("gold" if oro else "lose")
    return oro, f"Sacaste vetas por {puntos} puntos. Te pagan {oro} oro."


# ============================================================
#  RAYO — "Danza del Pararrayos"
#  8 rondas: la chispa recorre la barra; pulsa E dentro de la franja (cada
#  ronda más angosta y rápida). El combo multiplica la paga.
# ============================================================
def _pararrayos(g):
    oro, combo, combo_max, aciertos = 0, 0, 0, 0
    for ronda in range(8):
        ancho = max(0.07, 0.20 - ronda * 0.017)
        centro = random.uniform(0.25, 0.75)
        vel = 0.55 + ronda * 0.09
        pos, resuelto, exito = 0.0, False, False
        while not resuelto:
            dt = g["clock"].tick(g["FPS"])
            salir, accion, _ = _poll()
            if salir:
                return oro, f"Guiaste {aciertos} rayos. Buen ojo."
            pos += vel * dt / 1000.0
            if accion:
                exito = abs(pos - centro) < ancho
                resuelto = True
            elif pos >= 1.0:
                resuelto = True                 # se escapó el rayo
            _frame(g, "DANZA DEL PARARRAYOS", oro,
                   f"Ronda {ronda + 1}/8 · E/A cuando la chispa cruce la franja")
            scr = g["screen"]
            bx, bw = 80, g["W"] - 160
            pygame.draw.rect(scr, (30, 34, 52), (bx, 230, bw, 24), border_radius=8)
            fx = bx + int((centro - ancho) * bw)
            pygame.draw.rect(scr, (200, 190, 70),
                             (fx, 230, max(8, int(ancho * 2 * bw)), 24),
                             border_radius=8)
            px = bx + int(min(1.0, pos) * bw)
            pygame.draw.rect(scr, CYAN, (px - 3, 220, 6, 44), border_radius=3)
            _center(g, f"Combo: x{combo}   Aciertos: {aciertos}", 160)
            g["present"]()
        if exito:
            combo += 1
            combo_max = max(combo_max, combo)
            aciertos += 1
            oro += 8 * combo
            g["sfx"]("crit" if combo >= 3 else "hit")
        else:
            combo = 0
            g["sfx"]("miss")
    oro += combo_max * 5
    g["sfx"]("gold" if oro else "lose")
    return oro, (f"{aciertos}/8 rayos guiados (mejor combo x{combo_max}). "
                 f"Te pagan {oro} oro.")


# ============================================================
#  HIELO — "Talla Glacial"
#  Simón de flechas: memoriza la secuencia y repítela. Cada ronda añade un
#  corte y paga más. Un error rompe la escultura.
# ============================================================
_FLECHA = {"up": "↑", "down": "↓", "left": "←", "right": "→"}


def _talla(g):
    oro, sec = 0, []
    dirs = ["up", "down", "left", "right"]
    while len(sec) < 9:
        sec.append(random.choice(dirs))
        ronda = len(sec)
        # --- mostrar la secuencia ---
        for i, mv in enumerate(sec):
            fin_t = 0
            while fin_t < 480:
                dt = g["clock"].tick(g["FPS"])
                fin_t += dt
                salir, _, _ = _poll()
                if salir:
                    return oro, "La escultura queda a medio tallar."
                _frame(g, "TALLA GLACIAL", oro,
                       f"Ronda {ronda} · Memoriza los cortes")
                _center(g, "  ".join(_FLECHA[m] for m in sec[:i + 1]) if fin_t < 340
                        else "  ".join(_FLECHA[m] for m in sec[:i]),
                        210, g["font_lg"], CYAN)
                _center(g, f"Cortes: {ronda}", 150, g["font_sm"], g["DIM"])
                g["present"]()
        # --- repetirla ---
        idx = 0
        while idx < len(sec):
            dt = g["clock"].tick(g["FPS"])
            salir, _, d = _poll()
            if salir:
                return oro, "La escultura queda a medio tallar."
            if d:
                if d == sec[idx]:
                    idx += 1
                    g["sfx"]("menu")
                else:                              # ¡crac!
                    g["sfx"]("lose")
                    def rota():
                        _frame(g, "TALLA GLACIAL", oro)
                        _center(g, "¡CRAC! La escultura se rompió...", 200,
                                g["font_lg"], RED)
                        _center(g, f"Te pagan {oro} oro por lo tallado.", 240,
                                g["font_md"], GREEN)
                        _center(g, "E/ESC: salir", 300, g["font_xs"], g["DIM"])
                    _espera_tecla(g, rota)
                    return oro, f"Tallaste {ronda - 1} corte(s) antes del crac."
            _frame(g, "TALLA GLACIAL", oro, f"Ronda {ronda} · Repite los cortes")
            _center(g, "  ".join(_FLECHA[m] for m in sec[:idx]) + "  _" * 1,
                    210, g["font_lg"], g["GOLD"])
            g["present"]()
        oro += ronda * 8
        g["sfx"]("gold")
    return oro, f"¡Escultura PERFECTA de 9 cortes! Te pagan {oro} oro."


# ============================================================
#  Punto de entrada
# ============================================================
_JUEGOS = {"agua": _pesca, "fuego": _forja, "planta": _cosecha,
           "tierra": _vetas, "rayo": _pararrayos, "hielo": _talla}

NOMBRE = {"agua": "Pesca del Abismo", "fuego": "Templa la Hoja",
          "planta": "Cosecha del Bosque", "tierra": "Vetas del Cañón",
          "rayo": "Danza del Pararrayos", "hielo": "Talla Glacial"}


def play(elem, ctx):
    """Ejecuta el mini-juego del mundo `elem`. Devuelve (oro, resumen)."""
    fn = _JUEGOS.get(elem)
    if fn is None:
        return 0, "Aquí no hay nada que jugar todavía."
    _init_joy()                 # detecta el mando Xbox (si hay)
    pygame.event.clear()
    oro, resumen = fn(ctx)
    pygame.event.clear()
    return int(max(0, oro)), resumen
