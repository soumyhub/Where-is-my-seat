#!/usr/bin/env python3
"""Build the real-timetable dataset in ``data/tag2026/`` from open sources.

Inputs (downloaded once into a folder you pass on the command line):

* ``tag2026.json.gz`` — Indian Railways *Trains at a Glance 2026* (Railway Board), as parsed
  by the railways-mcp project (Apache-2.0):
  https://github.com/shubhamyadav8901/railways-mcp/tree/main/data
* ``wikidata_stations.json`` — Wikidata SPARQL result: every item with an Indian Railways
  station code (P5696), its English label and coordinates (CC0).
* ``junctions_wikitext.json`` — Wikipedia "List of railway junction stations in India"
  (CC BY-SA), used to flag junctions and add junction stations.
* ``ird_stations.json`` (optional) — the station directory of
  https://github.com/prasenjit-27/Indian-Railway-Data (MIT): ~9,000 station codes, names and
  coordinates. Only the directory is used; that repo's schedules are older than TAG 2026
  (most halt times differ), so none of its trains or timings are taken.

Nothing is guessed: trains without running days, classes or a confirmed origin are left out,
and every count of what was dropped is written to the dataset's meta block. The one inference:
when TAG does not mark the first listed stop as the origin but the train's own name starts
with that station (e.g. "Dadar Gorakhpur Special" listed from Dadar), that stop is taken as
the origin and day numbers follow TAG's own rule (+1 whenever the clock goes backwards).

Usage:  python3 -I data/tools/build_real_dataset.py <raw_dir>
"""

from __future__ import annotations

import gzip
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parents[1] / "tag2026"
DAYS = {"MON": "Mon", "TUE": "Tue", "WED": "Wed", "THU": "Thu", "FRI": "Fri", "SAT": "Sat", "SUN": "Sun"}
CLASSES = {"1A", "2A", "3A", "3E", "SL", "CC", "EC", "2S", "FC"}
CATEGORY = {"Exp": "Express", "SF": "Superfast", "Mail": "Mail", None: "Express"}
PREMIUM = {
    "Rajdhani", "Shatabdi", "Duronto", "Vande Bharat", "Humsafar", "Garib Rath", "Jan Shatabdi",
    "Sampark Kranti", "Tejas", "Double Decker", "Uday", "Amrit Bharat", "Antyodaya", "Superfast",
}
ROUTE_FACTOR = 1.18  # main halts only, so straight lines between them understate rail distance

# Multi-station cities. Only codes present in the network are used.
CITY_GROUPS: dict[str, dict] = {
    "delhi": {"name": "Delhi", "anchor": "NDLS", "aliases": ["new delhi", "dilli", "delhi ncr"],
              "codes": ["NDLS", "DLI", "NZM", "DEE", "DEC", "ANVT", "DSA", "ADRT"]},
    "mumbai": {"name": "Mumbai", "anchor": "CSMT", "aliases": ["bombay"],
               "codes": ["CSMT", "LTT", "MMCT", "BDTS", "DR", "DDR", "BCT", "BVI", "TNA", "ADH"]},
    "kolkata": {"name": "Kolkata", "anchor": "HWH", "aliases": ["calcutta", "howrah"],
                "codes": ["HWH", "SDAH", "KOAA", "SRC", "SHM"]},
    "chennai": {"name": "Chennai", "anchor": "MAS", "aliases": ["madras"],
                "codes": ["MAS", "MS", "TBM", "MSB", "PER"]},
    "bengaluru": {"name": "Bengaluru", "anchor": "SBC", "aliases": ["bangalore", "bengalooru"],
                  "codes": ["SBC", "YPR", "SMVB", "BNC", "KJM", "BNCE", "BAND"]},
    "hyderabad": {"name": "Hyderabad", "anchor": "SC", "aliases": ["secunderabad"],
                  "codes": ["SC", "HYB", "KCG", "LPI", "CHZ", "MJF"]},
    "pune": {"name": "Pune", "anchor": "PUNE", "aliases": ["poona"], "codes": ["PUNE", "HDP", "KK"]},
    "ahmedabad": {"name": "Ahmedabad", "anchor": "ADI", "aliases": ["amdavad"],
                  "codes": ["ADI", "SBT", "SBIB", "MAN"]},
    "jaipur": {"name": "Jaipur", "anchor": "JP", "aliases": ["pink city"], "codes": ["JP", "GADJ", "DPA"]},
    "lucknow": {"name": "Lucknow", "anchor": "LKO", "aliases": [], "codes": ["LKO", "LJN", "ASH", "GTNR"]},
    "kanpur": {"name": "Kanpur", "anchor": "CNB", "aliases": ["cawnpore"], "codes": ["CNB", "CPA", "GOY"]},
    "varanasi": {"name": "Varanasi", "anchor": "BSB", "aliases": ["banaras", "benares", "kashi"],
                 "codes": ["BSB", "BSBS", "BCY"]},
    "patna": {"name": "Patna", "anchor": "PNBE", "aliases": [], "codes": ["PNBE", "RJPB", "PPTA", "PNC"]},
    "agra": {"name": "Agra", "anchor": "AGC", "aliases": ["taj mahal"], "codes": ["AGC", "AF", "IDH", "RKM"]},
    "bhopal": {"name": "Bhopal", "anchor": "BPL", "aliases": ["habibganj"], "codes": ["BPL", "RKMP", "SHRN"]},
    "prayagraj": {"name": "Prayagraj", "anchor": "PRYJ", "aliases": ["allahabad"],
                  "codes": ["PRYJ", "PCOI", "PRRB", "SFG"]},
    "guwahati": {"name": "Guwahati", "anchor": "GHY", "aliases": ["gauhati"], "codes": ["GHY", "KYQ"]},
    "nagpur": {"name": "Nagpur", "anchor": "NGP", "aliases": [], "codes": ["NGP", "AJNI"]},
    "thiruvananthapuram": {"name": "Thiruvananthapuram", "anchor": "TVC", "aliases": ["trivandrum"],
                           "codes": ["TVC", "KCVL", "TVCN"]},
    "kochi": {"name": "Kochi", "anchor": "ERS", "aliases": ["cochin", "ernakulam"], "codes": ["ERS", "ERN"]},
    "jodhpur": {"name": "Jodhpur", "anchor": "JU", "aliases": [], "codes": ["JU", "BGKT", "RKB"]},
    "indore": {"name": "Indore", "anchor": "INDB", "aliases": [], "codes": ["INDB", "LMNR"]},
    "surat": {"name": "Surat", "anchor": "ST", "aliases": [], "codes": ["ST", "UDN"]},
    "vadodara": {"name": "Vadodara", "anchor": "BRC", "aliases": ["baroda"], "codes": ["BRC", "PRTN"]},
    "coimbatore": {"name": "Coimbatore", "anchor": "CBE", "aliases": [], "codes": ["CBE", "CBF", "PTJ"]},
    "madurai": {"name": "Madurai", "anchor": "MDU", "aliases": [], "codes": ["MDU", "KDL"]},
}

# Wikipedia junction names whose spelling differs from the timetable / Wikidata label.
# Each code was checked against Wikidata (label + coordinates) before being listed here.
JUNCTION_CODES = {
    "Ayodhya Junction": "AY", "Bangalore Cantonment": "BNC", "Dhrangadhra Junction": "DHG",
    "Gomoh Junction": "GMO", "Hubballi Junction": "UBL", "Itwari Junction": "ITR",
    "Jhansi Junction": "VGLJ", "Karaikudi Junction": "KKDI", "Mangalore Junction": "MAJN",
    "Pandit Deen Dayal Upadhyaya Junction": "DDU", "Sewagram Junction": "SEGM",
    "Singapur Road Junction": "SPRD", "Sitapur City Junction": "SPC", "Thiruthuraipoondi Junction": "TTP",
}

# Renamed stations travellers still search by old names.
STATION_ALIASES = {
    "DDU": ["mughalsarai"], "PRYJ": ["allahabad jn"], "RKMP": ["habibganj"], "AYC": ["faizabad"],
    "GGN": ["gurgaon", "gurugram"], "CSMT": ["vt", "victoria terminus", "bombay vt"],
    "MAS": ["madras central", "chennai central"], "SBC": ["bangalore city", "ksr bengaluru"],
    "KCVL": ["kochuveli"], "MMCT": ["bombay central"], "BSBS": ["manduadih"], "VGLJ": ["jhansi"],
    "DBG": ["darbhanga"], "MFP": ["muzaffarpur"], "KIR": ["katihar"],
}


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def norm(name: str) -> str:
    s = name.lower()
    s = re.sub(r"railway station|station|\(.*?\)", " ", s)
    s = re.sub(r"\bjunction\b|\bjn\b|\bjct\b", " ", s)
    s = re.sub(r"\bcantonment\b|\bcantt\b", " cantt ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return " ".join(s.split())


def hhmm(value: str | None) -> int | None:
    if not value:
        return None
    h, m = value.split(":")
    return int(h) * 60 + int(m)


INDIA_BOX = (6.0, 37.5, 68.0, 98.0)  # lat_min, lat_max, lon_min, lon_max
SMALL_WORDS = {"jn": "Jn", "jn.": "Jn", "rd": "Rd", "cantt": "Cantt", "t": "T"}


def tidy_name(raw: str) -> str:
    """'MUMBAI DADAR CENTRAL' -> 'Mumbai Dadar Central'; mixed-case names are kept."""
    name = " ".join(raw.split())
    if not name.isupper():
        return name
    words = [SMALL_WORDS.get(w.lower()) or w.capitalize() for w in name.split(" ")]
    return " ".join(words).replace("(t)", "(T)")


def origin_from_name(train: dict, station_names: dict[str, str]) -> bool:
    """True when the train's name starts with its first listed stop (that stop is the origin)."""
    first = train["stops"][0]
    names = {first[1] or ""}
    code = first[0] or (first[1] if first[1] in station_names else None)
    if code and code in station_names:
        names.add(station_names[code])
    title = norm(train.get("name") or "").split(" ")
    for n in names:
        words = norm(n).split(" ")
        if words and words[0] and len(words[0]) >= 3 and title[: 1] == words[:1]:
            return True
    return False


def infer_days(stops: list) -> list:
    """TAG's rule: day 1 at the origin, +1 whenever the clock time goes backwards."""
    day, last = 1, None
    out = []
    for stop in stops:
        arr, dep = hhmm(stop[2]), hhmm(stop[3])
        first = arr if arr is not None else dep
        if first is not None and last is not None and first < last:
            day += 1
        out.append([*stop[:4], day, stop[5]])
        if arr is not None and dep is not None and dep < arr:
            day += 1  # departs after midnight; the next stop is on the following day
        last = dep if dep is not None else arr
    return out


def parse_junctions(wikitext: str) -> list[dict]:
    rows = []
    for chunk in wikitext.split("\n|-"):
        m = re.search(r"\{\{rws\|([^}|]+)(?:\|[^}]*)?\}\}\s*\|\|\s*(\d+)\s*\|\|\s*(.*?)\|\|\s*(.*)", chunk)
        if not m:
            continue
        name, routes, division, state = m.groups()
        division = re.sub(r"\{\{rwd\|([^}]+)\}\}", r"\1", division).strip()
        state = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", state).split("\n")[0].strip()
        rows.append({"name": name.strip(), "routes": int(routes), "division": division, "state": state})
    return rows


def main(raw_dir: Path) -> None:
    tag = json.load(gzip.open(raw_dir / "tag2026.json.gz"))
    wikidata = json.load(open(raw_dir / "wikidata_stations.json"))["results"]["bindings"]
    junction_rows = parse_junctions(json.load(open(raw_dir / "junctions_wikitext.json"))["parse"]["wikitext"])

    # ----- stations ------------------------------------------------------
    tag_stations = {row[0]: row for row in tag["stations"]}
    wd: dict[str, dict] = {}
    for b in wikidata:
        code = b["code"]["value"].strip().upper()
        point = b.get("coord", {}).get("value", "")
        m = re.match(r"Point\(([-\d.]+) ([-\d.]+)\)", point)
        entry = wd.setdefault(code, {"label": None, "coord": None})
        if b.get("label") and not entry["label"]:
            entry["label"] = b["label"]["value"]
        if m and not entry["coord"]:
            entry["coord"] = (float(m.group(2)), float(m.group(1)))

    by_name_tag: dict[str, list[str]] = defaultdict(list)
    for code, row in tag_stations.items():
        by_name_tag[norm(row[1])].append(code)
    by_name_wd: dict[str, list[str]] = defaultdict(list)
    for code, entry in wd.items():
        if entry["label"]:
            by_name_wd[norm(entry["label"])].append(code)

    junctions: dict[str, dict] = {}
    unmatched: list[str] = []
    for j in junction_rows:
        if j["name"] in JUNCTION_CODES:
            code = JUNCTION_CODES[j["name"]]
            if code in tag_stations or wd.get(code, {}).get("coord"):
                junctions[code] = j
                continue
        key = norm(j["name"])
        candidates = by_name_tag.get(key) or []
        if len(candidates) > 1:
            candidates = [c for c in candidates if tag_stations[c][2] == j["state"]] or candidates
        if len(candidates) != 1:
            wd_candidates = by_name_wd.get(key) or []
            candidates = wd_candidates if len(wd_candidates) == 1 else []
        if len(candidates) == 1:
            junctions[candidates[0]] = j
        else:
            unmatched.append(j["name"])

    stations: dict[str, dict] = {}
    for code, (_, name, state, zone, lat, lon) in tag_stations.items():
        if lat is None and wd.get(code, {}).get("coord"):
            lat, lon = wd[code]["coord"]
        stations[code] = {"code": code, "name": name, "state": state or "", "zone": zone or "", "lat": lat, "lon": lon}
    for code, j in junctions.items():
        if code in stations:
            continue
        coord = wd.get(code, {}).get("coord")
        if not coord:
            unmatched.append(f"{j['name']} (no coordinates)")
            continue
        stations[code] = {"code": code, "name": j["name"], "state": j["state"], "zone": "", "lat": coord[0], "lon": coord[1]}

    # The full station directory: searchable even where no TAG train stops (the search then
    # starts or ends at the nearest station with trains, with a road leg).
    directory_added = 0
    ird_path = raw_dir / "ird_stations.json"
    for row in json.load(open(ird_path)) if ird_path.exists() else []:
        code = (row.get("code") or "").strip().upper()
        if not code or code in stations:
            continue
        c = row.get("coordinates") or {}
        lat, lon = c.get("latitude"), c.get("longitude")
        if lat is None and wd.get(code, {}).get("coord"):
            lat, lon = wd[code]["coord"]
        if lat is None or not (INDIA_BOX[0] < lat < INDIA_BOX[1] and INDIA_BOX[2] < lon < INDIA_BOX[3]):
            continue
        stations[code] = {
            "code": code, "name": tidy_name(row.get("name") or code), "state": row.get("state") or "",
            "zone": row.get("zone") or "", "lat": round(lat, 6), "lon": round(lon, 6),
        }
        directory_added += 1
    for code, s in stations.items():
        j = junctions.get(code)
        s["junction"] = bool(j)
        if j:
            s["routes"] = j["routes"]
            s["division"] = j["division"]
            if not s["state"]:
                s["state"] = j["state"]
            base = re.sub(r"\s+junction$", "", j["name"], flags=re.I)
            if norm(base) == norm(s["name"]) and "jn" not in s["name"].lower():
                s["name"] = f"{s['name']} Jn"
        s["aliases"] = STATION_ALIASES.get(code, [])

    # ----- trains --------------------------------------------------------
    skipped = Counter()
    recovered = 0  # trains whose origin is taken from the train's own name
    trains_out = []
    used_codes: set[str] = set()
    for t in tag["trains"]:
        number = t["n"]
        valid = t.get("valid")
        if valid and valid.get("from") == "06-10":
            skipped["konkan_monsoon_variant"] += 1
            continue
        if not t.get("days"):
            skipped["no_running_days"] += 1
            continue
        if t.get("classes") is None:
            skipped["classes_not_published"] += 1
            continue
        classes = [c for c in t["classes"] if c in CLASSES]
        unreserved_only = not classes  # TAG prints no reserved class: General (UR) coaches only
        raw_stops = t["stops"]
        origin_from_title = False
        if any(stop[4] is None for stop in raw_stops):
            if not origin_from_name(t, {c: r[1] for c, r in tag_stations.items()}):
                skipped["origin_not_confirmed"] += 1
                continue
            raw_stops = infer_days(raw_stops)
            origin_from_title = True
        stops = []
        seen: set[str] = set()
        duplicate = False
        dropped = 0
        for code, _name, arr, dep, day, _km in raw_stops:
            if not code or code not in stations or (arr is None and dep is None):
                dropped += 1
                continue
            if code in seen:
                duplicate = True
                break
            seen.add(code)
            stops.append({"code": code, "arr": arr, "dep": dep, "day": day})
        if duplicate:
            skipped["visits_station_twice"] += 1
            continue
        if len(stops) < 2:
            skipped["too_few_usable_stops"] += 1
            continue
        stops[0]["dep"] = stops[0]["dep"] or stops[0]["arr"]
        stops[0]["arr"] = None
        stops[-1]["arr"] = stops[-1]["arr"] or stops[-1]["dep"]
        stops[-1]["dep"] = None
        for s in stops[1:-1]:
            s["arr"] = s["arr"] or s["dep"]
            s["dep"] = s["dep"] or s["arr"]
        # monotonic time check with the same day rule the loader applies
        ok, last = True, -1
        for s in stops:
            base = (s["day"] - 1) * 1440
            a = base + hhmm(s["arr"]) if s["arr"] else None
            d = base + hhmm(s["dep"]) if s["dep"] else None
            if a is not None and d is not None and d < a:
                d += 1440
            for moment in (a, d):
                if moment is not None:
                    if moment < last:
                        ok = False
                    last = moment
        if not ok:
            skipped["times_go_backwards"] += 1
            continue
        km = 0.0
        prev = None
        for s in stops:
            here = stations[s["code"]]
            if prev is not None and None not in (prev["lat"], here["lat"]):
                km += haversine_km((prev["lat"], prev["lon"]), (here["lat"], here["lon"])) * ROUTE_FACTOR
            s["km"] = round(km)
            prev = here
        kind = t.get("type")
        category = CATEGORY.get(kind, kind)
        special = number.startswith("0")
        notes = []
        if dropped or any("omitted" in w for w in t.get("warnings") or []):
            notes.append("Some halts are not listed in the source timetable.")
        if special:
            notes.append("Special train: runs for a limited period — confirm the date on NTES or IRCTC.")
        if unreserved_only:
            notes.append("Unreserved train: General (UR) coaches only — buy on the UTS app or at the counter.")
        if origin_from_title:
            notes.append(
                "Running days assume the train starts at its first listed station (TAG does not mark it) "
                "— confirm the day on NTES or IRCTC."
            )
            recovered += 1
        trains_out.append({
            "number": number,
            "name": t.get("name") or f"Train {number}",
            "category": "Special" if special and category == "Express" else category,
            "simulated": False,
            "superfast": category in PREMIUM or number[:2] in ("12", "20", "22"),
            "runs_on": "daily" if len(t["days"]) == 7 else [DAYS[d] for d in t["days"]],
            "classes": classes,
            "unreserved": unreserved_only,
            "valid": {"from": valid["from"], "to": valid["to"]} if valid else None,
            "notes": notes,
            "source": "Trains at a Glance 2026",
            "stops": stops,
        })
        used_codes.update(s["code"] for s in stops)

    halts = Counter(stop["code"] for t in trains_out for stop in t["stops"])
    keep = stations
    for code, s in keep.items():
        s["halts"] = halts.get(code, 0)

    cities: dict[str, dict] = {}
    city_of: dict[str, str] = {}
    for key, group in CITY_GROUPS.items():
        codes = [c for c in group["codes"] if c in keep]
        if group["anchor"] in keep:  # keep the friendly city key even with one station
            cities[key] = {"name": group["name"], "anchor": group["anchor"], "aliases": group["aliases"]}
            for c in codes:
                city_of[c] = key
    for code, s in keep.items():
        key = city_of.get(code)
        if not key:
            key = code.lower()
            cities[key] = {"name": s["name"], "anchor": code, "aliases": []}
        s["city"] = key

    built = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    station_doc = {
        "meta": {
            "name": "Indian Railways stations on the TAG 2026 network",
            "version": "tag2026-2",
            "last_updated": built[:10],
            "coverage": f"{len(keep)} stations ({sum(1 for s in keep.values() if s['halts'])} with trains in "
            f"Trains at a Glance 2026, {len(junctions)} junctions from Wikipedia's list).",
            "directory": "Station codes, names and coordinates beyond TAG: prasenjit-27/Indian-Railway-Data (MIT).",
            "names_and_codes": "Indian Railways station codes (TAG 2026 / datameet / Wikidata).",
            "coordinates": "datameet 2016 via railways-mcp, gaps filled from Wikidata (CC0).",
            "junctions_source": "Wikipedia: List of railway junction stations in India (CC BY-SA 4.0).",
            "unmatched_junctions": sorted(unmatched),
        },
        "cities": cities,
        "stations": sorted(keep.values(), key=lambda s: s["code"]),
    }
    trains_doc = {
        "meta": {
            "simulated": False,
            "version": "tag2026-2",
            "source": "Indian Railways — Trains at a Glance 2026 (Railway Board)",
            "source_url": tag["meta"].get("source"),
            "parsed_by": "railways-mcp (Apache-2.0) — https://github.com/shubhamyadav8901/railways-mcp",
            "data_as_of": "2026",
            "last_updated": built[:10],
            "built_at": built,
            "trains": len(trains_out),
            "skipped": dict(skipped),
            "recovered_origin_from_name": recovered,
            "disclaimer": (
                "Timings are the published TAG 2026 timetable (main halts only). Retimings after publication "
                "are not reflected. Distances are estimated from station coordinates. Always confirm on NTES "
                "or IRCTC before travelling."
            ),
        },
        "trains": trains_out,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "stations.json").write_text(json.dumps(station_doc, ensure_ascii=False, indent=0) + "\n")
    (OUT_DIR / "trains.json").write_text(json.dumps(trains_doc, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"stations: {len(keep)} ({sum(s['junction'] for s in keep.values())} junctions, {len(cities)} cities, "
          f"{sum(1 for k in CITY_GROUPS if k in cities)} named city groups)")
    print(f"trains: {len(trains_out)}  skipped: {dict(skipped)}  recovered from name: {recovered}")
    print(f"directory stations added: {directory_added}  with trains: {sum(1 for s in keep.values() if s['halts'])}")
    print(f"junction rows: {len(junction_rows)}  matched: {len(junctions)}  unmatched: {len(unmatched)}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(Path(sys.argv[1]))
