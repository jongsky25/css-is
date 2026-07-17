"""Lightweight English ↔ Filipino i18n for the public survey form.

SCOPE: all respondent-facing pages: the survey form, the event link-tree
(registration + rating links), the thanks page, and the combined /seq form.
The admin/staff UI stays in English.

WHY THIS FILE EXISTS: so the bureau can review and refine every Filipino string
in ONE place. English remains the source of truth in app.py (the question
constants ARTA_TEXT / B_TEXT / scales live there, owned by the bureau); this
module only adds the Filipino counterparts plus the static UI strings.

TRANSLATION STATUS: SQD items use the official ARTA Harmonized CSM Tagalog
wording; everything else is a plain-language DRAFT marked below — the office
should review and tighten the wording before it is considered final.

HOW IT IS USED:
  - app.survey_spec(ctx, lang) selects the *_FIL maps when lang == "fil".
  - templates call the Jinja global  t('slug', lang)  for static chrome.
  - app.pick(request) decides the language from the `lang` cookie (then the
    Accept-Language header, then English).
"""
from __future__ import annotations

from markupsafe import Markup

LANGS = ("en", "fil")
DEFAULT = "en"


def pick(request) -> str:
    """Resolve the active language for a request: cookie → Accept-Language → en."""
    c = request.cookies.get("lang", "")
    if c in LANGS:
        return c
    al = (request.headers.get("accept-language", "") or "").lower()
    if "tl" in al or "fil" in al:
        return "fil"
    return DEFAULT


# ---------------------------------------------------------------------------
# Survey CONTENT — Filipino counterparts of the English constants in app.py.
# Same keys; same {subject} placeholder. Numeric scale VALUES never change —
# only the labels — so stored answers are identical across languages.
# ---------------------------------------------------------------------------

# SQD items — official ARTA Harmonized CSM Tagalog wording.
ARTA_TEXT_FIL = {
    "SQD0": "Nasiyahan ako sa serbisyo na aking natanggap sa napuntahang opisina.",
    "SQD1": "Makatuwiran ang oras na aking ginugol para sa pagproseso ng aking transaksyon.",
    "SQD2": "Ang opisina ay sumunod sa mga kinakailangan at hakbang ng transaksyon base sa "
            "impormasyong ibinigay.",
    "SQD3": "Ang mga hakbang (kasama na ang pagbabayad) na aking ginawa para sa aking "
            "transaksyon ay madali at simple.",
    "SQD4": "Mabilis at madali kong nahanap ang impormasyon tungkol sa aking transaksyon "
            "mula sa opisina o sa website nito.",
    "SQD5": "Makatuwiran ang halagang aking binayaran para sa aking transaksyon.",
    "SQD6": 'Pakiramdam ko ay patas ang opisina sa lahat, o "walang palakasan", sa aking '
            "transaksyon.",
    "SQD7": "Magalang akong trinato ng mga tauhan, at handa silang tumulong sa akin.",
    "SQD8": "Nakuha ko ang aking kailangan mula sa opisina, o naipaliwanag nang sapat ang "
            "aking hiling.",
}

# SERVQUAL items (Types 2 & 3) — keep the {subject} placeholder. DRAFT.
B_TEXT_FIL = {
    "B1": "Naihatid ni/ng {subject} ang sesyon ayon sa ipinangako at inanunsyo.",
    "B2": "Ang nilalaman mula kay/sa {subject} ay tumpak at maaasahan.",
    "B3": "Sinunod ni/ng {subject} ang iskedyul at programa.",
    "B4": "Sa kabuuan, maaasahan ang naging pagganap ni/ng {subject}.",
    "B5": "Si/Ang {subject} ay bukas at handang tumugon sa mga katanungan at pangangailangan.",
    "B6": "Si/Ang {subject} ay maalam at mahusay sa paksa.",
    "B7": "Si/Ang {subject} ay malinaw na nakapag-usap at nagbigay ng kumpiyansa.",
    "B8": "Si/Ang {subject} ay nagbigay ng maingat na atensyon sa mga kalahok.",
    "B9": "Ang mga materyales, lugar, at presentasyon ay angkop at malinaw.",
}
A_TEXT_FIL = "Bago ang kaganapang ito, gaano kataas ang iyong inaasahan kay/sa {subject}?"  # DRAFT
C_TEXT_FIL = "Sa kabuuan, paano mo iri-rate ang kalidad ni/ng {subject}?"  # DRAFT

# RA-10173 consent notice template — format(months=N) before use.  DRAFT
CONSENT_TMPL_FIL = (
    "Kinokolekta namin ang inyong pangalan, email, at (opsyonal) numero ng kontak "
    "lamang upang kumpirmahin ang inyong pagdalo sa aktibidad na ito at, kung "
    "kinakailangan, upang subaybayan ang inyong puna. Ang inyong mga rating ay "
    "naka-imbak nang hiwalay at sinusuri nang hindi nagpapakilala. Ang inyong "
    "personal na impormasyon ay itatago sa loob ng {months} buwan mula sa petsa "
    "na pumayag kayo at pagkatapos ay permanenteng mabubura, habang ang inyong "
    "mga anonymous na rating ay mananatili. Ibinibigay ninyo ang impormasyong ito "
    "nang kusang-loob ayon sa Data Privacy Act ng 2012 (RA 10173) at maaari "
    "kayong humiling ng access sa o pagtanggal ng inyong mga detalye sa "
    "pamamagitan ng pakikipag-ugnayan sa BLHSD."
)

# Scale labels — same values, Filipino labels. DRAFT.
LIKERT5_FIL = [(5, "Lubos na sang-ayon"), (4, "Sang-ayon"), (3, "Hindi tiyak"),
               (2, "Hindi sang-ayon"), (1, "Lubos na hindi sang-ayon")]
OSQ4_FIL = [(4, "Napakahusay"), (3, "Mahusay"), (2, "Katamtaman"), (1, "Mahina")]

# Quick-pick comment chips — order and groups mirror app.REMARK_CHIPS. DRAFT.
REMARK_CHIPS_FIL = {
    "servqual": [
        ("Maalam", None), ("Handa", None), ("Nakaka-engganyo", None),
        ("Malinaw at madaling sundan", "clarity"), ("Matulungin", None),
        ("Maayos", None), ("Nagsimula sa oras", "timing"),
        ("Praktikal at kapaki-pakinabang", None), ("Lumampas sa oras", "timing"),
        ("Gusto ng mas maraming Q&A", None), ("Mahirap sundan", "clarity"),
        ("Pwedeng pagbutihin ang lugar", None),
    ],
    "arta": [
        ("Mabilis na serbisyo", "speed"), ("Magalang na tauhan", None),
        ("Malinaw na panuto", "clarity"), ("Makatuwirang bayad", None),
        ("Madaling proseso", "process"), ("Mahabang paghihintay", "speed"),
        ("Masyadong maraming hakbang", "process"), ("Malabong kinakailangan", "clarity"),
        ("Mahirap hanapin ang impormasyon", None),
    ],
}


# ---------------------------------------------------------------------------
# Static UI chrome (slug -> {en, fil}). The English value MUST match the text
# currently in the template byte-for-byte, so the English render is unchanged.
# Filipino values below are DRAFT — office to refine.
# ---------------------------------------------------------------------------
UI = {
    # Group headings (survey_spec)
    "grp_arta": {
        "en": "Service Quality Dimensions (1 = Strongly Disagree … 5 = Strongly Agree)",
        "fil": "Mga Sukatan ng Kalidad ng Serbisyo (1 = Lubos na Hindi Sang-ayon … 5 = Lubos na Sang-ayon)",
    },
    "grp_expectation": {"en": "Expectation", "fil": "Inaasahan"},
    "grp_experience": {
        "en": "Your experience (1 = strongly disagree … 7 = strongly agree)",
        "fil": "Ang iyong karanasan (1 = lubos na hindi sang-ayon … 7 = lubos na sang-ayon)",
    },
    "grp_overall": {"en": "Overall", "fil": "Sa kabuuan"},

    # Page titles (rating.html)
    "title_service": {"en": "Service feedback", "fil": "Puna sa serbisyo"},
    "title_event": {"en": "Event feedback", "fil": "Puna sa kaganapan"},
    "title_rp": {"en": "Resource-person feedback", "fil": "Puna sa tagapagsalita"},

    # Intro line pieces
    "q_required_note": {
        "en": "all questions are required unless marked optional.",
        "fil": "lahat ng tanong ay kailangang sagutin maliban kung minarkahang opsyonal.",
    },

    # Served-by (rarely shown publicly, translated for completeness)
    "served_q": {"en": "Who served you?", "fil": "Sino ang tumulong sa iyo?"},
    "served_none": {"en": "— not sure / prefer not to say —",
                    "fil": "— hindi sigurado / ayaw sabihin —"},

    # Demographics
    "about_you": {"en": "About you", "fil": "Tungkol sa iyo"},
    "sex": {"en": "Sex", "fil": "Kasarian"},
    "affiliation": {"en": "Affiliation", "fil": "Kaugnayan"},
    "select": {"en": "Select…", "fil": "Pumili…"},
    "male": {"en": "Male", "fil": "Lalaki"},
    "female": {"en": "Female", "fil": "Babae"},
    "non_doh": {"en": "Non-DOH", "fil": "Hindi-DOH"},

    # Scale + items
    "na": {"en": "Not applicable", "fil": "Hindi naaangkop"},
    "lowest": {"en": "lowest", "fil": "pinakamababa"},
    "highest": {"en": "highest", "fil": "pinakamataas"},
    "note_ph": {"en": "Add a note about this (optional)",
                "fil": "Magdagdag ng puna tungkol dito (opsyonal)"},

    # Comments block
    "comments": {"en": "Comments &amp; suggestions", "fil": "Mga puna at mungkahi"},
    "optional": {"en": "(optional)", "fil": "(opsyonal)"},
    "chips_hint": {"en": "Tap up to 3 suggestions to add them, or write your own below:",
                   "fil": "Pindutin ang hanggang 3 mungkahi upang idagdag, o sumulat ng sarili mo sa ibaba:"},
    "remarks_ph": {"en": "Anything you'd like to add in your own words?",
                   "fil": "May nais ka pa bang idagdag sa sarili mong salita?"},

    # Skip-logic prompts (rating.html)
    "note_low_ph": {
        "en": "What specifically fell short? (optional)",
        "fil": "Ano ang hindi naging sapat? (opsyonal)",
    },
    "note_high_ph": {
        "en": "What worked well here? (optional)",
        "fil": "Ano ang naging maganda dito? (opsyonal)",
    },
    "add_note_lbl": {"en": "Add a note", "fil": "Magdagdag ng puna"},
    "remove_note_lbl": {"en": "Remove note", "fil": "Alisin ang puna"},
    "branch_improve": {
        "en": "Your feedback helps us improve — what could be better?",
        "fil": "Ang inyong puna ay tumutulong sa amin na mapabuti — ano ang pwedeng mas gawing mabuti?",
    },
    "branch_great": {
        "en": "Glad to hear it! What stood out for you?",
        "fil": "Masaya kaming marinig iyon! Ano ang namumukod-tangi para sa iyo?",
    },
    "remarks_low_ph": {
        "en": "What specifically could be improved? (optional)",
        "fil": "Ano ang tiyak na maaaring mapabuti? (opsyonal)",
    },
    "remarks_high_ph": {
        "en": "What did you like most? (optional)",
        "fil": "Ano ang pinaka-nagustuhan mo? (opsyonal)",
    },

    # Conversational mode
    "conv_toggle_on":  {"en": "Answer one at a time →", "fil": "Isa-isang sagutin →"},
    "conv_toggle_off": {"en": "← Show all", "fil": "← Ipakita lahat"},
    "conv_prev":       {"en": "← Back", "fil": "← Bumalik"},
    "conv_next":       {"en": "Next →", "fil": "Susunod →"},
    "conv_step_lbl":   {"en": "Question", "fil": "Tanong"},
    "conv_of":         {"en": "of", "fil": "ng"},
    "conv_required":   {
        "en": "Please select an answer to continue.",
        "fil": "Mangyaring pumili ng sagot upang magpatuloy.",
    },

    # Submit
    "submit": {"en": "Submit my answers", "fil": "Isumite ang aking mga sagot"},
    "anonymous": {"en": "Your answers are anonymous.",
                  "fil": "Ang iyong mga sagot ay hindi nagpapakilala."},

    # Not-found empty state
    "nf_title": {"en": "Survey not found", "fil": "Hindi natagpuan ang survey"},
    "nf_body": {
        "en": "This QR code doesn't match any saved survey. Please ask the event "
              "organizer for a fresh link or QR code.",
        "fil": "Ang QR code na ito ay hindi tumutugma sa anumang naka-save na survey. "
               "Mangyaring humingi ng bagong link o QR code sa organisador ng kaganapan.",
    },

    # Closed / not-yet door (closed.html)
    "closed_title": {"en": "This survey has closed", "fil": "Ang survey na ito ay sarado na"},
    "notyet_title": {"en": "This survey isn't open yet",
                     "fil": "Hindi pa bukas ang survey na ito"},
    "notyet_body_pre": {"en": "Feedback for", "fil": "Ang pagpuna para sa"},
    "closed_body_pre": {"en": "The feedback period for", "fil": "Ang panahon ng pagpuna para sa"},
    "closed_body_post": {"en": "has ended — thank you for your interest.",
                         "fil": "ay tapos na — salamat sa iyong interes."},
    "notyet_body_post": {"en": "hasn't started accepting responses.",
                         "fil": "ay hindi pa tumatanggap ng mga sagot."},
    "opens_lbl": {"en": "Opens", "fil": "Bubukas"},
    "closed_lbl": {"en": "Closed", "fil": "Sarado"},
    "closed_help": {
        "en": "If you believe this is a mistake, please contact the organizing "
              "section or the event organizer.",
        "fil": "Kung sa tingin mo ay may pagkakamali, mangyaring makipag-ugnayan sa "
               "namamahalang seksyon o sa organisador ng kaganapan.",
    },

    # Header language toggle
    "lang_aria": {"en": "Language", "fil": "Wika"},

    # ---------------------------------------------------------------------------
    # Thanks page (thanks.html)
    # ---------------------------------------------------------------------------
    "thanks_title": {"en": "Thank you — CSS-IS", "fil": "Salamat — CSS-IS"},
    "thanks_h1": {"en": "✓ Thank you!", "fil": "✓ Salamat!"},
    "thanks_rp_feedback_for": {"en": "Your feedback for", "fil": "Naitala ang inyong puna para sa"},
    "thanks_rp_person": {"en": "resource person", "fil": "tagapagsalita"},
    "thanks_rp_persons": {"en": "resource persons", "fil": "mga tagapagsalita"},
    "thanks_rp_was_recorded": {"en": "was recorded.", "fil": "ay naitala."},
    "thanks_rp_none": {"en": "No answers were submitted.", "fil": "Walang mga sagot na naisumite."},
    "thanks_recorded_pre": {"en": "Your response was recorded", "fil": "Naitala ang inyong sagot"},
    "thanks_recorded_for": {"en": "for", "fil": "para sa"},
    "thanks_anon_note": {
        "en": "Your answers are anonymous and feed into BLHSD's service-quality "
              "reports, helping improve future services and events.",
        "fil": "Ang inyong mga sagot ay hindi nagpapakilala at nakakatulong sa mga ulat ng kalidad "
               "ng serbisyo ng BLHSD, na nagpapabuti ng mga susunod na serbisyo at kaganapan.",
    },
    "thanks_continue": {"en": "Continue to the next survey →", "fil": "Magpatuloy sa susunod na survey →"},
    "thanks_all_done_event": {
        "en": "All done — thank you for completing the feedback! 🎉",
        "fil": "Tapos na — salamat sa pagkumpleto ng feedback! 🎉",
    },
    "thanks_cert_heading": {
        "en": "🎖️ Your Certificate of Appearance is ready",
        "fil": "🎖️ Handa na ang inyong Sertipiko ng Pagdalo",
    },
    "thanks_cert_pdf": {"en": "Download PDF", "fil": "I-download ang PDF"},
    "thanks_back_activity": {"en": "← Back to the activity page", "fil": "← Bumalik sa pahina ng aktibidad"},
    "thanks_seq_done": {
        "en": "All done — that was the last one in this set. 🎉",
        "fil": "Tapos na — iyon ang huli sa seryeng ito. 🎉",
    },
    "thanks_back_list": {"en": "← Back to the list", "fil": "← Bumalik sa listahan"},

    # ---------------------------------------------------------------------------
    # Offline capture (PWA Phase 2 — strings used by app.js via window.OFFLINE_I18N)
    # ---------------------------------------------------------------------------
    "offline_saved_h1": {"en": "✓ Saved on your device", "fil": "✓ Nai-save sa inyong device"},
    "offline_saved_msg": {
        "en": "You're offline, so your answers are saved on this device and will be "
              "sent automatically the moment you're back online.",
        "fil": "Wala kayong koneksyon, kaya nai-save ang inyong mga sagot sa device na ito "
               "at awtomatikong ipapadala sa sandaling bumalik kayo online.",
    },
    "offline_waiting": {"en": "waiting to send", "fil": "naghihintay na ipadala"},
    "offline_sending": {"en": "Sending saved responses…", "fil": "Ipinapadala ang mga naka-save na sagot…"},
    "offline_sent_one": {"en": "Saved response sent.", "fil": "Naipadala ang naka-save na sagot."},
    "offline_sent_many": {"en": "Saved responses sent.", "fil": "Naipadala ang mga naka-save na sagot."},
    "offline_failed": {
        "en": "couldn't be sent (the survey has closed)",
        "fil": "hindi naipadala (sarado na ang survey)",
    },
    "offline_failed_label": {"en": "Couldn't send", "fil": "Hindi naipadala"},
    "offline_discard": {"en": "Discard", "fil": "Itapon"},

    # ---------------------------------------------------------------------------
    # Combined /seq form (combined_form.html)
    # ---------------------------------------------------------------------------
    "cf_closed_title": {"en": "This feedback has closed", "fil": "Sarado na ang feedback na ito"},
    "cf_closed_body": {
        "en": "The feedback period for this activity has ended — thank you for your interest.",
        "fil": "Natapos na ang panahon ng feedback para sa aktibidad na ito — salamat sa inyong interes.",
    },
    "cf_rp_heading_intro": {
        "en": "Please rate each resource person below.",
        "fil": "Mangyaring i-rate ang bawat tagapagsalita sa ibaba.",
    },
    "cf_there_is": {"en": "There is", "fil": "Mayroon"},
    "cf_there_are": {"en": "There are", "fil": "Mayroon"},
    "cf_speaker_s": {"en": "speaker", "fil": "tagapagsalita"},
    "cf_speakers_p": {"en": "speakers", "fil": "mga tagapagsalita"},
    "cf_tick_pre": {"en": "tick", "fil": "lagyan ng tsek ang"},
    "cf_tick_post": {
        "en": "on any you missed, then submit once at the bottom.",
        "fil": "para sa mga napalampas ninyo, pagkatapos isumite nang isang beses sa ibaba.",
    },
    "cf_skip": {"en": "I didn't attend this one", "fil": "Hindi ko ito dinaluhan"},
    "cf_speaker_label": {"en": "Speaker", "fil": "Tagapagsalita"},
    "cf_of": {"en": "of", "fil": "ng"},
    "cf_rp_default": {"en": "Resource person", "fil": "Tagapagsalita"},
    "cf_comments_label": {
        "en": "Comments about this resource person",
        "fil": "Mga puna tungkol sa tagapagsalitang ito",
    },

    # ---------------------------------------------------------------------------
    # Event link-tree / registration (link_tree.html)
    # ---------------------------------------------------------------------------
    "lt_nf_title": {"en": "Event not found", "fil": "Hindi nahanap ang kaganapan"},
    "lt_nf_body": {
        "en": "This link is no longer valid. Please check with the event organizer.",
        "fil": "Hindi na wasto ang link na ito. Makipag-ugnayan sa organisador ng kaganapan.",
    },
    "lt_thanks_pre": {"en": "Thanks", "fil": "Salamat"},
    "lt_thanks_post": {
        "en": "! Your attendance is recorded. Everything for this activity is below.",
        "fil": "! Naitala ang inyong pagdalo. Nasa ibaba ang lahat para sa aktibidad na ito.",
    },
    "lt_not_you": {"en": "Not", "fil": "Hindi ikaw si"},
    "lt_start_fresh": {"en": "Start fresh on this device →", "fil": "Magsimulang muli sa device na ito →"},
    "lt_resource_persons": {"en": "Resource persons", "fil": "Mga tagapagsalita"},
    "lt_programme_resources": {"en": "Programme &amp; resources", "fil": "Programa at mga materyales"},
    "lt_unlocked": {
        "en": "🎉 Unlocked — thanks for your feedback",
        "fil": "🎉 Naka-unlock na — salamat sa inyong puna",
    },
    "lt_locked_resource": {"en": "more resource", "fil": "pang materyales"},
    "lt_locked_resources_pl": {"en": "more resources", "fil": "pang mga materyales"},
    "lt_locked_suffix": {
        "en": "(e.g. your certificate) unlock once you finish the feedback below.",
        "fil": "(hal. ang inyong sertipiko) ay ia-unlock kapag natapos ang feedback sa ibaba.",
    },
    "lt_rate_this": {"en": "Rate this activity", "fil": "I-rate ang aktibidad na ito"},
    "lt_n_of": {"en": "of", "fil": "ng"},
    "lt_each_hint": {
        "en": "Each link opens one short survey. Finish one and you'll be guided to the next.",
        "fil": "Ang bawat link ay nagbubukas ng isang maikling survey. Tapusin ang isa at gagabayan ka sa susunod.",
    },
    "lt_done": {"en": "Done", "fil": "Tapos na"},
    "lt_all_done": {
        "en": "Thank you — you've answered all the feedback for this activity.",
        "fil": "Salamat — nasagot mo na ang lahat ng feedback para sa aktibidad na ito.",
    },
    "lt_no_forms": {
        "en": "No rating forms are attached to this event yet.",
        "fil": "Wala pang mga form ng rating na nakalakip sa kaganapang ito.",
    },
    "lt_cert_heading": {"en": "🎖️ Certificate of Appearance", "fil": "🎖️ Sertipiko ng Pagdalo"},
    "lt_is_this_you": {"en": "Is this you?", "fil": "Ikaw ba ito?"},
    "lt_confirm_someone": {"en": "Someone", "fil": "Isang tao"},
    "lt_confirm_named": {"en": "named", "fil": "na nagngangalang"},
    "lt_confirm_registered": {
        "en": "is already registered with the email",
        "fil": "ay nakarehistrong gamit ang email",
    },
    "lt_confirm_but": {"en": "but you entered the name", "fil": "ngunit ipinasok mo ang pangalan"},
    "lt_confirm_q": {"en": "Are you the same person?", "fil": "Ikaw ba ang iyon?"},
    "lt_yes_me": {"en": "Yes, that's me — continue", "fil": "Oo, ako iyon — magpatuloy"},
    "lt_no_diff": {
        "en": "No, I'm a different person — register me separately",
        "fil": "Hindi, isa akong ibang tao — irehistro ako nang hiwalay",
    },
    "lt_shared_email": {
        "en": '"A different person" is for a shared email (e.g. an office inbox) used by more than one attendee.',
        "fil": '"Ibang tao" ay para sa isang pinagsamang email (hal. opisinang inbox) na ginagamit ng higit sa isang kalahok.',
    },
    "lt_sign_in": {"en": "Sign in to give your feedback", "fil": "Mag-sign in para ibigay ang inyong puna"},
    "lt_title_lbl": {"en": "Title", "fil": "Titulo"},
    "lt_name_lbl": {"en": "Full name", "fil": "Buong pangalan"},
    "lt_email_lbl": {"en": "Email", "fil": "Email"},
    "lt_dupe_notice": {
        "en": "This email is already registered. Submitting again just takes you back to "
              "your existing registration — you won't create a duplicate.",
        "fil": "Nakarehistrong na ang email na ito. Ang muling pagsusumite ay magbabalik sa inyong "
               "umiiral na rehistrasyon — hindi ito lilikha ng duplicate.",
    },
    "lt_contact_lbl": {"en": "Contact number", "fil": "Numero ng kontak"},
    "lt_cert_help": {
        "en": "Used to address you on your certificate, if the activity issues one.",
        "fil": "Ginagamit para tugunan kayo sa inyong sertipiko, kung naglalabas ang aktibidad nito.",
    },
    "lt_consent_label": {
        "en": "I have read the notice above and I consent to BLHSD collecting and "
              "processing my personal details for this purpose.",
        "fil": "Nabasa ko na ang paunawa sa itaas at sumasang-ayon ako na mangolekta at "
               "magproseso ang BLHSD ng aking personal na mga detalye para sa layuning ito.",
    },
    "lt_consent_submit": {
        "en": "I consent — continue to feedback",
        "fil": "Sumasang-ayon ako — magpatuloy sa feedback",
    },
    "lt_label_event": {"en": "Event review", "fil": "Pagtatasa ng kaganapan"},
    "lt_label_speaker": {"en": "Speaker review", "fil": "Pagtatasa ng tagapagsalita"},
    "lt_kind_program": {"en": "Programme / Agenda", "fil": "Programa / Agenda"},
    "lt_kind_slides": {"en": "Slides / Materials", "fil": "Mga Slide / Materyales"},
    "lt_kind_registration": {"en": "Registration", "fil": "Pagpaparehistro"},
    "lt_kind_recording": {"en": "Recording", "fil": "Rekording"},
    "lt_kind_certificate": {"en": "Certificate", "fil": "Sertipiko"},
    "lt_kind_info": {"en": "Info", "fil": "Impormasyon"},
    "lt_kind_link": {"en": "Link", "fil": "Link"},
}


def t(key: str, lang: str = DEFAULT):
    """Look up a static UI string; fall back to English, then to the key itself.

    Returns Markup (an already-safe string) so the English text renders
    byte-for-byte as it did when it was hardcoded in the templates — i.e. a
    literal apostrophe stays "'" rather than being auto-escaped to "&#39;".
    CONSEQUENCE: values in UI must be HTML-ready — pre-escape any `&`, `<`, `>`
    (these strings are trusted developer constants, never user input).
    """
    entry = UI.get(key)
    if not entry:
        return Markup(key)
    return Markup(entry.get(lang) or entry.get("en") or key)
