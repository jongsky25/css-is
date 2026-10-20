# Activity documents (DPO and invitation): one-time setup

A calendar item can say it needs a **DPO** or an **invitation** (Spot Feedback #136) and offer to draft it in Google
Docs. The app sends the item's details to the same signed relay the travel forms use. The relay fills a Google Doc
template, so the two templates must exist once before **Draft in Google Docs** can work.

Until then the button is shown, and a failed draft says the template has not been set up. Nothing else is affected.

## Steps (an administrator, once)

1. Open the Apps Script project that runs the travel relay (`travel_docs.gs`).
2. Add `apps_script/activity_templates.gs` to the same project (File > New > Script, paste the file).
3. Run `makeActivityTemplates()` as the office mailbox, the same account that runs the travel relay. The first run
   asks for permission to use Drive and Docs.
4. Read the Execution log. Each template reports `all placeholders present` or lists the ones that did not land.
5. No new web-app deployment is needed: the relay already accepts any template key that has a `TPL_<key>` property,
   and this script sets `TPL_dpo` and `TPL_invitation`. If you changed `travel_docs.gs` since the last deployment,
   redeploy it as usual.

`checkActivityTemplates()` re-checks the templates that are already set. Run `makeActivityTemplates()` again any time:
a template that is already set and has every placeholder is kept.

## Restyling a template

Both templates are plain Google Docs in the `_templates` folder under the relay's root folder. Restyle them freely
(letterhead, fonts, wording) and keep the `{{placeholders}}`; a placeholder you remove is left empty on the draft.

| Template | Placeholders |
|---|---|
| `dpo` | `dpo_no`, `dpo_date`, `title`, `purpose`, `dates`, `venue`, `funding_source`, `personnel` (a block), `head_name`, `head_title`, `prepared_by` |
| `invitation` | `date`, `title`, `invited`, `details` (a block), `sender_name`, `sender_title`, `contact`, `head_name`, `head_title` |

## What the app fills in, and what it leaves for you

- The DPO number, DPO date and funding source are left as blank lines to complete by hand. The app never guesses
  a number, a source of funds or a signature.
- The signatory is the Director settings already used by the travel forms (`travel.sig.head_name` and `head_title`).
- The personnel are the people marked as travelling on the item; if none, the people on the item; if none, the person
  drafting.
- An item's private **note** is never copied into a draft.
- The draft is shared with the person who asked for it. Only the choice (needed or not) and the link are stored; the
  content of a draft is built when it is asked for and not kept.
