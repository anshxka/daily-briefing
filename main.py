"""Daily AI / HR / business briefing.
Fetches RSS feeds -> AI picks stories and writes short articles -> writes dashboard (docs/) -> sends email / Telegram.
"""
import datetime as dt
import html
import json
import os
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import feedparser
import requests
import trafilatura

from config import CATEGORIES, FEEDS, HOURS_BACK, MAX_ARTICLES, MAX_PER_CATEGORY, PER_FEED

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "")
ROOT = Path(__file__).parent
esc = html.escape


# ---------- 1. Collect ----------
def clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def fetch_articles():
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=HOURS_BACK)
    seen, articles = set(), []
    for source, url in FEEDS:
        try:
            feed = feedparser.parse(url, agent="Mozilla/5.0 (daily-briefing)")
        except Exception as e:
            print(f"skip {source}: {e}")
            continue
        count = 0
        for entry in feed.entries:
            if count >= PER_FEED:
                break
            t = entry.get("published_parsed") or entry.get("updated_parsed")
            if t and dt.datetime(*t[:6], tzinfo=dt.timezone.utc) < cutoff:
                continue
            title = clean(entry.get("title", ""))
            key = re.sub(r"\W+", "", title.lower())[:60]
            if not title or not entry.get("link") or key in seen:
                continue
            seen.add(key)
            count += 1
            articles.append({
                "id": len(articles),
                "title": title,
                "link": entry.get("link"),
                "source": source.replace("Google News: ", ""),
                "snippet": clean(entry.get("summary", ""))[:300],
            })
        print(f"{source}: {count} stories")
    return articles[:MAX_ARTICLES]


def call_gemini(prompt):
    """Free option: Google Gemini API (key from aistudio.google.com)."""
    model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        params={"key": os.environ["GEMINI_API_KEY"]},
        json={"contents": [{"parts": [{"text": prompt}]}],
              "generationConfig": {"responseMimeType": "application/json", "temperature": 0.3}},
        timeout=300,
    )
    if r.status_code != 200:
        raise SystemExit(f"Gemini error {r.status_code}: {r.text[:500]}")
    return "".join(p.get("text", "") for p in r.json()["candidates"][0]["content"]["parts"])


def call_claude(prompt):
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"],
                 "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": MODEL, "max_tokens": 8000,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=300,
    )
    r.raise_for_status()
    return "".join(b.get("text", "") for b in r.json()["content"])


# ---------- 2. Pick stories, read them, write articles ----------
ARTICLES_PER_CATEGORY = 4   # full articles per category (keeps the read to ~15 minutes)


def ask_ai(prompt):
    text = call_gemini(prompt) if os.getenv("GEMINI_API_KEY") else call_claude(prompt)
    return json.loads(text[text.find("{"): text.rfind("}") + 1])


def fetch_full_text(url):
    """Download the article page and pull out the main text (empty string if blocked)."""
    try:
        downloaded = trafilatura.fetch_url(url)
        text = trafilatura.extract(downloaded) if downloaded else ""
        return (text or "")[:5000]
    except Exception:
        return ""


def ask_claude(articles):
    cats = "\n".join(f'- "{k}": {name} - {brief}' for k, (name, brief, _) in CATEGORIES.items())
    items = "\n".join(f'[{a["id"]}] {a["title"]} ({a["source"]}) :: {a["snippet"]}' for a in articles)

    # Pass 1: choose and categorize
    picked = ask_ai(f"""You are the editor of a daily briefing for an HR and business professional who wants
situational awareness on AI, the future of work, HR, and corporate news.

Categories:
{cats}

Today's headlines (id in brackets):
{items}

Pick the most important, genuinely newsworthy stories. Skip fluff, ads, opinion clickbait and repeats of the
same event. Put each in exactly ONE category, at most {ARTICLES_PER_CATEGORY} per category, most important first.
Reply with ONLY valid JSON: {{"stories": [{{"id": 0, "category": "future_of_ai"}}]}}""")

    by_id = {a["id"]: a for a in articles}
    chosen = []
    counts = {k: 0 for k in CATEGORIES}
    for s in picked.get("stories", []):
        a, cat = by_id.get(s.get("id")), s.get("category")
        if a and cat in counts and counts[cat] < ARTICLES_PER_CATEGORY:
            counts[cat] += 1
            chosen.append({**a, "category": cat})

    # Read the full stories
    for a in chosen:
        a["full_text"] = fetch_full_text(a["link"])
        print(f"read {len(a['full_text'])} chars: {a['title'][:60]}")

    sources = "\n\n".join(
        f'[{a["id"]}] {a["title"]} ({a["source"]})\n{a["full_text"] or a["snippet"]}' for a in chosen)

    # Pass 2: write the articles
    written = ask_ai(f"""You write a daily news briefing for an HR and business professional. For each story below,
write a short news article in your own words that she can read instead of the original.

Rules for each article:
- A clear, factual headline.
- 3 to 4 paragraphs, about 180-250 words in total: what happened, the key details and numbers, the context,
  and what comes next. Separate paragraphs with a blank line (\\n\\n).
- "why": 2 sentences on what this means for HR and business professionals.
- Use only facts from the source text. If a source is only a short snippet, write a shorter article
  (1-2 paragraphs) and do not make up details, quotes or numbers.

Also write:
- "big_picture": 3 sentences connecting today's news into trends.
- "hr_tip": one concrete thing an HR professional could do or learn this week, based on today's news.

Stories:
{sources}

Reply with ONLY valid JSON:
{{"big_picture": ["...", "...", "..."], "hr_tip": "...",
  "stories": [{{"id": 0, "headline": "...", "article": "para 1\\n\\npara 2\\n\\npara 3", "why": "..."}}]}}""")

    texts = {s.get("id"): s for s in written.get("stories", [])}
    grouped = {k: [] for k in CATEGORIES}
    for a in chosen:
        w = texts.get(a["id"])
        if w and w.get("article"):
            grouped[a["category"]].append({**a, "headline": w.get("headline") or a["title"],
                                           "article": w["article"], "why": w.get("why", "")})
    return {"big_picture": written.get("big_picture", []), "hr_tip": written.get("hr_tip", ""), "grouped": grouped}


def paragraphs(text):
    return [p.strip() for p in re.split(r"\n\s*\n|\n", text or "") if p.strip()]


# ---------- 3. Dashboard ----------
def build_dashboard(brief, today):
    total = sum(len(v) for v in brief["grouped"].values())
    chips = ['<button class="chip on" data-cat="all">All <span>%d</span></button>' % total]
    sections = []
    for key, (name, _, color) in CATEGORIES.items():
        stories = brief["grouped"][key]
        if not stories:
            continue
        chips.append(f'<button class="chip" data-cat="{key}" style="--c:{color}">{esc(name)} <span>{len(stories)}</span></button>')
        cards = "".join(
            f'''<article class="story">
  <h3>{esc(s["headline"])}</h3>
  {"".join(f"<p>{esc(p)}</p>" for p in paragraphs(s["article"]))}
  <p class="why"><b>Why it matters:</b> {esc(s["why"])}</p>
  <p class="src">Source: <a href="{esc(s["link"])}" target="_blank" rel="noopener">{esc(s["source"])}</a></p>
</article>''' for s in stories)
        sections.append(f'<section class="cat" data-cat="{key}" style="--c:{color}"><h2>{esc(name)}</h2>{cards}</section>')

    bullets = "".join(f"<li>{esc(b)}</li>" for b in brief["big_picture"])
    page = (ROOT / "template.html").read_text(encoding="utf-8")
    return (page.replace("{{DATE}}", today.strftime("%A, %d %B %Y"))
                .replace("{{BIG_PICTURE}}", bullets)
                .replace("{{HR_TIP}}", esc(brief["hr_tip"]))
                .replace("{{CHIPS}}", "".join(chips))
                .replace("{{SECTIONS}}", "".join(sections))
                .replace("{{UPDATED}}", today.strftime("%d %b %Y, %I:%M %p IST")))


# ---------- 4. Email ----------
def build_email(brief, today):
    parts = [f'<div style="font-family:Arial,sans-serif;max-width:640px;margin:auto;color:#1f2937">'
             f'<h1 style="font-size:22px;margin-bottom:4px">Your daily briefing</h1>'
             f'<p style="color:#6b7280;margin-top:0">{today.strftime("%A, %d %B %Y")}</p>'
             f'<h2 style="font-size:16px">Today\'s big picture</h2><ul>'
             + "".join(f"<li style='margin-bottom:6px'>{esc(b)}</li>" for b in brief["big_picture"]) + "</ul>"
             f'<p style="background:#FFF7ED;border-left:4px solid #EA580C;padding:10px 12px">'
             f'<b>HR tip of the day:</b> {esc(brief["hr_tip"])}</p>']
    if DASHBOARD_URL:
        parts.append(f'<p><a href="{DASHBOARD_URL}">Open the full dashboard</a></p>')
    for key, (name, _, color) in CATEGORIES.items():
        stories = brief["grouped"][key]
        if not stories:
            continue
        parts.append(f'<h2 style="font-size:17px;border-bottom:2px solid {color};padding-bottom:4px;margin-top:28px">{esc(name)}</h2>')
        for s in stories:
            parts.append(
                f'<h3 style="font-size:17px;margin:22px 0 6px">{esc(s["headline"])}</h3>'
                + "".join(f'<p style="margin:0 0 10px;line-height:1.55">{esc(p)}</p>' for p in paragraphs(s["article"]))
                + f'<p style="margin:4px 0;color:#4b5563"><i>Why it matters:</i> {esc(s["why"])}</p>'
                f'<p style="margin:4px 0 0;font-size:12px"><a href="{esc(s["link"])}" style="color:#6b7280">Source: {esc(s["source"])}</a></p>')
    parts.append("</div>")
    return "".join(parts)


def send_email(html_body, today):
    user, pwd, to = os.getenv("GMAIL_USER"), os.getenv("GMAIL_APP_PASSWORD"), os.getenv("EMAIL_TO")
    if not (user and pwd and to):
        print("Email not configured - skipping")
        return
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Daily briefing - {today.strftime('%d %b %Y')}"
    msg["From"], msg["To"] = user, to
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(user, pwd)
        s.sendmail(user, [x.strip() for x in to.split(",")], msg.as_string())
    print("Email sent")


# ---------- 5. Telegram ----------
def send_telegram(brief, today):
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not (token and chat):
        print("Telegram not configured - skipping")
        return
    blocks = [f"<b>Daily briefing - {today.strftime('%d %b %Y')}</b>\n\n<b>Big picture</b>\n"
              + "\n".join(f"• {esc(b)}" for b in brief["big_picture"])
              + f"\n\n<b>HR tip:</b> {esc(brief['hr_tip'])}"]
    for key, (name, _, _) in CATEGORIES.items():
        stories = brief["grouped"][key][:3]
        if stories:
            blocks.append(f"<b>{esc(name)}</b>\n" + "\n\n".join(
                f'<a href="{esc(s["link"])}">{esc(s["headline"])}</a>\n{esc((paragraphs(s["article"]) or [""])[0])}' for s in stories))
    if DASHBOARD_URL:
        blocks.append(f'<a href="{DASHBOARD_URL}">Open full dashboard</a>')

    # Telegram limit is 4096 characters per message
    messages, current = [], ""
    for b in blocks:
        if len(current) + len(b) + 2 > 3900:
            messages.append(current)
            current = ""
        current += b + "\n\n"
    messages.append(current)
    for m in messages:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat, "text": m, "parse_mode": "HTML",
                            "disable_web_page_preview": True}, timeout=30).raise_for_status()
    print("Telegram sent")


def main():
    today = dt.datetime.now(IST)
    articles = fetch_articles()
    print(f"Collected {len(articles)} articles")
    if not articles:
        raise SystemExit("No articles found - check your feeds")
    brief = ask_claude(articles)

    docs = ROOT / "docs"
    (docs / "archive").mkdir(parents=True, exist_ok=True)
    page = build_dashboard(brief, today)
    (docs / "index.html").write_text(page, encoding="utf-8")
    (docs / "archive" / f"{today:%Y-%m-%d}.html").write_text(page, encoding="utf-8")
    print("Dashboard written to docs/index.html")

    for step in (lambda: send_email(build_email(brief, today), today), lambda: send_telegram(brief, today)):
        try:
            step()
        except Exception as e:
            print(f"Delivery error: {e}")


if __name__ == "__main__":
    main()
