"""One-off: close out Spot Feedback #49 (local-only, not shipped).

Shipped in v1.78 (July 2, 2026):
  #49 = "when i close the activity, the report should be automatically generated"
        -> a closed activity's Manage page now shows a prominent "View the report".
Reuses pull_backup's cookie-session login + feedback.py's .env.local creds.
"""
import argparse
import urllib.parse

import pull_backup as pb
import feedback as fb

CLOSEOUTS = [
    (49, "Done",
     "Done in v1.78. When you close an activity, its Manage page now shows a "
     "prominent “View the report →” button right next to Reopen — so closing leads "
     "straight to the results instead of a dead end. It opens the right report for "
     "the activity: the per-activity report for a regular activity, or the Resource "
     "Persons results for an invited / resource-person one. Note the report is live "
     "the moment responses come in, so there's nothing to wait for — closing just "
     "puts the link front and centre. Thanks for the suggestion."),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base")
    ap.add_argument("--user")
    ap.add_argument("--password")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    fb._load_env_local()
    base, user, password = fb._creds(args)
    base = base.rstrip("/")

    opener, _jar = pb._opener()
    pb.login(opener, base, user, password)
    print(f"Logged in to {base} as {user}\n")

    for fid, status, reply in CLOSEOUTS:
        if args.dry_run:
            print(f"[dry-run] #{fid} -> {status}\n    {reply[:80]}...")
            continue
        url = f"{base}/admin/feedback/{fid}"
        resp = pb._post(opener, url, {"status": status, "reply": reply,
                                      "admin_note": "", "back": ""},
                        follow=False)
        loc = resp.headers.get("Location", "")
        ok = getattr(resp, "code", 200) in (302, 303) or "/admin/feedback" in loc
        print(f"#{fid} -> {status}: {'OK' if ok else 'CHECK'} "
              f"(HTTP {getattr(resp, 'code', '?')}, Location={loc})")


if __name__ == "__main__":
    main()
