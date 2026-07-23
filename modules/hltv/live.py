import time

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from modules.config import HLTV_LIVE_DEBUG_PORT
from modules.hltv.common import chrome_options_factory, kill_orphan_chrome


def get_live_match_selenium(team_name: str):
    chrome_options = chrome_options_factory(port=HLTV_LIVE_DEBUG_PORT, window_size="800,600")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")
    chrome_options.add_argument("--disable-application-cache")
    chrome_options.add_argument("--disk-cache-size=0")
    chrome_options.add_argument("--media-cache-size=0")

    driver = None
    try:
        kill_orphan_chrome(HLTV_LIVE_DEBUG_PORT)
        driver = webdriver.Chrome(options=chrome_options)
        driver.get("https://www.hltv.org/matches")

        try:
            WebDriverWait(driver, 4).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".match-wrapper.live-match-container[live='true'] .match-teamname"))
            )
        except TimeoutException:
            return None

        time.sleep(1)
        soup = BeautifulSoup(driver.page_source, "html.parser")

        for match_elem in soup.select(".match-wrapper.live-match-container[live='true']"):
            team1_elem = match_elem.select_one(".match-teams .match-team:nth-of-type(1) .match-teamname")
            team2_elem = match_elem.select_one(".match-teams .match-team:nth-of-type(2) .match-teamname")

            if not (team1_elem and team2_elem):
                continue

            team1_name = team1_elem.get_text(strip=True).lower()
            team2_name = team2_elem.get_text(strip=True).lower()

            if team_name.lower() == team1_name or team_name.lower() == team2_name:
                # Build a small result object for the first matching live game
                score1_elem = match_elem.select_one(".match-team-livescore .match-team:nth-of-type(1) .current-map-score")
                score2_elem = match_elem.select_one(".match-team-livescore .match-team:nth-of-type(2) .current-map-score")
                event_elem = match_elem.select_one(".match-event")
                link_elem = match_elem.select_one("a.match-top.a-reset")

                score1 = score1_elem.get_text(strip=True) if score1_elem else "?"
                score2 = score2_elem.get_text(strip=True) if score2_elem else "?"

                event_name = "Unknown Event"
                if event_elem:
                    event_name = event_elem.get("data-event-headline", "").strip() or event_elem.get_text(strip=True)
                    if not event_name:
                        img_elem = event_elem.select_one(".match-event-logo")
                        if img_elem:
                            event_name = (img_elem.get("alt", "") or img_elem.get("title", "")).strip()

                base_hltv_url = "https://www.hltv.org"
                relative_link = link_elem.get("href") if link_elem else None
                full_link = base_hltv_url + relative_link if relative_link and relative_link.startswith("/") else base_hltv_url + "/matches"

                return {"team1": team1_elem.get_text(strip=True), "team2": team2_elem.get_text(strip=True), "score1": score1, "score2": score2, "event": event_name, "link": full_link}
        return None
    except Exception as e:
        return None
    finally:
        if driver:
            driver.quit()
