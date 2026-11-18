"""Terugkerende diensten van één persoon in Shiftbase bekijken. ALLEEN LEZEN: verandert niets.

Draaien vanuit de projectmap:  python scripts/shiftbase_series.py Arodi
Laat per dienst-id zien op welke dagen hij staat (12 weken terug tot 26 weken vooruit) en, per id, de velden
van de dienst zelf (ook als hij verwijderd is), zodat een verwijderde reeks teruggezet kan worden.
"""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import shiftbase  # noqa: E402
import storage  # noqa: E402

name = sys.argv[1] if len(sys.argv) > 1 else "Arodi"
team = storage.load_team()
user_id = str(team.set_index("naam")["shiftbase_id"].get(name, "")).strip()
print(f"{name}: Shiftbase user id {user_id or '(not set in Employees)'}\n")

today = date.today()
day, last = today - timedelta(weeks=12), today + timedelta(weeks=26)
by_id: dict[str, list[str]] = {}
while day <= last:
    until = min(day + timedelta(days=27), last)
    status, data = shiftbase.get("rosters", {"min_date": day.isoformat(), "max_date": until.isoformat()})
    for item in (data.get("data", []) if isinstance(data, dict) else []):
        r = item.get("Roster", {}) if isinstance(item, dict) else {}
        if str(r.get("user_id")) == user_id:
            by_id.setdefault(str(r.get("id")), []).append(f"{r.get('date')} {str(r.get('starttime'))[:5]}-{str(r.get('endtime'))[:5]}")
    day = until + timedelta(days=1)

print("Shifts still in Shiftbase, per id:")
for rid, days in sorted(by_id.items()):
    print(f"  id {rid}: {len(days)} day(s), first {min(days)}, last {max(days)}")

print("\nDetails per id (also shows deleted ones; fields about repeating only):")
for rid in sorted(by_id):
    status, data = shiftbase.get(f"rosters/{rid}")
    roster = (data.get("data", {}) if isinstance(data, dict) else {})
    roster = roster.get("Roster", roster) if isinstance(roster, dict) else {}
    keys = {k: v for k, v in roster.items()
            if any(w in k.lower() for w in ("recur", "repeat", "interval", "until", "occur", "deleted", "date", "time",
                                             "shift_id", "description", "day"))}
    print(f"  id {rid} (HTTP {status}): {keys}")
print("\nAll field names of a roster:", sorted(roster) if by_id else "(none found)")
