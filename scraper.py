"""Lit le calendrier FFTA de tous les départements et écrit events.json (une ligne par concours)."""
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://www.ffta.fr/competitions"
HEADERS = {"User-Agent": "carte-tir-arc-44 (lecture du calendrier, une fois par nuit)"}
GEO_FILE = Path("geocache.json")
OUT_FILE = Path("events.json")

MOIS = {m: i + 1 for i, m in enumerate(
    "janvier février mars avril mai juin juillet août septembre octobre novembre décembre".split())}
SMALL = {"de", "du", "des", "la", "le", "les", "et", "à", "sur", "en", "aux", "au"}
# Codes : S salle, E extérieur, C campagne, T 3D, N nature, B beursault, L loisirs, A autres.
# Le para-tir est fusionné avec le concours correspondant (colonne "P").


def is_para(l):
    return (l or "").lower().startswith("para")


def code_disc(l):
    s = (l or "").lower()
    for mot, code in (("3d", "T"), ("campagne", "C"), ("nature", "N"), ("beursault", "B"), ("run archery", "A"),
                      ("18", "S"), ("salle", "S"), ("ext", "E"), ("fita", "E"), ("loisir", "L"), ("jeune", "L"),
                      ("poussin", "L"), ("divers", "L"), ("rencontre", "L"), ("débutant", "L")):
        if mot in s:
            return code
    return "A"


def decode(h):
    """Décode les adresses e-mail masquées par le site (Cloudflare)."""
    k = int(h[:2], 16)
    return bytes(int(h[i:i + 2], 16) ^ k for i in range(2, len(h), 2)).decode()


def tidy(s):
    """MAJUSCULES -> Majuscules lisibles."""
    out = []
    for i, w in enumerate(s.lower().split()):
        if w in ("st", "ste"):
            out.append("Saint" if w == "st" else "Sainte")
        elif "." in w:
            out.append(w.upper())
        elif i and w in SMALL:
            out.append(w)
        elif w[:2] in ("d'", "l'"):
            out.append(w[:2] + w[2:].capitalize())
        else:
            out.append("-".join(p.capitalize() for p in w.split("-")))
    return " ".join(out)


def fetch(n, start, end, dep=None):
    p = {"discipline": "All", "end": end, "inter": "All", "sort_by": "start", "sort_order": "ASC",
         "start": start, "univers": "All", "page": n}
    if dep:
        p["dep[]"] = dep
    for essai in (1, 2):
        try:
            r = requests.get(BASE, params=p, headers=HEADERS, timeout=30)
            r.raise_for_status()
            return r.text
        except Exception:
            if essai == 2:
                raise
            time.sleep(5)


def departements(html):
    """Lit la liste déroulante des départements : {code: {"val": valeur du site, "nom": nom}}."""
    soup = BeautifulSoup(html, "html.parser")
    sel = soup.find("select", attrs={"name": re.compile("dep")})
    out = {}
    for o in (sel.find_all("option") if sel else []):
        val, txt = (o.get("value") or "").strip(), o.get_text(" ", strip=True)
        m = re.match(r"^\s*(\d{2,3}|2[AB])\b\s*[-–:.]?\s*(.*)$", txt)
        if val and val.lower() != "all" and m:
            out[m[1]] = {"val": val, "nom": m[2].strip()}
    return out


def lines(html):
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=re.compile(r"/epreuve/\d+")):
        if a.find_parent(re.compile(r"^h[1-6]$")):
            num = re.search(r"/epreuve/(\d+)", a["href"]).group(1)
            a.replace_with("\n@@T|%s|%s\n" % (num, a.get_text(" ", strip=True)))
    for a in soup.find_all("a", href=re.compile(r"documents_epreuves/.+\.pdf")):
        a.replace_with("\n@@D|%s\n" % urljoin(BASE, a["href"]))
    for a in soup.find_all(href=re.compile("email-protection#")):
        try:
            a.replace_with("\n@@M|%s\n" % decode(a["href"].split("#")[1]))
        except Exception:
            pass
    for s in soup.find_all(attrs={"data-cfemail": True}):
        try:
            s.replace_with("\n@@M|%s\n" % decode(s["data-cfemail"]))
        except Exception:
            pass
    return [l.strip() for l in soup.get_text("\n").split("\n") if l.strip()]


def parse_date(l):
    m = re.fullmatch(r"Le (\d{1,2}) (\S+) (\d{4})", l)
    if m and m[2].lower() in MOIS:
        d = dt.date(int(m[3]), MOIS[m[2].lower()], int(m[1]))
        return d, d
    m = re.fullmatch(r"Du (\d{1,2})(?: (\S+))? au (\d{1,2}) (\S+) (\d{4})", l)
    if m and m[4].lower() in MOIS:
        y, m2 = int(m[5]), MOIS[m[4].lower()]
        m1 = MOIS.get((m[2] or "").lower(), m2)
        return dt.date(y - 1 if m1 > m2 else y, m1, int(m[1])), dt.date(y, m2, int(m[3]))
    return None


def parse_lines(ls):
    out, date, statut, cur = [], None, "", None
    for l in ls:
        d = parse_date(l)
        if d:
            date, statut, cur = d, "", None
            continue
        if l in ("Annulée", "Reportée"):
            statut = l
            continue
        if l.startswith("@@T|"):
            _, id_, t = l.split("|", 2)
            cur = {"id": id_, "t": t, "date": date, "s": statut, "d": None, "club": "", "m": "", "mandat": ""}
            out.append(cur)
            statut = ""
            continue
        if cur is None:
            continue
        if l.startswith("@@M|"):
            cur["m"] = cur["m"] or l[4:]
        elif l.startswith("@@D|"):
            cur["mandat"] = l[4:]
        elif l in ("Individuel", "Uniquement équipe", "Mail", "Site", "Mandat", "Détail"):
            continue
        elif cur["d"] is None:
            cur["d"] = l          # la première ligne après le titre est la discipline
        elif not cur["club"] and re.search(r"[A-ZÀ-Ý]{3}", l):
            cur["club"] = l
    return out


def geocode(ville, cache, code):
    cle = "%s|%s" % (ville, code)
    if cle in cache:
        return cache[cle]
    q0 = re.sub(r"\bSTE\b", "SAINTE", re.sub(r"\bST\b", "SAINT", ville.upper()))
    for q in dict.fromkeys([q0, re.sub(r"\s+(\d+|CEDEX).*$", "", q0)]):
        try:
            r = requests.get("https://api-adresse.data.gouv.fr/search/",
                             params={"q": q, "type": "municipality", "limit": 15},
                             headers=HEADERS, timeout=20).json()
            for f in r.get("features", []):
                if f["properties"].get("context", "").split(",")[0].strip() == code:
                    lon, lat = f["geometry"]["coordinates"]
                    cache[cle] = [round(lat, 4), round(lon, 4)]
                    time.sleep(0.15)
                    return cache[cle]
        except Exception as ex:
            print("Géocodage impossible pour", ville, ex)
    print("Commune introuvable :", ville, code)
    return None


def split(e):
    t, ville = e["t"], None
    if " à " in t:
        t, ville = t.rsplit(" à ", 1)
    m = re.match(r"(.*?)\s*\(([^)]+)\)\s*$", e["club"])
    club, cville = (m[1], m[2]) if m else (e["club"], None)
    return t, ville or cville, club


def build(raw, cache, code):
    """Une ligne par concours ; le para-tir est fusionné (colonne 12 = "P", colonne 13 = lien du mandat, colonne 14 = code du département) avec le concours correspondant."""
    rows, mails = {}, {}
    ok = [e for e in raw if e["s"] != "Annulée" and e["date"]]
    for e in ok:
        if e["m"]:
            mails[split(e)[2].lower()] = e["m"]
    for e in sorted(ok, key=lambda e: not e["m"]):  # ceux qui ont une adresse mail d'abord
        t, ville, club = split(e)
        if not e["d"] or is_para(e["d"]) or not ville:
            continue
        key = (t.lower(), str(e["date"][0]), ville.lower())
        if key in rows:
            continue
        ll = geocode(ville, cache, code) or ["", ""]
        rows[key] = [e["id"], tidy(t), e["date"][0].isoformat(), e["date"][1].isoformat(), code_disc(e["d"]),
                     tidy(club), tidy(ville), e["m"].lower(), e["s"], ll[0], ll[1], "", e["mandat"], code]
    for e in ok:
        if not is_para(e["d"]):
            continue
        t, ville, club = split(e)
        if not ville:
            continue
        key = (t.lower(), str(e["date"][0]), ville.lower())
        if key in rows:
            rows[key][11] = "P"
            rows[key][12] = rows[key][12] or e["mandat"]
        else:  # para-tir sans concours « valides » correspondant : on le garde seul
            ll = geocode(ville, cache, code) or ["", ""]
            rows[key] = [e["id"], tidy(t), e["date"][0].isoformat(), e["date"][1].isoformat(),
                         code_disc(e["d"]), tidy(club), tidy(ville),
                         (e["m"] or mails.get(club.lower(), "")).lower(), e["s"], ll[0], ll[1], "P", e["mandat"], code]
    return sorted(rows.values(), key=lambda r: (r[2], r[1]))


def lire_departement(val, start, end):
    raw, ids = [], set()
    for n in range(40):
        ls = lines(fetch(n, start, end, val))
        new = [e for e in parse_lines(ls) if e["id"] not in ids]
        if not new:
            break
        ids.update(e["id"] for e in new)
        raw += new
        time.sleep(1)
    return raw


def main():
    today = dt.date.today()
    start, end = today.isoformat(), (today + dt.timedelta(days=366)).isoformat()
    deps = departements(fetch(0, start, end))
    if not deps:
        sys.exit("Liste des départements introuvable : la page de la FFTA a peut-être changé.")
    print(len(deps), "départements trouvés")
    cache = json.loads(GEO_FILE.read_text("utf-8")) if GEO_FILE.exists() else {}
    rows, noms, echecs, vus = [], {}, [], set()
    for code in sorted(deps):
        try:
            raw = lire_departement(deps[code]["val"], start, end)
        except Exception as ex:
            print("Échec pour le département", code, ex)
            echecs.append(code)
            continue
        noms[code] = deps[code]["nom"]
        for r in build(raw, cache, code):
            if r[0] not in vus:          # un même concours n'est gardé qu'une fois
                vus.add(r[0])
                rows.append(r)
    if len(echecs) > 5 or not rows:
        sys.exit("Trop d'échecs (%s) ou aucun concours : les fichiers n'ont pas été modifiés." % echecs)
    GEO_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), "utf-8")
    Path("departements.json").write_text(json.dumps(noms, ensure_ascii=False), "utf-8")
    OUT_FILE.write_text(json.dumps(sorted(rows, key=lambda r: (r[2], r[1])), ensure_ascii=False), "utf-8")
    print(len(rows), "concours écrits dans", OUT_FILE, "| départements en échec :", echecs or "aucun")


if __name__ == "__main__":
    main()
