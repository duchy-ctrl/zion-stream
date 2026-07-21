# 🎵 Zion Stream

**YouTube → boxe, fără telefon, fără abonamente.**

Aplicație self-hosted pentru restaurante și terase: cauți o piesă sau un playlist de pe YouTube și sunetul pornește direct pe sistemul audio (streamere Arylic / Linkplay / 4Stream), controlat de pe PC sau telefon, din browser.

Construită pentru [Zion Gardens – The View](https://zion-gardens.ro), dar merge oriunde există un streamer Linkplay și un PC cu Windows pe aceeași rețea.

---

## Cum funcționează

```
┌──────────┐  caută/redă   ┌─────────────────┐  audio HTTP   ┌────────────┐
│ Browser  │ ────────────► │  zion-server.py │ ────────────► │  Streamer  │
│ (PC/tel) │               │  (PC, Flask +   │               │  Arylic /  │
└──────────┘               │   yt-dlp)       │  comenzi API  │  Linkplay  │
                           └─────────────────┘ ────────────► └─────┬──────┘
                                    ▲                              │
                                    │ extrage audio                ▼
                              ┌───────────┐                 🔊 Boxe (Bose)
                              │  YouTube  │
                              └───────────┘
```

Serverul de pe PC face trei lucruri:

1. **Extrage audio** de la YouTube cu `yt-dlp` (căutare, piese, playlisturi întregi)
2. **Releu audio HTTP** — streamerele Linkplay mai vechi nu redau HTTPS, așa că serverul le servește sunetul ca HTTP simplu din rețeaua locală
3. **Proxy de comenzi** către API-ul Linkplay al streamerului (play, pauză, volum, status) — cu răspunsuri citibile, deci aplicația confirmă că streamerul chiar redă

Interfața web (un singur fișier HTML, fără framework-uri) e servită chiar de server la `http://IP-PC:8321` — se deschide de pe orice dispozitiv din rețea.

## Funcții

- 🔍 Căutare YouTube + import de playlisturi întregi după link
- 📃 Playlisturi proprii: creare, editare, reordonare, salvare din coadă
- ▶️ Coadă de redare cu auto-next, shuffle real (fără repetări) și repeat
- 🔊 Control volum, pauză, next/prev de la distanță
- 🔍 Descoperire automată a streamerului în rețea (scanare LAN)
- ✅ Confirmare de redare — aplicația verifică starea reală a streamerului
- 🔄 yt-dlp se auto-actualizează la fiecare pornire a serverului
- 🛟 Fallback pe instanțe publice Piped/Invidious dacă serverul local e oprit
- 💾 Totul persistă în browser (playlisturi, coadă, setări)

## Instalare (Windows) — 2 pași

1. Descarcă [`instaleaza.bat`](https://raw.githubusercontent.com/duchy-ctrl/zion-stream/main/instaleaza.bat) (click dreapta → Save as)
2. Click dreapta pe el → **Run as administrator**

Atât. Instalatorul descarcă `ZionStream.exe` (ultima versiune, fără Python, fără dependențe), îl pune să pornească singur cu Windows-ul, deschide firewall-ul și îți lasă scurtătura **Zion Stream** pe Desktop.

Prima folosire: deschizi aplicația → **🔍 Găsește streamerul** → alegi dispozitivul → cauți o piesă → ▶. De pe telefon: `http://IP-PC:8321` (același WiFi).

## Structura

| Fișier | Rol |
|---|---|
| `instaleaza.bat` | Instalatorul — singurul fișier de care are nevoie utilizatorul |
| `zion-stream.html` | Interfața web (vanilla JS, un singur fișier) |
| `zion-server.py` | Serverul: căutare, extracție, releu audio, comenzi streamer |
| `porneste-server.bat` | Pentru dezvoltare: rulează serverul din sursă, cu consolă |
| `tests/test-harness.js` | Teste funcționale pentru logica UI (node) |
| `version.txt` | Versiunea curentă (folosită de auto-update) |
| `.github/workflows/build.yml` | Build automat de `ZionStream.exe` la fiecare tag `v*` |

## Auto-DJ (cântă și comută singur)

Serverul poate ține muzica pornită toată ziua fără să atingă nimeni nimic, cu comutare programată:

- **09:00 → 🏊 Deep House Piscină**
- **19:30 → 🌅 Dolce Far Niente** (peste noapte)

Muzica curge **neîntrerupt, ca un radio**: serverul emite un singur flux MP3 continuu (`/api/stream/live.mp3`) pe care streamerul îl deschide o singură dată și cântă la infinit — fără pauze între piese. Comutarea programată (ex. 19:30) se face în interiorul aceluiași flux, tot fără întrerupere.

Playlisturile predefinite sunt **căutări**, nu linkuri fixe — serverul ia mereu mixurile actuale de pe YouTube, deci nu „mor" niciodată. Totul se face pe server, deci merge chiar dacă nicio filă de browser nu e deschisă.

În interfață: cardul **🎛️ Auto-DJ** → „Pornește". Cele două playlisturi apar și ca butoane, să le pornești manual oricând. Dacă redai ceva manual, Auto-DJ se pune pe pauză 2 ore, apoi reia programul.

Programul și playlisturile se pot schimba din `zion-config.json` (`schedule` și `presets`). Ex.:

```json
{
  "schedule": [{"from": "09:00", "preset": "pool"}, {"from": "19:30", "preset": "chill"}],
  "presets": {
    "pool":  {"name": "🏊 Deep House Piscină", "query": "deep house sunset pool mix 2025"},
    "chill": {"name": "🌅 Dolce Far Niente", "query": "bossa nova jazz lounge mix"}
  }
}
```

## Auto-update și loguri

Aplicația se actualizează singură: verifică GitHub la pornire și la fiecare 6 ore, iar dacă există versiune nouă se descarcă și repornește singură. Pentru dezvoltator, publicarea unei versiuni = commit + push + tag nou `v*` (build-ul și release-ul se fac automat).

Un **paznic** (`zion-watchdog.bat`, pornit automat cu Windows) ține aplicația mereu în funcțiune: dacă se închide — din update sau dintr-o eroare — o repornește în ~4 secunde, iar muzica revine automat (Auto-DJ e salvat). Deci un update = o pauză de câteva secunde, nu o oprire până la restart manual.

Logurile sunt în `zion-log.txt` lângă aplicație și în browser la `http://IP-PC:8321/api/logs` — dacă ceva nu merge, deschizi adresa aia și trimiți ce scrie. (Opțional, pentru depanare de la distanță, logurile pot urca automat în repo — vezi `zion-config.exemplu.json`.)

## Teste

```bash
cd tests && node test-harness.js ../zion-stream.html
```

13 teste acoperă: fluxul de căutare/redare, coada, shuffle/repeat, race conditions la schimbarea pieselor, protecție XSS pe datele venite din API-uri externe, comportamentul la ștergere/golire.

## Depanare

| Simptom | Cauză probabilă |
|---|---|
| Nu se aude nimic, dar aplicația zice „streamerul redă" | Volumul streamerului la 0 sau intrarea greșită pe amplificator |
| „Nu pot ajunge la IP..." | IP greșit — folosește 🔍 Găsește streamerul |
| Căutarea nu întoarce nimic | Serverul oprit? Verifică cu „Testează serverul"; yt-dlp se repară singur la repornirea serverului |
| Telefonul nu se conectează | PC și telefon în rețele diferite, sau firewall — rulează instalatorul ca Administrator |

## Note

- ⚖️ Extracția audio de pe YouTube contravine termenilor YouTube; proiectul e gândit pentru **uz propriu**, nu ca serviciu public.
- 🔒 Serverul nu are autentificare și e accesibil oricui din LAN — nu-l expune spre internet.
- Testat cu streamere Arylic (app 4Stream) pe amplificatoare cu boxe Bose de exterior.

## Licență

[MIT](LICENSE)
