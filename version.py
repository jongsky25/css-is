"""Application version + plain-language changelog.

SINGLE SOURCE OF TRUTH for the version number shown on the sign-in screen.

────────────────────────────────────────────────────────────────────────
HOW TO BUMP (do this on EVERY push that changes what people see/use)
────────────────────────────────────────────────────────────────────────
1. Raise APP_VERSION by one step:
     • small change / fix .......... bump the minor:  1.1 → 1.2 → 1.3 …
     • big release / milestone ..... bump the major:  1.9 → 2.0
2. Prepend a NEW entry to the TOP of CHANGELOG (newest first) describing
   the change in LAYMAN terms — no jargon, written for the people who use
   the system, not for developers. Keep each bullet to one plain sentence.
3. Use a spelled-out date ("June 17, 2026").

The login page reads APP_VERSION and the newest CHANGELOG entry, so once you
edit this file the "What's new" note updates itself — nothing else to touch.
"""

APP_VERSION = "7.19"

# Newest first. CHANGELOG[0] is what the login screen highlights.
CHANGELOG = [
    {
        "version": "7.19",
        "date": "October 19, 2026",
        "summary": "Keep online activities out of travel claims.",
        "changes": [
            "Online activities no longer appear as travel claim options or show a claim reminder on the calendar.",
            "A travel claim cannot be started from an online activity."
        ]
    },
    {
        "version": "7.18",
        "date": "October 19, 2026",
        "summary": "Draft memoranda, mark PDF pages and search indexed Drive text.",
        "changes": [
            "Download an editable memorandum draft from an outgoing document.",
            "Add page notes or pen marks checked against the same PDF version in Drive.",
            "Explicitly index a file version to search its text within current document access."
        ]
    },
    {
        "version": "7.17",
        "date": "October 19, 2026",
        "summary": "Complete the Documents update for deployment.",
        "changes": [
            "Include the new instruction, search and action modules in the deployed app."
        ]
    },
    {
        "version": "7.16",
        "date": "October 19, 2026",
        "summary": "Find document instructions, saved text and your next steps.",
        "changes": [
            "Tag people and sections in document instructions and see unread tags in your queue.",
            "Search document details, references, receipts, instructions and saved email bodies.",
            "Open My actions for contributions, reviews and lead follow-up; division chiefs can see division exceptions."
        ]
    },
    {
        "version": "7.15",
        "date": "October 19, 2026",
        "summary": "Improve authentication when importing Gmail email text.",
        "changes": [
            "The Gmail importer signs the exact bytes it sends to Office Connect.",
            "Failed imports can be retried using their existing receipts without duplicating queued documents."
        ]
    },
    {
        "version": "7.14",
        "date": "October 19, 2026",
        "summary": "Read Gmail email bodies and attachments returned as byte arrays.",
        "changes": [
            "The updated Gmail importer accepts byte arrays and encoded text while retaining attachment size and checksum checks.",
            "A manual recovery action retries failed content reads using their existing checkpoints.",
            "Replace gmail_documents_import.gs in the existing mail Apps Script project to activate this fix."
        ]
    },
    {
        "version": "7.13",
        "date": "October 19, 2026",
        "summary": "Connect work email to the document review queue from Intake settings.",
        "changes": [
            "Records and workflow administrators can set the Gmail mailbox, select a records owner and enable or pause email intake.",
            "Setup checks the hosting secret and review queue before enabling intake, while keeping the secret hidden.",
            "Email importing still starts from the existing Apps Script project after a successful manual test."
        ]
    },
    {
        "version": "7.12",
        "date": "October 19, 2026",
        "summary": "Read the document date beside the originating office on routing slips.",
        "changes": [
            "Routing-slip OCR uses the date beside Originating office, so later routing entries and enclosed-page dates do not override it.",
            "Unreadable or conflicting routing-slip header dates remain for your review."
        ]
    },
    {
        "version": "7.11",
        "date": "October 19, 2026",
        "summary": "Review intake documents comfortably on monitors, laptops, tablets and phones.",
        "changes": [
            "Larger screens use a wider document-and-form workspace; smaller tablets stack the panels.",
            "Phones can switch between Document and Review details without losing entered values.",
            "OCR suggestions collapse above the fields, while Save review and Register document remain accessible during scrolling."
        ]
    },
    {
        "version": "7.10",
        "date": "October 19, 2026",
        "summary": "Determine document direction from the originating office.",
        "changes": [
            "Documents from the Bureau of Local Health Systems Development or BLHSD are classified as Outgoing; other identified senders are Incoming.",
            "The rule applies to saved reviews, OCR suggestions and registration, including documents received through email."
        ]
    },
    {
        "version": "7.09",
        "date": "October 19, 2026",
        "summary": "Capture more document details from routing slips and refresh OCR suggestions.",
        "changes": [
            "OCR recognizes originating office, type of document, document date and DTRAK reference labels, including values split across lines.",
            "Clear numeric and written dates become suggestions; conflicting dates and old routing-history deadlines still need review.",
            "Read scan again with OCR refreshes saved suggestions while keeping the details you already entered."
        ]
    },
    {
        "version": "7.08",
        "date": "October 19, 2026",
        "summary": "Check intake document contents during OCR without blocking on metadata changes.",
        "changes": [
            "Intake OCR checks the file checksum and the bytes read before accepting suggestions, while allowing metadata-only Drive version changes.",
            "Actual file-content changes still stop OCR; approval and signing keep their strict version checks.",
            "OCR errors now also appear beside the review controls, and disabled fields explain how to start a review."
        ]
    },
    {
        "version": "7.07",
        "date": "October 19, 2026",
        "summary": "Fix Drive intake checks that failed while reading Google’s reply.",
        "changes": [
            "Compressed Google replies are now decoded once, fixing the application error that appeared as an unreachable relay.",
            "The fix preserves response-size checks and does not repeat signed requests."
        ]
    },
    {
        "version": "7.06",
        "date": "October 19, 2026",
        "summary": "Identify the network problem behind a failed document intake connection.",
        "changes": [
            "Drive intake now distinguishes DNS, proxy, certificate and connection failures without displaying private network details.",
            "The diagnostic identifies whether the failure occurred at the Docs web app or Google’s reply service."
        ]
    },
    {
        "version": "7.05",
        "date": "October 19, 2026",
        "summary": "See the specific reason when the document intake Drive check fails.",
        "changes": [
            "Intake now explains missing relay configuration, rejected connections, outdated deployments and folder-setting mismatches instead of showing one generic error.",
            "Queued reviews are retained when a connection fails, and the message clears after the next successful check."
        ]
    },
    {
        "version": "7.04",
        "date": "October 19, 2026",
        "summary": "Review documents from office Drive and Gmail, then route them digitally.",
        "changes": [
            "Office uploads and Gmail messages enter one review queue before receiving a document number.",
            "Reviewers can preview files, save document details, use OCR suggestions and keep email attachments together.",
            "Emails without attachments appear in an Email body box marked No attachment, including after registration.",
            "Confirmed documents are numbered, renamed and filed by year and Incoming or Outgoing direction.",
            "Incoming documents wait for the Director’s digital routing instructions before staff assignments begin.",
            "The Intake menu requires Documents records access; enabling its folder settings also requires workflow-administrator access.",
            "The workflow uses the existing office Drive folders and must be configured before use; Gmail auto-pull stays paused during setup."
        ]
    },
    {
        "version": "7.03",
        "date": "October 19, 2026",
        "summary": "Review office uploads and emails, then issue digital routing instructions beside the document.",
        "changes": [
            "Configured office Drive folders feed a review queue with saved details and OCR suggestions.",
            "Reviewed scans receive a document number and are filed automatically with a visible retry status.",
            "The Director can read an incoming document, write instructions and send it to the concerned staff from one workspace.",
        ],
    },
    {
        "version": "7.02",
        "date": "October 17, 2026",
        "summary": "Documents workflow administrators can now archive finished records.",
        "changes": [
            "Archive a closed or cancelled document with a reason, and find it later in the Archive queue.",
            "Archived documents keep their history and can be restored when more work is needed.",
        ],
    },
    {
        "version": "7.01",
        "date": "October 17, 2026",
        "summary": "Choose how a document was received from a dropdown.",
        "changes": [
            "When registering a document or recording another receipt, choose Email, Gmail, Hand-delivered, Courier, DTRAK, or Other instead of typing the receipt channel.",
        ],
    },
    {
        "version": "7.00",
        "date": "October 17, 2026",
        "summary": "Travel forms now show the certifying officer's own title.",
        "changes": [
            "The certifying officer on the travel forms is shown with their plantilla title (for example Medical Officer V) instead of \"Division Chief\".",
            "The Director, including an OIC-Director, and the filer's division head are still picked from the directory.",
        ],
    },
    {
        "version": "6.99",
        "date": "October 17, 2026",
        "summary": "The rating statements on the service feedback form now read exactly as on the official form.",
        "changes": [
            "Statements 6, 7 and 8 now use the official wording, including \"(if asked for help)\" and \"(if denied)\".",
            "The same wording shows on the online form, the paper-entry form and the official report. The Filipino version says the same.",
        ],
    },
    {
        "version": "6.98",
        "date": "October 17, 2026",
        "summary": "See the names of the people who responded, straight from an activity's report.",
        "changes": [
            "An activity's report now has a See the name list button in the Who responded section, for people who manage that activity.",
            "It opens the activity's roster showing only the registered people who responded, with a link back to everyone.",
            "Walk-in and paper responses have no name, so they are counted but not listed.",
        ],
    },
    {
        "version": "6.97",
        "date": "October 17, 2026",
        "summary": "The online service feedback form now follows the official Client Satisfaction Measurement form.",
        "changes": [
            "The form opens with the official explanation and confidentiality note, and shows today's date.",
            "It now asks the official client questions: client type, sex, age, region of residence and the service availed, and keeps the DOH or non-DOH question. All are optional.",
            "It adds the Citizen's Charter section with its definition and questions CC1 to CC3; if someone does not know what a Citizen's Charter is, CC2 and CC3 are marked Not applicable for them.",
            "There is an optional email field, and the suggestions box now uses the official wording.",
            "These answers now count in the official CSM report, the same as paper forms. Available in English and Filipino.",
        ],
    },
    {
        "version": "6.96",
        "date": "October 17, 2026",
        "summary": "Appendix A and B are drafted from your uploads, and the signers fill themselves in.",
        "changes": [
            "Tickets, boarding passes and receipts you upload are read once, and the itinerary entries are drafted for you to check.",
            "The Certificate of Travel Completed suggests how the travel went from your Certificate of Appearance, and fills the refund receipt details.",
            "The Director and your division head are filled in as the signers, so you no longer type them each time.",
            "When all your attachments are in, the filing page offers to review and make Appendix A and B.",
            "A liquidation now picks up the Appendix A already made for its cash advance, and your DPO date is read from the uploaded DPO.",
        ],
    },
    {
        "version": "6.95",
        "date": "October 17, 2026",
        "summary": "Add more than one ride to a day when preparing travel forms.",
        "changes": [
            "Each itinerary entry now has an Add another ride on this day button, so a plane and a TNVS can both be listed.",
            "Plane entries have quick buttons to add a TNVS ride to or from the airport.",
            "You are warned if two entries on the same day both claim a per diem.",
        ],
    },
    {
        "version": "6.94",
        "date": "October 17, 2026",
        "summary": "No more retyping the per diem when the policy rates already give it.",
        "changes": [
            "When you pick a per diem rule for a day, the amount now comes straight from the policy rates and the Per diem box stays out of the way.",
            "Press Change amount if you want to claim a different figure, or choose to type the per diem yourself.",
        ],
    },
    {
        "version": "6.93",
        "date": "October 17, 2026",
        "summary": "The DPO number is now required on every travel filing.",
        "changes": [
            "Cash advance, liquidation and reimbursement filings all need a Department Personnel Order number before they can be opened or saved.",
            "The lodging question on the travel form now explains that it is about the room cost, not the kind of filing.",
        ],
    },
    {
        "version": "6.92",
        "date": "October 17, 2026",
        "summary": "Fix the break check-in rating buttons and keep your conference room choice.",
        "changes": [
            "On the break check-in, tapping a rating such as 5 now always selects that rating, not its neighbour.",
            "If a calendar form comes back with an error, a conference room you unticked stays unticked.",
        ],
    },
    {
        "version": "6.91",
        "date": "October 17, 2026",
        "summary": "Read DTRAK subjects from their own box and show the source beside the field.",
        "changes": [
            "Locate the DTRAK subject box, straighten slight scan tilt and read its text separately from the routing table.",
            "Keep the successfully read DTRAK subject when checking later pages.",
            "Show the cropped subject box, extracted text and specific reading failures beside the Subject field.",
        ],
    },
    {
        "version": "6.90",
        "date": "October 17, 2026",
        "summary": "Keep complete subjects when pages repeat or wrap the title.",
        "changes": [
            "Recognize Title and Subject/Title headings and wrapped subject lines.",
            "Keep the full subject when another page repeats it with different capitalization or a leading excerpt.",
            "Show genuinely different readings beside the field for review without replacing manual corrections.",
        ],
    },
    {
        "version": "6.89",
        "date": "October 17, 2026",
        "summary": "Read a PDF automatically, edit its details and approve them in one flow.",
        "changes": [
            "Selecting a PDF reads its first page and checks the next page when a DTRAK slip is found.",
            "Read details appear directly in editable fields with visible dates and source evidence.",
            "Approve reviewed details before choosing the work and registering correspondence.",
            "Separate document and routing dates, and check the deadline column when readable.",
        ],
    },
    {
        "version": "6.88",
        "date": "October 17, 2026",
        "summary": "Read DTRAK routing-slip details more accurately.",
        "changes": [
            "Capture the full subject, originating office, document type and tracking number from DTRAK headers.",
            "Separate the header date and flag routing-table details for manual review.",
        ],
    },
    {
        "version": "6.87",
        "date": "October 17, 2026",
        "summary": "Improve mobile PDF page reading and connection failure feedback.",
        "changes": [
            "Send temporary PDF reading requests directly without service worker forwarding.",
            "Keep selected files and completed pages when a connection fails, with clear retry guidance.",
        ],
    },
    {
        "version": "6.86",
        "date": "October 17, 2026",
        "summary": "Choose pages from larger PDFs and read them a few at a time.",
        "changes": [
            "Preview a PDF on your device and select the pages you need without uploading the original file.",
            "See each page finish reading, retry failed pages, or cancel while keeping completed results.",
            "Review suggestions with original page references before registering correspondence.",
        ],
    },
    {
        "version": "6.85",
        "date": "October 17, 2026",
        "summary": "Read larger PDFs up to 20 MiB.",
        "changes": [
            "Select a PDF or read a public PDF link up to 20 MiB without saving an attachment.",
            "The existing page counts and scanned-page reading limits still apply.",
        ],
    },
    {
        "version": "6.84",
        "date": "October 17, 2026",
        "summary": "Prepare Gmail documents for automatic registration and staff review.",
        "changes": [
            "Once configured, selected Gmail attachments can enter the registry without manual downloading and uploading.",
            "Imported documents show their email source and wait for staff verification.",
            "Reviewers can read attachment suggestions while keeping control of confirmed details and deadlines.",
            "Operators can inspect failures, pause importing and retry saved work without creating duplicate records.",
            "Gmail importing stays off until mailbox setup and live acceptance are completed.",
        ],
    },
    {
        "version": "6.83",
        "date": "October 17, 2026",
        "summary": "Keep your selected PDF and see exactly what happened after reading.",
        "changes": [
            "Your selected file stays available until you remove it, so failed readings can be retried.",
            "See how many fields were filled, which entries were kept, and which details still need your review.",
            "If no fields are recognized, the reading opens for inspection and clearly explains that nothing was filled.",
            "Read common labels split across lines and numbered document headings more reliably.",
        ],
    },
    {
        "version": "6.82",
        "date": "October 17, 2026",
        "summary": "See whether your PDF was read and clear it when needed.",
        "changes": [
            "File selection now explains when reading has not started or a file is too large.",
            "Completed readings say whether OCR ran and let you inspect the extracted text.",
            "Remove a selected file or clear its reading without losing your entered form details.",
        ],
    },
    {
        "version": "6.81",
        "date": "October 17, 2026",
        "summary": "Read scanned PDFs to help fill in correspondence details.",
        "changes": [
            "Scanned pages can now be read without saving the PDF or page images.",
            "Review suggested details with page references and an extra reminder to check scanned names, numbers and dates.",
            "Read up to ten scanned pages at a time, or continue entering the details manually.",
        ],
    },
    {
        "version": "6.80",
        "date": "October 17, 2026",
        "summary": "Start correspondence by reading a PDF to help fill in its details.",
        "changes": [
            "The PDF upload is the first field, with a public PDF link option beside the reading controls.",
            "Read a text PDF without saving the file and review suggested details with their page references.",
            "Your existing entries stay unchanged unless you choose a replacement suggestion.",
            "You can skip reading and enter the details manually, including for scanned or protected PDFs.",
        ],
    },
    {
        "version": "6.79",
        "date": "October 17, 2026",
        "summary": "The conference room switches now show up properly on the calendar form.",
        "changes": [
            "Fixed the conference room and meals options appearing as plain, misaligned tick boxes on the add form.",
            "They now show as the large on/off switches, including on phones.",
        ],
    },
    {
        "version": "6.78",
        "date": "October 17, 2026",
        "summary": "Reserving the conference room and asking for meals is now easy to see.",
        "changes": [
            "The conference room option is a clear card with big on/off switches instead of a small hidden line.",
            "You can see at a glance whether the room is free, partly booked or closed on the day you picked.",
            "Hours and the meals option appear only once you switch the room on, and everything is easy to tap on phones and tablets.",
        ],
    },
    {
        "version": "6.77",
        "date": "October 17, 2026",
        "summary": "See where shared work needs management support.",
        "changes": [
            "Find unassigned contributions, blockers and review waits in one support overview.",
            "Open each count to see the work behind it and the recorded reasons for concern.",
            "Keep missing targets separate from overdue work, with counts limited to work you manage and can access.",
        ],
    },
    {
        "version": "6.76",
        "date": "October 17, 2026",
        "summary": "The calendar add and edit form is easier to read and use.",
        "changes": [
            "Fields are grouped into What, When, Where and Who, so the form is shorter and less crowded.",
            "On a computer the form uses two columns; on tablets and phones the fields fit the screen.",
            "Save and Cancel are bigger and stay in view on tablets and phones.",
            "The last repeat date and the meeting link only appear when they are needed.",
        ],
    },
    {
        "version": "6.75",
        "date": "October 17, 2026",
        "summary": "Choose how you keep up with shared-work discussions.",
        "changes": [
            "Find mentions and replies separately from routine updates in discussions you follow.",
            "Keep routine updates out of your bell while tasks and required alerts remain available.",
            "Choose an optional daily or weekly email digest and see its delivery status.",
        ],
    },
    {
        "version": "6.74",
        "date": "October 17, 2026",
        "summary": "Complete shared work with confirmed release and closure evidence.",
        "changes": [
            "Review required contributions, signatures, delivery, acknowledgments and closure in one checklist.",
            "Record a completed outcome only after its requirements are met, with evidence retained in history.",
            "Reopen shared work for follow-up while preserving earlier completion and formal records.",
        ],
    },
    {
        "version": "6.73",
        "date": "October 16, 2026",
        "summary": "Create short links only when you choose to.",
        "changes": [
            "Click Create short link beside a sharing link to use your Short.io allowance.",
            "Opening pages and creating activities no longer create short links automatically.",
            "Existing short links remain available, while old waiting jobs require a click.",
        ],
    },
    {
        "version": "6.72",
        "date": "October 16, 2026",
        "summary": "Public activity links now use Short.io with clearer status messages.",
        "changes": [
            "Share registration and feedback links using blhsd.s.gy when shortening is enabled.",
            "See when shortening is waiting, needs configuration, or will retry.",
            "Previously failed shortening requests are retried through the new service.",
        ],
    },
    {
        "version": "6.71",
        "date": "October 16, 2026",
        "summary": "Review consolidated responses with clear inputs and retained feedback.",
        "changes": [
            "See accepted and outstanding contributions beside the exact outgoing draft version.",
            "Find consolidation context in Approvals and retain feedback when a draft is returned.",
            "Require renewed review when recorded inputs or the reviewed draft change.",
        ],
    },
    {
        "version": "6.70",
        "date": "October 16, 2026",
        "summary": "Coordinate team contributions in shared list and board views.",
        "changes": [
            "Filter team contributions by unit, owner, status, target dates and blockers.",
            "Update contributions from either view and see the same progress in My work and work details.",
            "Review submitted evidence and keep required notes when changing contribution status.",
        ],
    },
    {
        "version": "6.69",
        "date": "October 16, 2026",
        "summary": "Find the working draft and hand off contributions with clear context.",
        "changes": [
            "Open the named working Google draft and find supporting files from the work item.",
            "Record contribution handoff notes with the draft and task state you reviewed.",
            "Keep earlier draft selections and file references visible when the working draft changes.",
        ],
    },
    {
        "version": "6.68",
        "date": "October 16, 2026",
        "summary": "Registration pages now focus on participants.",
        "changes": [
            "Keep activity management and travel claim actions on staff pages instead of the public registration page.",
        ],
    },
    {
        "version": "6.67",
        "date": "October 16, 2026",
        "summary": "Calendar travel claim reminders now open the claim.",
        "changes": [
            "Select a travel claim reminder on the calendar to open its filing and checklist.",
            "Select the activity title to open the activity page.",
        ],
    },
    {
        "version": "6.66",
        "date": "October 16, 2026",
        "summary": "Public registration and feedback links can now be shortened automatically.",
        "changes": [
            "Share compact activity and feedback links with matching QR codes when shortening is enabled.",
            "Keep using the original link while a short link is being prepared or the service is unavailable.",
            "Personal participant recovery links stay private from the shortening service.",
        ],
    },
    {
        "version": "6.65",
        "date": "October 16, 2026",
        "summary": "Turn discussions into proposed tasks and traceable work decisions.",
        "changes": [
            "Create a proposed contribution from a message while retaining its original text.",
            "Record work decisions with their source, affected contributions and supporting correspondence.",
            "Review changed work direction while preserving earlier outputs and acceptance history.",
        ],
    },
    {
        "version": "6.64",
        "date": "October 16, 2026",
        "summary": "Make blocked contributions and prerequisite work visible to the team.",
        "changes": [
            "Record a blocker with a follow-up owner and date, then keep its resolution in history.",
            "Link prerequisite contributions and see what must be accepted before work can be submitted.",
            "Find blocker follow-ups in My work without changing official deadlines.",
        ],
    },
    {
        "version": "6.63",
        "date": "October 16, 2026",
        "summary": "Online meetings are easier to join.",
        "changes": [
            "A Join Google Meet button now sits on the calendar item.",
            "People on an online item get the meeting on their own Google Calendar, so they can join without asking.",
        ],
    },
    {
        "version": "6.62",
        "date": "October 16, 2026",
        "summary": "Online meetings on the calendar can get a Google Meet link automatically.",
        "changes": [
            "Save a calendar item as Online or Hybrid with no link and a Google Meet link is added for you.",
            "Changing the time of the item moves the Meet event, and cancelling it removes the event.",
            "A link you type yourself, such as Zoom or Teams, is never replaced.",
        ],
    },
    {
        "version": "6.61",
        "date": "October 16, 2026",
        "summary": "Follow discussions and see when colleagues need your attention.",
        "changes": [
            "Mention people who already have access and find their updates in the notification bell.",
            "Follow a work item or contribution and stop following whenever you choose.",
            "See unread messages and mark the displayed versions as read.",
        ],
    },
    {
        "version": "6.60",
        "date": "October 16, 2026",
        "summary": "Discuss shared work and contributions with your colleagues.",
        "changes": [
            "Post messages and replies within a work item or contribution.",
            "Edit your own messages while keeping earlier text visible in history.",
            "Keep discussions separate from task updates and formal document approvals.",
        ],
    },
    {
        "version": "6.59",
        "date": "October 16, 2026",
        "summary": "Administrators can review what still needs setup before collaborative work goes live.",
        "changes": [
            "Review roles, policies, holiday coverage and integrations with specific next steps.",
            "See which connections are configured and which still need live verification.",
            "Review setup without changing permissions or enabling document sending.",
        ],
    },
    {
        "version": "6.58",
        "date": "October 16, 2026",
        "summary": "Work items make the next action and contribution history easier to follow.",
        "changes": [
            "See outstanding contributions, your next actions, and return notes alongside each task.",
            "Review individual contribution histories with named people and submitted outputs.",
            "Update document contributions through named cards without typing assignment numbers.",
        ],
    },
    {
        "version": "6.57",
        "date": "October 16, 2026",
        "summary": "Correspondence intake connects reviewed records with the right shared work.",
        "changes": [
            "Choose reference-only intake, start shared work, or link an existing work item during registration.",
            "Office scenarios offer optional contribution proposals without assigning people or approval authority.",
            "Review source suggestions before registration, or continue manually if the source cannot be read.",
        ],
    },
    {
        "version": "6.56",
        "date": "October 16, 2026",
        "summary": "My work is included in the deployment package.",
        "changes": ["The deployment package now includes the personal work inbox used by home and notifications."],
    },
    {'version': '6.55',
 'date': 'October 16, 2026',
 'summary': 'My work shows your own contributions and decisions with their '
            'next steps.',
 'changes': ['Find assigned work, internal targets, and items waiting for '
             'review in one personal list.',
             'Home now links directly to individual contributions, while '
             'formal document reviews stay in Approvals.',
             'Completed tasks leave your action list, and migrated assignments '
             'appear only once.']},
    {
        "version": "6.54",
        "date": "October 16, 2026",
        "summary": "Behind-the-scenes fix so the latest updates can go live again.",
        "changes": [
            "Updates 6.50 to 6.53 (shared work, contribution review and the registration link layout) are now included in the live site.",
        ],
    },
    {
        "version": "6.53",
        "date": "October 16, 2026",
        "summary": "The registration link on an activity's page is easier to read and copy on a phone.",
        "changes": [
            "The registration link now sits on one tidy line with its Copy button instead of spilling over several lines.",
        ],
    },
    {
        "version": "6.52",
        "date": "October 16, 2026",
        "summary": "Existing assignments can be rehearsed as shared contributions while preserving their history.",
        "changes": [
            "For migrated records, document pages reflect current shared contribution progress.",
            "Required contributions still control closure, and officers can adjust internal targets with a recorded reason.",
            "Migration can be checked on a separate database copy before operational use.",
        ],
    },
    {
        "version": "6.51",
        "date": "October 16, 2026",
        "summary": "Shared work now supports individual contributions and review.",
        "changes": [
            "Officers can confirm contribution owners, while staff can start and submit their own outputs.",
            "Work leads can return contributions for changes or accept them, with each decision kept in history.",
            "Document leads can now confirm another contributor's completed work.",
        ],
    },
    {
        "version": "6.50",
        "date": "October 16, 2026",
        "summary": "Shared work items connect an expected outcome with its lead and correspondence.",
        "changes": [
            "When Shared work is enabled, staff can describe an outcome and link its incoming and outgoing records.",
            "Concerned officers can confirm the accountable lead without changing document access or approval authority.",
        ],
    },
    {
        "version": "6.49",
        "date": "October 16, 2026",
        "summary": "Travel claims are filed from activity and calendar pages.",
        "changes": [
            "The File a travel claim button no longer appears on the registration monitor; you can still file from the activity or calendar page.",
        ],
    },
    {
        "version": "6.48",
        "date": "October 16, 2026",
        "summary": "Travel claims show relevant questions and guide you to the next missing item.",
        "changes": [
            "The claim type controls which trip questions and form sections you see.",
            "Completed checklist items fold away, and the main button takes you to the next unfinished task.",
            "Actual fares stay separate from policy limits, while cash advance estimates can use the allowed rates.",
            "The preparation page tells you when your draft is saved in this browser and lets you return directly to the checklist.",
        ],
    },
    {
        "version": "6.47",
        "date": "October 16, 2026",
        "summary": "Documents can be enabled from its administrator setup page.",
        "changes": [
            "An appointed permissions administrator with system-admin access can enable Documents while keeping sending disabled.",
            "System administrators can disable Documents and sending together, with every change recorded in the audit log.",
        ],
    },
    {
        "version": "6.46",
        "date": "October 16, 2026",
        "summary": "Documents administrators can be appointed from the Administrator menu.",
        "changes": [
            "A system administrator can review and confirm the initial staff accounts responsible for Documents permissions and workflow rules.",
            "Appointments are recorded in the audit log, and Documents and sending stay disabled during setup.",
        ],
    },
    {
        "version": "6.45",
        "date": "October 15, 2026",
        "summary": "Travel claims: the DPO and the Certificate of Appearance are checked as you upload them.",
        "changes": [
            "Uploading the DPO now checks its number, date and travel dates against your filing, and warns if it does not state a funding source.",
            "Uploading the Certificate of Appearance warns if its dates do not cover the activity.",
            "If your filing has no DPO number or date, a button puts the one read from the file into your answers. You still press Save, and nothing read is kept on the server.",
        ],
    },
    {
        "version": "6.44",
        "date": "October 15, 2026",
        "summary": "Travel claims: tickets and receipts are read as you upload them.",
        "changes": [
            "When you upload a plane, bus or boat ticket, a taxi or Grab receipt, a terminal fee or a hotel bill to the checklist, the amount is read off it.",
            "On the prepare page, each day lists those readings with a \u201cUse\u201d button. Nothing fills in until you press it, and nothing read is kept on the server.",
        ],
    },
    {
        "version": "6.43",
        "date": "October 15, 2026",
        "summary": "Travel claims: upload a file to a checklist row instead of pasting a Drive link.",
        "changes": [
            "Each upload row on a travel filing now has a \u201cChoose file or take photo\u201d button. Pick a photo or PDF and it is stored in the office travel folder; pasting a Drive link still works.",
            "Large photos are shrunk on your device before they are sent. You can remove or replace the files you uploaded.",
            "The button appears once the office has updated the documents relay (Administration, Travel filing settings, Test the relay).",
        ],
    },
    {
        "version": "6.42",
        "date": "October 15, 2026",
        "summary": "Document-management workflows are ready for configuration and acceptance testing.",
        "changes": [
            "Incoming and outgoing documents can be tracked through assignments, review, signing, release and closure when enabled.",
            "Document reading, saved signatures and official email reuse the existing office Google connections.",
            "Documents stays disabled until office policies and launch checks are confirmed.",
        ],
    },
    {
        "version": "6.41",
        "date": "October 15, 2026",
        "summary": "Travel claims can read the fare off a ticket or receipt.",
        "changes": [
            "On the prepare page, each day has a new \u201cread it from a ticket or receipt\u201d button. Pick a photo or PDF of your plane, bus or boat ticket, taxi or Grab receipt, and it shows the amount it found.",
            "Nothing fills in until you press \u201cUse\u201d, so you can check it against the file first. The file is read once and is not kept.",
            "If the reading is not available or the file is unclear, you simply type the amount as before.",
        ],
    },
    {
        "version": "6.40",
        "date": "October 15, 2026",
        "summary": "Travel claim amounts now fill in by themselves.",
        "changes": [
            "Once you choose the destination and rates, the fare and daily allowance boxes fill in from the policy without pressing anything. Type a different amount if you spent less.",
            "One new choice sets the per diem rule for every day of the trip at once.",
        ],
    },
    {
        "version": "6.39",
        "date": "October 15, 2026",
        "summary": "Travel claims now work out the policy rates for you.",
        "changes": [
            "On the prepare page, pick where you are going and how each day was spent, and the page shows the daily allowance the policy gives for it, with a button to use it.",
            "For each ride, pick the rate that applies (airport trip by area, live-out trip by distance, taxi to an activity, public fare beyond 50 km) and the page shows the most the policy allows.",
            "A fare or daily amount above the policy is still allowed, but it is sent to the Admin Unit to check, as before.",
            "A new Policy rates tab lists every rate with the section it comes from.",
        ],
    },
    {
        "version": "6.38",
        "date": "October 15, 2026",
        "summary": "Travel forms can now be made from the office's own Word and Excel forms.",
        "changes": [
            "The CENRR and RER forms are now made from the office's Excel forms, so they keep their official layout.",
            "A one-time setup script turns the office's travel forms into ready-to-fill Google templates, so nobody has to edit them by hand.",
            "The generated Appendix B, CENRR and RER now say the DPO number and the activity, the way the originals do.",
        ],
    },
    {
        "version": "6.37",
        "date": "October 15, 2026",
        "summary": "Travel claims: set fare limits and routes, keep the justification texts, and clear old records.",
        "changes": [
            "The Administrative Section can now change the fare limits (TNVS, taxi, CENRR and each route's RER limit) and switch routes on or off from Ceilings and routes in the Travel menu. A new route always comes with its RER limit.",
            "Template administrators can edit the MC 114 justification texts that travel forms start from, from the Justification library. Other Administrative Section members can read them.",
            "A year after a travel claim is submitted (or withdrawn), the links and notes on it are cleared automatically. The claim itself, its dates and its status stay on record.",
            "The travel settings pages now warn when next year's holidays have not been loaded, since deadlines can land on a holiday until they are.",
        ],
    },
    {
        "version": "6.36",
        "date": "October 14, 2026",
        "summary": "The Administrative Section can now verify flagged travel claims.",
        "changes": [
            "A new Verify travel flags page, in the Travel menu for the Administrative Section, lists every travel claim item that needs a decision: a fare above the limit, a route that is not on the approved list, a fare over 1,000 with no receipt, or someone travelling only as a participant.",
            "The Admin Unit records Verified or Reject with a note. Rejecting needs a reason, and a participant-only trip needs the supervisor's confirmation that the travel was necessary.",
            "A claim cannot be marked ready while any flag is waiting or has been rejected. If a claim was already ready and something is rejected, it goes back to in progress.",
            "You see the outcome and note on your claim, and the bell tells you when something was not accepted. Changing a fare or route makes a fresh flag, so an old decision never covers a new amount.",
        ],
    },
    {
        "version": "6.35",
        "date": "October 14, 2026",
        "summary": "Make travel forms from your travel claim.",
        "changes": [
            "A new Prepare the forms page on each travel claim lets you fill in your itinerary, report and certificate once, and makes the Google Docs for you: Appendix A and B, the Post Travel Report, the Job Order certification, the MC 114 sheet, and the CENRR and RER forms your rides need.",
            "The page adds up your fares and tells you straight away if a ride will need the Admin Unit to check it, such as a fare above the limit or a route that is not on the approved list.",
            "What you type is used to make the forms and is not kept on this site. You can change it and make new copies at any time; the older copies stay in Drive.",
            "If a form fails to come out, you can try just that one again.",
        ],
    },
    {
        "version": "6.34",
        "date": "October 14, 2026",
        "summary": "Groundwork for making travel forms automatically.",
        "changes": [
            "The travel settings page now has a Test the relay button that checks whether the office's Google connection for travel forms is working, and says in plain words what is wrong if it is not.",
            "You can set who signs the travel forms (head of office and certifying officer) and who looks after the form templates.",
            "When you paste a Google Drive link on a travel claim, it can now be checked to see that the office can open the file. Nothing changes for you yet until forms are made automatically in a later update.",
        ],
    },
    {
        "version": "6.33",
        "date": "October 14, 2026",
        "summary": "Travel claim reminders by email and in the bell.",
        "changes": [
            "You now get one email a day while a travel claim of yours is due within 2 days or overdue. It lists each claim with a link straight to it.",
            "A cash advance whose activity is over and has no liquidation yet is included in the same email, and shows in the bell as 'A cash advance still needs a liquidation'.",
            "The bell also shows how many of your travel claims are due soon or overdue. Admin Unit members will see travel flags waiting to be verified once that queue opens.",
            "An administrator can turn the email off, or change the 2 days, on the email settings page.",
        ],
    },
    {
        "version": "6.32",
        "date": "October 14, 2026",
        "summary": "File travel claims: cash advance, liquidation and reimbursement checklists.",
        "changes": [
            "There is a new Travel menu with My travel claims. Pick an activity (or start one that is not on the calendar), answer a few short questions, and get the list of documents you need.",
            "Paste a Google Drive link for each document, mark what does not apply, and note the FMIS reference for finance papers. The page tells you exactly what is still missing.",
            "A cash advance can only be filed more than a week before the activity starts. Liquidations and reimbursements show their deadline and turn red when overdue.",
            "When everything is in, you get a print list showing how many copies each document needs and which ones to sign in ink. Tap Mark submitted once you have handed them in.",
            "The calendar now shows a small travel chip on your activities (Not filed, Due in 3 days, Ready to sign, Filed), and activity pages have a File a travel claim button.",
        ],
    },
    {
        "version": "6.31",
        "date": "October 14, 2026",
        "summary": "Groundwork for travel filing, plus an employee number on your profile.",
        "changes": [
            "Your profile now has an Employee number box. It will be printed on travel forms.",
            "Behind the scenes, the rules for travel claim deadlines, taxi and ride-hailing fare limits and the document checklist are in place. You will see the travel pages in a later update.",
        ],
    },
    {
        "version": "6.30",
        "date": "October 14, 2026",
        "summary": "Picking who is on a calendar item is easier on a phone.",
        "changes": [
            "The list of people on the Add to the calendar and Edit calendar item forms now scrolls on a phone.",
            "There is a new search box above the list, so you can find a name by typing part of it.",
        ],
    },
    {
        "version": "6.29",
        "date": "October 13, 2026",
        "summary": "Add a calendar item and reserve the conference room in one go, and the room now follows your activity or item everywhere.",
        "changes": [
            "The Add to the calendar form now has a Conference room line, just like Add activity. It shows which hours are free, follows the times you enter, and offers a standby request if the hours are taken.",
            "A calendar item or activity and its room show as one item on the calendar, and a calendar item's page shows the room's status with buttons to move or withdraw it.",
            "If you turn a calendar item into a CSS activity, its room goes with it.",
            "Cancelling a calendar item that still holds the room offers to release it.",
            "Standby requests are marked on My reservations, in Approvals and in the email to the Administrative Section, and Approvals shows which activity or calendar item each request is for.",
        ],
    },
    {
        "version": "6.28",
        "date": "October 13, 2026",
        "summary": "Standby (provisional) conference room requests, and no more double plotting on the calendar.",
        "changes": [
            "An activity and the conference room booked for it now show as one item on the calendar, with the room hours on it.",
            "If the hours you want are already booked or closed, you can ask for a provisional (standby) use on the Add activity form and the Conference room page. Nothing is held for you.",
            "The Administrative Section sees standby requests marked in Approvals and can confirm one in an emergency (the booking in the way is released and its owner is told why), or decline it.",
        ],
    },
    {
        "version": "6.27",
        "date": "October 11, 2026",
        "summary": "The Approvals page now shows you only the requests that are really yours to decide.",
        "changes": [
            "If you only manage conference rooms, Approvals no longer lists other people's wellness break and work arrangement requests.",
            "Wellness breaks and work arrangements appear only for people who hold a chief seat or are acting as OIC, and only for requests routed to them.",
            "The waiting-on-you counts on the home page and bell now match what the Approvals page shows.",
        ],
    },
    {
        "version": "6.26",
        "date": "October 10, 2026",
        "summary": "Organizers can now email a pinned update to everyone registered.",
        "changes": [
            "When you post a pinned update, tick \"Also email registrants\" to send it to everyone who registered with an email. People without an email simply see it on their page.",
            "Each email includes the person's own link back to the activity page.",
            "To protect the mail service, an activity can send one update email every 15 minutes, and there's a daily limit across all activities. The page tells you if anyone was left out.",
            "Admins can turn update emails on or off in Admin → Email.",
        ],
    },
    {
        "version": "6.25",
        "date": "October 10, 2026",
        "summary": "Participant pages and certificates are now protected from guessing.",
        "changes": [
            "A participant's page, feedback and certificate can no longer be opened by guessing or editing a number in the web address.",
            "Each participant now gets a private, unguessable link when they register.",
            "If an old certificate link or a remembered device stops working, register again with the same email to get straight back in. Nothing is duplicated.",
        ],
    },
    {
        "version": "6.24",
        "date": "October 10, 2026",
        "summary": "Organizers get a ready-to-print QR for their activity and can see how long participants' personal links last.",
        "changes": [
            "The activity's management page now shows a QR code of the participant page that you can download for posters and slides.",
            "The registration list now says the date until which participants' personal links keep working.",
        ],
    },
    {
        "version": "6.23",
        "date": "October 10, 2026",
        "summary": "The activity page is now event registration, with a personal link and QR you can save.",
        "changes": [
            "The activity page now says \"Register for this activity\" instead of asking you to sign in for feedback.",
            "Right after registering you get a personal link and QR code to save, copy, share or email to yourself. It brings you back to the activity on any device.",
            "Feedback forms stay locked until the activity starts, and the page tells you when they open.",
            "Your personal link keeps working until 30 days after the activity ends.",
            "Organizers can pin an update, such as a room change, that registered participants see at the top of their page.",
        ],
    },
    {
        "version": "6.22",
        "date": "October 10, 2026",
        "summary": "Profile pictures now load much faster.",
        "changes": [
            "Small profile pictures on the home screen, calendar and directory are now much lighter, so faces appear sooner.",
            "Pictures you have already seen are no longer downloaded again each time you open a page.",
            "Pictures you have seen before now appear instantly, even with a weak connection, and refresh quietly in the background.",
        ],
    },
    {
        "version": "6.21",
        "date": "October 10, 2026",
        "summary": "Your companion on the home page now plays: it roams, follows your cursor and can be dragged.",
        "changes": [
            "Your companion now wanders around the space beside your greeting instead of standing still.",
            "Move your mouse near it and it will chase your cursor, then pounce when it catches up.",
            "You can pick it up and drop it anywhere in that space, and it remembers where you left it.",
        ],
    },
    {
        "version": "6.20",
        "date": "October 10, 2026",
        "summary": "Administrators no longer see the room management menu unless they are in the Administrative Section.",
        "changes": [
            "The \"Manage the room\" part of the Office menu (Room requests, Room meals, Room closures) now shows only for members of the Administrative Section, not for every administrator account.",
        ],
    },
    {
        "version": "6.19",
        "date": "October 9, 2026",
        "summary": "Your profile page is simpler: the companion growth guide has moved off it.",
        "changes": [
            "The \"How your companion grows\" section is no longer shown on your profile page. It is still on the home screen.",
        ],
    },
    {
        "version": "6.18",
        "date": "October 9, 2026",
        "summary": "\"Change companion\" on the home screen now takes you straight to your companion.",
        "changes": [
            "Tapping \"Change companion\" opens your profile already scrolled to the companion choices, instead of the top of the page. \"Your profile\" still opens the top.",
        ],
    },
    {
        "version": "6.17",
        "date": "October 9, 2026",
        "summary": "Only the Administrative Section now manages the conference room.",
        "changes": [
            "Room requests, ordering meals, marking meals delivered, and room closures are for members of the Administrative Section only.",
            "A section's temporary OIC and admin accounts no longer see the room approval queue unless they belong to the Administrative Section.",
        ],
    },
    {
        "version": "6.16",
        "date": "October 9, 2026",
        "summary": "The Office calendar now has its own Calendar menu.",
        "changes": [
            "The Office calendar moved out of the Office menu into a new Calendar menu, so Office holds only the conference room.",
        ],
    },
    {
        "version": "6.15",
        "date": "October 9, 2026",
        "summary": "The conference room now has its own Office menu instead of sitting under AWA.",
        "changes": [
            "A new Office menu holds the Conference room, My room reservations and the Office calendar. Searching for the room now shows \"Office\" instead of \"AWA\".",
            "People in the Administrative Section also see Room requests, Room meals and Room closures there, and can find the door display and QR poster by search.",
            "AWA now holds only work arrangement pages.",
        ],
    },
    {
        "version": "6.14",
        "date": "October 9, 2026",
        "summary": "The assistant page's \"Classic home\" link now takes you to the home page.",
        "changes": [
            "On the assistant page, \"Classic home\" now opens the Office Connect home page instead of the CSS hub.",
        ],
    },
    {
        "version": "6.13",
        "date": "October 9, 2026",
        "summary": "A roomier, easier menu on phones, with Log out always in reach.",
        "changes": [
            "On a phone the menu now slides in from the right, so Log out is always visible at the bottom instead of being cut off.",
            "The menu sections fold open and closed, so the list is short and you can find things quickly.",
            "Display settings (theme, colour, text size) are behind the small gear button at the bottom of the menu.",
            "Close the menu with the X button, by tapping outside it, or with the Esc key.",
        ],
    },
    {
        "version": "6.11",
        "date": "October 9, 2026",
        "summary": "A tidier top of the screen on phones and tablets.",
        "changes": [
            "On a phone the top bar is one slim row: search, notifications and the menu button. Display settings, help and Log out are now inside the menu.",
            "On a tablet the menu button now appears sooner, so the top bar no longer stacks into several rows.",
            "On the home page, Team / Me / Calendar and the search box sit right under your greeting again instead of far down the screen.",
            "On a phone the Send feedback button is now a small round button, so it no longer covers your to-do list.",
        ],
    },
    {
        "version": "6.10",
        "date": "October 9, 2026",
        "summary": "Search and the assistant on the home page, polished and checked on phones.",
        "changes": [
            "You can search for colleagues, meetings, your to-dos, your requests, room bookings and help topics from the home page, and ask the assistant questions in the same box.",
            "On a phone, the Send feedback button no longer covers the search results.",
            "The search box works better with screen readers, and the answers are read out as they appear.",
            "The home page has a short guide to the new search box, and the help guide describes it and the colleague card.",
        ],
    },
    {
        "version": "6.9",
        "date": "October 9, 2026",
        "summary": "One box on the home page for both searching and asking.",
        "changes": [
            "Type a question into the search box, such as \u201cwho is in the office today?\u201d, and choose the Ask line at the top to see the answer right there.",
            "Pages and records you were searching for still appear underneath, so nothing is lost.",
            "The same Ask line works in the search that opens with Ctrl-K or the magnifier button.",
            "The full-page assistant at /start works exactly as before.",
        ],
    },
    {
        "version": "6.8",
        "date": "October 9, 2026",
        "summary": "The assistant can now answer questions about your own tasks and the office.",
        "changes": [
            "Ask about your to-do list, your approvals, how many wellness hours you have left, or whether you filed your work arrangement.",
            "Ask who is in the office or working from home today, whether the conference room is free today or tomorrow, and what room bookings you have.",
            "These answers work even when the AI is switched off, and also in Tagalog, for example \u201csino ang nasa opisina\u201d.",
        ],
    },
    {
        "version": "6.7",
        "date": "October 9, 2026",
        "summary": "Search for a colleague and see whether they are in the office today.",
        "changes": [
            "Typing a colleague's name in search now shows their position, their unit and whether they are in the office, working from home, in the field, on leave or off today.",
            "Opening a colleague shows a small card with their photo, who they are, and when they are away in the next seven days.",
            "Only that basic status is shown to everyone signed in. Notes, places and reasons stay private.",
            "An administrator can limit who sees this status to each person's own team, under AWA filing.",
        ],
    },
    {
        "version": "6.6",
        "date": "October 9, 2026",
        "summary": "Search on the home page now finds your calendar, to-dos, requests, room bookings and help.",
        "changes": [
            "Type a meeting name and see it from your calendar, with its date and time.",
            "Your to-do items, your wellness break and work arrangement, and your conference room bookings now show up in search.",
            "Typing \u201croom\u201d gives you a quick link to book the conference room, and help topics appear with a link to the guided tour.",
            "You only ever see your own requests and the calendar items you could already see.",
        ],
    },
    {
        "version": "6.5",
        "date": "October 9, 2026",
        "summary": "Search behind the scenes: no change to what you see.",
        "changes": [
            "Search now has a steadier setup underneath, ready for finding more things later.",
            "If one part of search ever has a problem, the rest keeps working.",
        ],
    },
    {
        "version": "6.4",
        "date": "October 9, 2026",
        "summary": "The search box on the CSS hub now looks only at CSS.",
        "changes": [
            "On the CSS hub, search shows only CSS pages, activities and resource persons.",
            "Below the CSS results there is a \u201cSearch everything\u201d line that opens full search with what you typed.",
        ],
    },
    {
        "version": "6.3",
        "date": "October 9, 2026",
        "summary": "Search and the assistant are now on your home page.",
        "changes": [
            "The home page has a search box under the greeting, with a shortcut to ask the assistant.",
            "A magnifier button at the top of every page opens search, so it also works on phones.",
            "The old home screen is now called the CSS hub, and its search box looks only at CSS.",
        ],
    },
    {
        "version": "6.2",
        "date": "October 9, 2026",
        "summary": "You can now send a birthday card to a teammate.",
        "changes": [
            "In the week before a teammate's birthday, the bell reminds you to send them a card. Pick a design and write a short message in Tagalog or English.",
            "Cards are kept hidden until their birthday, then they read them on the home page or on My profile, signed with your name.",
            "Only people who chose to share their birthday with you can get a card from you. Someone who shares with no one gets none.",
            "If a card is unkind or unsuitable, the person can hide it, and an admin can hide it too.",
        ],
    },
    {
        "version": "6.1",
        "date": "October 9, 2026",
        "summary": "The home page now greets you in the week before your birthday, and on the day.",
        "changes": [
            "From six days before your birthday, the home page says so in Tagalog and English, with a short message from all of us at BLHSD.",
            "On the day itself it greets you with \"Maligayang kaarawan! Happy birthday!\", and your companion joins in.",
            "You see the celebration message once, then just a friendly heading, so it never gets in the way. After your birthday the page goes back to normal.",
        ],
    },
    {
        "version": "6.0",
        "date": "October 9, 2026",
        "summary": "Everyone with a birthday on file now gets a warm greeting email from BLHSD.",
        "changes": [
            "On your birthday you receive a short greeting in Tagalog and English, signed by all of us at BLHSD.",
            "If your birthday falls on a weekend or holiday, the greeting arrives on the working day before, never late.",
            "It goes to everyone who has added a birthday, whoever they chose to share it with, and tells nobody else. To stop it, remove your birthday on your profile.",
        ],
    },
    {
        "version": "5.9",
        "date": "October 9, 2026",
        "summary": "A door screen for the conference room, and meetings that repeat.",
        "changes": [
            "New door display for a TV or tablet by the room: who has the room now, what is next, and today's schedule in large type, with a QR code to request it. It refreshes itself every minute. The Administrative Section sets it up from the Door display tab and can hide meeting titles if the screen faces a corridor.",
            "A weekly meeting no longer needs a request for every date. Choose Repeat (every week or every 2 weeks) and an end date, and the dates that can't be had are listed first so you can request the ones that work.",
            "The Administrative Section approves or declines a whole repeating request in one click, or one date at a time. You hear back once, and you can withdraw every remaining date together.",
        ],
    },
    {
        "version": "5.8",
        "date": "October 9, 2026",
        "summary": "Meal requests for the conference room, from the form to delivery.",
        "changes": [
            "When you ask for meals with a room booking, a meal form is prepared for you: the activity title, number of pax, any special request, and Yes or No for breakfast, AM snack, lunch and PM snack, each with the time you want it delivered. We fill the meals in from your hours and you correct them.",
            "The form can be printed or downloaded as a PDF, and guests can fill in theirs from their tracking link.",
            "The Administrative Section has a new Meals page that shows every filled-up form to order from. They tag each meal as requested, then delivered, not delivered or cancelled, with an optional note, and everything is recorded with who and when.",
            "If a booking is cancelled, the meals are cancelled with it, and the section is told to cancel with the caterer if an order was already placed.",
        ],
    },
    {
        "version": "5.7",
        "date": "October 9, 2026",
        "summary": "Activities and conference room bookings now know about each other.",
        "changes": [
            "When you create an activity, a Conference room line lets you ask for the room in the same step. It shows which hours are free that day, and ticks itself for online and hybrid activities, where the room can host the session. A choice that cannot work (too soon, or already booked) is caught before the activity is saved.",
            "On My reservations, \"Create a CSS activity for this\" starts the activity form filled in from the booking.",
            "An activity's page now says what is happening with its room. If you move the activity to another day it offers to move the booking too, and the old booking is kept until the move is approved. If the room is cancelled, it offers the nearest free times.",
        ],
    },
    {
        "version": "5.6",
        "date": "October 9, 2026",
        "summary": "Conference room bookings now show on the Office calendar.",
        "changes": [
            "Approved room bookings appear on the calendar for everyone, with their hours, so you can see at a glance when the room is taken. A request still waiting for a decision shows only to the person who asked and to the Administrative Section, marked as awaiting approval.",
            "You can show only the room with the \"Conference room\" type in the filter, and open the room board from the More menu.",
            "Your own bookings also go to your phone or computer calendar if you subscribe to your calendar feed, and are taken off again if you withdraw or they are cancelled.",
        ],
    },
    {
        "version": "5.5",
        "date": "October 9, 2026",
        "summary": "Outside guests can now request the conference room from a QR code, without an account.",
        "changes": [
            "A permanent web address and QR code (/room) let anyone outside the office pick a day, choose hours and send a request. They see which hours are free but never who booked them.",
            "Guests get an email with their reference and a private link to check the status, withdraw the request, or pick a new time if their booking is cancelled.",
            "The Administrative Section approves guest requests the same way as staff ones, and can print a ready-made QR poster from the Conference room page.",
            "To keep spam out, a guest can file only a few requests an hour and three open ones per email address. Guests' names and contact details are removed 12 months after their meeting date.",
        ],
    },
    {
        "version": "5.4",
        "date": "October 9, 2026",
        "summary": "Conference room: see what is free, request it, and get told what happens.",
        "changes": [
            "New Conference room page shows each hour from 7 AM to 7 PM, day by day. Click an hour (or a few in a row), fill in the meeting, and send your request. Requests need two working days' notice.",
            "My reservations lists your requests with their status and lets you withdraw one if plans change.",
            "The Administrative Section approves or declines from the Approvals page, or straight from the email. They can also book the room for someone, close it for repairs, and move a booking when something more important comes up.",
            "If your booking is cancelled you are told why and offered the nearest free times, and picking one books it at once.",
            "Approved bookings come with a calendar file, and you get a reminder the afternoon before.",
        ],
    },
    {
        "version": "5.3",
        "date": "October 9, 2026",
        "summary": "Admins can now add a person's birthday from the Directory.",
        "changes": [
            "On Directory, open Edit for a staff member and use the new Birthday card to add, change or remove their birthday, choosing who may see it.",
            "Birthdays are kept on the person's account, so staff without an account are asked to get one first.",
        ],
    },
    {
        "version": "5.2",
        "date": "October 9, 2026",
        "summary": "\"Mine only\" on the calendar no longer shows things you only imported.",
        "changes": [
            "If you imported calendar items from a file, they no longer appear under \"Mine only\" unless you are actually listed on them.",
            "Imported items still show under \"Mine + bureau-wide\" when they are bureau-wide.",
        ],
    },
    {
        "version": "5.1",
        "date": "October 9, 2026",
        "summary": "The calendar now has a colour key, and admins can add birthdays for people.",
        "changes": [
            "Under the agenda and month calendar there is now a key showing which colour belongs to which unit, and what each icon means.",
            "Admins can add, change or remove a person's birthday from the Users page, choosing who may see it.",
            "People can still change or remove their own birthday on their profile.",
        ],
    },
    {
        "version": "5.0",
        "date": "October 10, 2026",
        "summary": "The calendar is easier to use with a keyboard, a screen reader and large text.",
        "changes": [
            "Screen readers now find the month, week and timeline grids correctly laid out, with named column headings and today marked.",
            "Everything can be reached and used with the keyboard, with a clear focus ring, and the panels keep focus inside them and give it back when closed.",
            "Large text (up to 200%) no longer pushes the page sideways, and out-of-month days in the month grid are easier to read.",
            "Smaller tap targets in the month, week and timeline grids were enlarged to the recommended minimum.",
        ],
    },
    {
        "version": "4.9",
        "date": "October 10, 2026",
        "summary": "The calendar is faster to use: search, a details panel, add from any day, and keyboard and swipe.",
        "changes": [
            "Search the calendar by title, place, unit, tag or person. In the agenda it looks through the whole year.",
            "Tap an item to read it in a panel without leaving the page (a sheet from the bottom on a phone). Back or Escape closes it, and the address can be shared.",
            "Add something from any day: the + beside a day, or a date in the month grid. Quick add opens with that date filled in.",
            "The calendar remembers the layout and whose calendar you last chose, and opens that way next time.",
            "Arrow keys move through time, T goes to today, A adds, S searches. On a phone, swipe left or right to move.",
        ],
    },
    {
        "version": "4.8",
        "date": "October 9, 2026",
        "summary": "The calendar looks clearer and is easier to read.",
        "changes": [
            "Each day has a date badge with the weekday and number, a count of its items, and a Today highlight. Holidays show as a small red label.",
            "Each item shows its time in one column (or All day, or AM / PM), a small icon for what kind of thing it is, and the unit that owns it. Tentative and postponed items are clearly marked.",
            "Tap anywhere on an item to open it. Long titles are shortened to two lines, and the full title is on hover.",
            "An empty calendar now offers Add something and Look further ahead. Today is tinted in Week and Timeline. Three unit colours were darkened slightly so their names are easier to read.",
        ],
    },
    {
        "version": "4.7",
        "date": "October 9, 2026",
        "summary": "The calendar now fits every screen, from a phone to a wide monitor.",
        "changes": [
            "Month works on a phone: each day shows its number and coloured dots for the units that have something on. Tap a day to read it.",
            "On a laptop the agenda shows two days side by side, and on a wide monitor three, so the screen is no longer mostly empty.",
            "Week and Timeline scroll sideways inside their own box on a small screen, with shadows at the edges and a hint, and the names stay in view.",
            "The add form no longer runs off the edge of a phone: From and To sit side by side and the date boxes line up.",
        ],
    },
    {
        "version": "4.6",
        "date": "October 9, 2026",
        "summary": "The Calendar tab now shows only the calendar, with a much shorter toolbar.",
        "changes": [
            "Opening Calendar from the home page shows just the calendar. No greeting, companion or to-do list sits above it, and the Team / Me / Calendar switch stays at the top.",
            "The controls are two short rows: pick a layout and add, then move through time, choose whose calendar, and open Filters. On a phone, today's events are now on the first screen.",
            "Whose calendar is a single menu instead of five buttons. Birthdays and Import live under More. Filters apply as soon as you choose, and active ones show as chips you can remove.",
            "An empty calendar says so once, with a way forward, instead of twice. The page loads faster because the team panels are not built for it.",
        ],
    },
    {
        "version": "4.5",
        "date": "October 9, 2026",
        "summary": "The Word calendar import raises fewer false alarms and can no longer be applied twice by mistake.",
        "changes": [
            "Things like version numbers (v2 - 2nd) and date ranges (April 14-16) are no longer flagged as times.",
            "Two spellings of the same word are no longer flagged as two different activities; real differences still are.",
            "An import that has already been applied is refused if it is applied again, so Undo always knows what it created.",
        ],
    },
    {
        "version": "4.4",
        "date": "October 9, 2026",
        "summary": "The Word calendar import now finds more of the names, and the names step works on a phone.",
        "changes": [
            "Names written without brackets at the end of a line, such as Riza and Mae after a city, are now picked up when the name guide knows them.",
            "The names step says how many are already filled in and how many need you, and shows how many will be saved.",
            "On phones and tablets each name is a card, with a Save button that stays in view.",
        ],
    },
    {
        "version": "4.3",
        "date": "October 9, 2026",
        "summary": "A Word calendar import can now add missing holidays, and be undone.",
        "changes": [
            "The review screen lists holidays from the Word file that are not in Holidays yet. Tick the ones the bureau is really off for; nothing is ticked for you.",
            "Made a mistake? Undo this import removes the items it created that nobody has changed since, and the holidays it added.",
            "Items someone edited after the import are kept and listed, and the upload opens for review again once everything is gone.",
        ],
    },
    {
        "version": "4.2",
        "date": "October 9, 2026",
        "summary": "Reviewing a Word calendar import is quicker, and works on a phone.",
        "changes": [
            "The review screen lists the items that need you first. Items that look fine are folded away.",
            "A suggested owner appears next to an item with no colour; nothing is chosen for you.",
            "Do many rows at once: tick only the fine ones, give every unowned row an owner, or untick everything before a date.",
            "A bar at the bottom always shows how many will be imported, and the table turns into cards on phones and tablets.",
        ],
    },
    {
        "version": "4.1",
        "date": "October 9, 2026",
        "summary": "The Word calendar import reads your file more carefully.",
        "changes": [
            "Measles-rubella activities (\"MR SIA\") are no longer mistaken for management reviews.",
            "A link written in a line becomes the meeting link, and an odd time such as \"3 AM\" is flagged instead of saved.",
            "Items that may be two different activities, or that have a time left in the title, are marked for you to check.",
            "For items with no colour, the import now suggests an owner when the line or its topic points to one. You still choose.",
        ],
    },
    {
        "version": "4.0",
        "date": "October 9, 2026",
        "summary": "The Office calendar is complete: one place for meetings, trips, activities, leave and birthdays.",
        "changes": [
            "Calendar has Agenda, Week, Month and Timeline views, and you can add items in a tap, including ones that repeat.",
            "It connects to everything else: your weekly whereabouts, survey activities, your home page, the bell, and your own Google, Outlook or Apple calendar.",
            "Emails keep you informed without flooding you: one email for a burst of changes, a Monday week-ahead and a day-before reminder, all switchable on your profile.",
            "Birthdays are optional and private unless you share them. You can ask the search bar what is on your calendar.",
        ],
    },
    {
        "version": "3.79",
        "date": "October 9, 2026",
        "summary": "Ask the search bar what is on your calendar.",
        "changes": [
            "Ask things like what do I have today, what is on next week, what is my next meeting, who is away this week or whose birthday is this week.",
            "Answers come only from what you can already see on your calendar. Nobody's leave reason or private notes are ever included.",
            "These questions work even when the AI assistant is switched off.",
        ],
    },
    {
        "version": "3.78",
        "date": "October 9, 2026",
        "summary": "A new Timeline view shows your team over four weeks, and you can add items without leaving the page.",
        "changes": [
            "Calendar has a Timeline view: one row per person across four weeks, with trips, trainings, activities and days on leave as bars.",
            "Weekends are shaded, holidays are tinted, and nobody's reason for leave is ever shown.",
            "Quick add: press Quick add, tap a day, or tap an empty day on someone's row to add an item in a small sheet, then land back where you were.",
        ],
    },
    {
        "version": "3.77",
        "date": "October 9, 2026",
        "summary": "Calendar items can now repeat.",
        "changes": [
            "When you add or edit an item, choose how often it repeats: every weekday, weekly, every two weeks, monthly on the same date, or monthly on the same weekday like the 2nd Tuesday.",
            "A repeating item must have a last date, up to two years out.",
            "Open any one date to change just that one, or skip it. The rest of the series stays as it was.",
            "A repeat that lands on a holiday says so, and your calendar app gets the whole series with the skipped dates left out.",
        ],
    },
    {
        "version": "3.76",
        "date": "October 9, 2026",
        "summary": "You can put the office calendar in Google, Outlook or Apple Calendar.",
        "changes": [
            "Every calendar item has an Add to my calendar (.ics) link.",
            "Calendar emails now carry the item as an attachment, so your calendar app adds it and later updates it instead of duplicating it.",
            "My profile has a private Calendar link you can subscribe to. It shows only what you can already see, and you can make a new one or turn it off any time.",
            "Google only refreshes subscribed calendars every 12 to 24 hours, so changes can take a day to appear there.",
        ],
    },
    {
        "version": "3.75",
        "date": "October 9, 2026",
        "summary": "Your Monday email lists the week's calendar, and you get a reminder the day before.",
        "changes": [
            "The Monday email now has an On the calendar this week list, with what you are on and what is bureau-wide.",
            "The day before a calendar item you are on, you get one reminder listing everything tomorrow.",
            "Chiefs' Tuesday roll-up notes anyone whose report disagrees with the calendar, by name and day only.",
            "Both reminders can be switched off on your profile.",
        ],
    },
    {
        "version": "3.74",
        "date": "October 9, 2026",
        "summary": "You are reminded of teammates' birthdays, and an optional celebrations team gets a heads-up.",
        "changes": [
            "On someone's birthday the bell says whose it is, if they chose to share it with you.",
            "Your Monday email has one line listing the week's birthdays.",
            "Admins can tick the people who organise birthday celebrations. They get an email the day before and a list at the start of each month.",
            "You can switch teammates' birthday reminders off on your profile. Nobody is ever reminded about their own birthday.",
        ],
    },
    {
        "version": "3.73",
        "date": "October 9, 2026",
        "summary": "The bell now tells you about calendar items that are new or changed for you.",
        "changes": [
            "The bell shows how many calendar items you are on that were added, moved or cancelled since you last looked.",
            "Open the list, or open an item, and it counts as seen.",
            "If a trip you are on does not match what you reported, or it moved after you confirmed your week, the bell points you to that week.",
            "You never get a bell for something you changed yourself.",
        ],
    },
    {
        "version": "3.72",
        "date": "October 9, 2026",
        "summary": "People on a calendar item now get one email when it is added, changed or cancelled.",
        "changes": [
            "If several edits are made in a row, you get a single email, not one per edit.",
            "You never get an email about a change you made yourself.",
            "Changes to something happening today or tomorrow are sent right away.",
            "You can switch these emails off on your profile.",
        ],
    },
    {
        "version": "3.71",
        "date": "October 9, 2026",
        "summary": "Birthdays people chose to share now show on the calendar, with a happy birthday on your home page.",
        "changes": [
            "A 🎂 appears on the calendar for each birthday shared with you, every year.",
            "The Coming up card says who is celebrating this week, including weekend birthdays.",
            "On your own birthday the home page greets you with Happy birthday.",
            "A new Birthdays page lists the month's celebrants by section, ready to print.",
        ],
    },
    {
        "version": "3.70",
        "date": "October 9, 2026",
        "summary": "You can now add your birthday to your profile, and choose who sees it.",
        "changes": [
            "On My profile and in the welcome step, pick your birthday month and day. We keep no year.",
            "It is private unless you choose to share it with your section, division or the whole bureau.",
            "You can remove it in one click at any time. Nobody else, including admins, can set or edit it for you.",
        ],
    },
    {
        "version": "3.69",
        "date": "October 9, 2026",
        "summary": "The calendar and your weekly whereabouts now point out when they disagree, and you can add a trip you reported.",
        "changes": [
            "If the calendar has you on a trip but you reported Office or Leave, your weekly form and your home page ask you to check.",
            "If you report a place in the field that is not on the calendar, one button adds it for your section.",
            "A calendar item shows a heads-up when someone on it is on leave, is on a trip they reported differently, or is double-booked. Only that person, the leads and whoever added it see it.",
        ],
    },
    {
        "version": "3.68",
        "date": "October 9, 2026",
        "summary": "Trips on the calendar now fill in your weekly whereabouts, and leave shows on the calendar.",
        "changes": [
            "If you are listed on a confirmed trip, your weekly form and Monday email already show Field with the place. Just confirm it.",
            "If the trip moves, the plan moves with it until you confirm. What you reported yourself is never overwritten.",
            "Who's in and the team week show the trip as Field too, until you say otherwise.",
            "Days you reported as Leave now appear on the calendar as \"on leave\", for you and the people who can already see your team. No reason is ever shown.",
        ],
    },
    {
        "version": "3.67",
        "date": "October 9, 2026",
        "summary": "You can move an activity's dates from the calendar, and trainings get a feedback reminder.",
        "changes": [
            "Open an activity's calendar item and change its dates there. The activity, its forms and the calendar all follow.",
            "If people already registered, you choose whether to email them the new date.",
            "The day after a training that is only on the calendar, its creator gets one email asking if they want to collect feedback.",
        ],
    },
    {
        "version": "3.66",
        "date": "October 9, 2026",
        "summary": "You can now turn a calendar item into a survey activity in one click.",
        "changes": [
            "Open a meeting or training on the calendar and press Collect feedback (CSS) to start the survey form with its details already filled in.",
            "The calendar item and the new activity are linked, so it shows once.",
            "The app now warns you when the activity you are creating may already be on the calendar, and the other way round.",
        ],
    },
    {
        "version": "3.65",
        "date": "October 9, 2026",
        "summary": "Every survey activity now appears on the Office calendar by itself.",
        "changes": [
            "Activities you create for client feedback show up on the calendar automatically, marked with a star.",
            "Each one shows where it is: how many have registered, whether feedback is open, or that it has concluded.",
            "Click an activity to go to its page.",
        ],
    },
    {
        "version": "3.64",
        "date": "October 9, 2026",
        "summary": "The Office calendar has a new Week view that shows who is where.",
        "changes": [
            "Choose Week on the Office calendar to see your team down the side and Monday to Friday across.",
            "Trips and meetings appear as bars on each person's row, with who is in the office, at home, in the field or on leave.",
            "Leave only ever shows as On leave, never the reason.",
        ],
    },
    {
        "version": "3.63",
        "date": "October 9, 2026",
        "summary": "The home page now has a Calendar tab, and your to-do list shows what is on today.",
        "changes": [
            "Click Calendar next to Team and Me on the home page to see the whole office calendar without leaving it.",
            "Your to-do list now tells you how many things are on the calendar today.",
        ],
    },
    {
        "version": "3.62",
        "date": "October 9, 2026",
        "summary": "The home page now shows what is coming up on the office calendar.",
        "changes": [
            "A new Coming up card on the home page lists the next seven days: meetings, trips, trainings and holidays.",
            "Use the Team and Me buttons to switch between your team's calendar and your own.",
            "It also shows who is away on a trip.",
        ],
    },
    {
        "version": "3.61",
        "date": "October 9, 2026",
        "summary": "Administrators can fill in the nicknames the office calendar uses.",
        "changes": [
            "A new page lets an administrator give each person the nickname the office calls them, in one go.",
            "Nobody's own nickname is overwritten unless the administrator chooses to.",
            "You can still change your nickname any time on My profile.",
        ],
    },
    {
        "version": "3.60",
        "date": "October 9, 2026",
        "summary": "The imported calendar now recognises almost every name, including colleagues who have left.",
        "changes": [
            "Names written next to a place, like MDN - Malou, are now understood.",
            "People who have since left are still shown on the old items they were part of, marked as archived.",
        ],
    },
    {
        "version": "3.59",
        "date": "October 9, 2026",
        "summary": "Matching the names in the imported calendar is now much more accurate.",
        "changes": [
            "Calendar names such as Tek, Riza or Doc Malou are matched to the right person using the bureau's own list of who is who.",
            "Places and teams that were picked up as names, such as Cebu or CAR, are now marked as not a person.",
        ],
    },
    {
        "version": "3.58",
        "date": "October 9, 2026",
        "summary": "After importing the Word calendar, administrators can say who the names in it are.",
        "changes": [
            "Names like Riza, Tek or Doc Malou are matched to people's accounts, so those items appear in their calendars.",
            "Only clear matches are suggested; when two people could fit, the administrator chooses.",
            "Answers are remembered for next year's import.",
        ],
    },
    {
        "version": "3.57",
        "date": "October 9, 2026",
        "summary": "Administrators can now bring the yearly Word calendar into the Office calendar.",
        "changes": [
            "On the Office calendar, administrators have an Import from Word button to upload the Calendar of Activities.",
            "You check every item first, choose which unit each colour belongs to, and nothing is added until you press Import.",
            "Importing the same file again will not create duplicates.",
        ],
    },
    {
        "version": "3.56",
        "date": "October 9, 2026",
        "summary": "The Office calendar now has a month view and filters.",
        "changes": [
            "Switch to Month on the Office calendar to see the whole month at a glance, like the old Word calendar.",
            "A trip that lasts several days shows as one bar across the days it covers.",
            "Filter by type, status, tag or unit to see just what you need.",
        ],
    },
    {
        "version": "3.55",
        "date": "October 9, 2026",
        "summary": "You can now add and change items on the Office calendar.",
        "changes": [
            "Use + Add on the Office calendar to put a meeting, trip, training or deadline on it, and choose who it is for.",
            "Open any item to see the details, who changed it and when, and to edit or cancel it.",
            "A cancelled item can be brought back for 30 days.",
            "If two people edit the same item at once, the second person is shown what changed instead of overwriting it.",
        ],
    },
    {
        "version": "3.54",
        "date": "October 9, 2026",
        "summary": "There is now an Office calendar page where you can see what is happening across the bureau.",
        "changes": [
            "Open Office calendar from the AWA menu to see the next two weeks: meetings, trips, trainings and holidays.",
            "Switch between your own items, your section, your division, or everything you are allowed to see.",
            "For now the calendar is for viewing; adding and editing items comes next.",
        ],
    },
    {
        "version": "3.53",
        "date": "October 9, 2026",
        "summary": "The monthly wellness register PDF is tidier, and the app is now called Office Connect everywhere.",
        "changes": [
            "The register's Office field now always reads BLHSD, instead of the section you belong to.",
            "The long note at the bottom of the register has been removed.",
            "A few places that still used the old name now say Office Connect.",
        ],
    },
    {
        "version": "3.52",
        "date": "October 9, 2026",
        "summary": "The Administrative Officer's wellness break and work arrangement requests now go to the Director.",
        "changes": [
            "Requests filed by the head of the Administrative Section are now approved by the Director, the same as a Division Chief's.",
            "Staff in the Administrative Section still send their requests to their section head.",
        ],
    },
    {
        "version": "3.51",
        "date": "October 8, 2026",
        "summary": "You can now crop and zoom your profile photo on My profile and the Welcome page.",
        "changes": [
            "When you pick a profile photo, you can drag it and zoom to choose exactly what shows in your round picture.",
            "If you already have a photo, an \"Adjust size & position\" button lets you fix it without uploading again.",
        ],
    },
    {
        "version": "3.50",
        "date": "October 8, 2026",
        "summary": "You can now add a nickname to your profile, and the home page greets you by it.",
        "changes": [
            "My profile has a new Nickname box. Whatever you put there is what the home page calls you: \"Hi, <nickname>\".",
            "If you leave it blank, the home page keeps greeting you by your first name.",
        ],
    },
    {
        "version": "3.49",
        "date": "October 8, 2026",
        "summary": "Resource persons now always need a topic, and you can add, edit or remove them on the Manage activity page.",
        "changes": [
            "When creating an activity, a resource person can no longer be saved without a topic, so none get left out by mistake.",
            "On the Manage activity page you can now add resource persons, change their topic, or remove them.",
            "You can switch a resource person for someone else, or remove them, only while nobody has rated them yet.",
        ],
    },
    {
        "version": "3.48",
        "date": "October 8, 2026",
        "summary": "The CSS menu fix now shows up without having to clear your browser's saved pages.",
        "changes": [
            "The scrolling CSS menu from the last update was not appearing for some people because their browser kept an old copy of the page styling. It now loads the new one right away.",
        ],
    },
    {
        "version": "3.47",
        "date": "October 8, 2026",
        "summary": "The CSS menu no longer gets cut off on smaller screens.",
        "changes": [
            "The long CSS menu now scrolls when your screen is too short to show it all, so Monitor and Paper entry can always be reached.",
            "On shorter screens the menu also drops the small description lines, so more of it fits at once.",
        ],
    },
    {
        "version": "3.46",
        "date": "October 8, 2026",
        "summary": "Organizers can now add their own questions to an activity's registration form and read the answers.",
        "changes": [
            "Organizers can now add their own questions to an activity's registration "
            "form, like food restrictions or arrival time. Pick a ready-made set or "
            "write your own, from the activity's manage page.",
            "Questions can be short answers, paragraphs, pick-one or pick-many lists, "
            "yes/no, a date or a time, and can be marked required.",
            "On an activity's Monitor page, each registrant now has a \"Registration "
            "answers\" link showing what they answered, and a small summary at the top "
            "counts the answers to your pick-one, pick-many and yes/no questions.",
            "The downloaded roster (XLSX) now has a column for each registration question.",
            "Answers are deleted together with the registrant's name and email when "
            "the retention period ends.",
        ],
    },
    {
        "version": "3.45",
        "date": "October 8, 2026",
        "summary": "Section managers now see their section's activities on the home page and in their to-do list.",
        "changes": [
            "An activity an administrator created for your section now shows under "
            "\"Your recent activities\" and in your to-do list, not only the ones you made yourself.",
        ],
    },
    {
        "version": "3.44",
        "date": "October 8, 2026",
        "summary": "The Archive this activity button on Monitor works again.",
        "changes": [
            "Clicking Archive this activity (or Remove on a registrant) on an activity's "
            "Monitor page now actually goes through instead of greying the button out "
            "and doing nothing.",
        ],
    },
    {
        "version": "3.43",
        "date": "October 8, 2026",
        "summary": "Section managers can now manage activities that an administrator created for their section.",
        "changes": [
            "A section manager can now open Manage activity, the registration roster, "
            "exports and reminders for any activity belonging to their own section, "
            "even when an administrator was the one who created it.",
            "Activities of other sections stay off-limits to them, as before.",
        ],
    },
    {
        "version": "3.42",
        "date": "October 8, 2026",
        "summary": "Finished activities can still be opened from Monitor.",
        "changes": [
            "Monitor now has a Concluded view, so you can still open the participant "
            "roster, CSS status and export of an activity after it is over.",
        ],
    },
    {
        "version": "3.41",
        "date": "October 6, 2026",
        "summary": "The printed wellness register now shows the full time of each break.",
        "changes": [
            "Each break on the printed wellness register now shows a time range, "
            "like 16:00 - 17:00, instead of only the time it started.",
        ],
    },
    {
        "version": "3.40",
        "date": "October 5, 2026",
        "summary": "Fixed Who's in still saying \"not reported\" after you chose AWA.",
        "changes": [
            "If you answered AWA (work from home or day off) for a day, Who's in "
            "kept showing you as \"not reported\" for it. It now counts as reported.",
        ],
    },
    {
        "version": "3.39",
        "date": "October 5, 2026",
        "summary": "Fixed the error that stopped the home page and dashboards from opening.",
        "changes": [
            "The home page, dashboards and reports showed \"Internal Server Error\" "
            "after new responses came in. They open normally again.",
        ],
    },
    {
        "version": "3.38",
        "date": "October 1, 2026",
        "summary": "Who's in now has a Week view: everyone at your level, "
                   "Monday to Friday, on one page.",
        "changes": [
            "Open Who's in and tap Week to see each person's whole week: "
            "Office, Work from home, Field, Leave or Day off for every day, "
            "with the number in the office at the bottom. Each day lists first names under Office, Field, Leave and so on.",
            "You only see people at your own level, the same as the Day view. "
            "Leave never shows a reason; a Field location is shown.",
            "A day shown faded has not been confirmed yet. It is filled in "
            "from the person's work arrangement until they report their week.",
            "Chiefs also see who hasn't reported this week.",
        ],
    },
    {
        "version": "3.37",
        "date": "October 1, 2026",
        "summary": "Holidays and work suspensions are now known to the "
                   "weekly check-in and the Who's in page.",
        "changes": [
            "The 2026 Philippine holidays and special non-working days are "
            "pre-loaded. Administrators can add, change or remove days, and "
            "add a work suspension the moment one is declared, under "
            "Administrator > Holidays.",
            "On a holiday the weekly check-in shows the day as a holiday with "
            "nothing to choose, nobody is counted as not reported for it, "
            "and Who's in shows the holiday instead of listing everyone as in "
            "the office.",
            "Eid'l Fitr and Eid'l Adha are not pre-loaded because their dates "
            "are announced late; add them once proclaimed. The fortnightly "
            "work arrangement schedule is not changed.",
        ],
    },
    {
        "version": "3.36",
        "date": "October 1, 2026",
        "summary": "A new weekly check-in: tell us where you'll be this week, "
                   "and Who's in shows it.",
        "changes": [
            "Every Monday morning you get an email with your Monday-to-Friday "
            "already filled in from your work arrangement. Tap the button, "
            "change any day to Office, Field or Leave, and confirm. No login "
            "needed.",
            "The Who's in page now has \"In the field\" and \"On leave\" "
            "groups, and what you reported for a day takes priority over your "
            "fortnight schedule. Days nobody reported still follow the "
            "schedule. Leave never shows a reason.",
            "You can also report this week or next week anytime from \"Report "
            "my week\" on the Who's in page. Administrators can switch the "
            "Monday email off, or change its day, under Email.",
            "On Tuesday, anyone who hasn't answered gets a reminder. On "
            "Wednesday, each chief gets a list of who in their area still "
            "hasn't reported.",
            "Chiefs also see a \"not reported\" mark beside those people, and "
            "a \"Haven't reported\" count, on the Who's in page.",
        ],
    },
    {
        "version": "3.35",
        "date": "October 1, 2026",
        "summary": "Reports no longer get stuck showing fewer responses than "
                   "Monitor does.",
        "changes": [
            "An activity's report could keep showing an old, smaller response "
            "count (for example 12 while Monitor showed 44) for hours. Reports "
            "now catch up to new responses within about a minute and a half.",
        ],
    },
    {
        "version": "3.34",
        "date": "October 1, 2026",
        "summary": "Managers can now archive an activity from Monitor, "
                   "for example one that was created twice by mistake.",
        "changes": [
            "Each activity's Monitor page has a new \"Archive this activity\" "
            "button. Archiving removes it from Monitor and from reports, and "
            "its registration link stops working.",
            "Nothing is deleted. An archived activity can be brought back "
            "any time from Archived activities.",
        ],
    },
    {
        "version": "3.33",
        "date": "September 29, 2026",
        "summary": "Administrators can now reopen the next work arrangement "
                   "period after its filing deadline passes.",
        "changes": [
            "The AWA filing page under Administrator now shows October 1-15 "
            "once its normal filing deadline has passed, so an administrator "
            "can reopen it before the period begins.",
        ],
    },
    {
        "version": "3.32",
        "date": "September 25, 2026",
        "summary": "Fixed a work arrangement approval that was wrongly "
                   "blocked over a week already settled by an earlier filing.",
        "changes": [
            "Approving a work arrangement request could be refused with a "
            "false \"can't take priority automatically\" message, even when "
            "the later request it pointed to had already stepped aside for "
            "it. That request can now be approved normally.",
        ],
    },
    {
        "version": "3.31",
        "date": "September 25, 2026",
        "summary": "Tapping anywhere around your companion now makes it "
                   "react, not just tapping the companion itself.",
        "changes": [
            "On the home screen and on your wellness page, tapping your "
            "companion's name, its stage line, or the space right beside it "
            "now plays with it — the same bounce and hello as tapping it "
            "directly. The \"Change companion\" link still opens your profile.",
            "Browsers now pick up the latest versions of the companion, search "
            "and usage-tracking scripts straight away after an update, rather "
            "than on the second visit.",
        ],
    },
    {
        "version": "3.30",
        "date": "September 25, 2026",
        "summary": "For administrators: six occasional screens are now tabs "
                   "of one System page.",
        "changes": [
            "Under Administrator in the menu, Backups, Audit, Sharing, Ops, "
            "UX Insights and Learned rules are now a single \"System\" entry. "
            "It opens Backups, with the other five as tabs along the top.",
            "The Administrator menu now leads with what admins use every day: "
            "Feedback, AI, Directory, Users, System, Email and AWA filing.",
            "Links and bookmarks to each screen still work, and searching "
            "for any of them by name still finds it.",
        ],
    },
    {
        "version": "3.29",
        "date": "September 25, 2026",
        "summary": "Invited events is now a tab of Monitor, and Name cleanup "
                   "a tab of Directory.",
        "changes": [
            "Monitor has two tabs: Bureau activities (who registered and who "
            "answered) and Invited events (every activity organized by an "
            "outside body, including concluded ones). Invited events no "
            "longer has its own menu entry.",
            "Directory has two tabs: Org units & people, and Name cleanup — "
            "the tool for tidying up and merging external speakers' names, "
            "which used to be a small button at the top of the page.",
            "Old links and bookmarks to both still work, and searching for "
            "either by name still finds it.",
        ],
    },
    {
        "version": "3.28",
        "date": "September 25, 2026",
        "summary": "The CSS dashboards are now one Insights page, with tabs "
                   "for Pulse, People, Participation, Teams and Trends.",
        "changes": [
            "Under CSS in the menu, the five dashboard entries are now a single "
            "\"Insights\" entry that opens Pulse.",
            "Every dashboard has the same row of tabs at the top, so you can "
            "move between them without going back to the menu. The unit you "
            "picked comes along with you, and so does the period on the four "
            "tabs that use the same periods.",
            "Links, bookmarks and downloads to the individual dashboards all "
            "still work, and searching for one by name still finds it.",
        ],
    },
    {
        "version": "3.27",
        "date": "September 25, 2026",
        "summary": "The home screen now opens with \"Your to-do\": what you "
                   "need to do next, each with a button that takes you "
                   "straight there.",
        "changes": [
            "Approvers see how many requests are waiting on them, with a "
            "Review button that opens the Approvals inbox.",
            "Your wellness break: how many hours you have left this week "
            "(Apply for a break), or a reminder to check in after a break "
            "you've taken.",
            "Your work arrangement: whether you still need to file for the "
            "next period and when it's due, or that it's filed and waiting "
            "for approval.",
            "How many people are in the office today.",
            "Organizers see their own upcoming and ongoing activities, with how "
            "many people have finished, and a Monitor button that opens each "
            "one directly.",
            "Things that need you come first, then things you're waiting on, "
            "then things already done. The team charts are still below.",
        ],
    },
    {
        "version": "3.26",
        "date": "September 25, 2026",
        "summary": "UX Insights (Administrator) now also measures whether "
                   "tasks go through, how often searches find nothing, and "
                   "how fast pages load.",
        "changes": [
            "Forms that are submitted are now counted alongside forms left "
            "half-filled, so each screen shows what share of started forms "
            "gets abandoned. Pages that come back with an error message, and "
            "\"not allowed\" / \"not found\" / server-error pages people "
            "hit, are counted per screen too.",
            "Every search is now counted, not just the ones that found "
            "nothing, so UX Insights can show what share of searches come up "
            "empty.",
            "Page load times and whether a page was opened on a phone, tablet "
            "or computer are recorded, so slow screens and phone-heavy screens "
            "stand out.",
            "Each recorded event now notes which version of Office Connect "
            "received it, so a change in the numbers can be matched to an "
            "update. The downloadable handoff also breaks screen visits down "
            "by role.",
            "As before, nothing anyone types is ever recorded — not search "
            "terms that found results, not error messages, not form contents.",
        ],
    },
    {
        "version": "3.25",
        "date": "September 25, 2026",
        "summary": "Approvers now have one Approvals inbox for both wellness "
                   "breaks and work arrangements.",
        "changes": [
            "Everything waiting on your decision is on one page, Approvals, "
            "with a count for each kind at the top. Whichever kind has "
            "requests waiting is shown first.",
            "The Approvals links under Wellness and under AWA, the bell, the "
            "home-screen notes and the approval emails all open this inbox. "
            "Old links to the separate pages still work and land on the "
            "right section.",
            "After you approve or deny something you come back to the inbox, "
            "so you can move straight on to the next request.",
            "On a phone, wellness requests now show as cards instead of a table "
            "that ran off the side of the screen.",
        ],
    },
    {
        "version": "3.24",
        "date": "September 25, 2026",
        "summary": "UX Insights (Administrator) now shows where each "
                   "on-screen error happened, not just that one did.",
        "changes": [
            "Client errors in UX Insights and its downloadable handoff now "
            "carry the error message, the file and line it came from, and "
            "the first few steps that led to it — enough to find and fix the "
            "bug. Before, each one only said \"Error\".",
            "A script or stylesheet that fails to load is now recorded too.",
            "As before, nothing anyone typed is ever captured, and scripts from "
            "outside Office Connect are recorded by their site name only.",
        ],
    },
    {
        "version": "3.23",
        "date": "September 25, 2026",
        "summary": "Monitor can now remind everyone who hasn't finished an "
                   "activity's feedback, in one click.",
        "changes": [
            "A new \"Remind N not finished\" button on an activity's Monitor "
            "page emails each registrant who hasn't completed the feedback "
            "their own link back to the forms they still owe. People who have "
            "finished, or have no email on file, aren't emailed.",
            "It asks before sending, and can only be used once an hour per "
            "activity, so nobody gets the same reminder twice by accident. "
            "The page shows when the last reminder went out.",
            "It isn't offered once an activity is closed or its response "
            "window has ended, since the link would only land on a closed "
            "form.",
            "Admins can turn these reminders off under Admin → Email "
            "(\"Monitor — remind unfinished registrants\").",
        ],
    },
    {
        "version": "3.22",
        "date": "September 25, 2026",
        "summary": "When an email can't be sent because the mail relay isn't "
                   "set up right, Office Connect now says so plainly instead "
                   "of reporting it as \"likely sent\".",
        "changes": [
            "If the mail relay's access setting keeps it from running, a "
            "resend on Monitor, an invite or a password reset now shows "
            "\"Email not sent\" with the setting to fix, instead of "
            "\"Email likely sent — check the recipient's inbox\". Nothing "
            "went out in that case, so it is safe to try again once it's "
            "fixed.",
            "The same goes when the relay script itself can't run (wrong code "
            "pasted, or the deployment was never authorized).",
            "Nothing changes for the case where the relay did run but its "
            "confirmation came back garbled — that is still shown as likely "
            "sent, so nobody is prompted to send the same email twice.",
        ],
    },
    {
        "version": "3.21",
        "date": "September 25, 2026",
        "summary": "Things people kept clicking on now do something: the "
                   "companion's \"how it grows\" list, your greeting on the "
                   "home screen, the \"in the office\" count, and the "
                   "registration link on Monitor.",
        "changes": [
            "On the home screen and your profile, each way to grow your "
            "companion (\"Take a wellness break +10\" and the rest) is now a "
            "link to where you do it.",
            "Your photo and greeting at the top of the home screen now open "
            "your profile.",
            "The \"in the office today\" number on the work arrangement "
            "card now opens the day-by-day list of who's in.",
            "Monitor has a Copy button next to the registration link, and "
            "clicking the link itself selects all of it.",
            "On Work arrangement approvals, the note about a shared week now "
            "names whose arrangement it is (it used to say \"your\") and "
            "links to that period's schedule.",
        ],
    },
    {
        "version": "3.20",
        "date": "September 25, 2026",
        "summary": "UX Insights (Administrator) now ranks real interface "
                   "problems first, instead of signatures, clicks on empty "
                   "space and people happily tapping the companion.",
        "changes": [
            "Drawing your signature, clicking an empty part of the page, "
            "and selecting text to copy it are no longer counted as "
            "\"dead clicks\".",
            "Tapping a working button many times in a row (feeding the "
            "companion, for example) is now shown as \"rapid taps\" and "
            "weighs much less than frantic clicking on something that "
            "doesn't respond.",
            "Old Spot Feedback that is already Done or Won't fix no longer "
            "pushes unrelated items up the list, and the downloadable "
            "handoff now lists each matched comment once instead of "
            "repeating it under every item on the same screen.",
        ],
    },
    {
        "version": "3.19",
        "date": "September 25, 2026",
        "summary": "Admin → Users can now assign a section's own division "
                   "chief to cover its wellness and AWA approvals while the "
                   "section chief is on leave, deciding as division chief "
                   "rather than as a stand-in.",
        "changes": [
            "The Temporary OIC picker now also offers each section's "
            "division chief, labeled \"(Division Chief)\" in the list, "
            "alongside the section's own staff.",
            "Assigning the division chief works the same way as any other "
            "temporary OIC — the section's requests start routing to them "
            "too, alongside the section chief — but it's tracked and shown "
            "as \"as division chief,\" not \"acting OIC,\" since they "
            "already outrank the seat.",
            "That distinction matters for the division chief's OWN "
            "requests: covering a section no longer changes who decides "
            "them. Before this fix, a division chief assigned this way "
            "could end up with nobody able to approve their own wellness "
            "break or work arrangement. Their requests now keep going to "
            "the Director exactly as they always did.",
        ],
    },
    {
        "version": "3.18",
        "date": "September 25, 2026",
        "summary": "The Director's own wellness and work arrangement "
                   "requests are now approved instantly, and a temporary "
                   "OIC's own requests now go to the division chief (or the "
                   "Director) instead of sitting with the chief they're "
                   "standing in for.",
        "changes": [
            "The Director has nobody above them to send their own wellness "
            "break or work arrangement to, so it used to sit pending, "
            "waiting for an administrator to notice and approve it by hand. "
            "It's now approved automatically the moment the Director files "
            "it, with a note on the request saying so.",
            "A temporary OIC's own wellness break and work arrangement "
            "requests no longer route to the chief they're covering for — "
            "who is very likely the person on leave, i.e. unavailable to "
            "decide it. An OIC covering a section now has their own request "
            "decided by the division chief, and an OIC covering a division "
            "by the Director, the same as a genuine chief at that level. "
            "The \"Send for approval of...\" copy on the apply pages now "
            "names that person too.",
        ],
    },
    {
        "version": "3.17",
        "date": "September 25, 2026",
        "summary": "After you approve a work arrangement, it's now easy to "
                   "download the ANNEX C that actually shows it.",
        "changes": [
            "Approvals are always for the next half-month, but the schedule "
            "page opens on the current one — so a freshly approved "
            "arrangement looked missing from the downloaded form.",
            "The schedule page now shows a highlighted box for the period "
            "being filed, with its own PDF and Excel download buttons.",
            "After approving or denying a request, the approvals page links "
            "straight to that period's schedule and ANNEX C downloads.",
        ],
    },
    {
        "version": "3.16",
        "date": "September 24, 2026",
        "summary": "Your wellness companion now wears earned gear that "
                   "grows richer alongside it, and shows off when it does.",
        "changes": [
            "Every companion — plant or animal — now wears a small badge "
            "of honor that upgrades as it grows: a plain collar early on, "
            "then a scarf, a medal, a cape, and finally a jeweled crown "
            "once it's fully grown.",
            "When your companion earns its next piece of gear, you'll see "
            "a \"New gear!\" pop-up and hear a soft chime, the same way "
            "you're told about a new badge.",
        ],
    },
    {
        "version": "3.15",
        "date": "September 24, 2026",
        "summary": "The system administrator's check-in account no longer "
                   "shows up as a staff member on the work arrangement "
                   "schedule.",
        "changes": [
            "ray@gmail.com is an admin account used to check on the system "
            "once in a while, not an actual staff member, but it was "
            "appearing as an unfiled row on the ANNEX C work arrangement "
            "roster (on screen and in the printed export) and getting the "
            "\"please file\" nudge like everyone else. It's now left off "
            "the staff roster and the filing reminders, while keeping "
            "every admin permission it had.",
        ],
    },
    {
        "version": "3.14",
        "date": "September 24, 2026",
        "summary": "Pages now use the full width of a laptop or desktop "
                   "screen instead of a narrow strip down the middle.",
        "changes": [
            "Every page used to stop at the same narrow width, leaving wide "
            "empty margins on a big screen. Dashboards and lists now stretch "
            "much wider, and busy admin tables like Users, Directory, Audit "
            "and Reports use nearly the whole screen.",
            "On Admin → Users each person's role, access and buttons now sit "
            "on one line on a wide screen, and nothing is cut off at the right "
            "edge any more.",
            "Forms such as requesting a wellness break or filing a work "
            "arrangement stay a comfortable reading width, centred on the "
            "screen.",
            "The home page shows its three cards side by side on a wide "
            "screen.",
        ],
    },
    {
        "version": "3.13",
        "date": "September 24, 2026",
        "summary": "The Temporary OIC picker no longer offers a section's own "
                   "chief as their own stand-in.",
        "changes": [
            "Admin → Users' \"Temporary OIC\" picker listed every active "
            "account in a section, including whoever already holds that "
            "section's chief seat — so, for example, the Administrative "
            "Section's picker offered its own chief as a choice for covering "
            "their own leave. The picker now only offers someone else in the "
            "section; assigning the chief to their own seat is refused the "
            "same way picking someone from a different section is.",
        ],
    },
    {
        "version": "3.12",
        "date": "September 24, 2026",
        "summary": "The Administrative Section's chief is now recognized "
                   "automatically as its approver for wellness break and "
                   "work arrangement requests.",
        "changes": [
            "The system reads who is a section's chief from that person's "
            "\"Designation\" in the directory, matching wording like "
            "\"Section Head\" or \"Section Chief\". The Administrative "
            "Section's chief carries the designation \"Admin Head\" "
            "instead, so it wasn't being recognized — the section's "
            "wellness and work arrangement requests had nobody to "
            "automatically route to. \"Admin Head\" (and \"Administrative "
            "Head\") are now recognized the same way.",
        ],
    },
    {
        "version": "3.11",
        "date": "September 24, 2026",
        "summary": "Admins can now assign a temporary OIC to cover a section's "
                   "wellness break and work arrangement approvals while the "
                   "section chief is on leave.",
        "changes": [
            "Admin → Users has a new \"Temporary OIC\" panel, one row per "
            "section: pick anyone from that section and they start receiving "
            "the section's pending wellness break and AWA requests too, "
            "alongside the section chief, until you remove them. Only one "
            "person can hold it at a time per section — assigning someone "
            "new replaces whoever had it.",
            "The change is additive: the substantive chief keeps approving "
            "their own section's requests the whole time, so nothing has to "
            "be undone the day they're back from leave.",
        ],
    },
    {
        "version": "3.10",
        "date": "September 24, 2026",
        "summary": "An administrator could approve or deny another section's "
                   "wellness break or work arrangement request — that's now "
                   "limited to their own section.",
        "changes": [
            "Deciding a wellness break or work arrangement request now checks "
            "that it's actually routed to that administrator — their own "
            "section, or a request no section chief can reach — the same "
            "rule the approvals queue already followed. Before, an "
            "administrator could approve or deny a request from any "
            "section, even though their own queue only ever showed the ones "
            "that were really theirs to decide.",
        ],
    },
    {
        "version": "3.09",
        "date": "September 24, 2026",
        "summary": "The Alternative Work Arrangement approvals queue and the "
                   "admin Users list are now readable on a phone or narrow "
                   "laptop window.",
        "changes": [
            "The Alternative Work Arrangement approvals queue didn't adjust "
            "for a phone screen at all, so its five columns squeezed into "
            "an unreadable strip. It now stacks into readable cards on a "
            "narrow screen, the same as other tables in the app.",
            "The admin Users & roles page's tables already did this, but "
            "only below 640 pixels wide — a normal laptop or tablet window "
            "between roughly 640 and 960 pixels wide could still clip a "
            "column off-screen (like Status disappearing). They now stack "
            "properly all the way up to 960 pixels.",
        ],
    },
    {
        "version": "3.08",
        "date": "September 24, 2026",
        "summary": "ANNEX C now prints Alexander Medel as \"Prepared by,\" "
                   "with his actual position pulled from the directory.",
        "changes": [
            "The internal work arrangement schedule's \"Prepared by\" line "
            "is now pinned to Alexander Medel, and his title on the "
            "printout is read live from the directory (Administrative "
            "Officer IV) instead of needing to be typed in and kept in "
            "sync by hand.",
            "\"Approved by\" is unchanged — it still follows the directory's "
            "Director seat.",
        ],
    },
    {
        "version": "3.07",
        "date": "September 23, 2026",
        "summary": "\"Resend email\" and reminder emails no longer show a "
                   "false failure when the message actually went out.",
        "changes": [
            "The mail relay sometimes doesn't confirm a send even though "
            "the email genuinely went out — that was being reported as "
            "\"Email send failed,\" which risked someone clicking Resend "
            "and getting the same message twice. It's now reported as sent, "
            "with a note to check the recipient's inbox if you want to be "
            "sure, instead of inviting a resend that could double it up.",
        ],
    },
    {
        "version": "3.06",
        "date": "September 23, 2026",
        "summary": "Fixed the mail relay's retry (added in 3.05) so it can "
                   "no longer send the same email twice.",
        "changes": [
            "Yesterday's retry could, in a rare case, resend the exact "
            "same email a second time: if the relay had actually sent the "
            "message but only its confirmation failed to come back, the "
            "retry re-sent the whole message instead of just re-checking "
            "the confirmation. The retry now only re-checks whether the "
            "message went out — it can no longer trigger a second send.",
        ],
    },
    {
        "version": "3.05",
        "date": "September 23, 2026",
        "summary": "The mail relay now retries once before reporting a "
                   "failed send, so a brief hiccup isn't mistaken for a "
                   "broken setup.",
        "changes": [
            "If the mail relay answers with something other than the "
            "expected reply, the system now waits a couple of seconds and "
            "tries that one send again before giving up — Google's relay "
            "occasionally needs a moment to wake up on a deployment that "
            "hasn't sent mail in a while, even when it's set up correctly. "
            "A send that only needed the retry now goes through instead of "
            "being reported as failed.",
        ],
    },
    {
        "version": "3.04",
        "date": "September 23, 2026",
        "summary": "Added a Hybrid option for an activity's format, and made "
                   "the mail relay's error message easier to act on.",
        "changes": [
            "New survey's Format field now offers Hybrid alongside "
            "Face-to-face and Online. A Hybrid activity's venue field asks "
            "for both the venue and a platform link, and Hybrid now shows "
            "up correctly everywhere Format is displayed or reported on — "
            "the summary page, MRR exports, and dashboard trends — instead "
            "of quietly being counted as Face-to-face.",
            "If “Resend email” on Monitor fails with “mail "
            "relay did not return JSON,” the message now points "
            "straight at docs/MAIL_RELAY_SETUP.md and at “Send test "
            "to me” on Admin → Email so it can be fixed and "
            "re-checked without guessing.",
        ],
    },
    {
        "version": "3.03",
        "date": "September 18, 2026",
        "summary": "A Section Manager can now add an outside resource person "
                   "directly from New survey, without needing an admin.",
        "changes": [
            "Creating a survey with a guest speaker who isn't already in "
            "the directory used to be a dead end for a Section Manager — "
            "adding a new external resource person required the "
            "Directory, which is admin-only. There's now a \u201c+ Add an "
            "external resource person\u201d link right on the New survey "
            "screen that a Section Manager can use themselves, without "
            "getting the rest of Directory's admin tools.",
        ],
    },
    {
        "version": "3.02",
        "date": "September 18, 2026",
        "summary": "Withdrawing a wellness break now tells the approver, so "
                   "you're not left wondering if they know.",
        "changes": [
            "When you withdraw a wellness break request, the approver — "
            "whoever approved it, or whoever it was waiting on — now gets "
            "an email saying it's off their plate, including your reason "
            "if you gave one. An admin can turn this off from the Email "
            "screen like any other notification.",
        ],
    },
    {
        "version": "3.01",
        "date": "September 18, 2026",
        "summary": "Withdrawing a wellness break now asks why, for a record "
                   "of it.",
        "changes": [
            "Withdrawing a wellness break request now offers an optional "
            "box to say why (e.g. urgent work came up). It's shown right "
            "next to that request's \"cancelled\" status afterward, and "
            "withdrawing still works exactly the same if you leave it "
            "blank.",
        ],
    },
    {
        "version": "3.00",
        "date": "September 18, 2026",
        "summary": "Your wellness companion now leans toward your cursor "
                   "for a bit more depth, with a soft shadow underneath.",
        "changes": [
            "Your companion on the Wellness page (and on the home screen) "
            "now leans gently in 3D toward your mouse pointer while it's "
            "hovering over it, and sits above a soft shadow — a small bit "
            "of extra life on top of its usual sway and idle animations. "
            "Turned off automatically if your device is set to reduce "
            "motion.",
        ],
    },
    {
        "version": "2.99",
        "date": "September 18, 2026",
        "summary": "Date fields (like Date collected on paper entry) now "
                   "always open their calendar when you tap or click them.",
        "changes": [
            "A date field sometimes didn't respond when tapped or clicked, "
            "depending on exactly where on the field you touched — most of "
            "the field looked clickable but only a sliver near the edge "
            "actually opened the calendar. Every date field now opens its "
            "calendar no matter where in the field you tap or click.",
        ],
    },
    {
        "version": "2.98",
        "date": "September 18, 2026",
        "summary": "A top-menu dropdown that opened near the right edge of "
                   "the screen no longer runs off the side, hiding its "
                   "other choices.",
        "changes": [
            "Menus in the top navigation bar always opened toward the "
            "right of their button. For a menu sitting close to the right "
            "edge of the screen (e.g. on a narrower laptop window), that "
            "pushed part of the menu off-screen with no way to reach the "
            "hidden choices. Such a menu now opens toward the left instead "
            "whenever opening toward the right would run off-screen, so "
            "every choice stays visible.",
        ],
    },
    {
        "version": "2.97",
        "date": "September 18, 2026",
        "summary": "Wellness breaks can now only be requested for a day in "
                   "the current work week, not weeks ahead.",
        "changes": [
            "Filing a wellness break used to let you plan up to 4 weeks "
            "ahead. It's now limited to the current Monday-to-Friday work "
            "week, so plans stay close to when you'll actually take them "
            "and don't need to be cancelled or moved as the week changes.",
            "The \"Request a break\" button on the wellness page now turns "
            "off as soon as this week's 2 hours are fully claimed, since "
            "there's no longer a future week to fall back on.",
        ],
    },
    {
        "version": "2.96",
        "date": "September 18, 2026",
        "summary": "The wellness break form's time slots can now be paired "
                   "with an exact minute, for anyone who needs one that "
                   "isn't on the half-hour.",
        "changes": [
            "The new time-slot grid only offered times on the hour or "
            "half-hour. A \"Need a specific minute?\" box next to it now "
            "lets you type any exact time (like 9:16 or 2:11 PM) instead — "
            "it's checked against the same rules when you submit.",
        ],
    },
    {
        "version": "2.95",
        "date": "September 18, 2026",
        "summary": "Requesting a wellness break now shows you which dates and "
                   "times are actually open, instead of making you type them "
                   "and find out after submitting.",
        "changes": [
            "The wellness break request form now shows the day as tappable "
            "date buttons and the start time as a grid of time slots, "
            "instead of the old calendar/clock text boxes. Times that "
            "wouldn't be allowed (too soon, already booked, or no hours "
            "left that week) are greyed out with the reason shown when you "
            "point at them, so you find out before you submit, not after.",
            "Times that would run into your lunch break are marked with a "
            "fork-and-plate icon as a heads-up to coordinate with your "
            "section — they're still allowed, just flagged.",
            "Fixed a bug where two overlapping break requests on the same "
            "day (for example 9:00-10:00 and 9:30-10:30) could both be "
            "accepted as long as their start times weren't exactly the "
            "same.",
        ],
    },
    {
        "version": "2.94",
        "date": "September 18, 2026",
        "summary": "The Email screen now lets an admin adjust the timing of "
                   "the scheduled reminders, not just turn them on or off.",
        "changes": [
            "A new Timing section on the Email screen lets an admin change "
            "how many days ahead the day-before activity reminder goes out, "
            "how many days before its link expires the wellness approval "
            "reminder fires, which weekday the pending-approvals digest and "
            "the wellness filing nudge go out on, how many days after an "
            "activity ends its CSM results are announced, and how many days "
            "before the deadline the work-arrangement filing nudge fires. "
            "These were previously fixed in the code with no way to change "
            "them without a new release.",
            "The same section also exposes how many days the Email screen's "
            "send history is kept before being cleared out (previously "
            "fixed at 90 days with no admin control), matching the "
            "retention settings already available for AI logs and UI "
            "activity logs.",
        ],
    },
    {
        "version": "2.93",
        "date": "September 18, 2026",
        "summary": "The Email screen now shows a history of what was sent, "
                   "skipped, or failed.",
        "changes": [
            "The Email screen now lists the newest 50 emails the system has "
            "tried to send, each marked sent, failed, or skipped because a "
            "feature was turned off — so an admin can answer \"why didn't I "
            "get that email\" without asking anyone. This history is kept for "
            "90 days.",
        ],
    },
    {
        "version": "2.92",
        "date": "September 18, 2026",
        "summary": "The Email screen can now show a preview of each message "
                   "and send a sample to yourself.",
        "changes": [
            "On the Email screen, every notification now has a Preview you can "
            "open to see exactly what it looks like, and a “Send test to me” "
            "button that emails a sample straight to your own inbox — so you "
            "can check a message before deciding whether to turn it on.",
        ],
    },
    {
        "version": "2.91",
        "date": "September 18, 2026",
        "summary": "New Email screen under Administrator lets an admin turn "
                   "individual notification emails on or off.",
        "changes": [
            "Administrators now have an Email screen where every notification "
            "email — event reminders, approval requests, the weekly digest, and "
            "more — can be switched on or off one at a time, with account "
            "invites and password resets always left on so nobody gets locked "
            "out.",
        ],
    },
    {
        "version": "2.90",
        "date": "September 18, 2026",
        "summary": "More groundwork for the upcoming admin email on/off screen "
                   "— still no visible change.",
        "changes": [
            "No visible change yet — the system can now also skip a scheduled "
            "reminder email (like the weekly digest or a filing nudge) once an "
            "admin turns it off; there just isn't a switch to flip yet, so "
            "every reminder keeps sending exactly as before.",
        ],
    },
    {
        "version": "2.89",
        "date": "September 18, 2026",
        "summary": "More groundwork for the upcoming admin email on/off screen "
                   "— still no visible change.",
        "changes": [
            "No visible change yet — the system can now actually skip a "
            "notification email once an admin turns it off; there just isn't "
            "a switch to flip yet, so every email keeps sending exactly as "
            "before.",
        ],
    },
    {
        "version": "2.88",
        "date": "September 18, 2026",
        "summary": "Behind-the-scenes groundwork for an upcoming admin screen "
                   "to turn individual system emails on or off.",
        "changes": [
            "No visible change yet — this lays the foundation for an admin "
            "control panel over which automatic emails the system sends.",
        ],
    },
    {
        "version": "2.87",
        "date": "September 18, 2026",
        "summary": "Results emails now only cover activities that finish from "
                   "now on, not everything already in the records.",
        "changes": [
            "Yesterday's new \"CSM results are ready\" emails treated every "
            "activity ever recorded as one nobody had been told about yet, so "
            "the first run could have written to every organizer, chief and "
            "resource person about activities that finished months or years "
            "ago.",
            "Everything already on file is now marked as accounted for, "
            "quietly and with no email sent. Activities that finish from here "
            "on are announced exactly as intended.",
        ],
    },
    {
        "version": "2.86",
        "date": "September 18, 2026",
        "summary": "The system now sends the reminders and confirmations "
                   "people used to have to chase by hand.",
        "changes": [
            "Registering for an activity now sends you a confirmation email "
            "with your own link back to it, and finishing an activity's "
            "feedback emails you your Certificate of Appearance.",
            "A raffle winner who registered with an email address is told "
            "they won, instead of only finding out if they were watching "
            "the draw screen.",
            "The day before an activity, everyone registered for it — plus "
            "the organizer and their section chief — gets a reminder.",
            "Once an activity's feedback closes, its results are emailed to "
            "the organizer and their chief, and each resource person is sent "
            "their own results for the session they ran.",
            "Chiefs get a Monday summary of every wellness break and work "
            "arrangement still waiting on their decision, and a nudge if a "
            "request has been sitting unanswered long enough that its "
            "approve/deny link is about to expire.",
            "Staff who haven't used the week's wellness break are reminded "
            "the day before it lapses, and staff who haven't filed a work "
            "arrangement are reminded the day before the deadline. Anyone "
            "marked \"No AWA\" is left out of that one.",
            "When an admin reopens a closed work-arrangement period, the "
            "staff who still need to file are told it's open again.",
        ],
    },
    {
        "version": "2.85",
        "date": "September 18, 2026",
        "summary": "A wellness break request can now be approved or denied "
                   "straight from the notification email, no sign-in needed.",
        "changes": [
            "The email a chief gets when someone requests a wellness break "
            "now has Approve and Deny links. Tapping one opens a page "
            "confirming the details, and pressing Confirm decides it right "
            "then — the same as using the Wellness approvals page.",
            "The email's dashboard link is still there too, for anyone who'd "
            "rather review the full queue first.",
            "Each link only works for that one request, expires after 14 "
            "days, and stops working the moment the request is decided by "
            "anyone — so an old or already-used link can't do anything.",
        ],
    },
    {
        "version": "2.84",
        "date": "September 18, 2026",
        "summary": "Notification emails now look like a formal, official "
                   "message instead of plain text.",
        "changes": [
            "The email you get to set up your account or reset your "
            "password is now a proper formatted message with the Office "
            "Connect name and a clear button, instead of a bare wall of "
            "text.",
            "The same formal look now applies to every other email the "
            "system sends: event notifications, wellness and work-"
            "arrangement approvals and decisions, and Spot Feedback "
            "replies.",
        ],
    },
    {
        "version": "2.83",
        "date": "September 17, 2026",
        "summary": "Invite and password-reset emails can now actually be "
                   "sent from this server.",
        "changes": [
            "This server's network blocks the normal email channel "
            "entirely, on every port, so no email provider could work "
            "here \u2014 that's why sending kept timing out.",
            "Email now goes out over a secure web connection instead, "
            "sent from the bureau's own Google mailbox. An administrator "
            "sets this up once; see docs/MAIL_RELAY_SETUP.md.",
        ],
    },
    {
        "version": "2.82",
        "date": "September 17, 2026",
        "summary": "Added support for Gmail's alternate secure-email port, "
                   "in case the usual one is blocked on this server.",
        "changes": [
            "If invite/reset emails keep timing out, an admin can now set "
            "the mail port to 465 instead of 587 — the app automatically "
            "uses the right connection method for whichever port is set.",
        ],
    },
    {
        "version": "2.81",
        "date": "September 17, 2026",
        "summary": "Fixed invite/reset emails failing with an internal "
                   "error right after the v2.80 network fix shipped.",
        "changes": [
            "The v2.80 fix for the \"network unreachable\" send error had "
            "a bug of its own that made every send fail immediately with "
            "an internal error. Sending is fixed for real now.",
        ],
    },
    {
        "version": "2.80",
        "date": "September 17, 2026",
        "summary": "Fixed account invite/reset emails failing to send on "
                   "this server with a \"network unreachable\" error.",
        "changes": [
            "Invite and password-reset emails now connect over IPv4, "
            "working around a hosting quirk where this server's network "
            "path for the newer address format wasn't working.",
        ],
    },
    {
        "version": "2.79",
        "date": "September 17, 2026",
        "summary": "An admin now sees the real reason an invite or reset "
                   "email failed to send, instead of a misleading "
                   "\"email isn't configured\" message.",
        "changes": [
            "If email IS set up but the actual send fails (wrong "
            "password, blocked connection, etc.), the Users page now "
            "shows that real error next to the link, instead of "
            "wrongly saying email was never configured.",
        ],
    },
    {
        "version": "2.78",
        "date": "September 16, 2026",
        "summary": "Accounts are now set up and recovered by emailed link "
                   "instead of a shared temporary password.",
        "changes": [
            "Creating a staff account now emails them a link to choose "
            "their own password, instead of everyone starting on the "
            "same temporary one.",
            "\"Forgot your password?\" now really works by email: enter "
            "your address and, if you have an account, a reset link is "
            "sent to you.",
            "An admin's \"Send reset link\" on the Users page emails the "
            "person a link too — their old password keeps working until "
            "they use it.",
            "Until email is fully set up on this server, these links are "
            "shown to the admin on the Users page to pass along directly.",
        ],
    },
    {
        "version": "2.77",
        "date": "September 16, 2026",
        "summary": "Choosing a profile photo now works on your phone, not "
                   "just on a computer.",
        "changes": [
            "On My profile and the first-time welcome screen, tapping "
            "“Choose a photo” did nothing on some devices — the button "
            "wasn't actually wired up to open your photo picker. It now "
            "opens every time, on a phone the same as on a desktop.",
        ],
    },
    {
        "version": "2.76",
        "date": "September 16, 2026",
        "summary": "A period an admin reopened for filing now actually shows "
                   "up as a choice on the filing form.",
        "changes": [
            "The Work Arrangement hub already showed a reopened period as "
            "fileable, but the filing form itself still only listed the "
            "normal upcoming periods — so the reopened one had nowhere to "
            "go. It now appears there too, marked “reopened by an admin.”",
        ],
    },
    {
        "version": "2.75",
        "date": "September 16, 2026",
        "summary": "An admin can now temporarily reopen a work-arrangement "
                   "filing period after its deadline has passed.",
        "changes": [
            "Filing for a work arrangement normally closes on the Friday "
            "before the period starts. An admin can now reopen a period "
            "that already closed, so you can file or change your own "
            "arrangement for it again — from Admin → AWA filing.",
            "A period an admin has reopened shows on your Work Arrangement "
            "page as “Reopened by an admin,” the same as any other "
            "period still open for filing.",
        ],
    },
    {
        "version": "2.74",
        "date": "September 2, 2026",
        "summary": "An alternative work arrangement is now one day a week, "
                   "counted by the calendar week rather than by the period.",
        "changes": [
            "You can only have one work-from-home or day-off in any one "
            "week (Monday to Friday). Regular on-site weeks are not "
            "affected.",
            "This is now counted across the 15th/16th split. If Monday the "
            "14th is your work-from-home day, the 16th, 17th and 18th are "
            "in the same week and cannot be — even though they are filed "
            "for under the next period.",
            "If a day is already taken, filing says which week it clashes "
            "with and which day you already have, so you can pick another "
            "one. Arrangements approved before this change stay as they "
            "are.",
        ],
    },
    {
        "version": "2.73",
        "date": "August 26, 2026",
        "summary": "Approvers of wellness breaks or work arrangements now see "
                   "what's waiting on them without opening the queue first.",
        "changes": [
            "If you approve wellness breaks or work arrangements, the home "
            "page now shows how many requests are waiting for your "
            "decision, with a link straight to them.",
            "The notification bell (🔔) shows that same count from any "
            "page, and now also tells you once your own wellness break or "
            "work arrangement request has been approved or denied.",
        ],
    },
    {
        "version": "2.72",
        "date": "August 24, 2026",
        "summary": "The “Activities” card on the home page now fills the "
                   "row instead of sitting at half width.",
        "changes": [
            "The home page shows three cards: Wellness, Alternative Work "
            "Arrangement, and Activities. On a laptop or desktop screen the "
            "first two sit side by side, and Activities used to be left "
            "underneath at half width with empty space beside it. It now "
            "stretches across the full row, in both Team and Me view.",
        ],
    },
    {
        "version": "2.71",
        "date": "August 24, 2026",
        "summary": "The home page's cards line up evenly on a laptop or "
                   "desktop screen, in both Team and Me view.",
        "changes": [
            "On a wide screen the wellness and Alternative Work Arrangement "
            "cards sit side by side. When one had more to show than the "
            "other, the shorter card used to leave an odd empty gap on the "
            "page before the next card started. They now match height, so "
            "the row looks tidy whichever card has more to say.",
        ],
    },
    {
        "version": "2.70",
        "date": "August 16, 2026",
        "summary": "Sign with your finger. Draw your signature once on “My "
                   "profile” and it is stamped on the wellness breaks you "
                   "approve — on the day of each break, not once a week.",
        "changes": [
            "“My profile” has a signing box. Draw your signature with a finger, "
            "a stylus or a mouse — on a phone as easily as on a PC — press Save, "
            "and it is kept for you. Undo takes back a stroke, Clear starts "
            "over, and you can replace or remove it any time. There is no file "
            "to scan or upload, and nobody has to do it for you.",
            "On the monthly wellness register, each break now carries the "
            "signature of the chief who approved it, inside that day's box. "
            "Before, one “Approved By” line covered a whole week, so a week "
            "approved by two people could not be told apart.",
            "A chief who has not drawn a signature yet changes nothing: their "
            "name still prints over “Digitally approved and signed”, exactly as "
            "the register has always read.",
            "One signature per person: if you are named as the signatory on a "
            "Certificate of Appearance, the signature you drew is the one that "
            "prints there too — replacing any image an administrator uploaded "
            "for you.",
            "Your signature is never public. Only you can see it on your "
            "profile, and it is shown to nobody else except as the signature "
            "printed on what you have signed.",
        ],
    },
    {
        "version": "2.69",
        "date": "August 16, 2026",
        "summary": "The activities card on your home page said “Last 90 "
                   "days” but its charts were reading a whole year. They "
                   "now cover the same 90 days as the list above them.",
        "changes": [
            "Swipe past the list and every chart — how many a month, how they "
            "were rated, who spoke most, how many answered — now covers "
            "exactly the 90 days the card says it does. Before, the heading "
            "stayed on screen claiming 90 days while the charts quietly "
            "showed twelve months.",
            "The month chart now shows only the months those 90 days actually "
            "touch, and says the date it counts from — “2 activities since "
            "May 18” — so there is no guessing where the window starts.",
            "A month is only called the busiest when the 90 days cover it "
            "from the first to the last day. Today's month is always only "
            "part-counted, so calling it the busiest would be comparing half "
            "a month against whole ones.",
        ],
    },
    {
        "version": "2.68",
        "date": "August 16, 2026",
        "summary": "New page: who is in the office, day by day — by name. See "
                   "who is at their desk today, and for anyone who isn't, "
                   "whether they are off or working from home.",
        "changes": [
            "AWA → “Who's in the office” answers the question the "
            "fortnightly schedule never did: on a given day, who is actually "
            "in. Everyone is listed by name under In the office, Working from "
            "home, or Day off.",
            "Step through the days with ‹ previous / next ›, or pick a date. "
            "Weekends are skipped, since nobody is scheduled on them.",
            "Anyone marked No AWA is listed with the reason they gave, and "
            "anyone who never filed is listed separately rather than being "
            "counted as present — a blank row is not a person at their desk.",
            "This page is open to everyone, not just section heads. Knowing "
            "whether a colleague is in before you walk over is not the same "
            "as reading the filing progress, which stays with the chiefs. You "
            "see your own section or division, the same as everywhere else.",
            "Your home page now leads its Alternative Work Arrangement card "
            "with today: how many are in, who is away, and a link to the full "
            "day view.",
            "It shows the schedule people filed, not attendance — the system "
            "has never recorded who actually came in. Public holidays and "
            "work suspensions aren't known to it either, so those still show "
            "as ordinary working days.",
        ],
    },
    {
        "version": "2.67",
        "date": "August 15, 2026",
        "summary": "Everywhere the system lists activities, the section that RAN "
                   "one is now what decides who sees it — your home page, the "
                   "Monitor and the invited-events page alike. The activities "
                   "card is also swipeable now, like the two beside it.",
        "changes": [
            "“Me” now shows only the activities you actually spoke at. "
            "Filling in the form for an activity no longer counts as taking part "
            "in it.",
            "An activity set up by an administrator for another section no "
            "longer appears on your team's card. What decides is the section "
            "that ran it, not who typed it in.",
            "Your team's card still includes an activity another section ran, "
            "when one of your people spoke at it — that is your team's work "
            "too.",
            "The activities card is now swipeable. Swipe (or use the arrows) for "
            "how many activities a month you have run over the past year, how "
            "they were rated, who among you spoke most, and how many people "
            "answered.",
            "The rating slide counts an activity with too few responses "
            "separately, instead of quietly grading it — and on your own "
            "card it reads your speaker rating, not the whole activity's score.",
            "Monitor and the invited-events page follow the same rule now. They "
            "used to show an administrator every activity in the bureau and "
            "everyone else only what they had typed in; both pages now show "
            "your team's activities.",
            "For an invited event there is no section of ours that ran it, so "
            "it is placed by the section of whoever was invited to speak.",
            "A seat that genuinely needs every section — whoever consolidates "
            "for the whole bureau — gets it from the “Sees” setting in "
            "Admin → Users, which is recorded and can be taken back, "
            "rather than from holding the administrator role.",
            "If your account isn't linked to a directory record yet, Monitor "
            "still shows you what you created, so nobody is locked out of "
            "their own work.",
        ],
    },
    {
        "version": "2.66",
        "date": "August 15, 2026",
        "summary": "The Alternative Work Arrangement card on your home page "
                   "now shows where the team actually is this fortnight, "
                   "instead of only counting who has filed for the next one.",
        "changes": [
            "The card led with the fortnight open for filing — so it could "
            "say “0 of 10 filed for September 1-15” and tell you nothing at "
            "all about the fortnight your team is working right now. It now "
            "opens on the current fortnight: who is on-site each weekday, "
            "what everyone is on, and the day the office empties out.",
            "Filing is still there, one line down, as the deadline it is: "
            "which fortnight, by when, and how many have filed so far.",
            "The next fortnight's charts only appear once somebody has "
            "actually filed for it. Before, three empty charts sat between "
            "you and the fortnight you were working.",
            "Everything on the card is your own section or division, exactly "
            "as before — this changes which dates it covers, not who it "
            "covers.",
        ],
    },
    {
        "version": "2.65",
        "date": "August 15, 2026",
        "summary": "The work arrangement pages now move on to the next "
                   "fortnight as soon as the current one has no working days "
                   "left, instead of showing a period nobody will work again.",
        "changes": [
            "On a Saturday the 15th, the pages were still leading with the "
            "1st-15th schedule even though the last working day of it was the "
            "Friday before. They now show the 16th-to-end-of-month schedule "
            "— the one you are about to work — from that Saturday onward.",
            "The same applies at the end of every period, and only once the "
            "working days really have run out: a Saturday with a Monday still "
            "to come in the same period keeps showing that period.",
            "Downloading ANNEX C without picking a period now gives the "
            "schedule being worked, rather than the next one open for filing "
            "— which nobody has filed for yet, so it came out blank.",
            "Filing deadlines are unchanged. Which fortnight you may file "
            "for, and until when, still follow the calendar exactly as "
            "before — this only changes which schedule a page opens on.",
        ],
    },
    {
        "version": "2.64",
        "date": "August 15, 2026",
        "summary": "Both the home page and the work arrangement page now lead "
                   "with the schedule you're actually working today, not just "
                   "the next period open for filing. Your companion is bigger "
                   "in the header, and there's a way back to your profile from "
                   "every page again.",
        "changes": [
            "The work arrangement page now opens with a “Current "
            "schedule” panel showing what's in force for today's "
            "half-month, ahead of the cards for whatever period is still open "
            "for filing. Before, the period you were actually working could "
            "only be found — unlabeled — in the history table further down "
            "the page.",
            "The Alternative Work Arrangement card on the home page leads the "
            "same way: your current in-force arrangement first, with the "
            "filing deadline mentioned only when you still have something to "
            "file.",
            "A section or division chief's team schedule page now opens on "
            "today's period by default, instead of the next one open for "
            "filing — the ‹ earlier / later › links still reach "
            "that one just as easily.",
            "Your companion is bigger in the page header — 150px on "
            "desktop, 130px on a phone — undoing a mobile sizing slip "
            "that had it capped at 84px regardless of the size requested. A "
            "“Change companion” link now sits beside it.",
            "“My profile” (avatar, pet name, photo) is reachable "
            "from every page again — from the username pill in the "
            "header and from the mobile menu — after dropping out of the "
            "visible nav when the home page was redone.",
        ],
    },
    {
        "version": "2.63",
        "date": "August 15, 2026",
        "summary": "Your home page now shows more than one reading of each card "
                   "\u2014 swipe them \u2014 and an account can be given "
                   "bureau-wide sight on purpose, so whoever consolidates ANNEX C "
                   "can see and print every section.",
        "changes": [
            "Your companion is half again as big on the home page, and so is "
            "every stage of the growth strip, so the differences between them "
            "are actually worth looking at.",
            "Hover or tab onto anyone in your team's row of pictures and their "
            "name pops up, with what they filed. No more guessing who is who.",
            "The wellness and work-arrangement cards are now swipeable. Swipe "
            "(or use the arrows) for the day and time your team actually takes "
            "breaks, what they do with them, whether the break helped, which "
            "arrangement people filed, and the weekday your office empties out.",
            "“Team filing” is now called Alternative Work Arrangement, and the "
            "card leads with the fortnight it covers — the same dates the "
            "printed ANNEX C sheet carries.",
            "Who you see on the home page, on the wellness register and on the "
            "work-arrangement schedule comes from your record in the directory "
            "— your section, your division. An administrator account with no "
            "seat on the org chart no longer sees everyone automatically; when "
            "it needs to, say so with the new “Sees” setting below.",
            "Fixed: ticking two activities you had just added and choosing "
            "“Merge” could refuse with “the selected activities are no longer in "
            "this view”, and only work if you tried again a moment later.",
            "New in Admin \u2192 Users: a \u201cSees\u201d setting beside each "
            "account's role. Leave it alone and people see their own unit, from "
            "the directory. Set it to \u201cWork arrangement, bureau-wide\u201d "
            "and they get every section's team schedule and the ANNEX C print; "
            "set it to \u201cEverything, bureau-wide\u201d and they see every "
            "section across all three modules.",
            "Alexander Medel now sees and prints the whole bureau's work "
            "arrangement. It does not open anyone's wellness claims, and it does "
            "not make him an approver \u2014 seeing a schedule and deciding on "
            "one are separate.",
            "ray@gmail.com is now an administrator who sees every section "
            "everywhere.",
            "Changing what an account can see is written to the audit log, the "
            "same as changing its role, and can be taken back at any time.",
        ],
    },
    {
        "version": "2.62",
        "date": "August 15, 2026",
        "summary": "The August 16-31 work arrangement schedule is now in the "
                   "system, copied from the sheet the bureau submitted.",
        "changes": [
            "The ANNEX C schedule for August 16-31, 2026 now shows on the team "
            "schedule page and in the workbook and PDF exports, instead of 45 "
            "blank rows. It was copied from the sheet that was already "
            "submitted and signed — the module only arrived part-way through "
            "the month, so nobody had filed for this period in the app.",
            "The two people with no arrangement but a stated reason — one "
            "awaiting an OSEC decision, one on leave — carry that reason in "
            "the Remarks column, so their blank row says why it is blank.",
            "Nothing you filed yourself was touched. If you had already filed "
            "for the second half of August, or an administrator had corrected "
            "your row, that is what still stands.",
        ],
    },
    {
        "version": "2.61",
        "date": "August 15, 2026",
        "summary": "The directory's staff search works again — including on a "
                   "phone. You can archive staff who have left. And your team "
                   "now comes from the directory, so a section head sees their "
                   "section even if they also administer the app.",
        "changes": [
            "The search box on the Directory page works on a phone again. It "
            "was correctly picking out who matched and then showing every row "
            "anyway, so it looked like nothing was happening. The same fix "
            "covers the search on Users & roles.",
            "You can now search staff by the section they are in — “Section 4” "
            "or “Equity” — not just by the short code. Each row shows the "
            "section's full name, which is what you were typing.",
            "When a search matches nobody the table says so, instead of leaving "
            "a heading over an empty space that reads like a broken box.",
            "Staff who have left the bureau can now be archived. Use Archive on "
            "their row in the Directory, with an optional note such as "
            "“Resigned 31 Jul 2026”.",
            "Archiving is not deleting. Everything they earned stays — their "
            "ratings, the reports they appear in, the certificates they signed. "
            "What changes is that they stop showing as current staff and can no "
            "longer be picked as a speaker, as who served a client, or as a "
            "certificate signatory. They also stop being offered as anyone's "
            "approver, so a resigned section head is no longer sent this week's "
            "wellness requests.",
            "Archiving someone also switches off their sign-in. Restoring them "
            "puts them back in the directory but deliberately does not hand the "
            "sign-in back — turn that on again from Admin → Users if they need "
            "it.",
            "Everyone archived is listed at the bottom of the Directory, with "
            "when and why, and a Restore button.",
            "Your team is now taken from the directory rather than from your "
            "account type. If you are a section head who also administers the "
            "app, your home page, the wellness monitoring register and the work "
            "arrangement schedule now show your section — not all five. Before, "
            "holding the administrator role quietly widened all three to the "
            "whole bureau.",
            "The Director still sees the whole bureau, and so does an "
            "administrator account with no place on the org chart, so nothing "
            "loses its bureau-wide view.",
            "Approval queues follow the same rule: you get the requests the "
            "chain of command sends you. Administrators additionally get the "
            "ones that reach nobody — someone with no section, or an unfilled "
            "chief's seat — so no request is ever left with no one to decide it.",
        ],
    },
    {
        "version": "2.60",
        "date": "August 15, 2026",
        "summary": "The system has a new name — Office Connect. Nothing moved "
                   "and nothing you saved has changed. Your companion also "
                   "answers back properly now when it has already been fed.",
        "changes": [
            "You can now see all six growth stages of your companion — the ones "
            "you've reached and the ones still ahead, with the points each one "
            "needs — plus a plain list of what earns those points. It's on your "
            "home page and on your profile.",
            "Your home page now shows how your team is doing instead of just "
            "asking where you want to go: who has filed their wellness break "
            "and their work arrangement this period, and the recent activities "
            "your section ran, with their ratings. Tap “Me” to see just your "
            "own. The three buttons you used before are still there, "
            "underneath.",
            "The menu is now four groups — Wellness, CSS, AWA and "
            "Administrator — instead of seven. Wellness comes first because it "
            "is the page staff open most.",
            "Six pages that already existed but were in no menu at all are now "
            "listed: applying for a break, wellness team monitoring and "
            "approvals, and filing, team schedule and approvals for your work "
            "arrangement. If you were reaching these by bookmark, they now have "
            "a home.",
            "The CSS menu groups its pages under small headings — See how "
            "we're doing, Official reports, Run a survey, Data entry — so a "
            "long list is easier to scan.",
            "On the wellness page, the whole “This week — 0 of 2 hours "
            "claimed” box now takes you to the request form. Before, only the "
            "small button did, so clicking the words themselves did nothing.",
            "When you have already claimed every hour available, that button is "
            "now properly switched off instead of still opening the form when "
            "reached by keyboard.",
            "Your companion now always says something when you water or feed "
            "it. If you had already cared for it recently it says so — before, "
            "it went quiet, which made the button look broken when it had "
            "actually worked. This was far and away the thing people were most "
            "often clicking over and over.",
            "CSS-IS is now called Office Connect. The old name described only "
            "the client satisfaction survey, but the system now also carries "
            "your wellness break and your work arrangement, so it needed a name "
            "that covers all three.",
            "You will see the new name on the sign-in screen, at the top of "
            "every page, on the app icon if you installed it to your phone, and "
            "in account emails.",
            "The Client Satisfaction Survey itself keeps its name, and so does "
            "everything inside it — the same reports, the same scores, the same "
            "links. Every page you have bookmarked still works.",
        ],
    },
    {
        "version": "2.59",
        "date": "August 15, 2026",
        "summary": "You can now say you have no work arrangement, and why — for "
                   "leave, or while waiting on a decision from outside the "
                   "bureau. It stays until you remove it.",
        "changes": [
            "Some people have no alternative work arrangement in a period and a "
            "reason for it: on leave, or waiting on an approval from OSEC. On "
            "the old spreadsheet those rows were simply blank, which looked "
            "exactly like a row nobody had got round to filling in.",
            "Mark yourself “No AWA” with a short reason and it prints on "
            "ANNEX C as No AWA with that reason beside it — so your row says "
            "something, and a blank row now means only one thing: nobody has "
            "filed yet.",
            "It needs no approval and takes effect immediately, so unlike a work "
            "arrangement it is not tied to the Friday deadline. If something "
            "comes up in the middle of a period, you can record it that day.",
            "It carries into each new period on its own, reason and all, until "
            "you or an admin removes it — there is nothing to re-file every "
            "fortnight.",
            "Changing the reason later does not rewrite the past: a period whose "
            "annex has already gone out keeps the wording it was submitted with.",
            "An admin can record it for someone who is not signing in — useful "
            "for a long leave — and every such action names who did it and for "
            "whom in the audit trail.",
            "People marked No AWA drop out of the on-site counts entirely rather "
            "than being counted as present. Someone on leave was never going to "
            "be at a desk on Friday, so leaving them in made the coverage figures "
            "read better than they were.",
            "While you are marked No AWA, filing a work arrangement asks you to "
            "remove the mark first, rather than quietly deleting the reason you "
            "gave.",
        ],
    },
    {
        "version": "2.58",
        "date": "August 14, 2026",
        "summary": "New Work Arrangement module: file your ANNEX C schedule "
                   "for each half of the month, ask to change it, and let the "
                   "system produce the annex the bureau submits.",
        "changes": [
            "There is now a third door after you sign in, beside Wellness and "
            "CSS: Work arrangement. Tell the system whether you are on a "
            "regular 5-day on-site week (REG), a compressed workweek with a day "
            "off (CWW), or working from home one day (WFH) — and which day.",
            "You file once per half-month period, the same 1st-to-15th and "
            "16th-to-end-of-month halves as the paper form. Your section chief "
            "approves it; if you are a section chief, your division chief does.",
            "Filing closes on the Friday before a period begins, so the "
            "schedule is settled before the period starts. The page always "
            "tells you the exact deadline and how many days are left, and if "
            "you miss one it tells you which period you can still file for.",
            "Already approved and something changed? Ask for a change. Only you "
            "can start one — nobody can rewrite your schedule for you — and the "
            "arrangement you already have stays in force until your approver "
            "decides, so a denied change simply leaves things as they were.",
            "While you pick your day you will see how many people in your "
            "section are already off then, for example \"4 of 6 others in your "
            "section are already off on Friday. Filing this leaves 1 on-site.\" "
            "It is there to inform you, never to stop you.",
            "Your section chief sees the same picture on the approvals queue, "
            "flagged when approving would leave nobody on-site that day. The "
            "decision is still theirs to make.",
            "Chiefs and admins get a schedule page for each period: who has "
            "filed, who has not yet, and how many people are on-site each "
            "weekday. Anyone who has not filed shows up by name, so they can be "
            "chased before the deadline instead of appearing as a blank row "
            "afterwards.",
            "ANNEX C itself now comes out of the system — as an Excel file (a "
            "sheet per half-month, or the whole month in one file) and as a "
            "print-ready PDF, with the legend and the Prepared by / Approved by "
            "block already filled in from the directory.",
        ],
    },
    {
        "version": "2.57",
        "date": "August 11, 2026",
        "summary": "The activity Excel download (MRR format) now reads differently "
                   "for every activity, and its comments lead with what people "
                   "actually wrote.",
        "changes": [
            "In the activity list download, the \"Action / Improvement Plan\", "
            "\"Next Steps and Timeline\" and \"Resources Needed\" columns used to "
            "repeat the same few sentences down the whole sheet — Next Steps was "
            "the same paragraph on every single row. Each activity now gets its "
            "own: the plan names the dimension that actually scored lowest and "
            "matches how hard it fell, the timeline is pinned to that activity's "
            "real date and names the activity, and the resources match whether it "
            "was run face-to-face or online and how many people attended.",
            "The draft now reads all five service-quality dimensions instead of "
            "three, so \"Knowledgeable organizers\" and \"Clear & reassuring\" can "
            "be named as the area to work on — before, every activity in the "
            "bureau had to pick from the same three.",
            "An activity that did well is no longer told to fix something. It gets "
            "a \"no area needs correcting\" note and a line on keeping the standard.",
            "In the COMMENTS box of each row, the words people TYPED now come "
            "first — including the notes they wrote under a specific question, "
            "which the download used to leave out entirely.",
            "The tap-to-add feedback options (\"Knowledgeable\", \"Engaging\", and "
            "so on) no longer crowd out real comments. They only fill the space "
            "left over when an activity has few written comments, they are clearly "
            "marked as a picked option with the number of people who chose it, and "
            "the sheet spreads them out so the same option doesn't appear on every "
            "activity.",
            "An activity with nothing written now says so, instead of showing an "
            "empty \"COMMENTS:\" heading.",
            "The MRR draft shown on an activity's own page now matches the "
            "download exactly — it was quietly drafting from less information.",
        ],
    },
    {
        "version": "2.56",
        "date": "August 11, 2026",
        "summary": "Activity feedback forms now ask about the activity instead of "
                   "reading as though they were asking about a person, and the "
                   "dashboard now names each score after what it really measures.",
        "changes": [
            "On an activity's feedback form, the questions used to be written "
            "about a person with the activity's name dropped in — so a "
            "respondent read \"15th Learning Exchange Session was responsive "
            "and willing to address questions and needs\". The activity form "
            "now has its own wording: \"The organizers were responsive and "
            "willing to address questions and needs\", \"The activity kept to "
            "the schedule and program\", and so on.",
            "The activity's title no longer repeats inside all eleven "
            "questions — it stays in the form's heading, where it already was.",
            "Resource-person forms are unchanged. The one exception: a "
            "resource-person form with no name recorded yet used to borrow the "
            "activity's title; it now simply says \"the resource person\" "
            "(\"tagapagsalita\" on a Filipino form).",
            "Every question still means exactly what it meant before, so "
            "scores, reports and past results are unaffected and remain "
            "directly comparable.",
            "On the dashboard, several score names described questions the "
            "forms do not ask — a speaker's \"Materials & venue\" score was "
            "labelled \"Neat & well-presented\", and an activity's score for "
            "knowledgeable organizers was labelled \"Courteous organizers\". "
            "Each score is now named after the questions it is actually "
            "averaging. Only the names changed; every number is the same.",
            "One activity score, \"Attention & set-up\", now says so plainly: "
            "it averages a question about attention to participants together "
            "with one about materials and the venue. It always did — the old "
            "name mentioned only the venue.",
            "The Filipino version of the new activity wording is a draft, "
            "pending the office's review like the rest of the translation.",
        ],
    },
    {
        "version": "2.55",
        "date": "July 30, 2026",
        "summary": "Fixed an activity's response count sometimes including "
                   "unrelated resource-person reviews from the same date.",
        "changes": [
            "On the Activities page, an activity's shown response count could "
            "include responses to a completely different resource person's "
            "review — if that review happened to be logged under the same date "
            "and section, with no venue set, it silently added its responses "
            "to the activity's own count without changing the score shown "
            "beside it. The count now reflects only the activity's own "
            "responses.",
            "This only affected the number shown next to an activity's score "
            "on cards and its own report page — the score itself, and every "
            "official report, were never affected (they already counted "
            "correctly).",
        ],
    },
    {
        "version": "2.54",
        "date": "July 30, 2026",
        "summary": "Admins can now fix just an activity's date without merging it "
                   "into anything else.",
        "changes": [
            "On the Activities page's ✎ Edit / merge bar, admins now have a "
            "“Just fix the date →” button next to “Merge into one”. Tick one "
            "or more activities, set the date, and it corrects just that — no "
            "combining, no title change.",
            "Before this, correcting a wrong date required merging the activity "
            "into a second one even when there was nothing to actually merge.",
        ],
    },
    {
        "version": "2.53",
        "date": "July 30, 2026",
        "summary": "Admins can now fix or archive an individual walk-in (Type 1 "
                   "ARTA) response, not just whole activities.",
        "changes": [
            "New \"Manage entries\" page (linked from the Walk-in QR page) lists "
            "every walk-in/online client response one by one, newest first.",
            "An admin can edit a single response in full — the submission date, "
            "who served the client, the CO-CSM respondent details, the Citizen's "
            "Charter answers, and every SQD rating and comment.",
            "An admin can also archive a bad, duplicate, or test response — it "
            "drops out of every report and count immediately, and can be "
            "restored later. This is admin-only; it doesn't change what other "
            "roles can do.",
        ],
    },
    {
        "version": "2.52",
        "date": "July 30, 2026",
        "summary": "Admins can now merge activities that were accidentally logged "
                   "under two different dates into one — the Activities page's "
                   "existing merge only ever combined the names.",
        "changes": [
            "On the Activities page's ✎ Edit / merge bar, administrators now see a "
            "new “Merge (any date)” action alongside the existing “Rename / "
            "merge”. Tick the duplicate activities, type one shared title and the "
            "corrected date, and it actually combines their responses into a "
            "single activity dated what you entered — fixing the case where the "
            "same real event was typed in twice under two different dates.",
            "The regular “Rename / merge” only ever gave activities a matching "
            "name — it could never combine them if their dates didn't already "
            "match, since the Activities page always lists a same-dated event as "
            "one card. “Merge (any date)” is the one action that can cross that "
            "gap.",
            "Because this can fold two events' responses together, it's admin-"
            "only, and it double-checks with you first: if the ticked activities "
            "don't already share a date, it names the exact dates involved and "
            "asks you to confirm before doing anything.",
        ],
    },
    {
        "version": "2.51",
        "date": "July 30, 2026",
        "summary": "The Director is no longer individually tracked in CSS "
                   "rankings and reports — a standing rule, not a one-time fix, "
                   "so it applies to whoever holds the role.",
        "changes": [
            "Whoever currently holds the Director position is left out of the "
            "People rankings, their own scored profile page, the “resource "
            "person to watch” insight, and the per-activity roster "
            "PowerPoint. This is detected from their position/title, not a "
            "manual per-person setting, so it keeps applying automatically "
            "when the Director changes — nothing to remember to re-flag.",
            "Their survey responses still count toward every bureau-wide "
            "average as before; only the individually-named rankings/reports "
            "changed.",
        ],
    },
    {
        "version": "2.50",
        "date": "July 30, 2026",
        "summary": "Fixed the resource-person roster PowerPoint listing the same "
                   "person more than once on an activity that had several sessions.",
        "changes": [
            "When a resource person ran more than one session within the same "
            "activity (e.g. several batches of the same training on the same "
            "date and venue), the PowerPoint roster listed them once per session "
            "with different scores, instead of once for the activity. They now "
            "appear once, with their Overall Service Quality and SERVQUAL Score "
            "combined across all their sessions in that activity.",
        ],
    },
    {
        "version": "2.49",
        "date": "July 29, 2026",
        "summary": "The Resource-person report can now download a PowerPoint roster, "
                   "one slide per activity, filterable by quarter.",
        "changes": [
            "The Type 3 (Resource Person) report has a new \"PowerPoint — "
            "per-activity roster (Form 3.0)\" download. It builds a slide for each "
            "activity in the selected scope, listing every resource person who "
            "spoke at it with their Overall Service Quality rating and SERVQUAL "
            "score — matching the paper Form 3.0 roster sheet.",
            "The download honors the report page's existing quarter (and Activity) "
            "filter, so choosing a quarter and downloading gives a deck with just "
            "that quarter's activities.",
        ],
    },
    {
        "version": "2.48",
        "date": "July 27, 2026",
        "summary": "Fixed the wellness \"Request a break\" button locking up once "
                   "your current week's 2 hours were used, even if you meant to "
                   "request a future week.",
        "changes": [
            "Using up this week's 2-hour wellness entitlement no longer disables "
            "the \"Request a break\" button on your wellness page. You could always "
            "file a request for any open week up to four weeks ahead — the button "
            "just wasn't letting you get to the form. It now only locks once every "
            "week in that four-week window is fully claimed.",
        ],
    },
    {
        "version": "2.47",
        "date": "July 24, 2026",
        "summary": "The 0–100 quality index is now the headline score everywhere — "
                   "on cards, profiles, and the score-over-time and year-on-year charts.",
        "changes": [
            "A resource person's and a unit's main score is now the combined quality "
            "index (0–100) — the same all-questions measure the ranking uses — instead "
            "of the detailed 1–7 average. The 1–7 detailed rating and the 1–4 overall "
            "question are still shown beneath it as the two parts that make it up.",
            "The \"scores over time\" and \"year on year\" charts (on screen and in the "
            "PDF, PowerPoint and Excel downloads) now plot the quality index, so the "
            "trend you see matches the headline number.",
            "The people and teams lists, and the \"how you compare to the average\" "
            "read, all use the quality index too, so every quality number on the site "
            "is now on the same 0–100 scale. Walk-in service scores keep their own "
            "0–100 top-box percentage as before.",
        ],
    },
    {
        "version": "2.46",
        "date": "July 24, 2026",
        "summary": "Rating quality now counts every satisfaction question (including "
                   "the \"overall quality\" one), and Engagement now counts both "
                   "activities run and people reached.",
        "changes": [
            "\"Rating quality\" is now a single 0–100 index built from ALL the "
            "satisfaction questions on a person's or unit's surveys — the nine "
            "detailed questions (rated 1–7) and the one \"overall, how would you "
            "rate the quality?\" question (rated 1–4), which was previously left "
            "out. Every question counts equally, and the only one still excluded is "
            "the first — what people expected going in — because that's a starting "
            "point, not a rating. The familiar detailed score (x.xx/7) and the "
            "overall-quality score (x.xx/4) are shown as the two parts of the index.",
            "\"Engagement\" now rewards two things equally: how many activities or "
            "sessions were run, AND how many people rated them. Before, only the "
            "number of activities counted — so a unit that reached far more people "
            "now gets credit for that reach.",
            "The \"How is this computed?\" note on each person and unit page has been "
            "updated to explain both changes in plain language.",
        ],
    },
    {
        "version": "2.45",
        "date": "July 24, 2026",
        "summary": "\"Rating quality\" now ranks on the average rating you actually "
                   "see, and a new \"How is this computed?\" note explains every rank.",
        "changes": [
            "On a person's or a unit's page, the \"Rating quality\" rank is now based "
            "on the average rating shown — nothing hidden. The score is shown to three "
            "decimals, so two people or units that both looked like \"6.4\" are ranked "
            "by the finer difference (for example 6.417 vs 6.392) instead of appearing "
            "tied. Higher average, better rank.",
            "How many ratings or activities you have no longer changes your quality "
            "rank — that now counts only under Engagement, so it is never counted "
            "twice. The one safeguard: with fewer than ten ratings the sample is too "
            "thin to trust, so it is ranked below everyone with a full sample rather "
            "than topping the list on a lucky handful.",
            "A new \"How is this computed?\" drop-down on both the person and the unit "
            "comparison explains, in plain words, how each rank is worked out.",
        ],
    },
    {
        "version": "2.44",
        "date": "July 23, 2026",
        "summary": "Fixed a \"page not found\" error when opening the results of a "
                   "big event that was run as several sessions on the same day.",
        "changes": [
            "When an activity is set up as several sessions on the same day, at the "
            "same venue, run by the same office (for example a summit with a morning "
            "plenary and an afternoon workshop), closing a session and clicking "
            "\"View the report\" now opens its satisfaction results instead of "
            "showing a \"page not found\" error. The results were always saved — "
            "only the link to them was broken.",
            "Those sessions are shown together as one activity's results, matching "
            "how the event already appears in your Activities list and on the home "
            "page.",
        ],
    },
    {
        "version": "2.43",
        "date": "July 21, 2026",
        "summary": "My profile now lets everyone set a photo and their own "
                   "designation, and saving takes you back to the home page.",
        "changes": [
            "Everyone can now set a profile photo from My profile — before, only "
            "accounts tied to a staff-directory entry could. Your photo shows "
            "beside your name and greeting.",
            "My profile has a new Designation box you can fill in and update any "
            "time (for example \"Section Head\"). For staff listed in the "
            "directory it updates the directory entry too, so the two always "
            "match (the designation used on certificates).",
            "Saving your profile now returns you to the home page with a "
            "\"Profile saved\" note. (This replaces the recent change that sent "
            "you to the wellness break page — the profile now saves your photo "
            "and designation too, so it returns you home.)",
        ],
    },
    {
        "version": "2.42",
        "date": "July 21, 2026",
        "summary": "On the wellness utilization dashboard, the \"By person\" list "
                   "now shows only the people a chief actually oversees — their own "
                   "section — instead of everyone in the bureau.",
        "changes": [
            "When a section or division chief opens the wellness utilization "
            "dashboard, the \"By person\" table (and the section summary, the "
            "week totals and the pending-requests list) now covers only their own "
            "area: a section chief sees just their section, a division chief sees "
            "every section under them. Administrators still see the whole bureau, "
            "exactly as before.",
        ],
    },
    {
        "version": "2.41",
        "date": "July 21, 2026",
        "summary": "After you rename or change your companion on your profile, "
                   "saving now takes you straight to the wellness break page so you "
                   "can see your updated companion right where it grows.",
        "changes": [
            "When you rename your companion or pick a different one on \"My "
            "profile\" and press Save, you now land on the wellness break page — "
            "where your companion lives and grows — instead of staying on the "
            "profile form. Your changes are saved exactly as before.",
        ],
    },
    {
        "version": "2.40",
        "date": "July 21, 2026",
        "summary": "The wellness utilization dashboard's register download is now "
                   "an Excel file in the official Annex A format, covering only the "
                   "breaks people actually took — with a date-range filter.",
        "changes": [
            "On the wellness utilization dashboard, \"Download the register\" now "
            "gives an Excel workbook laid out as the official \"Annex A. Weekly "
            "Wellness Break Log\" (Name, Date/Time, Activity Type, Duration, "
            "Usefulness Rating and Remarks) instead of the old plain CSV.",
            "The register lists only breaks that were actually consumed "
            "(completed); pending, approved-but-not-taken, denied and cancelled "
            "requests are left off.",
            "A From/To date filter scopes the download to any span — it defaults "
            "to the week you're viewing, and clearing both dates exports the "
            "whole register.",
        ],
    },
    {
        "version": "2.39",
        "date": "July 21, 2026",
        "summary": "You can now download a monthly PDF of your own wellness "
                   "breaks — one file per month, laid out like the paper "
                   "monitoring form, with approvals shown as \"Digitally "
                   "approved and signed\".",
        "changes": [
            "Your wellness page now has a \"Monthly register (PDF)\" download. "
            "Pick a month and get a print-ready copy of the breaks you availed "
            "that month, set out like the official Monday-to-Friday monitoring "
            "form with a \"Name\" and \"Office\" header.",
            "In the approver box of each week, instead of a blank line to sign, "
            "the register reads \"Digitally approved and signed\" over the name "
            "of whoever approved it — because the approval already happened "
            "inside the system.",
            "The download only appears for months where you actually took a "
            "break, and only lists breaks that were approved or completed "
            "(withdrawn or denied ones don't show). It's your own record: "
            "everyone downloads only their own, no special role needed.",
        ],
    },
    {
        "version": "2.38",
        "date": "July 21, 2026",
        "summary": "Your wellness companion feels alive: it wanders on its own, "
                   "talks to you, can be petted — and watering plants finally "
                   "shows the water.",
        "changes": [
            "Fixed: watering a plant never showed the falling droplets (they "
            "were drawn but kept invisible by a styling slip), and the "
            "succulent showed no reaction at all. Every plant now visibly "
            "drinks — the succulent gives a satisfied little plump.",
            "Ground companions (dog, cat, rabbit, bird, turtle) now wander "
            "around their wellness-hub play area on their own — the dog trots "
            "and does the occasional zoomies, the cat strolls and sits, the "
            "rabbit hops, the turtle plods.",
            "Fish and dolphin get a 🌊 button: let them out and they swim "
            "around the whole wellness page (never blocking your clicks). Tap "
            "the swimmer or the button to call them home; the choice is "
            "remembered.",
            "Your companion now talks to you: it greets you by name and time "
            "of day, thanks you after care, remembers being neglected (\"I "
            "missed you…\"), and celebrates care streaks.",
            "Dogs, cats and birds watch your mouse move (the dog gets excited "
            "if you zip past), and pressing-and-holding your companion pets it "
            "— little hearts float up, with an optional soft purr if sounds "
            "are on.",
            "As always, every new motion respects your reduced-motion setting.",
        ],
    },
    {
        "version": "2.37",
        "date": "July 21, 2026",
        "summary": "A new dolphin joins the companion line-up, and the fish's "
                   "water no longer slides around while it swims.",
        "changes": [
            "You can now adopt a dolphin as your wellness companion — it swims "
            "and leaps around its pool, blinks, blows bubbles, and is fed like "
            "the other animals. Pick it on your profile page (/me) alongside the "
            "other species.",
            "Fixed a glitch where the fish's little pool of water drifted across "
            "the card as the fish swam — the water now stays put while the fish "
            "(and the new dolphin) glide around it.",
        ],
    },
    {
        "version": "2.36",
        "date": "July 21, 2026",
        "summary": "Filing a wellness break is clearer: it names the exact person "
                   "who'll approve it, lets you plan up to four weeks ahead, and "
                   "asks a few more questions when you check in afterwards.",
        "changes": [
            "The request screen now shows the actual name of who it goes to (for "
            "example, \"Send for approval of Ray Justin Ventura\") instead of the "
            "generic \"section chief\" — so you know exactly who's deciding.",
            "Picking \"Others\" for your activity now asks you to say what it is, "
            "so the request and the records are never left vague.",
            "You can now schedule a break for any workday in the next four weeks, "
            "not just the current week. Each week still has its own 2-hour limit, "
            "and the \"hours left\" note updates to match the date you pick.",
            "The after-break check-in now also asks how useful the break was (1–5), "
            "whether it helped you feel refreshed and manage stress, how it affected "
            "your focus, and leaves room for suggestions — matching the DOH "
            "post-activity report. Chiefs' register export gains a Usefulness column.",
            "A small tuning to the \"Maximize AI\" assistant: grounded answers built "
            "purely from your own numbers are now shown at a slightly more relaxed "
            "confidence level, so more valid answers surface — it still never shows "
            "an answer that isn't backed by your data.",
        ],
    },
    {
        "version": "2.35",
        "date": "July 21, 2026",
        "summary": "New \"Maximize AI\" option lets the assistant answer more of "
                   "your questions straight from your own survey numbers — with a "
                   "one-click admin switch to turn it on or keep the safe basics.",
        "changes": [
            "The assistant's Q&A used to only recognise a short list of fixed "
            "questions (like \"how many responses this month\"). That list is now "
            "longer, and there's a new \"Maximize AI\" mode that lets it answer "
            "free-form questions — comparisons, which activity scored highest, how "
            "a resource person is rated — using only your own aggregate numbers.",
            "Admins choose the behaviour on the AI console (/admin/ai): "
            "\"Canned catalog\" (the safe, fixed stats — still the default) or "
            "\"Maximize AI\" (compose from your data). It has its own daily budget "
            "cap, and if anything goes wrong it quietly falls back to the fixed "
            "stats — you never see an error and it never makes a number up.",
            "The assistant is told to answer only from the numbers it's given and "
            "to say when it doesn't have the data. It never sees attendee names or "
            "emails. Resource-person names are included only if an admin ticks the "
            "extra opt-in box, the same care taken elsewhere for staff names.",
            "The most common questions (\"how many responses this year\", \"how "
            "are we doing\", \"how many trainings this month\") are now answered "
            "instantly from a built-in list — no AI needed — so they stay fast, "
            "cost nothing, and keep working even when AI is switched off.",
        ],
    },
    {
        "version": "2.34",
        "date": "July 21, 2026",
        "summary": "On an activity's report, you can now correct the wording of "
                   "the comments people left — handy for tidying up encoding.",
        "changes": [
            "The “In people's own words” section of an activity report now has an "
            "“Edit the words (for encoding)” panel for section heads and admins, "
            "listing every comment on that activity with a box to fix a "
            "misspelling or hard-to-read text.",
            "Only the words are ever editable — never the ratings — and each "
            "correction is recorded in the audit log, so it's safe for cleaning up "
            "typed-in responses.",
        ],
    },
    {
        "version": "2.33",
        "date": "July 21, 2026",
        "summary": "Wellness break requests now correctly name who they go to — "
                   "your section chief, division chief, or the Director — instead "
                   "of defaulting to “an administrator.”",
        "changes": [
            "The break request form now shows the right approver for your place in "
            "the office: staff see “your section chief,” a section head sees "
            "“your division chief,” and a division chief sees “the Director.”",
            "It names that approver as long as the role is filled in the staff "
            "directory, even before that person has signed in for the first time — "
            "so section heads no longer see the request going to “an administrator.”",
            "The Director is now recognised from their official title, so requests "
            "from a division chief route to the Director as intended.",
        ],
    },
    {
        "version": "2.32",
        "date": "July 21, 2026",
        "summary": "Fixed the AI helpers quietly falling back to their non-AI "
                   "answers after the switch to Google's newer Gemini model.",
        "changes": [
            "Google's newer AI models silently spend part of each reply on "
            "hidden \"thinking\", which was crowding out the actual answer and "
            "making the AI search bar and other AI features drop back to their "
            "non-AI behaviour. The system now keeps that thinking to a minimum "
            "and leaves room for the real answer, so the AI features work again.",
        ],
    },
    {
        "version": "2.31",
        "date": "July 21, 2026",
        "summary": "You can now take your whole 2-hour wellness break in one "
                   "sitting, instead of only one hour at a time.",
        "changes": [
            "The wellness break request form now lets you choose a 1-hour or a "
            "2-hour break, so you can take both of your weekly hours at once if "
            "you'd rather.",
            "The 2-hour option is offered only when you still have both hours "
            "left for the week; once an hour is used, you can add just the one "
            "that's left.",
        ],
    },
    {
        "version": "2.30",
        "date": "July 21, 2026",
        "summary": "Wellness breaks now need a little lead time — file them at "
                   "least 30 minutes ahead so your approver can act.",
        "changes": [
            "When you request a wellness break, it now has to start at least 30 "
            "minutes from the time you file it, so the person approving it has a "
            "real chance to see it first.",
            "This also gently stops a break from being booked for a time that has "
            "already gone by earlier today.",
        ],
    },
    {
        "version": "2.29",
        "date": "July 21, 2026",
        "summary": "Companions now sleep at night, dress for the season, and reward "
                   "devoted caretakers with a badge — plus optional gentle sounds.",
        "changes": [
            "Companions doze off between 9 pm and 6 am on your device — eyes closed, "
            "little Zzz floating up. A tap gently wakes them for a moment. The bat, "
            "being nocturnal, stays wide awake at night.",
            "Every companion wears a small seasonal accessory that changes each month — "
            "a santa hat in December, hearts in February, a rain hat for June — and "
            "potted plants get a matching ribbon on their pot.",
            "Care for your companion seven days in a row and you earn the new "
            "“Devoted caretaker” badge (just for fun — points still come only from "
            "wellness breaks).",
            "A new sound button next to Water/Feed adds soft chirps and plips when you "
            "play with your companion — it's off unless you turn it on, and your choice "
            "is remembered.",
        ],
    },
    {
        "version": "2.28",
        "date": "July 21, 2026",
        "summary": "Your companion comes alive: nine new pets to adopt, prettier "
                   "artwork, and you can now water your plant or feed your animal.",
        "changes": [
            "Nine new companions joined the family: sunflower, fern, mushroom and "
            "succulent on the plant side; dog, rabbit, fish, owl and bat on the animal side.",
            "Every companion got a glow-up — richer colors, expressive eyes, and its own "
            "personality: the dog wags and jumps, the rabbit peeks shyly, the owl watches "
            "your cursor, the bat flutters around, and the succulent... stays wonderfully chill.",
            "You can now care for your pet on the Wellness page: water a plant or feed an "
            "animal and watch it react — a cared-for companion looks happy, a neglected one droops.",
            "Caring is just for fun: your companion still grows only from your wellness "
            "break points, exactly as before.",
            "You can pick up your companion and move it around its home on the Wellness page.",
            "All the new movement respects your device's reduced-motion setting.",
        ],
    },
    {
        "version": "2.27",
        "date": "July 21, 2026",
        "summary": "Small fixes: the wellness break form's picture cards no longer overlap "
                   "text, there's a new “Others” option, and a duplicate set of cards on the "
                   "CSS page is gone.",
        "changes": [
            "Fixed the wellness break request form so an activity's picture and label no "
            "longer overlap the note field below it.",
            "Added an “Others” option to the wellness break activity picker for requests "
            "that don't fit the other categories.",
            "Removed a duplicate set of “CSS” and “Wellness” cards that was showing again "
            "after you'd already picked one and reached the CSS page.",
        ],
    },
    {
        "version": "2.26",
        "date": "July 21, 2026",
        "summary": "A friendlier welcome: the first time you sign in you set up your "
                   "profile and adopt a named companion, then choose where to go from a "
                   "simple home page.",
        "changes": [
            "The first time you sign in after this update, a quick welcome screen lets you "
            "add a profile photo and adopt a companion — a plant or an animal — and give it a name.",
            "Signing in now opens a simple “what would you like to do?” page with two "
            "cards: Wellness and CSS.",
            "Your companion is the same little friend that grows on the Wellness page as you "
            "take your breaks; you can rename it or pick a different one any time from “My profile”.",
            "View-only accounts open straight to their own results page, with their section "
            "one tap away.",
            "The wellness break form now uses friendly pictures to choose your activity.",
            "Wellness break requests follow the chain of command: a section chief's own "
            "request goes to their division chief, and a division chief's to the Director.",
        ],
    },
    {
        "version": "2.25",
        "date": "July 20, 2026",
        "summary": "New Wellness module: request your 2-hour weekly wellness break, have "
                   "your section chief approve it, and grow a little companion plant as "
                   "you take care of yourself.",
        "changes": [
            "After signing in you now choose between CSS (surveys & reports) and Wellness "
            "— the new Wellness card on the home page and the Wellness menu both lead there.",
            "Everyone gets 2 hours of wellness break per week (DM 2025-0135), requested "
            "one hour at a time. The app won't let a week go over 2 hours, and denied or "
            "withdrawn requests give the hour back.",
            "Your section chief approves or denies requests from their own section; "
            "administrators handle everyone else (and the chiefs' own requests).",
            "After a break you answer a 2-minute check-in — how you felt before and after, "
            "and what you did. That completes the break, earns points and badges, and "
            "grows your companion plant through six stages.",
            "Chiefs and administrators get a Wellness utilization dashboard (per section "
            "and per person, week by week) and a downloadable register (CSV) for the "
            "monitoring report.",
        ],
    },
    {
        "version": "2.24",
        "date": "July 20, 2026",
        "summary": "The \"you already made this activity\" warning on the New survey screen "
                   "now catches duplicates made by a different staff member too, not just "
                   "your own.",
        "changes": [
            "Previously the duplicate warning only fired if the SAME signed-in account had "
            "created a matching activity within the last 6 hours. A real case showed the "
            "common duplicate isn't that — it's two different staff members entering the "
            "same activity, or someone re-entering it a day or more later. The warning now "
            "checks by activity name + date alone, no matter who created the earlier one or "
            "how long ago.",
            "Still just a heads-up: it never blocks Save. If it really is a second, separate "
            "activity with the same name, you can carry on as before.",
        ],
    },
    {
        "version": "2.23",
        "date": "July 19, 2026",
        "summary": "Fixed a start-up crash that could take the whole site offline after the "
                   "previous release, caused by one of the new instant-answer files being "
                   "left out of the upload.",
        "changes": [
            "The file that powers the new instant question-and-answer replies (added last "
            "release) was not being included when the site is published, so the app could "
            "fail to start and show a server error for everyone — it is now uploaded with "
            "every deploy.",
        ],
    },
    {
        "version": "2.22",
        "date": "July 19, 2026",
        "summary": "The AI search bar can now answer common questions instantly on its own, "
                   "without spending an AI request — and it learns which questions to add "
                   "from what people actually ask.",
        "changes": [
            "Frequently-asked questions (like \"open the dashboard\" or \"how many responses "
            "this month\") are now answered by a saved list of question-and-answer rules "
            "instead of the AI — so they come back instantly, keep working even when the AI "
            "is turned off or has hit its daily limit, and don't use up any AI requests.",
            "A starter set of these rules ships built-in, so the most common questions are "
            "already covered from day one.",
            "New Admin → Learned rules page: see how many questions were answered for free, "
            "review the questions people actually asked (ranked by how often), and promote "
            "any of them into a rule in one click — or add and edit rules by hand.",
            "Every saved question is still shown its usual answer (a page, a quick statistic, "
            "or a help tip) and can only ever point somewhere the person is already allowed "
            "to go — the same safety checks the AI answers already use.",
        ],
    },
    {
        "version": "2.21",
        "date": "July 19, 2026",
        "summary": "Fixed Admin → AI crashing with a server error right after the previous "
                   "release, on any server where the main AI (Google) has no access key set "
                   "up but the backup AI (Groq) does.",
        "changes": [
            "The previous release's new \"is any AI available\" check was written to run "
            "after the page had already finished reading from the database, and only hit "
            "that mistake in the one specific setup this app happens to be running in — "
            "main AI unset, backup AI set up — which is exactly why it slipped through "
            "testing and only showed up on the live server. Admin → AI opens normally "
            "again in every setup.",
            "No other page or feature was affected — this was isolated to the Admin → AI "
            "page itself.",
        ],
    },
    {
        "version": "2.20",
        "date": "July 19, 2026",
        "summary": "The backup AI helper (Groq) can now stand in as the only AI provider, "
                   "not just a top-up, if the main AI (Google) has no access key set up at "
                   "all — still off unless an administrator turns it on.",
        "changes": [
            "Previously, Groq only ever helped out for a moment when the main AI (Google) "
            "ran out of its free daily quota — if Google's access key wasn't set up on the "
            "server at all, every AI feature went straight to its ordinary non-AI behavior, "
            "even with Groq's own key ready and the backup switched on. Groq can now run the "
            "AI features entirely on its own in that situation.",
            "Nothing changes about the on/off switches: an administrator still has to turn "
            "on \"Fallback\" at Admin → AI and set up Groq's own access key on the server "
            "for this to do anything, and the directory-harmonizing feature still never uses "
            "Groq, exactly as before.",
            "The AI mode switch (off / router / answers / assistant) and each feature's own "
            "on/off flag still work exactly the same and still turn AI off entirely, for "
            "either service, when set that way — this only changes what happens when Google's "
            "key specifically is the thing that's missing.",
            "The two real causes behind the past \"error 500\" incidents (the AI calls "
            "briefly freezing the app, and a stray blank line in a pasted access key) were "
            "already fixed in code both services share, so this change doesn't bring either "
            "one back.",
        ],
    },
    {
        "version": "2.19",
        "date": "July 19, 2026",
        "summary": "Fixed the real cause of the recurring \"error 500\" pages: the "
                   "smart-assistant (AI) features could briefly freeze the whole app "
                   "while waiting on the AI service, which made every other person's "
                   "click fail. Those AI calls now run out of the way, so the app "
                   "stays responsive for everyone.",
        "changes": [
            "The recurring \"error 500\" was traced to the AI features, not to the "
            "hosting platform. The app runs as a single worker, and each AI request "
            "(most often the smart search/assistant bar) was made in a way that "
            "paused everything else the app was doing until the AI service replied — "
            "up to about 15 seconds if the AI service was slow. During that pause the "
            "app could not answer anyone else, so the hosting platform returned an "
            "\"error 500\" to every other person mid-click. This is why the earlier "
            "automatic-retry helper reduced but never removed the problem.",
            "AI requests now run off to the side (on their own worker thread), so the "
            "rest of the app keeps responding normally while an AI reply is awaited. "
            "One slow or stuck AI call can no longer take the whole app down for "
            "everyone else.",
            "Sign-in got the same treatment: checking a password is deliberately slow "
            "(for security), and doing it in-line briefly froze the app — noticeable "
            "when automated bots hammer the sign-in page. Password checks now also run "
            "off to the side, so a wave of sign-in attempts no longer stalls everyone.",
            "No change to what the AI or sign-in features do or to how their results "
            "are used — only to keep slow work from freezing the app.",
        ],
    },
    {
        "version": "2.18",
        "date": "July 19, 2026",
        "summary": "The app now shields itself against the hosting platform's "
                   "intermittent errors: when Hugging Face's own network layer "
                   "drops a request before it ever reaches the app, the page now "
                   "quietly retries instead of showing an error.",
        "changes": [
            "Hugging Face's network layer has been intermittently failing "
            "requests before they reach the app at all — users saw random "
            "\"error 500\" pages even though the app itself was healthy. The "
            "app's built-in offline helper (the service worker) now recognizes "
            "exactly that case and silently retries up to three times, so an "
            "affected click almost always succeeds on its own.",
            "This is safe even for form submissions: every real answer from the "
            "app now carries a hidden marker, so a retry only ever happens when "
            "it's provable the app never received the request in the first "
            "place — nothing can be submitted twice.",
            "The deploy pipeline got the same shield: the pre-deploy backup "
            "step now retries through these platform hiccups instead of "
            "aborting the whole deployment (which is what blocked two fixes "
            "from shipping earlier today).",
        ],
    },
    {
        "version": "2.17",
        "date": "July 19, 2026",
        "summary": "The AI features now ask Google for its current model: the one the "
                   "system was using is no longer offered to newly created access "
                   "keys, so Google was turning every request away.",
        "changes": [
            "Google no longer offers the AI model the system was asking for "
            "(gemini-2.5-flash) to newly created access keys — it answered every "
            "request with \"this model is no longer available to new users.\" The "
            "system now asks for Google's current model (gemini-3.5-flash) instead, "
            "so the AI features work with a fresh access key.",
            "If a different model is ever needed, the CSS_GEMINI_MODEL server "
            "setting still overrides this default, same as before.",
        ],
    },
    {
        "version": "2.16",
        "date": "July 19, 2026",
        "summary": "Fixed a server error that could hit the AI search bar right after "
                   "the AI service was newly set up on the server.",
        "changes": [
            "If the AI model name typed into the server's settings had picked up a "
            "stray blank line or space (easy to do when pasting), the AI search bar "
            "on the Start page could crash with a server error instead of just quietly "
            "not answering. Those settings are now cleaned up automatically, so a "
            "stray space or line break can no longer cause a crash.",
            "As a second safety net, if a request to the AI service still somehow "
            "can't be sent, the system now treats it the same as any other AI hiccup "
            "— it quietly falls back to the ordinary search instead of showing an "
            "error page.",
        ],
    },
    {
        "version": "2.15",
        "date": "July 19, 2026",
        "summary": "Added a backup AI helper: if the main AI runs out of its free daily "
                   "quota, the system can now automatically try a second, also-free "
                   "service instead of just going quiet.",
        "changes": [
            "This backup only switches on when the main AI (Google) has used up its "
            "free daily allowance or is being told to slow down — never for other kinds "
            "of hiccups, and never for the directory-harmonizing feature, which keeps "
            "its own stricter privacy rule regardless.",
            "It is off by default. An administrator has to turn it on at Admin → AI, "
            "and must also set up the backup service's own access key on the server "
            "first for it to do anything.",
            "The Admin → AI page now shows whether the backup service is set up, "
            "whether it's turned on, and which service actually answered each request "
            "in the interaction log.",
        ],
    },
    {
        "version": "2.14",
        "date": "July 19, 2026",
        "summary": "Fixed the AI features not working at all: the system was asking "
                   "Google for an AI model that has been retired, so every request was "
                   "being turned away. It now uses the current model.",
        "changes": [
            "Every AI feature (the Start page assistant, AI drafts, suggestions and "
            "the rest) was failing quietly because the AI model the system asked "
            "Google for is no longer offered on the free plan — Google was refusing "
            "every single request. The system now asks for the current model, so the "
            "AI features work again.",
            "When Google turns a request away like this in the future, the AI log at "
            "Admin → AI now records Google's own explanation of why, instead of a "
            "generic \"rate limited\" note — so this kind of problem can be spotted "
            "and named immediately next time.",
        ],
    },
    {
        "version": "2.13",
        "date": "July 19, 2026",
        "summary": "A new behind-the-scenes tool lets the office ask AI for a second "
                   "opinion on the draft Filipino wording used in the public survey "
                   "form — nothing changes automatically; a staff member still has to "
                   "read each suggestion and decide whether to use it.",
        "changes": [
            "A new offline helper (not something respondents or staff see in the app) "
            "can send the survey's draft Filipino text, side by side with the English "
            "original, to AI and print back a suggested revision for each one, so the "
            "bureau can review and tighten the wording faster.",
            "It never edits the survey text itself and never shows anything to the "
            "public — it only prints a report for a staff member to read, exactly like "
            "asking a colleague to proofread a draft.",
            "If a suggestion drops or changes a fill-in-the-blank part of a question "
            "(like the name of the resource person), it is automatically flagged as "
            "needing a manual fix rather than shown as ready to use.",
            "Uses the same AI on/off switch, daily limits, and usage log as every "
            "other AI feature at Admin → AI.",
        ],
    },
    {
        "version": "2.12",
        "date": "July 19, 2026",
        "summary": "The Start page's assistant can now remember the last few things you "
                   "said and, once turned on to its highest level, offer to do a small set "
                   "of tasks for you — starting a draft activity, archiving one, or "
                   "exporting a report — but only ever after showing you exactly what it "
                   "would do and waiting for you to confirm.",
        "changes": [
            "At the new \"assistant\" AI level, the Start page keeps a short memory of "
            "the last few things you typed and what it answered, so a follow-up like "
            "\"do it\" after a suggestion can be understood in context.",
            "The assistant can now propose three things: start a new bureau activity "
            "draft, archive one of your own recent activities, or export a report — "
            "each shown as a plain-language confirmation card with Confirm and Cancel, "
            "never done on its own.",
            "Nothing is ever taken from what the AI says at face value: which activities "
            "can be archived, which report types and formats are valid, and whether you "
            "even have permission for that action are all checked against the real "
            "system rules before the confirmation card is even shown — clicking Confirm "
            "always goes through the exact same screen and checks as doing it by hand.",
            "This is off unless an administrator raises the AI level to \"assistant\" at "
            "Admin → AI; at the earlier levels (router/answers), the Start page works "
            "exactly as it did before.",
        ],
    },
    {
        "version": "2.11",
        "date": "July 19, 2026",
        "summary": "The Name cleanup page can now ask AI whether a likely-duplicate pair "
                   "is really the same person — a quick hint next to the existing "
                   "\"fold in\" merge button. Off by default, and merging always stays a "
                   "human decision.",
        "changes": [
            "A new \"✨ Ask AI\" button beside each likely-duplicate suggestion on "
            "Directory → Name cleanup asks AI whether the two names are the same "
            "person, different people, or unclear, with a one-line reason — shown as "
            "a hint chip next to the existing one-click \"fold in ↦\" merge button.",
            "The suggestion is read-only: nothing merges on its own. Only clicking "
            "the existing \"fold in\" button (which an admin already had to click) "
            "actually combines two records, exactly as before.",
            "Because this is the one AI feature that looks at people's names, it "
            "ships switched off by default even after AI features are turned on "
            "elsewhere — an administrator has to flip it on for this feature "
            "specifically at Admin → AI, where it's clearly labeled.",
            "The button is silently unavailable, with a plain note instead of an "
            "error, if AI is off, not configured, or the daily limit has been "
            "reached — Name cleanup's search, quick fixes and merging keep working "
            "exactly as before either way.",
        ],
    },
    {
        "version": "2.10",
        "date": "July 19, 2026",
        "summary": "The welcome/ending messages an organizer sets up for an activity can now "
                   "be personalized by AI in one click, tailored to that activity's own title, "
                   "date, venue and modality — the five ready-made tone drafts are still there "
                   "as the starting point and the fallback.",
        "changes": [
            "A new \"✨ Personalize with AI\" button next to each message's tone picker on an "
            "activity's Manage page asks AI to write a fresh draft in the requested tone, using "
            "only that activity's own details (title, date, venue, face-to-face/online) — never "
            "any attendee's name or other personal data, since none is available to it.",
            "The AI draft keeps the same {name} placeholder the tone-preset drafts use, so it "
            "still greets each participant by their own first name once they view the page.",
            "Nothing is saved automatically: the draft only fills the message box, and the "
            "organizer's existing auto-save (or the Save button, without JavaScript) is what "
            "actually keeps it — exactly like picking one of the five tone-preset drafts today.",
            "The button is silently unavailable, with a plain note instead of an error, if AI "
            "is off, not configured, or the daily limit has been reached — the tone-preset "
            "drafts and manual editing keep working exactly as before either way.",
        ],
    },
    {
        "version": "2.09",
        "date": "July 19, 2026",
        "summary": "The admin Feedback board can now suggest a status, urgency, and a "
                   "possible duplicate for a submission with one click — the admin always "
                   "reviews and saves it themselves, nothing changes on its own.",
        "changes": [
            "A new \"✨ Suggest triage\" button on a feedback item's page asks AI for a "
            "suggested status, an urgency (Low/Medium/High/Critical), and whether it looks "
            "like a duplicate of another open item — with a short plain-language reason — "
            "and fills those fields into the existing Save form for the admin to review "
            "and submit (or change) themselves.",
            "A suggested duplicate is only ever one of the other currently-open items — "
            "the admin's own screen builds that list, so the suggestion can never point at "
            "an item that wasn't actually shown to it.",
            "Feedback text only ever leaves the server masked, and the button is silently "
            "unavailable (with a plain notice, no error) if AI is off, not configured, or "
            "the daily limit has been reached — the ordinary triage form always works.",
        ],
    },
    {
        "version": "2.08",
        "date": "July 19, 2026",
        "summary": "Report writers can now get an AI-drafted starting point for the parts that "
                   "used to be written by hand or left as \"N/A\" — the activity Excel export's "
                   "analysis columns, and the official CO-CSM report's Action Plan / Continuous "
                   "Improvement sections — always editable, and the download never depends on AI.",
        "changes": [
            "A new \"✨ Draft with AI\" button on an activity's report writes an AI-drafted "
            "Analysis / Action / Next Steps / Resources for that activity's \"AGENDA 4\" Excel "
            "row, from its scores only (no comments, no personal data) — shown in editable boxes "
            "right there so a manager or admin can review and Save before it's used.",
            "A matching \"✨ Draft with AI\" button on the official CO-CSM report (Reports → "
            "Type 1 · ARTA) drafts Section V (Agency Action Plan) and Section VI (Continuous "
            "Improvement) from that period's scores and its most common \"areas to improve\" "
            "comment themes, again editable and saved separately.",
            "Both are opt-in prefills, not automatic rewrites: nothing changes until a manager "
            "or admin clicks \"Draft with AI\", and downloading the Excel / Word / PDF report "
            "always works exactly as before — it uses whatever was last saved, or today's "
            "computed default / \"N/A\" if nothing ever was, even with AI off.",
        ],
    },
    {
        "version": "2.07",
        "date": "July 19, 2026",
        "summary": "Activity reports can now use AI to double-check how comments are sorted "
                   "(Appreciated / To improve / Mixed) and to write a quick 3-point summary — "
                   "still off by default, and a person's own re-tag always wins over AI's.",
        "changes": [
            "A new \"Re-analyze with AI\" button on an activity's report re-checks how its "
            "comments were sorted into Appreciated / To improve / Mixed, catching cases the "
            "word-list missed — it never touches a comment a person has already re-tagged by "
            "hand, and a human re-tag always wins if both ever disagree.",
            "A new \"AI summary\" button writes a short 3-point takeaway from that same "
            "activity's comments, grouped by topic the same way the page already groups them.",
            "Both only ever see the comment text itself (masked the same way as elsewhere), "
            "never who wrote it, and both are silently unavailable (with a plain notice, no "
            "error) if AI is off, not configured, or the daily limit has been reached.",
        ],
    },
    {
        "version": "2.06",
        "date": "July 19, 2026",
        "summary": "The admin UX Insights page can now run its AI analysis right there "
                   "with one click, instead of only downloading a file to paste "
                   "elsewhere. Still off by default, and it always falls back to the "
                   "download if anything goes wrong.",
        "changes": [
            "A new \"Analyze now\" button on Admin → UX Insights sends the same "
            "anonymized telemetry summary already offered as a download to the "
            "assistant and shows the write-up in the page, with 👍/👎 feedback.",
            "Nothing personally identifying is ever included — same masking and "
            "pseudonymization as the existing download.",
            "If AI analysis is off, unavailable, or over its daily usage cap, the "
            "button quietly points back to the existing download link — nothing "
            "ever breaks.",
        ],
    },
    {
        "version": "2.05",
        "date": "July 19, 2026",
        "summary": "The assistant page (Start) can now answer a straight question in "
                   "words — \"how many responses this month\" or \"how do I track a "
                   "training\" — instead of only jumping to a page. Still off by "
                   "default, and it always falls back the same way if anything goes "
                   "wrong.",
        "changes": [
            "Typing a factual question on /start (like a response count or overall "
            "satisfaction) now gets answered right there, computed the same way the "
            "home page's own numbers are — the assistant only ever picks which number "
            "you're asking for, it never makes one up.",
            "Typing a \"how do I…\" question now gets answered with the matching "
            "written guide's own text plus a link to open it, the same guide already "
            "available from the “?” on every page.",
            "Both are opt-in on top of the existing router mode (Admin → AI → "
            "\"answers\"), only ever answer with pages and figures this account "
            "could already reach on its own, and carry the same 👍/👎 feedback.",
        ],
    },
    {
        "version": "2.04",
        "date": "July 19, 2026",
        "summary": "An optional new \"assistant\" page (Start) lets you type what you want in "
                   "plain language and get taken straight there — still off by default, and it "
                   "always falls back to the ordinary search if anything goes wrong.",
        "changes": [
            "A new /start page — reachable from \"✨ Try the assistant\" on the home hub — lets "
            "you type a request like \"who answered yesterday's training\" and jump straight to "
            "the matching page, with a quick 👍/👎 on whether the suggestion was right.",
            "An administrator can turn this on from Admin → AI (the \"router\" mode) and choose "
            "whether a fresh sign-in lands on this new page or the classic hub; either setting "
            "can be flipped back at any time.",
            "The assistant only ever offers pages this account is already allowed to open, and "
            "if it's off, unavailable, or over its daily usage cap, the page quietly falls back "
            "to the same keyword search used everywhere else — nothing ever breaks.",
        ],
    },
    {
        "version": "2.03",
        "date": "July 19, 2026",
        "summary": "Behind-the-scenes groundwork for optional AI features — nothing changes "
                   "for anyone yet. A new Admin → AI page lets an administrator turn features "
                   "on later, one at a time, with a daily usage cap and a full log of every "
                   "call so nothing can run away unnoticed.",
        "changes": [
            "A new Admin → AI page shows whether an AI connection key is set up, lets an "
            "administrator switch AI features on (starting off by default) and set a daily "
            "limit on how many AI calls the system may make, and includes a “Test connection” "
            "button to confirm it can actually reach the AI service.",
            "Every AI call the system ever makes — and every time one is skipped or falls "
            "back to the ordinary non-AI behavior — is written to a log on that page, so any "
            "odd AI behavior can always be traced back and explained.",
            "This release turns nothing on. With no AI features enabled (the default), the "
            "system behaves exactly as it did before — this is purely the plumbing that later "
            "AI features will be built on top of.",
        ],
    },
    {
        "version": "2.02",
        "date": "July 18, 2026",
        "summary": "UX Insights can now be downloaded as a ready-to-share analysis file, "
                   "shows which screens are used most and least, and now also notices "
                   "searches that find nothing and forms people start but never submit.",
        "changes": [
            "The UX Insights page has a new “Download handoff for AI analysis” button. "
            "It saves one file that explains itself — what the system is, what each "
            "signal means, which screens see friction, and which screens are used most "
            "and least — ready to hand to an AI assistant for concrete interface-"
            "improvement suggestions. As always, nothing personal is in it: no names, "
            "no ids, nothing anyone typed.",
            "Searches that come back empty are now counted — the search palette, the "
            "search page, the paper-entry and People filters, and the help guide all "
            "report a search that found nothing, so the “Failed searches” panel finally "
            "fills in and shows what people look for but can't find.",
            "The system now also notices when someone starts filling in a form but "
            "leaves the page without submitting it — recording only which form and how "
            "many boxes were touched, never what was typed — so forms that quietly "
            "lose people can be found and fixed.",
        ],
    },
    {
        "version": "2.01",
        "date": "July 17, 2026",
        "summary": "Admins can now see exactly which build is running on the Ops page, and a new "
                   "“UX Insights” page shows where people are getting stuck on-screen — "
                   "clicks that don't do anything, frustrated repeat-clicking, and searches that come "
                   "back empty — ranked by how often it's happening.",
        "changes": [
            "The Ops page now shows a “Build” panel: the version currently running, "
            "when it was deployed, and by whom — so you can always tell which build is "
            "live without guessing.",
            "A new Admin → UX Insights page quietly watches how the system is actually "
            "used — clicks on things that don't respond, repeated frustrated clicking in "
            "the same spot, and searches that come back empty — and turns that into a "
            "ranked “what to fix first” list, matched up with anything people already "
            "reported through Send Feedback.",
            "Nothing personal is ever recorded — only which screen and which button or area, "
            "never names, ids, or what someone typed.",
        ],
    },
    {
        "version": "2.00",
        "date": "July 17, 2026",
        "summary": "The suggested comment tags on the survey forms now cap at 3 at a time, and picking one no longer lets you keep an opposite tag active too (like “Fast service” and “Long wait” together).",
        "changes": [
            "On the comments box of a survey form, tapping a 4th suggested tag while "
            "3 are already active is ignored (the rest dim to show you're at the "
            "limit) — pick fewer, clearer tags instead of stacking on a wall of "
            "them. Tags that mean opposite things (e.g. “Easy process” vs. “Too "
            "many steps”, “Started on time” vs. “Ran over time”) now also swap "
            "each other out automatically, so a comment can no longer end up "
            "saying both at once.",
        ],
    },
    {
        "version": "1.99",
        "date": "July 17, 2026",
        "summary": "The Type 2 activity Excel download (MRR format) now lays out each activity's “Relevant Findings” the way the official report reads it — title, date, SERVQUAL scores, response counts and a short list of what people wrote.",
        "changes": [
            "On Reports → Activities → Download (Excel, MRR format), each activity's "
            "“Relevant Findings” cell now reads as a single block: the activity title, "
            "date and format (Virtual / Face-to-Face); its official SERVQUAL Score and "
            "verdict, and Overall SERVQUAL Rating and grade; the response rate, total "
            "responses and total participants; and, under “COMMENTS:”, up to 5 of the "
            "actual comments people typed in — never the pre-set rating choices, and "
            "with empty or throwaway answers like “none” or “n/a” left out.",
        ],
    },
    {
        "version": "1.98",
        "date": "July 15, 2026",
        "summary": "Every QR code now has its own “Download” button, so you can save the image straight to your phone or computer instead of only printing the whole page.",
        "changes": [
            "The QR codes shown after creating an activity, on an invited activity's "
            "manage page, and on the standing Walk-in (ARTA) QR page now each have a "
            "“⤓ Download” link right under the code. It saves that one QR as a PNG "
            "image file, named after the activity or speaker it's for — no more "
            "relying on Print or a manual “save image as” to get a usable copy for a "
            "poster or handout.",
        ],
    },
    {
        "version": "1.97",
        "date": "July 15, 2026",
        "summary": "The create-activity screen now warns you if you already made an activity with that same name and date, before you save a duplicate.",
        "changes": [
            "As you type the activity name and date on the create screen, it "
            "checks whether you already created an activity with that same name "
            "on that same date recently, and shows a note with a link straight to "
            "it — so an accidental double-click or a lost confirmation doesn't "
            "quietly leave a second, empty copy behind.",
            "This is only a heads-up: it never blocks Save. If it really is a "
            "second, separate activity, just carry on — nothing changes about "
            "how creating an activity works.",
        ],
    },
    {
        "version": "1.96",
        "date": "July 15, 2026",
        "summary": "Archive a full activity — not just a standalone one — straight from “Your recent activities”, and restore it later from Archived activities.",
        "changes": [
            "A bureau or invited event now gets an Archive button on “Your recent "
            "activities” too, not only a lone speaker review. Previously the only "
            "place to archive a full activity was the “Ongoing” list, and that "
            "button disappears once the activity's window closes — so a same-day "
            "duplicate created by mistake, with no responses, had no Archive button "
            "left anywhere once the next day arrived.",
            "Archived activities now shows every archived activity, not just "
            "standalone ones, with a working Restore button on each — including "
            "ones archived from the Ongoing feed or in bulk from the Activities "
            "page, which previously had no way back once put away.",
        ],
    },
    {
        "version": "1.95",
        "date": "July 13, 2026",
        "summary": "You can now enter the real number of respondents for an activity, so its completion rate is measured against the true attendance instead of only the people who registered online.",
        "changes": [
            "On an activity's Manage page there's a new “Number of respondents” box. "
            "Fill it in when you know how many people actually took part — including "
            "walk-in, QR or paper answers that never registered through the link — and "
            "the Monitor's completion rate is measured against that number instead of "
            "the online registration count. Leave it blank to go back to counting "
            "against registrations, and you can change it any time.",
            "When you've entered a number, the Monitor's completion-rate box shows "
            "“of N expected” so everyone can see it's measured against the real "
            "attendance, and walk-in answers are counted toward it.",
            "You can't enter a number lower than the responses already collected, so "
            "the completion rate can never be pushed above 100%. Section managers can "
            "set this on their own activities; administrators on any activity.",
        ],
    },
    {
        "version": "1.94",
        "date": "July 13, 2026",
        "summary": "The activity Monitor’s “Completion rate” now counts everyone who took part — the people who answered without pre-registering are included, not set aside.",
        "changes": [
            "On an activity’s Monitor page, “Completion rate” used to look only at "
            "the people who pre-registered. It now measures how many of EVERYONE who "
            "took part finished: the walk-in / QR / paper responses (the “Not "
            "pre-registered” box) are added in, and each of them counts as a "
            "completed response. So a busy activity with lots of walk-ins now reads "
            "a fairer, higher number instead of being pulled down by people the old "
            "rate ignored.",
            "The rate still reaches 100% only when every registered person has "
            "actually finished — extra walk-in answers help the rate but can’t push "
            "it to a misleading 100% on their own.",
        ],
    },
    {
        "version": "1.93",
        "date": "July 9, 2026",
        "summary": "The activity Monitor now counts things correctly: “Completed” can never be higher than “Registered”, and it shows how many people answered without pre-registering.",
        "changes": [
            "On the Monitor page for an activity, the live “Completed CSS” number "
            "was sometimes showing more than the number of people registered, and "
            "would jump around when the page refreshed. It now always counts only "
            "the registered people who finished, so “Completed” is never higher "
            "than “Registered”, and all the boxes update together and stay in step.",
            "“Completion rate” now reaches 100% only when everyone registered has "
            "actually finished — an almost-complete activity reads 99%, not a "
            "misleading 100%.",
            "A new “Not pre-registered” box shows how many responses came in by "
            "walk-in, QR, or paper with no registration. These were being counted "
            "before but weren't shown on their own — so if someone answered without "
            "using their registration link, you can now see it there (which is why "
            "their name might still read “Not started”). The downloaded roster shows "
            "the same figure.",
        ],
    },
    {
        "version": "1.92",
        "date": "July 9, 2026",
        "summary": "A resource person's individual report download (PDF, PowerPoint and Excel) now includes the written comments people left about them — matching what their page already shows.",
        "changes": [
            "Following the per-activity change, downloading a single person's "
            "performance report now includes the written comments from their rated "
            "responses at the bottom — the same ones shown on their page. Before, the "
            "downloaded file left them out. The PDF and Excel gain a “Respondent "
            "comments” section, and the PowerPoint gains an “In their words” slide, "
            "with identical answers shown once and marked “×N”, and empty or "
            "throw-away answers left out.",
        ],
    },
    {
        "version": "1.91",
        "date": "July 9, 2026",
        "summary": "The download of a single activity's report (PDF, PowerPoint and Excel) now includes the written comments people left — the same ones shown on the activity's page.",
        "changes": [
            "When you open one activity's report and download it, the written "
            "comments people left are now included at the bottom — before, only the "
            "on-screen page showed them, and the downloaded file left them out. The "
            "PDF and the Word/Excel-style downloads now carry a “Respondent "
            "comments” section listing every written comment, with identical answers "
            "shown once and marked “×N” (so a repeated “Very helpful” reads as “Very "
            "helpful ×3”). Empty and throw-away answers (“none”, “n/a”, “wala”) are "
            "left out, so the list is only real feedback.",
            "The PowerPoint version gains an “In their words” slide with the most "
            "common comments, and the Excel gets a tidy “Respondent comments” sheet "
            "listing each distinct comment and how many people gave it. This matches "
            "how the bureau-wide reports already show comments, so the per-activity "
            "download and the on-screen page can never disagree.",
        ],
    },
    {
        "version": "1.90",
        "date": "July 9, 2026",
        "summary": "The downloadable reports now list the written comments at the bottom, with repeats grouped into one line and a “×N” count instead of the same answer over and over.",
        "changes": [
            "At the foot of the downloadable customer-satisfaction reports, the "
            "comments people wrote are now listed together. Identical answers are "
            "shown once with a “×N” next to them — so a repeated “Very helpful "
            "staff” shows as “Very helpful staff ×3” instead of the same comment "
            "printed again and again. Empty and throw-away answers (“none”, “n/a”, "
            "“wala”, and the like) are left out, so the list carries only real "
            "feedback.",
            "The Word walk-in (ARTA) report lists them grouped as Appreciated, To "
            "improve, and Other; the Word resource-person (SERVQUAL) report gains a "
            "new “Respondent comments” section it didn't have before; and the "
            "resource-person Excel gets a tidy “Comments” sheet with each distinct "
            "comment and how many people gave it, next to the existing "
            "one-row-per-person sheet.",
            "The PDF and slide versions still show just a few of the most common "
            "comments as a taste, but now mark repeats with “×N” too and point to "
            "the Word file for the complete list. Very long comment lists are "
            "capped with an “…and N more” note so a report never runs to hundreds "
            "of pages.",
        ],
    },
    {
        "version": "1.89",
        "date": "July 9, 2026",
        "summary": "Two labels now read more plainly: an “activity report” is now called a “customer satisfaction survey report,” and the “Verdict” column is now titled “Interpretation.”",
        "changes": [
            "Wherever the per-activity report was called an “activity report” — the "
            "report’s title, the “View individual reports” link, and the downloadable "
            "Word, Excel, PDF and PowerPoint versions — it is now called the "
            "“Customer Satisfaction Survey Report.”",
            "The service-quality table column that read “Verdict” (how each dimension "
            "landed against what people expected) is now headed “Interpretation,” on "
            "screen and in every download, along with the matching wording on the "
            "activity, team and dashboard cards.",
            "These are wording changes only — the scores, the way they are worked out, "
            "and the saved responses are all exactly the same.",
        ],
    },
    {
        "version": "1.88",
        "date": "July 9, 2026",
        "summary": "An activity you close now leaves the home “Ongoing” list right away, instead of lingering there for hours.",
        "changes": [
            "When you closed an activity, the home dashboard could keep showing it "
            "under “Ongoing — CSS collecting” long after — sometimes until the next "
            "day — even though its reporting was already closed. The dashboard was "
            "reading the wrong clock (the server's, which runs on a different time "
            "zone) to decide whether an activity was still collecting. It now uses "
            "the same Philippine-time clock as the rest of the app, so a closed "
            "activity drops off the Ongoing list the moment you close it. (The "
            "public response link itself was always closing on time; only the "
            "dashboard label lingered.)",
        ],
    },
    {
        "version": "1.87",
        "date": "July 9, 2026",
        "summary": "Fixed a problem where an activity's newly encoded responses could disappear from its reports — the count showed on the Manage page, but the resource-person report came up empty and the activity was missing from the report's activity list.",
        "changes": [
            "For one invited activity, the Manage page correctly showed its 286 "
            "responses, but opening “View resource-person results” said there were "
            "none, the responses didn't appear in the Resource Persons report, and "
            "the activity was missing from that report's activity picker. The "
            "answers were safe in the database the whole time — they had slipped "
            "out of the app's fast in-memory copy that the reports read from, "
            "during a busy live-encoding session, and stayed out. The reports now "
            "keep that fast copy exactly in step with what's saved, so freshly "
            "encoded responses always show up, and any activity affected before "
            "this fix is restored automatically.",
        ],
    },
    {
        "version": "1.86",
        "date": "July 6, 2026",
        "summary": "An invited (“we were invited / outside”) activity now stays on the home “Ongoing” list for as long as its combined-QR form is still open, so you can always find and manage it.",
        "changes": [
            "Invited activities — the ones where your office was a guest and you "
            "gather feedback through a single combined-QR link — used to drop off "
            "the home page about a week after the event, even when the link was "
            "still live and collecting answers. They never appeared under "
            "“Upcoming” or “Ongoing”, only briefly under “Your recent activities”, "
            "so an older-but-still-open one became impossible to reach. Now any "
            "invited activity whose feedback window is still open shows under "
            "“Ongoing — CSS collecting”, with its name, its running response count, "
            "and a link straight to its Manage page. It leaves the list once you "
            "close its window.",
        ],
    },
    {
        "version": "1.85",
        "date": "July 6, 2026",
        "summary": "On an activity's Monitor page, you can now click a participant's status to open their own answers — the exact ratings and comments they gave.",
        "changes": [
            "On the Monitor page for an activity, each participant who has "
            "answered now has a clickable status. Open it to see that person's "
            "own response — their rating for every question, any note they left "
            "on a question, and their overall comment, shown just as they "
            "answered. Only the activity's creator or an admin can open it. It "
            "covers people who registered and answered through the activity "
            "link; anonymous walk-in / QR / paper responses aren't tied to a "
            "name, so they don't appear here. If someone's personal details "
            "were removed under the data-retention policy, their row shows as "
            "“identity removed” with no answers.",
        ],
    },
    {
        "version": "1.84",
        "date": "July 6, 2026",
        "summary": "The Verbatims page now shows a third “Mixed” column, so good-and-bad comments have a home of their own instead of appearing on both sides.",
        "changes": [
            "On Reports → Verbatims, comments used to sit in two columns — what "
            "people appreciated and what they'd improve — and a “Mixed” comment "
            "(one that names a strength and a wish in the same breath) was shown "
            "in both. There's now a dedicated third “Mixed — good and bad” column, "
            "so each comment appears once, in the column that fits it. Re-tagging a "
            "comment still works the same way; a Mixed one simply moves to its own "
            "column now.",
        ],
    },
    {
        "version": "1.83",
        "date": "July 6, 2026",
        "summary": "The Resource Persons Excel download now includes a per-respondent “Responses” sheet — the actual scores behind each activity's numbers.",
        "changes": [
            "When you download the Excel (.xlsx) from Reports → Resource Persons, "
            "there's a new “Responses” sheet listing one row per person who "
            "answered — each respondent's own scores for the five service "
            "dimensions, their overall, their expectation and overall-service-"
            "quality ratings, plus when they answered, the activity, and any "
            "comment they left. It follows whatever activity you've filtered to, "
            "so you can pull the raw, per-submission data for a single activity or "
            "resource person instead of only the combined averages. The other "
            "sheets and all the report documents are unchanged.",
        ],
    },
    {
        "version": "1.82",
        "date": "July 5, 2026",
        "summary": "Fixed the automatic scheduled backup so it actually runs — it was switched on but silently never firing.",
        "changes": [
            "The Backups page's automatic schedule was turned on but had never "
            "actually run a single backup, because it was waiting on a starting "
            "point it could never set for itself. It now seeds that starting point "
            "when the schedule is on, so the daily backup fires as intended — and if "
            "the system happens to be paused at the scheduled time, it catches up the "
            "next time someone opens it, instead of skipping the day. Your data was "
            "never at risk in the meantime: the system already saves a copy to "
            "permanent storage continuously, and the new daily off-site copy on "
            "GitHub was unaffected.",
        ],
    },
    {
        "version": "1.81",
        "date": "July 5, 2026",
        "summary": "The Monitor page now has a “What people said” button that takes you straight to the written comments for that activity.",
        "changes": [
            "An activity's Monitor page now shows a “💬 What people said →” button "
            "that opens the comments people left, jumping straight to the "
            "“In people's own words” section of that activity's report. It works for "
            "both your own activities and invited (resource-person) ones, and only "
            "appears once at least one response has come in — so you can read the "
            "feedback in words without hunting through the reports for it.",
        ],
    },
    {
        "version": "1.80",
        "date": "July 5, 2026",
        "summary": "The Backups page now shows a history of the daily off-site backups kept safely on GitHub — so you can confirm at a glance that a recent copy exists off Hugging Face.",
        "changes": [
            "The Backups page has a new “Off-site backups (GitHub)” panel. A separate "
            "job now runs every day on GitHub — not on any office computer — and pulls "
            "an encrypted copy of the whole database into a private GitHub repository, "
            "so a recent copy survives even if Hugging Face itself were lost. Each time "
            "it succeeds it reports back here, and the panel lists the recent copies with "
            "the date and file name, plus a green “Off-site copy current” badge.",
            "If no off-site backup has reported in for more than two days, the panel "
            "shows an amber “overdue” warning pointing you to the GitHub job — so a "
            "silently broken backup can't go unnoticed. This replaces the old daily "
            "backup that only ran when a particular office PC happened to be switched on.",
        ],
    },
    {
        "version": "1.79",
        "date": "July 5, 2026",
        "summary": "Closing an activity now moves it to “Recently concluded” right away, and an invited activity's written comments now show on its results page.",
        "changes": [
            "When you close an activity, it now appears in the home page's "
            "“Recently concluded” list straight away — including a one-day activity "
            "you close on the same day, and activities with no end date set. Before, "
            "the list only went by the date, so a just-closed activity could stay off "
            "it until the next day (or never show, if it had no end date).",
            "An invited / resource-person activity now shows the written comments "
            "people left right on its results page (Resource Persons report, narrowed "
            "to that activity) — the same “In people's own words” section your own "
            "activities already have, with a “See this activity's verbatims” link that "
            "stays focused on just that activity. These activities had no comments view "
            "of their own before.",
            "Fixed a case where opening one invited activity's results could quietly "
            "show the whole bureau's numbers instead when the activity couldn't be "
            "matched — it now shows a clear, empty result for that activity rather than "
            "misleading figures.",
        ],
    },
    {
        "version": "1.78",
        "date": "July 2, 2026",
        "summary": "Once you close an activity, its report is one click away, right on the Manage page.",
        "changes": [
            "When an activity is closed, its Manage page now shows a prominent "
            "“View the report →” button next to Reopen — so closing an activity "
            "leads straight to its results instead of a dead end. The button opens "
            "the right report for the activity: the per-activity SERVQUAL report "
            "for a regular activity, or the Resource Persons results for an "
            "invited / resource-person one. (Invited activities already had this; "
            "now regular ones do too.)",
        ],
    },
    {
        "version": "1.77",
        "date": "July 2, 2026",
        "summary": "Resource-person results are one click from the home page, the Resource Persons report has an Excel download, and you can remove a stray registration.",
        "changes": [
            "On the home page's “Recently concluded” list, an invited / "
            "resource-person activity now opens its actual results (the Resource "
            "Persons report, narrowed to that activity) instead of a generic list "
            "— so “open the report” finally lands on the numbers.",
            "The Resource Persons report (Reports → Resource Persons) now has an "
            "Excel (.xlsx) download under “Raw data”, alongside the Word / PDF / "
            "PowerPoint options — the dimension scores, the SERVQUAL summary and "
            "the respondent profile in a spreadsheet you can work with.",
            "On an activity's Monitor page you can now remove a registrant entry "
            "that was a test, a duplicate, or a no-show — each roster row has a "
            "“Remove” button (with a confirm). For safety this is only offered "
            "before that person has answered: once an entry has ratings they're "
            "part of the reports, so it can't be deleted.",
        ],
    },
    {
        "version": "1.76",
        "date": "July 2, 2026",
        "summary": "Close a survey the moment you're done — and see at a glance when each survey stops accepting answers.",
        "changes": [
            "You can now stop a survey right away, without waiting for its "
            "“closes” date to arrive. Open the activity's Manage page and use "
            "“Close survey now” — it immediately stops new answers on both the "
            "public link and paper entry. Everything already collected stays in "
            "your reports, and you can reopen it any time to back-enter a late "
            "form or fix a typo, then close it again. This used to be available "
            "only for invited (“outside”) activities; now every activity has it.",
            "The Monitor page for an activity now shows, right under the title, "
            "whether it's still open and until when — “Open until December 31, "
            "2099”, “Open — no closing date set”, or “Closed”. No need to dig into "
            "the Manage page to check.",
        ],
    },
    {
        "version": "1.75",
        "date": "June 30, 2026",
        "summary": "The comment raffle now works for online activities too — not just face-to-face ones.",
        "changes": [
            "You can now run the comment raffle at an online activity, exactly like "
            "a face-to-face one. Anyone who leaves a comment on an online activity's "
            "feedback now gets a claim code on their thank-you screen and is entered "
            "in the draw; before, online responses were quietly left out. When you "
            "draw a winner, an online entrant is identified by their claim code — "
            "they show it to you or paste it in the chat to claim the prize — just "
            "like an anonymous walk-in. Nothing changes for face-to-face activities; "
            "this simply removes the face-to-face-only limit.",
        ],
    },
    {
        "version": "1.74",
        "date": "June 30, 2026",
        "summary": "Archive an activity straight from the home page's “Ongoing” list — no more hunting for where to put away a test or stray activity.",
        "changes": [
            "Admins now get an “Archive” button on each activity in the home "
            "page's “Ongoing — CSS collecting” list, so a test run or a stray "
            "activity that's still collecting can be put away right where you spot "
            "it — instead of going to the Edit / merge page to find the control. "
            "It works for both kinds the list shows: a one-off speaker review "
            "archives on its own, and a full event archives the whole activity "
            "(the event review and all its speaker forms) in one go. Nothing is "
            "deleted — every archived activity drops out of all lists, feeds and "
            "reports, and an admin can restore it any time from “Archived "
            "activities”.",
        ],
    },
    {
        "version": "1.73",
        "date": "June 26, 2026",
        "summary": "Safety net: the system now notices and warns within minutes if it ever stops saving your data — and can no longer get stuck doing so silently.",
        "changes": [
            "Hardened how the app saves live data to permanent storage. The "
            "background saver can no longer get silently stuck: each save now has "
            "a time limit, so a slow or stalled storage connection is abandoned "
            "and reported instead of freezing the saver. And the “is your data "
            "being saved?” line on the Operations page now turns red within a few "
            "minutes if saving has actually stopped — previously it could keep "
            "showing green while nothing was being saved. No action needed; this "
            "is purely a reliability and early-warning improvement.",
        ],
    },
    {
        "version": "1.72",
        "date": "June 26, 2026",
        "summary": "The Activity filter on the Resource Persons report is now a search box — type to find an activity instead of scrolling.",
        "changes": [
            "The “Activity” filter on the Resource Persons report is now a "
            "search-as-you-type box: click it and start typing an activity name "
            "to jump straight to it, instead of scrolling a long list. Use the "
            "up/down arrows and Enter to pick one from the keyboard. The list "
            "now stays a tidy, fixed width with longer titles trimmed, so it "
            "never runs off the side of the page. If a browser has scripting "
            "turned off it quietly falls back to the ordinary dropdown.",
        ],
    },
    {
        "version": "1.71",
        "date": "June 26, 2026",
        "summary": "Fixed the Activity dropdown on the Resource Persons report stretching too wide.",
        "changes": [
            "On the Resource Persons report, the new “Activity” filter sized itself "
            "to its longest activity title, so once you picked one it stretched "
            "almost the full width of the page. It now stays a sensible, compact "
            "width like the Scope and Period filters beside it, with longer titles "
            "trimmed inside the box.",
        ],
    },
    {
        "version": "1.70",
        "date": "June 25, 2026",
        "summary": "The shortcut cards on the home page now point to everything the system can do — including the newer pages.",
        "changes": [
            "The shortcut cards at the bottom of the home page had fallen behind as "
            "new pages were added, so a few things were only reachable from the top "
            "menu or the search box. They now list them all: “See how we're doing” "
            "adds Teams and Participation; “Official reports” adds the Resource "
            "Persons report and Shared materials; “Run a survey” adds the Monitor and "
            "the Invited events list; and Administration adds Sharing and the user "
            "Feedback board. Each shortcut still only shows to people whose role can "
            "open it.",
        ],
    },
    {
        "version": "1.69",
        "date": "June 25, 2026",
        "summary": "One click from an invited activity to its resource-person results — plus a fix so an activity report never breaks on a half-finished response.",
        "changes": [
            "Invited (outside) activities now have a direct “View resource-person "
            "results” link — on the new Invited events page and on the activity's own "
            "manage page. Because these activities are scored per resource person (they "
            "have no separate event report), the link opens the Resource Persons report "
            "already narrowed to just that activity, so you can see how the speakers did "
            "in one step instead of hunting for it. The link appears once an activity has "
            "responses; the manage page's old “View report” button used to lead to a "
            "page that didn't exist for these activities, and now points to the right place.",
            "Fixed a case where an activity's report page could fail to load if someone "
            "had submitted feedback only part-way (rating the event but skipping the "
            "“what did you expect” question). That dimension now simply shows a dash "
            "instead of a score gap, and the report opens normally.",
        ],
    },
    {
        "version": "1.68",
        "date": "June 25, 2026",
        "summary": "Invited (outside) activities are easier to find — a new list of them all, and they now show up on the home page after they finish.",
        "changes": [
            "A new “Invited events” page (under Manage) lists every activity run by "
            "an outside body where your staff were resource persons — upcoming, "
            "ongoing and finished, all in one place. Before, once an invited activity "
            "wrapped up it dropped off the Monitor and was only findable by digging "
            "through the reports; now it always has a home, and you can reach it from "
            "the menu or the search box. The Monitor's invited section also links "
            "straight to it for the ones that have concluded.",
            "The home page's “Recently concluded” strip now includes invited "
            "activities too, not just bureau events — so a just-finished invited "
            "session shows up there like everything else, marked with an “Invited” "
            "tag and linking to the invited-events list. Invited activities in your "
            "“Your recent activities” strip now carry the same “Invited” tag, so "
            "they're easy to tell apart from bureau-run ones at a glance.",
        ],
    },
    {
        "version": "1.67",
        "date": "June 25, 2026",
        "summary": "The Audit log now reads in plain English, with a quick look at what's been happening lately.",
        "changes": [
            "Every row in the Audit log now shows a plain-English action instead of "
            "a technical code — “Signed in”, “Updated feedback status”, “Set an "
            "activity's response window”, and so on — colour-grouped by kind "
            "(sign-ins, accounts, activities, feedback, data & backups). The exact "
            "technical code is still there if you hover over the label, and the "
            "filter dropdown now lists the friendly names too.",
            "A new “What's been happening” panel sums up the last 7 days: which "
            "kinds of action came up most (with a little bar for each) and who's "
            "been the busiest — so you get the shape of recent activity at a glance, "
            "on top of the existing today / this-week / all-time counts.",
        ],
    },
    {
        "version": "1.66",
        "date": "June 25, 2026",
        "summary": "The System health page now shows who's using the app and what's happened lately, in plain numbers.",
        "changes": [
            "The System health page has two new panels. “Who's using it” shows how "
            "many staff are active right now (anyone who did something in the last "
            "15 minutes), how many different people have signed in today and over "
            "the last 7 days, who signed in most recently, and a short list of the "
            "latest sign-ins — so you can see at a glance who's on the system.",
            "“Lately” shows what's moved in the last 7 days — feedback received "
            "today and this week, activities set up this week, and new participants "
            "registered this week — alongside the existing all-time totals, so the "
            "page reflects what's happening now and not just lifetime counts.",
        ],
    },
    {
        "version": "1.65",
        "date": "June 25, 2026",
        "summary": "Narrow the Resource Persons report to a single activity with a new Activity filter.",
        "changes": [
            "The Resource Persons report (Reports → Resource Persons) now has an "
            "“Activity” dropdown next to Scope and Period. Pick an activity and the "
            "whole report — the scores, dimensions and respondent count — narrows to "
            "just that activity's resource-person responses, so you can quickly pull "
            "up and review one activity on its own. Leave it on “All activities” to "
            "see everything combined as before. The downloads (Word, PDF, PowerPoint) "
            "follow the chosen activity too.",
        ],
    },
    {
        "version": "1.64",
        "date": "June 25, 2026",
        "summary": "Fixed the Activities list on a phone — turning on “Edit / merge” no longer hides the list behind the actions panel.",
        "changes": [
            "On the Activities list, switching on “Edit / merge” opens a panel of "
            "actions (rename, re-file, export, archive) that stays pinned to the "
            "bottom of the screen. On a phone that panel grew so tall it covered the "
            "whole activity list, so you couldn't see or tick anything. It now takes "
            "up at most half the screen and scrolls on its own, leaving the list "
            "visible above it — and its labels and boxes now stack full-width so "
            "they're no longer squeezed into a narrow column.",
        ],
    },
    {
        "version": "1.63",
        "date": "June 25, 2026",
        "summary": "A safeguard so automatic saving can recover on its own if it ever gets stuck — and the System health page now tells you, in plain words, whether your data is being saved right now.",
        "changes": [
            "We fixed a rare condition where the system's automatic save to "
            "permanent storage could get stuck and quietly stop saving new entries "
            "— the cause of some entries being lost on June 24. The system now "
            "recognises when this safety check has wedged itself for no good reason "
            "and clears it automatically, so saving resumes on its own within about "
            "a minute instead of staying stuck.",
            "The System health page now shows, in everyday words, whether your live "
            "data is actually being saved to permanent storage at that moment — with "
            "a clear red warning if it ever isn't — so this kind of problem can be "
            "spotted right away instead of going unnoticed.",
        ],
    },
    {
        "version": "1.62",
        "date": "June 25, 2026",
        "summary": "Closing an invited activity now really closes it — no more entries, its details lock, and a report is one click away.",
        "changes": [
            "On an invited (outside) activity's manage page, “Close responses now” "
            "now does what it says: it stops new answers on every speaker review — "
            "on paper as well as through the online link — instead of only the "
            "online link. A closed activity also disappears from the paper-entry "
            "list, so no one can key in more slips for it by mistake.",
            "Once an activity is closed, its details on that page (speakers, dates, "
            "the open/close window and the raffle) are locked and clearly marked, so "
            "a finished activity can't be edited by accident. A “Reopen to make a "
            "correction” button brings it all back if you need to fix a typo or "
            "back-enter a late form — then you simply close it again.",
            "Closing now also surfaces a “View activity report →” link right at the "
            "top of the page, so the report for that activity is one click away the "
            "moment you wrap it up. Nothing is ever deleted — a closed activity "
            "stays in all your reports.",
        ],
    },
    {
        "version": "1.61",
        "date": "June 23, 2026",
        "summary": "A stronger safeguard against a restart quietly rolling back very recent changes.",
        "changes": [
            "We closed a rare but real way the system could lose a few minutes of "
            "recent work. When the app restarts, it restores your data from the "
            "permanent storage; on a busy hand-off the storage can briefly show an "
            "out-of-date list, and the app could pick up an older copy and then save "
            "that back — quietly undoing the newest changes. (This is what briefly "
            "dropped three pieces of feedback overnight; no survey responses were "
            "affected, and the three were restored.)",
            "The app now stamps a “high-water mark” every time it saves, so on "
            "restart it refuses to load a copy that's older than what it already "
            "knows exists — it waits for the storage to catch up, and a container "
            "that finds itself on a stale copy will not overwrite the good backups. "
            "Nothing changes in how you use the system; it's purely a durability "
            "safeguard behind the scenes.",
        ],
    },
    {
        "version": "1.60",
        "date": "June 23, 2026",
        "summary": "The System health and Audit log pages now open with plain-language summaries — what's in the system, and what the log has been recording.",
        "changes": [
            "The System health page has a new “What's in the system” panel with "
            "everyday totals at a glance: how many staff accounts are signing in, "
            "how many people are in the directory, how many activities have been set "
            "up, how many participants have registered, and how much feedback has "
            "been collected — alongside the existing “is it healthy and fast” cards.",
            "The Audit log page now opens with an “At a glance” summary: how many "
            "actions were recorded today and in the last 7 days, the total on file, "
            "who's been the busiest this week, the most common kind of action, and "
            "what the most recent action was — so you get the shape of the activity "
            "before scrolling the full list.",
        ],
    },
    {
        "version": "1.59",
        "date": "June 23, 2026",
        "summary": "Fixed a person's page and downloads breaking when a period had activity but no score yet.",
        "changes": [
            "A staff member's “Scores over time” chart could fail to load — both on "
            "their page and in the image/PDF downloads — if one of the periods had "
            "an engagement recorded but no ratable score yet (for example, all "
            "answers left as “not applicable”). Such a period now simply shows as a "
            "gap with a “—” instead of stopping the whole chart from drawing.",
        ],
    },
    {
        "version": "1.58",
        "date": "June 23, 2026",
        "summary": "Each registered participant now answers a feedback form once — already-answered forms show as done.",
        "changes": [
            "On an activity's feedback page, any survey a registered participant has "
            "already answered now shows with a green “✓ Done” mark and can't be opened "
            "again — so the same person can't accidentally rate the same speaker or "
            "event twice (from a double-tap, the back button, or re-opening their "
            "link). Once they've answered everything, a short “you've answered all the "
            "feedback” note appears. Walk-in and anonymous responses on a shared device "
            "are unaffected — those still get a fresh form each time.",
        ],
    },
    {
        "version": "1.57",
        "date": "June 23, 2026",
        "summary": "Quickly find a staff member on the Users & roles page with a new search box.",
        "changes": [
            "The Users & roles page now has a search box above the staff list. Start "
            "typing a name, email or section and the list narrows to just the matching "
            "people as you type — handy once you have more staff than fit on one screen. "
            "Clear the box to see everyone again.",
        ],
    },
    {
        "version": "1.56",
        "date": "June 22, 2026",
        "summary": "Spot Feedback can now be reviewed faster behind the scenes, so replies and fixes come back to you sooner.",
        "changes": [
            "Admins who handle Spot Feedback now have a quicker way to pull up the "
            "current list of submissions and their replies, without exporting a file "
            "each time. Nothing changes in how you send feedback or see updates — "
            "this just shortens the loop between you flagging something and the team "
            "acting on it.",
        ],
    },
    {
        "version": "1.55",
        "date": "June 22, 2026",
        "summary": "A stronger safeguard so a restart can never quietly bring back old data.",
        "changes": [
            "We fixed the cause of a recent incident where the system briefly came "
            "back showing older information after a restart. The permanent storage "
            "the app saves to can take a few seconds to connect when the system "
            "starts up; if the app didn't wait, it mistook “not ready yet” for "
            "“nothing saved” and fell back to a built-in starter copy.",
            "Now, on every start the app first confirms the permanent storage is "
            "really connected and waits for it, and it will refuse to start on the "
            "old starter copy rather than show you stale data — so a slow "
            "connection self-corrects on the next start instead of losing recent "
            "work.",
            "It also now keeps a daily safety copy going back two weeks, on top of "
            "the frequent ones, so there's always a recent point to restore from.",
        ],
    },
    {
        "version": "1.54",
        "date": "June 22, 2026",
        "summary": "Event dates now read in plain words (no more day/month mix-ups), and a bureau activity can be saved without a resource person.",
        "changes": [
            "Every date you pick now shows in plain words — “22 Jun 2026”, with the "
            "full “Monday, 22 June 2026” spelled out underneath on the create form. "
            "Before, the date box followed your computer's region setting, so on some "
            "desktops it read 06/22 (month first) and on others 22/06 (day first), "
            "which was easy to misread. The calendar still works the same; only how "
            "the date is shown changed.",
            "When you set up a bureau-organized activity that had no resource person "
            "(a consultation, a service day, an internal activity), you can now leave "
            "the resource-person section empty — you'll still get the event review. "
            "Outside events we were invited to still need at least one resource person.",
        ],
    },
    {
        "version": "1.53",
        "date": "June 22, 2026",
        "summary": "The hidden data tables for screen readers now cover the Pulse, Participation and Written-comments charts too.",
        "changes": [
            "Following last update's Trends charts, every chart on the Pulse, "
            "Participation and Written-comments pages now also has a matching data "
            "table that's hidden on screen but read out by screen readers — so the "
            "exact figure behind each line is available to someone who can't see it. "
            "The tone-of-comments chart reads out all three shares (appreciation, "
            "areas to improve, and mixed) for each period.",
        ],
    },
    {
        "version": "1.52",
        "date": "June 22, 2026",
        "summary": "Keyboard users can skip straight to the page content, and every Trends chart now carries a hidden data table for screen readers.",
        "changes": [
            "A “Skip to content” link now appears the moment you press Tab on any "
            "page — press Enter and you jump past the menu straight to the main "
            "content, instead of tabbing through every menu item first. It stays "
            "out of sight until you need it.",
            "Every chart on the Trends page now has a matching data table that's "
            "hidden on screen but read out by screen readers, so someone who can't "
            "see the lines can still hear the exact figure for each period. (The "
            "other dashboard charts get the same treatment next.)",
        ],
    },
    {
        "version": "1.51",
        "date": "June 22, 2026",
        "summary": "Changing a staff member's email in the Directory now also updates the email they sign in with.",
        "changes": [
            "When you edit a staff member's email in the Directory, that change now "
            "carries over to their account too — so they sign in with the new email, "
            "and resetting or reactivating their account uses it as well. Until now "
            "the account quietly kept the old email, so it looked like your change "
            "had reverted. If the new email already belongs to someone else's "
            "account, the Directory still saves but the sign-in email is left "
            "unchanged, with a note explaining why.",
        ],
    },
    {
        "version": "1.50",
        "date": "June 22, 2026",
        "summary": "A new duck-race draw for the comment raffle, and certificates are now signed only by the bureau's chiefs and director.",
        "changes": [
            "The comment-raffle draw screen has a new animation to choose from: a "
            "“Duck race”. Pick it and the entries line up as rubber ducks paddling "
            "across a pond — the winner's duck pulls ahead for a photo finish — "
            "alongside the existing slot machine, prize wheel, name shuffle and "
            "lottery tumbler, with the same sound effects and confetti.",
            "When you set up a Certificate of Appearance, the “Signed by” list now "
            "offers only the people who actually sign them — Section Chiefs, "
            "Division Chiefs and the Director — instead of the whole directory, so "
            "you don't have to scroll past everyone else or keep a signature on "
            "file for staff who never sign. If an activity was already set to "
            "someone outside that list, it keeps that choice until you change it.",
        ],
    },
    {
        "version": "1.49",
        "date": "June 22, 2026",
        "summary": "Set a start-and-end date for multi-day activities, and the Certificate of Appearance is now PDF-only.",
        "changes": [
            "When you create an activity you can now give it an end date as well as "
            "a start date — for anything that runs more than one day (a three-day "
            "training, say). Leave the end date blank and it stays a single-day "
            "activity, exactly as before. The activity then shows its full run "
            "everywhere — “June 16–18, 2026” — on the sign-in page, the survey, the "
            "monitor, and the certificate.",
            "You can also fix or change an activity's dates after it's created: open "
            "its manage page and use the new “Activity dates” box. The reporting "
            "period still follows the start date, so reports keep counting the "
            "activity in the right quarter and year.",
            "The Certificate of Appearance now downloads as a PDF only. The editable "
            "PowerPoint version has been removed, so an official certificate can't be "
            "altered after it's issued.",
        ],
    },
    {
        "version": "1.48",
        "date": "June 22, 2026",
        "summary": "See how the tone of written comments has shifted over time.",
        "changes": [
            "The Written Comments page now opens with a “Tone of comments over "
            "time” chart. For each period it shows what share of comments read as "
            "appreciation, as something to improve, or as mixed (a good point and "
            "a gripe in one) — three lines that always add up to 100%, so you can "
            "see at a glance whether feedback is warming or cooling. A short "
            "plain-language line sums up the shift, and you can switch between "
            "monthly, quarterly and yearly.",
            "The same chart now appears in the page's PDF and PowerPoint "
            "downloads, with labelled axes and a caption, so it's ready to drop "
            "into a report.",
        ],
    },
    {
        "version": "1.47",
        "date": "June 22, 2026",
        "summary": "Run a comment raffle at face-to-face activities — draw a random winner on a big screen.",
        "changes": [
            "On any activity's manage page you can now switch on a “Comment "
            "raffle”. Once it's on, anyone who leaves a comment when they answer "
            "the feedback gets a short claim code on their thank-you screen — their "
            "ticket to a prize.",
            "When it's time to draw, open the full-screen draw page and pick a "
            "random winner with a bit of show: choose between a slot machine, a "
            "spinning prize wheel, a name shuffle, or a lottery tumbler — each with "
            "optional sound effects and confetti. You can draw again for more "
            "prizes, and past winners aren't drawn twice.",
            "It works for both your own activities and invited (outside) ones. For "
            "registered participants the winner's name shows on screen; for "
            "anonymous responses the winner is identified by their claim code, which "
            "they show you to collect the prize. Only face-to-face responses are "
            "entered.",
        ],
    },
    {
        "version": "1.46",
        "date": "June 21, 2026",
        "summary": "Export several activities at once, and restore several archived ones together.",
        "changes": [
            "On the activities list, click “Edit / merge”, tick the activities you "
            "want, and a new “Export selected” button downloads just those activities "
            "as a spreadsheet — handy for pulling together a report on a specific set "
            "of activities without exporting the whole list.",
            "The “Archived activities” page now has a “Select to restore” mode: tick "
            "several put-away activities and bring them all back in one click, instead "
            "of restoring them one at a time.",
        ],
    },
    {
        "version": "1.45",
        "date": "June 21, 2026",
        "summary": "Guided tours — a short, skippable walk-through of each page, plus a full written guide.",
        "changes": [
            "The first time you open a page, a short guided tour now points out the "
            "main things on it — one tip at a time, with Back, Next and Skip. It "
            "shows once per page; close it and it won't pop up again.",
            "A new “?” button at the top-right of every page lets you replay that "
            "page's tour whenever you like, or open the full written guide — a single "
            "searchable page that collects every page's walk-through in one place.",
        ],
    },
    {
        "version": "1.44",
        "date": "June 21, 2026",
        "summary": "Small accessibility and dark-mode fixes on the survey forms.",
        "changes": [
            "The optional “add a note” boxes under each survey question now carry "
            "a proper label, so people using a screen reader know what the box is "
            "for.",
            "The one-question-at-a-time view's “please answer first” warning used a "
            "fixed red that was hard to read in dark mode; it now follows your "
            "chosen theme.",
        ],
    },
    {
        "version": "1.43",
        "date": "June 21, 2026",
        "summary": "Admin pages read better on phones and in dark mode.",
        "changes": [
            "Tables on the Backups and Paper-entry pages, and the resource and "
            "speaker lists on the activity-management pages, now stack or scroll "
            "neatly on a narrow phone screen instead of running off the edge.",
            "A few faint colours on the Backups and Directory pages (a status "
            "chip and a delete-button outline) used to stay light grey in dark "
            "mode; they now follow whichever theme you've chosen.",
            "The small decorative icons on the Directory, System-health and Audit "
            "pages are now skipped by screen readers, and the disabled-remove "
            "padlock on the invited-activity page now announces what it means.",
        ],
    },
    {
        "version": "1.42",
        "date": "June 21, 2026",
        "summary": "Dark-mode and narrow-screen fixes on the official Reports page.",
        "changes": [
            "On the official Reports page, the neutral middle section of the "
            "answer-distribution bars and a couple of faint table lines used to "
            "stay light grey even in dark mode, where they glared against the dark "
            "background. They now follow whichever theme you've chosen.",
            "The small breakdown tables on that page (the respondent profile and "
            "the Citizen's Charter details) now scroll neatly on a narrow phone "
            "screen instead of being cut off at the edge.",
        ],
    },
    {
        "version": "1.41",
        "date": "June 21, 2026",
        "summary": "Tidier “nothing here yet” notes on an activity's report page.",
        "changes": [
            "On a single activity's report, the spots that say there's nothing to "
            "show yet — no demographic breakdown, no service-quality scores, or no "
            "other activities to compare against — now use the same tidy little "
            "message as the rest of the dashboard, instead of a bare line of text, "
            "so it's clear nothing is broken.",
        ],
    },
    {
        "version": "1.40",
        "date": "June 21, 2026",
        "summary": "Charts on the Trends and Participation pages now read correctly in dark mode.",
        "changes": [
            "On the Trends and Participation pages, the faint gridlines, the shaded "
            "“normal range” bands behind the charts, the progress bars and their "
            "small colour keys used to stay light-grey even in dark mode, where "
            "they glared against the dark background. They now follow whichever "
            "theme you've chosen — light, dark, or high-contrast — so the figures "
            "look right everywhere.",
            "Two faint chart labels on the Trends page (the axis titles and the "
            "“how it's computed” note) were too dark to read in dark mode; they now "
            "use the same readable shade as the rest of the page.",
        ],
    },
    {
        "version": "1.39",
        "date": "June 21, 2026",
        "summary": "Screen-reader cleanups on the Teams, Trends and Participation pages.",
        "changes": [
            "The little decorative icons and arrows on the Teams, Trends and "
            "Participation pages are now skipped by screen readers, so they no "
            "longer interrupt the reading of a unit's name or a figure with stray "
            "symbols.",
            "A unit's coaching page with no rated activities yet now shows the same "
            "tidy “nothing here yet” message as the rest of the dashboard, instead "
            "of a bare line of text.",
        ],
    },
    {
        "version": "1.38",
        "date": "June 21, 2026",
        "summary": "Better support for screen readers on the home, Pulse and People pages.",
        "changes": [
            "Profile photos across the People pages now carry the person's name, so "
            "someone using a screen reader hears who each picture is instead of a blank "
            "image.",
            "The small decorative icons on the home page and in the search box are now "
            "skipped by screen readers, so they no longer interrupt the reading of the "
            "page with meaningless graphics.",
        ],
    },
    {
        "version": "1.37",
        "date": "June 21, 2026",
        "summary": "Clearer “nothing here yet” messages and small readability fixes.",
        "changes": [
            "When a page has no data yet — no people, no activities, no responses — it now "
            "shows a tidy, consistent little message instead of a bare line of text, so it’s "
            "clear nothing is broken.",
            "Nudged one accent colour (amber) slightly darker so every colour scheme now "
            "meets the international readability standard, even on its own tinted background.",
            "Fixed the Name cleanup page so its description text shows in the proper muted "
            "style, and tidied the Sharing settings page title to match the rest.",
        ],
    },
    {
        "version": "1.36",
        "date": "June 21, 2026",
        "summary": "See your own feedback snapshot the moment you log in.",
        "changes": [
            "After signing in, a small card now pops up showing your latest rating, "
            "whether it's trending up or down compared to last quarter, where you stand "
            "among your peers, and — if there’s something worth watching — which area "
            "has the most room to grow. It appears once a day; close it to go straight "
            "to the dashboard, or choose “Don’t show daily” to turn it off.",
        ],
    },
    {
        "version": "1.35",
        "date": "June 21, 2026",
        "summary": "Tidier colours and consistent page titles across the whole dashboard.",
        "changes": [
            "Text colours for status badges (green ticks, amber warnings) and two "
            "accent colour schemes (teal and emerald) have been adjusted so they "
            "meet the international readability standard in every theme — light, "
            "dark, and high-contrast. Nothing moves; things are simply easier to "
            "read at a glance.",
            "Every dashboard page now uses the same layout pattern for its title "
            "and opening description, so the header looks and behaves consistently "
            "wherever you are in the system.",
        ],
    },
    {
        "version": "1.34",
        "date": "June 21, 2026",
        "summary": "Save and share a filtered report view — pin it under a name or copy a link.",
        "changes": [
            "When you've narrowed a dashboard or report — picked a division, a "
            "time period, or a particular view — the scope bar at the top now lets "
            "you keep it. “Copy link” copies a web address that reopens the report "
            "exactly as you've filtered it, so you can paste it into an email or "
            "chat and a colleague sees the same view. “Save view” pins the current "
            "view under a name you choose; “Saved views” then lists them for "
            "one-click return. Saved views are kept on the device you're using.",
        ],
    },
    {
        "version": "1.33",
        "date": "June 21, 2026",
        "summary": "Answer surveys with no internet — answers save on the phone and send themselves once you're back online.",
        "changes": [
            "If you submit a survey while your phone has no signal, your answers are "
            "now saved safely on the device instead of being lost — you'll see a "
            "“Saved on your device” message. The moment the phone is back online "
            "(or the next time the survey is opened), the saved answers are sent "
            "automatically, and a small counter shows how many are still waiting. "
            "This makes it practical to collect feedback at venues with weak or no "
            "internet and sync everything later. If a survey has already closed by "
            "the time a saved answer tries to send, it's flagged clearly rather than "
            "disappearing silently.",
        ],
    },
    {
        "version": "1.32",
        "date": "June 21, 2026",
        "summary": "Add the survey to your phone's home screen — and it still opens if you lose signal.",
        "changes": [
            "Surveys can now be installed like an app: open a survey link on your "
            "phone and choose “Add to Home Screen” to get an icon that opens "
            "straight back to that survey. Once you've opened a survey while "
            "online, it will keep loading even if you lose your connection — handy "
            "for collecting feedback at venues with weak signal. (Sending answers "
            "still needs a connection for now; saving them to send later is coming "
            "next.)",
        ],
    },
    {
        "version": "1.31",
        "date": "June 21, 2026",
        "summary": "Your survey progress is now saved automatically — come back and pick up where you left off.",
        "changes": [
            "If you close the survey tab or step away mid-form, your answers are "
            "saved to your browser. When you reopen the same survey link, a banner "
            "asks whether to resume your draft or start fresh — so no one has to "
            "fill in the same ratings twice. Drafts are kept for 7 days and cleared "
            "automatically once you submit.",
        ],
    },
    {
        "version": "1.30",
        "date": "June 21, 2026",
        "summary": "The monitor page now shows a live response counter that updates the moment someone submits.",
        "changes": [
            "When you open the Monitor page during an active activity, the "
            "Completed CSS number now updates in real time — no refreshing "
            "needed. A green pulse dot next to the count shows the live "
            "connection is active; it turns grey if the connection drops and "
            "reconnects automatically.",
        ],
    },
    {
        "version": "1.29",
        "date": "June 21, 2026",
        "summary": "Search now finds activities and people — not just menu pages.",
        "changes": [
            "The Ctrl-K search palette (and the search box on the home page) now "
            "looks inside your data as well as the navigation. Type an activity "
            "name, topic, organiser, or a staff member's name and the matching "
            "activities and people appear right in the results list — grouped by "
            "type, with a short description beside each one.",
        ],
    },
    {
        "version": "1.28",
        "date": "June 21, 2026",
        "summary": "One-question-at-a-time mode now waits when a follow-up note appears.",
        "changes": [
            "In the focused “one question at a time” survey view, picking a low or "
            "high rating opens a short note box for that question. The form no "
            "longer jumps ahead to the next question while that box is showing — it "
            "waits so you can type your note, then move on with Next when you're ready.",
        ],
    },
    {
        "version": "1.27",
        "date": "June 20, 2026",
        "summary": "Hover over any chart dot to see the exact value — and how it moved.",
        "changes": [
            "Every line chart on the Trends and Participation dashboards now shows a "
            "tooltip when you hover over a data point: the period label, the exact "
            "value, and how much it changed compared to the period before. A small "
            "badge at the end of each line also shows the most recent period-over-"
            "period move at a glance.",
        ],
    },
    {
        "version": "1.26",
        "date": "June 20, 2026",
        "summary": "Answer the survey one question at a time — or all at once.",
        "changes": [
            "A new “Answer one at a time” button at the top of any survey lets you "
            "switch to a focused, one-question view: one question fills the screen, "
            "with Back and Next buttons to move between them. The form auto-advances "
            "after you pick a rating, and you can switch back to the full-scroll view "
            "at any time without losing your answers.",
        ],
    },
    {
        "version": "1.25",
        "date": "June 20, 2026",
        "summary": "The survey now prompts you to explain a low rating — and celebrates a high one.",
        "changes": [
            "When you give a low score on any question, an “Add a note” box "
            "automatically opens with a prompt asking what fell short — so you "
            "can explain without hunting for the comments section.",
            "When you rate the overall quality, the comments section adapts: "
            "a low rating prompts “What could be improved?” and a high rating "
            "asks “What stood out?” so the question always matches how you felt.",
        ],
    },
    {
        "version": "1.24",
        "date": "June 20, 2026",
        "summary": "Mistakes are caught as you type — no more surprises on submit.",
        "changes": [
            "The sign-in and survey forms now tell you about a problem the moment "
            "you leave a field — a red message appears right below it saying what's "
            "wrong (for example “Please enter a valid email address” or “This field "
            "is required”). If you click Submit with anything missing or wrong, every "
            "problem lights up at once and the page scrolls to the first one, so you "
            "can fix things without having to guess what went wrong.",
        ],
    },
    {
        "version": "1.23",
        "date": "June 20, 2026",
        "summary": "Filipino now covers the full respondent journey, not just the survey form.",
        "changes": [
            "The language toggle (EN / FIL) now works on every page a respondent "
            "touches: the activity sign-in and registration form, the RA-10173 "
            "privacy notice, the combined resource-person survey, and the thank-you "
            "page after submitting — including the certificate download buttons and "
            "the back-to-activity link. The activity link tree also shows resource "
            "person and programme labels in Filipino when that language is selected.",
        ],
    },
    {
        "version": "1.22",
        "date": "June 20, 2026",
        "summary": "The survey form can now be answered in Filipino.",
        "changes": [
            "People answering a survey can now switch the whole form between "
            "English and Filipino with the “EN / FIL” buttons at the top of the "
            "page — the questions, the rating choices, and every label change "
            "language together, and the system remembers the choice for next time. "
            "The Filipino wording is a first version for the office to review and "
            "refine over time.",
        ],
    },
    {
        "version": "1.21",
        "date": "June 19, 2026",
        "summary": "Admins can now close all historical activities to paper encoding.",
        "changes": [
            "The Paper entry page now has a “Close all to encoding” button for admins. "
            "Clicking it hides all existing activities from the encode picker so encoders "
            "can no longer key in new paper slips for them — but nothing is deleted: "
            "every response still appears in all reports and dashboards as before.",
        ],
    },
    {
        "version": "1.20",
        "date": "June 19, 2026",
        "summary": "Better text colours across every page in dark mode.",
        "changes": [
            "Every page now uses text colours that adapt to the theme you have "
            "chosen. Warning banners, status flags, chart labels, action buttons, "
            "and category badges all flip to a readable shade in dark mode instead "
            "of showing dark text on a dark background.",
        ],
    },
    {
        "version": "1.19",
        "date": "June 19, 2026",
        "summary": "Filter written comments by scope and period — and better dark-mode colours.",
        "changes": [
            "The Written Comments page now has the same Scope and Period selectors "
            "as the other reports — so you can narrow the comments to a specific "
            "division, section, or time period without going back to the reports hub.",
            "Fixed a dark-mode display issue on activity scorecards where the big "
            "numbers and some verdict labels were hard to see against the card "
            "background — they now use the right colours in every theme.",
        ],
    },
    {
        "version": "1.18",
        "date": "June 18, 2026",
        "summary": "A lighter, faster system behind the scenes.",
        "changes": [
            "The dashboards and reports now run on a fraction of the memory they "
            "used to, and the figures behind them are prepared noticeably faster — "
            "so pages stay quick and the system keeps more headroom as the records "
            "keep growing. Nothing changes in what you see; it just runs leaner.",
        ],
    },
    {
        "version": "1.17",
        "date": "June 18, 2026",
        "summary": "Smoother comment sorting and a one-click “save both” when editing activities.",
        "changes": [
            "On the written-comments page, re-sorting a comment (Appreciated, Mixed "
            "or To improve) no longer reloads the whole page — the comment updates "
            "right where it is and shows a “✓ re-tagged” mark, so you can see at a "
            "glance what you've already done and never lose your place.",
            "When editing activities, you can now type a new name AND pick a new "
            "section, then click “Apply all changes” once to save both together — no "
            "more saving the rename, reopening, and re-filing separately. A single "
            "undo reverses both.",
        ],
    },
    {
        "version": "1.16",
        "date": "June 18, 2026",
        "summary": "Your data is now saved permanently and survives every system update.",
        "changes": [
            "The system now keeps your information on permanent storage, so nothing "
            "is lost when the app updates or restarts — edits like renaming and "
            "merging activities are saved continuously and brought back automatically.",
        ],
    },
    {
        "version": "1.15",
        "date": "June 18, 2026",
        "summary": "Jump straight to a page in the activities list — and search it more easily.",
        "changes": [
            "The activities list can run to hundreds of pages, so the bottom of the "
            "list now has a “Jump to” box: type a page number, press Go, and you're "
            "there — no more clicking “Older” one page at a time.",
            "A search box now also sits at the foot of the list, with a reminder that "
            "searching by activity or organiser name is the quickest way to find what "
            "you're after.",
        ],
    },
    {
        "version": "1.14",
        "date": "June 18, 2026",
        "summary": "Editing activities keeps your place in the list.",
        "changes": [
            "When you rename, merge, re-file or archive activities from the "
            "“Edit & merge activities” list, you now stay on the same page you "
            "were working on — with the same sort and search — instead of being "
            "sent back to the top of the first page each time.",
        ],
    },
    {
        "version": "1.13",
        "date": "June 18, 2026",
        "summary": "A faster home page, especially right after the app wakes up.",
        "changes": [
            "The home page now loads its summary numbers and activity lists "
            "noticeably faster — most noticeable the first time you open it after "
            "the system has been idle. Behind the scenes the app no longer re-reads "
            "every past response just to show this week's totals.",
        ],
    },
    {
        "version": "1.12",
        "date": "June 18, 2026",
        "summary": "Cleaner one-activity downloads — a proper scorecard instead of an empty timeline.",
        "changes": [
            "When you download a resource person's report for a single activity, it no "
            "longer shows a “scores over time” chart with just one dot — which never "
            "made sense for a one-off session. Instead it leads with a clear scorecard: "
            "the score, the rating band, how many people rated, and how it compares to "
            "the bureau average.",
            "Fixed the comparison on those single-activity downloads: it now measures "
            "against the real bureau average instead of comparing the session to itself "
            "(which always read as “right around average”).",
        ],
    },
    {
        "version": "1.11",
        "date": "June 18, 2026",
        "summary": "See how a resource person did at one specific activity — with its own page and downloads.",
        "changes": [
            "On a person's page you'll now find a “Per-activity engagements” list — "
            "every activity they spoke at since June 15, 2026, marked as either an "
            "invited (outside) activity or a bureau-led one.",
            "Tap any activity to open its own scorecard for that person: their rating "
            "for that session, what stood out, the comments people left, and a short "
            "coaching note — separate from their overall all-time report.",
            "Each of those per-activity scorecards can be downloaded on its own as a "
            "PDF, PowerPoint, Excel sheet, or image.",
        ],
    },
    {
        "version": "1.10",
        "date": "June 17, 2026",
        "summary": "The home “Recent activities” list now focuses on the last 7 days.",
        "changes": [
            "The “Recent activities” list on the home page now shows only "
            "activities from the last 7 days (and any still to come), so it stays "
            "even shorter and more current — just this week's work at a glance.",
        ],
    },
    {
        "version": "1.9",
        "date": "June 17, 2026",
        "summary": "The home “Recent activities” list now focuses on the last 30 days.",
        "changes": [
            "The “Recent activities” list on the home page now shows only "
            "activities from the last 30 days (and any still to come), so it stays "
            "short and current instead of filling up with older items.",
        ],
    },
    {
        "version": "1.8",
        "date": "June 17, 2026",
        "summary": "Admins can now archive any activity right from the home page.",
        "changes": [
            "If you're an admin, “Your recent activities” on the home page now shows "
            "every recent activity across the office — not just the ones you set up — "
            "so you can Archive any standalone activity in one tap.",
            "The “Archived activities” page now lists everything that's been put away, "
            "including older items that weren't tied to a person, so an admin can "
            "restore any of them.",
        ],
    },
    {
        "version": "1.7",
        "date": "June 17, 2026",
        "summary": "Archive a standalone activity instead of deleting it — and restore it any time.",
        "changes": [
            "If you created an activity that should no longer count — for example a "
            "speaker rating you set up by mistake or one that ended with no responses "
            "— you can now Archive it straight from “Your recent activities” on the "
            "home page. It disappears from every list, feed and total at once.",
            "Nothing is deleted: a new “Archived activities” page lists everything "
            "you've put away, and one tap restores any of them, fully intact.",
        ],
    },
    {
        "version": "1.6",
        "date": "June 17, 2026",
        "summary": "Easier list editing, clearer speaker sections, and your own friendly activity links.",
        "changes": [
            "When you're tidying up the activities list, the “Edit / merge”, "
            "“Expand all” and “Collapse all” buttons now stay on screen as you "
            "scroll, so you no longer have to scroll back to the top to use them.",
            "On the single combined survey, each speaker now stands out clearly — "
            "with a coloured stripe down the side and a “Speaker 1 of 3” label — so "
            "it's obvious where one section ends and the next begins.",
            "You can now give an activity a short, friendly web link of your own "
            "(for example “…/e/les-quezon-june”) instead of the long random one, "
            "making it easier to share — and the original link and any QR codes "
            "you've already printed keep working.",
        ],
    },
    {
        "version": "1.5",
        "date": "June 17, 2026",
        "summary": "Clearer survey wording, easier speaker ratings, and a fuller home page.",
        "changes": [
            "The combined survey for invited activities now gently guides you with "
            "ready-made prompts again, so it's easier to know what to write.",
            "The box that used to say “Honorific” now simply says “Title”, so it's "
            "clear what to put there.",
            "The home page now also shows activities that are still collecting "
            "speaker ratings even when there's no formal event attached, so nothing "
            "in progress gets missed.",
        ],
    },
    {
        "version": "1.4",
        "date": "June 17, 2026",
        "summary": "Manage the activities you were invited to, and clearer feedback comments.",
        "changes": [
            "Activities run by an outside group — where your staff took part only as "
            "resource persons — now keep their name and have their own page where you "
            "can re-print the QR codes, change when feedback is open, add or rename "
            "speakers, and close or archive the activity once it's done.",
            "For those invited activities, the single combined QR code now opens ONE "
            "page where a person can rate every speaker and submit just once — and "
            "they can tick “I didn't attend this one” to skip any session they missed.",
            "You can now follow responses to invited activities from the Monitor — how "
            "many answers came in, when, and the overall mix of who replied — kept "
            "fully anonymous, with no names shown.",
            "The written-comments report is easier to read: it tells the story in "
            "words instead of long tallies, and a comment that is both praise and a "
            "suggestion (“great session, but the room was cold”) now correctly appears "
            "under both “what people appreciated” and “what to improve”.",
        ],
    },
    {
        "version": "1.3",
        "date": "June 17, 2026",
        "summary": "Frame profile photos just the way you want them.",
        "changes": [
            "When you add or change a staff member's profile photo, you can now "
            "zoom in and drag the picture to frame it nicely inside the round "
            "avatar — no more faces getting cut off or sitting off-centre.",
        ],
    },
    {
        "version": "1.2",
        "date": "June 17, 2026",
        "summary": "Tidier feedback and activity tools, plus speakers shown on activity cards.",
        "changes": [
            "Once your Spot Feedback is finished, you can now tuck it into an "
            "“Archived” section to keep your feedback list clean — and bring it "
            "back any time.",
            "Fixing or merging activity names is easier to find under a new "
            "“Edit & merge activities” menu item, and a friendly green message "
            "now confirms when a change goes through.",
            "Activity cards on the home page now show who the speakers or "
            "resource persons are.",
        ],
    },
    {
        "version": "1.1",
        "date": "June 17, 2026",
        "summary": "Version tracking starts here, plus recent quality-of-life upgrades.",
        "changes": [
            "The sign-in screen now shows a version number so everyone knows "
            "which build of the system they are using.",
            "Times and dates now show in Philippine time, so the activity log "
            "matches your watch instead of running hours behind.",
            "When you send Spot Feedback you now get a friendly “we heard you” "
            "reply, can follow its status, and see a bell notification when "
            "there is an update for you.",
            "You can now personalise the look — pick an accent colour, light or "
            "dark mode, and text size — and the Equity in Health logo now "
            "appears across the system.",
            "The home page now shows a quick strip of your recent activities.",
        ],
    },
]
