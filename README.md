# Daily briefing: AI, future of work, HR and business

Every morning at 7:30 AM IST, this tool:
1. Collects the last day's news from about 16 sources (listed in `config.py`).
2. Uses Claude to pick the important stories, sort them into your 6 categories, and summarize each one with a "why it matters" line.
3. Updates your web dashboard and sends the digest by email and/or Telegram.

It runs free on GitHub. The only cost is Claude API usage, which is roughly a few rupees per day.

## Setup (about 30-40 minutes, one time)

### Step 1: Create a GitHub account and repository
1. Sign up at github.com.
2. Click **New repository**. Name it `daily-briefing` and set it to **Public**. GitHub Pages is free only for public repos; the page shows public news only, and your keys stay secret.
3. Click **uploading an existing file** and drag in all the files from this folder. Keep the `.github/workflows` folder structure. If drag-and-drop skips hidden folders, create the file `.github/workflows/daily.yml` manually with **Add file > Create new file** and paste its contents.

### Step 2: Get an Anthropic API key
1. Go to console.anthropic.com, add a small credit balance (such as $5), then open **API Keys > Create key**.
2. Copy the key.

### Step 3: Add your secrets
In your repo, go to **Settings > Secrets and variables > Actions > New repository secret** and add:

| Secret | Value |
|---|---|
| `ANTHROPIC_API_KEY` | your key from Step 2 |

**For email (Gmail):**
1. Turn on 2-Step Verification in your Google account.
2. Go to myaccount.google.com/apppasswords and create an app password.

| Secret | Value |
|---|---|
| `GMAIL_USER` | your Gmail address |
| `GMAIL_APP_PASSWORD` | the 16-character app password |
| `EMAIL_TO` | where to send it (you can list several, separated by commas) |

**For Telegram:**
1. In Telegram, message **@BotFather**, send `/newbot`, and follow the prompts. Copy the bot token.
2. Send any message to your new bot.
3. Open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser and find `"chat":{"id": ...}`. That number is your chat ID.

| Secret | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | the token from BotFather |
| `TELEGRAM_CHAT_ID` | your chat ID |

You can set up email, Telegram, or both. Anything you leave out is skipped.

### Step 4: Turn on the dashboard
1. Go to **Settings > Pages**. Under Source, choose **Deploy from a branch**, then select branch `main` and folder `/docs`. Save.
2. GitHub shows your link, which looks like `https://<username>.github.io/daily-briefing/`.
3. *(Optional)* Go to **Settings > Secrets and variables > Actions > Variables** and add `DASHBOARD_URL` with that link, so your email and Telegram messages link to the dashboard.

### Step 5: Run it once
1. Go to the **Actions** tab and enable workflows if GitHub asks.
2. Open **Daily briefing** and click **Run workflow**.
3. After 1-3 minutes, check your email, Telegram, and dashboard link. From then on it runs every day automatically.

## Customising
- **Add or remove sources:** edit `FEEDS` in `config.py`. For any topic, `gnews("your keywords")` creates a Google News feed.
- **Change categories:** edit `CATEGORIES`. The description text is what the AI uses to sort stories, so make it specific.
- **Change the time:** edit the `cron` line in `daily.yml`. Times are in UTC, which is IST minus 5:30.
- **Past days:** each day's page is saved at `docs/archive/YYYY-MM-DD.html`.

## Troubleshooting
- **Run failed:** open the run in the Actions tab and read the red step. Most failures come from a wrong secret name or an API key without credit.
- **No email arrives:** check your spam folder, and confirm you used an app password, not your normal Gmail password.
- **Dashboard shows 404:** wait a few minutes after the first run, and check that the Pages settings point to `/docs`.
- **The 7:30 run is late:** GitHub's scheduled runs can be delayed by up to about 30 minutes at busy times. This is normal.
