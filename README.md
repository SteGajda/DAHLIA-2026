# DAHLIA 2026 — Architektura Klient-Serwer

DAHLIA to interaktywne narzędzie do powtarzalnych eksperymentów "human-in-the-loop" związanych z imputacją brakujących wartości w zbiorach danych. 
Projekt przeszedł transformację z izolowanego desktopowego Proof of Concept (PoC) do pełnoprawnej architektury Klient-Serwer (Monorepo), zachowując przy tym tryb offline-first.

## Architektura (Monorepo)

Repozytorium składa się z dwóch niezależnych, odizolowanych modułów. Każdy z nich zarządza własnymi zależnościami (`pyproject.toml`):

### 1. `backend/` (Serwer REST API)
- **Technologia:** FastAPI (Python 3.12), SQLAlchemy 2.0, Pydantic, Alembic.
- **Rola:** Centralny serwer odbierający i agregujący wyniki eksperymentów od badaczy z różnych stacji roboczych.
- **Bezpieczeństwo:** Posiada zaimplementowany system kont, bezstanową autoryzację JWT (krótkotrwałe Access Tokeny oraz haszowane SHA-256 Refresh Tokeny) oraz system kontroli ról (RBAC: `USER`, `USER_PLUS`, `RESEARCHER`, `DEVELOPER`).
- **Baza danych:** Docelowo Microsoft SQL Server / Azure SQL (lokalnie wykorzystuje SQLite na potrzeby developmentu i testów).

### 2. `frontend/` (Klient Desktopowy)
- **Technologia:** NiceGUI, Plotly, Scikit-learn, HTTPX, Keyring.
- **Rola:** Aplikacja kliencka, w której badacze przeprowadzają eksperyment (wskazują poprawne pozycje na wykresach PCA/t-SNE/UMAP).
- **Offline-first:** Aplikacja pozwala na ukończenie badania bez dostępu do sieci. Wyniki zapisują się w lokalnej bazie danych SQLite (`%APPDATA%/DAHLIA/dahlia_local.db` na Windows).
- **Bezpieczeństwo Sesji:** Długoterminowy Refresh Token przechowywany jest w bezpiecznym magazynie poświadczeń systemu operacyjnego (`keyring` - Windows Credential Manager / macOS Keychain), bez zapisywania poufnych haseł w plikach konfiguracyjnych.
- **Synchronizacja i Status:** Interfejs zawiera dynamiczny wskaźnik stanu sieci (Online / Offline) odpytujący endpoint `/health`. Przy aktywnej sesji użytkownika wyniki mogą zostać przesłane do centralnej bazy backendowej.

---

## Praca z Repozytorium (Instalacja)

Zalecane jest korzystanie z jednego, wspólnego środowiska wirtualnego w korzeniu projektu, do którego doinstalowuje się zależności obu modułów w trybie edytowalnym.

**Instalacja:**
```powershell
# 1. Utworzenie i aktywacja wspólnego środowiska w katalogu głównym:
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Instalacja zależności frontendu (z folderu frontend):
cd frontend
pip install -e .[dev]
cd ..

# 3. Instalacja zależności backendu (z folderu backend):
cd backend
pip install -e .[dev]
cd ..
```

**Uruchamianie aplikacji:**
Wymaga osobnych okien terminala z aktywnym środowiskiem `.venv`:
```powershell
# Backend (API REST pod adresem http://127.0.0.1:8000, dokumentacja Swagger pod /docs):
cd backend
fastapi dev app/main.py
# lub bezpośrednio uvicorn:
# uvicorn app.main:app --reload --port 8000

# Frontend (domyślnie pełnoekranowe, natywne okno desktopowe):
python frontend/run_app.py
# Opcjonalnie w oknie zwykłej przeglądarki (port 8080):
# python frontend/run_app.py --browser
```

---

## Uruchamianie Testów (pytest)

Zarówno frontend, jak i backend posiadają kompletne zestawy testów jednostkowych:

```powershell
# Uruchomienie testów frontendu (32 testy: API client, sesja, admin panel, algorytmy):
pytest frontend/tests

# Uruchomienie testów backendu (70 testów: JWT, autentykacja, RBAC, rejestracja):
cd backend
pytest tests
cd ..
```

---

## Ekrany Aplikacji (Frontend)
Interfejs kliencki zawiera następujące widoki:
1. `Experiment Setup` - konfiguracja parametrów imputacji (seed, ułamek braków, metoda projekcji).
2. `Active Experiment` - główny widok interaktywnego wykresu i suwaków annotatora.
3. `Results Summary` - podsumowanie metryk MAE/RMSE w porównaniu z metodami bazowymi.
4. `My Results` - lokalne wyniki pobrane z bazy SQLite z możliwością eksportu do CSV.
5. `Profile` / `Login` / `Register` - logowanie badacza, rejestracja (z weryfikacją numeru indeksu PW), odświeżanie tokena i wnioskowanie o wyższą rolę.
6. `Admin Panel` - panel moderacji wniosków o podniesienie ról (`USER_PLUS`, `RESEARCHER`) oraz przełączania aktywności kont użytkowników (dostępny w menu bocznym wyłącznie dla roli `DEVELOPER`).

---

## Budowanie pliku EXE (Tylko Windows)

Aplikację desktopową można skompilować do jednego, samodzielnego pliku wykonywalnego (bez konieczności posiadania Pythona przez użytkownika końcowego). W folderze `frontend/` wykonaj:

```powershell
.\scripts\build_windows.ps1
```
Skrypt wywoła narzędzie `nicegui-pack`:
```powershell
nicegui-pack --clean --noconfirm --onefile --windowed --name "DAHLIA-1.1" --add-data "data;data" run_app.py
```
Gotowy plik `DAHLIA-1.1.exe` znajdzie się w katalogu `frontend/dist/`.

---

## Najważniejsze reguły eksperymentu (Silnik naukowy)

- **Seed**: `0–4294967295`. Gwarantuje determinizm (identyczny układ braków dla tego samego ziarna).
- Zawsze 15 ocen użytkownika per eksperyment.
- Braki powstają tylko w kolumnie `SepalLengthCm`.
- Projekcja (PCA, t-SNE, UMAP) wykorzystuje wyłącznie kolumny referencyjne: `SepalWidthCm`, `PetalLengthCm`, `PetalWidthCm`.
- Inne brakujące punkty są ukryte na wykresie; widoczny i podświetlony jest tylko aktualnie rozpatrywany punkt.
- Wartość początkowa suwaka to zawsze minimum skali.
- Suwak, pole liczbowe i kolor punktu na wykresie są reaktywne (mają jedno, zsynchronizowane źródło wartości).
- Metody bazowe (KNN, Random Forest, MICE itp.) liczą się w tle w innej usłudze, nie blokując interfejsu annotatora.
- Zakończenie badania zapisuje wynik w lokalnej bazie SQLite. Wysłanie danych do centralnej bazy wymaga zatwierdzenia.
