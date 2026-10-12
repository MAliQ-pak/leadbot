"""Businesses: industry templates, per-business bot settings, and creating a new business.

Each business has its own bot (name, greeting, colour, quick replies), its own lead questions and
buying-signal words, and its own knowledge base. A template fills all of these in one click, so a
new company (a shoe shop, say) starts with a working bot and only edits its own details.
"""
import json
import re
from pathlib import Path

from . import db

ROOT = Path(__file__).resolve().parent.parent

# The lead details every bot collects (db.LEAD_FIELDS); a template only changes how it asks for them.
TEMPLATES = {
    "solar": {
        "label": "Solar installer",
        "blurb": "prices, installation, warranty, site visits",
        "sample": "BrightPath Solar",
        "bot_name": "BrightPath Assistant",
        "color": "#047857",
        "greeting": "Assalam o Alaikum! I can help with prices, installation, warranty, installments or booking a free site visit. You can write in English or Roman Urdu.",
        "quick_replies": ["How much is a 5 kW system?", "5kw ki qeemat kitni hai?", "Book a free site visit", "Do you offer installments?"],
        "questions": {
            "need": "What are you looking for (e.g. home system size or backup needs)?",
            "name": "May I know your name?",
            "phone": "What's the best phone number for our advisor to reach you?",
            "budget": "Do you have a rough budget in mind?",
            "timeline": "When are you hoping to get this done?",
        },
        "need_keywords": ["kw", "solar", "inverter", "battery", "net metering", "maintenance", "hybrid", "on-grid"],
        "intent_words": ["install", "lagwana", "lagwani", "site visit"],
        "kb_file": "kb/business.md",
        "synonyms": {
            "kist": "installment financing",
            "qist": "installment financing",
            "installments": "installment financing",
            "emi": "installment financing",
            "loan": "installment financing",
            "guarantee": "warranty",
            "waranty": "warranty",
            "time": "installation time duration",
            "kitna time": "installation time duration",
            "kab": "installation time",
            "visit": "site visit",
            "net metering": "services net metering paperwork",
            "installation": "installation time",
            "how long": "installation time duration",
            "where": "areas karachi lahore islamabad",
            "areas": "about karachi lahore islamabad",
            "cities": "about karachi lahore islamabad",
            "city": "about karachi lahore islamabad",
            "serve": "about karachi lahore islamabad",
            "located": "about karachi lahore islamabad",
            "price list": "pricing price maintenance",
            "plans": "pricing price financing",
            "which system": "pricing services",
            "on grid": "pricing on-grid",
            "on-grid": "pricing",
            "hybrid": "pricing services battery",
            "battery": "services battery backup pricing",
            "backup": "services battery backup pricing",
            "load shedding": "services battery backup",
            "offer": "services pricing",
            "options": "services pricing",
            "products": "services pricing",
        },
        "stage_names": {"site_visit": "Site visit booked", "quote_sent": "Quote sent"},
    },
    "shoes": {
        "label": "Shoe store",
        "blurb": "sizes, prices, delivery, returns",
        "sample": "Stride Shoes",
        "bot_name": "Stride Assistant",
        "color": "#2E3A6E",
        "greeting": "Hi! Looking for shoes? Ask me about sizes, prices, delivery or returns. English or Roman Urdu both work.",
        "quick_replies": ["Do you have size 44?", "Delivery charges?", "Return policy?", "Khussa ki qeemat kya hai?"],
        "questions": {
            "need": "Which shoes are you looking for (style and size)?",
            "name": "May I have your name?",
            "phone": "What's your phone number so we can confirm the order?",
            "budget": "Do you have a budget in mind?",
            "timeline": "When do you need them by?",
        },
        "need_keywords": ["sneakers", "sneaker", "joggers", "formal shoes", "formal", "khussa", "sandals", "heels",
                          "boots", "loafers", "sports shoes", "kids shoes", "school shoes"],
        "intent_words": ["order", "buy", "size", "deliver", "cod", "chahiye"],
        "stage_names": {"site_visit": "Order confirmed", "quote_sent": "Out for delivery"},
        "synonyms": {
            "delivery": "delivery",
            "shipping": "delivery",
            "deliver": "delivery",
            "cod": "delivery payment cash",
            "cash on delivery": "delivery payment",
            "return": "returns exchange",
            "returns": "returns exchange",
            "exchange": "returns exchange",
            "refund": "returns exchange",
            "size": "sizes",
            "sizes": "sizes",
            "joota": "products shoes",
            "joote": "products shoes",
            "shoes": "products",
            "jazzcash": "payment",
            "easypaisa": "payment",
            "card": "payment",
            "pay": "payment",
            "bulk": "bulk orders",
        },
        "kb": """# Stride Shoes (sample business for demo)

## About
Stride Shoes sells men's, women's and kids' shoes online across Pakistan and in two stores, in Lahore and Karachi. We have been in business since 2018.

## Products
We sell sneakers, joggers and sports shoes, formal shoes, loafers, sandals, heels, boots, traditional khussa, and kids' school shoes.

## Pricing
Sneakers and joggers start from Rs 4,500. Formal shoes start from Rs 6,000. Khussa start from Rs 2,500. Kids' shoes start from Rs 2,000. Prices are shown on each product page and may change during sales.

## Sizes
Adult sizes run from EU 36 to EU 46. Kids' sizes run from EU 24 to EU 35. Half sizes are not available. If you are between sizes, we suggest the larger size.

## Delivery
We deliver across Pakistan in 3 to 5 working days. Delivery is free on orders above Rs 5,000; otherwise it costs Rs 250. Cash on delivery is available.

## Returns and exchange
Unworn shoes can be returned or exchanged within 7 days of delivery with the receipt. Exchanging for a different size is free.

## Payment
We accept cash on delivery, debit and credit cards, JazzCash and EasyPaisa.

## Store hours and contact
Our stores are open every day, 11 am to 10 pm. Our customer team replies to messages within a few hours.

## Bulk orders
Schools and companies ordering 20 or more pairs can ask for a bulk quote. A team member will call to confirm sizes and prices.
""",
    },
    "clinic": {
        "label": "Clinic or doctor",
        "blurb": "appointments, fees, doctors, lab tests",
        "sample": "CarePlus Clinic",
        "bot_name": "CarePlus Assistant",
        "color": "#2B5CE6",
        "greeting": "Assalam o Alaikum! I can help with doctors' timings, consultation fees, lab tests or booking an appointment. English or Roman Urdu both work.",
        "quick_replies": ["Consultation fee?", "Book an appointment", "Lady doctor available?", "Lab test ki report kab milegi?"],
        "questions": {
            "need": "Which doctor or service do you need (for example a general check-up, dental or a lab test)?",
            "name": "May I have the patient's name?",
            "phone": "What's the best phone number to confirm the appointment?",
            "budget": "Would you like to keep the visit within a certain fee?",
            "timeline": "Which day would you like to come in?",
        },
        "need_keywords": ["check-up", "checkup", "consultation", "dentist", "dental", "skin", "physiotherapy",
                          "lab test", "blood test", "ultrasound", "vaccination", "child specialist", "gynae"],
        "intent_words": ["appointment", "book", "booking", "dikhana", "checkup karwana"],
        "stage_names": {"site_visit": "Appointment booked", "quote_sent": "Visited"},
        "synonyms": {
            "doctor": "doctors", "dr": "doctors", "lady doctor": "doctors female", "specialist": "doctors",
            "fee": "fees price", "fees": "fees price", "charges": "fees price",
            "appointment": "appointments booking", "book": "appointments booking", "token": "appointments booking",
            "daant": "dental check-up", "teeth": "dental", "tooth": "dental", "dentist": "dentist doctors timings",
            "checkup": "check-up fees price", "check-up": "fees price",
            "where": "location contact", "kahan": "location contact", "address": "location contact",
            "test": "lab tests", "tests": "lab tests", "report": "lab tests reports", "blood": "lab tests",
            "emergency": "emergency", "insurance": "payment insurance panel", "pay": "payment",
        },
        "kb": """# CarePlus Clinic (sample business for demo)

## About
CarePlus Clinic is a family clinic in Lahore with general physicians, a dentist, a skin specialist and a lab. We have served families since 2015. This assistant can share timings, fees and services and book appointments, but it cannot give medical advice.

## Doctors and timings
General physician: Monday to Saturday, 10 am to 9 pm. Lady doctor: Monday to Saturday, 11 am to 5 pm. Dentist: Monday, Wednesday and Friday, 4 pm to 9 pm. Skin specialist: Tuesday and Thursday, 5 pm to 8 pm.

## Fees and prices
General consultation Rs 1,500. Specialist consultation Rs 2,500. Dental check-up Rs 2,000; scaling and polishing from Rs 4,000. Follow-up visit within 7 days is free.

## Appointments and booking
Appointments can be booked through this chat, by phone or on WhatsApp. Walk-ins are welcome, but patients with an appointment are seen first. Please arrive 10 minutes early.

## Lab tests and reports
Our lab does blood tests, sugar and cholesterol tests, urine tests and thyroid tests. Most reports are ready the same evening and can be sent on WhatsApp. Home sample collection costs Rs 500.

## Emergency
We are not an emergency hospital. In an emergency, go to the nearest hospital or call 1122.

## Payment
Cash, card, JazzCash and Easypaisa are accepted. We are on the panel of two insurance companies; ask the front desk for details.

## Location and contact
CarePlus Clinic, Main Boulevard, Gulberg, Lahore. Phone and WhatsApp 0300-1234567. Closed on Sundays.
""",
    },
    "restaurant": {
        "label": "Restaurant or caterer",
        "blurb": "menu, delivery, catering and events",
        "sample": "Spice Route Kitchen",
        "bot_name": "Spice Route Assistant",
        "color": "#7A5A2A",
        "greeting": "Hi! Ask me about our menu, delivery, catering for events or booking a table. English or Roman Urdu both work.",
        "quick_replies": ["Catering for 100 guests?", "Do you deliver?", "Book a table", "Biryani ki price kya hai?"],
        "questions": {
            "need": "What would you like: catering for an event, a table booking or a bulk order?",
            "name": "May I have your name?",
            "phone": "What's your phone number so our team can confirm the details?",
            "budget": "Do you have a budget per head in mind?",
            "timeline": "What's the date of your event or booking?",
        },
        "need_keywords": ["catering", "event", "wedding", "mehndi", "birthday", "office lunch", "corporate",
                          "table", "bulk order", "deal", "bbq", "biryani"],
        "intent_words": ["book", "booking", "order", "guests", "event", "chahiye"],
        "stage_names": {"site_visit": "Menu shared", "quote_sent": "Booking confirmed"},
        "synonyms": {
            "menu": "menu prices", "dishes": "menu", "food": "menu", "khana": "menu", "biryani": "menu",
            "karahi": "menu", "bbq": "menu", "deal": "menu deals",
            "delivery": "delivery", "deliver": "delivery", "home delivery": "delivery", "cod": "delivery payment",
            "catering": "catering events", "event": "catering events", "wedding": "catering events",
            "shaadi": "catering events", "guests": "catering events", "per head": "catering events",
            "table": "table booking reservations", "reservation": "table booking reservations", "book": "table booking",
            "halal": "about halal", "pay": "payment",
        },
        "kb": """# Spice Route Kitchen (sample business for demo)

## About
Spice Route Kitchen is a family restaurant in Karachi serving Pakistani and BBQ food since 2017. All meat is halal. We also do catering for weddings, birthdays and office events.

## Menu and prices
Chicken biryani Rs 650 per plate. Chicken karahi Rs 2,400 (full). Mutton karahi Rs 3,800 (full). BBQ platter for four Rs 4,500. Family deal for four (biryani, karahi, naan and drinks) Rs 5,500.

## Delivery
We deliver within 6 km of the restaurant, from 12 pm to 11:30 pm. Delivery is free on orders above Rs 2,000; otherwise Rs 150. Delivery usually takes 40 to 60 minutes. Cash on delivery is available.

## Catering and events
Catering starts at 50 guests. Menus start from Rs 1,800 per head, including two main dishes, rice, naan, salad and a dessert. We bring serving staff and crockery. Please book at least 7 days before the event; a 30 percent advance confirms the booking.

## Table booking
Tables can be booked for lunch or dinner through this chat or by phone. A family hall seats up to 40 people for private gatherings.

## Payment
Cash, card, JazzCash and Easypaisa are accepted.

## Opening hours and contact
Open every day, 12 pm to 12 am. Shahrah-e-Faisal, Karachi. Phone and WhatsApp 0321-7654321.
""",
    },
    "realestate": {
        "label": "Real estate agency",
        "blurb": "properties, rent, viewings, documents",
        "sample": "Keystone Properties",
        "bot_name": "Keystone Assistant",
        "color": "#1C1B18",
        "greeting": "Assalam o Alaikum! Looking to buy, sell or rent a property? Ask me about areas, prices or booking a viewing.",
        "quick_replies": ["5 marla house for sale?", "Flats for rent", "Book a viewing", "Commission kitna hai?"],
        "questions": {
            "need": "Are you looking to buy, sell or rent, and what kind of property (house, flat, plot)?",
            "name": "May I have your name?",
            "phone": "What's the best phone number for our agent to call you?",
            "budget": "What is your budget?",
            "timeline": "When are you planning to move or buy?",
        },
        "need_keywords": ["house", "flat", "apartment", "plot", "shop", "office", "marla", "kanal",
                          "for rent", "for sale", "commercial"],
        "intent_words": ["buy", "rent", "viewing", "visit", "lena", "kiraye"],
        "stage_names": {"site_visit": "Viewing booked", "quote_sent": "Offer made"},
        "synonyms": {
            "house": "properties houses", "ghar": "properties houses", "makan": "properties houses",
            "flat": "properties flats apartments", "apartment": "properties flats apartments",
            "plot": "properties plots", "marla": "properties prices", "kanal": "properties prices",
            "rent": "renting rent", "kiraya": "renting rent", "kiraye": "renting rent", "tenant": "renting rent",
            "sell": "selling", "bechna": "selling",
            "commission": "fees commission", "fee": "fees commission", "charges": "fees commission",
            "viewing": "viewings visit", "visit": "viewings visit", "dekhna": "viewings visit",
            "documents": "documents transfer", "transfer": "documents transfer", "registry": "documents transfer",
            "area": "areas", "where": "areas", "dha": "areas", "bahria": "areas",
        },
        "kb": """# Keystone Properties (sample business for demo)

## About
Keystone Properties is a real estate agency in Islamabad and Rawalpindi helping families buy, sell and rent houses, flats and plots since 2012.

## Areas
We work in DHA, Bahria Town, Gulberg Greens, F-11, G-13 and Saddar.

## Properties for sale and prices
5 marla houses in Bahria Town start from about Rs 1.8 crore. 10 marla houses in DHA start from about Rs 4.5 crore. 2-bedroom flats in G-13 start from about Rs 95 lakh. Prices change with location and condition; our agent shares current listings.

## Renting
2-bedroom flats rent from about Rs 60,000 a month, and 10 marla houses from about Rs 1.2 lakh a month. Most landlords ask for two months' advance and one month's security.

## Selling with us
We value your property for free, list it and bring serious buyers. We check every buyer's documents before a deal.

## Fees and commission
Our commission is 1 percent of the sale price from each side, or one month's rent for a rental. There is no fee to view properties.

## Viewings
Viewings can be booked through this chat, Monday to Saturday, 10 am to 7 pm. An agent meets you at the property.

## Documents and transfer
We help with the sale agreement, the society transfer and the registry, and recommend a lawyer for checks.

## Office and contact
Keystone Properties, Blue Area, Islamabad. Phone and WhatsApp 0333-5551234. Open Monday to Saturday, 10 am to 7 pm.
""",
    },
    "academy": {
        "label": "School or tuition academy",
        "blurb": "courses, fees, timings, admissions",
        "sample": "Bright Minds Academy",
        "bot_name": "Bright Minds Assistant",
        "color": "#2E3A6E",
        "greeting": "Hi! Ask me about our classes, fees, timings, admissions or booking a free demo class.",
        "quick_replies": ["O Level classes?", "Monthly fee kitni hai?", "Book a free demo class", "Online classes?"],
        "questions": {
            "need": "Which class or course is this for (for example Matric, O Level or entry test)?",
            "name": "May I have the student's name?",
            "phone": "What's the best phone number for a parent or the student?",
            "budget": "Do you have a monthly budget for fees in mind?",
            "timeline": "When would you like to start?",
        },
        "need_keywords": ["matric", "fsc", "o level", "a level", "entry test", "mdcat", "ecat", "ielts",
                          "maths", "physics", "chemistry", "biology", "english", "computer"],
        "intent_words": ["admission", "enroll", "join", "demo class", "start", "dakhla"],
        "stage_names": {"site_visit": "Demo class booked", "quote_sent": "Admission form sent"},
        "synonyms": {
            "fee": "fees", "fees": "fees", "monthly": "fees",
            "class": "courses classes", "classes": "courses classes", "course": "courses classes",
            "subject": "courses classes", "subjects": "courses classes", "tuition": "courses classes",
            "teacher": "teachers", "teachers": "teachers", "ustad": "teachers",
            "timing": "timings batches", "timings": "timings batches", "batch": "timings batches", "shift": "timings batches",
            "admission": "admissions", "dakhla": "admissions", "enroll": "admissions", "join": "admissions",
            "demo": "demo class", "trial": "demo class",
            "online": "online classes", "zoom": "online classes",
            "test": "tests results", "result": "tests results",
        },
        "kb": """# Bright Minds Academy (sample business for demo)

## About
Bright Minds Academy is a tuition academy in Rawalpindi for Matric, FSc, O Level, A Level and entry-test students, running since 2014.

## Courses and classes
Matric and FSc: maths, physics, chemistry, biology, computer and English. O Level and A Level: maths, physics, chemistry, biology and English. Entry-test preparation for MDCAT and ECAT. IELTS preparation.

## Fees
Matric and FSc: Rs 4,000 per subject per month. O Level and A Level: Rs 7,000 per subject per month. MDCAT or ECAT full course: Rs 45,000. IELTS course: Rs 25,000. Admission fee Rs 2,000, paid once. Siblings get 10 percent off.

## Timings and batches
Classes run Monday to Saturday in two shifts: 3 pm to 6 pm and 6 pm to 9 pm. Each class has at most 20 students.

## Teachers
Our teachers have at least five years' teaching experience; most hold a master's degree in their subject.

## Admissions
Admissions are open all year. Bring the student's last result card and a B-form or CNIC copy. The first class is a free demo class.

## Demo class
Any student can attend one free demo class before joining. Book it through this chat or by phone.

## Online classes
O Level, A Level and IELTS classes are also available online on Zoom, at the same fees.

## Tests and results
Weekly tests, monthly progress reports to parents, and a parent-teacher meeting every term.

## Location and contact
Bright Minds Academy, Saddar, Rawalpindi. Phone and WhatsApp 0312-4445566. Office open Monday to Saturday, 2 pm to 9 pm.
""",
    },
    "salon": {
        "label": "Salon or beauty parlour",
        "blurb": "services, prices, bridal packages, bookings",
        "sample": "Glow Studio",
        "bot_name": "Glow Studio Assistant",
        "color": "#5E3A6E",
        "greeting": "Hi! Ask me about our services, prices, bridal packages or booking an appointment. English or Roman Urdu both work.",
        "quick_replies": ["Bridal package price?", "Book an appointment", "Facial ki price?", "Home service available?"],
        "questions": {
            "need": "Which service are you interested in (for example bridal makeup, a facial or a haircut)?",
            "name": "May I have your name?",
            "phone": "What's the best phone number to confirm your booking?",
            "budget": "Do you have a budget in mind?",
            "timeline": "Which date would you like to book?",
        },
        "need_keywords": ["bridal", "makeup", "mehndi", "facial", "haircut", "hair colour", "keratin",
                          "manicure", "pedicure", "waxing", "threading", "party makeup"],
        "intent_words": ["book", "booking", "appointment", "date", "chahiye"],
        "stage_names": {"site_visit": "Appointment booked", "quote_sent": "Advance paid"},
        "synonyms": {
            "bridal": "bridal packages", "dulhan": "bridal packages", "shaadi": "bridal packages",
            "barat": "bridal packages", "walima": "bridal packages",
            "makeup": "makeup services", "facial": "services prices", "haircut": "services prices",
            "hair": "services prices", "keratin": "services prices", "waxing": "services prices",
            "appointment": "appointments booking", "book": "appointments booking",
            "home service": "home service", "ghar": "home service",
            "advance": "appointments booking advance", "pay": "payment",
        },
        "kb": """# Glow Studio (sample business for demo)

## About
Glow Studio is a women's salon in Lahore offering makeup, hair, skin and bridal services since 2016. All staff are women.

## Services and prices
All services are for women only. Haircut from Rs 1,500. Hair colour from Rs 4,000. Keratin treatment from Rs 12,000. Facial from Rs 3,000. Manicure or pedicure Rs 1,800 each. Full arms waxing Rs 1,200. Threading Rs 300. Party makeup Rs 6,000.

## Bridal packages
Barat bridal makeup from Rs 45,000. Walima makeup from Rs 35,000. Mehndi makeup from Rs 20,000. Every bridal package includes a trial, hair styling, dupatta setting and a pre-bridal facial.

## Appointments and booking
Book through this chat, by phone or on WhatsApp. Bridal bookings need a 30 percent advance to confirm the date; the advance is not refundable within 15 days of the event.

## Home service
Bridal and party makeup can be done at home within Lahore for an extra Rs 5,000.

## Payment
Cash, card, JazzCash and Easypaisa are accepted.

## Timings and contact
Open Tuesday to Sunday, 11 am to 8 pm; closed on Mondays. Glow Studio, MM Alam Road, Lahore. Phone and WhatsApp 0322-9876543.
""",
    },
    "blank": {
        "label": "Start from scratch",
        "blurb": "empty sections to fill in",
        "sample": "My business",
        "bot_name": "Assistant",
        "color": "#047857",
        "greeting": "Hi! How can I help you today?",
        "quick_replies": ["What do you offer?", "What are your prices?", "How can I contact you?"],
        "questions": {
            "need": "What are you looking for?",
            "name": "May I know your name?",
            "phone": "What's the best phone number to reach you?",
            "budget": "Do you have a budget in mind?",
            "timeline": "When do you need it?",
        },
        "need_keywords": [],
        "intent_words": [],
        "stage_names": {"site_visit": "Meeting booked", "quote_sent": "Proposal sent"},
        "kb": """# My business

## About
Describe your business in two or three sentences: what you sell, where, and since when.

## Services
List what you offer.

## Pricing
Give starting prices for your main products or services.

## Working hours and contact
When you are open and how customers can reach you.
""",
    },
}


def template(key):
    return TEMPLATES.get(key) or TEMPLATES["blank"]


def template_kb(key, name=None):
    """The template's starting text, with the sample business's name swapped for this business's."""
    t = template(key)
    text = (ROOT / t["kb_file"]).read_text(encoding="utf-8") if "kb_file" in t else t["kb"]
    if name and name != t["sample"]:
        text = text.replace(" (sample business for demo)", " (sample text: change it to your own details)")
        text = text.replace(t["sample"], name)
    return text


def template_bot_name(key, name):
    t = template(key)
    return t["bot_name"] if name == t["sample"] else f"{name} Assistant"[:40]


BASE_STAGES = {"new": "New", "contacted": "Contacted", "won": "Won", "lost": "Lost"}


def settings_from_template(key):
    t = template(key)
    out = {k: t[k] for k in ("quick_replies", "questions", "need_keywords", "intent_words")}
    out["stage_names"] = {**BASE_STAGES, **t["stage_names"]}  # the six pipeline stages, named for this industry
    return out


def settings(biz):
    """The business's bot settings, with any missing key filled from its template."""
    try:
        s = json.loads(biz.get("settings") or "{}")
    except json.JSONDecodeError:
        s = {}
    base = settings_from_template(biz.get("industry") or "blank")
    merged = {**base, **{k: v for k, v in s.items() if v not in (None, "")}}
    merged["stage_names"] = {**base["stage_names"], **(s.get("stage_names") or {})}
    return merged


def slugify(name):
    base = re.sub(r"[^a-z0-9]+", "-", (name or "business").lower()).strip("-")[:40] or "business"
    slug, n = base, 2
    while db.business_by_slug(slug):
        slug, n = f"{base}-{n}", n + 1
    return slug


def create_from_template(name, industry, website="", setup_done=0, slug=None):
    t = template(industry)
    return db.create_business(
        slug or slugify(name), name=name, industry=industry if industry in TEMPLATES else "blank", website=website,
        bot_name=template_bot_name(industry, name), greeting=t["greeting"], color=t["color"],
        settings=json.dumps(settings_from_template(industry)), kb_text=template_kb(industry, name), setup_done=setup_done)


def public_config(biz):
    """What the chat window needs to look right: safe to show anyone."""
    s = settings(biz)
    return {"slug": biz["slug"], "name": biz["name"], "bot_name": biz["bot_name"], "greeting": biz["greeting"],
            "color": biz["color"], "quick_replies": s["quick_replies"][:6]}


def bootstrap():
    """At start-up: make sure the original solar demo exists as a business and owns any older data."""
    first = db.business_by_slug("brightpath-solar")
    if not first:
        bid = create_from_template("BrightPath Solar", "solar", "", setup_done=1, slug="brightpath-solar")
        first = db.get_business(bid)
    db.adopt_orphans(first["id"])
    return first
