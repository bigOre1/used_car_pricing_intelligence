"""
generate_data.py
----------------
Generates a realistic used car transaction dataset and loads it into SQLite.
Run this first to initialize the project database.

Author: Ore Atobatele | Used Car Pricing Intelligence Suite
"""

import sqlite3
import random
import math
from datetime import date, timedelta

random.seed(42)

# ── Constants ──────────────────────────────────────────────────────────────────
DB_PATH = "car_pricing.db"

MAKES = {
    "Toyota":   ["Camry", "Corolla", "RAV4", "Highlander", "Tacoma"],
    "Honda":    ["Civic", "Accord", "CR-V", "Pilot", "Odyssey"],
    "Ford":     ["F-150", "Explorer", "Escape", "Mustang", "Edge"],
    "Chevrolet":["Silverado", "Equinox", "Malibu", "Traverse", "Tahoe"],
    "BMW":      ["3 Series", "5 Series", "X3", "X5", "7 Series"],
    "Mercedes": ["C-Class", "E-Class", "GLC", "GLE", "S-Class"],
    "Nissan":   ["Altima", "Sentra", "Rogue", "Pathfinder", "Frontier"],
    "Hyundai":  ["Elantra", "Sonata", "Tucson", "Santa Fe", "Palisade"],
}

LUXURY_MAKES = {"BMW", "Mercedes"}

CONDITIONS = ["Excellent", "Good", "Fair", "Poor"]
CONDITION_WEIGHTS = [0.20, 0.45, 0.25, 0.10]

COLORS = ["Black", "White", "Silver", "Gray", "Red", "Blue", "Brown", "Green"]

SALESPEOPLE = [
    "Marcus Johnson", "Tanya Williams", "Derek Osei",
    "Lisa Chen", "Carlos Rivera", "Amara Patel",
]

MONTHS = list(range(1, 13))
# Seasonality multiplier per month (Jan=low, summer=high, Dec=moderate)
SEASON_FACTOR = {
    1: 0.88, 2: 0.90, 3: 0.98, 4: 1.03, 5: 1.06, 6: 1.08,
    7: 1.07, 8: 1.05, 9: 1.02, 10: 0.97, 11: 0.93, 12: 0.95,
}


def base_price(make, model, year):
    """Estimate a realistic base price from make/model/age."""
    current_year = 2025
    age = current_year - year
    is_luxury = make in LUXURY_MAKES

    # Starting MSRP proxies
    msrp_map = {
        "F-150": 42000, "Silverado": 41000, "Tacoma": 38000,
        "Highlander": 40000, "Pilot": 38000, "Tahoe": 52000,
        "Traverse": 37000, "Pathfinder": 36000, "Palisade": 40000,
        "5 Series": 62000, "E-Class": 65000, "X5": 67000, "GLE": 65000,
        "7 Series": 95000, "S-Class": 98000,
        "3 Series": 45000, "C-Class": 44000, "X3": 48000, "GLC": 48000,
        "RAV4": 32000, "CR-V": 31000, "Equinox": 30000, "Escape": 29000,
        "Tucson": 28000, "Santa Fe": 33000, "Rogue": 30000,
        "Camry": 28000, "Accord": 29000, "Malibu": 24000, "Sonata": 26000,
        "Altima": 25000, "Civic": 24000, "Corolla": 23000,
        "Elantra": 22000, "Sentra": 21000,
        "Mustang": 35000, "Explorer": 39000, "Edge": 34000,
        "Odyssey": 38000, "Frontier": 32000,
    }
    msrp = msrp_map.get(model, 30000)

    # Depreciation curve: fast early, slower later
    depreciation = 1.0
    for i in range(age):
        if i == 0:
            depreciation *= 0.85   # first year: -15%
        elif i < 3:
            depreciation *= 0.91
        elif i < 7:
            depreciation *= 0.94
        else:
            depreciation *= 0.97

    return msrp * depreciation


def mileage_for_age(age):
    annual = random.gauss(12500, 2500)
    return max(500, int(annual * age + random.gauss(0, 3000)))


def days_to_sale(condition, age, season_month):
    base = {"Excellent": 18, "Good": 28, "Fair": 42, "Poor": 65}[condition]
    age_adj = age * 1.2
    season_adj = (1 / SEASON_FACTOR[season_month]) * 5
    noise = random.gauss(0, 5)
    return max(1, int(base + age_adj + season_adj + noise))


def condition_multiplier(condition):
    return {"Excellent": 1.08, "Good": 1.00, "Fair": 0.88, "Poor": 0.74}[condition]


# ── Schema ─────────────────────────────────────────────────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS vehicles (
    vehicle_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    vin             TEXT UNIQUE NOT NULL,
    make            TEXT NOT NULL,
    model           TEXT NOT NULL,
    year            INTEGER NOT NULL,
    color           TEXT,
    mileage         INTEGER,
    condition       TEXT CHECK(condition IN ('Excellent','Good','Fair','Poor')),
    acquisition_cost REAL,
    list_price      REAL,
    sale_price      REAL,
    days_in_inventory INTEGER,
    sale_date       TEXT,
    sale_month      INTEGER,
    sale_year       INTEGER,
    salesperson     TEXT,
    gross_profit    REAL,
    gross_margin_pct REAL
);

CREATE TABLE IF NOT EXISTS market_benchmarks (
    benchmark_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    make            TEXT,
    model           TEXT,
    year            INTEGER,
    condition       TEXT,
    market_avg_price REAL,
    benchmark_date  TEXT
);

CREATE TABLE IF NOT EXISTS monthly_inventory_snapshot (
    snapshot_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_month  INTEGER,
    snapshot_year   INTEGER,
    total_units     INTEGER,
    avg_list_price  REAL,
    avg_days_listed REAL,
    aged_units_30plus INTEGER,
    aged_units_60plus INTEGER
);
"""


def generate_vin():
    chars = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"
    return "".join(random.choices(chars, k=17))


def generate_vehicles(n=520):
    rows = []
    used_vins = set()
    start_date = date(2024, 1, 1)
    end_date = date(2025, 6, 30)
    date_range = (end_date - start_date).days

    for _ in range(n):
        make = random.choice(list(MAKES.keys()))
        model = random.choice(MAKES[make])
        year = random.randint(2015, 2023)
        age = 2025 - year
        color = random.choice(COLORS)
        condition = random.choices(CONDITIONS, weights=CONDITION_WEIGHTS)[0]
        mileage = mileage_for_age(age)
        salesperson = random.choice(SALESPEOPLE)

        bp = base_price(make, model, year)
        cond_mult = condition_multiplier(condition)
        mileage_adj = max(0.70, 1 - (mileage / 200000) * 0.25)

        acquisition_cost = bp * cond_mult * mileage_adj * random.uniform(0.82, 0.91)
        list_price = acquisition_cost * random.uniform(1.14, 1.22)

        sale_date = start_date + timedelta(days=random.randint(0, date_range))
        season_month = sale_date.month
        dts = days_to_sale(condition, age, season_month)

        # Price negotiation: longer on lot = more discount
        discount_pct = min(0.12, 0.01 + (dts / 365) * 0.15 + random.uniform(-0.01, 0.02))
        sale_price = list_price * (1 - discount_pct)

        gross_profit = sale_price - acquisition_cost
        gross_margin = (gross_profit / sale_price) * 100

        vin = generate_vin()
        while vin in used_vins:
            vin = generate_vin()
        used_vins.add(vin)

        rows.append((
            vin, make, model, year, color, mileage, condition,
            round(acquisition_cost, 2), round(list_price, 2), round(sale_price, 2),
            dts, sale_date.isoformat(), sale_date.month, sale_date.year,
            salesperson, round(gross_profit, 2), round(gross_margin, 2)
        ))
    return rows


def generate_benchmarks(vehicles):
    """Generate market benchmark prices slightly above/below our sale prices."""
    seen = {}
    for v in vehicles:
        key = (v[1], v[2], v[3], v[6])  # make, model, year, condition
        if key not in seen:
            market_price = v[9] * random.uniform(0.96, 1.04)  # near sale price
            seen[key] = round(market_price, 2)
    rows = []
    for (make, model, year, condition), price in seen.items():
        rows.append((make, model, year, condition, price, "2025-01-01"))
    return rows


def generate_snapshots():
    """Monthly inventory snapshots."""
    rows = []
    for year in [2024, 2025]:
        months = range(1, 13) if year == 2024 else range(1, 7)
        for month in months:
            units = random.randint(55, 110)
            avg_price = random.uniform(22000, 38000)
            avg_days = random.uniform(25, 55)
            aged_30 = int(units * random.uniform(0.20, 0.40))
            aged_60 = int(aged_30 * random.uniform(0.25, 0.50))
            rows.append((month, year, units, round(avg_price, 2),
                         round(avg_days, 1), aged_30, aged_60))
    return rows


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.executescript(SCHEMA)

    vehicles = generate_vehicles(520)
    cur.executemany("""
        INSERT OR IGNORE INTO vehicles
        (vin, make, model, year, color, mileage, condition,
         acquisition_cost, list_price, sale_price, days_in_inventory,
         sale_date, sale_month, sale_year, salesperson, gross_profit, gross_margin_pct)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, vehicles)

    benchmarks = generate_benchmarks(vehicles)
    cur.executemany("""
        INSERT INTO market_benchmarks
        (make, model, year, condition, market_avg_price, benchmark_date)
        VALUES (?,?,?,?,?,?)
    """, benchmarks)

    snapshots = generate_snapshots()
    cur.executemany("""
        INSERT INTO monthly_inventory_snapshot
        (snapshot_month, snapshot_year, total_units, avg_list_price,
         avg_days_listed, aged_units_30plus, aged_units_60plus)
        VALUES (?,?,?,?,?,?,?)
    """, snapshots)

    conn.commit()
    count = cur.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0]
    print(f"Database initialized: {count} vehicle records loaded into {DB_PATH}")
    conn.close()


if __name__ == "__main__":
    main()
