import json
import os
import sys
import time
import requests

DATA_URL = "https://mosaic-plaza-aanbodapi.zig365.nl/api/v1/actueel-aanbod?limit=60&locale=en_GB&page=0&sort=%2BreactionData.aangepasteTotaleHuurprijs"
PLAZA_PAGE = "https://plaza.newnewnew.space/"
SEEN_FILE = "seen.json"
TOPIC = os.environ["NTFY_TOPIC"]


def notify(title, message):
    # Sends one notification and checks that ntfy really accepted it.
    # Tries up to 6 times (about 3 minutes in total) before giving up.
    last_error = ""
    for attempt in range(6):
        try:
            r = requests.post(
                f"https://ntfy.sh/{TOPIC}",
                data=message.encode("utf-8"),
                headers={"Title": title, "Click": PLAZA_PAGE, "Priority": "high", "Tags": "house"},
                timeout=30,
            )
            if r.status_code == 200:
                print(f"Notification sent: {title}")
                return True
            last_error = f"ntfy answered {r.status_code}: {r.text[:200]}"
        except requests.RequestException as e:
            last_error = str(e)
        print(f"Notification attempt {attempt + 1} failed: {last_error}")
        time.sleep(10 * (attempt + 1))
    print(f"GAVE UP sending notification: {last_error}")
    return False


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


def address(item):
    parts = []
    for k in ("street", "houseNumber", "houseNumberAddition", "postalcode"):
        if item.get(k):
            parts.append(str(item[k]))
    return " ".join(parts) if parts else f"Listing id {listing_key(item)}"


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
        ok = notify("Plaza alert is set up", f"Watching {len(delft)} current Delft listings. You'll get a message for every new one.")
    elif len(new) == 1:
        ok = notify("New Plaza listing in Delft", address(new[0]) + "\nTap to open Plaza and apply.")
    elif new:
        # Several new listings at once: ONE message that lists all of them,
        # so nothing gets lost in a burst of separate notifications.
        lines = "\n".join(f"- {address(i)}" for i in new)
        ok = notify(f"{len(new)} new Plaza listings in Delft", lines + "\nTap to open Plaza and apply.")
    else:
        ok = True

    print(f"Total listings: {len(listings)}, Delft: {len(delft)}, new: {len(new)}")
    for i in new:
        print(f"  new: {listing_key(i)} {address(i)}")

    if not ok:
        # Do NOT mark these listings as seen, so the next run tries again,
        # and fail the run so GitHub emails you.
        sys.exit(1)

    seen |= {listing_key(i) for i in delft}
    with open(SEEN_FILE, "w") as f:
        json.dump(sorted(seen), f, indent=1)


main()
