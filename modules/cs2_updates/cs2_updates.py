import asyncio
import html as html_lib
import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import urljoin

import aiohttp
import discord
from bs4 import BeautifulSoup, Tag
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from discord.ext import commands, tasks
from modules.config import (
    CS2_UPDATES_CACHE_FILE,
    CS2_UPDATES_CHANNEL_ID,
    CS2_UPDATES_DEBUG_PORT,
    CS2_UPDATES_POLL_MINUTES,
)
from modules.common import log_to_channel, safe_send
from modules.hltv.common import chrome_options_factory, kill_orphan_chrome


FEED_URL = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?appid=730&count=20&maxlength=5000"
CS_LOGO_URL = "https://mobbi.dev/cs.webp"
EXCLUDED_TITLE_WORDS = ("esports", "major", "tournament", "sale")
IMAGE_RE = re.compile(r"https?://\S+\.(?:png|jpg|jpeg|webp)")
URL_RE = re.compile(r"https?://\S+")
OG_IMAGE_RE = re.compile(r'<meta property="og:image" content="([^"]+)"')
META_DESCRIPTION_RE = re.compile(r'<meta\s+(?:property|name)="(?:og:description|Description)"\s+content="([^"]*)"', re.IGNORECASE)
PATCH_NOTE_PHRASE = "Updated to the latest version from the Community Workshop (Update Notes)."

# Future improvement
# Add a scheduled CS2 patch checker that runs only on Valves usual patch days
# (Tuesdays and Thursdays?) and at predefined times. This minimizes unnecessary checks

class CS2Updates(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        # Start the Steam news polling loop on load
        if not self.post_updates.is_running():
            self.post_updates.start()

    def cog_unload(self):
        self.post_updates.cancel()

    def _load_cache(self):
        # Read the seen-news cache so we only post new updates once
        if not CS2_UPDATES_CACHE_FILE.is_file():
            return {"seen_ids": []}

        try:
            cache = json.loads(CS2_UPDATES_CACHE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"seen_ids": []}

        if not isinstance(cache, dict):
            return {"seen_ids": []}

        cache.setdefault("seen_ids", [])
        return cache

    def _save_cache(self, cache):
        # Keep the seen news cache up to date
        CS2_UPDATES_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CS2_UPDATES_CACHE_FILE.write_text(
            json.dumps(cache, indent=2, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )

    @staticmethod
    def _is_patch_notes(item):
        title = (item.get("title") or "").lower()
        tags = item.get("tags") or []
        return "patchnotes" in tags or any(word in title for word in ("patch notes", "release notes"))

    @staticmethod
    def _is_relevant_item(item):
        title = (item.get("title") or "").lower()
        tags = item.get("tags") or []

        if "patchnotes" in tags:
            return True

        if any(word in title for word in ("regular update", "update")):
            return not any(word in title for word in EXCLUDED_TITLE_WORDS)

        return False

    @staticmethod
    def _is_heading_line(line: str) -> bool:
        if not line:
            return False
        if any(ch in line for ch in (".", "!", "?", "•")):
            return False
        words = line.split()
        if not words or len(words) > 5:
            return False
        return line[0].isupper()

    @staticmethod
    def _soft_wrap_text(text: str) -> str:
        if not text:
            return text

        if "[" in text and "](" in text:
            return text
        if "http://" in text or "https://" in text:
            return text

        # Steam identifiers and dotted names are long; zero-width spaces let Discord wrap them cleanly
        # without changing the visible text
        text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "\u200b", text)
        text = re.sub(r"\.(?=[A-Za-z0-9])", ".\u200b", text)
        return text

    def _clean_content(self, contents, title=None, limit=1100):
        text = (contents or "").replace("\r", "\n").replace("\\", "\n")
        text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
        text = IMAGE_RE.sub("", text)
        text = URL_RE.sub("", text)
        text = re.sub(r":\s*-\s*", ":\n- ", text)
        text = re.sub(r"\s-\s+(?=[A-Z])", "\n- ", text)
        text = re.sub(r"(?<=[.!?])\s*(?=[A-Z])", "\n", text)

        text = re.sub(
            rf"([A-Z][A-Za-z0-9'\- ]+?){re.escape(PATCH_NOTE_PHRASE)}",
            rf"\1\n{PATCH_NOTE_PHRASE}",
            text,
        )

        lines = []
        for raw_line in text.splitlines():
            line = " ".join(raw_line.split()).strip()
            if not line:
                if lines and lines[-1] != "":
                    lines.append("")
                continue

            if title and line.lower() == title.lower():
                continue
            if line.startswith("[") and line.endswith("]"):
                lines.append(f"**{line}**")
            elif self._is_heading_line(line):
                lines.append(f"**{line.rstrip(':')}**")
            else:
                lines.append(self._soft_wrap_text(line))

        body = "\n\n".join(lines)
        if len(body) > limit:
            body = body[: limit - 3].rstrip() + "..."
        return body

    @staticmethod
    def _extract_first_image_from_html(html, base_url=None):
        if not html:
            return None

        soup = BeautifulSoup(html, "html.parser")
        article = soup.select_one(".EventDetail") or soup

        # Prefer the first real content image inside the article body
        for node in article.find_all(style=True):
            style = node.get("style") or ""
            match = re.search(r'background-image:\s*url\(["\']?([^"\')]+)', style)
            if match:
                src = match.group(1)
                if "/ss_" in src or "steam/apps/730/ss_" in src:
                    return urljoin(base_url, src) if base_url else src

        body = soup.select_one(".EventDetailsBody")
        if body:
            for img in body.find_all("img"):
                src = img.get("src")
                if src:
                    if any(part in src.lower() for part in ("valve", "logo", "header_2x", "capsule_616x353")):
                        continue
                    return urljoin(base_url, src) if base_url else src

        return None

    @staticmethod
    def _fetch_article_html_sync(url):
        chrome_options = chrome_options_factory(port=CS2_UPDATES_DEBUG_PORT, window_size="1280,900")
        chrome_options.add_argument("--blink-settings=imagesEnabled=false")
        chrome_options.add_argument("--disable-application-cache")
        chrome_options.add_argument("--disk-cache-size=0")
        chrome_options.add_argument("--media-cache-size=0")

        driver = None
        try:
            kill_orphan_chrome(CS2_UPDATES_DEBUG_PORT)
            driver = webdriver.Chrome(options=chrome_options)
            driver.get(url)

            try:
                WebDriverWait(driver, 12).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".EventDetailsBody"))
                )
            except TimeoutException:
                pass

            time.sleep(1)
            return driver.page_source
        except Exception:
            return None
        finally:
            if driver:
                driver.quit()

    def _format_article_html(self, html, title=None, limit=1400):
        if not html:
            return None

        soup = BeautifulSoup(html, "html.parser")
        body = soup.select_one(".EventDetailsBody")
        if not body:
            description = soup.select_one('meta[property="og:description"]') or soup.select_one('meta[name="Description"]')
            if not description:
                return None

            return self._format_article_text(description.get("content"), title=title, limit=limit)

        blocks = []

        def render_inline(node):
            if not isinstance(node, Tag):
                return " ".join(str(node).split())

            name = node.name.lower()
            if name == "wbr":
                return ""
            if name == "a":
                text = " ".join(node.get_text(" ", strip=True).split())
                href = node.get("href")
                if href and text and href != text:
                    return f"[{self._soft_wrap_text(text)}]({href})"
                return self._soft_wrap_text(text)

            parts = []
            for child in node.children:
                rendered = render_inline(child)
                if rendered:
                    parts.append(rendered)
            return " ".join("".join(parts).split())

        def render_list(node, indent=0):
            rendered = []

            for li in node.find_all("li", recursive=False):
                text_parts = []

                for child in li.children:
                    if isinstance(child, Tag) and child.name.lower() in {"ul", "ol"}:
                        continue
                    inline_text = render_inline(child)
                    if inline_text:
                        text_parts.append(inline_text)

                text = " ".join("".join(text_parts).split()).strip()
                if text:
                    # Preserve Steams nested bullet hierarchy while formatting the text for discord
                    rendered.append(f"{'  ' * indent}• {self._soft_wrap_text(text)}")

                for child in li.children:
                    if isinstance(child, Tag) and child.name.lower() in {"ul", "ol"}:
                        rendered.extend(render_list(child, indent + 1))

            return rendered

        def render_node(node):
            if not isinstance(node, Tag):
                return
            name = node.name.lower()
            if name == "p":
                text = render_inline(node).strip()
                if not text or (title and text.lower() == title.lower()):
                    return
                if text.startswith("[") and text.endswith("]"):
                    blocks.append(f"**{text}**")
                elif self._is_heading_line(text):
                    blocks.append(f"**{text.rstrip(':')}**")
                else:
                    blocks.append(text)
                return

            if name in {"ul", "ol"}:
                bullet_lines = render_list(node)
                if bullet_lines:
                    blocks.append("\n\n".join(bullet_lines))
                return

            if name in {"div", "section", "article", "header", "main", "footer", "blockquote"}:
                for child in node.children:
                    render_node(child)

        for child in body.children:
            render_node(child)

        body_text = "\n\n".join(blocks)
        if len(body_text) > limit:
            body_text = body_text[: limit - 3].rstrip() + "..."
        return body_text

    def _format_article_text(self, text, title=None, limit=1400):
        if not text:
            return None

        blocks = []
        in_section = False
        previous_was_section = False

        for raw_line in text.replace("\r", "\n").splitlines():
            line = " ".join(raw_line.split()).strip()
            if not line or (title and line.lower() == title.lower()):
                continue

            if line.startswith("[") and line.endswith("]"):
                blocks.append(f"**{line}**")
                in_section = True
                previous_was_section = True
                continue

            if previous_was_section and self._is_heading_line(line) and not line.endswith(":"):
                blocks.append(f"**{line.rstrip(':')}**")
            elif in_section:
                blocks.append(f"• {self._soft_wrap_text(line)}")
            elif self._is_heading_line(line):
                blocks.append(f"**{line.rstrip(':')}**")
            else:
                blocks.append(self._soft_wrap_text(line))

            previous_was_section = False

        body_text = "\n\n".join(blocks)
        if len(body_text) > limit:
            body_text = body_text[: limit - 3].rstrip() + "..."
        return body_text

    @staticmethod
    def _article_url(item):
        url = item.get("url")
        if url:
            return url

        gid = item.get("gid")
        if gid:
            return f"https://store.steampowered.com/news/app/730/view/{gid}"
        return None

    async def _fetch_og_image(self, url):
        async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:
            async with session.get(url, timeout=20) as response:
                if response.status != 200:
                    return None
                html = await response.text()

        match = OG_IMAGE_RE.search(html)
        if match:
            return match.group(1)

        return None

    async def _fetch_meta_description(self, url):
        async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:
            for request_url in (url, f"{url}?l=english"):
                async with session.get(request_url, timeout=20) as response:
                    if response.status != 200:
                        continue
                    html = await response.text()

                match = META_DESCRIPTION_RE.search(html)
                if match:
                    return html_lib.unescape(match.group(1))

                soup = BeautifulSoup(html, "html.parser")
                description = soup.find("meta", attrs={"property": "og:description"}) or soup.find("meta", attrs={"name": "Description"})
                if description:
                    return description.get("content")

        return None

    async def _fetch_article_html(self, url):
        return await asyncio.to_thread(self._fetch_article_html_sync, url)

    async def _fetch_news(self):
        async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:
            async with session.get(FEED_URL, timeout=20) as response:
                response.raise_for_status()
                data = await response.json()

        items = data.get("appnews", {}).get("newsitems", [])
        return [item for item in items if self._is_relevant_item(item)]

    async def _build_embed(self, item):
        title = item.get("title") or "Counter-Strike 2"
        url = self._article_url(item)
        contents = item.get("contents") or ""
        is_patch_notes = self._is_patch_notes(item)
        excerpt_limit = 1400 if is_patch_notes else 1000
        excerpt = self._clean_content(contents, title=title, limit=excerpt_limit)
        has_structured_excerpt = False
        image_url = None

        if url:
            description = await self._fetch_meta_description(url)
            meta_excerpt = self._format_article_text(description, title=title, limit=excerpt_limit)
            if meta_excerpt:
                excerpt = meta_excerpt
                has_structured_excerpt = True

            # Use the rendered Steam page when available: that's where the section layout lives
            html = await self._fetch_article_html(url)
            if html:
                html_excerpt = self._format_article_html(html, title=title, limit=excerpt_limit)
                if html_excerpt and not has_structured_excerpt:
                    excerpt = html_excerpt
                    has_structured_excerpt = True

                image_url = self._extract_first_image_from_html(html, base_url=url)

        if not image_url and url:
            image_url = await self._fetch_og_image(url)

        embed = discord.Embed(
            title=f"🎮 {title}",
            url=url,
            description=excerpt,
            color=discord.Color.from_rgb(255, 140, 0),
        )

        embed.set_thumbnail(url=CS_LOGO_URL)
        if image_url:
            embed.set_image(url=image_url)

        embed.set_footer(text="Steam • CS2 • Patch Notes" if is_patch_notes else "Steam • CS2 • Regular Update")
        if item.get("date"):
            embed.timestamp = datetime.fromtimestamp(int(item["date"]), tz=timezone.utc)

        return embed

    @tasks.loop(minutes=CS2_UPDATES_POLL_MINUTES)
    async def post_updates(self):
        try:
            channel = self.bot.get_channel(CS2_UPDATES_CHANNEL_ID)
            if not channel:
                await log_to_channel(f"CS2 updates channel missing: {CS2_UPDATES_CHANNEL_ID}")
                return

            cache = await asyncio.to_thread(self._load_cache)
            seen_ids = set(cache.get("seen_ids", []))
            items = await self._fetch_news()

            current_ids = [item.get("gid") for item in items if item.get("gid")]

            if not seen_ids:
                cache["seen_ids"] = current_ids
                await asyncio.to_thread(self._save_cache, cache)
                return

            new_items = [item for item in items if item.get("gid") and item["gid"] not in seen_ids]

            for item in reversed(new_items):
                embed = await self._build_embed(item)
                await safe_send(channel, embed=embed)
                seen_ids.add(item["gid"])

            cache["seen_ids"] = list(seen_ids)
            await asyncio.to_thread(self._save_cache, cache)

        except Exception as exc:
            await log_to_channel(f"CS2 updates error: {exc}")

    @post_updates.before_loop
    async def before_post_updates(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    # Register the cog
    await bot.add_cog(CS2Updates(bot))
