import os, csv
from datetime import datetime, timezone
from pathlib import Path
import requests
from dotenv import load_dotenv
import json  # store an “already seen” list as JSON

SEND_NO_NEWS_MESSAGE = True          # sends “No new sightings” if no new species sighted
NO_NEWS_TEXT = "No new sightings"
SEEN_PATH = "seen.json"              # this remembers what was already alerted


# load .env with this file and say what happened
ENV_PATH = Path(__file__).resolve().with_name(".env")
print("[env] Loading:", ENV_PATH, "exists:", ENV_PATH.exists())
load_dotenv(ENV_PATH, override=True)

# hardcoded fallbacks so script runs even if .env isn't read
EBIRD_TOKEN = os.getenv("EBIRD_TOKEN")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
WEBHOOK_LOG_URL = os.getenv("WEBHOOK_LOG_URL")
WATCHLIST_RAW = os.getenv("WATCHLIST", "")
WATCHLIST = [w.strip().lower() for w in WATCHLIST_RAW.split("|") if w.strip()]

print("[env] EBIRD_TOKEN present:", bool(EBIRD_TOKEN))
print("[env] SLACK_WEBHOOK_URL present:", bool(SLACK_WEBHOOK_URL))

# locations to track for birds - 15km radius
SITES = [
    {"id": "london", "name": "London Site", "lat": 51.44470675255037, "lon": -0.20651818603007366, "radius_km": 15},
]

CSV_PATH = "alerts.csv"
LOG_TO_CSV = False # don't log to local csv

def ebird_recent(lat, lon, dist_km=15, back_days=1):
    url = "https://api.ebird.org/v2/data/obs/geo/recent"
    headers = {"X-eBirdApiToken": EBIRD_TOKEN}
    params = {"lat": lat, "lng": lon, "dist": dist_km, "back": back_days}
    r = requests.get(url, headers=headers, params=params, timeout=20)
    r.raise_for_status()
    return r.json()

def match_watchlist(obs):
    name = (obs.get("comName") or "").lower()
    code = (obs.get("speciesCode") or "").lower()
    by_name = any(w in name for w in WATCHLIST) if WATCHLIST else False
    by_code = any(w == code for w in WATCHLIST) if WATCHLIST else False
    return by_name or by_code

def send_slack(text, blocks=None):
    try:
        payload = {"text": text}
        if blocks: payload["blocks"] = blocks
        r = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"[warn] Slack post failed: {e}")

def log_csv(row: dict):
    """Append one row to alerts.csv (only if LOG_TO_CSV is True)."""
    new = not Path(CSV_PATH).exists()
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["ts","siteId","siteName","comName","sciName","locName","obsDt","lat","lng"]
        )
        if new:
            w.writeheader()
        w.writerow(row)

def post_webhook_log(payload: dict):
    """Send one row to Google Sheet via Apps Script URL."""
    url = (WEBHOOK_LOG_URL or "").strip()
    if not url:
        print("[sheet] No WEBHOOK_LOG_URL set; not sending to Google Sheet.")
        return
    try:
        r = requests.post(url, json=payload, timeout=20)
        if r.status_code < 300:
            print("[sheet] Row sent to Google Sheet.")
        else:
            print(f"[sheet] Google Sheet returned {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"[sheet] Couldn’t reach Google Sheet webhook: {e}")

def load_seen() -> set:
    """Read seen.json. If it doesn't exist yet, return an empty set."""
    try:
        with open(SEEN_PATH, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()

def save_seen(seen: set):
    """Save our updated 'seen' list back to seen.json. Keep it short."""
    try:
        data = sorted(seen)
        if len(data) > 5000:          # keeps last 5000 keys
            data = data[-5000:]
        with open(SEEN_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"[warn] couldn't save seen cache: {e}")

def obs_key(site_id, o) -> str:
    """Make a unique ID for each sighting to remember it. If same key, we skip it"""
    return f"{site_id}|{o.get('speciesCode')}|{o.get('obsDt')}|{o.get('lat')}|{o.get('lng')}"


def run_once():
    total_new = 0
    seen = load_seen()

    print("[i] Started:", datetime.now(timezone.utc).isoformat())
    for site in SITES:
        try:
            obs = ebird_recent(site["lat"], site["lon"], site["radius_km"], back_days=3)
        except Exception as e:
            print(f"[warn] eBird fetch failed for {site['name']}: {e}")
            continue

        matches = [o for o in obs if match_watchlist(o)]
        print(f"[i] {site['name']}: {len(matches)} matches in last 3 days (radius {site['radius_km']}km)")

        for o in matches[:50]:
            key = obs_key(site["id"], o)
            if key in seen:
                continue

            # send Slack alert for a new sighting
            text = f":bird: *{o.get('comName')}* near *{site['name']}* — {o.get('locName','Unknown')} (obs {o.get('obsDt')})"
            map_link = f"https://www.google.com/maps?q={o.get('lat')},{o.get('lng')}"
            blocks = [
                {"type":"section","text":{"type":"mrkdwn","text":text}},
                {"type":"context","elements":[{"type":"mrkdwn","text":f"<{map_link}|Open map>"}]}
            ]
            send_slack(text, blocks=blocks)

            # build row for Google Sheet
            row = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "siteId": site["id"], "siteName": site["name"],
                "comName": o.get("comName"), "sciName": o.get("sciName"),
                "locName": o.get("locName"), "obsDt": o.get("obsDt"),
                "lat": o.get("lat"), "lng": o.get("lng")
            }
            if LOG_TO_CSV:
                log_csv(row)          # stays off unless you flip LOG_TO_CSV = True
            post_webhook_log(row)      # sends to Google Sheet

            seen.add(key)
            total_new += 1

    save_seen(seen)

    # If no new sightings, send this message
    if total_new == 0 and SEND_NO_NEWS_MESSAGE:
        try:
            send_slack(NO_NEWS_TEXT)
        except Exception as e:
            print(f"[warn] couldn't post 'no new sightings': {e}")

    print(f"[i] New alerts this run: {total_new}")


if __name__ == "__main__":
    # DO NOT exit, just warn if something is missing
    if not EBIRD_TOKEN or not SLACK_WEBHOOK_URL:
        print("[env] Warning: missing EBIRD_TOKEN or SLACK_WEBHOOK_URL — continuing with current values")
    run_once()

