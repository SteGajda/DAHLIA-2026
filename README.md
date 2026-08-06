# DAHLIA 1.1 — desktop PoC

DAHLIA 1.1 jest desktopową aplikacją do eksperymentów human-in-the-loop związanych z imputacją brakujących wartości. Interfejs jest w całości po angielsku. Aplikacja działa lokalnie, nie zapisuje wyników i nie łączy się z żadną usługą sieciową.

## Zakres MVP

Aplikacja zawiera dokładnie trzy ekrany:

1. `Experiment Setup`
2. `Active Experiment`
3. `Results Summary`

W MVP dostępny jest zbiór `iris`, frakcje braków `0.1`, `0.2`, `0.3` oraz projekcje `tsne`, `pca`, `umap`.

## Struktura

```text
data/
  iris.csv                     dane wejściowe
scripts/
  run_windows.ps1              uruchomienie z kodu
  build_windows.ps1            budowa pliku EXE
src/dahlia/
  app/
    components/                wykres i współdzielone elementy UI
    screens/                   trzy ekrany MVP
    controller.py              stan i przejścia między ekranami
    main.py                    natywne okno desktopowe
    theme.py                   styl zgodny z Figmą
  datasets/                    wybór braków i 15 punktów
  imputation/                  istniejące metody imputacji
  services/
    config.py                  stałe datasetu i eksperymentu
    data.py                    wczytywanie oraz walidacja CSV
    projection.py              PCA, t-SNE i UMAP bez leaka
    experiment.py              przygotowanie, metody i metryki
tests/                         testy logiki naukowej
run_app.py                     główny plik uruchomieniowy
```

Warstwa `app` nie implementuje algorytmów naukowych. UI korzysta wyłącznie z funkcji z `services`, a istniejące klasy imputacji pozostają w `imputation`.

## Instalacja w VS Code

W terminalu PowerShell, w katalogu projektu:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Zalecany Python: **3.12**.

## Uruchomienie

```powershell
python run_app.py
```

Można też uruchomić:

```powershell
.\scripts\run_windows.ps1
```

Aplikacja otwiera się jako jasne, pełnoekranowe, niezmienialne okno desktopowe.

## Testy

```powershell
pytest
```

Testy sprawdzają między innymi:

- deterministyczny wybór braków i kolejności 15 punktów,
- brak użycia `SepalLengthCm`, `Species` i `Id` w projekcji,
- stabilność projekcji PCA dla tego samego seedu,
- zakres suwaka wyznaczany tylko z obserwowanych wartości,
- wyniki wszystkich sześciu metod,
- obliczanie MAE i RMSE na tych samych 15 punktach.

## Budowanie pliku EXE

Na Windows uruchom:

```powershell
.\scripts\build_windows.ps1
```

Skrypt instaluje zależności budowania i wykonuje:

```powershell
nicegui-pack --onefile --windowed --name "DAHLIA-1.1" --add-data "data;data" run_app.py
```

Gotowy plik powinien znaleźć się w:

```text
dist/DAHLIA-1.1.exe
```

Budowanie `.exe` należy wykonywać na Windows. Pozostałe systemy są traktowane jako przyszłe rozszerzenie.

## Najważniejsze reguły eksperymentu

- Seed: `0–4294967295`.
- Zawsze 15 ocen użytkownika.
- Braki powstają tylko w `SepalLengthCm`.
- Projekcja wykorzystuje tylko `SepalWidthCm`, `PetalLengthCm`, `PetalWidthCm`.
- Inne brakujące punkty są ukryte; widoczny jest tylko aktualny punkt.
- Po zatwierdzeniu punkt znika z wykresu.
- Wartość początkowa to minimum skali.
- Suwak, pole liczbowe i kolor punktu mają jedno wspólne źródło wartości.
- Metody działają w tle podczas anotacji.
- Błąd którejkolwiek metody przerywa eksperyment.
- Wyniki nie są zapisywane ani eksportowane.
