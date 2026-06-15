#!/usr/bin/env python3
"""Hakee jalkapallon MM 2026 -otteluiden tulokset ja tallentaa ne tulokset.json-tiedostoon.

Lähde: FIFA:n julkinen API (koko turnauksen kalenteri tuloksineen).
Ei riippuvuuksia: pelkkä Pythonin standardikirjasto (vaatii Python 3.9+).

Käyttö: python3 hae_tulokset.py
"""
import json
import os
import ssl
import sys
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

FIFA_URL = ("https://api.fifa.com/api/v3/calendar/matches"
            "?idCompetition=17&idSeason=285023&language=en&count=200")
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
    """Yksilöivä avain ottelulle (dedup)."""
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


def main():
    print("Haetaan FIFA:n APIsta...")
    fifa = fifa_tulokset()
    print(f"  {len(fifa)} päättynyttä ottelua")

    tulokset = []
    for f in sorted(fifa.values(), key=lambda x: (x["pvm"], x["aika_fi"])):
        rivi = dict(f)
        rivi["tulos"] = f"{f['koti_maalit']}–{f['vieras_maalit']}"
        rivi["ottelu"] = f"{f['koti']} – {f['vieras']}"
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
        "lahde": "FIFA API",
        "tuloksia": len(tulokset),
        "tulokset": tulokset,
    }
    with open(TULOSTIEDOSTO, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\nTallennettu {len(tulokset)} tulosta tiedostoon {TULOSTIEDOSTO}:")
    for r in tulokset:
        print(f"  {r['pvm']} {r['aika_fi']} {r['ottelu']} {r['tulos']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
