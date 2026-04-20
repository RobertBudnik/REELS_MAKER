# 🎬 REELS_MAKER

Zaawansowany system automatycznego generowania, edytowania i publikowania krótkich filmów (Reels/Shorts) na YouTube z użyciem AI, transkrypcji i profesjonalnych napisów.



# 📋 Struktura projektu

```
REELS_MAKER/
├── main.py                # Główny skrypt - generowanie i edycja wideo
├── subtitles.py           # Transkrypcja i dodawanie profesjonalnych napisów
├── youtube_bot_final.py   # Automatyczna publikacja na YouTube
├── client_secret.json     # ⚠️ Dane OAuth2 (NIE wrzucać do gita!)
├── token.json             # ⚠️ Token dostępu YouTube (wygenerowany automatycznie)
├── FredokaOne-Regular.ttf # Czcionka dla napisów (opcjonalnie)
│
├── gotowe_filmy/          # Output: Gotowe filmy do wrzucenia
├── do_publikacji/         # Input: Filmy do uploadowania na YouTube
├── opublikowane/          # Archiwum: Filmy już opublikowane
├── filmy/                 # Output: Filmy z napisami (ze subtitles.py)
└── README.md              # Ta dokumentacja
```

-----

# 💻 Wymagania systemowe

### Python

  - **Python 3.8+** (rekomendowane 3.10+)

### Systemy operacyjne

  - 🪟 **Windows 10+** (ImageMagick wymagany dla napisów)
  - 🐧 **Linux** (Ubuntu 20.04+)
  - 🍎 **macOS** (12.0+)

### Wymagania sprzętowe

  - **RAM**: Minimum 4 GB (8 GB rekomendowane)
  - **Dysk**: \~2-3 GB wolnego miejsca
  - **Internet**: Wymagane połączenie (API calls)

### Zależności systemowe

#### Windows

Pobierz ImageMagick (dla przetwarzania tekstu w wideo) z [oficjalnej strony](https://imagemagick.org/script/download.php#windows) i zainstaluj z opcją **"Add ImageMagick to PATH"**.

#### Linux (Ubuntu/Debian)

```bash
sudo apt update
sudo apt install imagemagick ffmpeg
```

#### macOS

```bash
brew install imagemagick ffmpeg
```

-----

# 🚀 Instalacja

**1. Klonowanie repozytorium**

```bash
git clone [https://github.com/RobertBudnik/REELS_MAKER.git](https://github.com/RobertBudnik/REELS_MAKER.git)
cd REELS_MAKER
```

**2. Stworzenie wirtualnego środowiska (rekomendowane)**

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/macOS
python3 -m venv venv
source venv/bin/activate
```

**3. Instalacja zależności Python**

```bash
pip install --upgrade pip
pip install google-api-python-client google-auth-oauthlib google-auth-httplib2 google.generativeai edge-tts moviepy yt-dlp openai-whisper
```

**4. Pobranie czcionki (opcjonalnie, dla lepszych napisów)**
Pobierz [Fredoka One Regular](https://www.google.com/search?q=https://fonts.google.com/specimen/Fredoka%2BOne) i umieść plik `FredokaOne-Regular.ttf` w głównym folderze projektu.

-----

# ⚙️ Konfiguracja

### 1\. Konfiguracja Google Gemini API (generowanie historii)

1.  Wejdź na [Google AI Studio](https://ai.google.dev/)
2.  Kliknij "Get API Key" i zaloguj się na swoje konto Google
3.  Skopiuj wygenerowany klucz API
4.  W pliku `main.py` zmień:

<!-- end list -->

```python
GEMINI_API_KEY = "TUTAJ_WKLEJ_SWOJ_KLUCZ"
```

### 2\. Konfiguracja YouTube OAuth2 (publikacja wideo)

1.  Wejdź na [Google Cloud Console](https://console.cloud.google.com/)
2.  Utwórz nowy projekt (np. "REELS\_MAKER")
3.  Przejdź do **API i usługi → Biblioteka**, wyszukaj **YouTube Data API v3** i włącz.
4.  Przejdź do **Dane uwierzytelniające** → **Utwórz dane uwierzytelniające** → **Identyfikator klienta OAuth 2.0**.
5.  Typ aplikacji: **Aplikacja na komputer**.
6.  Pobierz plik JSON i zmień jego nazwę na `client_secret.json`, a następnie wrzuć do głównego folderu projektu.

### 3\. Personalizacja treści (`main.py`)

```python
# Tematy historii (zmień na własne)
TEMATY = [
    "opuszczony szpital",
    "dziwna aplikacja w telefonie",
    "istota w lesie",
]

# URL kanału (dla materiału tła)
URL_KANALU = "[https://www.youtube.com/@OrbitalNCG/videos](https://www.youtube.com/@OrbitalNCG/videos)"

# Folder wyjściowy
FOLDER_WYJSCIOWY = "gotowe_filmy"
```

### 4\. Ustawienia publikacji YouTube (`youtube_bot_final.py`)

```python
# Strefa czasowa
STREFA_PL = ZoneInfo("Europe/Warsaw")

# Metadane wideo
TAGS = ['shorts', 'horror', 'creepypasta', 'polska']
KATEGORIA = '22'  # 22 = Film i animacja
```

-----

# 📖 Użytkowanie

**Scenariusz 1: Pełny workflow (od A do Z)**

```bash
python main.py             # 1. Generowanie i edycja wideo
python subtitles.py        # 2. Dodawanie napisów AI
python youtube_bot_final.py # 3. Publikacja na YouTube
```

**Scenariusz 2: Tylko generowanie wideo**

```bash
python main.py
# Filmy trafią do folderu "gotowe_filmy"
```

**Scenariusz 3: Tylko transkrypcja + napisy**

```bash
# Umieść filmy w folderze "gotowe_filmy"
python subtitles.py
# Gotowe filmy z napisami będą w "filmy"
```

**Scenariusz 4: Tylko publikacja**

```bash
# Umieść filmy mp4 w folderze "do_publikacji"
python youtube_bot_final.py
# Skrypt zaplanuje i opublikuje filmy
```

> **Sterowanie:** Wciśnij `Ctrl + C`, aby zatrzymać program.

-----

# 🔧 Komponenty

### 1\. `main.py` - Silnik generowania wideo

  * Generuje historie AI za pomocą Google Gemini
  * Pobiera losowe wideo z YouTube jako tło
  * Syntezuje mowę (edge-tts)
  * Renderuje finalne wideo (9:16, 1920x1080)

### 2\. `subtitles.py` - Transkrypcja i napisy

  * Transkrybuje wideo za pomocą OpenAI Whisper
  * Generuje dynamiczne napisy słowo-po-słowie
  * Automatyczna synchronizacja czasowa
  * Obsługiwane formaty: `.mp4`, `.mov`, `.mkv`, `.avi`

### 3\. `youtube_bot_final.py` - Publikacja na YouTube

  * Zaplanowana publikacja (Domyślnie Pon-Czw: 15:00 i 19:30 | Pt-Nd: 11:00 i 18:00)
  * Obsługa błędów serwera z "retry logic"
  * Bezpieczne przenoszenie opublikowanych plików do archiwum

-----

# 🔑 API i klucze

  * **Google Gemini API**: Limit 60 zapytań/minutę (darmowy plan). Model `gemini-1.5-flash`.
  * **YouTube Data API v3**: Limit 10,000 jednostek/dzień (darmowy plan). Wymagany zakres: `youtube.upload`.
  * **Edge TTS / OpenAI Whisper**: Brak limitów (przetwarzanie darmowe/lokalne).

-----

# 📊 Performance (Szacunki)

| Operacja | Średni Czas |
| :--- | :--- |
| Generowanie historii AI | 5-10 sekund |
| Synteza mowy (2 minuty audio) | 10-15 sekund |
| Pobieranie tła (YouTube) | 20-40 sekund |
| Renderowanie wideo (1 min) | 1-2 minuty |
| Upload na YouTube | 2-5 minut |
| **Całkowity czas cyklu** | **\~10-15 minut** |

> **Optymalizacja:** Możesz zmniejszyć zużycie zasobów edytując parametry renderowania (np. `threads=2`, rozdzielczość `720p`) lub ładując mniejszy model Whisper (`whisper.load_model("tiny")`).

-----


# 🎯 Roadmap

  - [ ] Obsługa wielu języków (EN, ES, FR, DE)
  - [ ] Integracja z TikTok
  - [ ] GUI (interfejs graficzny)
  - [ ] Baza danych historii (uniknięcie duplikatów)
  - [ ] A/B testing dla tematów
  - [ ] Analytics z YouTube API
  - [ ] Zaawansowany scheduling

<!-- end list -->


```
