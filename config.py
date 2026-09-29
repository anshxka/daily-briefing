"""Edit this file to change what the briefing covers."""
from urllib.parse import quote_plus


def gnews(query: str) -> str:
    """Google News RSS feed for any search query (India edition, English)."""
    return f"https://news.google.com/rss/search?q={quote_plus(query)}+when:1d&hl=en-IN&gl=IN&ceid=IN:en"


# key: (display name, what counts - this brief is sent to the AI, colour for the dashboard)
CATEGORIES = {
    "future_of_work": ("Future of work",
        "Remote/hybrid work, hiring and layoff trends, jobs being automated or created, skills shifts, workplace culture.",
        "#2563EB"),
    "future_of_ai": ("Future of AI",
        "New AI models and products, AI company moves and funding, AI regulation and policy, research breakthroughs.",
        "#7C3AED"),
    "ai_in_hr": ("AI in HR",
        "AI used in recruiting, onboarding, performance, learning and development, people analytics; HR tech launches.",
        "#0D9488"),
    "hr_evolution": ("How HR is evolving",
        "Changes in the HR function and CHRO role, labour laws and policy, employee experience, benefits, DEI, HR strategy.",
        "#DB2777"),
    "future_proof_hr": ("Future-proofing HR",
        "Reskilling and upskilling, new HR competencies, certifications, frameworks and practical playbooks HR people can use.",
        "#EA580C"),
    "business": ("Business & corporate",
        "Big corporate news: M&A, earnings, leadership changes, markets, economy - India and global.",
        "#475569"),
}

# (source name, RSS url). Broken or slow feeds are skipped automatically.
FEEDS = [
    # AI and tech
    ("MIT Technology Review", "https://www.technologyreview.com/topic/artificial-intelligence/feed"),
    ("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("The Verge AI", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ("VentureBeat AI", "https://venturebeat.com/category/ai/feed/"),
    # HR
    ("HR Dive", "https://www.hrdive.com/feeds/news/"),
    ("ETHRWorld", "https://hr.economictimes.indiatimes.com/rss/topstories"),
    ("Google News: SHRM", gnews("site:shrm.org")),
    ("Google News: People Matters", gnews("site:peoplematters.in")),
    ("Google News: AI in HR", gnews('"AI in HR" OR "HR tech" OR "AI recruiting"')),
    ("Google News: CHRO", gnews("CHRO OR \"chief people officer\"")),
    ("Google News: reskilling", gnews("reskilling OR upskilling workforce")),
    # Future of work
    ("Google News: future of work", gnews('"future of work"')),
    ("Google News: AI and jobs", gnews("AI jobs workforce layoffs hiring")),
    # Business
    ("Economic Times", "https://economictimes.indiatimes.com/rssfeedstopstories.cms"),
    ("Mint Companies", "https://www.livemint.com/rss/companies"),
    ("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml"),
]

HOURS_BACK = 30          # only keep stories from the last N hours
PER_FEED = 12            # max stories taken from each feed
MAX_ARTICLES = 140       # max stories sent to the AI for sorting
MAX_PER_CATEGORY = 6     # stories shown per category
