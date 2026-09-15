#!/usr/bin/env python3


import requests, re, csv
from pyproj import Geod
from tqdm import tqdm
import os
import json

GEOD = Geod(ellps='WGS84')

def parse_maxspeed(v):
    """Returns the speed in km/h (float) or None if not interpretable."""
    if not v: return None
    s = str(v).lower().strip()
    # if "signals" or "none"
    if not re.search(r'\d', s):
        return None
    # extract the first number
    m = re.search(r'(\d+(\.\d+)?)', s)
    if not m:
        return None
    val = float(m.group(1))
    if 'mph' in s:
        val *= 1.609344
    # other rare units not handled -> we ignore them
    return val

def geodesic_length_coords(coords):
    """coords = list of (lon, lat). Returns length in meters (WGS84 geodesic)."""
    total = 0.0
    for (lon1, lat1), (lon2, lat2) in zip(coords, coords[1:]):
        # pyproj.Geod.inv(lon1, lat1, lon2, lat2) -> (az12, az21, dist)
        _, _, d = GEOD.inv(lon1, lat1, lon2, lat2)
        total += d
    return total

overpass_server_idx = 0
def overpass_fetch_country_ways(iso, out_json_path, tries=10):
    global overpass_server_idx

    query = f"""
        [out:json][timeout:900];
        area["ISO3166-1"="{iso}"][admin_level=2]->.a;
        (
        way["railway"="rail"]["maxspeed"~"^([2-9][0-9]{{2}}|1[2-9][0-9] ?mph).*", i](area.a);
        way["railway"="rail"]["maxspeed:forward"~"^([2-9][0-9]{{2}}|1[2-9][0-9] ?mph).*", i](area.a);
        );
        out geom;
    """

    overpass_servers = [
        "https://overpass-api.de/api/interpreter",
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
        "https://overpass.private.coffee/api/interpreter"
    ]

    for i in range(tries):
        url = overpass_servers[overpass_server_idx%len(overpass_servers)]
        try:
            response = requests.post(
                url,
                data={"data": query},
                headers={
                        "User-Agent": "HSR-get-stats-openstreetmap/1.0 (https://github.com/achille-correge/HSR-get-stats-openstreetmap)"
                    },
                    timeout=900
                )
            if response.status_code != 200:
                print("URL:", response.url)
                print("HTTP:", response.status_code)
                print("Content-Type:", response.headers.get("Content-Type"))
                print(response.text[:2000])
                response.raise_for_status()
            data = response.json()
            # save the json in out-jsons/iso.json for debugging non-empty elements
            if data.get("elements"):
                print("nb elements:", len(data.get("elements", [])))
                with open(f"{out_json_path}/{iso}.json", "w", encoding="utf-8") as f:
                    json.dump(data, f)
            if overpass_server_idx >= 2: overpass_server_idx = 0 # The 2 first servers are the fastest, we prefer go back to them when we can
            return data
        except requests.RequestException as e:
            overpass_server_idx = (overpass_server_idx+1)%3
            if i == tries-1:
                print(f"Error fetching Overpass data for {iso}: {e}; no retries left, giving up.")
                raise
            else:
                print(f"Error fetching Overpass data for {iso}: {e}; trying again...({tries-i-1} retries left)")



def fetch_country_list():
    """Returns the list of ISO 3166-1 countries (alpha2 code and name)."""
    # We use the list from https://datahub.io/core/country-list
    url =  "https://datahub-next-new.vercel.app/core/country-list/_r/-/data.csv"
    r = requests.get(url)
    r.raise_for_status()
    countries = []
    for line in r.text.splitlines()[1:]:
        parts = line.split(",")
        if len(parts) >= 2:
            countries.append({"iso": parts[-1].strip().upper(), "name": parts[0].strip()})
    return countries

def fetch_data_from_iso(iso, out_json_path, skip_list):
    """Returns the list of OSM elements (ways + nodes) for a country given by its ISO 3166-1 alpha2 code."""
    
    # if iso in force_skip.txt, skip
    if iso in skip_list:
        print(f"Skipping {iso} as it's in force_skip.txt")
        return []
    
    # if out-jsons/iso.json exists, skip fetch
    if os.path.exists(f"{out_json_path}/{iso}.json"):
        print(f"Found existing {out_json_path}/{iso}.json, loading from file...")
        with open(f"{out_json_path}/{iso}.json", "r", encoding="utf-8") as f:
            data = json.loads(f.read())
    else:
        print(f"Fetching railways in {iso} from Overpass (may be long)...")
        data = overpass_fetch_country_ways(iso, out_json_path)
    elements = data.get("elements", [])
    print(f"Total elements fetched: {len(elements)} (ways + nodes). Processing...")
    # if elements is empty, add to force_skip.txt
    if not elements:
        with open("force_skip.txt", "a", encoding="utf-8") as f:
            f.write(f"{iso}\n")
        print(f"No elements found for {iso}, added to force_skip.txt to skip in future.")
    return elements

def csv_and_length_from_elements(elements, iso, min_speed=200):
    """Returns the CSV rows (list of dict) to write, and the total lengths (tracks, unique)."""
    total_tracks_len = 0.0   # sum of way lengths (counts each track, including duplicates)
    rows = []

    for e in tqdm(elements):
        if e.get("type") != "way":
            continue
        geom = e.get("geometry")
        if not geom or len(geom) < 2:
            continue
        coords = [(p["lon"], p["lat"]) for p in geom]
        way_len = geodesic_length_coords(coords)  # meters
        # parse maxspeed
        tags = e.get("tags", {})
        if tags.get("maxspeed"):
            maxs_raw = tags.get("maxspeed")
        elif tags.get("maxspeed:forward"):
            maxs_raw = tags.get("maxspeed:forward")
        maxs = parse_maxspeed(maxs_raw)
        name = tags.get("name") or tags.get("ref") or ""

        # only export if maxspeed exists and >= threshold
        if maxs is None or maxs < min_speed:
            continue

        total_tracks_len += way_len

        # add row to intermediate CSV
        rows.append({
            "way_id": e.get("id"),
            "name": name,
            "country": iso,
            "maxspeed_kmh": maxs,
            "length_m": round(way_len, 3),
            "length_km": round(way_len/1000.0, 6)
        })
    return rows, total_tracks_len

def process_speeds(rows, iso, country_name):
    """Returns a dict with speed statistics."""
    return_dict = {"iso": iso, "country": country_name, "200-224":0, "225-249":0, "250-274":0, "275-299":0, "300-324":0, "325-349":0, "350+":0}
    for r in rows:
        s = r["maxspeed_kmh"]
        if s >= 350:
            return_dict["350+"] += r["length_km"]
        elif s >= 325:
            return_dict["325-349"] += r["length_km"]
        elif s >= 300:
            return_dict["300-324"] += r["length_km"]
        elif s >= 275:
            return_dict["275-299"] += r["length_km"]
        elif s >= 250:
            return_dict["250-274"] += r["length_km"]
        elif s >= 225:
            return_dict["225-249"] += r["length_km"]
        elif s >= 200:
            return_dict["200-224"] += r["length_km"]
    return return_dict


def main():
    
    out_csv_path = "out-csvs"
    out_json_path = "out-jsons"
    os.makedirs(out_csv_path, exist_ok=True)
    os.makedirs(out_json_path, exist_ok=True)

    country_list = fetch_country_list()
    # country_list = [{"iso": "GB", "name": "United Kingdom"}]  # for quick test

    global_stats = []

    # read force_skip.txt if it exists
    skip_list = []
    if os.path.exists("force_skip.txt"):
        with open("force_skip.txt", "r", encoding="utf-8") as f:
            skip_list = [line.strip().upper() for line in f if line.strip()]

    for country in country_list:
        iso = country["iso"]
        name = country["name"]
        print(f"\n=== Processing country: {name} ({iso}) ===")

        # fetch data (or load from existing file)
        elements = fetch_data_from_iso(iso, out_json_path, skip_list)
        if not elements:
            print(f"No elements found for {iso}, skipping.")
            continue

        # process elements to get CSV rows and lengths
        rows, total_tracks_len = csv_and_length_from_elements(elements, iso)

        # write detailed CSV
        out_csv = f"{out_csv_path}/rails_highspeed_{iso.lower()}.csv"
        with open(out_csv, "w", newline="", encoding="utf-8") as f:
            fieldnames = ["way_id","name","country","maxspeed_kmh","length_m","length_km"]
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";", )
            writer.writeheader()
            for r in rows:
                writer.writerow(r)

        # process speeds
        stats = process_speeds(rows, iso, name)
        global_stats.append(stats)
        print(stats)

        print("Done.")
        print(f"SUM (tracks) = {total_tracks_len/1000.0:.3f} km")
        print(f"CSV written: {out_csv}")

    # write global CSV
    out_global_csv = f"rails_highspeed_all_countries.csv"
    with open(out_global_csv, "w", newline="", encoding="utf-8") as f:
        fieldnames = ["iso","country","200-224","225-249","250-274","275-299","300-324","325-349","350+"]
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for stats in global_stats:
            row = {
                "iso": stats["iso"],
                "country": stats["country"],
                "200-224": stats["200-224"],
                "225-249": stats["225-249"],
                "250-274": stats["250-274"],
                "275-299": stats["275-299"],
                "300-324": stats["300-324"],
                "325-349": stats["325-349"],
                "350+": stats["350+"]
            }
            writer.writerow(row)
    print(f"\n=== GLOBAL CSV written: {out_global_csv} ===")

if __name__ == "__main__":
    main()
