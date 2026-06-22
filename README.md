# Nerea RPG — Edición Ollama 🎮

RPG 2D por turnos (magos de colores) **autónomo**: corre solo en tu PC y las
compañeras IA usan **modelos locales de Ollama** (sin nube ni el backend de Nerea).

---

## ✅ Requisitos

- **Python 3.10+** (con `python` o `py` en el PATH).
- **pygame** (lo instala el `install_rpg.bat`).
- **[Ollama](https://ollama.com)** instalado y corriendo (`ollama serve`), con al
  menos un modelo de chat descargado. *Opcional*: sin Ollama el juego funciona
  igual, pero las IAs usan respuestas de respaldo.

---

## 📦 Instalación (Windows)

1. Doble clic en **`install_rpg.bat`** (una sola vez).
   - Crea el entorno `.venv` y instala `pygame`.
2. Descarga algún modelo de Ollama, por ejemplo:
   ```
   ollama pull qwen3:4b
   ollama pull llama3.2
   ```

### Manual (otros sistemas)
```bash
python -m venv .venv
.venv/Scripts/pip install pygame      # Linux/Mac: .venv/bin/pip
```

---

## ▶️ Jugar

- **Windows:** doble clic en **`run_rpg_ollama.bat`**.
- **Manual:**
  ```bash
  .venv/Scripts/python games/rpg_ollama.py
  ```

Asegúrate de tener Ollama activo (`ollama serve`) para que las IAs hablen.

---

## 🤖 Modelos de IA (Ollama)

Al arrancar, el juego **consulta `ollama list`** (vía `http://localhost:11434/api/tags`)
y carga **todos** tus modelos de chat automáticamente (excluye los de *embeddings*).

En la pantalla **“Elige el MODELO de cada personaje”**:
- ↑/↓ = elegir personaje (las 6 magas + **Mago Blanco** + **Mago Negro**).
- ←/→ = cambiar el modelo de Ollama de ese personaje (muestra `(i/N)`).
- ENTER / Start = empezar.

Cambiar el servidor de Ollama (opcional):
```
set OLLAMA_URL=http://localhost:11434/api/chat   &  run_rpg_ollama.bat
```

---

## 🎮 Controles

| Acción | Teclado | Mando Xbox |
|---|---|---|
| Mover | Flechas / WASD | Stick / D-Pad |
| Hablar / Confirmar | E / Enter | A |
| Atrás / Cancelar | Esc / Q | B |
| Estado (personajes) | C | X |
| Bolsa | B | Start |
| Grupo (orden de magas) | T | — |
| Pestañas de menú | ← / → | LB / RB |
| Pantalla completa | F11 | — |

El mando se puede **conectar/desconectar en caliente**.

---

## 🧩 Cómo se juega

- Eres el **Mago Gris** (neutro). Libera a las **6 magas** (una por reino) venciéndolas.
- **Rueda elemental** (fuerte vs 2, débil vs 2): agua▸fuego/tierra · fuego▸planta/hielo ·
  planta▸agua/rayo · tierra▸fuego/rayo · rayo▸agua/hielo · hielo▸planta/tierra.
- Combate por turnos: **Atacar, Poderes, Combos, Bolsa, Cubrirse, Huir**.
- Tras liberar 3 magas aparece el **Mago Negro** en el hall (puedes hablarle o
  enfrentarlo). Hay **varios finales**
  según tus decisiones.

---

## 📁 Archivos y carpetas

```
rpg_ollama.py                 # el juego (autónomo)
rpg_ollama_data/              # se crea solo
  ├─ music/                   # audio propio del juego
  ├─ rpg_options.json         # opciones
  └─ rpg_save_1..3.json       # 3 ranuras de guardado
run_rpg_ollama.bat            # lanzador
install_rpg.bat               # instalador de dependencias
requirements_rpg.txt          # pygame
```

> La música no es obligatoria: si falta la carpeta `music/`, el juego corre sin sonido.

---

## 🛠️ Problemas comunes

- **“no se detectaron modelos”** → abre Ollama (`ollama serve`) y descarga uno
  (`ollama pull qwen3:4b`). Reinicia el juego.
- **Las IAs no responden / tardan** → modelos grandes tardan; los que tienen
  *thinking* (qwen) esperan más. Si no hay Ollama, usan frases de respaldo.
- **No abre el juego** → corre `install_rpg.bat` primero; necesitas Python en el PATH.
- **Va lento** → usa modelos chicos (1B–8B). Los `:cloud` requieren cuenta de Ollama.
