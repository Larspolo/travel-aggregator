"""The lane lines of health.py give the cost sum and the share of each lane (#1508)."""
import health


def test_lane_shares_give_the_sum_and_the_share_of_each_lane():
    shares = health.lane_shares({"deep": [1.0, 2.0], "haiku": [0.5, 0.5], "opus": [1.0]})
    assert shares["deep"] == (3.0, 0.6)
    assert shares["haiku"] == (1.0, 0.2)
    assert shares["opus"] == (1.0, 0.2)


def test_lane_shares_with_no_cost_give_zero():
    assert health.lane_shares({"deep": [0.0]}) == {"deep": (0.0, 0.0)}
    assert health.lane_shares({}) == {}
