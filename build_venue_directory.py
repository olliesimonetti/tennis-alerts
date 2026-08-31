#!/usr/bin/env python3
"""One-off (re-runnable) crawl of LTA's public 'Book a tennis court' search to
build a directory of all discoverable venues across Great Britain.

Not part of the recurring poller — run manually / occasionally to refresh
venues_directory.json, which feeds the court dropdown on the preferences site.

Approach: LTA's search results page (https://www.lta.org.uk/play/book-a-tennis-court/)
is server-rendered HTML and radius-limited (remote coordinates return zero
results), so we query from a list of GB towns/cities and page through results
(?p=2, p=3, ...) until a page comes back empty. Venues found from overlapping
searches are deduped by their venue ID.
"""
import concurrent.futures
import json
import re
import time
import urllib.request
from pathlib import Path

OUT_PATH = Path(__file__).parent / "venues_directory.json"
BASE_URL = "https://www.lta.org.uk/play/book-a-tennis-court/"
LINK_RE = re.compile(
    r'book-a-tennis-court/courts/([a-z0-9-]+)_([a-f0-9-]{36})'
)
NAME_RE = re.compile(r'<h3[^>]*>\s*([^<]+?)\s*</h3>')

# Town/city centroids spanning England, Scotland and Wales, weighted toward
# population centres (where LTA park/club courts concentrate). Best-effort
# coverage, not an exhaustive geographic grid -- rerun with more points added
# below if you find a gap.
TOWNS = [
    ("London-Central", 51.5074, -0.1278), ("London-East", 51.5450, -0.0350),
    ("London-North", 51.5900, -0.1100), ("London-South", 51.4400, -0.1000),
    ("London-West", 51.4975, -0.2200), ("Croydon", 51.3762, -0.0982),
    ("Bromley", 51.4039, 0.0198), ("Watford", 51.6565, -0.3903),
    ("Reading", 51.4543, -0.9781), ("Guildford", 51.2362, -0.5704),
    ("Brighton", 50.8225, -0.1372), ("Southampton", 50.9097, -1.4044),
    ("Portsmouth", 50.8198, -1.0880), ("Oxford", 51.7520, -1.2577),
    ("Cambridge", 52.2053, 0.1218), ("Norwich", 52.6309, 1.2974),
    ("Ipswich", 52.0567, 1.1482), ("Colchester", 51.8959, 0.8919),
    ("Milton Keynes", 52.0406, -0.7594), ("Luton", 51.8787, -0.4200),
    ("Bristol", 51.4545, -2.5879), ("Bath", 51.3811, -2.3590),
    ("Exeter", 50.7184, -3.5339), ("Plymouth", 50.3755, -4.1427),
    ("Truro", 50.2632, -5.0510), ("Bournemouth", 50.7192, -1.8808),
    ("Swindon", 51.5558, -1.7797), ("Gloucester", 51.8642, -2.2380),
    ("Cheltenham", 51.8994, -2.0783), ("Worcester", 52.1936, -2.2216),
    ("Birmingham", 52.4862, -1.8904), ("Coventry", 52.4068, -1.5197),
    ("Leicester", 52.6369, -1.1398), ("Nottingham", 52.9548, -1.1581),
    ("Derby", 52.9225, -1.4746), ("Stoke-on-Trent", 53.0027, -2.1794),
    ("Wolverhampton", 52.5870, -2.1288), ("Northampton", 52.2405, -0.9027),
    ("Leamington Spa", 52.2864, -1.5350), ("Lincoln", 53.2307, -0.5406),
    ("Sheffield", 53.3811, -1.4701), ("Leeds", 53.8008, -1.5491),
    ("Bradford", 53.7960, -1.7594), ("York", 53.9600, -1.0873),
    ("Hull", 53.7676, -0.3274), ("Wakefield", 53.6833, -1.4977),
    ("Harrogate", 53.9919, -1.5378), ("Manchester", 53.4808, -2.2426),
    ("Liverpool", 53.4084, -2.9916), ("Preston", 53.7632, -2.7031),
    ("Blackpool", 53.8175, -3.0357), ("Warrington", 53.3900, -2.5970),
    ("Chester", 53.1934, -2.8931), ("Newcastle", 54.9783, -1.6178),
    ("Sunderland", 54.9069, -1.3838), ("Middlesbrough", 54.5742, -1.2350),
    ("Durham", 54.7761, -1.5733), ("Carlisle", 54.8951, -2.9382),
    ("Cardiff", 51.4816, -3.1791), ("Swansea", 51.6214, -3.9436),
    ("Newport", 51.5842, -2.9977), ("Wrexham", 53.0478, -2.9916),
    ("Bangor", 53.2280, -4.1293), ("Aberystwyth", 52.4153, -4.0829),
    ("Edinburgh", 55.9533, -3.1883), ("Glasgow", 55.8642, -4.2518),
    ("Aberdeen", 57.1497, -2.0943), ("Dundee", 56.4620, -2.9707),
    ("Inverness", 57.4778, -4.2247), ("Perth", 56.3950, -3.4308),
    ("Stirling", 56.1165, -3.9369), ("Ayr", 55.4586, -4.6292),
    ("Kilmarnock", 55.6111, -4.4956), ("Falkirk", 56.0019, -3.7839),
    ("Paisley", 55.8456, -4.4239), ("Dumfries", 55.0700, -3.6050),
    ("St Andrews", 56.3398, -2.7967), ("Kent-Maidstone", 51.2704, 0.5227),
    ("Canterbury", 51.2802, 1.0789), ("Tunbridge Wells", 51.1324, 0.2637),
    ("Surrey-Woking", 51.3168, -0.5600), ("Surrey-Epsom", 51.3336, -0.2679),
    ("Essex-Chelmsford", 51.7356, 0.4685), ("Essex-Basildon", 51.5761, 0.4887),
    ("Herts-St Albans", 51.7520, -0.3360), ("Herts-Hemel Hempstead", 51.7526, -0.4685),
    ("Sussex-Eastbourne", 50.7687, 0.2900), ("Sussex-Worthing", 50.8180, -0.3720),
    ("Kent-Dover", 51.1279, 1.3134), ("Kent-Margate", 51.3813, 1.3862),
    ("Berks-Slough", 51.5105, -0.5950), ("Bucks-Aylesbury", 51.8156, -0.8087),
    ("Beds-Bedford", 52.1359, -0.4666), ("Kings Lynn", 52.7527, 0.4004),
    ("Peterborough", 52.5695, -0.2405), ("Chesterfield", 53.2350, -1.4210),
    ("Mansfield", 53.1472, -1.1988), ("Telford", 52.6784, -2.4453),
    ("Shrewsbury", 52.7069, -2.7530), ("Hereford", 52.0567, -2.7160),
    ("Bolton", 53.5769, -2.4283), ("Wigan", 53.5450, -2.6318),
    ("Stockport", 53.4083, -2.1494), ("Oldham", 53.5409, -2.1114),
    ("Rochdale", 53.6097, -2.1561), ("Blackburn", 53.7486, -2.4823),
    ("Barnsley", 53.5526, -1.4797), ("Doncaster", 53.5228, -1.1288),
    ("Rotherham", 53.4302, -1.3567), ("Scarborough", 54.2807, -0.4013),
    ("Lancaster", 54.0466, -2.8007), ("Kendal", 54.3287, -2.7443),
]


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


def crawl_town(name: str, lat: float, lon: float) -> list[dict]:
    found = []
    for page in range(1, 8):  # safety cap; loop breaks earlier in practice
        url = f"{BASE_URL}?latitude={lat}&longitude={lon}&p={page}"
        try:
            html = fetch(url)
        except Exception as exc:
            print(f"[error] {name} p{page}: {exc}")
            break
        matches = LINK_RE.findall(html)
        if not matches:
            break
        for slug, vid in matches:
            found.append({"id": vid, "slug": slug})
        if len(set(matches)) < 10:
            break
        time.sleep(0.1)
    return found


def main() -> None:
    all_venues: dict[str, dict] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(crawl_town, name, lat, lon): name
            for name, lat, lon in TOWNS
        }
        for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
            name = futures[future]
            try:
                results = future.result()
            except Exception as exc:
                print(f"[error] {name}: {exc}")
                continue
            for v in results:
                all_venues.setdefault(v["id"], v)
            print(f"[{i}/{len(TOWNS)}] {name}: {len(results)} results, {len(all_venues)} unique so far")

    directory = []
    for vid, v in sorted(all_venues.items(), key=lambda kv: kv[1]["slug"]):
        display_name = v["slug"].replace("-", " ").title()
        directory.append({"id": vid, "slug": v["slug"], "name": display_name})

    OUT_PATH.write_text(json.dumps(directory, indent=2))
    print(f"\nWrote {len(directory)} unique venues to {OUT_PATH}")


if __name__ == "__main__":
    main()
