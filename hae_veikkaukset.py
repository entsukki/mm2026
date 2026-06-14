#!/usr/bin/env python3
"""Hakee kaveriporukan MM 2026 -tulosveikkaukset julkaistusta Google Sheetistä
ja tallentaa ne veikkaukset.json-tiedostoon.

Lähde: julkaistu Sheet CSV-exportina (72 ottelua × 14 veikkaajaa = 1008 veikkausta).
Veikkaukset ovat lukittuja (esiturnaus), joten tämä ajetaan kertaluonteisesti
käsin — EI GitHub Actionsiin. Ei riippuvuuksia: pelkkä standardikirjasto (3.9+).

Käyttö: python3 hae_veikkaukset.py
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

CSV_URL = ("https://docs.google.com/spreadsheets/d/e/REDACTED"
           "REDACTED/pub?output=csv")
VEIKKAUSTIEDOSTO = "veikkaukset.json"
INDEX_HTML = "index.html"
AIKAVYOHYKE = ZoneInfo("Europe/Helsinki")

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


def index_ottelut():
    """Palauttaa index.html:n alkulohko-otteluiden match-merkkijonot joukkona.
    Alkulohko-ottelut ovat ne, joilla EI ole stage-kenttää."""
    teksti = open(INDEX_HTML, encoding="utf-8").read()
    ottelut = set()
    for rivi in teksti.splitlines():
        if "match:'" in rivi and "stage:" not in rivi:
            m = re.search(r"match:'([^']+)'", rivi)
            if m:
                ottelut.add(m.group(1))
    return ottelut


def main():
    print("Haetaan veikkaukset julkaistusta Sheetistä...")
    rivit = list(csv.reader(io.StringIO(hae_csv(CSV_URL))))

    # Rivi indeksissä 1 = veikkaajien nimet sarakkeissa 3, 6, 9, ...
    nimirivi = rivit[1]
    veikkaajat = []
    for c in range(3, len(nimirivi), 3):
        nimi = nimirivi[c].strip()
        if nimi:
            veikkaajat.append((c, nimi))
    print(f"  veikkaajia: {len(veikkaajat)}")

    valid_ottelut = index_ottelut()
    ottelut = {}
    tasmaamattomat = []
    for r in rivit[2:]:
        if not r or not r[0].strip():
            continue
        koti = normalisoi(r[0])
        vieras = normalisoi(r[2])
        avain = f"{koti} – {vieras}"  # en-dash, kuten index.html
        if avain not in valid_ottelut:
            tasmaamattomat.append(avain)
            continue
        lista = []
        for c, nimi in veikkaajat:
            k, v = r[c].strip(), r[c + 2].strip()
            if k.isdigit() and v.isdigit():
                lista.append({"nimi": nimi, "koti": int(k), "vieras": int(v)})
        ottelut[avain] = lista

    print(f"  {len(ottelut)}/{len(valid_ottelut)} ottelua täsmäsi index.html:ään")
    if tasmaamattomat:
        print("  VAROITUS: täsmäämättömät ottelut (tarkista alias-map):", file=sys.stderr)
        for a in tasmaamattomat:
            print(f"    - {a}", file=sys.stderr)
        return 1
    if len(ottelut) != 72:
        print(f"  VAROITUS: odotettiin 72 ottelua, saatiin {len(ottelut)}", file=sys.stderr)
        return 1

    data = {
        "haettu": datetime.now(AIKAVYOHYKE).isoformat(timespec="seconds"),
        "veikkaajat": [n for _, n in veikkaajat],
        "ottelut": ottelut,
    }
    with open(VEIKKAUSTIEDOSTO, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    yht = sum(len(v) for v in ottelut.values())
    print(f"\nTallennettu {len(ottelut)} ottelua, {yht} veikkausta -> {VEIKKAUSTIEDOSTO}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
