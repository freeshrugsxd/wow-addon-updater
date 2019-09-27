import json
from multiprocessing import Manager, Pool, Value
from os import cpu_count, mkdir
from os.path import expanduser, getsize, isdir, isfile, join as pjoin
from time import time
from zipfile import ZipFile

import cfscrape
from colorama import Fore, Style, deinit, init
from tqdm import tqdm
from bs4 import BeautifulSoup as bs

ADDONS = [
    'advancedinterfaceoptions',
    'advanced-tooltips',
    'azeritepowerweights',
    'azeritetooltip',
    'battlegroundenemies',
    'bigdebuffs',
    'big-wigs',
    'blizzmove',
    'dejacharacterstats',
    'details',
    'ealign-updated',
    'easy-frames',
    'faster-loot',
    'gladiatorlossa2',
    'grid2',
    'handynotes',
    'tomcats-tours-mechagon',
    'immersion',
    'little-wigs',
    'map-coords',
    'method-dungeon-tools',
    'nameplate-scrolling-combat-text',
    'omnibar',
    'omni-cc',
    'prat-3-0',
    'premade-filter',
    'premade-groups-filter',
    'raiderio',
    'range-display',
    'sarena',
    'scrap',
    'sexymap',
    'simulationcraft',
    'spy',
    'stat-weight-score',
    'tidy-plates-threat-plates',
    'trufigcd',
    'undermine-journal',
    'weakauras-2',
    'world-quest-tracker',
    'angry-assignments'
]

ADDON_DIR = '/usr/local/games/world-of-warcraft/drive_c/World of Warcraft/_retail_/Interface/AddOns/'
GAME_VERSION = '1738749986%3A517'  # the code to filter the latest files page for retail addons
BASE_URL = 'https://www.curseforge.com'

ALLOWED_RELEASE_TYPES = 'RB'  # [R = release, B = beta, A = alpha]

CACHE_DIR = pjoin(expanduser('~'), '.cache', 'wow-addon-updates')
UPDATE_CACHE = pjoin(CACHE_DIR, 'addon_updates.json')

if not isdir(CACHE_DIR):
    mkdir(CACHE_DIR)

if not isfile(UPDATE_CACHE):
    with open(UPDATE_CACHE, 'w') as f:
        f.write(json.dumps({addon: 0 for addon in ADDONS}))

UPDATEABLE = Manager().dict({})
SIZE = Value('d', 0.0)
UPDATED = Value('i', 0)
IDX = Value('i', 0)

LAST_UPDATE = Manager().dict(json.load(open(UPDATE_CACHE)))
LAST_UPDATE_LEN = len(LAST_UPDATE)
ADDONS_LEN = len(ADDONS)

if LAST_UPDATE_LEN != ADDONS_LEN:
    ON_DISK = LAST_UPDATE.keys()
    if LAST_UPDATE_LEN > ADDONS_LEN:
        for addon in list(set(ON_DISK) - set(ADDONS)):
            del LAST_UPDATE[addon]
    elif LAST_UPDATE_LEN < ADDONS_LEN:
        for addon in list(set(ADDONS) - set(ON_DISK)):
            if addon not in ON_DISK:
                LAST_UPDATE[addon] = 0


def find_update(addon_name):
    cfs = cfscrape.create_scraper()
    r = cfs.get(f'{BASE_URL}/wow/addons/{addon_name}/files/all?filter-game-version={GAME_VERSION}')
    soup = bs(r.text, 'html.parser')
    rows = soup.find_all('tr')

    print_looking_for_update(IDX.value)
    IDX.value += 1

    for row in rows[1:]:
        cols = row.find_all('td')
        release_type = cols[0].text.strip()
        if release_type in ALLOWED_RELEASE_TYPES:
            last_update_curse = int(cols[3].find('abbr').get('data-epoch'))
            if last_update_curse > LAST_UPDATE[addon_name]:
                file_url = cols[1].find('a')['href']
                UPDATEABLE[addon_name] = file_url
                break


def update_addon(addon_name):

    file_url = UPDATEABLE[addon_name]
    addon_start = time()
    out_path = pjoin(CACHE_DIR, f'{addon_name}.zip')
    cfs = cfscrape.create_scraper()
    r = cfs.get(f'{BASE_URL}{file_url}')
    soup = bs(r.text, 'html.parser')
    a_tag_buttons = soup.find_all('a', {'class': 'button button--hollow'})

    for a_tag in a_tag_buttons:
        url = a_tag.get('href')
        if url.startswith(f'/wow/addons/{addon_name}/download/'):
            cfs = cfscrape.create_scraper()
            zip_file = cfs.get(f'{BASE_URL}{url}/file')
            with open(out_path, 'wb') as f:
                f.write(zip_file.content)
                break

    ZipFile(out_path).extractall(ADDON_DIR)
    LAST_UPDATE[addon_name] = addon_start
    zip_size = getsize(out_path) / 1024 / 1024
    SIZE.value += zip_size


def print_looking_for_update(idx, eol=' '):
    anim = ['⠶', '⠦', '⠖', '⠲', '⠴']
    symbol = anim[int(idx / 2) % len(anim)]
    print(f'\r{Style.BRIGHT}{Fore.BLUE}{symbol}{Fore.RESET}'
          f' Checking for latest versions of {Fore.YELLOW}{ADDONS_LEN}'
          f'{Fore.RESET} {"addons" if ADDONS_LEN > 1 else "addon"}.{Style.RESET_ALL}', end=eol)


def main():
    num_workers = cpu_count() * 2

    init()
    start = time()

    # check for lates versions
    with Pool(num_workers) as p:
        p.map(find_update, ADDONS)

    print_looking_for_update(idx=0, eol='\n\n')

    # find_update populates updateable
    updateable_len = len(UPDATEABLE)

    if updateable_len == 0:
        print(f'{Fore.CYAN}=>{Fore.RESET} All addons are up-to-date! '
              f'We\'re done here! ({round(time() - start, ndigits=2)}s)')

    else:
        print(f'{Style.BRIGHT}{Fore.CYAN}=>{Fore.RESET}'
              f' Updating {Fore.YELLOW}{updateable_len if updateable_len > 1 else ""}'
              f'{Fore.RESET}{" addons" if updateable_len > 1 else "addon"}:{Style.RESET_ALL}'
              f'{Fore.LIGHTGREEN_EX}', ' '.join(sorted(UPDATEABLE.keys())), Fore.RESET, '\n')

        tqdm.get_lock()  # ensures locks exist

        # update out-of-date addons
        with Pool(num_workers) as p:
            for _ in tqdm(p.imap_unordered(update_addon, UPDATEABLE), total=updateable_len):
                pass

        # write updated timestamps to disk
        with open(UPDATE_CACHE, 'w') as fn:
            json.dump(dict(LAST_UPDATE), fn)

        print(f'\nsummary: {round(time() - start, ndigits=2)}s, {round(SIZE.value, ndigits=2)}MB')

    deinit()


if __name__ == '__main__':
    main()
