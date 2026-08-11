"""The dashboard's plain-language dimension labels must describe the questions
people actually answered.

The labels were originally written from a bureau spreadsheet describing a
DIFFERENT set of B-items than this app asks, so the dashboard reported item B6
("handled by knowledgeable and competent people") as "Courteous organizers" and
item B9 ("the materials, venue, and presentation…") as "well dressed and appears
neat". These lock the corrected labels against the real question text:
  * every dimension in each form's map has exactly one label and one concern;
  * a label shares vocabulary with the items it actually covers;
  * the specific wrong labels don't come back.

The vocabulary check is a heuristic — it catches gross drift (a label about
grooming over an item about a venue), not every subtle mismatch. The explicit
assertions below are the real guard.
"""
import re

import app
import css_is_engine as eng
import dashboard_insights as di


FORMS = {
    2: (eng.DIM_MAP_FORM2, di.DIM_LABELS_F2, di.DIM_CONCERN_F2, app.B_TEXT_ACTIVITY),
    3: (eng.DIM_MAP_FORM3, di.DIM_LABELS_F3, di.DIM_CONCERN_F3, app.B_TEXT),
}


def _words(text):
    """Meaningful lowercase words, stemmed to five characters so 'attentive'
    matches 'attention' and 'clear' matches 'clearly'."""
    stop = {"with", "that", "were", "them", "they", "this", "their", "about",
            "from", "have", "been", "over", "than", "into", "your"}
    out = set()
    for w in re.findall(r"[a-z]+", text.lower()):
        if len(w) >= 4 and w not in stop:
            out.add(w[:5])
    return out


def _bucket_text(items, texts):
    return " ".join(texts[i] for i in items)


# ---- structure ---------------------------------------------------------------

def test_every_dimension_has_exactly_one_label_and_one_concern():
    for survey_type, (dim_map, labels, concern, _texts) in FORMS.items():
        assert set(labels) == set(dim_map), f"Form {survey_type} labels drifted from the map"
        assert set(concern) == set(dim_map), f"Form {survey_type} concerns drifted from the map"
        for dim in dim_map:
            assert labels[dim].strip() and concern[dim].strip()


def test_label_lookup_helpers_return_the_right_set():
    assert di.dim_labels(2) is di.DIM_LABELS_F2
    assert di.dim_labels(3) is di.DIM_LABELS_F3
    assert di.dim_concern(2) is di.DIM_CONCERN_F2
    assert di.dim_concern(3) is di.DIM_CONCERN_F3
    # The person-centric views (People grid, benchmarks) default to Form 3.
    assert di.DIM_LABELS is di.DIM_LABELS_F3
    assert di.EVENT_DIM_LABELS is di.DIM_LABELS_F2


# ---- labels vs the questions they cover --------------------------------------

def test_each_label_shares_vocabulary_with_its_own_items():
    for survey_type, (dim_map, labels, _concern, texts) in FORMS.items():
        for dim, items in dim_map.items():
            blob = _words(_bucket_text(items, texts))
            label = _words(labels[dim])
            assert label & blob, (
                f"Form {survey_type} {dim} is labelled {labels[dim]!r}, which shares no "
                f"wording with what it actually asks: {_bucket_text(items, texts)!r}")


def test_the_previously_wrong_labels_are_gone():
    """Each of these described an item the form does not ask."""
    # B6 asks about competence, not courtesy.
    assert "Courteous" not in di.DIM_LABELS_F2["Assurance"]
    assert "courtesy" not in di.DIM_CONCERN_F2["Assurance"]
    # B7 asks how clearly things were communicated, not about attentiveness.
    assert di.DIM_LABELS_F2["Empathy"] != "Attentive to participants"
    # F2's Tangible covers B8 (attention) as well as B9 (venue) — it must not
    # claim to be only the venue.
    assert di.DIM_LABELS_F2["Tangible"] != "Venue & set-up"
    # B9 asks about materials and the venue, not the speaker's grooming.
    assert "dressed" not in di.DIM_CONCERN_F3["Tangible"]
    assert di.DIM_LABELS_F3["Tangible"] != "Neat & well-presented"


def test_f2_tangible_label_names_both_of_its_items():
    """The bucket averages attention to participants with materials/venue, so a
    label naming only one of them misreports the number underneath it."""
    label = di.DIM_LABELS_F2["Tangible"].lower()
    assert "attention" in label or "attentio" in label
    assert "set-up" in label or "venue" in label


# ---- the labels are display-only ---------------------------------------------

def test_labels_do_not_touch_the_scoring_maps():
    """Locked: this change was labels only. The maps decide every score."""
    assert eng.DIM_MAP_FORM2 == {
        "Reliability":    ["B1", "B2", "B3", "B4"],
        "Responsiveness": ["B5"],
        "Assurance":      ["B6"],
        "Empathy":        ["B7"],
        "Tangible":       ["B8", "B9"],
    }
    assert eng.DIM_MAP_FORM3 == {
        "Reliability":    ["B1", "B2", "B3", "B4"],
        "Responsiveness": ["B5"],
        "Assurance":      ["B6", "B7"],
        "Empathy":        ["B8"],
        "Tangible":       ["B9"],
    }
    # The Activities page scores the event-about dimensions only.
    assert set(di.EVENT_DIMS_FORM2) == {"Reliability", "Responsiveness", "Tangible"}
