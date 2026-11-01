"""Independent, stdlib-only Office Connect checks and deduplicated incidents.

Runs on trusted main in GitHub Actions, independently of the app host. Never
prints response bodies, credentials, private record contents or exception text.
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE = 'https://equityinhealth-office-connect.hf.space'
REPO = 'jongsky25/css-is'
OWNER = 'jongsky25'
LABEL = 'office-connect-monitor'
SIGNALS = ('uptime', 'backup', 'audit', 'monitor')
NAMES = {'uptime': 'App unavailable', 'backup': 'Backup checks need attention',
         'audit': 'New audit failure', 'monitor': 'Monitoring checks unavailable'}
LIMIT = 32768


class CheckUnavailable(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def read_json(response, limit=LIMIT):
    body = response.read(limit + 1)
    if len(body) > limit:
        raise CheckUnavailable()
    value = json.loads(body)
    if not isinstance(value, (dict, list)):
        raise CheckUnavailable()
    return value


def status_checks(value):
    """Strictly validate the small protocol; unknown is never healthy."""
    if (not isinstance(value, dict) or type(value.get('schema')) is not int
            or value['schema'] != 1 or not isinstance(value.get('version'), str)
            or not re.fullmatch(r'\d+\.\d{2}', value['version'])):
        raise CheckUnavailable()
    checks = value.get('checks')
    allowed = {'durability': {'ok', 'starting', 'failed', 'stale', 'unconfigured'},
               'scheduled_backups': {'ok', 'failed', 'overdue', 'disabled', 'unknown'},
               'audit': {'ok', 'failed'}}
    if not isinstance(checks, dict) or set(checks) != set(allowed):
        raise CheckUnavailable()
    if any(not isinstance(checks[k], str) or checks[k] not in states
           for k, states in allowed.items()):
        raise CheckUnavailable()
    # A boot grace never closes an existing backup incident. A definite failure
    # in either backup signal overrides the other signal's startup grace.
    backup = (False if checks['scheduled_backups'] != 'ok'
              or checks['durability'] in {'failed', 'stale', 'unconfigured'}
              else None if checks['durability'] == 'starting' else True)
    return {'uptime': True, 'backup': backup, 'audit': checks['audit'] == 'ok', 'monitor': True}


class Probe:
    def __init__(self, username, password):
        self.username, self.password = username, password
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()), NoRedirect())
        self.signed_in = False
        self.login_attempted = False

    def request(self, path, fields=None):
        data = urllib.parse.urlencode(fields).encode() if fields is not None else None
        headers = {'User-Agent': 'office-connect-operational-monitor', 'Accept': 'application/json'}
        if fields is not None:
            headers['Origin'] = BASE
        request = urllib.request.Request(BASE + path, data=data, headers=headers)
        return self.opener.open(request, timeout=15)

    def login(self):
        if self.signed_in:
            return
        # Never retry rejected credentials within a run.
        if self.login_attempted or not self.username or not self.password:
            raise CheckUnavailable()
        self.login_attempted = True
        try:
            with self.request('/login', {'username': self.username, 'password': self.password,
                                         'next': '/admin/monitoring-status',
                                         'existing_account_only': '1'}) as response:
                status, location = response.status, response.headers.get('Location')
        except urllib.error.HTTPError as response:
            status, location = response.code, response.headers.get('Location')
            response.close()
        if status != 303 or location != '/admin/monitoring-status':
            raise CheckUnavailable()
        self.signed_in = True

    def sample(self):
        try:
            with self.request('/health') as response:
                value = read_json(response)
            if not isinstance(value, dict) or value.get('status') != 'ok' or value.get('db') != 'ok':
                raise CheckUnavailable()
        except Exception:
            return {'uptime': False, 'backup': None, 'audit': None, 'monitor': None}
        if type(value.get('monitoring_protocol')) is not int or value['monitoring_protocol'] != 1:
            return {'uptime': True, 'backup': None, 'audit': None, 'monitor': False}
        try:
            self.login()
            with self.request('/admin/monitoring-status') as response:
                return status_checks(read_json(response))
        except Exception:
            return {'uptime': True, 'backup': None, 'audit': None, 'monitor': False}

    def close(self):
        if self.signed_in:
            try:
                with self.request('/logout', {}) as response:
                    response.read(1024)
            except Exception:
                pass
            self.signed_in = False


class GitHub:
    def __init__(self, token):
        self.token = token
        self.opener = urllib.request.build_opener(NoRedirect())

    def api(self, path, payload=None, method=None):
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request('https://api.github.com/repos/' + REPO + path,
            data=data, method=method, headers={'Authorization': 'Bearer ' + self.token,
                'Accept': 'application/vnd.github+json', 'Content-Type': 'application/json',
                'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'office-connect-monitor'})
        with self.opener.open(request, timeout=20) as response:
            return read_json(response, limit=1024 * 1024)

    def incidents(self):
        result = []
        for page in range(1, 11):
            rows = self.api('/issues?state=open&labels=' + LABEL + f'&per_page=20&page={page}')
            if not isinstance(rows, list):
                raise CheckUnavailable()
            result.extend(r for r in rows if 'pull_request' not in r)
            if len(rows) < 20:
                return result
        raise CheckUnavailable()

    def maintenance(self, now=None):
        """Only an active deploy job gets a bounded ten-minute outage grace.

        Verification suites do not suppress alerts. Missing GitHub evidence does
        not suppress an outage either.
        """
        now = now or datetime.now(timezone.utc)
        try:
            runs = self.api('/actions/workflows/deploy-hf.yml/runs?branch=main&status=in_progress&per_page=5')
            for run in runs['workflow_runs']:
                for job in self.api(f'/actions/runs/{int(run["id"])}/jobs')['jobs']:
                    if job['name'] == 'deploy' and job['status'] == 'in_progress':
                        started = datetime.fromisoformat(job['started_at'].replace('Z', '+00:00'))
                        if 0 <= (now - started).total_seconds() <= 600:
                            return True
        except Exception:
            pass
        return False

    def label(self):
        try:
            self.api('/labels', {'name': LABEL, 'color': 'b60205',
                                'description': 'Content-free operational monitoring incidents'})
        except urllib.error.HTTPError as error:
            # A duplicate label is expected; distinguish it from validation or
            # permission failures by verifying the label exists.
            if error.code != 422:
                raise
            self.api('/labels/' + LABEL)

    def rolling_out(self, sha, now=None):
        """Allow the new private protocol to arrive during its first rollout.

        This holds only the monitor-configuration signal, for at most 90 minutes
        on the exact source commit being deployed. Outages/audit/backup failures
        are not suppressed by this initial protocol-availability grace.
        """
        if not re.fullmatch(r'[a-f0-9]{40}', sha):
            return False
        now = now or datetime.now(timezone.utc)
        try:
            runs = self.api('/actions/workflows/deploy-hf.yml/runs?branch=main&head_sha=' + sha + '&per_page=5')
            for run in runs['workflow_runs']:
                started = datetime.fromisoformat(run['created_at'].replace('Z', '+00:00'))
                if (run.get('head_sha') == sha and run.get('status') in {'queued', 'in_progress'}
                        and 0 <= (now - started).total_seconds() <= 5400):
                    return True
        except Exception:
            pass
        return False


def marker(signal):
    return '<!-- office-connect-monitor:v1:' + signal + ' -->'


def reconcile(github, first, second, run_url, *, maintenance=False, rolling_out=False, test=False):
    """Only two matching observations change incident state; unknown holds it.

    Open incident issues are the durable deduplication record. No app state or
    cache is needed during outages. Closing an issue manually allows a new alert
    on the next confirmed failure.
    """
    github.label()
    existing = github.incidents()
    changed = []
    signals = ('test',) if test else SIGNALS
    for signal in signals:
        active = [r for r in existing if marker(signal) in (r.get('body') or '')
                  and r.get('user', {}).get('login') == 'github-actions[bot]']
        if test and active:
            continue
        state = False if test else second[signal] if first[signal] is second[signal] else None
        if signal == 'uptime' and maintenance:
            state = None
        if signal == 'monitor' and rolling_out and state is False:
            state = None
        if state is False and not active:
            title = 'Monitoring test notification' if test else NAMES[signal]
            body = (marker(signal) + '\n\n' +
                    ('This is an authorized delivery test, not a production incident.' if test else
                     'Two checks, twenty seconds apart, confirmed this operational problem.') +
                    '\n\nReview [System health](' + BASE + '/ops).\n\n[Monitor run](' + run_url +
                    ').\n\n' + ('Close this test issue after confirming delivery on your phone. '
                    if test else 'This issue remains open until two checks confirm recovery. ') +
                    'No private records or provider error text are included.')
            github.api('/issues', {'title': 'Office Connect: ' + title, 'body': body,
                                  'labels': [LABEL], 'assignees': [OWNER]})
            changed.append(signal + ':opened')
        elif state is True and active:
            for issue in active:
                github.api('/issues/' + str(int(issue['number'])), {'state': 'closed',
                           'state_reason': 'completed'}, method='PATCH')
            changed.append(signal + ':recovered')
    return changed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--test-notification', action='store_true')
    args = parser.parse_args()
    # Production credentials are never available to a PR/alternate-branch run.
    if (os.environ.get('GITHUB_REPOSITORY') != REPO
            or os.environ.get('GITHUB_REF') != 'refs/heads/main'):
        raise CheckUnavailable()
    run_id = os.environ.get('GITHUB_RUN_ID', '')
    if not run_id.isdigit():
        raise CheckUnavailable()
    github = GitHub(os.environ['GH_TOKEN'])
    run_url = 'https://github.com/' + REPO + '/actions/runs/' + run_id
    probe = Probe(os.environ.get('CSS_ADMIN_USER', ''), os.environ.get('CSS_ADMIN_PASS', ''))
    try:
        first = probe.sample()
        time.sleep(20)
        second = probe.sample()
    finally:
        probe.close()
    changed = reconcile(github, first, second, run_url,
                        maintenance=github.maintenance(),
                        rolling_out=github.rolling_out(os.environ.get('GITHUB_SHA', '')),
                        test=args.test_notification)
    # Only booleans/null and closed signal names leave the process. App/GitHub
    # error messages, pages and exception details never enter logs/artifacts.
    print(json.dumps({'first': first, 'second': second, 'transitions': changed,
                      'delivery': 'GitHub issue assignment notifications'}))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('Operational monitor could not complete. Check workflow permissions or configuration.')
        raise SystemExit(1)
