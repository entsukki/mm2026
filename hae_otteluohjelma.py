#!/usr/bin/env python3
"""Hakee jalkapallon MM 2026 -pudotusvaiheen (jatkopelit) otteluohjelman ja
tallentaa sen otteluohjelma.json-tiedostoon.

Lohkovaihe (First Stage) jätetään pois — se on jo tiedossa ja pelattu, ja sen
tulokset hoitaa hae_tulokset.py. Tämä skripti tuo pudotuskaavion ottelut (R32,
R16, neljännesvälierät, välierät, pronssi, finaali) oikeilla joukkuenimillä heti
kun edellinen kierros / lohko ratkeaa. index.html yhdistää nämä kovakoodattuihin
otteluihin vakaan MatchNumber-tunnisteen (kenttä "mno") perusteella.

Lähde: FIFA:n julkinen API — sama endpoint kuin hae_tulokset.py käyttää.
Ei uusia riippuvuuksia: pelkkä Pythonin standardikirjasto (vaatii Python 3.9+).

Käyttö: python3 hae_otteluohjelma.py
"""
import json
import sys
from datetime import datetime

from hae_tulokset import suomeksi, hae_json, FIFA_URL, AIKAVYOHYKE

OHJELMATIEDOSTO = "otteluohjelma.json"


def joukkue_nimi(side):
    """Joukkueen suomenkielinen nimi, tai None jos ottelu vielä ratkeamatta."""
    nimet = (side or {}).get("TeamName") or []
    kuvaus = nimet[0].get("Description") if nimet else None
    return suomeksi(kuvaus) if kuvaus else None


def pudotusottelut():
    """Pudotusvaiheen ottelut FIFA:n APIsta (kaikki paitsi First Stage).
    Palautetaan riveinä järjestettynä MatchNumberin mukaan."""
    data = hae_json(FIFA_URL)
    ottelut = []
    for m in data.get("Results", []):
        stage = ((m.get("StageName") or [{}])[0]).get("Description", "")
        if stage == "First Stage":  # lohkovaihe pois
            continue
        alku_utc = datetime.fromisoformat(m["Date"].replace("Z", "+00:00"))
        alku_fi = alku_utc.astimezone(AIKAVYOHYKE)
        ottelut.append({
            "mno": m.get("MatchNumber"),
            "stage": stage,
            "pvm": alku_fi.date().isoformat(),
            "aika_fi": alku_fi.strftime("%H:%M"),
            "koti": joukkue_nimi(m.get("Home")),
            "vieras": joukkue_nimi(m.get("Away")),
            # Lähdeottelu kun joukkue ei vielä selvillä: esim. "W73" = ottelun 73
            # voittaja. index.html näyttää tyhjälle paikalle vaihtoehdot (A/B).
            "koti_lahde": m.get("PlaceHolderA"),
            "vieras_lahde": m.get("PlaceHolderB"),
        })
    ottelut.sort(key=lambda x: x["mno"] if x["mno"] is not None else 0)
    return ottelut


def main():
    print("Haetaan pudotusvaiheen otteluohjelma FIFA:n APIsta...")
    ottelut = pudotusottelut()
    ratkennut = sum(1 for o in ottelut if o["koti"] and o["vieras"])
    print(f"  {len(ottelut)} ottelua ({ratkennut} joukkueparia selvillä)")

    # Kirjoitetaan vain jos otteluohjelma muuttui — muuten haettu-aikaleima
    # aiheuttaisi turhan commitin jokaisella ajolla (GitHub Actions).
    try:
        with open(OHJELMATIEDOSTO, encoding="utf-8") as f:
            vanhat = json.load(f).get("ottelut")
    except (FileNotFoundError, json.JSONDecodeError):
        vanhat = None
    if vanhat == ottelut:
        print(f"\nEi muutoksia - {OHJELMATIEDOSTO} ennallaan ({len(ottelut)} ottelua).")
        return 0

    data = {
        "haettu": datetime.now(AIKAVYOHYKE).isoformat(timespec="seconds"),
        "lahde": "FIFA API",
        "otteluita": len(ottelut),
        "ottelut": ottelut,
    }
    with open(OHJELMATIEDOSTO, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\nTallennettu {len(ottelut)} ottelua tiedostoon {OHJELMATIEDOSTO}:")
    for o in ottelut:
        pari = f"{o['koti']} – {o['vieras']}" if o["koti"] and o["vieras"] else "(ei vielä ratkennut)"
        print(f"  #{o['mno']:>3} {o['stage']:<24} {o['pvm']} {o['aika_fi']}  {pari}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
