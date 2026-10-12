"""Lead scoring: the rule points, the tiers, the business's own buying words, and the blend with the classifier."""
from app import classifier, main
from app.scoring import WEIGHTS, score_lead, tier_for


def test_points_add_up_per_detail():
    lead = {"name": "Sara", "phone": "03211234567", "need": "sneakers", "budget": "5000", "timeline": "Friday"}
    pts, tier, reason = score_lead(lead, "")
    assert pts == WEIGHTS["name"] + WEIGHTS["phone"] + WEIGHTS["need"] + WEIGHTS["budget"] + WEIGHTS["timeline"]
    assert tier == "hot" and "shared phone" in reason


def test_no_details_is_cold_with_a_reason():
    assert score_lead({}, "hello") == (0, "cold", "no buying signals yet")


def test_price_question_and_urgency_add_points():
    assert score_lead({}, "how much is a 5kw system?")[0] == 10
    assert score_lead({}, "kitne ka hai, jaldi chahiye")[0] == 15  # Roman Urdu price word + urgency


def test_score_is_capped_at_100():
    lead = {f: "x" for f in WEIGHTS}
    assert score_lead(lead, "price asap")[0] == 100


def test_tier_boundaries():
    assert [tier_for(p) for p in (69, 70, 39, 40)] == ["warm", "hot", "cold", "warm"]


def test_business_buying_words_count():
    """A shoe shop's own words ("size") are buying signals for it, not for everyone."""
    assert score_lead({}, "do you have my size?")[0] == 0
    assert score_lead({}, "do you have my size?", extra_intent=["size"])[0] == 10


def test_classifier_spots_not_now_wording():
    keen = {"phone": "03001234567", "need": "5kw"}
    p_keen = classifier.predict(keen, "how much is 5kw? I want it installed this month")
    p_later = classifier.predict(keen, "just checking prices for next year")
    assert p_keen is not None and p_later is not None
    assert p_later < p_keen


def test_final_score_blends_rules_and_model():
    lead = {"phone": "03001234567", "need": "5kw"}
    main.score_and_tier(lead, "just checking prices for next year")
    assert lead["score"] == round(0.5 * lead["rule_score"] + 0.5 * lead["ml_score"])
    assert lead["tier"] == tier_for(lead["score"]) and "model:" in lead["reason"]
