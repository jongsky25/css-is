# Meal requests and room booking dates

Conference room requests may be made on the activity date when the requested
hours are available. Approval, conflicts, closures, booking horizons and guest
limits still apply. A short-notice reason is no longer required when staff encode
a room booking.

Meals require at least two **calendar days** before the activity date, using
Philippine local dates. For example, a Thursday activity can be requested through
Tuesday. Weekends and holidays count toward meal notice. The server validates
this rule when submitting a request or adding meals to an existing room booking.
Existing orders can still be tracked and marked delivered on the activity date.

## Requesting and monitoring meals

- **Office → Request meals** (`/meals/new`) accepts an activity title, date,
  venue/delivery location, pax, dietary needs, and selected meals with delivery
  times. It requires no room reservation or room approval.
- **Office → My meal requests** (`/meals/mine`) lists the requester's own requests,
  including past requests, and links to existing room-based meal forms.
- Each request has its own `MR-` reference and detail page showing the status,
  update time, updater and note for each meal. The owner can withdraw it.
- Administrative Section members use **Office → Meal requests** (`/meals`) to
  order and track meals. Requests begin at **Awaiting order**, then progress to
  **Ordered**, **Delivered**, **Not delivered**, or **Cancelled**.
- Withdrawals preserve delivered records and cancel outstanding meal lines.
  A withdrawal after ordering flags the need to cancel with the supplier.

The new `meal_request` and `meal_request_item` tables are created idempotently at
database initialization. They contain no room foreign keys and create no room
slots. Existing room meal records are preserved with their original forms and
ordering workflow; they are visible through links in the new requester and
management lists. New standalone meal requests use the separate flow above.

Owners can see only their own requests. Ordering and delivery updates use the
existing Administrative Section membership check; an app administrator role
alone does not confer this permission. Submissions, status updates and
withdrawals are audited. Status monitoring is available on the request pages;
standalone requests do not send email notifications.
