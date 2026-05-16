import PIL.Image
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

import os
import re
import time
import random
import asyncio
import edge_tts
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip, vfx
import yt_dlp
from dotenv import load_dotenv
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted

# ==========================================
# 1. KONFIGURACJA I KLUCZE API
# ==========================================
load_dotenv("geminiapikey.env")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise RuntimeError("Brak GEMINI_API_KEY. Dodaj go w pliku geminiapikey.env.")

genai.configure(api_key=GEMINI_API_KEY)

# ==========================================
# 2. KONFIGURACJA PLIKOW I FOLDEROW
# ==========================================
BASE_DIR          = os.path.dirname(os.path.abspath(__file__))
FOLDER_WYJSCIOWY  = os.path.join(BASE_DIR, "gotowe_filmy")   # tymczasowy – wideo bez napisow
FOLDER_UPLOAD     = os.path.join(BASE_DIR, "filmy")           # cel finalny – wideo z napisami
PLIK_TLA_NAZWA    = os.path.join(BASE_DIR, "minecraft_tlo.mp4")
URL_KANALU        = "https://www.youtube.com/@OrbitalNCG/videos"
PLIK_FONTU        = os.path.join(BASE_DIR, "FredokaOne-Regular.ttf")
SZEROKOSC_SHORTA  = 1080
WYSOKOSC_SHORTA   = 1920
MAKS_ZNAKOW_NAPISU = 72
MAKS_SLOW_NAPISU  = 2
SLOWA_AKCENTOWANE = {
    "NIE", "NIGDY", "KREW", "CIEN", "KRZYK", "STRACH", "DZIWNE", "SEKRET",
    "MROCZNY", "MROKU", "DRZWI", "NOCY", "CISZA", "CISZY", "PATRZYL",
    "FRIEND", "BOYS", "STOP", "HELP", "DEAD", "SCARY"
}

# ==========================================
# 3. USTAWIENIA LIMITOW API (ANTI-429)
# ==========================================
PRZERWA_MIEDZY_SERIAMI  = 300
MAKS_PROB_API           = 5
BAZOWY_CZAS_OCZEKIWANIA = 60

os.makedirs(FOLDER_WYJSCIOWY, exist_ok=True)
os.makedirs(FOLDER_UPLOAD,    exist_ok=True)

JEZYKI = [
    {
        "id":       "PL",
        "glos":     "pl-PL-ZofiaNeural",
        "tempo":    "+10%",
        "wysokosc": "+8Hz",
        "glosnosc": "+12%",
    },
]

# ==========================================
# 4. SILNIK NAPISOW (identyczny z program_napisy.py)
# ==========================================

def wczytaj_font(rozmiar):
    if os.path.exists(PLIK_FONTU):
        return ImageFont.truetype(PLIK_FONTU, rozmiar)
    return ImageFont.truetype("arial.ttf", rozmiar)


def zawin_linie(draw, tekst, font, max_szerokosc):
    linie, aktualna = [], []
    for slowo in tekst.split():
        kandydat = " ".join(aktualna + [slowo])
        if draw.textlength(kandydat, font=font) <= max_szerokosc or not aktualna:
            aktualna.append(slowo)
        else:
            linie.append(" ".join(aktualna))
            aktualna = [slowo]
    if aktualna:
        linie.append(" ".join(aktualna))
    return linie


def podziel_timingi_na_napisy(timingi_slow, czas_trwania):
    grupy, grupa = [], []
    for timing in timingi_slow:
        slowo = timing["text"].strip()
        if not slowo:
            continue
        if grupa and timing["start"] - grupa[-1]["end"] > 0.28:
            grupy.append(grupa)
            grupa = []
        grupa.append(timing)
        tekst_grupy = " ".join(i["text"] for i in grupa)
        if (len(grupa) >= MAKS_SLOW_NAPISU
                or len(tekst_grupy) >= MAKS_ZNAKOW_NAPISU
                or grupa[-1]["end"] - grupa[0]["start"] >= 0.9):
            grupy.append(grupa)
            grupa = []
    if grupa:
        grupy.append(grupa)

    wynik = []
    for idx, grp in enumerate(grupy):
        start = max(0, grp[0]["start"] - 0.035)
        end   = min(czas_trwania, grp[-1]["end"] + 0.08)
        if idx + 1 < len(grupy):
            end = min(end, max(0, grupy[idx + 1][0]["start"] - 0.035))
        if end <= start:
            end = min(czas_trwania, start + 0.18)
        wynik.append({
            "text":     " ".join(i["text"] for i in grp),
            "start":    start,
            "duration": max(0.16, end - start),
        })
    return wynik


def utworz_klip_napisu(tekst, start, czas):
    szerokosc, wysokosc = 1080, 270
    obraz = Image.new("RGBA", (szerokosc, wysokosc), (0, 0, 0, 0))
    draw  = ImageDraw.Draw(obraz)
    tekst = tekst.upper()
    fs, sw = 104, 10

    while fs >= 66:
        font  = wczytaj_font(fs)
        linie = zawin_linie(draw, tekst, font, szerokosc - 80)
        bbox  = draw.multiline_textbbox((0, 0), "\n".join(linie), font=font,
                                        spacing=4, stroke_width=sw)
        if len(linie) <= 1 and (bbox[3] - bbox[1]) <= 150:
            break
        fs -= 2

    slowa = tekst.split()
    bbox  = draw.textbbox((0, 0), " ".join(slowa), font=font, stroke_width=sw)
    x = (szerokosc - (bbox[2] - bbox[0])) / 2
    y = (wysokosc  - (bbox[3] - bbox[1])) / 2 - 4

    for idx, slowo in enumerate(slowa):
        if slowo in SLOWA_AKCENTOWANE:
            kolor = (255, 53, 86, 255)
        elif idx == len(slowa) - 1 and len(slowa) > 1:
            kolor = (255, 224, 35, 255)
        else:
            kolor = (255, 255, 255, 255)

        if idx > 0:
            x += draw.textlength(" ", font=font)

        draw.text((x + 7, y + 9), slowo, font=font, fill=(0, 0, 0, 150),
                  stroke_width=sw + 2, stroke_fill=(0, 0, 0, 150))
        draw.text((x + 3, y + 3), slowo, font=font, fill=(255, 255, 255, 80),
                  stroke_width=sw,     stroke_fill=(0, 0, 0, 255))
        draw.text((x, y),         slowo, font=font, fill=kolor,
                  stroke_width=sw,     stroke_fill=(0, 0, 0, 255))
        x += draw.textlength(slowo, font=font)

    return (
        ImageClip(np.array(obraz))
        .set_start(start)
        .set_duration(czas)
        .resize(lambda t: 0.88 + 0.16 * min(1, t / 0.12))
        .set_position(("center", int(WYSOKOSC_SHORTA * 0.53)))
    )


def utworz_napisy_z_timingow(timingi_slow, czas_trwania):
    klipy = []
    for napis in podziel_timingi_na_napisy(timingi_slow, czas_trwania):
        if napis["start"] >= czas_trwania:
            continue
        czas = min(napis["duration"], czas_trwania - napis["start"])
        if czas <= 0:
            continue
        klipy.append(utworz_klip_napisu(napis["text"], napis["start"], czas))
    return klipy

# ==========================================
# 5. AI + AUDIO
# ==========================================

def pobierz_automatycznie_model():
    print("Szukam najnowszego modelu Gemini...")
    for model in genai.list_models():
        if 'generateContent' in model.supported_generation_methods and 'flash' in model.name:
            print(f"Wybrano model: {model.name}")
            return model.name
    return 'gemini-1.5-flash-latest'


async def wygeneruj_historie_ai(model):
    prompt = (
        "Wymysl losowy, oryginalny i lekko przerazajacy motyw, a potem napisz po polsku "
        "krotka historie do filmu Short, okolo 120-140 slow. Pisz naturalnie, prostymi "
        "zdaniami, z poprawna interpunkcja, zeby tekst dobrze brzmial czytany glosem AI "
        "i ladnie dzielil sie na napisy. Historia ma miec otwarte zakonczenie w najbardziej "
        "napietym momencie. Styl: creepypasta / Reddit horror. Zwroc tylko tekst historii, "
        "bez tytulu, wstepu i komentarzy."
    )
    for proba in range(MAKS_PROB_API):
        try:
            response = model.generate_content(prompt)
            return response.text.strip()
        except ResourceExhausted:
            czas = BAZOWY_CZAS_OCZEKIWANIA * (2 ** proba)
            print(f"API 429 – czekam {czas}s (proba {proba+1}/{MAKS_PROB_API})...")
            await asyncio.sleep(czas)
        except Exception as e:
            print(f"Blad API: {e}. Czekam 10s...")
            await asyncio.sleep(10)
    raise RuntimeError("Nie udalo sie polaczyc z Gemini.")


async def wygeneruj_audio(tekst, glos, plik_audio, tempo, wysokosc, glosnosc):
    print(f"Generowanie glosu ({glos})...")
    communicate  = edge_tts.Communicate(tekst, glos, rate=tempo, pitch=wysokosc,
                                        volume=glosnosc, boundary="WordBoundary")
    timingi_slow = []
    with open(plik_audio, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                s = chunk["offset"] / 10_000_000
                d = chunk["duration"] / 10_000_000
                timingi_slow.append({"text": chunk["text"], "start": s, "end": s + d})
    print(f"Glos gotowy – {len(timingi_slow)} slow z timingiami.")
    return timingi_slow


def pobierz_losowe_z_kanalu(url_kanalu):
    if os.path.exists(PLIK_TLA_NAZWA):
        try:
            os.remove(PLIK_TLA_NAZWA)
        except Exception as e:
            print(f"Nie mozna usunac starego tla: {e}")

    print("Pobieram nowy film z kanalu do tla...")
    with yt_dlp.YoutubeDL({'extract_flat': True, 'quiet': True}) as ydl:
        result = ydl.extract_info(url_kanalu, download=False)
        filmy  = result.get('entries', [])[:20]
        if not filmy:
            raise RuntimeError("Nie znaleziono filmow na kanale YouTube.")
        wybrany    = random.choice(filmy)
        url_filmu  = f"https://www.youtube.com/watch?v={wybrany['id']}"

    with yt_dlp.YoutubeDL({
        'format': 'bestvideo[ext=mp4]/best[ext=mp4]',
        'outtmpl': PLIK_TLA_NAZWA,
        'quiet':   True
    }) as ydl:
        ydl.download([url_filmu])

    return PLIK_TLA_NAZWA

# ==========================================
# 6. GLOWNY PIPELINE – generuj + napisy + zapis do upload
# ==========================================

async def stworz_shorta(konfig, model):
    """
    Pelny pipeline dla jednego shorta:
      1. Gemini generuje tekst
      2. edge_tts robi audio z timingiami
      3. Pobiera tlo z YouTube
      4. Montuje wideo z tlem
      5. Naklada napisy zsynchronizowane z timingiami
      6. Zapisuje finalny plik do FOLDER_UPLOAD (filmy/)
    """
    print(f"\n--- WERSJA: {konfig['id']} ---")

    ts           = int(time.time())
    plik_audio   = os.path.join(BASE_DIR, f"tmp_audio_{konfig['id']}_{ts}.mp3")
    plik_wynikowy = os.path.join(FOLDER_UPLOAD,
                                 f"short_{konfig['id']}_{ts}.mp4")

    audio_clip = bg_wideo = wideo_clip = bazowy_klip = final = None
    napisy = []

    try:
        # 1. Historia przez AI
        print("Generuje tekst historii...")
        historia = await wygeneruj_historie_ai(model)
        print(f"Tekst ({len(historia.split())} slow):\n{historia[:100]}...\n")

        # 2. Tlo z YouTube
        pobierz_losowe_z_kanalu(URL_KANALU)

        # 3. Audio TTS z timingiami slow
        timingi_slow = await wygeneruj_audio(
            historia,
            konfig["glos"],
            plik_audio,
            konfig.get("tempo",    "+10%"),
            konfig.get("wysokosc", "+8Hz"),
            konfig.get("glosnosc", "+12%"),
        )
        if not timingi_slow:
            raise RuntimeError("edge_tts nie zwrocil timingow slow.")

        # 4. Montaz wideo
        audio_clip   = AudioFileClip(plik_audio)
        czas_trwania = audio_clip.duration + 0.8

        bg_wideo = VideoFileClip(PLIK_TLA_NAZWA)
        if bg_wideo.duration < czas_trwania:
            bg_wideo = bg_wideo.fx(vfx.loop, duration=czas_trwania + 1)

        start_time = random.uniform(0, max(0, bg_wideo.duration - czas_trwania))
        wideo_clip  = bg_wideo.subclip(start_time, start_time + czas_trwania)
        szer, wys   = wideo_clip.size
        nowa_szer   = int(wys * (9 / 16))
        bazowy_klip = (wideo_clip
                       .crop(x_center=szer / 2, width=nowa_szer)
                       .resize((SZEROKOSC_SHORTA, WYSOKOSC_SHORTA)))

        # 5. Napisy zsynchronizowane z audio (timingami slow)
        print("Nakladam napisy...")
        napisy = utworz_napisy_z_timingow(timingi_slow, czas_trwania)
        if not napisy:
            print("Brak timingow – awaryjne napisy.")
            napisy = []   # bez napisow awaryjnych; mozna dodac fallback

        final = (CompositeVideoClip([bazowy_klip, *napisy],
                                    size=(SZEROKOSC_SHORTA, WYSOKOSC_SHORTA))
                 .set_audio(audio_clip))

        # 6. Zapis do folderu upload (filmy/)
        print(f"Renderuje finalny film do: {plik_wynikowy}")
        final.write_videofile(
            plik_wynikowy,
            fps=30,
            codec="libx264",
            audio_codec="aac",
            threads=4,
            logger=None,
        )
        print(f"✅ Gotowe! Film zapisany: {plik_wynikowy}")
        return plik_wynikowy

    except Exception as e:
        print(f"❌ Blad podczas tworzenia shorta: {e}")
        return None

    finally:
        print("Sprzatanie pamieci...")
        for obj in [final, bazowy_klip, wideo_clip, bg_wideo, audio_clip]:
            try:
                if obj:
                    obj.close()
            except Exception:
                pass
        for n in napisy:
            try:
                n.close()
            except Exception:
                pass
        await asyncio.sleep(1)
        if os.path.exists(plik_audio):
            try:
                os.remove(plik_audio)
            except Exception:
                pass


# ==========================================
# 7. GLOWNA PETLA
# ==========================================

async def main():
    print("Inicjalizacja AI...")
    nazwa_modelu = pobierz_automatycznie_model()
    model        = genai.GenerativeModel(nazwa_modelu)

    numer_serii = 1
    while True:
        print(f"\n{'='*50}")
        print(f"ROZPOCZYNAM SERIE NR {numer_serii}")
        print(f"{'='*50}")

        for jezyk in JEZYKI:
            wynik = await stworz_shorta(jezyk, model)
            if wynik:
                print(f"Film gotowy do uploadu: {wynik}")

        print(f"\nSeria {numer_serii} zakonczona.")
        print(f"Czekam {PRZERWA_MIEDZY_SERIAMI // 60} minut przed kolejna seria...")
        print("(Ctrl+C aby zatrzymac)")

        await asyncio.sleep(PRZERWA_MIEDZY_SERIAMI)
        numer_serii += 1


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProgram zatrzymany.")
