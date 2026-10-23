"""Atomic, revision-checked appearance settings in the existing SQLite store."""
import copy
import json
import time
import uuid

import appearance as rules

KEY = "appearance.config"


def init_db(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS appearance_history (
        id INTEGER PRIMARY KEY, created_at INTEGER NOT NULL, actor TEXT NOT NULL,
        action TEXT NOT NULL, snapshot TEXT NOT NULL)""")


def load(conn):
    row = conn.execute("SELECT value FROM app_setting WHERE key=?", (KEY,)).fetchone()
    return rules.normalize(json.loads(row[0])) if row else rules.initial()


def history(conn):
    return [dict(zip(("id", "created_at", "actor", "action"), row)) for row in conn.execute(
        "SELECT id,created_at,actor,action FROM appearance_history ORDER BY id DESC LIMIT 50")]


def mutate(conn, actor, revision, action, data, *, ip=None, now=None):
    import storage as st
    now = int(time.time() if now is None else now)
    try:
        conn.execute("BEGIN IMMEDIATE")
        config = load(conn)
        if str(config["revision"]) != str(revision):
            raise ValueError("Another administrator changed these settings. Reload before saving again.")
        before = json.dumps(config, sort_keys=True)
        if action in ("draft", "publish", "defaults"):
            chosen = rules.from_form(data)
            if action == "draft":
                config["draft"] = chosen
            elif action == "defaults":
                config["default"] = chosen
            else:
                expiry = rules.local_timestamp(data["expires"], data.get("timezone", "Asia/Manila")) if data.get("expires") else None
                if expiry is not None and expiry <= now:
                    raise ValueError("The override end time must be in the future.")
                config["draft"] = chosen
                config["override"] = {"selection": chosen, "expires_at": expiry}
        elif action == "resume":
            config["override"] = None
        elif action == "reset":
            config["override"] = {"selection": copy.deepcopy(config["default"]), "expires_at": None}
        elif action == "event":
            event_id = data.get("event_id") or uuid.uuid4().hex
            existing = next((e for e in config["events"] if e["id"] == event_id), None)
            if data.get("event_id") and not existing:
                raise ValueError("This event no longer exists. Reload the page.")
            if not existing and len(config["events"]) >= 100:
                raise ValueError("Remove an old event before adding another (maximum 100).")
            name = data.get("name", "").strip()
            if not 1 <= len(name) <= 100:
                raise ValueError("Enter an event name of 1–100 characters.")
            zone = data.get("timezone", "Asia/Manila")
            start, end = rules.local_timestamp(data.get("start"), zone), rules.local_timestamp(data.get("end"), zone)
            status = data.get("status")
            if end <= start:
                raise ValueError("The event must end after it starts.")
            if status not in ("draft", "published", "disabled"):
                raise ValueError("Choose draft, published, or disabled.")
            event = {"id": event_id, "name": name, "timezone": zone, "start": start, "end": end,
                     "status": status, "selection": rules.from_form(data)}
            config["events"] = [e for e in config["events"] if e["id"] != event_id] + [event]
        elif action == "delete_event":
            if not any(e["id"] == data.get("event_id") for e in config["events"]):
                raise ValueError("This event no longer exists. Reload the page.")
            config["events"] = [e for e in config["events"] if e["id"] != data.get("event_id")]
        elif action == "restore":
            row = conn.execute("SELECT snapshot FROM appearance_history WHERE id=?", (data.get("history_id"),)).fetchone()
            if not row:
                raise ValueError("That history entry is unavailable.")
            restored = rules.normalize(json.loads(row[0]))
            # Restoration is a new publication, with current revision and a fresh audit entry.
            restored["revision"] = config["revision"]
            config = restored
        else:
            raise ValueError("Choose a supported appearance action.")
        rules.validate_events(config["events"])
        config["revision"] += 1
        after = json.dumps(config, sort_keys=True)
        conn.execute("INSERT INTO app_setting(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (KEY, after))
        # Drafts are audited, but only public configuration changes are restorable.
        if action != "draft":
            if not conn.execute("SELECT 1 FROM appearance_history LIMIT 1").fetchone():
                conn.execute("INSERT INTO appearance_history(created_at,actor,action,snapshot) VALUES (?,?,?,?)",
                             (now, actor, "Before first change", before))
            conn.execute("INSERT INTO appearance_history(created_at,actor,action,snapshot) VALUES (?,?,?,?)", (now, actor, action, after))
        st.audit(conn, actor, "appearance_" + action, target_type="appearance", target_id=config["revision"],
                 summary="Updated page theme and avatar styling", before=before, after=after, ip=ip, commit=False)
        conn.commit()
        return config
    except Exception:
        conn.rollback()
        raise
