"""`tokens.phases` counts the run time of the last call of a transcript up to its result: the phase split of #5528
gave the last call 0 s, also when its tool ran for minutes (a last `ship_pr.py` waits up to 10 minutes for the CI)."""
import tokens
from test_tokens_phases import call, result


def test_the_last_call_counts_up_to_its_result():
    recs = [call(0, "a", "Bash", command="python3 framework/tools/claim.py 7"), result(1, "a", "claimed claim/7"),
            call(60, "b", "Bash", command="python3 framework/tools/ship_pr.py 7 --message m"), result(360, "b", "ok")]
    sec = {p: round(m * 60) for p, m in tokens.phases(recs)[7].items()}
    assert sec["claim"] == 1 and sec["ci"] == 59 + 300                 # 59 s to write the call, 300 s for the CI wait


def test_a_last_call_with_no_result_counts_nothing():
    recs = [call(0, "a", "Bash", command="python3 framework/tools/claim.py 7"), result(1, "a", "claimed claim/7"),
            call(60, "b", "Bash", command="python3 framework/tools/ship_pr.py 7 --message m")]
    sec = {p: round(m * 60) for p, m in tokens.phases(recs)[7].items()}
    assert sec["claim"] == 1 and sec["ci"] == 59
