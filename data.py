import requests
import os
import time
import random
import json
from bs4 import BeautifulSoup
from urllib.parse import urljoin, quote_plus
from datetime import datetime

# 尝试导入Selenium（可选）
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    print("[Warning] Selenium not installed. Install with: pip install selenium")
    print("[Warning] Will try requests library, but may encounter 403 errors")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'DNT': '1',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Cache-Control': 'max-age=0'
}

MIN_WAIT = 8  # 增加等待时间
MAX_WAIT = 15

FBREF_BASE_URL = 'https://fbref.com'
TM_BASE_URL = 'https://www.transfermarkt.com'
LEAGUE_URL = 'https://fbref.com/en/comps/9/Premier-League-Stats'

CACHE_DIR_FBREF = 'cache/fbref'
CACHE_DIR_TM = 'cache/transfermarkt'
OUTPUT_DIR = 'output'

# 使用Selenium还是requests
USE_SELENIUM = SELENIUM_AVAILABLE  # 如果Selenium可用就使用它


def safe_request(url, cache_path, force_refresh=False):
    """安全的HTTP请求函数，带缓存机制和Session支持"""
    if os.path.exists(cache_path) and not force_refresh:
        print(f"[Cache] Hit: {cache_path}")
        with open(cache_path, 'r', encoding='utf-8') as f:
            return f.read()

    print(f"[Network] Fetching: {url}")
    wait_time = random.uniform(MIN_WAIT, MAX_WAIT)
    print(f"  ...waiting for {wait_time:.1f} seconds...")
    time.sleep(wait_time)

    # 尝试使用Selenium
    if USE_SELENIUM and 'fbref.com' in url:
        try:
            html = fetch_with_selenium(url)
            if html:
                os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                with open(cache_path, 'w', encoding='utf-8') as f:
                    f.write(html)
                print(f"[Cache] Saved: {cache_path}")
                return html
        except Exception as e:
            print(f"[Warning] Selenium failed: {e}, trying requests...")

    # 使用requests作为备选
    try:
        session = requests.Session()
        session.headers.update(HEADERS)

        if 'fbref.com' in url and url != LEAGUE_URL:
            session.headers['Referer'] = FBREF_BASE_URL

        response = session.get(url, timeout=30, allow_redirects=True)
        response.raise_for_status()

        os.makedirs(os.path.dirname(cache_path), exist_ok=True)

        with open(cache_path, 'w', encoding='utf-8') as f:
            f.write(response.text)
        print(f"[Cache] Saved: {cache_path}")
        return response.text

    except requests.exceptions.HTTPError as e:
        print(f"[ERROR] HTTP Error for {url}: {e}")
        if e.response.status_code == 403:
            print("\n!!! FBref is blocking automated requests !!!")
            print("!!! SOLUTIONS: !!!")
            print("1. Install Selenium: pip install selenium")
            print("2. Download ChromeDriver from https://chromedriver.chromium.org/")
            print("3. Wait several hours before trying again")
            print("4. Use a VPN to change your IP address")
            print("5. Manually save HTML pages from your browser to cache/fbref/")
            raise SystemExit(f"Blocked by server: {e.response.status_code}")
        elif e.response.status_code == 429:
            print("!!! Too many requests. Please wait longer !!!")
            raise SystemExit(f"Rate limited: {e.response.status_code}")
        return None
    except Exception as e:
        print(f"[ERROR] Request failed for {url}: {e}")
        return None


def fetch_with_selenium(url):
    """使用Selenium获取页面（更像真实浏览器）"""
    print(f"[Selenium] Fetching with browser automation...")

    options = Options()
    options.add_argument('--headless')  # 无头模式
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument(f'user-agent={HEADERS["User-Agent"]}')

    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        driver.get(url)

        # 等待页面加载
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        # 额外等待JavaScript执行
        time.sleep(3)

        html = driver.page_source
        return html

    finally:
        if driver:
            driver.quit()


def parse_fbref_team_page(html, team_name):
    """解析FBref球队页面，提取球员信息"""
    soup = BeautifulSoup(html, 'html.parser')
    players = []

    # 查找标准统计表
    table = soup.find('table', {'id': 'stats_standard_9'})
    if not table:
        table = soup.find('table', class_='stats_table')

    if not table:
        print(f"[Warning] No player table found for {team_name}")
        return players

    rows = table.find('tbody').find_all('tr')

    for row in rows:
        if 'thead' in row.get('class', []):
            continue

        player_data = {}

        # 球员姓名和链接
        name_cell = row.find('th', {'data-stat': 'player'})
        if name_cell:
            a_tag = name_cell.find('a')
            if a_tag:
                player_data['name'] = a_tag.text.strip()
                player_data['fbref_url'] = urljoin(FBREF_BASE_URL, a_tag['href'])
                player_data['fbref_id'] = a_tag['href'].split('/')[3]

        # 国籍
        nation_cell = row.find('td', {'data-stat': 'nationality'})
        if nation_cell:
            nation_text = nation_cell.text.strip()
            player_data['nationality'] = nation_text.split()[-1] if nation_text else ''

        # 位置
        position_cell = row.find('td', {'data-stat': 'position'})
        if position_cell:
            player_data['position'] = position_cell.text.strip()

        # 年龄
        age_cell = row.find('td', {'data-stat': 'age'})
        if age_cell:
            player_data['age'] = age_cell.text.strip()

        # 出场次数
        games_cell = row.find('td', {'data-stat': 'games'})
        if games_cell:
            player_data['games'] = games_cell.text.strip()

        # 首发次数
        starts_cell = row.find('td', {'data-stat': 'games_starts'})
        if starts_cell:
            player_data['starts'] = starts_cell.text.strip()

        # 进球
        goals_cell = row.find('td', {'data-stat': 'goals'})
        if goals_cell:
            player_data['goals'] = goals_cell.text.strip()

        # 助攻
        assists_cell = row.find('td', {'data-stat': 'assists'})
        if assists_cell:
            player_data['assists'] = assists_cell.text.strip()

        if player_data.get('name'):
            player_data['team'] = team_name
            players.append(player_data)

    return players


def parse_transfermarkt_search(html, player_name):
    """解析Transfermarkt搜索结果，并返回球员详情页URL"""
    soup = BeautifulSoup(html, 'html.parser')
    player_info = {'search_name': player_name}

    # 查找球员搜索结果
    player_box = soup.find('div', {'id': 'schnellsuche'})
    if not player_box:
        return player_info

    # 获取第一个球员结果
    player_row = player_box.find('table', class_='items')
    if player_row:
        tbody = player_row.find('tbody')
        if tbody:
            first_row = tbody.find('tr')
            if first_row:
                # 球员链接
                name_cell = first_row.find('td', class_='hauptlink')
                if name_cell:
                    a_tag = name_cell.find('a')
                    if a_tag:
                        player_info['tm_name'] = a_tag.text.strip()
                        # 获取球员详情页URL（不是搜索URL）
                        profile_href = a_tag.get('href', '')
                        player_info['tm_profile_url'] = urljoin(TM_BASE_URL, profile_href)
                        # 提取球员ID
                        if '/profil/spieler/' in profile_href:
                            player_info['tm_player_id'] = profile_href.split('/')[-1]

                # 俱乐部
                club_cell = first_row.find('td', class_='zentriert')
                if club_cell:
                    club_imgs = club_cell.find_all('img')
                    if club_imgs:
                        player_info['tm_club'] = club_imgs[0].get('alt', '')

                # 市场价值
                value_cell = first_row.find('td', class_='rechts hauptlink')
                if value_cell:
                    player_info['market_value'] = value_cell.text.strip()

    return player_info


def parse_transfermarkt_profile(html, player_name):
    """解析Transfermarkt球员详情页，提取转会历史和职业生涯"""
    soup = BeautifulSoup(html, 'html.parser')
    profile_data = {
        'player_name': player_name,
        'transfer_history': [],  # 原始转会记录
        'career_history': [],  # 职业生涯效力记录（带时间段）
        'career_stats': {},
        'honours': []
    }

    # ========== 解析转会历史 ==========
    transfer_box = soup.find('div', class_='box', id=lambda x: x and 'transfers' in str(x).lower())
    if not transfer_box:
        transfer_tables = soup.find_all('div', class_='box')
        for box in transfer_tables:
            header = box.find('h2')
            if header and 'Transfer' in header.text:
                transfer_box = box
                break

    if transfer_box:
        transfer_table = transfer_box.find('table', class_='items')
        if transfer_table:
            tbody = transfer_table.find('tbody')
            if tbody:
                rows = tbody.find_all('tr')

                for row in rows:
                    if 'subhead' in row.get('class', []):
                        continue

                    transfer_entry = {}
                    cells = row.find_all('td')

                    # 赛季
                    season_cell = row.find('td', class_='zentriert')
                    if season_cell:
                        transfer_entry['season'] = season_cell.text.strip()

                    # 日期
                    date_cells = row.find_all('td', class_='zentriert')
                    if len(date_cells) > 1:
                        date_text = date_cells[1].text.strip()
                        transfer_entry['date'] = date_text
                        transfer_entry['date_parsed'] = parse_transfer_date(date_text)

                    # 离开的俱乐部
                    left_cells = row.find_all('td', class_='hauptlink')
                    if len(left_cells) > 0:
                        left_club = left_cells[0].find('a')
                        if left_club:
                            transfer_entry['from_club'] = left_club.get('title', left_club.text.strip())

                    # 加入的俱乐部
                    if len(left_cells) > 1:
                        joined_club = left_cells[1].find('a')
                        if joined_club:
                            transfer_entry['to_club'] = joined_club.get('title', joined_club.text.strip())

                    # 市场价值
                    mv_cell = row.find('td', class_='rechts')
                    if mv_cell:
                        transfer_entry['market_value_at_transfer'] = mv_cell.text.strip()

                    # 转会费
                    fee_cell = row.find('td', class_='rechts hauptlink')
                    if fee_cell:
                        transfer_entry['transfer_fee'] = fee_cell.text.strip()

                    if transfer_entry:
                        profile_data['transfer_history'].append(transfer_entry)

    # ========== 构建职业生涯效力记录（带时间段）==========
    profile_data['career_history'] = build_career_timeline(profile_data['transfer_history'])

    # ========== 解析荣誉奖项 ==========
    success_box = soup.find('div', class_='box', id=lambda x: x and 'erfolge' in str(x).lower())
    if not success_box:
        success_tables = soup.find_all('div', class_='box')
        for box in success_tables:
            header = box.find('h2')
            if header and ('Success' in header.text or 'Honour' in header.text or 'Award' in header.text):
                success_box = box
                break

    if success_box:
        success_table = success_box.find('table', class_='items')
        if success_table:
            tbody = success_table.find('tbody')
            if tbody:
                rows = tbody.find_all('tr')
                for row in rows:
                    honour = {}

                    year_cell = row.find('td', class_='zentriert')
                    if year_cell:
                        honour['year'] = year_cell.text.strip()

                    title_cell = row.find('td', class_='hauptlink')
                    if title_cell:
                        honour['title'] = title_cell.text.strip()

                    club_cells = row.find_all('td')
                    if len(club_cells) > 2:
                        honour['club'] = club_cells[2].text.strip()

                    if honour:
                        profile_data['honours'].append(honour)

    return profile_data


def parse_transfer_date(date_str):
    """解析转会日期为标准格式"""
    import re
    from datetime import datetime

    if not date_str or date_str == '-':
        return None

    # 常见格式: "Jul 1, 2019" 或 "01.07.2019"
    try:
        # 尝试英文格式
        if ',' in date_str:
            date_obj = datetime.strptime(date_str, '%b %d, %Y')
            return date_obj.strftime('%Y-%m-%d')
        # 尝试德文格式
        elif '.' in date_str:
            parts = date_str.split('.')
            if len(parts) == 3:
                return f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
    except:
        pass

    # 如果只有年份，返回该年7月1日（常见转会窗口）
    year_match = re.search(r'\b(19|20)\d{2}\b', date_str)
    if year_match:
        return f"{year_match.group()}-07-01"

    return None


def build_career_timeline(transfer_history):
    """从转会记录构建职业生涯时间线"""
    if not transfer_history:
        return []

    career = []

    # 按日期排序
    sorted_transfers = sorted(
        transfer_history,
        key=lambda x: x.get('date_parsed') or '1900-01-01'
    )

    for i, transfer in enumerate(sorted_transfers):
        to_club = transfer.get('to_club')
        start_date = transfer.get('date_parsed')

        if not to_club or not start_date:
            continue

        # 确定结束日期：下一次转会的日期，或者"present"
        if i < len(sorted_transfers) - 1:
            # 查找下一次离开该俱乐部的转会
            end_date = None
            for next_transfer in sorted_transfers[i + 1:]:
                if next_transfer.get('from_club') == to_club:
                    end_date = next_transfer.get('date_parsed')
                    break

            # 如果没找到明确的离开记录，使用下一次转会的日期
            if not end_date and sorted_transfers[i + 1].get('date_parsed'):
                end_date = sorted_transfers[i + 1].get('date_parsed')
        else:
            # 最后一次转会，假设仍在效力
            end_date = 'present'

        # 检查是否已经存在该俱乐部的记录（处理租借回归等情况）
        existing_club = None
        for club_record in career:
            if club_record['club'] == to_club:
                existing_club = club_record
                break

        if existing_club:
            # 更新结束日期（如果是回归老东家）
            if end_date == 'present' or (
                    existing_club['end_date'] != 'present' and end_date > existing_club['end_date']):
                existing_club['end_date'] = end_date
                if transfer.get('season'):
                    existing_club['seasons'].append(transfer['season'])
        else:
            # 新的俱乐部记录
            club_record = {
                'club': to_club,
                'start_date': start_date,
                'end_date': end_date,
                'seasons': [transfer.get('season')] if transfer.get('season') else [],
                'transfer_fee': transfer.get('transfer_fee', 'Unknown')
            }
            career.append(club_record)

    return career


def scrape_fbref_squads():
    """爬取FBref所有球队数据"""
    print("\n=== Starting FBref Squad Scrape ===")

    league_html = safe_request(LEAGUE_URL, os.path.join(CACHE_DIR_FBREF, '_league_premier-league.html'))
    if not league_html:
        print("Failed to fetch league page")
        return []

    soup = BeautifulSoup(league_html, 'html.parser')
    squad_links = []

    # 查找球队链接
    standings_table = soup.find('table', {'id': 'results2024-202591_overall'})
    if not standings_table:
        standings_table = soup.find('table', class_='stats_table')

    if standings_table:
        for cell in standings_table.find_all('td', {'data-stat': 'team'}):
            a_tag = cell.find('a')
            if a_tag and a_tag.has_attr('href'):
                squad_links.append(a_tag['href'])

    print(f"Found {len(squad_links)} teams")

    all_teams_data = []

    for idx, link in enumerate(squad_links, 1):
        try:
            parts = link.split('/')
            team_identifier = parts[4] if len(parts) > 4 else f"team_{idx}"
            squad_name = parts[3] if len(parts) > 3 else team_identifier

            squad_url = urljoin(FBREF_BASE_URL, link)
            cache_file = os.path.join(CACHE_DIR_FBREF, f'squad_{team_identifier}.html')

            print(f"\n[{idx}/{len(squad_links)}] Processing: {squad_name}")
            html = safe_request(squad_url, cache_file)

            if html:
                players = parse_fbref_team_page(html, squad_name)
                team_data = {
                    'team_name': squad_name,
                    'team_id': team_identifier,
                    'team_url': squad_url,
                    'players': players,
                    'player_count': len(players)
                }
                all_teams_data.append(team_data)
                print(f"  → Found {len(players)} players")

        except Exception as e:
            print(f"[Error] Processing {link}: {e}")

    print("\n=== FBref Scrape Complete ===")
    return all_teams_data


def scrape_transfermarkt_profiles(player_names):
    """爬取Transfermarkt球员数据，包括转会历史"""
    print(f"\n=== Starting Transfermarkt Scrape ({len(player_names)} players) ===")

    player_tm_data = []

    for idx, name in enumerate(player_names, 1):
        if idx > 50:  # 限制数量以避免被封
            print(f"\n[Limit] Stopping at 50 players for safety")
            break

        try:
            query = quote_plus(name)

            # 第一步：搜索球员
            search_url = f"{TM_BASE_URL}/schnellsuche/ergebnis/schnellsuche?query={query}"
            search_cache_file = os.path.join(CACHE_DIR_TM, f'search_{query}.html')

            print(f"[{idx}/{min(len(player_names), 50)}] Searching: {name}")
            search_html = safe_request(search_url, search_cache_file)

            if not search_html:
                continue

            # 解析搜索结果，获取球员详情页URL
            search_info = parse_transfermarkt_search(search_html, name)
            search_info['original_name'] = name

            # 第二步：如果找到球员详情页URL，爬取详情页
            if search_info.get('tm_profile_url'):
                profile_url = search_info['tm_profile_url']
                player_id = search_info.get('tm_player_id', query)

                profile_cache_file = os.path.join(CACHE_DIR_TM, f'profile_{player_id}.html')

                print(f"  → Fetching profile: {search_info.get('tm_name', name)}")
                profile_html = safe_request(profile_url, profile_cache_file)

                if profile_html:
                    # 解析球员详情页，包括转会历史
                    profile_data = parse_transfermarkt_profile(profile_html, name)

                    # 合并搜索信息和详情信息
                    combined_data = {**search_info, **profile_data}
                    player_tm_data.append(combined_data)

                    transfer_count = len(profile_data.get('transfer_history', []))
                    honours_count = len(profile_data.get('honours', []))
                    print(f"  → Found {transfer_count} transfers, {honours_count} honours")
                else:
                    # 如果详情页失败，至少保存搜索信息
                    player_tm_data.append(search_info)
            else:
                # 如果没找到详情页URL，保存搜索信息
                player_tm_data.append(search_info)

        except Exception as e:
            print(f"[Error] Processing {name}: {e}")

    print("\n=== Transfermarkt Scrape Complete ===")
    return player_tm_data


def save_results(teams_data, tm_data):
    """保存所有结果到JSON文件"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # 保存FBref球队和球员数据
    fbref_file = os.path.join(OUTPUT_DIR, f'fbref_data_{timestamp}.json')
    with open(fbref_file, 'w', encoding='utf-8') as f:
        json.dump(teams_data, f, ensure_ascii=False, indent=2)

    # 保存Transfermarkt数据
    tm_file = os.path.join(OUTPUT_DIR, f'transfermarkt_data_{timestamp}.json')
    with open(tm_file, 'w', encoding='utf-8') as f:
        json.dump(tm_data, f, ensure_ascii=False, indent=2)

    # 生成统计信息
    total_players = sum(team['player_count'] for team in teams_data)
    stats = {
        'scrape_date': timestamp,
        'total_teams': len(teams_data),
        'total_players': total_players,
        'tm_profiles_found': len([tm for tm in tm_data if tm.get('tm_url')])
    }

    stats_file = os.path.join(OUTPUT_DIR, f'scrape_stats_{timestamp}.json')
    with open(stats_file, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f"\n=== Data Saved to {OUTPUT_DIR} ===")
    print(f"  - {fbref_file}")
    print(f"  - {tm_file}")
    print(f"  - {stats_file}")

    return stats


def main():
    """主函数"""
    print("=" * 60)
    print("Football Data Scraper")
    print("=" * 60)

    if USE_SELENIUM:
        print("[Info] Using Selenium for better success rate")
    else:
        print("[Warning] Selenium not available, using requests")
        print("[Warning] FBref may block requests. Consider installing Selenium:")
        print("        pip install selenium")

    print("\nIf you encounter 403 errors, you can:")
    print("1. Manually save pages from browser to cache/fbref/")
    print("2. Install and use Selenium (see above)")
    print("3. Wait and try again later")
    print("=" * 60)

    # 创建目录
    os.makedirs(CACHE_DIR_FBREF, exist_ok=True)
    os.makedirs(CACHE_DIR_TM, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 1. 爬取FBref球队和球员数据
    teams_data = scrape_fbref_squads()

    if not teams_data:
        print("[Error] No team data collected. Exiting.")
        return

    # 2. 收集所有球员名字
    all_player_names = []
    for team in teams_data:
        for player in team['players']:
            all_player_names.append(player['name'])

    print(f"\nCollected {len(all_player_names)} player names")

    # 3. 爬取Transfermarkt数据
    tm_data = scrape_transfermarkt_profiles(all_player_names)

    # 4. 保存数据到JSON文件
    stats = save_results(teams_data, tm_data)

    # 5. 打印统计信息
    print("\n" + "=" * 60)
    print("SCRAPE SUMMARY")
    print("=" * 60)
    print(f"Teams scraped: {stats['total_teams']}")
    print(f"Players found: {stats['total_players']}")
    print(f"Transfermarkt profiles: {stats['tm_profiles_found']}")
    print("=" * 60)
    print("\nAll data saved to JSON files.")
    print("You can now use these files to build your networks.")


if __name__ == "__main__":
    main()