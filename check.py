import json
import os
import subprocess
import sys
import time
import requests

DATA_URL = "https://mosaic-plaza-aanbodapi.zig365.nl/api/v1/actueel-aanbod?limit=60&locale=en_GB&page=0&sort=%2BreactionData.aangepasteTotaleHuurprijs"
PLAZA_PAGE = "https://plaza.newnewnew.space/"
SEEN_FILE = "seen.json"
TOPIC = os.environ["NTFY_TOPIC"]

CHECK_EVERY_SECONDS = 60
RUN_FOR_SECONDS = 340 * 60  # about 5 h 40 min, then the next run takes over
MAX_ERRORS_IN_A_ROW = 10


def notify(title, message):
    # Sends one notification and checks that ntfy really accepted it.
    last_error = ""
    for attempt in range(4):
        try:
            r = requests.post(
                f"https://ntfy.sh/{TOPIC}",
                data=message.encode("utf-8"),
                headers={"Title": title, "Click": PLAZA_PAGE, "Priority": "high", "Tags": "house"},
                timeout=30,
            )
            if r.status_code == 200:
                print(f"Notification sent: {title}", flush=True)
                return True
            last_error = f"ntfy answered {r.status_code}: {r.text[:200]}"
        except requests.RequestException as e:
            last_error = str(e)
        print(f"Notification attempt {attempt + 1} failed: {last_error}", flush=True)
        time.sleep(5 * (attempt + 1))
    print(f"Could not send notification, will try again next minute: {last_error}", flush=True)
    return False


def find_listings(data):
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


def fetch_listings():
    r = requests.get(DATA_URL, headers={"User-Agent": "Mozilla/5.0 (personal listing alert)"}, timeout=30)
    r.raise_for_status()
    listings = find_listings(r.json())
    if not listings:
        raise ValueError("No listings found in the data. The site may have changed.")
    return listings


def save_and_push(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(sorted(seen), f, indent=1)
    try:
        subprocess.run(["git", "add", SEEN_FILE], check=True)
        if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode != 0:
            subprocess.run(["git", "commit", "-m", "Update seen listings"], check=True)
            subprocess.run(["git", "pull", "--rebase", "-X", "theirs"], check=True)
            subprocess.run(["git", "push"], check=True)
    except subprocess.CalledProcessError as e:
        # Not fatal: the list is still kept in memory for this run.
        print(f"Could not save seen.json to GitHub: {e}", flush=True)


def main():
    first_run = not os.path.exists(SEEN_FILE)
    seen = set()
    if not first_run:
        with open(SEEN_FILE) as f:
            seen = set(json.load(f))

    start = time.time()
    errors = 0

    while time.time() - start < RUN_FOR_SECONDS:
        try:
            listings = fetch_listings()
            delft = [i for i in listings if "delft" in json.dumps(i).lower()]
            new = [i for i in delft if listing_key(i) not in seen]

            if first_run:
                ok = notify("Plaza alert is set up", f"Watching {len(delft)} current Delft listings. You'll get a message for every new one.")
                if ok:
                    first_run = False
            elif len(new) == 1:
                ok = notify("New Plaza listing in Delft", address(new[0]) + "\nTap to open Plaza and apply now.")
            elif new:
                lines = "\n".join(f"- {address(i)}" for i in new)
                ok = notify(f"{len(new)} new Plaza listings in Delft", lines + "\nTap to open Plaza and apply now.")
            else:
                ok = True

            # Only mark listings as seen once the notification really went out.
            if ok and (new or not os.path.exists(SEEN_FILE)):
                seen |= {listing_key(i) for i in delft}
                save_and_push(seen)

            errors = 0
            print(time.strftime("%H:%M:%S"), f"Total: {len(listings)}, Delft: {len(delft)}, new: {len(new)}", flush=True)
            for i in new:
                print(f"  new: {listing_key(i)} {address(i)}", flush=True)
        except Exception as e:
            errors += 1
            print(time.strftime("%H:%M:%S"), f"Error ({errors} in a row): {e}", flush=True)
            if errors >= MAX_ERRORS_IN_A_ROW:
                sys.exit(1)

        time.sleep(CHECK_EVERY_SECONDS)


main()
