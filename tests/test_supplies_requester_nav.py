"""Increment 1.1: requester-only users get the three-link Supplies navigation."""
import re

from starlette.testclient import TestClient

import auth
from tests.test_supplies import supplies_db, setup_catalog
from tests.conftest import session_token

REQUESTER_LINKS = ['/supplies', '/supplies/requests/new', '/supplies/requests']


def nav_links(html):
    nav = re.search(r'<nav class="supply-actions".*?</nav>', html, re.S).group(0)
    return re.findall(r'href="([^"]+)"', nav)


def test_requester_sees_three_links_and_custodian_nav_unchanged(supplies_db, app_mod):
    c, u, _, path = supplies_db
    setup_catalog(c, u)
    old = app_mod.DB
    app_mod.DB = path
    try:
        with TestClient(app_mod.app) as client:
            client.cookies.set(auth.COOKIE_NAME, session_token(u[2]))
            page = client.get('/supplies')
            assert page.status_code == 200
            assert nav_links(page.text) == REQUESTER_LINKS
            client.cookies.set(auth.COOKIE_NAME, session_token(u[1]))
            links = nav_links(client.get('/supplies').text)
            assert links[:2] == ['/supplies', '/supplies/items']
            assert '/supplies/issuance' in links and len(links) > 3
    finally:
        app_mod.DB = old
