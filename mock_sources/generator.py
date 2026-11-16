"""Deterministic synthetic data for a four-venue hospitality group.

Everything here is invented. Employee records deliberately include the kinds of
sensitive fields real workforce systems return (email, phone, tax file number,
bank details, pay rate) so the PII controls can be demonstrated. A few data
problems are injected on purpose: re-sent (duplicate) transactions, a transaction
whose lines don't sum to the header, and a shift that ends before it starts.
"""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

CUTOFF_HOURS = 4  # trading day ends at 4am local time
GST = Decimal("0.10")

LOCATIONS = [
    # pos id, workforce id, inventory code, name, tz, open hour, close hour (may pass midnight)
    ("pos_loc_8f1a", "1001", "BONDI", "Harbourside Cafe", "Australia/Sydney", 7, 16),
    ("pos_loc_2c7e", "1002", "SURRY", "Laneway Bistro", "Australia/Sydney", 11, 23),
    ("pos_loc_9b3d", "1003", "FITZ", "Northside Kitchen", "Australia/Melbourne", 8, 22),
    ("pos_loc_4e6f", "1004", "SBANK", "Riverfront Bar", "Australia/Brisbane", 16, 26),
]

PRODUCTS = [
    ("Coffee", ["Flat White", "Latte", "Long Black", "Cappuccino", "Chai Latte"], (4.5, 6.0)),
    ("Breakfast", ["Smashed Avo", "Eggs Benedict", "Granola Bowl", "Big Breakfast"], (16, 26)),
    (
        "Mains",
        [
            "Fish & Chips",
            "Chicken Schnitzel",
            "Steak Frites",
            "Mushroom Risotto",
            "Wagyu Burger",
            "Caesar Salad",
        ],
        (22, 42),
    ),
    (
        "Bar",
        [
            "House Lager",
            "Pale Ale",
            "Sauvignon Blanc",
            "Shiraz",
            "Espresso Martini",
            "Margarita",
            "Soft Drink",
        ],
        (6, 22),
    ),
    ("Dessert", ["Sticky Date Pudding", "Pavlova", "Affogato"], (12, 16)),
]

ROLES = ["barista", "chef", "kitchen_hand", "floor_staff", "bartender", "venue_manager"]
FIRST = ["Alex", "Sam", "Jordan", "Taylor", "Casey", "Riley", "Morgan", "Jamie", "Quinn", "Drew"]
LAST = ["Nguyen", "Smith", "Patel", "Brown", "Wilson", "Chen", "Kelly", "Singh", "Martin", "Lee"]


def money(x: float | Decimal) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


@dataclass
class Dataset:
    locations: list[dict] = field(default_factory=list)
    products: list[dict] = field(default_factory=list)
    transactions: list[dict] = field(default_factory=list)
    employees: list[dict] = field(default_factory=list)
    shifts: list[dict] = field(default_factory=list)
    stock_counts: list[dict] = field(default_factory=list)


def generate(end_date: date = date(2026, 11, 15), days: int = 28, seed: int = 42) -> Dataset:
    rng = random.Random(seed)
    ds = Dataset()
    created = datetime(2026, 1, 5, tzinfo=UTC)

    for pos_id, _wf, _inv, name, tz, *_ in LOCATIONS:
        ds.locations.append(
            {
                "location_id": pos_id,
                "name": name,
                "timezone": tz,
                "address": f"{rng.randint(1, 200)} Example St",
                "updated_at": iso(created),
            }
        )

    pid = 0
    for category, names, (lo, hi) in PRODUCTS:
        for n in names:
            pid += 1
            ds.products.append(
                {
                    "product_id": f"prod_{pid:04d}",
                    "sku": f"SKU-{pid:04d}",
                    "name": n,
                    "category": category,
                    "price": str(money(rng.uniform(lo, hi))),
                    "unit_cost": None,
                    "updated_at": iso(created),
                }
            )
    for p in ds.products:
        p["unit_cost"] = str(money(Decimal(p["price"]) * Decimal(str(rng.uniform(0.25, 0.4)))))

    # ---- employees (with sensitive fields a real system would return) ----
    for i in range(1, 37):
        loc = LOCATIONS[(i - 1) % 4]
        first, last = rng.choice(FIRST), rng.choice(LAST)
        ds.employees.append(
            {
                "employee_id": f"EMP{i:04d}",
                "first_name": first,
                "last_name": last,
                "display_name": f"{first} {last[0]}.",
                "email": f"{first.lower()}{i}@example.com",
                "mobile": f"04{rng.randint(10000000, 99999999)}",
                "date_of_birth": "1995-01-01",
                "tax_file_number": "000 000 000",
                "bank_bsb": "000-000",
                "bank_account_number": "00000000",
                "home_address": {"street": "1 Example Rd", "postcode": "2000"},
                "pay_rate": str(money(rng.uniform(28, 45))),
                "role": ROLES[(i - 1) % len(ROLES)],
                "employment_type": rng.choice(["full_time", "part_time", "casual", "casual"]),
                "home_location_id": loc[1],
                "status": "active",
                "start_date": "2025-03-01",
                "manager_id": f"EMP{((i - 1) // 6) * 6 + 1:04d}",
                "updated_at": iso(created + timedelta(days=i)),
            }
        )

    start_day = end_date - timedelta(days=days - 1)
    tx_n = shift_n = 0
    for d in range(days):
        day = start_day + timedelta(days=d)
        weekend = day.weekday() >= 4
        for pos_id, wf_id, _inv, _name, tz, open_h, close_h in LOCATIONS:
            zone = ZoneInfo(tz)
            base = datetime(day.year, day.month, day.day, tzinfo=zone)
            n_tx = int(rng.gauss(95 if weekend else 70, 10))
            for _ in range(n_tx):
                tx_n += 1
                opened = base + timedelta(minutes=rng.uniform(open_h * 60, close_h * 60 - 15))
                lines, total_net, total_tax = [], Decimal(0), Decimal(0)
                for ln in range(1, rng.randint(1, 5) + 1):
                    p = rng.choice(ds.products)
                    qty = rng.choice([1, 1, 1, 2, 2, 3])
                    unit = Decimal(p["price"])
                    discount = (
                        money(unit * qty * Decimal("0.1")) if rng.random() < 0.05 else Decimal(0)
                    )
                    net = money(unit * qty - discount)
                    tax = money(net * GST)
                    total_net += net
                    total_tax += tax
                    lines.append(
                        {
                            "line_id": f"{ln}",
                            "product_id": p["product_id"],
                            "sku": p["sku"],
                            "quantity": qty,
                            "unit_price": str(unit),
                            "discount": str(discount),
                            "tax": str(tax),
                            "net_amount": str(net),
                        }
                    )
                r = rng.random()
                status = "voided" if r < 0.01 else "refund" if r < 0.02 else "completed"
                if status == "refund":
                    for li in lines:
                        for k in ("net_amount", "tax", "discount"):
                            li[k] = str(-Decimal(li[k]))
                        li["quantity"] = -li["quantity"]
                    total_net, total_tax = -total_net, -total_tax
                closed = opened + timedelta(minutes=rng.randint(2, 70))
                ds.transactions.append(
                    {
                        "transaction_id": f"txn_{tx_n:07d}",
                        "location_id": pos_id,
                        "register_id": f"reg_{rng.randint(1, 3)}",
                        "staff_id": f"EMP{rng.randint(1, 36):04d}",
                        "status": status,
                        "channel": rng.choice(["dine_in", "dine_in", "takeaway", "delivery"]),
                        "opened_at": iso(opened),
                        "closed_at": iso(closed),
                        "total_net": str(total_net),
                        "total_tax": str(total_tax),
                        "line_items": lines,
                        "customer": {"email": "guest@example.com"} if rng.random() < 0.1 else None,
                        "card": {"card_last4": "4242"} if rng.random() < 0.6 else None,
                        "updated_at": iso(closed + timedelta(minutes=1)),
                    }
                )

            # ---- shifts ----
            staff = [e for e in ds.employees if e["home_location_id"] == wf_id]
            for emp in staff:
                if rng.random() < (0.85 if weekend else 0.7):
                    shift_n += 1
                    start = base + timedelta(hours=open_h - 1 + rng.choice([0, 0, 2, 4]))
                    hours = rng.choice([4, 5, 6, 7.5, 8, 9])
                    end = start + timedelta(hours=hours)
                    brk = 30 if hours >= 5 else 0
                    rate = Decimal(emp["pay_rate"]) * (
                        Decimal("1.25") if emp["employment_type"] == "casual" else 1
                    )
                    cost = money(rate * Decimal(str(hours - brk / 60)))
                    ds.shifts.append(
                        {
                            "shift_id": f"sh_{shift_n:06d}",
                            "employee_id": emp["employee_id"],
                            "location_id": wf_id,
                            "start_at": iso(start),
                            "end_at": iso(end),
                            "break_minutes": brk,
                            "role": emp["role"],
                            "hourly_rate": emp["pay_rate"],
                            "labour_cost": str(cost),
                            "status": "approved" if day < end_date else "pending",
                            "approved_by": emp["manager_id"],
                            "notes": None,
                            "updated_at": iso(end + timedelta(hours=2)),
                        }
                    )

    # ---- injected data problems ----
    dup = dict(ds.transactions[10])  # re-sent with a later updated_at: should dedupe
    dup["updated_at"] = iso(datetime.fromisoformat(dup["updated_at"]) + timedelta(minutes=5))
    ds.transactions.append(dup)
    ds.transactions.append(dict(ds.transactions[20]))  # exact duplicate
    bad = dict(ds.transactions[30])
    bad["transaction_id"], bad["total_net"] = "txn_BROKEN01", "999.99"  # lines don't sum
    ds.transactions.append(bad)
    bad_shift = dict(ds.shifts[5])
    bad_shift["shift_id"], bad_shift["end_at"] = "sh_BROKEN1", bad_shift["start_at"]
    ds.shifts.append(bad_shift)

    # ---- weekly stock counts (Monday 3am export) ----
    for d in range(days):
        day = start_day + timedelta(days=d)
        if day.weekday() != 0:
            continue
        for _pos, _wf, inv_code, *_ in LOCATIONS:
            for p in ds.products:
                ds.stock_counts.append(
                    {
                        "location_code": inv_code,
                        "sku": p["sku"],
                        "counted_on": day.isoformat(),
                        "quantity_on_hand": rng.randint(0, 120),
                        "unit_cost": p["unit_cost"],
                        "export_file": f"stock_counts_{day:%Y%m%d}T0300.csv",
                    }
                )
    return ds


def business_date(ts_iso: str, tz: str) -> date:
    local = datetime.fromisoformat(ts_iso).astimezone(ZoneInfo(tz))
    return (local - timedelta(hours=CUTOFF_HOURS)).date()


def daily_sales_report(ds: Dataset, on: date) -> list[dict]:
    """What the POS vendor's own 'daily sales' report would say (for reconciliation)."""
    tz = {loc["location_id"]: loc["timezone"] for loc in ds.locations}
    latest = {
        t["transaction_id"]: t for t in ds.transactions if t["transaction_id"] != "txn_BROKEN01"
    }
    out = {
        loc_id: {"pos_location_id": loc_id, "net_sales": Decimal(0), "transaction_count": 0}
        for loc_id in tz
    }
    for t in latest.values():
        if t["status"] == "voided" or business_date(t["opened_at"], tz[t["location_id"]]) != on:
            continue
        row = out[t["location_id"]]
        row["net_sales"] += Decimal(t["total_net"])
        if t["status"] == "completed":
            row["transaction_count"] += 1
    return [{**r, "net_sales": str(r["net_sales"])} for r in out.values()]


def write_sftp_drop(ds: Dataset, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    by_file: dict[str, list[dict]] = {}
    for row in ds.stock_counts:
        by_file.setdefault(row["export_file"], []).append(row)
    for name, rows in by_file.items():
        with (directory / name).open("w", newline="") as fh:
            w = csv.DictWriter(
                fh,
                fieldnames=["Location_Code", "SKU", "Counted_On", "Quantity_On_Hand", "Unit_Cost"],
            )
            w.writeheader()
            for r in rows:
                w.writerow(
                    {
                        "Location_Code": r["location_code"],
                        "SKU": r["sku"],
                        "Counted_On": r["counted_on"],
                        "Quantity_On_Hand": r["quantity_on_hand"],
                        "Unit_Cost": r["unit_cost"],
                    }
                )


if __name__ == "__main__":
    data = generate()
    write_sftp_drop(data, Path(__file__).parent / "sftp_drop")
    print(
        f"{len(data.transactions)} transactions, {len(data.shifts)} shifts, "
        f"{len(data.employees)} employees, {len(data.stock_counts)} stock count rows"
    )
