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
    const message = {
      to: body.to,
      subject: body.subject,
      body: body.text || '',
      name: body.fromName || 'Office Connect',
    };
    if (body.html) {
      message.htmlBody = body.html;
    }
    // Calendar emails attach an .ics so a calendar app can add/update the event.
    if (body.attachments && body.attachments.length) {
      message.attachments = body.attachments.map(function (a) {
        return Utilities.newBlob(Utilities.base64Decode(a.base64), a.mimeType, a.name);
      });
    }
    MailApp.sendEmail(message);
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

> **Calendar attachments (since v3.76):** the script above also reads an optional `attachments`
> list so calendar emails can carry an `.ics` file. An older script just ignores it and the email
> still goes out, without the file. To enable it, paste the updated script and redeploy a **New version**.
>
> **Already deployed an earlier version of this script?** Paste the updated
> code in (it adds the `if (body.html) { message.htmlBody = body.html; }`
> block — everything else is unchanged), save, then **Deploy → Manage
> deployments** → pencil icon on your existing deployment → **Version: New
> version** → **Deploy**. Editing the code alone does not update the live
> `/exec` URL.

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
| `mail relay said unauthorized` | `CSS_MAIL_RELAY_SECRET` does not match `SHARED_SECRET` in the script. |
| `mail relay unreachable` | Wrong URL, or it does not end in `/exec`. |
| `Email not sent: the relay answered with a Google sign-in page…` | Web app access is not *Anyone* — Google sent the request to its sign-in page, so the script never ran. On a Google Workspace account the admin may only allow "Anyone within `<domain>`"; that is not enough, since the Space calls the relay without signing in. Redeploy with *Anyone*, or ask the Workspace admin to allow it (since v3.22). |
| `Email not sent: the relay script couldn't run (Apps Script said "…")` | The script has no `doPost` (wrong code pasted), or the deployment was never authorized. Paste the script above, **Deploy → Manage deployments → New version**, and approve the permission prompt. |

Any other 200 response that doesn't parse as JSON — one that came back
through Google's `script.googleusercontent.com/macros/echo` step, even after
the app's own GET retry on the same reply — is **not** reported as a failure
(since v3.07). By
the time any response comes back, `doPost()` has already run and
`MailApp.sendEmail()` has already fired; real-world testing confirmed the
mail is reliably delivered even when this echo step is flaky, so treating it
as a failure only invited an admin to click "Resend email" and genuinely
double-send. It's shown as sent, with a note that delivery wasn't formally
confirmed — check the recipient's inbox. If mail is *actually* not arriving,
that's still almost always the access-not-"Anyone" cause above; confirm with
"Send test to me" on Admin → Email and a look at the Apps Script project's
Executions log (script.google.com → your project → Executions).

Editing the script later requires **Deploy → Manage deployments → edit → New
version** for the change to reach the live URL.

## Quota

Google Workspace accounts can send ~1,500 recipients/day this way (consumer
Gmail: 100). Invites and password resets are nowhere near that.

## Reuse for official document dispatch

Documents uses the same `CSS_MAIL_RELAY_URL` / `CSS_MAIL_RELAY_SECRET` connection. Its durable
per-recipient Gmail receipts require updating the existing project with `apps_script/mail_relay.gs`
and `apps_script/documents_relay.gs`, and enabling the Gmail/Drive advanced services. Legacy mail
requests remain supported. Follow [the upgrade steps](DOCUMENT_MANAGEMENT_SETUP.md#existing-mail-apps-script-project);
keep the existing secret value, deployment URL and sending account. Merely pointing Documents at an
older mail deployment is insufficient: an unqualified `{ok:true}` is not official dispatch evidence.


## Reply-to (since v7.84)

`/admin/email` can set a reply-to address. The relay passes it on if the script contains
`if (body.replyTo) message.replyTo=String(body.replyTo);` right after the `htmlBody` line (it is in
`apps_script/mail_relay.gs`). Replace the script and deploy a new version; an older script ignores the
reply-to and mail still sends.
