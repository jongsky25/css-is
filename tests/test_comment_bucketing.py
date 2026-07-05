"""Theme bucketing of free-text comments — the 'In people's own words' panel.

A spot-feedback report flagged that "Clear sounds of audio" showed under the
*Knowledge & content* box when it is plainly about the room/AV. The word "clear"
is the one cue the Knowledge bucket shares with the AV world: it means content
clarity ("the speaker explained clearly") OR audio clarity ("clear audio"). When
a comment also lands in Facilities (a real venue/AV/connectivity word is present)
and Knowledge matched ONLY on "clear", the clarity is about the AV — so Knowledge
is dropped. A comment that also names the content (speaker, topic, …) keeps it.
"""
import dashboard_insights as di


def test_clear_audio_is_facilities_not_knowledge():
    # The exact comment from the spot-feedback report.
    b = di.match_buckets("Clear sounds of audio")
    assert "facilities" in b
    assert "knowledge" not in b


def test_clear_only_av_comments_drop_knowledge():
    for text in ["Audio not clear", "The audio was not that clear.",
                 "Virtual platform not clear...on and off and no audio",
                 "audio is not so clear"]:
        b = di.match_buckets(text)
        assert "facilities" in b, text
        assert "knowledge" not in b, text


def test_genuine_knowledge_clarity_is_kept():
    # No AV/venue word -> "clear" is about the content, stays Knowledge.
    b = di.match_buckets("The presentation was clear")
    assert "knowledge" in b
    assert "facilities" not in b


def test_content_word_keeps_knowledge_even_with_av():
    # Names the speaker/content too -> legitimately both buckets.
    b = di.match_buckets("The speaker was not clear and the audio was poor")
    assert "knowledge" in b
    assert "facilities" in b


def test_connectivity_words_route_to_facilities():
    for text in ["Internet connection is not stable",
                 "Please choose another virtual platform",
                 "weak wifi signal during the session"]:
        assert "facilities" in di.match_buckets(text), text
