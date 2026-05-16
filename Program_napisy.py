"""
program_napisy.py  –  Automatyczny procesor napisow
====================================================
Dzialanie:
  1. Skanuje folder  filmy/          (filmy do obrobki)
  2. Dla kazdego wideo:
       a) generuje tekst narracji przez Gemini AI
       b) tworzy audio TTS z edge_tts (z timingiami slow)
       c) naklada zsynchronizowane napisy na wideo
       d) gotowy plik przenosi do  filmy/  (folder 'do uploadu')
       e) oryginalne wideo usuwa z folderu wejsciowego
  3. Moze dzialac w petli (tryb Watch) lub jednorazowo
"""

import PIL.Image
if not hasattr(PIL.Image, "ANTIALIAS"):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

import asyncio
import os
import queue
import re
import shutil
import subprocess
import threading
import time

import customtkinter as ctk
import edge_tts
import numpy as np
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import (
    AudioFileClip, CompositeVideoClip, ImageClip, VideoFileClip, vfx
)

import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted

# ─────────────────────────────────────────────────────────────────────────────
# KONFIGURACJA
# ─────────────────────────────────────────────────────────────────────────────

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
FOLDER_INPUT = os.path.join(BASE_DIR, "filmy")           # tu leza wideo do obrobki
FOLDER_OUT   = os.path.join(BASE_DIR, "filmy")           # gotowe trafia tez do 'filmy' (upload)
FOLDER_DONE  = os.path.join(BASE_DIR, "filmy_z_napisami") # kopia archiwalna (opcjonalna)
FONT_PATH    = os.path.join(BASE_DIR, "FredokaOne-Regular.ttf")

VIDEO_EXTENSIONS = (".mp4", ".mkv", ".mov", ".avi")

SHORT_WIDTH  = 1080
SHORT_HEIGHT = 1920
MAX_WORDS    = 2
MAX_CHARS    = 72
ACCENT_WORDS = {
    "NIE", "NIGDY", "KREW", "CIEN", "KRZYK", "STRACH", "DZIWNE", "SEKRET",
    "MROCZNY", "MROKU", "DRZWI", "NOCY", "CISZA", "CISZY", "PATRZYL",
    "STOP", "HELP", "DEAD", "SCARY", "FRIEND", "BOYS",
}

VOICE   = "pl-PL-ZofiaNeural"
RATE    = "+10%"
PITCH   = "+8Hz"
VOLUME  = "+12%"

GEMINI_PROMPT = (
    "Wymysl losowy, oryginalny i lekko przerazajacy motyw, a potem napisz po polsku "
    "krotka historie do filmu Short, okolo 120-140 slow. Pisz naturalnie, prostymi "
    "zdaniami, z poprawna interpunkcja, zeby tekst dobrze brzmial czytany glosem AI "
    "i ladnie dzielil sie na napisy. Historia ma miec otwarte zakonczenie w najbardziej "
    "napietym momencie. Styl: creepypasta / Reddit horror. Zwroc tylko tekst historii, "
    "bez tytulu, wstepu i komentarzy."
)

MAKS_PROB_API          = 5
BAZOWY_CZAS_OCZEKIWANIA = 60   # sekundy (exponential backoff)
INTERVAL_WATCH         = 60   # co ile sekund skanowac folder w trybie Watch

# ─────────────────────────────────────────────────────────────────────────────
# SUBTITLE ENGINE  (identyczny jak w main.py)
# ─────────────────────────────────────────────────────────────────────────────

def load_font(size):
    if os.path.exists(FONT_PATH):
        return ImageFont.truetype(FONT_PATH, size)
    return ImageFont.truetype("arial.ttf", size)


def wrap_lines(draw, text, font, max_width):
    lines, current = [], []
    for word in text.split():
        candidate = " ".join(current + [word])
        if draw.textlength(candidate, font=font) <= max_width or not current:
            current.append(word)
        else:
            lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines


def split_word_timings(word_timings, duration):
    groups, group = [], []
    for timing in word_timings:
        word = timing["text"].strip()
        if not word:
            continue
        if group and timing["start"] - group[-1]["end"] > 0.28:
            groups.append(group)
            group = []
        group.append(timing)
        group_text = " ".join(i["text"] for i in group)
        if (len(group) >= MAX_WORDS
                or len(group_text) >= MAX_CHARS
                or group[-1]["end"] - group[0]["start"] >= 0.9):
            groups.append(group)
            group = []
    if group:
        groups.append(group)

    captions = []
    for idx, grp in enumerate(groups):
        start = max(0, grp[0]["start"] - 0.035)
        end   = min(duration, grp[-1]["end"] + 0.08)
        if idx + 1 < len(groups):
            end = min(end, max(0, groups[idx + 1][0]["start"] - 0.035))
        if end <= start:
            end = min(duration, start + 0.18)
        captions.append({
            "text":     " ".join(i["text"] for i in grp),
            "start":    start,
            "duration": max(0.16, end - start),
        })
    return captions


def create_caption_clip(text, start, duration):
    w, h   = 1080, 270
    image  = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw   = ImageDraw.Draw(image)
    text   = text.upper()
    fs, sw = 104, 10

    while fs >= 66:
        font  = load_font(fs)
        lines = wrap_lines(draw, text, font, w - 80)
        bbox  = draw.multiline_textbbox((0, 0), "\n".join(lines), font=font,
                                        spacing=4, stroke_width=sw)
        if len(lines) <= 1 and (bbox[3] - bbox[1]) <= 150:
            break
        fs -= 2

    words = text.split()
    bbox  = draw.textbbox((0, 0), " ".join(words), font=font, stroke_width=sw)
    x = (w - (bbox[2] - bbox[0])) / 2
    y = (h - (bbox[3] - bbox[1])) / 2 - 4

    for idx, word in enumerate(words):
        if word in ACCENT_WORDS:
            color = (255, 53, 86, 255)
        elif idx == len(words) - 1 and len(words) > 1:
            color = (255, 224, 35, 255)
        else:
            color = (255, 255, 255, 255)

        if idx > 0:
            x += draw.textlength(" ", font=font)

        draw.text((x + 7, y + 9), word, font=font, fill=(0, 0, 0, 150),
                  stroke_width=sw + 2, stroke_fill=(0, 0, 0, 150))
        draw.text((x + 3, y + 3), word, font=font, fill=(255, 255, 255, 80),
                  stroke_width=sw, stroke_fill=(0, 0, 0, 255))
        draw.text((x, y),         word, font=font, fill=color,
                  stroke_width=sw, stroke_fill=(0, 0, 0, 255))
        x += draw.textlength(word, font=font)

    return (
        ImageClip(np.array(image))
        .set_start(start)
        .set_duration(duration)
        .resize(lambda t: 0.88 + 0.16 * min(1, t / 0.12))
        .set_position(("center", int(SHORT_HEIGHT * 0.53)))
    )


def create_caption_clips(word_timings, duration):
    return [
        create_caption_clip(c["text"], c["start"], c["duration"])
        for c in split_word_timings(word_timings, duration)
        if c["start"] < duration
    ]

# ─────────────────────────────────────────────────────────────────────────────
# GEMINI AI
# ─────────────────────────────────────────────────────────────────────────────

def init_gemini():
    load_dotenv(os.path.join(BASE_DIR, "geminiapikey.env"))
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("Brak GEMINI_API_KEY w pliku geminiapikey.env!")
    genai.configure(api_key=key)

    for m in genai.list_models():
        if "generateContent" in m.supported_generation_methods and "flash" in m.name:
            return genai.GenerativeModel(m.name)
    return genai.GenerativeModel("gemini-1.5-flash-latest")


async def generate_story(model, log):
    for attempt in range(MAKS_PROB_API):
        try:
            response = model.generate_content(GEMINI_PROMPT)
            return response.text.strip()
        except ResourceExhausted:
            wait = BAZOWY_CZAS_OCZEKIWANIA * (2 ** attempt)
            log(f"⬛ API 429 – czekam {wait}s (proba {attempt+1}/{MAKS_PROB_API})...\n")
            await asyncio.sleep(wait)
        except Exception as e:
            log(f"⚠️ Blad API: {e}. Czekam 10s...\n")
            await asyncio.sleep(10)
    raise RuntimeError("Nie udalo sie polaczyc z Gemini po wszystkich probach.")

# ─────────────────────────────────────────────────────────────────────────────
# AUDIO TTS
# ─────────────────────────────────────────────────────────────────────────────

async def generate_audio(text, audio_path, log):
    log("Generuje glos TTS...\n")
    communicate  = edge_tts.Communicate(text, VOICE, rate=RATE,
                                         pitch=PITCH, volume=VOLUME,
                                         boundary="WordBoundary")
    word_timings = []
    with open(audio_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                s = chunk["offset"] / 10_000_000
                d = chunk["duration"] / 10_000_000
                word_timings.append({"text": chunk["text"], "start": s, "end": s + d})
    log(f"Glos gotowy – {len(word_timings)} slow z timingiami.\n")
    return word_timings

# ─────────────────────────────────────────────────────────────────────────────
# RENDER
# ─────────────────────────────────────────────────────────────────────────────

async def process_video(video_path, model, log):
    """Pelny pipeline dla jednego pliku wideo."""
    name      = os.path.splitext(os.path.basename(video_path))[0]
    ts        = int(time.time())
    audio_tmp = os.path.join(BASE_DIR, f"tmp_napisy_{ts}.mp3")
    out_name  = f"{name}_napisy_{ts}.mp4"
    out_path  = os.path.join(FOLDER_OUT, out_name)

    os.makedirs(FOLDER_OUT,  exist_ok=True)
    os.makedirs(FOLDER_DONE, exist_ok=True)

    video = audio = base = final = None
    captions = []

    try:
        # 1. Tekst z AI
        log(f"[{name}] Generuje tekst przez Gemini AI...\n")
        story = await generate_story(model, log)
        log(f"[{name}] Tekst ({len(story.split())} slow):\n{story[:120]}...\n\n")

        # 2. Audio TTS
        word_timings = await generate_audio(story, audio_tmp, log)
        if not word_timings:
            raise RuntimeError("edge_tts nie zwrocil timingow slow.")

        audio    = AudioFileClip(audio_tmp)
        duration = audio.duration + 0.8

        # 3. Wideo – przygotowanie pod format Shorts
        log(f"[{name}] Przygotowuje wideo pod format Shorts...\n")
        video = VideoFileClip(video_path)
        if video.duration < duration:
            video = video.fx(vfx.loop, duration=duration + 1)

        start_t = max(0, (video.duration - duration) / 2)
        clip    = video.subclip(start_t, start_t + duration)
        vw, vh  = clip.size
        tw      = int(vh * (9 / 16))

        if vw >= tw:
            base = clip.crop(x_center=vw / 2, width=tw).resize((SHORT_WIDTH, SHORT_HEIGHT))
        else:
            r = clip.resize(height=SHORT_HEIGHT)
            if r.w < SHORT_WIDTH:
                r = r.resize(width=SHORT_WIDTH)
            base = r.crop(x_center=r.w / 2, y_center=r.h / 2,
                          width=SHORT_WIDTH, height=SHORT_HEIGHT)

        # 4. Napisy
        log(f"[{name}] Tworze napisy ({len(word_timings)} slow)...\n")
        captions = create_caption_clips(word_timings, duration)
        final    = CompositeVideoClip([base, *captions],
                                      size=(SHORT_WIDTH, SHORT_HEIGHT)).set_audio(audio)

        # 5. Render
        log(f"[{name}] Renderuje MP4...\n")
        final.write_videofile(out_path, fps=30, codec="libx264",
                              audio_codec="aac", threads=4, logger=None)
        log(f"[{name}] ✅ Gotowe → {out_path}\n")

        # 6. Przenies oryginal do archiwum, by nie przetwarzac go ponownie
        archive_path = os.path.join(FOLDER_DONE, os.path.basename(video_path))
        shutil.move(video_path, archive_path)
        log(f"[{name}] Oryginal przeniesiony do archiwum: {FOLDER_DONE}\n")

        return out_path

    finally:
        for obj in [final, base, audio, video]:
            try:
                if obj:
                    obj.close()
            except Exception:
                pass
        for c in captions:
            try:
                c.close()
            except Exception:
                pass
        if os.path.exists(audio_tmp):
            try:
                os.remove(audio_tmp)
            except OSError:
                pass

# ─────────────────────────────────────────────────────────────────────────────
# GLOWNA PETLA
# ─────────────────────────────────────────────────────────────────────────────

async def run_auto(log, stop_event, model, watch_mode=False):
    """Przetwarza wszystkie wideo w folderze. Jesli watch_mode=True, petla ciagle."""
    log(f"📂 Folder wejsciowy: {FOLDER_INPUT}\n")
    log(f"📤 Folder wynikowy:  {FOLDER_OUT}\n\n")

    processed_in_session = set()

    while True:
        files = [
            os.path.join(FOLDER_INPUT, f)
            for f in os.listdir(FOLDER_INPUT)
            if f.lower().endswith(VIDEO_EXTENSIONS)
            and os.path.join(FOLDER_INPUT, f) not in processed_in_session
        ]

        if not files:
            if not watch_mode:
                log("Brak nowych plikow wideo w folderze. Koniec.\n")
                break
            log(f"Brak nowych plikow. Czekam {INTERVAL_WATCH}s...\n")
            for _ in range(INTERVAL_WATCH):
                if stop_event.is_set():
                    break
                await asyncio.sleep(1)
            if stop_event.is_set():
                break
            continue

        log(f"Znaleziono {len(files)} plikow do obrobki.\n\n")

        for video_path in files:
            if stop_event.is_set():
                log("Zatrzymano przez uzytkownika.\n")
                return

            log(f"{'─'*48}\n")
            log(f"🎬 Przetwarzam: {os.path.basename(video_path)}\n")
            try:
                await process_video(video_path, model, log)
                processed_in_session.add(video_path)
            except Exception as e:
                log(f"❌ Blad: {e}\n")

        if not watch_mode:
            break

    log("\n✅ Wszystkie pliki przetworzone.\n")

# ─────────────────────────────────────────────────────────────────────────────
# GUI
# ─────────────────────────────────────────────────────────────────────────────

class AutoSubtitleApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("Auto Napisy TTS – Gemini AI")
        self.geometry("860x640")
        self.minsize(700, 500)

        self.log_queue  = queue.Queue()
        self.stop_event = threading.Event()
        self.worker     = None
        self.model      = None
        self.watch_mode = ctk.BooleanVar(value=False)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_toolbar()
        self._build_log()

        self.after(100, self._flush_log)
        self._init_gemini()

    def _build_toolbar(self):
        bar = ctk.CTkFrame(self)
        bar.grid(row=0, column=0, padx=16, pady=(16, 8), sticky="ew")
        bar.grid_columnconfigure(0, weight=1)

        # Tytul + status
        left = ctk.CTkFrame(bar, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w", padx=10, pady=8)

        ctk.CTkLabel(left, text="Auto Napisy TTS",
                     font=("Arial", 18, "bold")).grid(row=0, column=0, sticky="w")
        self.status_lbl = ctk.CTkLabel(left, text="Inicjalizacja...", text_color="gray")
        self.status_lbl.grid(row=1, column=0, sticky="w")

        # Przyciski
        right = ctk.CTkFrame(bar, fg_color="transparent")
        right.grid(row=0, column=1, sticky="e", padx=10, pady=8)

        ctk.CTkCheckBox(right, text="Tryb Watch\n(petla ciagla)",
                        variable=self.watch_mode).grid(row=0, column=0, padx=(0, 14))

        self.btn_start = ctk.CTkButton(
            right, text="▶  Start", fg_color="#2ea043", hover_color="#238636",
            width=110, state="disabled", command=self._start)
        self.btn_start.grid(row=0, column=1, padx=(0, 8))

        self.btn_stop = ctk.CTkButton(
            right, text="⏹  Stop", fg_color="#da3633", hover_color="#b62324",
            width=110, state="disabled", command=self._stop)
        self.btn_stop.grid(row=0, column=2, padx=(0, 8))

        ctk.CTkButton(right, text="📂 Folder wejsciowy", width=150,
                      command=lambda: self._open_folder(FOLDER_INPUT)
                      ).grid(row=0, column=3, padx=(0, 8))

        ctk.CTkButton(right, text="📤 Folder wynikowy", width=145,
                      command=lambda: self._open_folder(FOLDER_OUT)
                      ).grid(row=0, column=4)

    def _build_log(self):
        frame = ctk.CTkFrame(self)
        frame.grid(row=1, column=0, padx=16, pady=(0, 16), sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        hdr = ctk.CTkFrame(frame, fg_color="transparent")
        hdr.grid(row=0, column=0, padx=8, pady=(8, 4), sticky="ew")
        hdr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hdr, text="Log", text_color="gray").grid(row=0, column=0, sticky="w")
        ctk.CTkButton(hdr, text="Wyczysc", width=78,
                      command=self._clear_log).grid(row=0, column=1)

        self.log_box = ctk.CTkTextbox(frame, font=("Consolas", 12), wrap="word")
        self.log_box.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="nsew")

    # ── Gemini init (w tle) ──────────────────────────────────────────────────

    def _init_gemini(self):
        def _do():
            try:
                m = init_gemini()
                self.model = m
                self.log_queue.put("✅ Gemini AI gotowe.\n")
                self.log_queue.put("__READY__")
            except Exception as e:
                self.log_queue.put(f"❌ Blad inicjalizacji Gemini: {e}\n")
                self.log_queue.put("__ERROR__")

        threading.Thread(target=_do, daemon=True).start()

    # ── Start / Stop ─────────────────────────────────────────────────────────

    def _start(self):
        if self.worker and self.worker.is_alive():
            return
        self.stop_event.clear()
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.status_lbl.configure(text="Dziala...", text_color="#2ea043")
        self._clear_log()

        watch = self.watch_mode.get()
        model = self.model

        def _thread():
            asyncio.run(run_auto(self.log_queue.put, self.stop_event, model, watch))
            self.log_queue.put("__DONE__")

        self.worker = threading.Thread(target=_thread, daemon=True)
        self.worker.start()

    def _stop(self):
        self.stop_event.set()
        self.log_queue.put("⏹ Zatrzymywanie...\n")

    # ── Log flush ────────────────────────────────────────────────────────────

    def _flush_log(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get()
            if msg == "__READY__":
                self.btn_start.configure(state="normal")
                self.status_lbl.configure(text="Gotowy", text_color="gray")
            elif msg == "__ERROR__":
                self.status_lbl.configure(text="Blad Gemini – sprawdz klucz API",
                                          text_color="#da3633")
            elif msg == "__DONE__":
                self.btn_start.configure(state="normal")
                self.btn_stop.configure(state="disabled")
                self.status_lbl.configure(text="Gotowy", text_color="gray")
            else:
                self._append_log(msg)
        self.after(100, self._flush_log)

    def _append_log(self, text):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text)
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def _open_folder(self, folder):
        os.makedirs(folder, exist_ok=True)
        if os.name == "nt":
            os.startfile(folder)
        else:
            subprocess.Popen(["xdg-open", folder])

    def destroy(self):
        self.stop_event.set()
        super().destroy()


if __name__ == "__main__":
    app = AutoSubtitleApp()
    app.mainloop()
