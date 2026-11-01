import json
import os
import sys
import requests

DATA_URL = "https://mosaic-plaza-aanbodapi.zig365.nl/api/v1/actueel-aanbod?limit=60&locale=en_GB&page=0&sort=%2BreactionData.aangepasteTotaleHuurprijs"
PLAZA_PAGE = "https://plaza.newnewnew.space/"
SEEN_FILE = "seen.json"
TOPIC = os.environ["NTFY_TOPIC"]


def notify(title, message):
    requests.post(
        f"https://ntfy.sh/{TOPIC}",
        data=message.encode("utf-8"),
        headers={"Title": title, "Click": PLAZA_PAGE, "Priority": "high"},
        timeout=30,
    )


def find_listings(data):
    # Finds the biggest list of items in the data, which is the list of listings
    best = []

    def walk(x):
        nonlocal best
        if isinstance(x, list):
            items = [i for i in x if isinstance(i, dict)]
            if len(items) > len(best):
                best = items
            for i in x:
                walk(i)
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)

    walk(data)
    return best


def listing_key(item):
    return str(item.get("id") or hash(json.dumps(item, sort_keys=True)))


def describe(item):
    parts = []
    for k in ("street", "houseNumber", "houseNumberAddition", "postalcode"):
        if item.get(k):
            parts.append(str(item[k]))
    text = " ".join(parts) if parts else f"Listing id {listing_key(item)}"
    return text + "\nTap to open Plaza and apply."


def main():
    r = requests.get(DATA_URL, headers={"User-Agent": "Mozilla/5.0 (personal listing alert)"}, timeout=30)
    r.raise_for_status()
    listings = find_listings(r.json())
    if not listings:
        print("No listings found in the data. The site may have changed.")
        sys.exit(1)

    delft = [i for i in listings if "delft" in json.dumps(i).lower()]

    first_run = not os.path.exists(SEEN_FILE)
    seen = set()
    if not first_run:
        with open(SEEN_FILE) as f:
            seen = set(json.load(f))

    new = [i for i in delft if listing_key(i) not in seen]

    if first_run:
        notify("Plaza alert is set up", f"Watching {len(delft)} current Delft listings. You'll get a message for every new one.")
    else:
        for item in new:
            notify("New Plaza listing in Delft", describe(item))

    seen |= {listing_key(i) for i in delft}
    with open(SEEN_FILE, "w") as f:
        json.dump(sorted(seen), f, indent=1)

    print(f"Total listings: {len(listings)}, Delft: {len(delft)}, new: {len(new)}")


main()
