import os
import shutil
import datetime
import sys
import time
from datetime import timedelta, timezone
from zoneinfo import ZoneInfo

# Sprawdzenie czy biblioteki są zainstalowane
try:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
except ImportError:
    print("Brakuje bibliotek! Instaluję je dla Ciebie...")
    os.system(f"{sys.executable} -m pip install google-api-python-client google-auth-oauthlib google-auth-httplib2")
    print("\nBiblioteki zainstalowane. Uruchom skrypt ponownie.")
    sys.exit()

# --- KONFIGURACJA ---
FOLDER_ZRODLOWY = "do_publikacji"
FOLDER_ZAKONCZONY = "opublikowane"
PLIK_KLUCZA = "client_secret.json"
STREFA_PL = ZoneInfo("Europe/Warsaw")
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']


def przygotuj_srodowisko():
    sciezka_skryptu = os.path.dirname(os.path.realpath(__file__))
    os.chdir(sciezka_skryptu)

    os.makedirs(FOLDER_ZRODLOWY, exist_ok=True)
    os.makedirs(FOLDER_ZAKONCZONY, exist_ok=True)

    if not os.path.exists(PLIK_KLUCZA):
        print("\n" + "!" * 50)
        print(f"BŁĄD: Brak pliku '{PLIK_KLUCZA}'!")
        print("1. Wejdź na https://console.cloud.google.com/")
        print("2. Utwórz projekt → API i usługi → Dane uwierzytelniające")
        print("3. Utwórz 'Identyfikator klienta OAuth 2.0' (Aplikacja na komputer)")
        print("4. Pobierz plik JSON i umieść go tutaj jako 'client_secret.json'")
        print("!" * 50)
        sys.exit()


def authenticate_youtube():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"⚠️ Nie udało się odświeżyć tokenu ({e}). Loguję ponownie...")
                creds = None

        if not creds:
            flow = InstalledAppFlow.from_client_secrets_file(PLIK_KLUCZA, SCOPES)
            creds = flow.run_local_server(port=0)

        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return build('youtube', 'v3', credentials=creds)


def generuj_harmonogram(liczba_filmow):
    daty = []
    teraz = datetime.datetime.now(STREFA_PL)
    czas_startowy = teraz + timedelta(hours=2)
    dzien_sprawdzany = teraz.date()

    while len(daty) < liczba_filmow:
        dzien_tygodnia = dzien_sprawdzany.weekday()
        if dzien_tygodnia < 5:
            godziny = [datetime.time(15, 0), datetime.time(19, 30)]
        else:
            godziny = [datetime.time(11, 0), datetime.time(18, 0)]

        for g in godziny:
            kandydat = datetime.datetime.combine(dzien_sprawdzany, g).replace(tzinfo=STREFA_PL)
            if kandydat > czas_startowy:
                data_utc_str = kandydat.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
                daty.append((data_utc_str, kandydat.strftime('%Y-%m-%d %H:%M')))
                if len(daty) == liczba_filmow:
                    return daty

        dzien_sprawdzany += timedelta(days=1)
    return daty


def upload_film(youtube, sciezka_pliku, tytul, data_utc):
    body = {
        'snippet': {
            'title': tytul,
            'description': '🔴 Zostaw komentarz co sądzisz!\n\n#shorts #horror #creepypasta',
            'categoryId': '22',
            'tags': ['shorts', 'horror', 'creepypasta', 'polska'],
        },
        'status': {
            'privacyStatus': 'private',
            'publishAt': data_utc,
            'selfDeclaredMadeForKids': False
        }
    }

    insert_request = youtube.videos().insert(
        part=','.join(body.keys()),
        body=body,
        media_body=MediaFileUpload(sciezka_pliku, chunksize=1024 * 1024, resumable=True)
    )

    response = None
    ostatni_procent = -1

    while response is None:
        try:
            status, response = insert_request.next_chunk()
            if status:
                procent = int(status.progress() * 100)
                if procent != ostatni_procent:
                    print(f"  📤 Przesyłanie: {procent}%", end='\r')
                    ostatni_procent = procent
        except HttpError as e:
            if e.resp.status in [500, 502, 503, 504]:
                print(f"\n  ⚠️ Błąd serwera {e.resp.status}, ponawiam za 5 sekund...")
                time.sleep(5)
            else:
                raise

    print(f"\n  ✅ Upload zakończony! Video ID: {response.get('id', 'nieznany')}")
    return response


def bezpieczne_przeniesienie(src, dst, max_prob=3):
    """Przenosi plik próbując kilkukrotnie, jeśli jest zablokowany przez system."""
    for proba in range(max_prob):
        try:
            shutil.move(src, dst)
            return True
        except PermissionError:
            print(f"  ⚠️ Plik zajęty przez system. Próba {proba + 1}/{max_prob} za 2 sekundy...")
            time.sleep(2)
        except Exception as e:
            print(f"  ❌ Nie udało się przenieść pliku: {e}")
            break
    return False


def main():
    przygotuj_srodowisko()

    pliki = sorted([f for f in os.listdir(FOLDER_ZRODLOWY) if f.lower().endswith(('.mp4', '.mov', '.avi'))])

    if not pliki:
        print(f"\n📂 Folder '{FOLDER_ZRODLOWY}' jest pusty.")
        print("Wrzuć tam filmy i uruchom skrypt ponownie.")
        return

    print(f"✅ Znaleziono {len(pliki)} filmów.")
    print("🔑 Łączę z YouTube...")

    youtube = authenticate_youtube()
    harmonogram = generuj_harmonogram(len(pliki))

    sukces = 0
    blad = 0

    for i, nazwa_pliku in enumerate(pliki):
        sciezka_pliku = os.path.join(FOLDER_ZRODLOWY, nazwa_pliku)
        tytul = os.path.splitext(nazwa_pliku)[0]
        data_utc, data_lokalna = harmonogram[i]

        print(f"\n[{i + 1}/{len(pliki)}] 📹 {tytul}")
        print(f"  🕐 Zaplanowane na: {data_lokalna}")

        try:
            upload_film(youtube, sciezka_pliku, tytul, data_utc)

            # Bezpieczne przenoszenie pliku
            docelowa_sciezka = os.path.join(FOLDER_ZAKONCZONY, nazwa_pliku)
            if bezpieczne_przeniesienie(sciezka_pliku, docelowa_sciezka):
                sukces += 1
            else:
                blad += 1

        except HttpError as e:
            print(f"\n  ❌ Błąd HTTP {e.resp.status}: {e.content}")
            blad += 1
        except Exception as e:
            print(f"\n  ❌ Nieoczekiwany błąd: {e}")
            blad += 1

    print(f"\n{'=' * 40}")
    print(f"🏁 Zakończono! ✅ Sukces: {sukces} | ❌ Błędy: {blad}")
    print(f"{'=' * 40}")


if __name__ == "__main__":
    main()