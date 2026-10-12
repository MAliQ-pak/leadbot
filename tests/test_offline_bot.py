"""The offline bot, which answers whenever the AI is slow or down. Regression for a real chat on the live
site while Google's models were overloaded: the bot asked "Which shoes are you looking for?", the visitor
answered "simple office wear, EU 44", and the bot repeated the sizes paragraph and the same question."""
from conftest import signup


def talk(visitor, slug, sid, messages):
    return [visitor.post("/api/chat", json={"bot": slug, "session_id": sid, "message": m}).json()["reply"] for m in messages]


def test_an_answer_to_the_bots_question_counts(visitor):
    owner, biz = signup("Offline Shoes")
    replies = talk(visitor, biz["slug"], "sess-off-1", ["Do you have size 44?", "simple office wear, EU 44",
                                                        "Saad Ahmed", "0300-4561237", "around 6000", "by Friday"])
    assert "Which shoes" in replies[0]
    assert "Which shoes" not in replies[1] and "name" in replies[1]  # moved on to the next question
    assert "Adult sizes" not in replies[1]  # no knowledge-base quote for a statement
    lead = next(l for l in owner.get("/api/leads").json() if l["session_id"] == "sess-off-1")
    assert (lead["name"], lead["phone"], lead["budget"], lead["timeline"]) == ("Saad Ahmed", "0300-4561237", "around 6000", "by Friday")
    assert "office" in lead["need"] and lead["tier"] == "hot"
    assert replies[-1].endswith("Our team will get back to you shortly.")


def test_words_no_pattern_knows_still_count_as_the_need(visitor):
    owner, biz = signup("Words Shoes")
    talk(visitor, biz["slug"], "sess-off-2", ["hi", "something comfy for my dad"])
    lead = next(l for l in owner.get("/api/leads").json() if l["session_id"] == "sess-off-2")
    assert lead["need"] == "something comfy for my dad"


def test_never_the_same_paragraph_twice_in_a_row(visitor):
    _, biz = signup("Repeat Shoes")
    first, second = talk(visitor, biz["slug"], "sess-off-3", ["Do you have size 44?", "what sizes do you have?"])
    assert "Adult sizes" in first and second.startswith("As I mentioned")
