"""
PC Game Pass → games.js Generator
-----------------------------------
Fetches the live PC Game Pass catalog directly from Microsoft's public APIs
(no API key or login required) and regenerates games.js + downloads cover art.

HOW IT WORKS
------------
Step 1 — Fetch PC Game Pass game IDs from the Xbox sigl catalog endpoint
Step 2 — Batch-fetch full product details (title, genres, images) from the
          Microsoft Display Catalog API
Step 3 — Download the best available cover/portrait image for each game
Step 4 — Write a fresh games.js from the live data

USAGE
-----
    pip install requests
    python fetch-gamepass.py

OPTIONS
-------
    --no-images     Skip image downloads (just regenerate games.js)
    --force-images  Re-download images even if they already exist
    --market US     Change store market/region (default: US)
    --lang en-us    Change language (default: en-us)
"""

import os
import re
import sys
import time
import json
import argparse
import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGES_DIR = os.path.join(SCRIPT_DIR, "images")
GAMES_JS   = os.path.join(SCRIPT_DIR, "games.js")

# ── PC Game Pass catalog ID (this is Microsoft's public identifier)
PC_GAMEPASS_SIGL_ID = "fdd9e2a7-0fee-49f6-ad69-4354098401ff"

SIGL_URL    = "https://catalog.gamepass.com/sigls/v2"
CATALOG_URL = "https://displaycatalog.mp.microsoft.com/v7.0/products"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

# Microsoft image CDN base
IMAGE_CDN = "https://store-images.s-microsoft.com/image/apps."


# ─── Step 1: Get all PC Game Pass product IDs ────────────────────────────────
def fetch_gamepass_ids(market, lang):
    print("Fetching PC Game Pass catalog IDs …")
    r = requests.get(
        SIGL_URL,
        params={
            "id":       PC_GAMEPASS_SIGL_ID,
            "language": lang,
            "market":   market,
        },
        headers=HEADERS,
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()

    # Response is a list — first item is the sigl metadata, rest are game entries
    ids = [entry["id"] for entry in data if "id" in entry and entry["id"] != PC_GAMEPASS_SIGL_ID]
    print(f"  Found {len(ids)} product IDs.\n")
    return ids


# ─── Step 2: Batch-fetch product details ─────────────────────────────────────
def fetch_products(ids, market, lang, batch_size=20):
    print(f"Fetching product details in batches of {batch_size} …")
    products = []

    for i in range(0, len(ids), batch_size):
        batch = ids[i : i + batch_size]
        try:
            r = requests.get(
                CATALOG_URL,
                params={
                    "bigIds":    ",".join(batch),
                    "market":    market,
                    "languages": lang,
                    "MS-CV":     "DGU1mcuYo0WMMp+F.1",
                },
                headers=HEADERS,
                timeout=20,
            )
            r.raise_for_status()
            batch_products = r.json().get("Products", [])
            products.extend(batch_products)
            print(f"  Batch {i // batch_size + 1}: got {len(batch_products)} products")
            time.sleep(0.3)
        except Exception as e:
            print(f"  Batch {i // batch_size + 1}: ERROR — {e}")

    print(f"\nTotal products fetched: {len(products)}\n")
    return products


# ─── Step 3: Extract useful fields from a product entry ──────────────────────
def extract_game(product):
    try:
        props      = product.get("LocalizedProperties", [{}])[0]
        attribs    = product.get("MarketProperties",    [{}])[0]
        attributes = product.get("Properties", {})
        platforms  = product.get("PlatformProperties", [])

        title = props.get("ProductTitle", "").strip()
        if not title:
            return None

        # Slug: lowercase title, keep alphanumeric and hyphens
        slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')

        description = props.get("ShortDescription", "") or props.get("ProductDescription", "")
        description = description.strip().replace('\n', ' ')[:200]

        developer = props.get("DeveloperName", "").strip() or props.get("PublisherName", "").strip() or "Unknown"

        # Release year
        release = attribs.get("OriginalReleaseDate", "") or attributes.get("ReleaseDate", "")
        year = int(release[:4]) if release and release[:4].isdigit() else 0

        # Primary genre from Categories list (what the API actually provides)
        raw_genres = [c for c in attributes.get("Categories", []) if c and c != "Games"]
        if not raw_genres and attributes.get("Category"):
            raw_genres = [attributes["Category"]]

        genres = list(dict.fromkeys(raw_genres)) or ["Action"]

        # Player modes go into a separate field, not genres
        PLAYER_MAP = {
            "SinglePlayer":                 "Single Player",
            "XblOnlineMultiPlayer":         "Online Multiplayer",
            "XblLocalMultiPlayer":          "Local Multiplayer",
            "XblOnlineCoop":                "Online Co-op",
            "XblLocalCoop":                 "Local Co-op",
            "XblCrossPlatformMultiPlayer":  "Online Multiplayer",
        }
        players = []
        for attr in attributes.get("Attributes", []):
            tag = PLAYER_MAP.get(attr.get("Name", ""))
            if tag and tag not in players:
                players.append(tag)

        # Best portrait/cover image — use full URI directly
        image_url = None
        image_type_priority = ["Poster", "BoxArt", "SuperHeroArt", "Logo", "Tile", "Screenshot"]
        all_images = props.get("Images", [])

        def img_priority(img):
            t = img.get("ImagePurpose", "")
            try:
                return image_type_priority.index(t)
            except ValueError:
                return 99

        sorted_images = sorted(all_images, key=img_priority)
        for img in sorted_images:
            uri = img.get("Uri", "")
            if uri:
                # Ensure the URI has a scheme
                if uri.startswith("//"):
                    uri = "https:" + uri
                image_url = uri
                break

        product_id = product.get("ProductId", slug)

        return {
            "id":          slug,
            "productId":   product_id,
            "title":       title,
            "image":       f"images/{slug}.jpg",
            "genres":      genres,
            "players":     players,
            "description": description,
            "year":        year,
            "developer":   developer,
            "imageUrl":    image_url,
        }

    except Exception as e:
        return None


# ─── Step 4: Download cover image ────────────────────────────────────────────
def download_image(image_url, dest, width=600):
    if not image_url:
        return False
    # Append size params to Microsoft's CDN URL
    url = f"{image_url}?q=90&w={width}&mode=scale"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20, stream=True)
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        return True
    except Exception as e:
        return False


# ─── Step 5: Write games.js ───────────────────────────────────────────────────
def write_games_js(games, path):
    print(f"\nWriting {path} …")

    lines = [
        "// PC Game Pass library — auto-generated by fetch-gamepass.py",
        "// Do not edit by hand; re-run the script to refresh.",
        "",
        "const GAMES = [",
    ]

    for g in games:
        # Use json.dumps for safe escaping of all special characters
        genres_str  = ", ".join(json.dumps(x) for x in g["genres"])
        players_str = ", ".join(json.dumps(x) for x in g["players"])
        lines.append("  {")
        lines.append(f'    id: {json.dumps(g["id"])},')
        lines.append(f'    title: {json.dumps(g["title"])},')
        lines.append(f'    image: {json.dumps(g["image"])},')
        lines.append(f'    genres: [{genres_str}],')
        lines.append(f'    players: [{players_str}],')
        lines.append(f'    description: {json.dumps(g["description"])},')
        lines.append(f'    year: {g["year"]},')
        lines.append(f'    developer: {json.dumps(g["developer"])}')
        lines.append("  },")

    lines.append("];")
    lines.append("")
    lines.append("// Derive all unique genres and player modes for filter chips")
    lines.append("const ALL_GENRES  = [...new Set(GAMES.flatMap(g => g.genres))].sort();")
    lines.append("const ALL_PLAYERS = [...new Set(GAMES.flatMap(g => g.players))].sort();")
    lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"  Wrote {len(games)} games to games.js")


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-images",     action="store_true", help="Skip image downloads")
    parser.add_argument("--force-images",  action="store_true", help="Re-download existing images")
    parser.add_argument("--market",        default="US",        help="Store market (default: US)")
    parser.add_argument("--lang",          default="en-us",     help="Language (default: en-us)")
    args = parser.parse_args()

    os.makedirs(IMAGES_DIR, exist_ok=True)

    # 1. Get IDs
    ids = fetch_gamepass_ids(args.market, args.lang)
    if not ids:
        print("ERROR: No IDs returned. The API endpoint may have changed.")
        sys.exit(1)

    # 2. Get product details
    products = fetch_products(ids, args.market, args.lang)

    # 3. Extract game data
    games = []
    seen_ids = set()
    for p in products:
        g = extract_game(p)
        if not g:
            continue
        # Deduplicate by slug
        if g["id"] in seen_ids:
            # Append product ID suffix to make unique
            g["id"] = f"{g['id']}-{g['productId'].lower()}"
        seen_ids.add(g["id"])
        games.append(g)

    # Sort A-Z
    games.sort(key=lambda g: g["title"].lower())

    print(f"Extracted {len(games)} games after deduplication.\n")

    # 4. Download images
    if not args.no_images:
        print("Downloading cover images …")
        img_ok = img_skip = img_fail = 0
        for g in games:
            dest = os.path.join(IMAGES_DIR, f"{g['id']}.jpg")
            if os.path.exists(dest) and not args.force_images:
                img_skip += 1
                continue
            if download_image(g.get("imageUrl"), dest):
                print(f"  OK    {g['title']}")
                img_ok += 1
            else:
                print(f"  MISS  {g['title']}")
                img_fail += 1
            time.sleep(0.1)
        print(f"\nImages: {img_ok} downloaded, {img_skip} skipped, {img_fail} failed.\n")

    # 5. Write games.js
    write_games_js(games, GAMES_JS)

    print("\nAll done! Open index.html in your browser.")


if __name__ == "__main__":
    main()
