"""
Xbox Game Pass Cover Art Downloader
------------------------------------
Reads game IDs and titles from games.js, then fetches cover art from the
IGDB API (powered by Twitch) and saves JPGs to the images/ folder.

SETUP
-----
1. Create a free Twitch developer account at https://dev.twitch.tv/
2. Create an Application → get a Client ID and Client Secret
3. Set the two variables below (or use environment variables)
4. Install requests:  pip install requests
5. Run:               python download-images.py

NOTES
-----
- Existing images are skipped unless you pass --force
- Games where no cover is found will show placeholder.svg in the site
- IGDB rate-limits to ~4 requests/second; a small delay is included
"""

import os
import re
import sys
import time
import argparse
import requests

# ── Credentials ──────────────────────────────────────────────────────────────
CLIENT_ID     = os.environ.get("IGDB_CLIENT_ID",     "YOUR_CLIENT_ID_HERE")
CLIENT_SECRET = os.environ.get("IGDB_CLIENT_SECRET", "YOUR_CLIENT_SECRET_HERE")

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
GAMES_JS    = os.path.join(SCRIPT_DIR, "games.js")
IMAGES_DIR  = os.path.join(SCRIPT_DIR, "images")


# ── Parse games.js to extract {id: title} pairs ──────────────────────────────
def parse_games_js(path):
    with open(path, encoding="utf-8") as f:
        src = f.read()

    # Match each game object block
    games = {}
    blocks = re.findall(r'\{[^{}]+\}', src, re.DOTALL)
    for block in blocks:
        id_m    = re.search(r'id\s*:\s*"([^"]+)"', block)
        title_m = re.search(r'title\s*:\s*"([^"]+)"', block)
        if id_m and title_m:
            games[id_m.group(1)] = title_m.group(1)
    return games


# ── IGDB helpers ─────────────────────────────────────────────────────────────
def get_token():
    r = requests.post(
        "https://id.twitch.tv/oauth2/token",
        params={
            "client_id":     CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type":    "client_credentials",
        },
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def search_game(title, token):
    r = requests.post(
        "https://api.igdb.com/v4/games",
        headers={"Client-ID": CLIENT_ID, "Authorization": f"Bearer {token}"},
        data=f'search "{title}"; fields name,cover; limit 1;',
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    return data[0] if data else None


def get_cover_url(cover_id, token):
    r = requests.post(
        "https://api.igdb.com/v4/covers",
        headers={"Client-ID": CLIENT_ID, "Authorization": f"Bearer {token}"},
        data=f"fields image_id; where id = {cover_id};",
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    if not data:
        return None
    # t_cover_big_2x → ~528×748 (2:3 ratio, good quality)
    return f"https://images.igdb.com/igdb/image/upload/t_cover_big_2x/{data[0]['image_id']}.jpg"


def download_file(url, dest):
    r = requests.get(url, timeout=20, stream=True)
    r.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in r.iter_content(8192):
            f.write(chunk)


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Download Game Pass cover art from IGDB.")
    parser.add_argument("--force", action="store_true", help="Re-download existing images")
    args = parser.parse_args()

    if CLIENT_ID == "YOUR_CLIENT_ID_HERE":
        print("ERROR: Set IGDB_CLIENT_ID and IGDB_CLIENT_SECRET.")
        print("       Edit the top of this script or set environment variables.")
        sys.exit(1)

    os.makedirs(IMAGES_DIR, exist_ok=True)

    print(f"Parsing {GAMES_JS} …")
    games = parse_games_js(GAMES_JS)
    print(f"Found {len(games)} games.\n")

    print("Authenticating with Twitch …")
    token = get_token()
    print("OK\n")

    ok = skipped = failed = 0

    for slug, title in games.items():
        dest = os.path.join(IMAGES_DIR, f"{slug}.jpg")

        if os.path.exists(dest) and not args.force:
            print(f"  SKIP  {title}")
            skipped += 1
            continue

        try:
            game = search_game(title, token)
            if not game or "cover" not in game:
                print(f"  MISS  {title}  (no cover on IGDB)")
                failed += 1
                continue

            url = get_cover_url(game["cover"], token)
            if not url:
                print(f"  MISS  {title}  (cover URL unavailable)")
                failed += 1
                continue

            download_file(url, dest)
            print(f"  OK    {title}")
            ok += 1
            time.sleep(0.27)   # stay within ~4 req/s rate limit

        except Exception as exc:
            print(f"  ERR   {title}  ({exc})")
            failed += 1

    print(f"\nDone — {ok} downloaded, {skipped} skipped, {failed} failed.")
    if failed:
        print("Games without images will show placeholder.svg in the browser.")


if __name__ == "__main__":
    main()
