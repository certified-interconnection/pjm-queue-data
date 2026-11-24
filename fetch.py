"""Download PJM's public interconnection queue file (PlanningQueues.xml) into data/raw/."""
import pathlib, urllib.request
URL = "https://www.pjm.com/pub/planning/downloads/xml/PlanningQueues.xml"
out = pathlib.Path(__file__).parent / "data" / "raw" / "PlanningQueues.xml"
out.parent.mkdir(parents=True, exist_ok=True)
req = urllib.request.Request(URL, headers={"User-Agent": "certified-interconnection/0.1"})
out.write_bytes(urllib.request.urlopen(req, timeout=120).read())
print("saved", out, out.stat().st_size, "bytes")
