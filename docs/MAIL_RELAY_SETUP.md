# Mail relay setup — sending email from the Hugging Face Space

## Why this exists

The Space's network **blocks outbound SMTP on every port**. Confirmed live:
`smtp.gmail.com:587` and `:465` both hang until the client timeout, while
outbound HTTPS works fine (it is how `ai_core.py` reaches Gemini). A blocked
port times out rather than refusing, which is what a firewall silently
dropping packets looks like.

So no SMTP provider can work here — not Gmail, not Brevo, not any other. Mail
has to leave over HTTPS.

This relay is a ~20-line Google Apps Script bound to the sending mailbox,
deployed as a web app. The Space POSTs the message to it over HTTPS; the
script sends it through Gmail as that mailbox.

Two problems disappear at once:

- **The port block** — it is an ordinary HTTPS request.
- **Deliverability** — the mail genuinely originates from your Google
  Workspace mailbox, so Google signs it (SPF/DKIM/DMARC all already correct
  for `doh.gov.ph`). There are **no DNS records to add**, which is the wall we
  could not get past with a third-party sender.

## Step 1 — create the script

1. Sign in as the mailbox that should send the mail (e.g. `blhsd@doh.gov.ph`).
2. Go to <https://script.google.com> → **New project**.
3. Delete the sample code and paste this in, replacing the placeholder secret
   with a long random string of your own (keep a copy — it goes into the Space
   in step 3):

```javascript
// Office Connect mail relay. Sends as the account that owns this script.
const SHARED_SECRET = 'PUT-A-LONG-RANDOM-STRING-HERE';

function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents);
    if (body.secret !== SHARED_SECRET) {
      return reply({ ok: false, error: 'unauthorized' });
    }
    if (!body.to || !body.subject) {
      return reply({ ok: false, error: 'missing to/subject' });
    }
    MailApp.sendEmail({
      to: body.to,
      subject: body.subject,
      body: body.text || '',
      name: body.fromName || 'Office Connect',
    });
    return reply({ ok: true });
  } catch (err) {
    return reply({ ok: false, error: String(err) });
  }
}

function reply(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
```

4. Name the project something recognisable, e.g. `Office Connect mail relay`.

## Step 2 — deploy it

1. **Deploy** → **New deployment** → gear icon → **Web app**.
2. Set:
   - **Execute as:** *Me* (`blhsd@doh.gov.ph`) — this is what makes the mail
     send as that mailbox.
   - **Who has access:** *Anyone*.
3. **Deploy**, then approve the permission prompt (it asks to send mail as
   you). If Google warns the app is unverified, that is expected for your own
   script — continue via **Advanced** → **Go to … (unsafe)**.
4. Copy the **Web app URL**. It ends in `/exec`.

> "Anyone" means anyone who knows the URL can reach the endpoint, which is why
> it checks `SHARED_SECRET` before sending anything. Treat the URL as a
> secret, and it will only ever send mail to whoever the app asks it to.

## Step 3 — point the Space at it

Space → **Settings** → **Variables and secrets**:

| Name | Type | Value |
|---|---|---|
| `CSS_MAIL_RELAY_URL` | **secret** | the `/exec` web app URL from step 2 |
| `CSS_MAIL_RELAY_SECRET` | **secret** | the same random string you put in the script |
| `CSS_MAIL_RELAY_NAME` | variable | optional display name, default `Office Connect` |

The old `CSS_SMTP_*` values can be deleted — they cannot work on this network.
If both are set the relay wins; SMTP is only kept for networks that allow it
(e.g. the original LAN pilot).

Restart the Space, then test: **Users** → **Send reset link** on any account.

## If something fails

The Users page shows the real reason (since v2.79). The likely ones:

| Message | Cause |
|---|---|
| `mail relay returned HTTP 401/403` | Web app access is not set to *Anyone*. Redeploy with that access level. |
| `mail relay did not return JSON` | Same cause — Google served a sign-in page instead of the script. |
| `mail relay said unauthorized` | `CSS_MAIL_RELAY_SECRET` does not match `SHARED_SECRET` in the script. |
| `mail relay unreachable` | Wrong URL, or it does not end in `/exec`. |

Editing the script later requires **Deploy → Manage deployments → edit → New
version** for the change to reach the live URL.

## Quota

Google Workspace accounts can send ~1,500 recipients/day this way (consumer
Gmail: 100). Invites and password resets are nowhere near that.
