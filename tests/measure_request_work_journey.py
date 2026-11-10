"""Opt-in synthetic measurement of the request-to-work journey; not collected by the suite.

Run explicitly: cloud_workspace.py test tests/measure_request_work_journey.py -s
The same file runs unchanged on any revision so the shipped baseline (a21044a, before
10.15) and the current tree are compared on identical disposable fixtures. A simulated
person only follows links and submits forms present in the returned HTML; there is no
browser history or back button. No real data, provider, browser or notification is used.

Metric: the minimum number of link clicks, found by breadth-first search over same-origin
GET links, needed to reach a goal page from the page the person is on. None means the goal
was not reachable within MAX_DEPTH clicks, which is what a person would experience as
"start over from the top".
"""
import html
import json
import re
from collections import deque
from urllib.parse import urlsplit

import documents_navigation as nav
from test_document_request_work_routes import proposal_record, payload
from test_document_understanding_review_routes import review_record
from test_documents_routes import token

ORIGIN = '/documents/actions?view=mine&step_state=waiting&overdue=1'
MAX_DEPTH = 4
MAX_PAGES = 120
SKIP = ('/static/', '/logout', '/api/', 'mailto:', '.png', '.css', '.js')


def links(page_text):
    found = []
    for raw in re.findall(r'href="([^"#][^"]*)"', page_text):
        href = html.unescape(raw)
        if href.startswith('/') and not href.startswith('//') and not any(s in href for s in SKIP):
            found.append(href)
    return found


def key(url):
    parts = urlsplit(url)
    return parts.path + ('?' + parts.query if parts.query else '')


def shortest(viewer, start, goals, max_depth=MAX_DEPTH):
    """Minimum clicks from `start` to each goal predicate; None if unreachable."""
    result = {name: None for name in goals}
    result['_pages_explored'] = 0
    seen = {key(start)}
    queue = deque([(start, 0)])
    pages = 0
    while queue and any(result[n] is None for n in goals):
        url, depth = queue.popleft()
        for name, goal in goals.items():
            if result[name] is None and goal(url):
                result[name] = depth
        if depth >= max_depth:
            continue
        if pages >= MAX_PAGES:
            result['_page_cap_hit'] = True
            continue
        response = viewer.get(url, follow_redirects=False)
        pages += 1
        result['_pages_explored'] = pages
        if response.status_code != 200:
            continue
        for href in links(response.text):
            if key(href) not in seen:
                seen.add(key(href))
                queue.append((href, depth + 1))
    for name, goal in goals.items():
        # A goal can be the final page of the search without having been expanded.
        if result[name] is None and any(goal(u) for u, _ in queue):
            result[name] = min(d for u, d in queue if goal(u))
    return result


def test_measure_request_work_journey(proposal_record, viewer):
    c, u, doc, unit, url = proposal_record
    assert viewer.post(url, data=payload(viewer.get(url), doc, unit), follow_redirects=False).status_code == 303
    case_id, task_id = c.execute('SELECT case_id,task_id FROM document_request_work').fetchone()
    c.execute('UPDATE work_case SET lead_id=? WHERE id=?', (u['id'], case_id)); c.commit()
    receipt_path = f"/documents/{doc['id']}/requests/0/work"
    start = nav.record_url(url, ORIGIN)

    def is_receipt(candidate): return urlsplit(candidate).path == receipt_path
    def is_exact_receipt(candidate): return key(candidate) == key(start)
    def is_exact_queue(candidate):
        parts = urlsplit(candidate)
        return parts.path == '/documents/actions' and all(p in parts.query for p in ('step_state=waiting', 'overdue=1'))

    goals = {'receipt_any': is_receipt, 'receipt_with_context': is_exact_receipt, 'filtered_queue': is_exact_queue}
    result = {'revision_has_request_work_url': hasattr(nav, 'request_work_url')}

    # Journey A: inspect the work from the reviewed request, then come back.
    receipt = viewer.get(start)
    open_links = [h for h in links(receipt.text) if h.startswith(f'/work/{case_id}')]
    assert open_links, 'receipt must link to the existing work'
    work_url = open_links[0]
    result['A_receipt_to_work_clicks'] = 1
    result['A_back_from_work'] = shortest(viewer, work_url, goals)
    work_links = links(viewer.get(work_url).text)
    # Deterministic companion to the bounded search: does any link on the work page
    # itself carry the person's queue filter or point to the exact receipt context?
    result['A_work_page_links_total'] = len(work_links)
    result['A_work_page_links_carrying_queue_filter'] = sum('step_state=waiting' in h for h in work_links)
    result['A_work_page_links_to_exact_receipt'] = sum(key(h) == key(start) for h in work_links)

    # Journey C: screens outside the 10.15 slice, reached from the work page. Two clicks
    # of search is enough to show whether the request/queue context survives there.
    result['C_other_screens'] = {}
    for name, fragment in (('discussion', '/discussion'), ('handoff', '/draft'), ('completion', '/completion')):
        target = next((h for h in links(viewer.get(work_url).text) if fragment in h), None)
        if target is None:
            result['C_other_screens'][name] = 'no link found'
            continue
        found = shortest(viewer, target, goals, max_depth=2)
        found.pop('_pages_explored', None); found.pop('_page_cap_hit', None)
        carried = [h for h in links(viewer.get(target).text) if 'step_state=waiting' in h or 'source_task=' in h]
        found['links_on_screen_carrying_context'] = len(carried)
        result['C_other_screens'][name] = found

    # Journey B: update a contribution on the work page, then come back.
    work_page = viewer.get(work_url)
    action = next(html.unescape(m) for m in re.findall(r'action="([^"]+/milestone[^"]*)"', work_page.text))
    revision = c.execute('SELECT revision FROM work_task WHERE id=?', (task_id,)).fetchone()[0]
    saved = viewer.post(action, data={'csrf': token(work_page), 'revision': str(revision),
                                      'due_date': '2026-11-19', 'reason': 'Measured update'}, follow_redirects=False)
    assert saved.status_code == 303
    landing = saved.headers['location']
    result['B_landing_keeps_request_context'] = 'source_task=' in landing
    result['B_back_after_save'] = shortest(viewer, landing, goals)
    print('REQUEST_WORK_JOURNEY ' + json.dumps(result, sort_keys=True), flush=True)
