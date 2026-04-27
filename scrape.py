import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
import time
import re

# Takes the base URL
BASE_URL = "https://12thman.com/boxscore.aspx?id="

# Range of valid game IDs to search for and scrape data
CUSTOM_GAME_IDS = (
    list(range(23580, 23589)) +   # Nonconference
    [23503, 23568] +              # Tournament
    list(range(23589, 23592)) +   # More nonconference
    list(range(23608, 23623))     # Conference
)

TARGET_TEAM = "Texas A&M"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def clean_name(text):
    # Gets team name and removes unused data
    text = re.sub(r'\(.*?\)', '', text)
    text = re.sub(r'\s*-\s*\d+$', '', text)
    return text.strip()


def clean_filename(title):
    # Remove invalid characters
    safe_title = re.sub(r'[\\/*?:"<>|]', "", title)
    return safe_title.strip()


def get_team_name_from_table(table):
    # Gets the team name
    if table.caption:
        return clean_name(table.caption.get_text(strip=True))

    curr = table
    # Finds the header
    for _ in range(10):
        for sibling in curr.find_previous_siblings(["h2", "h3", "h4", "header", "div", "span"]):
            text = sibling.get_text(strip=True)
            upper_text = text.upper()

            if not text:
                continue
            if any(x in upper_text for x in ["STATS", "BOX SCORE", "GAME TOTALS", "MEN'S BASKETBALL", "SCORE"]):
                continue

            return clean_name(text)

        if curr.parent:
            curr = curr.parent
        else:
            break

    return "Unknown Team"


def scrape_game(game_id):
    url = f"{BASE_URL}{game_id}"
    print(f"Scraping {url}...")

    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"Request failed: {e}")
        return None, None

    soup = BeautifulSoup(r.text, "html.parser")
    tables = soup.find_all("table")

    player_stats = []
    teams_found_in_order = []
    game_title = f"Game_{game_id}"  # Added for the case where A&M plays same team twice

    # Identify the opponent and A&M team
    for table in tables:
        rows = table.find_all("tr")
        if not rows:
            continue

        is_stats_table = False
        for row in rows[:2]:
            txt = [c.get_text(strip=True).upper() for c in row.find_all(["th", "td"])]
            if "MIN" in txt or "MP" in txt:
                is_stats_table = True
                break

        if is_stats_table:
            t_name = get_team_name_from_table(table)
            if t_name and t_name != "Unknown Team" and t_name not in teams_found_in_order:
                teams_found_in_order.append(t_name)

    # Makes the correct title
    if len(teams_found_in_order) >= 2:
        game_title = f"{teams_found_in_order[0].upper()} VS {teams_found_in_order[1].upper()}"

    # Extracts our data
    for i, table in enumerate(tables):
        rows = table.find_all("tr")
        if not rows:
            continue

        headers = []
        header_row_index = 0

        # Check headers
        for idx, row in enumerate(rows[:2]):
            cells = row.find_all(["th", "td"])
            txt = [c.get_text(strip=True).upper() for c in cells]
            if "MIN" in txt or "MP" in txt:
                headers = [c.get_text(strip=True) for c in cells]
                header_row_index = idx
                break

        if not headers:
            continue

        current_table_team = get_team_name_from_table(table)

        for row in rows[header_row_index + 1:]:
            cells = row.find_all(["td", "th"])
            cell_values = [c.get_text(strip=True) for c in cells]

            if not cell_values or not cell_values[0]:
                continue

            # Get the totals
            is_totals = "TOTAL" in cell_values[0].upper() or (
                    len(cell_values) > 1 and "TOTAL" in cell_values[1].upper()
            )

            if is_totals:
                row_dict = {h: "" for h in headers}
                rev_headers = list(reversed(headers))
                rev_cells = list(reversed(cell_values))

                for k, h in enumerate(rev_headers):
                    if k < len(rev_cells):
                        row_dict[h] = rev_cells[k]

                if len(headers) > 1:
                    row_dict[headers[1]] = "Totals"

                row_dict['game_id'] = game_id
                row_dict['team'] = current_table_team
                player_stats.append(row_dict)
                continue

            # 2. Skips dead ball statistics
            if "TM" in cell_values[0].upper() or (len(cell_values) > 1 and "TEAM" in cell_values[1].upper()):
                continue

            # 3. Standard Player
            if len(cells) != len(headers):
                continue

            row_dict = dict(zip(headers, cell_values))
            row_dict['game_id'] = game_id
            row_dict['team'] = current_table_team
            player_stats.append(row_dict)

    if not player_stats:
        return None, clean_filename(game_title)

    return pd.DataFrame(player_stats), clean_filename(game_title)


def main():
    os.makedirs("data", exist_ok=True)

    for game_id in CUSTOM_GAME_IDS:
        df, game_title = scrape_game(game_id)

        if df is not None and not df.empty:
            filename = f"{game_title}_{game_id}.csv"  # Avoids duplicate game titles
            file_path = os.path.join("data", filename)
            df.to_csv(file_path, index=False)
            print(f"Success! Saved {len(df)} rows to {file_path}")
        else:
            print(f"No data found for game {game_id}")

        time.sleep(1)  # Timer to avoid crashing site


if __name__ == "__main__":
    main()