"""Small display results shared by one request's navigation and Home builders.

Never a permission grant or a write precondition. Construct after resolving the
current session; keep on request.state only. Each new request starts empty.
Failures are not stored and mutable results are copied for each consumer.
"""
from copy import deepcopy

import storage as st


class RequestReads:
    def __init__(self, user_id):
        self.user_id = user_id
        self._values = {}

    def _read(self, key, user, build):
        if user.get('id') != self.user_id:
            raise ValueError('Request display reads belong to another account.')
        if key not in self._values:
            self._values[key] = build()
        return deepcopy(self._values[key])

    def approvals(self, conn, user):
        return self._read('approvals', user, lambda: st.pending_approval_counts(conn, user))

    def room_admin(self, conn, user):
        import rooms
        return self._read('room_admin', user, lambda: rooms.is_room_admin(conn, user))

    def documents_enabled(self, conn, user):
        import documents
        return self._read('documents_enabled', user, lambda: documents.enabled(conn))

    def document_reviews(self, conn, user):
        import documents
        return self._read('document_reviews', user, lambda:
            documents.count_visible(conn, user, queue='review')
            if self.documents_enabled(conn, user) else 0)

    def work_preview(self, conn, user, today):
        import work_inbox
        return self._read(('work_preview', today.isoformat()), user,
                          lambda: work_inbox.page(conn, user, limit=3, today=today))
