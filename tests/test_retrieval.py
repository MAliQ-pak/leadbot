"""Retrieval: for every industry template, questions its sample text answers score at or above the 0.3
threshold, and questions it does not answer score below it, so the bot says "not sure" instead of guessing."""
import pytest

from app import business, rag

CASES = {
    "solar": (["what is the warranty?", "kist milti hai?", "how much is a 5kw system?", "5kw ki qeemat kitni hai?",
               "what are your packages?", "book a free site visit", "what are your timings?"],
              ["do you sell generators?", "do you have jobs?", "can I pay with credit card?",
               "is there a discount for students?"]),
    "shoes": (["do you have size 44?", "delivery charges?", "return policy?", "khussa ki qeemat kya hai?",
               "can I pay with card?", "cash on delivery?", "bulk order for school"],
              ["do you sell socks?", "do you have jobs?"]),
    "clinic": (["consultation fee?", "dentist timings", "where is the clinic?", "daant ka checkup kitne ka hai?",
                "lab test ki report kab milegi?", "book an appointment"],
               ["do you do heart surgery?", "can I park my car?"]),
    "restaurant": (["catering for 100 guests?", "do you deliver?", "book a table", "biryani ki price kya hai?",
                    "is the food halal?"],
                   ["do you have vegan sushi?", "is there wifi?"]),
    "realestate": (["5 marla house for sale in bahria?", "flats for rent", "commission kitna hai?",
                    "help with registry transfer?", "ghar kiraye pe chahiye"],
                   ["do you build houses?", "home loans from banks?"]),
    "academy": (["O level classes?", "monthly fee kitni hai?", "book a free demo class", "online classes?",
                 "how do I get admission?"],
                ["do you have a hostel?", "is there a school bus?"]),
    "salon": (["bridal package price?", "facial ki price?", "home service available?", "walima makeup",
               "dulhan makeup kitne ka hai?"],
              ["do you do tattoos?", "do you have jobs?"]),
}


@pytest.fixture(scope="module")
def kbs():
    return {ind: rag.get_kb(business.create_from_template(business.TEMPLATES[ind]["sample"] + " Test", ind))
            for ind in CASES}


@pytest.mark.parametrize("industry,question", [(i, q) for i, (yes, _) in CASES.items() for q in yes])
def test_answerable_questions_pass_the_threshold(kbs, industry, question):
    best = kbs[industry].search_scored(question)[0]
    assert best["score"] >= rag.CONFIDENT, f"{question!r} matched {best['section']!r} at {best['score']:.2f}"


@pytest.mark.parametrize("industry,question", [(i, q) for i, (_, no) in CASES.items() for q in no])
def test_off_topic_questions_stay_below_the_threshold(kbs, industry, question):
    best = kbs[industry].search_scored(question)[0]
    assert best["score"] < rag.CONFIDENT, f"{question!r} matched {best['section']!r} at {best['score']:.2f}"


def test_one_industry_s_synonyms_do_not_leak_into_another(kbs):
    """Regression: "card" and "pay" were added for the shoe shop and once pulled the solar
    "credit card" question onto its financing text (0.38). Each template now has its own synonyms."""
    assert "card" in kbs["shoes"].synonyms and "card" not in kbs["solar"].synonyms


def test_template_text_uses_the_new_business_name():
    bid = business.create_from_template("Kicks Corner", "shoes")
    from app import db
    biz = db.get_business(bid)
    assert biz["bot_name"] == "Kicks Corner Assistant"
    assert "Kicks Corner" in biz["kb_text"] and "Stride Shoes" not in biz["kb_text"]
