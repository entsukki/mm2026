#!/usr/bin/env python3
"""Hakee jalkapallon MM 2026 -otteluiden tulokset ja tallentaa ne tulokset.json-tiedostoon.

Lähteet:
  1. FIFA:n julkinen API (ensisijainen) - koko turnauksen kalenteri tuloksineen
  2. TheSportsDB (ristiintarkistus) - ilmainen julkinen testiavain

Tulos merkitään vahvistetuksi vain, jos molemmat lähteet ovat samaa mieltä.
Ei riippuvuuksia: pelkkä Pythonin standardikirjasto (vaatii Python 3.9+).

Käyttö: python3 hae_tulokset.py
"""
import json
import os
import ssl
import sys
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

FIFA_URL = ("https://api.fifa.com/api/v3/calendar/matches"
            "?idCompetition=17&idSeason=285023&language=en&count=200")
TSDB_SEASON_URL = "https://www.thesportsdb.com/api/v1/json/3/eventsseason.php?id=4429&s=2026"
TSDB_PAST_URL = "https://www.thesportsdb.com/api/v1/json/3/eventspastleague.php?id=4429"
TULOSTIEDOSTO = "tulokset.json"
AIKAVYOHYKE = ZoneInfo("Europe/Helsinki")

# Englanninkieliset joukkuenimet (FIFA + TheSportsDB -variantit) -> sivuston suomenkieliset nimet
FI_NIMET = {
    "Mexico": "Meksiko", "South Africa": "Etelä-Afrikka",
    "Korea Republic": "Etelä-Korea", "South Korea": "Etelä-Korea",
    "Czechia": "Tshekki", "Czech Republic": "Tshekki",
    "Canada": "Kanada",
    "Bosnia and Herzegovina": "Bosnia ja Hertsegovina", "Bosnia-Herzegovina": "Bosnia ja Hertsegovina",
    "USA": "USA", "United States": "USA",
    "Paraguay": "Paraguay", "Qatar": "Qatar",
    "Switzerland": "Sveitsi", "Brazil": "Brasilia", "Morocco": "Marokko",
    "Haiti": "Haiti", "Scotland": "Skotlanti", "Australia": "Australia",
    "Türkiye": "Turkki", "Turkey": "Turkki",
    "Germany": "Saksa", "Curaçao": "Curaçao", "Curacao": "Curaçao",
    "Netherlands": "Hollanti", "Japan": "Japani",
    "Côte d'Ivoire": "Norsunluurannikko", "Ivory Coast": "Norsunluurannikko",
    "Ecuador": "Ecuador", "Sweden": "Ruotsi", "Tunisia": "Tunisia",
    "Spain": "Espanja",
    "Cabo Verde": "Kap Verde", "Cape Verde": "Kap Verde", "Cape Verde Islands": "Kap Verde",
    "Belgium": "Belgia", "Egypt": "Egypti",
    "Saudi Arabia": "Saudi-Arabia",
    "Uruguay": "Uruguay",
    "IR Iran": "Iran", "Iran": "Iran",
    "New Zealand": "Uusi-Seelanti", "France": "Ranska", "Senegal": "Senegal",
    "Iraq": "Irak", "Norway": "Norja", "Argentina": "Argentiina",
    "Algeria": "Algeria", "Austria": "Itävalta", "Jordan": "Jordania",
    "Portugal": "Portugali",
    "Congo DR": "Kongon dem. tasavalta", "DR Congo": "Kongon dem. tasavalta",
    "England": "Englanti", "Croatia": "Kroatia", "Ghana": "Ghana",
    "Panama": "Panama", "Uzbekistan": "Uzbekistan", "Colombia": "Kolumbia",
}


def suomeksi(nimi):
    """Palauttaa joukkueen suomenkielisen nimen tai alkuperäisen, jos mäppäys puuttuu."""
    return FI_NIMET.get(nimi, nimi)


def ssl_konteksti():
    """python.org-asennuksilta puuttuu usein juurivarmenteet; käytetään
    certifi-pakettia jos asennettu, muuten macOS:n järjestelmänippua."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    if os.path.exists("/etc/ssl/cert.pem"):
        return ssl.create_default_context(cafile="/etc/ssl/cert.pem")
    return ssl.create_default_context()


SSL_CTX = ssl_konteksti()


def hae_json(url):
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "mm2026-tuloshaku/1.0 (github.com/entsukki/mm2026)",
    })
    with urllib.request.urlopen(req, timeout=20, context=SSL_CTX) as vastaus:
        return json.load(vastaus)


def avain(pvm_fi, koti, vieras):
    """Yksilöivä avain ottelulle ristiintarkistusta varten."""
    return f"{pvm_fi}|{koti}|{vieras}"


def fifa_tulokset():
    """Päättyneet ottelut FIFA:n APIsta. MatchStatus: 0=päättynyt, 3=käynnissä, 1=ei alkanut."""
    data = hae_json(FIFA_URL)
    tulokset = {}
    for m in data.get("Results", []):
        if m.get("MatchStatus") != 0:
            continue
        koti = suomeksi((m.get("Home") or {}).get("TeamName", [{}])[0].get("Description", "?"))
        vieras = suomeksi((m.get("Away") or {}).get("TeamName", [{}])[0].get("Description", "?"))
        alku_utc = datetime.fromisoformat(m["Date"].replace("Z", "+00:00"))
        alku_fi = alku_utc.astimezone(AIKAVYOHYKE)
        tulokset[avain(alku_fi.date().isoformat(), koti, vieras)] = {
            "pvm": alku_fi.date().isoformat(),
            "aika_fi": alku_fi.strftime("%H:%M"),
            "koti": koti,
            "vieras": vieras,
            "koti_maalit": int(m["Home"]["Score"]),
            "vieras_maalit": int(m["Away"]["Score"]),
        }
    return tulokset


def tsdb_tulokset():
    """Päättyneet ottelut TheSportsDB:stä (kausi + viimeksi pelatut yhdistettynä)."""
    tapahtumat = []
    for url in (TSDB_SEASON_URL, TSDB_PAST_URL):
        try:
            tapahtumat += hae_json(url).get("events") or []
        except Exception as virhe:  # toissijainen lähde saa epäonnistua
            print(f"  varoitus: TheSportsDB-haku epäonnistui ({virhe})", file=sys.stderr)
    tulokset = {}
    for e in tapahtumat:
        if e.get("strStatus") not in ("FT", "AET", "PEN", "Match Finished"):
            continue
        koti = suomeksi(e["strHomeTeam"])
        vieras = suomeksi(e["strAwayTeam"])
        alku_utc = datetime.fromisoformat(e["strTimestamp"]).replace(tzinfo=timezone.utc)
        alku_fi = alku_utc.astimezone(AIKAVYOHYKE)
        tulokset[avain(alku_fi.date().isoformat(), koti, vieras)] = {
            "koti_maalit": int(e["intHomeScore"]),
            "vieras_maalit": int(e["intAwayScore"]),
        }
    return tulokset


def main():
    print("Haetaan FIFA:n APIsta...")
    fifa = fifa_tulokset()
    print(f"  {len(fifa)} päättynyttä ottelua")

    print("Haetaan TheSportsDB:stä (ristiintarkistus)...")
    tsdb = tsdb_tulokset()
    print(f"  {len(tsdb)} päättynyttä ottelua")

    tulokset = []
    for k, f in sorted(fifa.items(), key=lambda x: (x[1]["pvm"], x[1]["aika_fi"])):
        rivi = dict(f)
        rivi["tulos"] = f"{f['koti_maalit']}–{f['vieras_maalit']}"
        rivi["ottelu"] = f"{f['koti']} – {f['vieras']}"
        t = tsdb.get(k)
        if t is None:
            rivi["vahvistus"] = "vain FIFA"
        elif (t["koti_maalit"], t["vieras_maalit"]) == (f["koti_maalit"], f["vieras_maalit"]):
            rivi["vahvistus"] = "FIFA + TheSportsDB"
        else:
            rivi["vahvistus"] = "RISTIRIITA"
            rivi["tsdb_tulos"] = f"{t['koti_maalit']}–{t['vieras_maalit']}"
        tulokset.append(rivi)

    # Kirjoitetaan vain jos tulokset muuttuivat - muuten haettu-aikaleima
    # aiheuttaisi turhan commitin jokaisella ajolla (GitHub Actions)
    try:
        with open(TULOSTIEDOSTO, encoding="utf-8") as f:
            vanhat = json.load(f).get("tulokset")
    except (FileNotFoundError, json.JSONDecodeError):
        vanhat = None
    if vanhat == tulokset:
        print(f"\nEi uusia tuloksia - {TULOSTIEDOSTO} ennallaan ({len(tulokset)} tulosta).")
        return 0

    data = {
        "haettu": datetime.now(AIKAVYOHYKE).isoformat(timespec="seconds"),
        "lahteet": {"ensisijainen": "FIFA API", "ristiintarkistus": "TheSportsDB"},
        "tuloksia": len(tulokset),
        "tulokset": tulokset,
    }
    with open(TULOSTIEDOSTO, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\nTallennettu {len(tulokset)} tulosta tiedostoon {TULOSTIEDOSTO}:")
    for r in tulokset:
        merkki = "✓" if r["vahvistus"] == "FIFA + TheSportsDB" else "!"
        print(f"  {merkki} {r['pvm']} {r['aika_fi']} {r['ottelu']} {r['tulos']} ({r['vahvistus']})")
    ristiriidat = [r for r in tulokset if r["vahvistus"] == "RISTIRIITA"]
    if ristiriidat:
        print(f"\nHUOM: {len(ristiriidat)} ristiriitaista tulosta - tarkista käsin ennen käyttöä!")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
