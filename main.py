"""Daily AI / HR / business briefing.
Fetches RSS feeds -> Claude sorts & summarizes -> writes dashboard (docs/) -> sends email / Telegram.
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


# ---------- 2. Sort & summarize with Claude ----------
def ask_claude(articles):
    cats = "\n".join(f'- "{k}": {name} - {brief}' for k, (name, brief, _) in CATEGORIES.items())
    items = "\n".join(f'[{a["id"]}] {a["title"]} ({a["source"]}) :: {a["snippet"]}' for a in articles)
    prompt = f"""You are the editor of a daily briefing for an HR and business professional who wants
situational awareness on AI, the future of work, HR, and corporate news.

Categories:
{cats}

Today's articles (id in brackets):
{items}

Instructions:
- Pick the most important, genuinely newsworthy stories. Skip fluff, ads, duplicates of the same event, and anything irrelevant.
- Put each chosen story in exactly ONE category. At most {MAX_PER_CATEGORY} stories per category, most important first.
- For each story write "summary" (2 short sentences, plain English) and "why" (1 sentence: why it matters for HR/business professionals).
- "big_picture": 3 bullet sentences connecting today's news into trends.
- "hr_tip": one concrete thing an HR professional could do or learn this week to stay future-proof, based on today's news.
- Only use facts from the articles given. Do not invent details.

Reply with ONLY valid JSON, no markdown:
{{"big_picture": ["...", "...", "..."], "hr_tip": "...",
  "stories": [{{"id": 0, "category": "future_of_ai", "summary": "...", "why": "..."}}]}}"""

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
    text = "".join(b.get("text", "") for b in r.json()["content"])
    data = json.loads(text[text.find("{"): text.rfind("}") + 1])

    by_id = {a["id"]: a for a in articles}
    grouped = {k: [] for k in CATEGORIES}
    for s in data.get("stories", []):
        a = by_id.get(s.get("id"))
        cat = s.get("category")
        if a and cat in grouped and len(grouped[cat]) < MAX_PER_CATEGORY:
            grouped[cat].append({**a, "summary": s.get("summary", ""), "why": s.get("why", "")})
    return {"big_picture": data.get("big_picture", []), "hr_tip": data.get("hr_tip", ""), "grouped": grouped}


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
  <h3><a href="{esc(s["link"])}" target="_blank" rel="noopener">{esc(s["title"])}</a></h3>
  <p>{esc(s["summary"])}</p>
  <p class="why"><b>Why it matters:</b> {esc(s["why"])}</p>
  <p class="src">{esc(s["source"])}</p>
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
                f'<p style="margin:14px 0 2px"><a href="{esc(s["link"])}" style="color:#111827;font-weight:bold;text-decoration:none">{esc(s["title"])}</a></p>'
                f'<p style="margin:2px 0">{esc(s["summary"])}</p>'
                f'<p style="margin:2px 0;color:#4b5563"><i>Why it matters:</i> {esc(s["why"])}</p>'
                f'<p style="margin:2px 0;font-size:12px;color:#9ca3af">{esc(s["source"])}</p>')
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
                f'<a href="{esc(s["link"])}">{esc(s["title"])}</a>\n{esc(s["summary"])}' for s in stories))
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
