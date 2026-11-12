"""Build data.js for the exoplanet map.

Downloads the NASA Exoplanet Archive composite planet table and Hipparcos
(van Leeuwen 2007) parallaxes for the reference stars, projects everything
onto the Galactic plane, and writes a compact data.js next to this file.

    uv run python exoplanets/build_data.py
"""

import csv
import datetime as dt
import io
import json
import math
import re
import statistics
import urllib.parse
from collections import Counter
import urllib.request
from pathlib import Path

OUT = Path(__file__).parent / "data.js"

ARCHIVE_TAP = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
ARCHIVE_COLS = (
    "pl_name,hostname,ra,dec,glon,glat,sy_dist,sy_disterr1,sy_disterr2,"
    "sy_dist_reflink,discoverymethod,disc_facility,disc_year,disc_refname,"
    "pl_rade,pl_bmasse,pl_orbper,st_spectype,st_teff,st_mass,st_logg"
)
# VizieR mirror at CfA; the Strasbourg TAP services were down when this was written.
VIZIER_ASU = "https://vizier.cfa.harvard.edu/viz-bin/asu-tsv"

HIPPARCOS_REF = {
    "label": "van Leeuwen 2007 (Hipparcos new reduction)",
    "url": "https://doi.org/10.1051/0004-6361:20078357",
}

# name, HIP, constellation, note
STARS = [
    ("Sirius", 32349, "CMa", ""),
    ("Canopus", 30438, "Car", ""),
    ("Rigil Kentaurus", 71683, "Cen", "α Cen A"),
    ("Proxima Centauri", 70890, "Cen", "Nearest star; hosts Proxima b"),
    ("Barnard's Star", 87937, "Oph", ""),
    ("Arcturus", 69673, "Boo", ""),
    ("Vega", 91262, "Lyr", ""),
    ("Capella", 24608, "Aur", ""),
    ("Rigel", 24436, "Ori", ""),
    ("Procyon", 37279, "CMi", ""),
    ("Achernar", 7588, "Eri", ""),
    ("Hadar", 68702, "Cen", ""),
    ("Altair", 97649, "Aql", ""),
    ("Acrux", 60718, "Cru", ""),
    ("Mimosa", 62434, "Cru", ""),
    ("Gacrux", 61084, "Cru", ""),
    ("Imai", 59747, "Cru", "δ Cru"),
    ("Aldebaran", 21421, "Tau", ""),
    ("Antares", 80763, "Sco", ""),
    ("Shaula", 85927, "Sco", ""),
    ("Spica", 65474, "Vir", ""),
    ("Pollux", 37826, "Gem", ""),
    ("Castor", 36850, "Gem", ""),
    ("Fomalhaut", 113368, "PsA", ""),
    ("Regulus", 49669, "Leo", ""),
    ("Polaris", 11767, "UMi", ""),
    ("Bellatrix", 25336, "Ori", ""),
    ("Mintaka", 25930, "Ori", ""),
    ("Alnilam", 26311, "Ori", ""),
    ("Alnitak", 26727, "Ori", ""),
    ("Saiph", 27366, "Ori", ""),
    ("Dubhe", 54061, "UMa", ""),
    ("Merak", 53910, "UMa", ""),
    ("Phecda", 58001, "UMa", ""),
    ("Megrez", 59774, "UMa", ""),
    ("Alioth", 62956, "UMa", ""),
    ("Mizar", 65378, "UMa", ""),
    ("Alkaid", 67301, "UMa", ""),
    ("Alcyone", 17702, "Tau", "Brightest Pleiad"),
    ("Mirfak", 15863, "Per", ""),
    ("Algol", 14576, "Per", ""),
    ("Mira", 10826, "Cet", ""),
    ("Wezen", 34444, "CMa", ""),
    ("Naos", 39429, "Pup", ""),
    ("Eltanin", 87833, "Dra", ""),
    ("Albireo", 95947, "Cyg", ""),
    ("Sadr", 100453, "Cyg", ""),
]

# Hipparcos parallaxes are poor (or unusable) for these; use a published distance.
# name -> (distance pc, err+, err-, label, url)
DISTANCE_OVERRIDES = {
    "Betelgeuse": (168, 27, 15, "Joyce et al. 2020", "https://doi.org/10.3847/1538-4357/abb8db"),
    "Deneb": (802, 66, 66, "Schiller & Przybilla 2008", "https://doi.org/10.1051/0004-6361:20078590"),
}

# Objects not taken from Hipparcos at all: name, constellation, ra, dec, dist pc, err+, err-, ref, note
EXTRA_OBJECTS = [
    ("Betelgeuse", "Ori", 88.79287149, 7.40703653, *DISTANCE_OVERRIDES["Betelgeuse"], ""),
    ("Deneb", "Cyg", 310.35797281, 45.28033431, *DISTANCE_OVERRIDES["Deneb"], ""),
    ("Eta Carinae", "Car", 161.26477, -59.68443, 2350, 50, 50, "Smith 2006", "https://doi.org/10.1086/503766", "Luminous blue variable"),
    ("VY Canis Majoris", "CMa", 110.74302, -25.76755, 1200, 130, 100, "Zhang et al. 2012", "https://doi.org/10.1088/0004-637x/744/1/23", "Red hypergiant; maser parallax"),
    ("Orion Nebula", "Ori", 83.82208, -5.39111, 414, 7, 7, "Menten et al. 2007", "https://doi.org/10.1051/0004-6361:20078247", "M42; VLBA parallax"),
]

CONSTELLATION_FIGURES = {
    "Orion": [("Betelgeuse", "Bellatrix"), ("Bellatrix", "Mintaka"), ("Mintaka", "Alnilam"),
              ("Alnilam", "Alnitak"), ("Alnitak", "Saiph"), ("Saiph", "Rigel"), ("Rigel", "Mintaka"),
              ("Betelgeuse", "Alnitak")],
    "Big Dipper": [("Dubhe", "Merak"), ("Merak", "Phecda"), ("Phecda", "Megrez"), ("Megrez", "Dubhe"),
                   ("Megrez", "Alioth"), ("Alioth", "Mizar"), ("Mizar", "Alkaid")],
    "Crux": [("Acrux", "Gacrux"), ("Mimosa", "Imai")],
}

# ICRS -> Galactic rotation (Hipparcos catalogue, vol. 1, sec. 1.5.3)
GAL = (
    (-0.0548755604, -0.8734370902, -0.4838350155),
    (0.4941094279, -0.4448296300, 0.7469822445),
    (-0.8676661490, -0.1980763734, 0.4559837762),
)


def to_galactic(ra_deg, dec_deg):
    ra, dec = math.radians(ra_deg), math.radians(dec_deg)
    v = (math.cos(dec) * math.cos(ra), math.cos(dec) * math.sin(ra), math.sin(dec))
    x, y, z = (sum(r[i] * v[i] for i in range(3)) for r in GAL)
    return math.degrees(math.atan2(y, x)) % 360, math.degrees(math.asin(z))


def plane_xy(glon, glat, dist_pc):
    """Sun at origin, +x toward l=90 (direction of rotation), +y toward the Galactic centre."""
    l, b = math.radians(glon), math.radians(glat)
    d = dist_pc * math.cos(b)
    return round(d * math.sin(l), 2), round(d * math.cos(l), 2)


def fetch(url, data=None):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode() if data else None)
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read().decode()


def parse_anchor(html):
    """'<a refstr=... href=URL target=ref> Label</a>' -> (label, url)."""
    m = re.search(r"href=(\S+)[^>]*>\s*(.*?)\s*</a>", html or "")
    return (m.group(2), m.group(1)) if m else (None, None)


def num(s):
    return float(s) if s not in ("", None) else None


def category(method, facility):
    if facility == "Kepler" or facility == "K2":
        return "kepler"
    if facility.startswith("Transiting Exoplanet Survey Satellite"):
        return "tess"
    if method == "Transit":
        return "transit"
    return {"Radial Velocity": "rv", "Microlensing": "micro", "Imaging": "imaging"}.get(method, "other")


# Class boundaries: midpoints between adjacent subclasses in Mamajek's dwarf sequence
# (Pecaut & Mamajek 2013, table version 2022.04.16), e.g. F/G = (F9.5V 5990 K + G0V 5930 K) / 2.
# (class, Teff lower bound K, mass lower bound Msun), hottest first.
CLASS_BOUNDS = [("hot", 7310, 1.68), ("F", 5960, 1.07), ("G", 5325, 0.89), ("K", 3890, 0.58),
                ("M", 2310, 0.0775), ("bd", 0, 0)]
SPT_CLASS = {"O": "hot", "B": "hot", "A": "hot", "F": "F", "G": "G", "K": "K", "M": "M",
             "L": "bd", "T": "bd", "Y": "bd"}
# How a host's class was decided; shown on each planet's card.
CLASS_SOURCES = ["spectral type", "Teff", "mass (main sequence assumed)", "pulsar host", "white dwarf"]


def host_class(name, spts, teffs, masses, loggs):
    """-> (class id, source index, spectral type, Teff, mass, log g) from all of a host's rows.

    The composite table picks stellar parameters per planet, so rows for one host can
    disagree; take the most common spectral type and the median of each number.
    """
    spt = Counter(spts).most_common(1)[0][0] if spts else None
    teff = statistics.median(teffs) if teffs else None
    mass = statistics.median(masses) if masses else None
    logg = statistics.median(loggs) if loggs else None
    info = (spt, round(teff) if teff else None, round(mass, 3) if mass else None,
            round(logg, 2) if logg is not None else None)
    if name.startswith("PSR "):
        return ("ns", 3, *info)
    if (spt and re.match(r"D[ABCOQXZ]", spt)) or (logg is not None and logg >= 6.5) or name.startswith("WD "):
        return ("wd", 4, *info)
    m = re.match(r"(?:[a-z]+)?\s*([OBAFGKMLTY])", spt or "")
    if m:
        return (SPT_CLASS[m.group(1)], 0, *info)
    if teff:
        return (next(c for c, t, _ in CLASS_BOUNDS if teff >= t), 1, *info)
    if mass:
        return (next(c for c, _, ms in CLASS_BOUNDS if mass >= ms), 2, *info)
    return ("unk", -1, *info)


def build_hosts(rows):
    """-> (host names, host table rows) with one class per host."""
    acc = {}
    for r in rows:
        a = acc.setdefault(r["hostname"], ([], [], [], []))
        if r["st_spectype"].strip():
            a[0].append(r["st_spectype"].strip())
        for k, col in ((1, "st_teff"), (2, "st_mass"), (3, "st_logg")):
            if num(r[col]) is not None:
                a[k].append(num(r[col]))
    names = sorted(acc)
    return names, [list(host_class(n, *acc[n])) for n in names]


def build_planets():
    query = f"select {ARCHIVE_COLS} from pscomppars"
    rows = list(csv.DictReader(io.StringIO(fetch(ARCHIVE_TAP, {"query": query, "format": "csv"}))))

    refs, ref_index = [], {}

    def ref_id(html):
        label, url = parse_anchor(html)
        if not url:
            return -1
        if url not in ref_index:
            ref_index[url] = len(refs)
            refs.append([label, url])
        return ref_index[url]

    host_names, host_rows = build_hosts(rows)
    host_index = {n: i for i, n in enumerate(host_names)}

    cols = {k: [] for k in ("name", "host", "hidx", "x", "y", "d", "dep", "dem", "l", "b", "cat", "method",
                            "facility", "year", "disc", "dref", "rade", "masse", "per")}
    facilities, fac_index = [], {}
    methods, method_index = [], {}
    missing = []
    for r in rows:
        dist, glon, glat = num(r["sy_dist"]), num(r["glon"]), num(r["glat"])
        if dist is None:
            missing.append([r["pl_name"], r["discoverymethod"], r["disc_facility"], ref_id(r["disc_refname"])])
            continue
        x, y = plane_xy(glon, glat, dist)
        fac = r["disc_facility"]
        if fac not in fac_index:
            fac_index[fac] = len(facilities)
            facilities.append(fac)
        meth = r["discoverymethod"]
        if meth not in method_index:
            method_index[meth] = len(methods)
            methods.append(meth)
        cols["name"].append(r["pl_name"])
        cols["host"].append(r["hostname"])
        cols["hidx"].append(host_index[r["hostname"]])
        cols["x"].append(x)
        cols["y"].append(y)
        cols["d"].append(round(dist, 2))
        cols["dep"].append(num(r["sy_disterr1"]))
        cols["dem"].append(num(r["sy_disterr2"]))
        cols["l"].append(round(glon, 3))
        cols["b"].append(round(glat, 3))
        cols["cat"].append(category(meth, fac))
        cols["method"].append(method_index[meth])
        cols["facility"].append(fac_index[fac])
        cols["year"].append(int(r["disc_year"]))
        cols["disc"].append(ref_id(r["disc_refname"]))
        cols["dref"].append(ref_id(r["sy_dist_reflink"]))
        cols["rade"].append(num(r["pl_rade"]))
        cols["masse"].append(num(r["pl_bmasse"]))
        cols["per"].append(num(r["pl_orbper"]))
    # hosts: [class, source, spectral type, Teff, mass, log g]; planets point in with hidx
    return {"cols": cols, "refs": refs, "facilities": facilities, "methods": methods,
            "hosts": host_rows, "class_sources": CLASS_SOURCES,
            "missing": missing, "total": len(rows)}


def build_stars():
    hips = ",".join(str(h) for _, h, _, _ in STARS)
    tsv = fetch(VIZIER_ASU, {"-source": "I/311/hip2", "-out.max": "500",
                             "-out": "HIP,RArad,DErad,Plx,e_Plx", "HIP": hips})
    hip = {}
    for line in tsv.splitlines():
        parts = line.split("\t")
        if len(parts) == 5 and parts[0].strip().isdigit():
            hip[int(parts[0])] = [float(p) for p in parts[1:]]

    stars = []
    for name, h, con, note in STARS:
        ra, dec, plx, eplx = hip[h]
        lo, hi = 1000 / (plx + eplx), 1000 / (plx - eplx) if plx > eplx else None
        d = 1000 / plx
        glon, glat = to_galactic(ra, dec)
        x, y = plane_xy(glon, glat, d)
        stars.append({
            "name": name, "con": con, "note": note, "x": x, "y": y, "d": round(d, 2),
            "dep": round(hi - d, 2) if hi else None, "dem": round(d - lo, 2),
            "l": round(glon, 3), "b": round(glat, 3), "plx": plx, "eplx": eplx,
            "ref": HIPPARCOS_REF, "simbad": f"https://simbad.cds.unistra.fr/simbad/sim-id?Ident=HIP+{h}",
        })
    for name, con, ra, dec, d, ep, em, label, url, note in EXTRA_OBJECTS:
        glon, glat = to_galactic(ra, dec)
        x, y = plane_xy(glon, glat, d)
        stars.append({
            "name": name, "con": con, "note": note, "x": x, "y": y, "d": d, "dep": ep, "dem": em,
            "l": round(glon, 3), "b": round(glat, 3), "ref": {"label": label, "url": url},
            "simbad": "https://simbad.cds.unistra.fr/simbad/sim-id?Ident=" + urllib.parse.quote(name),
        })
    return stars


def main():
    planets = build_planets()
    data = {
        "retrieved": dt.date.today().isoformat(),
        "planets": planets,
        "stars": build_stars(),
        "figures": CONSTELLATION_FIGURES,
    }
    OUT.write_text("window.GALAXY_DATA = " + json.dumps(data, separators=(",", ":"), ensure_ascii=False) + ";\n")
    n = len(planets["cols"]["name"])
    print(f"{n} planets plotted, {len(planets['missing'])} without distance, "
          f"{len(data['stars'])} reference objects -> {OUT} ({OUT.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
