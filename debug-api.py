"""
Dumps the raw API response for the first 2 games so we can see
exactly what genre/category fields Microsoft returns.
"""
import json, requests

HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
SIGL_URL    = "https://catalog.gamepass.com/sigls/v2"
CATALOG_URL = "https://displaycatalog.mp.microsoft.com/v7.0/products"
SIGL_ID     = "fdd9e2a7-0fee-49f6-ad69-4354098401ff"

# Get first 2 IDs
r = requests.get(SIGL_URL, params={"id": SIGL_ID, "language": "en-us", "market": "US"}, headers=HEADERS, timeout=15)
ids = [e["id"] for e in r.json() if "id" in e and e["id"] != SIGL_ID][:2]
print("IDs:", ids)

# Fetch their full product data
r = requests.get(CATALOG_URL, params={"bigIds": ",".join(ids), "market": "US", "languages": "en-us"}, headers=HEADERS, timeout=20)
products = r.json().get("Products", [])

for p in products:
    props   = p.get("LocalizedProperties", [{}])[0]
    attribs = p.get("Properties", {})
    print("\n" + "="*60)
    print("Title:", props.get("ProductTitle"))
    print("\n--- Properties keys ---")
    print(list(attribs.keys()))
    print("\n--- Category:", attribs.get("Category"))
    print("--- Categories:", attribs.get("Categories"))
    print("--- SubcategoryName:", attribs.get("SubcategoryName"))
    print("--- Genres:", attribs.get("Genres"))
    print("--- PackageFamilyName:", attribs.get("PackageFamilyName"))
    print("\n--- LocalizedProperties keys ---")
    print(list(props.keys()))
    print("--- DeveloperName:", props.get("DeveloperName"))
    print("--- PublisherName:", props.get("PublisherName"))
    print("\n--- Images (first 5) ---")
    for img in props.get("Images", [])[:5]:
        print(f"  Purpose={img.get('ImagePurpose')}, Uri={img.get('Uri','')[:80]}")
    print("\n--- Attributes (full) ---")
    print(json.dumps(attribs, indent=2)[:2000])
