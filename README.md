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

## Instalare (Windows)

1. Descarcă acest repo (Code → Download ZIP) și dezarhivează-l, de ex. în `C:\ZionStream`
2. Click dreapta pe **`instaleaza-autostart.bat`** → *Run as administrator*

Instalatorul face totul singur: instalează Python dacă lipsește, pune dependențele, configurează pornirea automată cu Windows (pe fundal, fără ferestre), deschide portul 8321 în firewall (doar rețele private) și creează scurtătura **Zion Stream** pe Desktop.

3. Deschide aplicația (scurtătura de pe Desktop sau `http://IP-PC:8321` de pe telefon)
4. Apasă **🔍 Găsește streamerul** → alege dispozitivul → **Testează conexiunea**
5. Caută o piesă → ▶

Pentru depanare, rulează `porneste-server.bat` — pornește serverul cu mesajele vizibile într-o fereastră.

## Structura

| Fișier | Rol |
|---|---|
| `zion-stream.html` | Interfața web (vanilla JS, un singur fișier) |
| `zion-server.py` | Server Flask: căutare, extracție, releu audio, proxy comenzi, descoperire LAN |
| `instaleaza-autostart.bat` | Instalator complet (o singură rulare, ca Administrator) |
| `porneste-server.bat` | Pornire manuală, cu consolă vizibilă (depanare) |
| `tests/test-harness.js` | Teste funcționale pentru logica UI (node) |

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
