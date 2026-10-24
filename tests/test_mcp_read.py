"""A24 requires an actual remote-MCP/OAuth journey, not a mocked tool call."""
from pathlib import Path
import subprocess
import sys

import backups
import mcp_auth
import storage as st


def test_chatgpt_style_oauth_consent_read_and_disconnect():
    root = Path(__file__).resolve().parents[1]
    run = subprocess.run([sys.executable, 'tests/mcp_probe.py'], cwd=root,
                         capture_output=True, text=True, timeout=90)
    assert run.returncode == 0, run.stderr[-3000:]


def test_account_change_and_historical_restore_revoke_mcp_grants(app_mod):
    conn = st.connect(app_mod.DB)
    owner = st.get_admin_user(conn, 'viewer@test.local')['id']
    first = mcp_auth.Provider._tokens(conn, 'synthetic-client', owner, ['work:read'],
                                      'https://office.example/mcp')
    conn.commit()
    assert mcp_auth.current_grant(conn, first.access_token, 'https://office.example/mcp', 'work:read')
    conn.execute("UPDATE admin_user SET role='encoder' WHERE id=?", (owner,))
    conn.commit()
    assert mcp_auth.current_grant(conn, first.access_token, 'https://office.example/mcp', 'work:read') is None
    second = mcp_auth.Provider._tokens(conn, 'synthetic-client', owner, ['work:read'],
                                       'https://office.example/mcp')
    conn.commit(); conn.close()
    backups.clear_restored_sessions(app_mod.DB, revoke_integrations=True)
    conn = st.connect(app_mod.DB)
    assert mcp_auth.current_grant(conn, second.access_token, 'https://office.example/mcp', 'work:read') is None
    conn.close()
