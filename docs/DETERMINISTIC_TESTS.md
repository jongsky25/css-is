# Deterministic tests — A10 step 2 / candidate 7.35

## Isolation

`tests/conftest.py` builds one synthetic SQLite reference database for a pytest run. It never reads or copies the repository's `css_is.db`. Each HTTP test receives its own temporary database through SQLite's backup API, and that copy is removed after the test. Clients and sample IDs are function-scoped. Reporting caches and directory-status caches are reset per test; rate-limit state is reset as before. Ordinary role clients are closed after use.

The reference contains four active role accounts, a pending account, a bureau and reference section, three internal people, and two dated examples of each survey type. Each form has twelve synthetic responses. Dates are seven and forty-two days before the configured test date. This supplies nonempty reporting, trend, directory and export examples without depending on another test having created them. The accounts are deliberately not assigned directory authority.

Tests that require special state create it explicitly. Audit-label tests perform a real sign-in, archived-page tests create an archived item, and multi-event tests use different dates. The global `find_similar_events` bypass has been removed: duplicate protection is exercised normally.

## Clock

Default application reference time: **2026-10-20 06:00:00**, in the application's configured local timezone. `CSS_TEST_NOW` accepts an alternative naive ISO local datetime before starting pytest.

The clock is installed before collection so module-level date constants agree with runtime fixtures, and restored when pytest exits. Each test resets local dates and epoch-based token time to the same reference. Epoch time continues to advance by real monotonic elapsed seconds within the test; worker timeouts can still terminate. Monotonic/performance clocks and sleep are not frozen. Tests can use `monkeypatch` to override local time for a specific scenario. `real_application_clock` is reserved for checking the production timezone adapter itself.

The JavaScript Gmail-import contract harness receives the Python test epoch explicitly, keeping signed requests within the real verification window. No signature or freshness check is disabled.

Test helpers use the application clock rather than the host date. Future examples use day offsets rather than replacing the year of February 29.

## Repeatable commands

```bash
# Normal order, with a private database per HTTP test
python -m pytest

# Stable, seed-specific ordering across all collected cases
python -m pytest --shuffle-seed=732

# Example boundary run, with a different order
CSS_TEST_NOW=2028-02-29T23:55:00 python -m pytest \
  tests/test_date_handling.py tests/test_event_hub.py \
  tests/test_att_hardening.py tests/test_registration_questions.py \
  tests/test_registration_dedup.py tests/test_update_email.py \
  tests/test_responder_name_list.py --shuffle-seed=229

# One test without any preceding module/suite setup
python -m pytest tests/test_audit_insights.py::test_audit_page_shows_friendly_labels
```

Shuffling sorts case IDs by a seed-specific SHA-256 value, so the order is reproducible and independent of Python's hash seed. The reference time and shuffle seed appear in the pytest report header.

## Verification and limits

Verification on committed source (the two clean-checkout runs precede integration of the 7.34 calendar fix; seed 735 verifies the combined 7.35 release):

| Run | Result |
|---|---|
| Integrated 7.35 release, shuffled seed 735 | 4,195 passed; zero failures; 16 existing skips |
| Clean checkout, normal order | 4,195 passed; zero failures; 16 existing skips |
| Separate clean checkout, shuffled seed 734 | 4,195 passed; zero failures; 16 existing skips |
| Leap day, shuffled seed 229 | 137 passed |
| Six selected tests, each in a fresh process | All six passed |
| JavaScript/Python clock and signature contracts | 27 passed |

Results and source hashes are recorded in `docs/phase1/deterministic-tests/verification.json`. Verification covers normal full-suite execution, shuffled full-suite execution, selected tests in separate pytest processes, and a leap-day date-sensitive selection. A clean worktree run verifies that no database snapshot or generated local file is needed.

Existing environment-dependent browser skips remain; no failing case is converted to a skip or expected failure. These checks do not prove every possible ordering or date. Python 3.11 parity and mandatory release gates are the next A10 steps. Manual production testing remains deferred. This increment preserves main's 7.33 travel-upload and 7.34 calendar date-prefill changes and requires no database migration.
