"""Seasonal appearance rules, shared by previews and live pages."""
from contextvars import ContextVar
from datetime import datetime, timezone
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

THEMES = {
    "default": {"name": "Default", "icon": "◉", "description": "The everyday Office Connect appearance."},
    "halloween": {"name": "Halloween", "icon": "🎃", "description": "A haunted office, moonlit skies, pumpkins and full costumes."},
    "christmas": {"name": "Christmas", "icon": "🎄", "description": "Parol lanterns, evergreen warmth and a little Christmas light."},
    "newyear": {"name": "New Year", "icon": "✦", "description": "Midnight blue, warm gold and a Philippine-time countdown."},
}
OUTFITS = {
    "default": {"name": "Default · no accessory", "month": 0},
    "monthly": {"name": "Automatic monthly accessory", "month": None},
    "halloween": {"name": "Halloween · witch hat & cape", "month": 10},
    "halloween_vampire": {"name": "Halloween · vampire cape & collar", "month": 10},
    "halloween_pumpkin": {"name": "Halloween · pumpkin costume", "month": 10},
    "christmas": {"name": "Christmas · Santa", "month": 12},
    "christmas_elf": {"name": "Christmas · Elf helper", "month": 12},
    "christmas_reindeer": {"name": "Christmas · Reindeer", "month": 12},
    "christmas_parol": {"name": "Christmas · Parol keeper", "month": 12},
    "christmas_knit": {"name": "Christmas · Festive knit", "month": 12},
}
current = ContextVar("seasonal_appearance", default=None)
BANNER = "A little spooky. Still productive."


BANNERS = {"default": "", "halloween": BANNER,
           "christmas": "A season of gratitude. A little brighter together.",
           "newyear": "A brighter year, together."}


def newyear_target(year):
    return int(datetime(year, 1, 1, tzinfo=ZoneInfo("Asia/Manila")).timestamp())


def selection(theme="default", outfit="monthly", effects=False, artwork=None, banner="", target_year=2027):
    if theme not in THEMES or outfit not in OUTFITS:
        raise ValueError("Choose a listed theme and avatar outfit.")
    if not isinstance(banner, str) or len(banner.strip()) > 100:
        raise ValueError("Keep the seasonal banner message to 100 characters.")
    try:
        if isinstance(target_year, bool) or str(int(target_year)) != str(target_year) or not 2027 <= int(target_year) <= 2100:
            raise ValueError()
        target_year = int(target_year)
    except (ValueError, TypeError, OverflowError):
        raise ValueError("Choose a New Year target from 2027 to 2100.") from None
    return {"theme": theme, "outfit": outfit, "effects": bool(effects),
            "artwork": theme != "default" if artwork is None else bool(artwork),
            "banner": banner.strip() or BANNERS[theme], "target_year": target_year}


def from_form(data):
    artwork = data.get("artwork") == "1" if data.get("artwork_present") == "1" else None
    return selection(data.get("theme"), data.get("outfit"), data.get("effects") == "1", artwork, data.get("banner", ""), data.get("target_year", "2027"))


def normalize(config):
    """Supply the new visual controls for previously saved settings/snapshots."""
    for key in ("default", "draft"):
        config[key] = selection(**config[key])
    if config["override"]:
        config["override"]["selection"] = selection(**config["override"]["selection"])
    for event in config["events"]:
        event["selection"] = selection(**event["selection"])
    return config


def avatar_outfit():
    active = current.get()
    return active["outfit"] if active else "monthly"


def initial():
    return {"revision": 0, "default": selection(), "draft": selection(), "override": None, "events": []}


def local_timestamp(value, zone="Asia/Manila"):
    try:
        tz = ZoneInfo(zone)
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is not None:
            raise ValueError()
        # Reject ambiguous/nonexistent local times rather than silently shifting them.
        first = dt.replace(tzinfo=tz, fold=0)
        second = dt.replace(tzinfo=tz, fold=1)
        if first.utcoffset() != second.utcoffset():
            raise ValueError()
        if first.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None) != dt:
            raise ValueError()
        return int(first.timestamp())
    except (ValueError, TypeError, OverflowError, ZoneInfoNotFoundError):
        raise ValueError("Enter a valid, unambiguous local date and time in the selected timezone.") from None


def date_label(value, zone="Asia/Manila", *, form=False):
    if value is None:
        return "Until turned off"
    dt = datetime.fromtimestamp(value, timezone.utc).astimezone(ZoneInfo(zone))
    return dt.strftime("%Y-%m-%dT%H:%M" if form else "%b %d, %Y · %H:%M")


def accessory_month(outfit=None, now=None):
    active = current.get()
    if outfit is None and active is not None:
        return active["month"]
    outfit = outfit or "monthly"
    month = OUTFITS[outfit]["month"]
    if month is not None:
        return month
    return datetime.fromtimestamp(time.time() if now is None else now, ZoneInfo("Asia/Manila")).month


def resolve(config, now=None):
    now = time.time() if now is None else now
    chosen, source, event_name = config["default"], "default", None
    override = config["override"]
    active_override = override and (override["expires_at"] is None or override["expires_at"] > now)
    events = [e for e in config["events"] if e["status"] == "published"]
    for event in events:
        if event["start"] <= now < event["end"]:
            chosen, source, event_name = event["selection"], "scheduled", event["name"]
            break
    if active_override:
        chosen, source, event_name = override["selection"], "manual", None
    chosen = selection(**chosen)
    boundaries = [t for e in events for t in (e["start"], e["end"]) if t > now]
    if active_override:
        boundaries = [override["expires_at"]] if override["expires_at"] is not None else []
    # Monthly outfits also change at midnight on the first of the month.
    if chosen["outfit"] == "monthly":
        dt = datetime.fromtimestamp(now, ZoneInfo("Asia/Manila"))
        next_month = datetime(dt.year + (dt.month == 12), dt.month % 12 + 1, 1, tzinfo=dt.tzinfo).timestamp()
        boundaries.append(next_month)
    return {**chosen, "source": source, "event_name": event_name,
            "theme_name": THEMES[chosen["theme"]]["name"], "outfit_name": OUTFITS[chosen["outfit"]]["name"],
            "override_expires_at": override["expires_at"] if active_override else None,
            "revision": config["revision"], "month": accessory_month(chosen["outfit"], now),
            "next_transition": min(boundaries) if boundaries else None, "preview": False,
            "server_time": now, "newyear_target": newyear_target(chosen["target_year"])}


def validate_events(events):
    for event in events:
        chosen = event["selection"]
        if chosen["theme"] == "newyear" and not event["start"] <= newyear_target(chosen["target_year"]) < event["end"]:
            raise ValueError("A New Year event must include midnight January 1 of its target year (Asia/Manila).")
    published = sorted((e for e in events if e["status"] == "published"), key=lambda e: e["start"])
    for previous, event in zip(published, published[1:]):
        if event["start"] < previous["end"]:
            raise ValueError(f'Schedule overlaps with “{previous["name"]}”. Change its dates or disable it first.')
