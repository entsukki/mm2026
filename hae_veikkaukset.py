#!/usr/bin/env python3
"""Hakee kaveriporukan MM 2026 -tulosveikkaukset julkaistusta Google Sheetistä
ja päivittää ne veikkaukset.json-tiedostoon.

Alkulohkoveikkaukset (72 ottelua × 14 veikkaajaa) ovat lukittuja ja jo
tallennettuna; Sheetissä ne ovat nykyään 3-kirjaimisina FIFA-koodeina, joten
niitä EI parsita uudelleen. Tämä skripti päivittää vain ratkenneet
pudotusvaiheen ottelut (1/16-välierät eteenpäin), joissa joukkueet ovat
suomenkielisinä niminä ja jotka löytyvät otteluohjelma.json:sta. Ajetaan
uudelleen aina kun uusi pudotuskierros ratkeaa. Lähde-URL annetaan
ympäristömuuttujassa MM2026_SHEET_URL — sitä ei tallenneta tähän tiedostoon
eikä versionhallintaan. Ei riippuvuuksia: standardikirjasto (3.9+).

Käyttö: MM2026_SHEET_URL='<julkaistu sheet .../pub?output=csv>' python3 hae_veikkaukset.py
"""
import csv
import io
import json
import os
import re
import ssl
import sys
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

CSV_URL = os.environ.get("MM2026_SHEET_URL")  # annetaan ympäristömuuttujassa, ei repossa
VEIKKAUSTIEDOSTO = "veikkaukset.json"
OTTELUOHJELMA = "otteluohjelma.json"
AIKAVYOHYKE = ZoneInfo("Europe/Helsinki")

# Sheetin sarakerakenne (1/16-välierien lisäyksen jälkeen):
#   sarake 0 = selite (tyhjä = alkulohko, esim. "R32" = pudotusvaihe)
#   sarake 1 = koti, sarake 2 = "-", sarake 3 = vieras
#   sarakkeet 4, 7, 10, ... = veikkaajat (koti-maalit; vieras-maalit +2)
SELITE_SARAKE = 0
KOTI_SARAKE = 1
VIERAS_SARAKE = 3
VEIKKAAJA_ALKU = 4
NIMIRIVI = 1

# Pudotusvaiheen lähde-tunnisteet (esim. "W73", "L101") eivät ole joukkueita
PLACEHOLDER = re.compile(r"^[WL]\d+$")

# Sheetin joukkuenimet -> index.html:n nimet (vain poikkeavat; loput täsmäävät)
ALIAS = {
    "Tsekki": "Tshekki",
    "Bosnia": "Bosnia ja Hertsegovina",
    "Curacao": "Curaçao",
    "Kongon DT": "Kongon dem. tasavalta",
    "Saudi Arabia": "Saudi-Arabia",
    "Uusi Seelanti": "Uusi-Seelanti",
}


def normalisoi(nimi):
    nimi = nimi.strip()
    return ALIAS.get(nimi, nimi)


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


def hae_csv(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "mm2026-veikkaukset/1.0 (github.com/entsukki/mm2026)",
    })
    with urllib.request.urlopen(req, timeout=20, context=SSL_CTX) as vastaus:
        return vastaus.read().decode("utf-8")


def pudotusvaiheen_ottelut():
    """Palauttaa otteluohjelma.json:n SELVINNEET pudotusotteluiden
    match-avaimet ('Koti – Vieras') joukkona. Mukaan vain ne, joiden
    molemmat joukkueet ovat ratkenneet (ei None eikä W##/L##-placeholder).
    Nämä avaimet vastaavat index.html:n haunavainta data.ottelut[m.match]."""
    data = json.load(open(OTTELUOHJELMA, encoding="utf-8"))
    ottelut = data if isinstance(data, list) else data.get("ottelut", [])
    avaimet = set()
    for o in ottelut:
        koti, vieras = o.get("koti"), o.get("vieras")
        if not koti or not vieras:
            continue
        if PLACEHOLDER.match(str(koti)) or PLACEHOLDER.match(str(vieras)):
            continue
        avaimet.add(f"{koti} – {vieras}")  # en-dash, kuten index.html
    return avaimet


def main():
    if not CSV_URL:
        print("Aseta lähde-URL ympäristömuuttujaan MM2026_SHEET_URL.", file=sys.stderr)
        print("Esim: MM2026_SHEET_URL='https://docs.google.com/.../pub?output=csv' python3 hae_veikkaukset.py", file=sys.stderr)
        return 1
    # Alkulohkoveikkaukset (72 ottelua) ovat lukittuja ja jo tallennettuna.
    # Sheetin alkulohkorivit käyttävät nyt 3-kirjaimisia FIFA-koodeja, joten
    # niitä EI parsita uudelleen — säilytetään olemassa olevat entryt ja
    # päivitetään vain ratkenneet pudotusvaiheen ottelut (suomenkieliset nimet).
    if not os.path.exists(VEIKKAUSTIEDOSTO):
        print(f"Puuttuu {VEIKKAUSTIEDOSTO} (alkulohkodata). Aja ensin alkulohkohaku.", file=sys.stderr)
        return 1
    vanha = json.load(open(VEIKKAUSTIEDOSTO, encoding="utf-8"))
    ottelut = vanha.get("ottelut", {})

    print("Haetaan veikkaukset julkaistusta Sheetistä...")
    rivit = list(csv.reader(io.StringIO(hae_csv(CSV_URL))))

    # Rivi indeksissä 1 = veikkaajien nimet sarakkeissa 4, 7, 10, ...
    nimirivi = rivit[NIMIRIVI]
    veikkaajat = []
    for c in range(VEIKKAAJA_ALKU, len(nimirivi), 3):
        nimi = nimirivi[c].strip()
        if nimi:
            veikkaajat.append((c, nimi))
    print(f"  veikkaajia: {len(veikkaajat)}")

    valid_pudotus = pudotusvaiheen_ottelut()
    paivitetyt = {}
    tasmaamattomat = []
    for r in rivit[2:]:
        if len(r) <= VIERAS_SARAKE or not r[SELITE_SARAKE].strip():
            continue  # tyhjä selite = alkulohko (ohitetaan), tyhjä rivi = väli
        koti = normalisoi(r[KOTI_SARAKE])
        vieras = normalisoi(r[VIERAS_SARAKE])
        if PLACEHOLDER.match(koti) or PLACEHOLDER.match(vieras):
            continue  # ottelu ei vielä ratkennut (esim. "W73 – W75")
        avain = f"{koti} – {vieras}"  # en-dash, kuten index.html
        if avain not in valid_pudotus:
            tasmaamattomat.append(f"{r[SELITE_SARAKE].strip()}: {avain}")
            continue
        lista = []
        for c, nimi in veikkaajat:
            k, v = r[c].strip(), r[c + 2].strip()
            if k.isdigit() and v.isdigit():
                lista.append({"nimi": nimi, "koti": int(k), "vieras": int(v)})
        paivitetyt[avain] = lista
        ottelut[avain] = lista

    print(f"  {len(paivitetyt)}/{len(valid_pudotus)} ratkennutta pudotusottelua täsmäsi otteluohjelmaan")
    if tasmaamattomat:
        print("  VAROITUS: täsmäämättömät pudotusottelut (tarkista alias-map):", file=sys.stderr)
        for a in tasmaamattomat:
            print(f"    - {a}", file=sys.stderr)
        return 1
    if len(paivitetyt) != len(valid_pudotus):
        print(f"  VAROITUS: ratkenneita otteluita {len(valid_pudotus)}, "
              f"Sheetistä löytyi {len(paivitetyt)}", file=sys.stderr)
        return 1

    data = {
        "haettu": datetime.now(AIKAVYOHYKE).isoformat(timespec="seconds"),
        "veikkaajat": [n for _, n in veikkaajat],
        "ottelut": ottelut,
    }
    with open(VEIKKAUSTIEDOSTO, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    yht = sum(len(v) for v in ottelut.values())
    print(f"\nPäivitetty {len(paivitetyt)} pudotusottelua "
          f"(yhteensä {len(ottelut)} ottelua, {yht} veikkausta) -> {VEIKKAUSTIEDOSTO}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
