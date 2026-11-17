# ✨ ASCII Mate — a floating desktop ASCII companion

Fully transparent, draggable, resizable ASCII animations that float **on top of** your PDFs, VS Code and windows while you study, code or read — no background, no frame. **141 animations**: 123 pure classic ASCII / mathematical 3D shaders (Saturn, donut, heart, Christmas tree...) plus 18 **HD colour ASCII** pieces (11 renewed animals/characters, 4 scenes, 3 samples). Every character, and the timer label, is plain ASCII.

> **Platform:** Windows 10/11 only (transparent tray widget, named-pipe IPC, lock-screen/fullscreen detection and smart readability use Windows APIs).
>
> **Language:** the interface is **English by default**; Turkish is available from the tray menu (**Language → Türkçe**). Asset ids and file names never change, so favourites and profiles survive a language switch. See [Türkçe özet](#türkçe) at the end.

---

## 🚀 Install & run

### 1. One click (Windows)
Double-click **`baslat.bat`**. Missing packages (`PyQt6`, `rich`) are installed automatically and the **ASCII Mate Terminal Hub** opens.

### 2. Command line
```bash
python main.py                          # interactive Terminal Hub
python main.py --widget sleeping_cat    # place one character on the desktop
python main.py --widget saturn_3d
python tests/validate_library.py        # validate all 141 animations (pure ASCII, alignment, frame jitter, shaders)
python -m pytest tests -q               # unit tests (requirements-dev.txt)
python tests/preview_art.py cat_bust_3d --w 64 --h 30 --color   # preview in the terminal
python tests/bench_render.py [--hd]     # render CPU/RAM benchmarks
python tests/bench_cpu_real.py --repeat 3   # REAL process CPU (real host + widgets)
python tools/hd_convert.py photo.png --out assets/animations/community --id portrait --cols 180   # your own image → HD
```

### 3. Build a Python-free `.exe`
Double-click **`build_exe.bat`** (`--onedir`). It produces a console-less **`ASCII_Mate.exe`** (tray + widgets) and a console **`ASCII_Mate_CLI.exe`** (Terminal Hub). Dev dependencies (`pyinstaller`, `pytest`) are in `requirements-dev.txt`.

---

## 📁 Project layout
```text
ascii_mate/
├── baslat.bat / build_exe.bat / ASCII_Mate.spec
├── main.py                     # entry point
├── config.example.json         # sample settings (the real config.json is git-ignored)
├── THIRD_PARTY.md              # CC0 3D models used to generate some HD scenes
├── src/
│   ├── core/                   # models, 3D shader engine, particles, library, i18n (src/core/i18n*.py)
│   ├── gui/                    # transparent widget, context menu, settings, tray
│   └── cli/                    # Terminal Hub and live preview
├── tools/                      # hd_convert, scenes/ (HD builders), blender_prep, import_local_art, ...
├── assets/animations/          # categorised .ascii.json (+ .ascii.hd) files, themes.json
└── tests/                      # validate_library, pytest, benchmarks, previews
```

---

## 🎮 Desktop widget controls

* **Left-click + drag:** move the character (position is saved).
* **Shift + left-click (3D orbit) / free look:** rotate live 3D models (`pitch` / `yaw`).
* **Edge/corner handles, mouse wheel / `+` `-`:** resize smoothly (`6 pt` – `48 pt`). In **Automatic** 3D resolution the ASCII grid density grows with the widget.
* **Hover:** drag and resize handles appear on hover and disappear again.
* **Right-click menu:**
  * 💧 **Opacity** `15%`–`100%` + the Fine-Tuning slider panel.
  * 🖥️ **3D grid resolution:** Compact (`38×18`), Standard (`52×24`), HD (`64×30`), Ultra HD (`74×34`) or automatic.
  * ⏱️ **Study timer (Pomodoro):** `15 / 25 / 45 / 60 min` or custom (the `3D Hourglass` follows the remaining time); a **5-second 3D fireworks celebration** plays at the end, optionally followed by a **5-minute break timer**.
  * ⚡ **Animation speed:** `0.25x` – `3x` + manual FPS.
  * 🎨 **Colour modes:** white, cream, Matrix green, Amber CRT, Cyberpunk neon, pastel lavender, ice blue, sakura, gold, rainbow and a custom hex picker.
  * ✨ **Effects & particles:** snow, rain, thunderstorm, steam, hearts, sparks, stardust, sleep `Zzz` bubbles, eye blink, **look toward the mouse cursor**, horizontal flip, soft neon glow and a readability shadow.
  * 👻 **Study / Ghost mode (click-through):** lets you click the PDF or browser under the widget. *(Turn it off from the tray icon.)*
* **System tray:** **Desktop Layout (Profiles)** saves/loads multi-widget layouts, **Restore last open widgets on startup**, HD mode, battery saver and **Language**.
* **Terminal Hub keys:** `F` adds to **Favorites**, `C` changes the preview theme live, `I` imports a file.
* **Drag & drop:** drop an `.ascii.json` or `.txt` file onto an open widget to add it to the library instantly.

---

## 🌐 Language / i18n

* The UI language is stored in `config.json` as `"language": "en"` (default) or `"tr"`; switch it from the tray (**Language**), no restart needed.
* `src/core/i18n.py` is a dependency-free translation layer: UI strings in code are Turkish source text used as lookup keys, `tr()` returns the English text from `src/core/i18n_en.py` when the language is `en`. Unknown keys fall back to the source text.
* Asset display names: add an optional **`"name_en"`** field to an asset JSON; otherwise the bundled English names (`src/core/i18n_names_en.py`) or the stored `name` are shown. Category names are translated for display only.

---

## 👁️ Smart readability ("go behind text")

Right-click → **Go Behind Text** (default **off**). Where the screen under the widget contains text, those cells fade and shift to a contrasting colour; elsewhere the widget looks normal.

> **Note:** the widget is an always-on-top overlay and cannot truly go *behind* another window; this mode makes text-covering cells **faded / contrast-coloured**.

* **How it works (no OCR, language-independent):** the area under the widget is captured at ~1.4 Hz, high-frequency energy is reduced to the character-cell grid and text-like cells are detected; transitions are smoothed with an EMA (no flicker). Analysis is skipped when the screen did not change.
* **Excludes its own window:** `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)` (Windows 10 2004+).
* **🔒 Privacy:** screen capture happens **only while this mode is on**, is processed **in memory only**, and is **never written to disk or sent over the network**; only a per-cell "text / no text" flag and average brightness are kept. While the mode is on, ASCII Mate widgets are also hidden from screenshot/recording apps.
* **Performance:** ≈ 17 ms per poll (≈ 2.5 % of one core; ≈ 0.6 % on 4 cores).

---

## 🖼️ HD mode (high-resolution colour ASCII) — optional

A separate asset type (`schema_version: "3.0"`, `"hd": true`; shown with an **[HD]** badge). Hundreds of columns, **per-character RGB colour**; dark/background cells emit no character (transparent). Classic 1.0/2.0 animations and shaders are untouched.

* **Off by default:** the first HD widget asks for confirmation (it uses more CPU/RAM; also toggle in tray → *HD Mode*). **At most 2 HD widgets** at once.
* **Right-click → HD Quality:** Low (half columns/rows, ≤8 FPS), Medium (full, ≤12 FPS), High (full, ≤15 FPS) and an **HD FPS cap** (4 / 8 / 10 / 15 / auto). A spinning HD asset never exceeds 15 FPS.
* **Rendering pipeline:** 95 ASCII glyphs are drawn once into a mask (NumPy atlas); each frame writes **only the changed cells** into one `QImage` buffer and `paintEvent` does a single `drawImage`. Unchanged frames are not drawn; still HD wakes at 2 Hz. Battery saver, lock screen, fullscreen apps and hidden widgets pause as for classic widgets.
* **Storage:** `<id>.ascii.json` (small metadata) + `<id>.ascii.hd` (zlib per frame; ASCII codes + planar RGB). Frames decode lazily (max 3 in memory). Copy **both files** into the community folder.
* **Requirements:** `numpy` (≈ +26.5 MB in the packaged build).

### Converter: `tools/hd_convert.py`
```bash
python tools/hd_convert.py photo.png --out assets/animations/community --id portrait --cols 180 --gamma 0.8 --edge-boost 0.5
python tools/hd_convert.py anim.gif  --out assets/animations/community --id anim --cols 160 --fps 10
python tools/hd_convert.py frames/   --out assets/animations/community --id series --frames 48
python tools/hd_convert.py model.obj --out assets/animations/community --id spin --frames 48 --rotate-y 360 --tilt 20 --obj-color "#d8b45a"
```
Options: `--cols`, `--ramp` (`auto` or your own characters), `--gamma`, `--edge-boost` (Sobel edges `| - / \`), `--bg-threshold`, `--color-lift`, `--fps`, `--frames`. Characters are ASCII only; the density ramp is ordered by the **measured real ink density** of the widget font. OBJ files (vertex colours supported) are rotated with an orthographic z-buffer and passed through the same pipeline.

### HD animals, characters and scenes (`tools/scenes/`)
The old ellipsoid models were renewed as HD **under the same ids** (favourites/profiles keep working). New scenes: `hd_knight_resting`, `hd_rider_horse`, `hd_meadow_warrior`, `hd_skeleton_giant`.

* **Realistic style:** no contour characters (`| - _ / \`) or fixed face characters; form comes from light/shadow only, like the Saturn/heart shaders. Each cell is sampled with 2×4 sub-pixels, half-covered edge cells get lighter characters, ramp `.:;+*%#$@` (no horizontal characters → no scan-line look). Grass overlays use the same ramp: dense at the root, sparse at the tip, with wind sway.
* **Smooth motion:** 48-frame loops at 8 FPS; **no render at runtime**, only changed cells are drawn. Colours are quantised to 5 bits per channel so tiny shading changes do not redraw cells.
* **Two ways to build scenes:**
  * **Parametric SDF models** (`tools/scenes/animals.py`): NumPy ray-marching at *build time* (key light, soft shadow, sky fill, AO, specular) → cell grid. All geometry is in this repository.
  * **CC0 3D models** (`tools/scenes/mesh_scenes.py`): `sentinel_robot_3d`, `astronaut_eva_3d`, `knight_sitting_3d`, `hd_knight_resting` are rendered from public-domain models prepared with `tools/blender_prep.py` (Blender in background mode: pick objects, decimate, bake material colours into vertex colours; the astronaut's T-pose arms are lowered around the shoulder). They sway ±25° in a seamless loop. **The model files are not in the repository** (`tools/models_cache/` is git-ignored); only the generated frames are. Authors, URLs and licences: [`THIRD_PARTY.md`](THIRD_PARTY.md) and each JSON's `model_credit` field (checked by tests).
* **Build:** `python tools/scenes/build_assets.py [ids]` — lightweight by default (3 processes, low priority); fast mode `--workers=8 --normal-priority`.
* **Classic fallback:** every HD asset ships a 62-column single-frame classic fallback (64-colour palette), used when HD is off or the 2-HD limit is reached.
* **Brightness:** the scene converter applies auto-exposure (mean colour brightness target ≈ 0.62); `python tools/hd_brightness.py` prints each asset's mean and the test rejects anything below 125/255.
* **Source/licence:** parametric scenes are original; the four mesh scenes derive from CC0 models listed in `THIRD_PARTY.md`. Reference images were used only as mood/tone inspiration (no copying or tracing).

### Personal images: `tools/import_local_art.py` (never enters the repo)
```bash
python tools/import_local_art.py "C:\Pictures\painting.jpg" --preset high --bg tinted --look vivid --min-brightness 0.45 --subject-mask auto --bg-dim 0.55 --edge-pct 94 --anim wind
```
Output goes to **`%APPDATA%\ASCII_Mate\community`** by default (the app scans it too); writing into the repository is refused without `--allow-repo`. Conversions of other people's work are **for personal use only** — do not commit or share them. Options: `--preset low|medium|high`, `--gamma`, `--edges`, `--bg auto|threshold|solid|tinted`, `--look vivid|soft|photo`, `--clahe`, `--min-brightness`, `--subject-mask auto|center|edge` + `--bg-dim`, `--edge-pct`, `--crop`, `--invert`, `--black-point/--white-point`, `--saturation`, `--anim wind|embers|pulse`.

### Sample assets and licence
Two samples are generated entirely by `tools/make_hd_samples.py` (no external images or meshes): `hd_torus_knot_spin` (150×75, 48 frames) and `hd_poppy_field` (190×44, 24 frames). Generated data is under the project licence (CC0-equivalent free use).

### HD performance (`python tests/bench_render.py --hd`)
Windows 11, offscreen Qt, single-core estimate; "CPU" = tick + `paintEvent` time ÷ timer interval. On a 4-core machine total CPU ≈ value ÷ 4.

| Scenario | Quality | Interval | ms/tick | CPU (1 core) | +RAM |
|---|---|---|---|---|---|
| Lightly moving grass/poppies (10 FPS) | Medium/High | 100 ms | ≈1.9 | **1.9 %** | ≈3–5 MB |
| Same | Low (≤8 FPS) | 125 ms | ≈2.5 | 2.0 % | ≈4 MB |
| Spinning torus knot | Low (≤8 FPS) | 125 ms | ≈5.9 | 4.7 % | ≈6 MB |
| Same | Medium (≤12 FPS) | 83 ms | ≈5.7 | 6.9 % | ≈4–5 MB |
| Same | High (15 FPS) | 67 ms | ≈5.6 | 8.4 % | ≈5 MB |

For comparison a classic live 3D shader (cat, 12 FPS) is ≈ 8 % of one core. With two HD widgets open the tray process working set is ≈ 147 MB (including Qt).

### Real CPU measurement (before / after)
`python tests/bench_cpu_real.py` starts a real tray host, launches widgets over IPC and measures the **host process's OS CPU time** (not an estimate). Single-core equivalent = CPU time / wall time. "Before" = commit 6a64039 (20 s, one window), "after" = median of 3 × 12 s windows; raw values in `bench_results/*.json`. A laptop's single window can vary by ±3 %. The HD scene rows were measured with earlier versions of the scenes and have **not been re-measured** with the latest assets.

| Scenario | Before (1 core) | After (median) | Target |
|---|---|---|---|
| Saturn | 13.98 % | **3.26 %** | ≤ 4 % ✓ |
| Donut | 13.52 % | **2.73 %** | ≤ 4 % ✓ |
| Heart | 12.73 % | **4.04 %** | ≤ 4 % ≈ |
| Christmas tree | 9.69 % | **3.52 %** | ≤ 4 % ✓ |
| HD poppy (moving) | 1.87 % | **2.99 %** | ≤ 3 % ≈ |
| HD cat (earlier contour version, 8 FPS) | — | **3.52 %** | ≤ 3 % ✗ |
| HD warrior in meadow | — | **2.08 %** | ≤ 3 % ✓ |
| HD spinning torus (10.6 FPS) | 10.55 % | **7.2 %** | ≤ 3 % ✗ |
| Saturn + donut + heart + HD poppy | 48.28 % | **12.11 %** | ≤ 10 % ✗ |

What was done: glyph atlas + changed-cells-only drawing instead of `drawText`, a (character, colour) block cache, repainting only the dirty region, NumPy ray/z-buffer steps for Saturn/donut/heart (**byte-identical output**: equivalence and golden tests), 8 FPS shader default, no ticks for fully covered widgets, 1 Hz for single-frame drawings. What was not reached: the spinning torus changes almost every cell each frame with 1500+ distinct (character, colour) pairs, so the cache cannot help; four heavy widgets together ≈ 12 % (target 10 %). Easiest saving: Fine-Tuning → Manual FPS, or HD Quality → Low.

---

## 🔋 Performance tips

* Math 3D shaders run at **8 FPS** by default and HD animals at 8 FPS (48-frame loop); change it in **Fine-Tuning → Manual FPS**. Lower FPS and a smaller grid (`Compact`) directly reduce CPU.
* The shadow is a single pass; **Glow is off by default** (extra paint pass).
* Drawing pauses while the **screen is locked**, and when a fullscreen app covers the widget's screen (unless the widget is "Always on Top"). On **battery** FPS drops ~40 % automatically (can be disabled in the tray).
* Static animations only update at 1–8 FPS when a frame/particle/timer needs it.
* Error logs: `%APPDATA%\ASCII_Mate\logs\ascii_mate.log` (rotating).

---

## 🧩 Library rules

* If the same `id` exists in two files, the **built-in animation wins**; a community file never overrides it (a warning is logged).
* Several copies of one animation can be open; each keeps its **own position/settings** (`id`, `id#2`, ...). Timer duration is saved but **never starts by itself**.
* IPC (Terminal Hub ↔ tray host) is protected by a per-user `authkey` (`%APPDATA%\ASCII_Mate\ipc.key`).

---

## 🌍 Creating community animations (`.ascii.json` and `.txt`)

### Option 1: plain text (`.txt`)
Separate frames with a **`===FRAME===`** line:

```text
  /\_/\
 ( o.o )
  > ^ <
===FRAME===
  /\_/\
 ( -.- )
  > ^ <
```
Drop the file onto an open widget, or press **`I`** in the Terminal Hub — it is converted to `.ascii.json` and aligned automatically.

### Option 2: `.ascii.json`
Put files into `assets/animations/community/` as `<name>.ascii.json`:

```json
{
  "schema_version": "1.0",
  "id": "cozy_snow_cloud",
  "name": "Kar Yağdıran Bulut",
  "name_en": "Snow-Dropping Cloud",
  "category": "Topluluk / Özel Eklenenler",
  "author": "Your name",
  "tags": ["cloud", "snow", "winter"],
  "default_fps": 4,
  "recommended_color": "pastel_blue",
  "particles": {
    "enabled_by_default": true,
    "type": "snow",
    "toggle_label": "Let it snow from the cloud",
    "spawn_area": "bottom",
    "density": "medium",
    "chars": ["*", ".", "+", "o"]
  },
  "frames": [
    "   .--.    \n .-(    ). \n(___.__)__)",
    "   .--.    \n .-(    )~ \n(___.__)__)"
  ]
}
```
`name_en` is optional (English UI shows it when present). The optional `"blink_patterns": [["o.o", "-.-"]]` defines custom blink substitutions (equal-length text pairs). Supported `particles.type` values: `"none"`, `"snow"`, `"rain"`, `"lightning"`, `"steam"`, `"hearts"`, `"sparks"`, `"stars"`.

---

## Türkçe

**ASCII Mate**, ders çalışırken/kod yazarken masaüstünüzde PDF ve pencerelerin üzerinde süzülen, tamamen saydam, sürüklenebilir **141 ASCII animasyonu** (123 klasik/3B shader + 18 HD renkli) sunan bir **Windows 10/11** uygulamasıdır. Arayüz varsayılan olarak **İngilizcedir**; tepsi menüsünden **Language → Türkçe** ile Türkçeye geçebilirsiniz (ayar `config.json` içinde `"language": "tr"`). Varlık id'leri değişmediği için favoriler ve profiller dil değişiminde bozulmaz.

**Kurulum:** `baslat.bat` dosyasına çift tıklayın (eksik `PyQt6` ve `rich` otomatik kurulur ve Terminal Hub açılır).
**Komut satırı:** `python main.py` (Terminal Hub) · `python main.py --widget saturn_3d` (doğrudan masaüstüne) · `python tests/validate_library.py` · `python -m pytest tests -q`.
**.exe üretmek için:** `build_exe.bat` (`ASCII_Mate.exe` + `ASCII_Mate_CLI.exe`).

**Temel kullanım:** sol tık + sürükle = taşı · tekerlek / köşe tutmaçları = boyut · sağ tık = saydamlık, Pomodoro zamanlayıcı, renk, efektler, **Hayalet Modu** (tıklama geçirgen) · Shift + sol tık = 3B kamera · sistem tepsisi = masaüstü düzenleri (profiller), HD mod, pil tasarrufu, dil. Terminal Hub'da `F` favori, `C` tema, `I` içe aktar. HD mod varsayılan kapalıdır ve daha fazla CPU/RAM kullanır; aynı anda en fazla 2 HD widget açılabilir. Robot, astronot ve şövalye HD sahneleri CC0 lisanslı 3B modellerden üretilmiştir (künye: `THIRD_PARTY.md`); modeller depoda yoktur.
