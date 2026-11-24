"""Real PJM queue data: parse PJM's public PlanningQueues.xml (pjm.com/pub/planning/downloads/xml/PlanningQueues.xml)
into a clean table of generation interconnection requests and compute the statistics used in the paper.
Outputs: data/pjm_generation_requests.csv, results/pjm_queue_stats.json"""
import collections, csv, datetime as dt, json, pathlib, re, statistics as stx
import xml.etree.ElementTree as ET

HERE = pathlib.Path(__file__).parent
ROOT = HERE
SRC = HERE / "data" / "raw" / "PlanningQueues.xml"


def num(x):
    try:
        return float(x)
    except Exception:
        return None


def date(x):
    try:
        return dt.datetime.strptime(x, "%m/%d/%Y").date()
    except Exception:
        return None


def window(pn):
    m = re.match(r"([A-Z]{1,2})(\d)", pn)
    return m.group(1) + m.group(2) if m else None


def fuel_class(f):
    f = f.lower()
    if "solar" in f and "storage" in f:
        return "solar+storage"
    for k in ("offshore wind", "solar", "storage", "wind", "natural gas", "nuclear", "hydro", "coal"):
        if k in f:
            return k
    return "other" if f else "unknown"


rows = [{c.tag: (c.text or "").strip() for c in p} for p in ET.parse(SRC).getroot()]
gen = []
for r in rows:
    if r["ProjectType"] != "Generation Interconnection":
        continue
    mw = num(r["MaximumFacilityOutput"]) or num(r["MWEnergy"])
    gen.append(dict(project=r["ProjectNumber"], window=window(r["ProjectNumber"]), status=r["Status"], state=r["State"],
                    county=r["County"], to=r["TransmissionOwner"], mw=mw, fuel=r["Fuel"], fuel_class=fuel_class(r["Fuel"]),
                    submitted=r["SubmittedDate"], withdrawn=r["WithdrawalDate"], in_service=r["ActualInServiceDate"]))
with open(HERE / "data" / "pjm_generation_requests.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(gen[0])); w.writeheader(); w.writerows(gen)

S = {"source": "PJM PlanningQueues.xml (public), downloaded 2026-11-24", "n_all_rows": len(rows), "n_generation_requests": len(gen)}
S["status_counts"] = dict(collections.Counter(g["status"] for g in gen).most_common())
done = ("In Service", "Partially in Service - Under Construction")
gone = ("Withdrawn", "Retracted", "Annulled", "Canceled", "Deactivated")

# completion and withdrawal for requests submitted 2008-2017 (old enough to have resolved)
old = [g for g in gen if (d := date(g["submitted"])) and 2008 <= d.year <= 2017 and g["mw"]]
S["submitted_2008_2017"] = dict(
    n=len(old), mw=sum(g["mw"] for g in old),
    share_requests_in_service=sum(g["status"] in done for g in old) / len(old),
    share_mw_in_service=sum(g["mw"] for g in old if g["status"] in done) / sum(g["mw"] for g in old),
    share_requests_withdrawn=sum(g["status"] in gone for g in old) / len(old))

# time from submission to in-service, by submission year
yrs = collections.defaultdict(list)
for g in gen:
    a, b = date(g["submitted"]), date(g["in_service"])
    if a and b and b >= a:
        yrs[a.year].append((b - a).days / 365.25)
S["years_to_in_service_median_by_submit_year"] = {y: round(stx.median(v), 2) for y, v in sorted(yrs.items()) if len(v) >= 10}

# active queue
act = [g for g in gen if g["status"] == "Active" and g["mw"]]
S["active"] = dict(n=len(act), gw=sum(g["mw"] for g in act) / 1000,
                   by_fuel_gw={k: round(sum(g["mw"] for g in act if g["fuel_class"] == k) / 1000, 2)
                               for k in sorted({g["fuel_class"] for g in act})},
                   by_window_n=dict(collections.Counter(g["window"] for g in act).most_common()))
mws = sorted(g["mw"] for g in act)
q = lambda p: mws[min(len(mws) - 1, int(p * len(mws)))]
S["active"]["mw_quantiles"] = {p: q(p) for p in (0.1, 0.25, 0.5, 0.75, 0.9, 0.99)}
S["active"]["mw_median_by_fuel"] = {k: stx.median([g["mw"] for g in act if g["fuel_class"] == k])
                                     for k in sorted({g["fuel_class"] for g in act}) if sum(g["fuel_class"] == k for g in act) >= 10}

# spatial clustering: how many active requests share a county with others (same TO)
key = lambda g: (g["state"], g["county"], g["to"])
cnt = collections.Counter(key(g) for g in act if g["county"] and g["county"] != "N/A")
loc = [g for g in act if g["county"] and g["county"] != "N/A"]
S["active"]["clustering"] = dict(
    n_counties=len(cnt),
    share_requests_sharing_county_with_ge_2_others=sum(cnt[key(g)] >= 3 for g in loc) / len(loc),
    share_requests_sharing_county_with_ge_5_others=sum(cnt[key(g)] >= 6 for g in loc) / len(loc),
    share_mw_in_counties_with_ge_5_requests=sum(g["mw"] for g in loc if cnt[key(g)] >= 5) / sum(g["mw"] for g in loc),
    top_counties=[dict(state=k[0], county=k[1], to=k[2], n=n, gw=round(sum(g["mw"] for g in loc if key(g) == k) / 1000, 2))
                  for k, n in cnt.most_common(10)])
(ROOT / "results").mkdir(exist_ok=True)
(ROOT / "results" / "pjm_queue_stats.json").write_text(json.dumps(S, indent=1))
print(json.dumps({k: v for k, v in S.items() if k != "years_to_in_service_median_by_submit_year"}, indent=1)[:4000])
print("years to in-service:", S["years_to_in_service_median_by_submit_year"])
