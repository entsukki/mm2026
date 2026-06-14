#!/usr/bin/env node
/**
 * Salaa veikkaukset.json jaetulla salasanalla -> veikkaukset.enc.json.
 *
 * Salasana = purkuavain: sitä EI tallenneta mihinkään (ei tähän skriptiin,
 * ei outputtiin, ei repoon). Vain salattu möykky viedään versionhallintaan,
 * joten salasanaa ei voi selvittää koodia tai historiaa lukemalla.
 *
 * Parametrit ovat identtiset selaimen Web Crypto -purun kanssa (index.html):
 *   PBKDF2 SHA-256, 200000 kierrosta -> AES-256-GCM, salt 16 t, iv 12 t.
 *
 * Käyttö:
 *   MM2026_PW='jaettu-salasana' node salaa_veikkaukset.js
 *   (tai ilman muuttujaa -> kysyy salasanan interaktiivisesti)
 */
const crypto = require("crypto");
const fs = require("fs");

const SISAAN = "veikkaukset.json";
const ULOS = "veikkaukset.enc.json";
const ITER = 200000;

function kysySalasana() {
  return new Promise((resolve) => {
    const rl = require("readline").createInterface({ input: process.stdin, output: process.stdout });
    rl.question("Salasana: ", (vastaus) => { rl.close(); resolve(vastaus); });
  });
}

async function main() {
  const salasana = process.env.MM2026_PW || (await kysySalasana());
  if (!salasana) { console.error("Salasana puuttuu."); process.exit(1); }

  const data = fs.readFileSync(SISAAN, "utf-8"); // selkokielinen JSON
  const salt = crypto.randomBytes(16);
  const iv = crypto.randomBytes(12);
  const key = crypto.pbkdf2Sync(salasana, salt, ITER, 32, "sha256");

  const cipher = crypto.createCipheriv("aes-256-gcm", key, iv);
  const ct = Buffer.concat([cipher.update(data, "utf-8"), cipher.final()]);
  const tag = cipher.getAuthTag();

  // ct + authTag yhdistettynä (Web Crypto odottaa tagin ciphertextin perään)
  const paketti = {
    v: 1,
    salt: salt.toString("base64"),
    iv: iv.toString("base64"),
    ct: Buffer.concat([ct, tag]).toString("base64"),
  };
  fs.writeFileSync(ULOS, JSON.stringify(paketti, null, 2));
  console.log(`Salattu ${SISAAN} -> ${ULOS} (${paketti.ct.length} merkkiä ciphertextiä).`);
}

main();
