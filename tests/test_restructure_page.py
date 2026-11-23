"""Admin restructure page: preview changes nothing; apply needs the previewed file,
a ticked confirmation and a backup; everything else is refused."""
from __future__ import annotations

import io
import json

import pytest

import restructure_routes as rr
import storage as st


def upload(client, mapping, raw=None):
    body = raw if raw is not None else json.dumps(mapping).encode()
    return client.post("/admin/restructure/preview",
                       files={"mapping": ("mapping.json", io.BytesIO(body), "application/json")})


def office3(app_mod):
    conn = st.connect(app_mod.DB)
    try:
        bureau = conn.execute("SELECT path FROM org_unit WHERE level='bureau' ORDER BY id LIMIT 1").fetchone()[0]
        return conn.execute("SELECT id FROM org_unit WHERE path=?", (bureau + "/OD3",)).fetchone()
    finally:
        conn.close()


@pytest.fixture()
def backups(monkeypatch):
    made = []

    def fake(db_path, kind="manual"):
        made.append((db_path, kind))
        return {"name": "css_is_20261123_120000_manual.db"}
    monkeypatch.setattr(rr.bk, "make_backup", fake)
    return made


def test_only_administrators_reach_the_page(viewer, admin):
    assert viewer.get("/admin/restructure", follow_redirects=False).status_code in (302, 303, 403)
    page = admin.get("/admin/restructure")
    assert page.status_code == 200 and "Restructure the directory" in page.text


def test_preview_changes_nothing_and_apply_needs_confirmation_and_a_backup(admin, app_mod, backups):
    r = upload(admin, {"staff": []})
    assert r.status_code == 200 and "Preview: ready to apply" in r.text
    assert office3(app_mod) is None                                  # preview rolled back
    digest = json.loads(st.get_setting(st.connect(app_mod.DB), rr.PENDING))["digest"]

    r = admin.post("/admin/restructure/apply", data={"digest": digest})
    assert "Tick the confirmation box" in r.text and office3(app_mod) is None and not backups

    r = admin.post("/admin/restructure/apply", data={"digest": "stale", "confirm": "1"})
    assert "Preview the mapping again" in r.text and office3(app_mod) is None

    r = admin.post("/admin/restructure/apply", data={"digest": digest, "confirm": "1"})
    assert r.status_code == 200 and "The directory was restructured" in r.text
    assert backups and backups[0][1] == "manual" and office3(app_mod) is not None
    assert st.get_setting(st.connect(app_mod.DB), rr.PENDING) in (None, "")


def test_a_failed_backup_changes_nothing(admin, app_mod, monkeypatch):
    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(rr.bk, "make_backup", boom)
    upload(admin, {"staff": []})
    digest = json.loads(st.get_setting(st.connect(app_mod.DB), rr.PENDING))["digest"]
    r = admin.post("/admin/restructure/apply", data={"digest": digest, "confirm": "1"})
    assert "The backup failed, so nothing was changed" in r.text and office3(app_mod) is None


def test_a_stopped_preview_explains_and_offers_no_apply(admin):
    r = upload(admin, {"staff": [{"name": "Nobody Anywhere Here", "unit": "S7"}]})
    assert "Preview stopped" in r.text and "Nobody Anywhere Here" in r.text
    assert "Apply the restructure" not in r.text


@pytest.mark.parametrize("raw", [b"", b"not json", b'["a list"]', b'{"staff": "x"}'])
def test_a_file_that_is_not_a_mapping_is_refused(admin, raw):
    r = upload(admin, None, raw=raw)
    assert r.status_code == 200 and "flash err" in r.text and "Apply the restructure" not in r.text
