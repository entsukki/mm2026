#!/usr/bin/env python3
"""Hakee jalkapallon MM 2026 -otteluiden tulokset ja tallentaa ne tulokset.json-tiedostoon.

Lähde: FIFA:n julkinen API (koko turnauksen kalenteri tuloksineen).
Ei riippuvuuksia: pelkkä Pythonin standardikirjasto (vaatii Python 3.9+).

Käyttö: python3 hae_tulokset.py
"""
import json
import os
import re
import ssl
import sys
import time
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

FIFA_URL = ("https://api.fifa.com/api/v3/calendar/matches"
            "?idCompetition=17&idSeason=285023&language=en&count=200")
# Ottelun tapahtuma-aikajana (maalit minuutteineen) — tarvitaan varsinaisen
# peliajan tuloksen erotteluun jatkoajasta/rangaistuspotkuista.
TIMELINE_URL = ("https://api.fifa.com/api/v3/timelines/"
                "{comp}/{season}/{stage}/{mid}?language=en")
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


def hae_json(url, yrityksia=3, odotus=3):
    """Hae JSON. Ohimenevä verkkovirhe (timeout ym.) uudelleenyritetään muutaman
    kerran, jottei yksittäinen hidas vastaus kaada koko ajoa — seuraava yritys
    onnistuu yleensä. Viimeisen yrityksen virhe nostetaan kutsujalle."""
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "mm2026-tuloshaku/1.0 (github.com/entsukki/mm2026)",
    })
    for yritys in range(1, yrityksia + 1):
        try:
            with urllib.request.urlopen(req, timeout=20, context=SSL_CTX) as vastaus:
                return json.load(vastaus)
        except Exception as e:
            if yritys == yrityksia:
                raise
            print(f"  VAROITUS: haku epäonnistui (yritys {yritys}/{yrityksia}): {e} — "
                  f"uudelleenyritys {odotus} s kuluttua", file=sys.stderr)
            time.sleep(odotus)


def avain(pvm_fi, koti, vieras):
    """Yksilöivä avain ottelulle (dedup)."""
    return f"{pvm_fi}|{koti}|{vieras}"


def base_minuutti(match_minute):
    """'45'+6'' -> 45, '104'' -> 104, None -> None. Perusminuutti ennen lisäaikaa."""
    m = re.match(r"(\d+)", str(match_minute or ""))
    return int(m.group(1)) if m else None


# FIFA timeline "Period": pariton = pelijakso. 3 = 1. puoliaika, 5 = 2. puoliaika
# (molemmat sis. tuomarin lisäajan, esim. maali minuutilla "90'+3'" on jaksossa 5),
# 7 ja 9 = jatkoajan puoliajat, 11 = rangaistuspotkukilpailu. Varsinainen peliaika =
# jaksot ENNEN jatkoaikaa. Jakso on luotettavampi kuin minuutti: 2. puoliajan lisäajan
# maali kuuluu jaksoon 5 riippumatta siitä näytetäänkö se muodossa "90'+3'" vai "93'".
JATKOAJAN_JAKSO = 7


def on_varsinaista_peliaikaa(e):
    """True jos tapahtuma on varsinaista peliaikaa (1.–2. puoliaika lisäaikoineen).
    Ensisijaisesti jakson (Period) mukaan; jos jaksoa ei ole, perusminuutti <= 90."""
    p = e.get("Period")
    if p is not None:
        return p < JATKOAJAN_JAKSO
    b = base_minuutti(e.get("MatchMinute"))
    return b is not None and b <= 90


def varsinaisen_peliajan_tulos(m):
    """Ottelun tulos VARSINAISEN peliajan lopussa (2. puoliaika lisäaikoineen).
    Jatkoajalla ja rangaistuspotkukilpailussa tehdyt maalit jätetään pois — kisan
    pisteet lasketaan vain varsinaisesta peliajasta (ks. pisteytys.json huomiot).
    Timeline-tapahtumissa on juokseva HomeGoals/AwayGoals (rankkarikisan maalit
    ovat erikseen HomePenaltyGoals/AwayPenaltyGoals, eivät mukana). Palauttaa
    (koti, vieras) tai None jos aikajanaa ei saatu."""
    url = TIMELINE_URL.format(comp=m["IdCompetition"], season=m["IdSeason"],
                              stage=m["IdStage"], mid=m["IdMatch"])
    try:
        tl = hae_json(url)
    except Exception as e:  # verkko/HTTP-virhe: palataan lopputulokseen (itsekorjautuu seuraavalla ajolla)
        print(f"  VAROITUS: timeline-haku epäonnistui (IdMatch {m.get('IdMatch')}): {e}", file=sys.stderr)
        return None
    koti = vieras = 0
    loytyi = False
    for e in tl.get("Event", []):
        if not on_varsinaista_peliaikaa(e):
            continue  # jatkoaika (jakso 7/9) ja rankkarit (11) pois
        if e.get("HomeGoals") is not None:
            koti = max(koti, int(e["HomeGoals"])); loytyi = True
        if e.get("AwayGoals") is not None:
            vieras = max(vieras, int(e["AwayGoals"])); loytyi = True
    return (koti, vieras) if loytyi else None


def fifa_tulokset():
    """Päättyneet JA käynnissä olevat ottelut FIFA:n APIsta.
    MatchStatus: 0=päättynyt, 3=käynnissä, 1=ei alkanut.
    Käynnissä olevat merkitään lipulla kesken=True (juokseva tulos näkyy sivulla, mutta
    selain ei laske niistä pisteitä ennen ottelun päättymistä). Peliminuuttia ei tallenneta,
    jotta tiedosto ei muuttuisi joka haulla (minuutti tikittäisi) ja aiheuttaisi turhia committeja."""
    data = hae_json(FIFA_URL)
    tulokset = {}
    for m in data.get("Results", []):
        status = m.get("MatchStatus")
        if status not in (0, 3):  # 0=päättynyt, 3=käynnissä; muut (ei alkanut yms.) ohi
            continue
        koti = suomeksi((m.get("Home") or {}).get("TeamName", [{}])[0].get("Description", "?"))
        vieras = suomeksi((m.get("Away") or {}).get("TeamName", [{}])[0].get("Description", "?"))
        alku_utc = datetime.fromisoformat(m["Date"].replace("Z", "+00:00"))
        alku_fi = alku_utc.astimezone(AIKAVYOHYKE)
        koti_maalit = int((m.get("Home") or {}).get("Score") or 0)
        vieras_maalit = int((m.get("Away") or {}).get("Score") or 0)
        # Pudotuspelissä lopputulos (Score) sisältää jatkoajan maalit. Kisan pisteet
        # lasketaan vain varsinaisesta peliajasta, joten päättyneille otteluille jotka
        # menivät jatkoajalle/rankkareihin (ResultType != 1 tai rankkarikisa) haetaan
        # 90 min tulos aikajanalta. Normaalit ottelut (ResultType 1) eivät hae timelinea.
        if status == 0 and (m.get("ResultType") != 1 or m.get("HomeTeamPenaltyScore") is not None):
            reg = varsinaisen_peliajan_tulos(m)
            if reg is not None:
                koti_maalit, vieras_maalit = reg
        rivi = {
            "pvm": alku_fi.date().isoformat(),
            "aika_fi": alku_fi.strftime("%H:%M"),
            "koti": koti,
            "vieras": vieras,
            "koti_maalit": koti_maalit,
            "vieras_maalit": vieras_maalit,
        }
        if status == 3:
            rivi["kesken"] = True
        tulokset[avain(alku_fi.date().isoformat(), koti, vieras)] = rivi
    return tulokset


def main():
    print("Haetaan FIFA:n APIsta...")
    fifa = fifa_tulokset()
    kesken = sum(1 for f in fifa.values() if f.get("kesken"))
    print(f"  {len(fifa)} ottelua ({len(fifa) - kesken} päättynyttä, {kesken} käynnissä)")

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
        merkki = " (käynnissä)" if r.get("kesken") else ""
        print(f"  {r['pvm']} {r['aika_fi']} {r['ottelu']} {r['tulos']}{merkki}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
