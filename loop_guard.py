"""
games/loop_guard.py — anti-bucle para las respuestas de IA de los juegos

Los modelos locales pequeños (LocalAI / Ollama) se atascan a veces repitiendo un
token o una frase corta durante miles de caracteres. En los juegos eso llega como
una respuesta larguísima e inservible que rompe el parseo de la jugada.

Los juegos piden la respuesta completa (sin streaming), así que aquí solo se puede
recortar la cola repetida — no se ahorra GPU. El corte de la generación en caliente
está en backend/services/ai/loop_guard.py, que sí ve el stream.

Uso:
    from loop_guard import strip_loop
    texto = strip_loop(respuesta_de_la_ia)

Copia autónoma a propósito: los juegos se lanzan como scripts sueltos y no pueden
importar del paquete backend.
"""

MAX_UNIT = 24      # longitud máxima del patrón que se considera "bucle"
MIN_REPS = 20      # repeticiones consecutivas para darlo por bucle


def find_loop(text: str, max_unit: int = MAX_UNIT, min_reps: int = MIN_REPS) -> int:
    """Índice donde empieza la repetición degenerada al final de `text`, o -1."""
    for unit_len in range(1, max_unit + 1):
        if unit_len * min_reps > len(text):
            break
        unit = text[-unit_len:]
        if not text.endswith(unit * min_reps):
            continue
        start = len(text) - unit_len * min_reps
        while start - unit_len >= 0 and text[start - unit_len:start] == unit:
            start -= unit_len
        return start
    return -1


def strip_loop(text, min_reps: int = MIN_REPS):
    """Devuelve `text` sin la repetición degenerada del final (si la hay).

    Tolerante: si no recibe una cadena, la devuelve tal cual."""
    if not text or not isinstance(text, str):
        return text
    cut = find_loop(text, MAX_UNIT, min_reps)
    return text[:cut].rstrip() if cut >= 0 else text
