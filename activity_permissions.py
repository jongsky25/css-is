"""Shared management authority for ordinary activity screens and bounded MCP actions."""
import auth
import storage as st


def can_manage(user, ev, conn=None):
    """Current creator/admin or permitted section-manager team authority."""
    if not user or not ev:
        return False
    if user['role']=='admin' or (bool(ev.get('created_by')) and ev['created_by']==user['username']):
        return True
    if conn is None or not ev.get('id') or not auth.can(user['role'],'manage_event'):
        return False
    scope_path,kind=st.team_scope_for_user(conn,user)
    if kind=='none':return False
    return st.event_in_team_scope(st.event_scope_paths(conn,ev['id']),scope_path)
