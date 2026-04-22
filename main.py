import PIL.Image
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS
import os
import time
import random
import asyncio
import edge_tts
from moviepy.editor import VideoFileClip, AudioFileClip
import yt_dlp
from dotenv import load_dotenv
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted


def pobierz_automatycznie_model():
    print("🔍 Szukam najnowszego dostępnego modelu w API...")

    # Przeszukujemy wszystkie modele przypisane do Twojego klucza
    for model in genai.list_models():
        # Szukamy modelu, który obsługuje tekst i jest z szybkiej/taniej rodziny "flash"
        if 'generateContent' in model.supported_generation_methods and 'flash' in model.name:
            print(f"✅ Wybrano automatycznie model: {model.name}")
            # Zwraca gotową nazwę, np. 'models/gemini-1.5-flash-002'
            return model.name

    print("⚠️ Nie udało się przefiltrować modeli, używam domyślnego.")
    return 'gemini-1.5-flash-latest'

# ==========================================
# 1. KONFIGURACJA I KLUCZE API
# ==========================================
# UWAGA: Klucz wklejony na Twoje życzenie. Uważaj, żeby nie udostępnić tego pliku w sieci!
GEMINI_API_KEY = ""

genai.configure(api_key=GEMINI_API_KEY)

# ==========================================
# 2. KONFIGURACJA PLIKÓW I FOLDERÓW
# ==========================================
FOLDER_WYJSCIOWY = "gotowe_filmy"
PLIK_TLA_NAZWA = "minecraft_tlo.mp4"
URL_KANALU = "https://www.youtube.com/@OrbitalNCG/videos"

os.makedirs(FOLDER_WYJSCIOWY, exist_ok=True)

TEMATY = [
    "opuszczony szpital", "dziwna aplikacja w telefonie", "istota w lesie",
    "nocna zmiana na stacji benzynowej", "niepokojący sąsiad z naprzeciwka",
    "nagranie z ukrytej kamery", "przeklęta gra wideo", "człowiek bez twarzy",
    "tajemnicze drzwi w piwnicy", "głos z wentylacji", "znikające odbicie w lustrze"
]

JEZYKI = [
    {
        "id": "PL",
        "glos": "pl-PL-ZofiaNeural",
        "prompt": (
            "Napisz krótką, dziwną, wciągającą historię po polsku (ok. 130 słów) na temat: '{temat}'. "
            "ZASADY: 1) Zadbaj o IDEALNĄ, naturalną polską gramatykę, interpunkcję i składnię. "
            "2) Historia MUSI mieć otwarte zakończenie (cliffhanger) w najbardziej napiętym momencie. "
            "Styl: Creepypasta / Reddit Horror. Tylko tekst, bez żadnych tytułów i wstępów."
        )
    },
]


async def wygeneruj_historie_ai(konfiguracja):
    temat = random.choice(TEMATY)
    print(f"🧠 AI wymyśla nową historię [{konfiguracja['id']}] na temat: {temat}...")

    prompt_finalny = konfiguracja["prompt"].format(temat=temat)

    # ----------------------------------------------------
    # TUTAJ JEST ZMIANA: Model sam się znajduje i wpisuje
    # ----------------------------------------------------
    nazwa_modelu = pobierz_automatycznie_model()
    model = genai.GenerativeModel(nazwa_modelu)
    # ----------------------------------------------------

    for proba in range(3):
        try:
            response = model.generate_content(prompt_finalny)
            return response.text.strip()
        except ResourceExhausted:
            print(f"⏳ Błąd 429: API przeciążone. Czekam 20 sekund przed kolejną próbą ({proba + 1}/3)...")
            await asyncio.sleep(60)
        except Exception as e:
            print(f"⚠️ Nieoczekiwany błąd API: {e}. Próbuję ponownie...")
            await asyncio.sleep(5)

    print("❌ Krytyczny błąd: Nie udało się połączyć z API Gemini po 3 próbach.")
    exit(1)


async def wygeneruj_audio(tekst, glos, plik_audio):
    print(f"🎙️ Generowanie głosu ({glos})...")
    communicate = edge_tts.Communicate(tekst, glos)
    await communicate.save(plik_audio)
    print("✅ Głos gotowy.")


def pobierz_losowe_z_kanalu(url_kanalu):
    if os.path.exists(PLIK_TLA_NAZWA):
        try:
            os.remove(PLIK_TLA_NAZWA)
            print("🗑️ Usunięto stare tło.")
        except Exception as e:
            print(f"⚠️ Nie można usunąć starego tła: {e}")

    print(f"📡 Pobieram nowy film z kanału do tła...")
    ydl_opts_list = {'extract_flat': True, 'quiet': True}
    with yt_dlp.YoutubeDL(ydl_opts_list) as ydl:
        result = ydl.extract_info(url_kanalu, download=False)
        filmy = result.get('entries', [])[:20]
        wybrany = random.choice(filmy)
        url_filmu = f"https://www.youtube.com/watch?v={wybrany['id']}"

    ydl_opts_dl = {
        'format': 'bestvideo[ext=mp4]/best[ext=mp4]',
        'outtmpl': PLIK_TLA_NAZWA,
        'quiet': True
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts_dl) as ydl:
            ydl.download([url_filmu])
    except Exception as e:
        print(f"❌ Błąd pobierania yt-dlp: {e}")
        exit(1)

    return PLIK_TLA_NAZWA


async def stworz_shorta(konfig_jezyka):
    print(f"\n--- 🚀 WERSJA: {konfig_jezyka['id']} ---")

    timestamp = int(time.time())
    plik_audio_tmp = f"tmp_audio_{konfig_jezyka['id']}_{timestamp}.mp3"
    plik_wyjsciowy = os.path.join(FOLDER_WYJSCIOWY, f"brainrot_{konfig_jezyka['id']}_{timestamp}.mp4")

    audio_clip = None
    bg_wideo = None
    wideo_clip = None
    final = None

    try:
        historia = await wygeneruj_historie_ai(konfig_jezyka)
        pobierz_losowe_z_kanalu(URL_KANALU)
        await wygeneruj_audio(historia, konfig_jezyka["glos"], plik_audio_tmp)

        audio_clip = AudioFileClip(plik_audio_tmp)
        czas_trwania = audio_clip.duration + 0.8
        bg_wideo = VideoFileClip(PLIK_TLA_NAZWA)

        print("🧱 Docinanie tła i renderowanie wideo...")
        start_time = random.uniform(0, max(0, bg_wideo.duration - czas_trwania))

        wideo_clip = bg_wideo.subclip(start_time, start_time + czas_trwania)
        szer, wys = wideo_clip.size
        nowa_szerokosc = int(wys * (9 / 16))

        final = (wideo_clip.crop(x_center=szer / 2, width=nowa_szerokosc)
                 .resize(height=1920)
                 .set_audio(audio_clip))

        final.write_videofile(
            plik_wyjsciowy,
            fps=30,
            codec="libx264",
            audio_codec="aac",
            threads=4,
            logger=None
        )

    except Exception as e:
        print(f"❌ Wystąpił błąd podczas montażu wideo: {e}")
    finally:
        print("🧹 Sprzątanie plików z pamięci...")
        if audio_clip: audio_clip.close()
        if bg_wideo: bg_wideo.close()
        if wideo_clip: wideo_clip.close()
        if final: final.close()

        await asyncio.sleep(1)
        if os.path.exists(plik_audio_tmp):
            try:
                os.remove(plik_audio_tmp)
            except Exception:
                pass


async def main():
    numer_serii = 1
    while True:
        print(f"\n{'=' * 50}")
        print(f"🎬 ROZPOCZYNAM SERIĘ GENEROWANIA NR {numer_serii}")
        print(f"{'=' * 50}")

        for jezyk in JEZYKI:
            await stworz_shorta(jezyk)

        print(f"\n🎉 SUKCES! Seria {numer_serii} zakończona. Filmy są w folderze '{FOLDER_WYJSCIOWY}'.")
        print("⏳ Czekam 10 sekund przed rozpoczęciem kolejnej serii...")
        print("🛑 (Aby zatrzymać program, wciśnij Ctrl+C)")

        await asyncio.sleep(10)
        numer_serii += 1


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Program zatrzymany przez użytkownika.")
