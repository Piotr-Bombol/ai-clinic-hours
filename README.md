# AI Clinic Hours: strona

Strona jest generowana z danych. Nie edytuj plików w `docs/` ręcznie: każda zmiana idzie przez `dane/` albo `zasoby/`, a potem przez build.

- Na żywo: https://piotr-bombol.github.io/ai-clinic-hours/ (GitHub Pages, gałąź `main`, folder `docs/`)
- Zamknięta beta: strona ma `noindex` i `robots.txt` z `Disallow`. Przełącznik: `konfig.indeksowanie` w `dane/strona.toml`.

## Co gdzie jest

| Ścieżka | Co zawiera |
|---|---|
| `dane/strona.toml` | Wszystkie teksty strony, cena, ustawienia, opisy dla Google |
| `dane/sytuacje.toml` | Sytuacje, z którymi przychodzą liderzy, i to, z czym wychodzą; kto je prowadzi |
| `dane/eksperci/*.toml` | Jeden plik na osobę. Wzór: `dane/eksperci/_wzor.toml` |
| `dane/strony/*.html` | Treść stron Dla ekspertów, Regulamin, Polityka prywatności |
| `zasoby/` | Style, skrypty, fonty, zdjęcia (oryginały), szablon karty do udostępniania |
| `build.py` | Generator. Sprawdza dane i buduje `docs/` |
| `docs/` | Gotowa strona (wynik buildu, publikowana przez GitHub Pages) |

## Zbudować i opublikować

```
python3 build.py --og      # --og odświeża karty do udostępniania i ikony (wymaga Chrome)
git add -A && git commit -m "Opis zmiany" && git push
```

Strona odświeża się po około minucie. Generator zatrzyma się z listą błędów, jeśli sytuacja wskazuje nieistniejącą osobę albo brakuje zdjęcia.

## Dodać eksperta

1. Skopiuj `dane/eksperci/_wzor.toml` jako `dane/eksperci/<imie-nazwisko>.toml` i wypełnij. Każdy fakt ma źródło i akceptację tej osoby.
2. Portret (pionowy, min. 570 px szerokości) wrzuć do `zasoby/img/`.
3. W `dane/sytuacje.toml` dopisz osobę do spraw, które prowadzi (`[[sytuacja.kto]]`), albo dodaj nową sytuację.
4. Link z Zencal wpisz w `[rezerwacja]`. Bez linku przycisk otwiera mail z rezerwacją.
5. `python3 build.py --og`, sprawdź stronę lokalnie (`docs/index.html`), wypchnij.

Od 6 osób na stronie głównej pojawiają się filtry po obszarze (`konfig.filtry_od`). Przy jednej sprawie może być kilka osób: kolejne `[[sytuacja.kto]]` z polem `kiedy` pokazują się pod pierwszą osobą jako „Druga osoba”, „Kolejna osoba”.

## Wyjście z bety

W `dane/strona.toml`: wpisać `domena` i nowe `base_url`, ustawić `indeksowanie = true`, zbudować i wypchnąć. Wcześniej: regulamin i polityka po prawniku, profile zaakceptowane przez ekspertów.
