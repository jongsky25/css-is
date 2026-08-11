"""Type-2 (activity) forms must not read as though they rate a PERSON.

Both SERVQUAL forms used to share one set of statements with a {subject} slot,
so an activity form dropped its own title into sentences written about a human
("15th Learning Exchange Session was knowledgeable and competent in the
subject"). Type 2 now has its own wording. These lock:
  * Type 2 renders the activity wording, never a person phrasing, and never
    repeats the activity's title (that lives in the form header);
  * Type 3 wording is untouched, and a Type-3 form with no name on file says
    "the resource person" rather than naming the activity;
  * both forms still emit the SAME item_ids, scales, N/A flags and dimensions —
    the calculator reads only those, so nothing recalculates.
"""
import app
import i18n


TOPIC = "15th Learning Exchange Session"

# Phrasings that only make sense about a person.
PERSON_PHRASES = [
    "was responsive and willing",
    "knowledgeable and competent in the subject",
    "gave caring attention",
    "delivered the session as promised",
    "performed reliably",
    "communicated clearly and inspired confidence",
]


def _ctx(survey_type, *, rp_name=None, topic=TOPIC):
    """The four fields survey_spec() actually reads off a form context."""
    return {"survey_type": survey_type, "form": f"F{survey_type}",
            "topic": topic, "rp_name": rp_name}


def _texts(spec):
    return [it["text"] for g in spec["groups"] for it in g["items"]]


def _items(spec):
    return [(it["id"], tuple(it["scale"]), it["allow_na"], it["dim"])
            for g in spec["groups"] for it in g["items"]]


# ---- Type 2: about the activity --------------------------------------------

def test_activity_form_never_reads_as_a_person():
    texts = _texts(app.survey_spec(_ctx(2)))
    blob = " ".join(texts).lower()
    for phrase in PERSON_PHRASES:
        assert phrase not in blob, f"person phrasing left on the activity form: {phrase}"


def test_activity_form_does_not_repeat_the_title_in_every_question():
    """The header already names the activity; the statements must not."""
    for text in _texts(app.survey_spec(_ctx(2))):
        assert TOPIC not in text


def test_activity_form_uses_the_activity_wording():
    texts = _texts(app.survey_spec(_ctx(2)))
    assert app.A_TEXT_ACTIVITY in texts
    assert app.C_TEXT_ACTIVITY in texts
    for text in app.B_TEXT_ACTIVITY.values():
        assert text in texts


def test_activity_form_in_filipino_uses_the_activity_wording():
    texts = _texts(app.survey_spec(_ctx(2), lang="fil"))
    assert i18n.A_TEXT_ACTIVITY_FIL in texts
    assert i18n.C_TEXT_ACTIVITY_FIL in texts
    assert i18n.B_TEXT_ACTIVITY_FIL["B5"] in texts
    assert TOPIC not in " ".join(texts)


# ---- Type 3: unchanged ------------------------------------------------------

def test_resource_person_form_wording_is_unchanged():
    texts = _texts(app.survey_spec(_ctx(3, rp_name="Dr. Maria Santos")))
    assert "Dr. Maria Santos delivered the session as promised and announced." in texts
    assert "Dr. Maria Santos was responsive and willing to address questions and needs." in texts
    assert "Overall, how would you rate the quality of Dr. Maria Santos?" in texts


def test_resource_person_form_without_a_name_does_not_borrow_the_activity_title():
    spec = app.survey_spec(_ctx(3, rp_name=None))
    texts = _texts(spec)
    assert TOPIC not in " ".join(texts)
    assert spec["subject"] == "the resource person"
    assert "The resource person was knowledgeable and competent in the subject." in texts


def test_resource_person_fallback_is_translated():
    """A Filipino form must not fall back to an English phrase mid-sentence."""
    texts = _texts(app.survey_spec(_ctx(3, rp_name=None), lang="fil"))
    assert "the resource person" not in " ".join(texts)
    assert "tagapagsalita" in " ".join(texts)


# ---- the part that must NOT change -----------------------------------------

def test_both_forms_keep_the_same_items_scales_and_dimensions():
    """Wording is display-only: ids, scales, N/A and dims are what the engine
    reads, and they are identical to what each form emitted before."""
    f2 = app.survey_spec(_ctx(2))
    f3 = app.survey_spec(_ctx(3, rp_name="Dr. Maria Santos"))

    ids = ["A"] + [f"B{i}" for i in range(1, 10)] + ["C"]
    assert [i[0] for i in _items(f2)] == ids
    assert [i[0] for i in _items(f3)] == ids

    for spec in (f2, f3):
        for _id, scale, allow_na, _dim in _items(spec):
            assert allow_na is True
            assert scale == tuple(app.OSQ4 if _id == "C" else app.SCALE7)

    # Only the dimension GROUPING differs between the two forms.
    dims = {i[0]: i[3] for i in _items(f2)}
    assert dims["B7"] == "Empathy" and dims["B8"] == "Tangible"
    dims3 = {i[0]: i[3] for i in _items(f3)}
    assert dims3["B7"] == "Assurance" and dims3["B8"] == "Empathy"


def test_language_never_changes_the_recorded_shape():
    """Filipino swaps the DISPLAY text and the scale LABELS; item ids, N/A and
    the numeric scale values a submission is stored as are identical."""
    def shape(spec):
        return [(it["id"], tuple(v for v, _ in it["scale"]), it["allow_na"], it["dim"])
                for g in spec["groups"] for it in g["items"]]

    assert shape(app.survey_spec(_ctx(2))) == shape(app.survey_spec(_ctx(2), lang="fil"))
    assert shape(app.survey_spec(_ctx(3, rp_name="Dr. Maria Santos"))) == \
        shape(app.survey_spec(_ctx(3, rp_name="Dr. Maria Santos"), lang="fil"))
