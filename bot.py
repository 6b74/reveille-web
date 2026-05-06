import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import json
import asyncio
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import feedparser
import anthropic

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# ── Configuration ──────────────────────────────────────────────────────────────
BRIEF_CHANNEL_ID = 1482095132290318346  # fallback channel ID
BRIEF_HOUR_UTC = 13
BRIEF_MINUTE_UTC = 0
SEEN_FILE = "/data/seen.json"
CHANNELS_FILE = "/data/channels.json"
SEEN_EXPIRY_DAYS = 7
AUTHORIZED_USER_IDS = {
    514235621632376868,  # lasagna.jpeg
}

# ── RSS Feed Sources ───────────────────────────────────────────────────────────
RSS_FEEDS = [
    # --- US Military & DoD ---
    ("Defense One", "https://www.defenseone.com/rss/all/"),
    ("Military Times", "https://www.militarytimes.com/arc/outboundfeeds/rss/"),
    ("DoD News", "https://www.defense.gov/DesktopModules/ArticleCS/RSS.ashx?ContentType=1&Site=945&max=10"),
    ("Stars and Stripes", "https://www.stripes.com/arc/outboundfeeds/rss/"),
    ("Defense News", "https://www.defensenews.com/arc/outboundfeeds/rss/"),
    ("Task & Purpose", "https://taskandpurpose.com/feed/"),
    ("Breaking Defense", "https://breakingdefense.com/feed/"),
    ("USNI News", "https://news.usni.org/feed"),
    ("Naval News", "https://www.navalnews.com/feed/"),
    ("Aviation Week Defense", "https://aviationweek.com/rss/defense"),
    ("Space Force News", "https://www.spaceforce.mil/RSS/"),
    # --- Geopolitics & Think Tanks ---
    ("War on the Rocks", "https://warontherocks.com/feed/"),
    ("Foreign Policy", "https://foreignpolicy.com/feed/"),
    ("ISW", "https://www.understandingwar.org/rss.xml"),
    ("RAND Corporation", "https://www.rand.org/pubs/rss/research_briefs.xml"),
    ("Small Wars Journal", "https://smallwarsjournal.com/rss.xml"),
    # --- Intelligence & OSINT ---
    ("Recorded Future - The Record", "https://therecord.media/feed/"),
    ("Recorded Future - Insikt Group", "https://www.recordedfuture.com/research/insikt-group/feed"),
    ("Bellingcat", "https://www.bellingcat.com/feed/"),
    ("The War Zone", "https://www.twz.com/feed"),
    ("Oryx", "https://www.oryxspioenkop.com/feeds/posts/default"),
    ("CISA Alerts", "https://www.cisa.gov/cybersecurity-advisories/all.xml"),
    ("ODNI News", "https://www.dni.gov/index.php/newsroom/press-releases?format=feed&type=rss"),
    ("Krebs on Security", "https://krebsonsecurity.com/feed/"),
    # --- Vet Affairs ---

    ("VA News", "https://news.va.gov/feed/"),
]

# ── Bot setup ──────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ── Channel helpers ────────────────────────────────────────────────────────────
def load_channels() -> dict:
    if os.path.exists(CHANNELS_FILE):
        with open(CHANNELS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_channels(data: dict):
    os.makedirs(os.path.dirname(CHANNELS_FILE), exist_ok=True)
    with open(CHANNELS_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ── Seen articles helpers ──────────────────────────────────────────────────────
def load_seen() -> dict:
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            return json.load(f)
    return {}

def save_seen(data: dict):
    os.makedirs(os.path.dirname(SEEN_FILE), exist_ok=True)
    with open(SEEN_FILE, "w") as f:
        json.dump(data, f, indent=2)

def prune_seen(data: dict) -> dict:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=SEEN_EXPIRY_DAYS)).isoformat()
    return {url: ts for url, ts in data.items() if ts >= cutoff}

def mark_seen(urls: list):
    data = load_seen()
    data = prune_seen(data)
    now = datetime.now(timezone.utc).isoformat()
    for url in urls:
        data[url] = now
    save_seen(data)

# ── RSS Fetching ───────────────────────────────────────────────────────────────
def fetch_headlines() -> tuple[str, list]:
    seen = load_seen()
    seen = prune_seen(seen)
    all_headlines = []
    new_urls = []

    for source_name, url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                title = entry.get("title", "").strip()
                summary = entry.get("summary", "").strip()[:200]
                link = entry.get("link", "").strip()
                if not title or not link:
                    continue
                if link in seen:
                    continue
                all_headlines.append(f"[{source_name}] {title}\n{summary}")
                new_urls.append(link)
        except Exception as e:
            print(f"⚠️ Failed to fetch {source_name}: {e}")

    if not all_headlines:
        return "No new headlines since last brief.", []

    print(f"📰 Found {len(all_headlines)} new articles across {len(RSS_FEEDS)} feeds")
    return "\n\n".join(all_headlines), new_urls

# ── AI Brief Generation ────────────────────────────────────────────────────────
def generate_brief(headlines: str) -> str:
    eastern_time = datetime.now(timezone.utc) - timedelta(hours=5)
    today = eastern_time.strftime("%d %B %Y").upper()
    current_time = eastern_time.strftime("%H%M")

    prompt = f"""You are a military intelligence analyst writing a daily brief for a military Discord server. 
Based on the following headlines, write a concise, professional intel-style daily brief.

Format it EXACTLY like this:

DAILY BRIEF // {today} | {current_time} EASTERN

**EXECUTIVE SUMMARY**
[2 sentence overview of the most important developments across all categories]

**U.S. MILITARY & DOD**
• [bullet point]
• [bullet point]
• [bullet point]

**GEOPOLITICS & THINK TANKS**
• [bullet point]
• [bullet point]
• [bullet point]

**INTELLIGENCE & OSINT**
• [bullet point]
• [bullet point]
• [bullet point]

**VETERAN AFFAIRS**
• [bullet point]
• [bullet point]

**ANALYST NOTE**
[1-2 sentence closing observation or item to watch]


Keep bullet points to one sentence maximum. Be extremely concise. Use military terminology where appropriate. Do not editorialize or inject opinion. If a section has no relevant news, write "NSTR". Do not use emojis anywhere in the brief. The entire brief must fit within 1900 characters total to fit into one single discord post character limitations, including formatting.

HEADLINES:
{headlines}"""

    message = anthropic_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text

# ── Events ─────────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} ({bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash command(s)")
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")
    daily_brief.start()

# ── Slash Commands ─────────────────────────────────────────────────────────────
@bot.tree.command(name="setchannel", description="Set the channel for daily briefs in this server")
@app_commands.describe(channel="The channel to post daily briefs in")
async def setchannel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("❌ You need Manage Server permission to use this.", ephemeral=True)
        return
    data = load_channels()
    data[str(interaction.guild.id)] = channel.id
    save_channels(data)
    await interaction.response.send_message(
        f"✅ Daily briefs will now be posted in {channel.mention}.", ephemeral=True
    )

@bot.tree.command(name="brief", description="Generate and post today's daily brief right now")
async def brief(interaction: discord.Interaction):
    if interaction.user.id not in AUTHORIZED_USER_IDS:
        await interaction.response.send_message("❌ You are not authorized to use this command.", ephemeral=True)
        return
    await interaction.response.send_message("📰 Generating brief, stand by...", ephemeral=True)
    await post_brief(guild=interaction.guild, mark_as_seen=False)

@bot.tree.command(name="briefstatus", description="Check when the next daily brief is scheduled")
async def briefstatus(interaction: discord.Interaction):
    now = datetime.now(timezone.utc)
    target = now.replace(hour=BRIEF_HOUR_UTC, minute=BRIEF_MINUTE_UTC, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    delta = target - now
    hours = int(delta.total_seconds() // 3600)
    minutes = int((delta.total_seconds() % 3600) // 60)
    await interaction.response.send_message(
        f"📅 Next brief posts in **{hours}h {minutes}m** (0800 Eastern).", ephemeral=True
    )

@bot.tree.command(name="clearseen", description="Clear the seen articles cache")
async def clearseen(interaction: discord.Interaction):
    if interaction.user.id not in AUTHORIZED_USER_IDS:
        await interaction.response.send_message("❌ You are not authorized to use this command.", ephemeral=True)
        return
    if os.path.exists(SEEN_FILE):
        os.remove(SEEN_FILE)
        await interaction.response.send_message("🗑️ Seen articles cache cleared. Next brief will pull all available articles.", ephemeral=True)
    else:
        await interaction.response.send_message("Nothing to clear — cache is already empty.", ephemeral=True)

# ── Brief posting ──────────────────────────────────────────────────────────────
async def post_brief(guild: discord.Guild = None, mark_as_seen: bool = True):
    guilds_to_brief = [guild] if guild else bot.guilds

    print("📰 Fetching new headlines...")
    headlines, new_urls = await asyncio.to_thread(fetch_headlines)

    if not new_urls:
        print("ℹ️ No new articles found — skipping brief.")
        for g in guilds_to_brief:
            channels = load_channels()
            channel_id = channels.get(str(g.id), BRIEF_CHANNEL_ID)
            channel = bot.get_channel(channel_id)
            if channel:
                await channel.send("No new stories since the last brief. Check back tomorrow!")
        return

    print(f"🤖 Generating brief with Claude ({len(new_urls)} new articles)...")
    brief_text = await asyncio.to_thread(generate_brief, headlines)

    for g in guilds_to_brief:
        channels = load_channels()
        channel_id = channels.get(str(g.id), BRIEF_CHANNEL_ID)
        channel = bot.get_channel(channel_id)
        if not channel:
            print(f"❌ Could not find brief channel for {g.name}!")
            continue

        # Post the brief
        if len(brief_text) <= 2000:
            message = await channel.send(brief_text)
        else:
            chunks = [brief_text[i:i+1990] for i in range(0, len(brief_text), 1990)]
            message = None
            for chunk in chunks:
                message = await channel.send(chunk)

        # Create discussion thread
        today = datetime.now().strftime("%d %b %Y").upper()
        thread = await message.create_thread(
            name=f"DISCUSSION -- {today}",
            auto_archive_duration=4320
        )

        # Schedule thread deletion after 2 weeks
        async def delete_thread_later():
            await asyncio.sleep(1209600)  # 14 days
            try:
                await thread.delete()
                print(f"✅ Discussion thread deleted.")
            except Exception as e:
                print(f"⚠️ Could not delete thread: {e}")

        asyncio.create_task(delete_thread_later())

    if mark_as_seen:
        mark_seen(new_urls)
        print(f"✅ Brief posted! Marked {len(new_urls)} articles as seen.")
    else:
        print(f"✅ Brief posted! (manual run — articles not marked as seen)")

# ── Daily task ─────────────────────────────────────────────────────────────────
@tasks.loop(hours=24)
async def daily_brief():
    await post_brief(mark_as_seen=True)

@daily_brief.before_loop
async def before_brief():
    await bot.wait_until_ready()
    now = datetime.now(timezone.utc)
    target = now.replace(hour=BRIEF_HOUR_UTC, minute=BRIEF_MINUTE_UTC, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    seconds_to_wait = (target - now).total_seconds()
    hours = int(seconds_to_wait // 3600)
    minutes = int((seconds_to_wait % 3600) // 60)
    print(f"⏰ First brief in {hours}h {minutes}m (0800 Eastern)")
    await asyncio.sleep(seconds_to_wait)

# ── Run ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise ValueError("DISCORD_TOKEN not found!")
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not found!")
    bot.run(DISCORD_TOKEN)
