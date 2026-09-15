# HSR-get-stats-openstreetmap

A python script to get data from 200+ km/h rail tracks around the world, using data from openstreetmap via overpass API

## Installation

Clone the repository and install the required Python packages:

```bash
git clone <repository-url>
```

```bash
pip install -r requirements.txt
```

## Usage

Run the script with:

```bash
python get-hsr-v3.py
```

The script will query OpenStreetMap through the Overpass API and process the countries one by one.

> **Note:** Processing all countries can take a while depending on the amount of data and Overpass server availability.

## Output

The script generates the following files and folders:

* `rails_highspeed_all_countries.csv` — aggregated results for all countries (some older versions are included in the repo for the sake of memory)
* `out-csvs/` — detailed CSV results for each country
* `out-jsons/` — raw Overpass API responses, reused when available
* `force_skip.txt` — countries to skip during processing

## Notes

This script aims to gather statistics independant from the UIC on high speed rail network. I made a [reddit post](https://www.reddit.com/r/highspeedrail/comments/1o7a29n/highspeed_rail_network_by_speed_by_country_v2/) with it.

Instead of using official data from the UIC, this script checks for data from openstreetmap (what you can see on [openrailwaymap](https://www.openrailwaymap.org/)).

Why using this instead of the official UIC data:

**Upsides**:
- It no longer relies on UIC membership, so Uzbekistan is included.
- There is no more inconsistencies on speed. This included all railways with 200+km/h max speed.
- The maximum speed is counted on every track section, and not on the whole line (so if a long line has a small section with high speed, only the small section will be counted)

**Downsides I see**:
- The UIC is often considered the authority on this matter. I don't use their data nor their definition of high-speed rail here
- The lengths gathered by the scripts are ~2 times more important than on every other stats you can find. Most of the lines have 2 tracks and tracks are counted independently on openstreetmap.  
It is possible to halve the numbers to get comparable scores, only there can exist in theory some portion of rail with 4 tracks that would be counted twice (this is still negligeable on the data and anyways, these portions have twice the capacity in function the same as 2 HSR line next to each other imo they can be coubted twice)
- Some small testing lines are included, it's not only passenger rail