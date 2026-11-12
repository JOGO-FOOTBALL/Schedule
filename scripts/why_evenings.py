"""Waarom staat Karel op een avond en Jonathan niet? Alleen lezen, verandert niets.

Draaien vanuit de projectmap:  python scripts/why_evenings.py 49
(week van dit jaar; optioneel twee namen: python scripts/why_evenings.py 49 Karel Jonathan)
"""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pandas as pd  # noqa: E402

import scheduler as sch  # noqa: E402
import storage  # noqa: E402

week = int(sys.argv[1]) if len(sys.argv) > 1 else 49
a, b = (sys.argv[2], sys.argv[3]) if len(sys.argv) > 3 else ("Karel", "Jonathan")
monday = date.fromisocalendar(date.today().year, week, 1)
days = [monday + timedelta(days=i) for i in range(7)]

team, shifts = storage.load_team(), storage.load_shifts()
roster, absences, rules = storage.load_roster(), storage.load_absences(), storage.load_person_rules()

print(f"Week {week}: {monday:%d-%m} - {days[-1]:%d-%m}\n")
cols = ["naam", "kanalen", "contracturen", "max_per_week", "geen_avond", "avond_samen", "vaste_dienst", "vaste_dagen", "vrije_dagen"]
print("Employees:\n", team[team["naam"].isin([a, b])][cols].to_string(index=False), "\n")
print("Person rules:\n", rules[rules["naam"].isin([a, b])].to_string(index=False) or "  (none)", "\n")
off = absences[absences["naam"].isin([a, b])]
print("Time off:\n", off.to_string(index=False) if not off.empty else "  (none)", "\n")

week_rows = roster[roster["datum"].isin(days)]
for n in (a, b):
    mine = week_rows[week_rows["naam"] == n].sort_values("datum")
    print(f"{n}: " + ", ".join(f"{sch.WEEKDAYS[r.datum.weekday()]} {r.dienst} ({r.kanaal})" for r in mine.itertuples()))
print()

# Per avond van `a`: had `b` die avond kunnen doen (als `b` die dag niet al werkte)?
for r in week_rows[(week_rows["naam"] == a) & (week_rows["dienst"] == sch.EVENING)].sort_values("datum").itertuples():
    others = roster[roster["naam"] == b]
    own_that_day = others[others["datum"] == r.datum]
    if not own_that_day.empty:
        why = f"already works {own_that_day['dienst'].iloc[0]} that day"
        # Zou het wel gaan als die dienst er niet was?
        others = others[others["datum"] != r.datum]
    else:
        why = None
    problem = sch.assignment_problem(b, r.datum, sch.EVENING, r.kanaal, others, team, shifts, absences, sch.MIN_REST_HOURS)
    if problem is None:
        crew = [(x.naam, x.kanaal) for x in week_rows[(week_rows["datum"] == r.datum) & (week_rows["dienst"] == sch.EVENING)].itertuples() if x.naam != a]
        broken = sch.rule_breaks(b, r.datum, sch.EVENING, r.kanaal, crew, rules)
        problem = broken[0] if broken else None
    print(f"{sch.WEEKDAYS[r.datum.weekday()]} {r.datum:%d-%m} evening ({r.kanaal}): {b} -> "
          + (why + "; " if why else "") + (problem or "allowed by the rules"))
    if own_that_day.empty:
        continue
    # Ruil: `b` naar de avond, `a` naar de dienst van `b`. Kan dat, en wordt iets een late dagdienst (10-18)?
    b_shift, b_channel = own_that_day["dienst"].iloc[0], own_that_day["kanaal"].iloc[0]
    rest_a = roster[(roster["naam"] == a) & (roster["datum"] != r.datum)]
    swap_a = sch.assignment_problem(a, r.datum, b_shift, b_channel, rest_a, team, shifts, absences, sch.MIN_REST_HOURS)
    swapped = pd.concat([
        roster[~((roster["datum"] == r.datum) & roster["naam"].isin([a, b]))],
        pd.DataFrame([{"datum": r.datum, "dienst": sch.EVENING, "kanaal": r.kanaal, "naam": b},
                      {"datum": r.datum, "dienst": b_shift, "kanaal": b_channel, "naam": a}]),
    ], ignore_index=True)
    near = swapped[(swapped["datum"] >= r.datum - timedelta(days=1)) & (swapped["datum"] <= r.datum + timedelta(days=1))]
    late = sorted(f"{n} {d:%a %d-%m}" for d, n in sch.late_days(near) if n in (a, b))
    print(f"    swap ({b} evening, {a} {b_shift}): "
          + (f"{a} -> {swap_a}" if swap_a else "allowed by the rules")
          + (f"; would make a late day shift 10-18 for {', '.join(late)}" if late else ""))
