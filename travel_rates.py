"""Travel policy rates: DOH Department Order No. 2019-0225, as amended by No. 2019-0225-A
(docs/TRAVEL_RATES_PLAN.md). Pure functions and constant tables; no database, no request.

Every table carries the section it came from, so the Admin Unit can check a number against the
issuance. The area lists of Annex C were typed in from a scan: the rate card page (/travel/rates)
prints all of them for that check.

Two kinds of answer come out of here:
  * a daily allowance (`day_amount`): what the Daily Travel Expense (DTE) rules allow for one day;
  * a fare limit (`row_cap`): the most one ride may cost under the rate that applies to it.
Both are limits, not payments. The person still enters what was actually spent; the rules in
travel_rules.py flag a claim that goes over."""
from __future__ import annotations
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from typing import Optional

POLICY = "DO No. 2019-0225, as amended by DO No. 2019-0225-A"
Q = Decimal("0.01")


def _d(v) -> Decimal:
    try:
        return Decimal(str(v if v not in (None, "") else 0).replace(",", ""))
    except Exception:                                       # noqa: BLE001
        return Decimal(0)


def _money(v) -> Decimal:
    return _d(v).quantize(Q, rounding=ROUND_HALF_UP)


def _fold(text) -> str:
    """Lower case, accents removed: 'Parañaque' and 'paranaque' match."""
    s = unicodedata.normalize("NFKD", str(text or ""))
    return re.sub(r"\s+", " ", "".join(c for c in s if not unicodedata.combining(c)).lower()).strip()


# ============================================================ Daily Travel Expense ===
# VI.A.2.h(1): the same maximum for every rank, by where the person is going.

CLUSTER_DTE = {1: Decimal(1500), 2: Decimal(1800), 3: Decimal(2200)}
REGIONS = (
    ("NCR", "National Capital Region (NCR)", 3),
    ("IV-A", "Region IV-A (CALABARZON)", 3),
    ("IV-B", "Region IV-B (MIMAROPA)", 3),
    ("CAR", "Cordillera Administrative Region (CAR)", 2),
    ("VI", "Region VI (Western Visayas)", 2),
    ("VII", "Region VII (Central Visayas)", 2),
    ("X", "Region X (Northern Mindanao)", 2),
    ("XI", "Region XI (Davao Region)", 2),
    ("I", "Region I (Ilocos Region)", 1),
    ("II", "Region II (Cagayan Valley)", 1),
    ("III", "Region III (Central Luzon)", 1),
    ("V", "Region V (Bicol Region)", 1),
    ("VIII", "Region VIII (Eastern Visayas)", 1),
    ("IX", "Region IX (Zamboanga Peninsula)", 1),
    ("XII", "Region XII (SOCCSKSARGEN)", 1),
    ("XIII", "Region XIII (Caraga)", 1),
    ("BARMM", "Bangsamoro Autonomous Region in Muslim Mindanao (BARMM)", 1),
)
_REGION = {c: (label, cl) for c, label, cl in REGIONS}

# VI.A.2.i(1): how a full day is shared out, and the departure-day share.
LODGING, MEALS, INCIDENTALS = Decimal("0.50"), Decimal("0.30"), Decimal("0.20")
DEPARTURE_SHARE = Decimal("0.50")           # meals 30% + incidentals 20%; no lodging
SUBSISTENCE_ALLOWANCE = Decimal(50)         # VI.A.2.i(2): taken off meals on working days when paid through payroll
EARLIEST_LIAISON = "8:00 AM"
LATE_HOUR = "7 PM"
SHUTTLE_MIN_DAYS = 3                        # VI.A.2.g

# What one itinerary day can be. (code, group, label, rule)
DAY_KINDS = (
    ("full", "DTE", "Full day: arrival day and each day of official business",
     "100% of the DTE: lodging 50%, meals 30%, incidentals 20% (VI.A.2.i(1))."),
    ("departure", "DTE", "Departure day only (left the station the day before arriving)",
     "50% of the DTE: meals 30%, incidentals 20% (VI.A.2.i(1))."),
    ("live_in", "DTE", "Live-in: hotel and meals are provided",
     "Nothing for these days; incidentals are claimed for the day before and the day after (VI.A.2.i(3))."),
    ("live_in_edge", "DTE", "Day before or after a live-in activity",
     "Incidentals only: 20% of the DTE (VI.A.2.i(3))."),
    ("commute", "Within 50 km, going home each day", "Commuting only, no meal allowance",
     "Actual fare only (VI.A.3.b(1))."),
    ("monitor", "Within 50 km, going home each day", "Monitoring, audit, inspection, investigation, evaluation",
     "Meal allowance of 20% of the DTE (VI.A.3.b(2))."),
    ("monitor_late", "Within 50 km, going home each day", "The same, and the work ran beyond 7 PM",
     "Meal allowance of 20% + 10% of the DTE; the Head of Office approves the extension (VI.A.3.b(2))."),
    ("liaison", "Within 50 km, going home each day", "Liaison officer who left the station by 8:00 AM",
     "Meal allowance of 10% of the DTE (VI.A.3.b(4))."),
    ("hpdpb", "Within 50 km, going home each day", "Staff of HPDPB Legislative Liaison Division",
     "Meal allowance of 20% of the DTE (VI.A.3.b(4)(b.2))."),
    ("late_activity", "Within 50 km, going home each day", "Meeting, forum or seminar outside DOH that ran beyond 7 PM",
     "Incidental expenses, 20% of the DTE, with the Head of Office's approval of the extension (VI.A.3.b(3))."),
)
DAY_KIND_CODES = tuple(k[0] for k in DAY_KINDS)
_DAY_KIND = {k[0]: k for k in DAY_KINDS}

# Share of the DTE that a within-50 km meal allowance pays.
_MEAL_SHARE = {"monitor": Decimal("0.20"), "monitor_late": Decimal("0.30"),
               "liaison": Decimal("0.10"), "hpdpb": Decimal("0.20")}


def region_dte(region) -> Optional[Decimal]:
    """The maximum DTE for a region code, or None when the code is not a region."""
    hit = _REGION.get(region)
    return CLUSTER_DTE[hit[1]] if hit else None


def region_cluster(region) -> Optional[int]:
    hit = _REGION.get(region)
    return hit[1] if hit else None


@dataclass
class DayResult:
    total: Decimal = Decimal(0)
    lodging: Decimal = Decimal(0)
    meals: Decimal = Decimal(0)
    incidentals: Decimal = Decimal(0)
    notes: list = field(default_factory=list)

    def as_dict(self):
        return {"total": float(self.total), "lodging": float(self.lodging), "meals": float(self.meals),
                "incidentals": float(self.incidentals), "notes": list(self.notes)}


def day_amount(kind, dte, *, working_day=True, receives_sa=False, lodging_provided=False,
               meals_provided=False) -> Optional[DayResult]:
    """What one day allows. None when the kind or the DTE is unknown.

    `lodging_provided` / `meals_provided`: the government or another party paid for them, so that
    part of the DTE is not allowed (VI.A.2.k). `receives_sa`: the person is paid the Php 50 daily
    subsistence allowance through payroll, which comes off the meals of a working day (VI.A.2.i(2))."""
    dte = _d(dte)
    if kind not in _DAY_KIND or dte <= 0:
        return None
    res = DayResult()
    if kind == "full":
        res.lodging, res.meals, res.incidentals = dte * LODGING, dte * MEALS, dte * INCIDENTALS
    elif kind == "departure":
        res.meals, res.incidentals = dte * MEALS, dte * INCIDENTALS
    elif kind == "live_in_edge":
        res.incidentals = dte * INCIDENTALS
    elif kind == "late_activity":
        res.incidentals = dte * INCIDENTALS
    elif kind in _MEAL_SHARE:
        res.meals = dte * _MEAL_SHARE[kind]
    # live_in and commute pay nothing here.
    if lodging_provided and res.lodging:
        res.lodging = Decimal(0)
        res.notes.append("Lodging is provided, so the lodging part is not allowed.")
    if meals_provided and res.meals:
        res.meals = Decimal(0)
        res.notes.append("Meals are provided, so the meals part is not allowed.")
    if receives_sa and working_day and res.meals:
        cut = min(res.meals, SUBSISTENCE_ALLOWANCE)
        res.meals -= cut
        res.notes.append("The Php 50 subsistence allowance paid through payroll comes off the meals.")
    res.lodging, res.meals, res.incidentals = _money(res.lodging), _money(res.meals), _money(res.incidentals)
    res.total = res.lodging + res.meals + res.incidentals
    return res


# ================================================================== fare limits ===
# Annex C (amended VI.A.2.f): taxi from residence or official station to the airport terminal and
# back, by city area. (code, city, name, rate, places). Typed in from the scan; spelling tidied.

@dataclass(frozen=True)
class Area:
    code: str
    city: str
    name: str
    amount: Decimal
    places: tuple


def _area(city, n, amount, places):
    name = city if not n else (f"{city} {n}" if city == "Caloocan North" else f"{city} Area {n}")     # the annex prints it so
    code = re.sub(r"[^a-z0-9]+", "_", _fold(name)).strip("_")
    return Area(code, city, name, Decimal(amount), tuple(p.strip() for p in places.split(";") if p.strip()))


ANNEX_C = (
    _area("Parañaque", 1, 150, "Baltao; Casino Filipino; Duty Free; MIAA Old Domestic; Moonwalk 1; Multinational Village 1 "
          "(Jerusalem St., Tel Aviv St.); Sto. Niño; Tambo; Uniwide Coastal Mall"),
    _area("Pasay", 1, 150, "Airmen's Village; Pildera 1 & 2; Rivera Village; Villamor Airbase"),
    _area("Las Piñas", 1, 250, "Ilaya (Marine Pond); Manuyo Dos; Poblacion"),
    _area("Parañaque", 2, 250, "Baclaran; Better Living; Bicutan Interchange; Don Bosco; Kalayaan Village; Marcelo Green; "
          "Merville; Moonwalk 2; Multinational Village 2 (all other streets: refer to Multinational Village 1); PNCC area; "
          "Sun Valley; San Dionisio; SM Sucat; United Parañaque"),
    _area("Pasay", 2, 250, "FB Harrison; GSIS; Russian Embassy; Senate; Tramo; Vietnam Embassy; World Trade Center"),
    _area("Makati", 1, 250, "Dasmariñas Village; Forbes Park (South); Glorietta; Greenbelt; Legaspi Village; Magallanes"),
    _area("Taguig", 1, 250, "FTI; Ft. Bonifacio (Lawton Avenue); Signal Village; Upper Bicutan; Western Bicutan"),
    _area("Las Piñas", 2, 300, "BF Executive Village; BF International; CAA 13 Compound; Pamplona 1 & 3; Pulang Lupa 440"),
    _area("Makati", 2, 300, "Bel-Air; Carmona Tracks (Sta. Ana); Forbes Park (North); JP Rizal; Guadalupe; Makati City Hall; "
          "Olympia; Pitogo; Primetown; Century Tower; Rockwell; San Antonio Village; South Cembo; Sunrise Tower; Urdaneta Village"),
    _area("Parañaque", 3, 300, "BF Homes; Camella Homes Parañaque; Hillsborough; Tahanan Village; Sucat Parañaque"),
    _area("Muntinlupa", 1, 300, "Doña Rosario (Heights & Bayview); Don Juan Bayview; Posadas Village"),
    _area("Pateros", 0, 300, "Aguho; Sta. Ana; San Pedro; Poblacion Martirez Del '96"),
    _area("Taguig", 2, 300, "Bonifacio Global City (BGC, Market-Market); Bambang; Hagonoy (Bay Freeze Village); Lower Bicutan; "
          "Bagumbayan; Bagong Tanyag; Tuktukan; Sta. Ana"),
    _area("Manila", 1, 300, "Adriatico Hotel; Ambassador Hotel; Harrison Plaza; Central Bank; Century Hotel; Folk Arts Theater; "
          "Malate; San Andres Bukid"),
    _area("Las Piñas", 3, 350, "Almanza; BF Almanza; Pamplona 2; Philamlife Village; Pilar; SM South Mall; Talon 2, 4 & 5"),
    _area("Muntinlupa", 2, 350, "Alabang Town Center; Alabang Hills 1, 2 & 3; Buli; Cupang; DSWD; Rizal Village; Sucat"),
    _area("Pasig", 1, 350, "Bagong Ilog; Kalayaan; Kapitolyo; Phil. Sports Complex (ULTRA); Pasig City Hall; Pinagbuhatan; "
          "San Joaquin; Valle Verde 1"),
    _area("Taguig", 3, 350, "Napindan; Palingon; Tipas"),
    _area("Mandaluyong", 1, 350, "Mandaluyong City Hall; Mega Mall; Star Mall EDSA; Shangri-La Plaza EDSA"),
    _area("Manila", 2, 350, "Bacood; Ermita; Intramuros; Lawton; Malacañang Area; Manila City Hall; Manila Hotel; Paco; Pandacan; "
          "Pier South (Pier 1-11); Punta; San Miguel; Sta. Ana"),
    _area("Las Piñas", 4, 400, "BF Classic; Metrocor Homes; Pilar Village Phase 4; Soldier Hills II"),
    _area("Muntinlupa", 3, 400, "Ayala Alabang Village 1; Alabang Golf Course; New Alabang 1; Bayanan; Festival Mall; "
          "Star Mall Alabang (Metropolis)"),
    _area("Pasig", 2, 400, "ADB; May Bunga; Meralco; San Miguel; Robinson's; Rosario; Valle Verde 2, 3, 4, 5 & 6"),
    _area("Mandaluyong", 2, 400, "La Salle; Wack-Wack Golf"),
    _area("Manila", 3, 400, "Binondo; Customs; Divisoria; Fort Santiago; North Harbor; Pier South (Pier 12-up); Quiapo; "
          "San Nicholas; Sta. Cruz; Sta. Mesa; Tutuban"),
    _area("Quezon City", 1, 400, "Camp Aguinaldo; Camp Crame; Corinthian Garden; Green Meadows; New Manila; PCSO; Santolan; "
          "SM Center Point; Ugong Norte"),
    _area("San Juan", 0, 400, "Greenhills; Little Baguio; Pinaglabanan; Wack-Wack"),
    _area("Muntinlupa", 4, 450, "Camp Bukang Liwayway; Ayala Alabang Village 2; Camp Sampaguita; New Alabang 1; "
          "New Bilibid Prison area; Katarungan Village; Putatan; Poblacion"),
    _area("Pasig", 3, 450, "Manggahan; Green Park; Ever Gotesco (Ortigas); Sta. Lucia De Castro; Santolan"),
    _area("Manila", 4, 450, "Gagalangin (Tondo); North Chinese Cemetery; Sampaloc"),
    _area("Quezon City", 2, 450, "Araneta Center; Amoranto; Banawe; Cubao; Galas; Kamias; Kamuning; La Loma; Libis (Bagumbayan); "
          "LTO; LTFRB; Project 2, 3 & 4; Sacred Heart; San Francisco Del Monte; Sta. Mesa Heights; Scout Streets; Timog; "
          "Tomas Morato; Welcome Rotonda; White Plains"),
    _area("Marikina", 1, 450, "Industrial Valley"),
    _area("Muntinlupa", 5, 500, "Camella Homes; Park Homes Subdivision; Refedor Teacher's Village; Susana Heights; "
          "Victoria Homes (Tunasan); Villa Carolina Subdivision"),
    _area("Pasig", 4, 500, "Dela Peña; Karangalan Village; Robinson's Place (Metro East); Sta. Lucia Mall"),
    _area("Quezon City", 3, 500, "Apolinario Samson; Bagong Bantay; Bagong Bato; Bagong Pag-Asa; Balintawak; Balingasi; "
          "East Avenue (Heart Center, Bangko Sentral); Krus na Ligas; Loyola Heights; Muñoz; Project 6, 7 & 8; Paltok; "
          "Quezon Memorial Circle; San Antonio; Sto. Kristo; SM West; Sikatuna; UP Campus; UP Village; Teachers Village; "
          "Wildlife Park"),
    _area("Navotas", 1, 500, "North Bay Boulevard; Bangkulasi"),
    _area("Marikina", 2, 500, "Barangka (River Banks); Calumpang; J. Dela Peña; San Roque; Sta. Elena; Sto. Niño; Tañong"),
    _area("Caloocan", 1, 500, "Bagong Barrio West; Grace Park; Maypajo; Monumento; Obrero; Sangandaan"),
    _area("Malabon", 1, 500, "Dagat-Dagatan"),
    _area("Malabon", 2, 500, "Acacia; Baba; Bayan-Bayanan; Baritan; Catmon; Concepcion; Flores; Longos; Maysilo; Muzon; "
          "Niugan; Potrero; San Agustin; Tañong; Tinajeros; Tugatog"),
    _area("Quezon City", 4, 500, "Bahay Toro; Baesa; Bagong Barrio East; Culiat; Old Balara; Sangandaan; Tandang Sora; "
          "Talipapa; Matandang Balara 2 (all other streets: refer to Matandang Balara 1)"),
    _area("Navotas", 2, 500, "Daang Hari; Navotas West; Sipak-Almacen; San Roque; San Jose"),
    _area("Valenzuela", 1, 500, "Fatima; Marulas; Karuhatan"),
    _area("Marikina", 3, 500, "Concepcion 1 & 2; Lamuan; Malanday; Marikina Heights"),
    _area("Caloocan", 2, 500, "Baesa; Sta. Quiteria; Talipapa"),
    _area("Quezon City", 5, 550, "Batasan Complex; Bagbag; COA; Ever Commonwealth; Fairview; Holy Spirit; Mangahan; "
          "San Bartolome; Sta. Lucia; Sauyo; Matandang Balara 1 (all other streets: refer to Matandang Balara 2)"),
    _area("Navotas", 3, 550, "Tangos; Tanza"),
    _area("Valenzuela", 2, 550, "Gen. T. De Leon; Arkong Bato; Rincon; Mapulang Lupa; Paso De Blas; Maysan; Dalandan; Malinta"),
    _area("Marikina", 4, 550, "Parang; Nangka"),
    _area("Malabon", 3, 550, "Dampalit; Hulong Duhat; Panghulo; Santolan"),
    _area("Quezon City", 6, 550, "Bagong Silang; Capri; Commonwealth (Payatas); Fairview Market; Gulod; La Mesa Dam; Pason; "
          "Putik; San Agustin; Sta. Monica; Sitio Gao"),
    _area("Valenzuela", 3, 550, "Balangkas; Polo; Palasan; Poblacion; Bisig; Mabolo; Palanday; Veintereales; Lingunan; "
          "Canumay; Bagbaguin; Canumay East; Lawang Bato"),
    _area("Caloocan North", 1, 550, "Bagbaguin; Kaybiga"),
    _area("Quezon City", 7, 550, "Amlang Village; Capitol View; Park Subdivision; Commonwealth; Countryside Village; "
          "Kaligayahan; Pasong Putik; Regalado Highway; Zamora Homes"),
    _area("Valenzuela", 4, 550, "Bignay; Punturin"),
    _area("Caloocan North", 2, 550, "Bagumbong; Deparo; Llano"),
    _area("Caloocan North", 3, 550, "Bagong Silang; Camarin; Tala"),
)
OUTSIDE_METRO = Area("outside_metro_manila", "Outside Metro Manila", "Outside Metro Manila (Rizal, Cavite, Bulacan and the rest)",
                     Decimal(550), ("Rizal", "Cavite", "Bulacan", "all areas outside Metro Manila"))
_AREAS = {a.code: a for a in ANNEX_C + (OUTSIDE_METRO,)}


def area_by_code(code) -> Optional[Area]:
    return _AREAS.get(code)


def find_areas(text, limit=12) -> list:
    """Annex C areas whose name or any listed place contains the text (accents and case ignored)."""
    needle = _fold(text)
    if len(needle) < 2:
        return []
    out = [a for a in ANNEX_C + (OUTSIDE_METRO,)
           if needle in _fold(a.name) or any(needle in _fold(p) for p in a.places)]
    return out[:limit]


@dataclass(frozen=True)
class Zone:
    code: str
    amount: Decimal
    places: str


def _zones(prefix, rows):
    return tuple(Zone(f"{prefix}{n}", Decimal(n), p) for n, p in rows)


# VI.A.2.f (original table; the airport column is replaced by Annex C): taxi from the residence
# to a seaport or bus station, by area.
TERMINAL_ZONES = _zones("t", (
    (350, "All areas nearest to the airport including Parañaque"),
    (400, "San Andres, Sta. Ana, Sta. Mesa, Blumentritt, Quezon City Rotonda, Greenhills, San Juan, Cubao, Pasig, Makati, "
          "Las Piñas, Taguig and other areas within the vicinity of these"),
    (500, "Navotas, Malabon, Sangandaan, Southern part of Caloocan, Central Area of Quezon City and other areas within "
          "the vicinity of these"),
    (550, "Northern Caloocan, Novaliches, Fairview, Valenzuela, Meycauayan, Marikina, Antipolo, Cainta, Cavite and all areas "
          "outside Metro Manila and other areas within the vicinity of these"),
))
# VI.A.2.g: residence to the DOH Central Office to catch the DOH shuttle or rented bus, for a trip of three days or more.
SHUTTLE_ZONES = _zones("s", (
    (100, "Blumentritt, España, Welcome Rotonda, Tondo, Divisoria and other areas within the vicinity"),
    (250, "San Andres, Sta. Ana, Sta. Mesa, Pasay, Greenhills, San Juan and other areas within the vicinity"),
    (300, "Monumento, Navotas, Malabon, Sangandaan, Southern part of Caloocan, Central area of Quezon City and other "
          "areas within the vicinity"),
    (400, "Makati, Las Piñas, Taguig and other areas within the vicinity"),
    (450, "Tala, Northern Caloocan, Novaliches, Fairview, Valenzuela, Marikina, Antipolo, Cainta, Muntinlupa, Cavite and all "
          "areas outside Metro Manila and other areas within the vicinity"),
))
_ZONES = {z.code: z for z in TERMINAL_ZONES + SHUTTLE_ZONES}

# VI.A.3 (amended c): taxi for live-out activities within 50 km in Metro Manila, per trip, by Google Maps distance.
LIVE_OUT_BANDS = ((10, 100), (15, 250), (20, 300), (25, 400), (None, 450))      # (up to km, maximum)
NO_RECEIPT_MAX = Decimal(300)               # COA Circular 2017-001 (Annex A): without an official receipt
TAXI_ACTIVITY_MAX = Decimal(550)            # VI.A.2.b(1): taxi to an official activity outside DOH
TNVS_MAX = Decimal(700)                     # VI.A.2.b(1): TNVS (e.g. Grab), with justification and an e-receipt in the claimant's name

# Annex B: LTFRB ordinary public utility bus fare guide, Metro Manila. Regular, then student / senior / PWD (20% off).
LTFRB_REGULAR = tuple(Decimal(x) for x in (
    "10 10 10 10 10 11.75 13.75 15.5 17.5 19.25 21 23 24.75 26.75 28.5 30.25 32.25 34 36 37.75 39.5 41.5 43.25 45.25 47 48.75 "
    "50.75 52.5 54.5 56.25 58 60 61.75 63.75 65.5 67.25 69.25 71 73 74.75 76.5 78.5 80.25 82.25 84 85.75 87.75 89.5 91.5 93.25 "
    "95 97 98.75 100.75 102.5 104.25 106.25 108 110 111.75").split())
LTFRB_DISCOUNT = tuple(Decimal(x) for x in (
    "8 8 8 8 8 9.5 11 12.5 14 15.5 17 18.25 19.75 21.25 22.75 24.25 25.75 27.25 28.75 30.25 31.75 33.25 34.75 36 37.5 39 40.5 "
    "42 43.5 45 46.5 48 49.5 51 52.5 54 55.25 56.75 58.25 59.75 61.25 62.75 64.25 65.75 67.25 68.75 70.25 71.75 73 74.5 76 "
    "77.5 79 80.5 82 83.5 85 86.5 88 89.5").split())
LTFRB_FIRST_KM = 5
_LTFRB_ADD = {False: (Decimal(10), Decimal("1.85")), True: (Decimal(8), Decimal("1.48"))}


def ltfrb_formula(km, discounted=False) -> Decimal:
    """Add-on method printed on Annex B: the first five km, then a rate per succeeding km, rounded to the nearest 25 centavos."""
    base, per = _LTFRB_ADD[bool(discounted)]
    raw = base + per * max(0, int(km) - LTFRB_FIRST_KM)
    return (raw * 4).quantize(Decimal(1), rounding=ROUND_HALF_UP) / 4


def ltfrb_fare(km, discounted=False) -> Optional[Decimal]:
    """The Annex B fare for a distance. A part of a kilometre counts as a whole one; beyond the
    60 km on the printed table the add-on method continues it. None for no distance."""
    km = _d(km)
    if km <= 0:
        return None
    whole = int(km.to_integral_value(rounding=ROUND_CEILING))
    table = LTFRB_DISCOUNT if discounted else LTFRB_REGULAR
    return table[whole - 1] if whole <= len(table) else ltfrb_formula(whole, discounted)


def live_out_max(km) -> Optional[Decimal]:
    km = _d(km)
    if km <= 0:
        return None
    for upto, amount in LIVE_OUT_BANDS:
        if upto is None or km <= upto:
            return Decimal(amount)
    return None


# ------------------------------------------------------------ rate bases and caps ---

BASES = (
    ("activity", "Taxi or TNVS to an official activity", "mode",
     "Taxi up to Php 550, TNVS up to Php 700 (VI.A.2.b(1))"),
    ("airport", "Residence or station ⇄ airport", "area", "Annex C, by area (VI.A.2.f as amended)"),
    ("terminal", "Residence ⇄ seaport or bus station", "zone", "Area table (VI.A.2.f)"),
    ("shuttle", "Residence ⇄ DOH to catch the shuttle (3 days or more)", "zone", "Area table (VI.A.2.g)"),
    ("live_out", "Taxi for a live-out activity within 50 km", "km", "Distance table (VI.A.3.c, amended)"),
    ("beyond50", "Public fare beyond 50 km, when no local rate exists", "km", "LTFRB fare guide (Annex B)"),
)
BASIS_CODES = tuple(b[0] for b in BASES)
_BASIS_INPUT = {b[0]: b[2] for b in BASES}
RIDE_MODES = ("taxi", "tnvs", "public_noreceipt")


@dataclass(frozen=True)
class Cap:
    amount: Decimal
    rule: str


def place_choices(basis) -> list:
    """[(code, label, amount, search_text)] for the place picker of a basis that has one, else [].
    `search_text` holds every place name, so the page can filter the list as the person types."""
    if basis == "airport":
        return [(a.code, f"{a.name} (Php {a.amount:,.0f}): {', '.join(a.places[:3])}{'…' if len(a.places) > 3 else ''}",
                 a.amount, _fold(a.name + " " + " ".join(a.places))) for a in ANNEX_C + (OUTSIDE_METRO,)]
    zones = {"terminal": TERMINAL_ZONES, "shuttle": SHUTTLE_ZONES}.get(basis)
    return [(z.code, f"Php {z.amount:,.0f}: {z.places}", z.amount, _fold(z.places)) for z in zones] if zones else []


def row_cap(row, *, discounted=False) -> Optional[Cap]:
    """The most one ride may cost under the basis the person chose, or None when there is nothing
    to check it against (no basis, no place or distance yet, or a mode the rate does not cover).

    `row` carries mode, basis, place, km and receipt."""
    basis, mode = row.get("basis"), row.get("mode")
    if basis not in _BASIS_INPUT or mode not in RIDE_MODES:
        return None
    if basis == "activity":
        if mode == "tnvs":
            return Cap(TNVS_MAX, "TNVS: up to Php 700, with a justification approved by the Head of Office and an e-receipt in your name (VI.A.2.b(1)).")
        if mode == "taxi":
            return Cap(TAXI_ACTIVITY_MAX, "Taxi: up to Php 550, with a receipt and a justification approved by the Head of Office (VI.A.2.b(1)).")
        return None
    if basis == "airport":
        a = area_by_code(row.get("place"))
        return Cap(a.amount, f"{a.name}: up to Php {a.amount:,.0f} per trip (Annex C).") if a else None
    if basis in ("terminal", "shuttle"):
        z = _ZONES.get(row.get("place"))
        if not z or z.code[0] != basis[0]:
            return None
        return Cap(z.amount, f"Up to Php {z.amount:,.0f} per trip (VI.A.2.{'f' if basis == 'terminal' else 'g'}).")
    if basis == "live_out":
        band = live_out_max(row.get("km"))
        if band is None:
            return None
        if row.get("receipt") != "receipt":
            if band > NO_RECEIPT_MAX:
                return Cap(NO_RECEIPT_MAX, f"Php {band:,.0f} with an official receipt; without one, only up to Php 300 (COA Circular 2017-001).")
            return Cap(band, f"Up to Php {band:,.0f} per trip.")
        return Cap(band, f"Up to Php {band:,.0f} per trip for {_d(row.get('km')):.1f} km, with an official receipt (VI.A.3.c).")
    fare = ltfrb_fare(row.get("km"), discounted)
    if fare is None:
        return None
    return Cap(fare, f"LTFRB fare for {_d(row.get('km')):.1f} km: Php {fare:,.2f}"
                     f"{' (senior / PWD / student)' if discounted else ''} (Annex B).")


# ================================================================= whole itinerary ===

@dataclass
class RowRates:
    per_diem: Optional[Decimal] = None          # what the day kind allows
    day: Optional[DayResult] = None
    cap: Optional[Cap] = None
    warnings: list = field(default_factory=list)

    def as_dict(self):
        return {"per_diem": float(self.per_diem) if self.per_diem is not None else None,
                "day": self.day.as_dict() if self.day else None,
                "cap": float(self.cap.amount) if self.cap else None, "cap_rule": self.cap.rule if self.cap else "",
                "warnings": list(self.warnings)}


def _row_date(row):
    try:
        return date.fromisoformat(str(row.get("date") or "")[:10])
    except ValueError:
        return None


def rates_for_rows(rows, opts, is_working=None) -> list:
    """One RowRates per itinerary row. `warnings` are plain-language notes only; a claim that goes over a
    limit is caught by travel_rules.flags_for, which compares the amounts. `opts`: region, receives_sa, discounted, trip_days.
    `is_working(date) -> bool` tells Monday-to-Friday non-holidays from the rest; without it
    every day counts as a working day (the stricter reading for the subsistence allowance)."""
    opts = opts or {}
    dte = region_dte(opts.get("region"))
    out = []
    for r in rows:
        rr = RowRates()
        day = _row_date(r)
        working = True if (is_working is None or day is None) else bool(is_working(day))
        kind = r.get("day_kind")
        if kind in _DAY_KIND:
            if dte is None:
                rr.warnings.append("Choose where you are going to see the daily rate.")
            else:
                rr.day = day_amount(kind, dte, working_day=working, receives_sa=bool(opts.get("receives_sa")),
                                    lodging_provided=bool(r.get("lodging_provided")), meals_provided=bool(r.get("meals_provided")))
                rr.per_diem = rr.day.total
        rr.cap = row_cap(r, discounted=bool(opts.get("discounted")))
        if r.get("basis") == "shuttle" and int(opts.get("trip_days") or 0) and int(opts["trip_days"]) < SHUTTLE_MIN_DAYS:
            rr.warnings.append("The shuttle allowance is for trips of three days or more.")
        if r.get("mode") == "govt" and _d(r.get("allowance")) > 0:
            rr.warnings.append("With a government vehicle there is no transportation claim, except fuel, tolls and parking "
                               "when the DPO says so.")
        out.append(rr)
    return out
