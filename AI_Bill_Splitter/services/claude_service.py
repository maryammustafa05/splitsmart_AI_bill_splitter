import os
import base64
import httpx
import json
import uuid
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama-3.3-70b-versatile"
HISTORY_FILE = "expense_history.json"

HEADERS = {
    "Authorization": f"Bearer {GROQ_API_KEY}",
    "Content-Type": "application/json"
}


def load_history() -> list:
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_to_history(entry: dict):
    history = load_history()
    history.append(entry)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


async def call_groq(messages: list, model: str = MODEL) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            API_URL,
            headers=HEADERS,
            json={"model": model, "messages": messages},
            timeout=30.0
        )
        if response.status_code != 200:
            print("GROQ ERROR:", response.text)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


async def get_summary(explanation: str, people_names: list, num_people: int) -> list:
    names = people_names if people_names else [f"Person {i+1}" for i in range(num_people)]
    messages = [
        {
            "role": "user",
            "content": f"""Based on this bill split explanation, extract each person's name and exact amount they owe in PKR.
Return ONLY a JSON array like this, nothing else:
[{{"name": "Ali", "amount": 500}}, {{"name": "Sara", "amount": 300}}]

People: {', '.join(names)}
Explanation: {explanation}"""
        }
    ]
    raw = await call_groq(messages)
    try:
        raw = raw.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception:
        return [{"name": name, "amount": 0} for name in names]


async def split_manual_bill(
    num_people: int,
    split_type: str,
    items: list,
    tax: float = 0.0,
    tip: float = 0.0,
    people_names: list = []
) -> dict:
    people_label = ", ".join(people_names) if people_names else f"{num_people} people"
    items_text = "\n".join(
        [f"- {item['name']}: Rs. {item['price']} x {item['quantity']}" for item in items]
    )

    prompt = f"""
You are a bill splitting assistant in Pakistan. All amounts are in Pakistani Rupees (Rs. / PKR).
Given the following bill details, calculate how much each person owes and explain clearly.

Number of people: {num_people}
People: {people_label}
Split type: {split_type}
Tax: Rs. {tax}
Tip: Rs. {tip}

Items:
{items_text}

Please:
1. Calculate the subtotal of all items in Rs.
2. Add tax and tip in Rs.
3. Split the total based on the split type (equal = divide everything equally, itemized = each person pays for what they ordered)
4. For each person, state exactly how much they owe in Rs. (Pakistani Rupees) and why
5. Give a friendly, clear explanation in plain English. Always use Rs. for all amounts, never use $ or USD.
"""

    explanation = await call_groq([{"role": "user", "content": prompt}])
    summary = await get_summary(explanation, people_names, num_people)

    entry = {
        "id": str(uuid.uuid4()),
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": "manual",
        "split_type": split_type,
        "num_people": num_people,
        "people_names": people_names,
        "items": items,
        "tax": tax,
        "tip": tip,
        "summary": summary,
        "explanation": explanation
    }
    save_to_history(entry)

    return {
        "success": True,
        "split_type": split_type,
        "num_people": num_people,
        "explanation": explanation,
        "summary": summary
    }

async def split_image_bill(
    image_bytes: bytes,
    image_content_type: str,
    num_people: int,
    split_type: str,
    people_names: list = []
) -> dict:

    names = people_names if people_names else [f"Person {i+1}" for i in range(num_people)]
    image_data = base64.b64encode(image_bytes).decode("utf-8")

    # ✅ STEP 1: Extract ONLY raw data (NO conversion)
    prompt = """
Extract structured data from this receipt.

Return ONLY valid JSON:
{
  "currency": "USD",
  "items": [
    {"name": "item", "price": number, "quantity": number}
  ],
  "tax": number,
  "tip": number
}

Rules:
- Do NOT convert currency
- Keep original currency (USD or PKR)
- Prices must be numbers only
- If quantity missing, assume 1
- If tax/tip missing, use 0
- No explanation
"""

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{image_content_type};base64,{image_data}"
                    }
                }
            ]
        }
    ]

    raw = await call_groq(messages, model="meta-llama/llama-4-scout-17b-16e-instruct")

    # ✅ STEP 2: Clean JSON safely
    def clean_json(raw_text: str):
        raw_text = raw_text.strip()
        if "```" in raw_text:
            parts = raw_text.split("```")
            for part in parts:
                if "{" in part:
                    raw_text = part
                    break
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
        return raw_text.strip()

    try:
        data = json.loads(clean_json(raw))
    except Exception:
        return {"success": False, "error": "Failed to parse receipt"}

    # ✅ STEP 3: Extract data
    currency = data.get("currency", "PKR")
    items = data.get("items", [])
    tax = float(data.get("tax", 0))
    tip = float(data.get("tip", 0))

    if not items:
        return {"success": False, "error": "No items detected"}

    # ✅ STEP 4: Convert currency in backend ONLY
    USD_TO_PKR = 275

    if currency.upper() == "USD":
        for item in items:
            item["price"] *= USD_TO_PKR
        tax *= USD_TO_PKR
        tip *= USD_TO_PKR

    # ✅ STEP 5: Calculate totals
    subtotal = sum(item["price"] * item["quantity"] for item in items)
    total = subtotal + tax + tip

    # ✅ STEP 6: Split logic
    summary = []

    if split_type == "equal":
        per_person = round(total / num_people, 2)
        summary = [{"name": name, "amount": per_person} for name in names]

    elif split_type == "itemized":
        balances = {name: 0 for name in names}

        for item in items:
            assigned = item.get("assigned_to", names)
            share = (item["price"] * item["quantity"]) / len(assigned)

            for person in assigned:
                balances[person] += share

        extra = (tax + tip) / num_people
        for person in balances:
            balances[person] += extra

        summary = [{"name": k, "amount": round(v, 2)} for k, v in balances.items()]

    # ✅ STEP 7: Explanation (safe, backend-generated)
    explanation = f"""
Subtotal: Rs. {subtotal:.2f}
Tax: Rs. {tax:.2f}
Tip: Rs. {tip:.2f}
Total: Rs. {total:.2f}

Split type: {split_type}

Each person owes:
""" + "\n".join([f"{p['name']}: Rs. {p['amount']}" for p in summary])

    # ✅ STEP 8: Save history
    entry = {
        "id": str(uuid.uuid4()),
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": "image",
        "split_type": split_type,
        "num_people": num_people,
        "people_names": people_names,
        "items": items,
        "tax": tax,
        "tip": tip,
        "summary": summary,
        "explanation": explanation
    }

    save_to_history(entry)

    return {
        "success": True,
        "split_type": split_type,
        "num_people": num_people,
        "items": items,
        "total": round(total, 2),
        "explanation": explanation,
        "summary": summary
    }


def get_expense_history() -> list:
    return load_history()