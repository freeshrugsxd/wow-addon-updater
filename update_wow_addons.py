from configparser import ConfigParser
from multiprocessing import Manager, Pool, Value
from os import cpu_count, mkdir
from os.path import dirname, expanduser, getsize, isdir, isfile, join as pjoin
from time import time
from zipfile import ZipFile

import cfscrape
from colorama import Fore, Style, deinit, init
from tqdm import tqdm
from bs4 import BeautifulSoup as bs

OVERWRITE = False

CONFIG_FILE = pjoin(dirname(__file__), 'update_wow_addons.config')
if not isfile(CONFIG_FILE):
    exit(f'Error: Config file \'{CONFIG_FILE}\' not found.')

CONFIG = ConfigParser(allow_no_value=True, interpolation=None)

with open(CONFIG_FILE, 'r') as f:
    CONFIG.read_file(f)

GAME_VERSION = CONFIG['settings']['version'].lower()
if GAME_VERSION not in ['classic', 'retail']:
    exit(f'Error: Game version \'{GAME_VERSION}\' not recognized. Must be either \'classic\' or \'retail\'.')

GAME_DIR = CONFIG['settings']['game directory']
if not isdir(GAME_DIR):
    exit(f'Error: \'{GAME_DIR}\' is not a directory.')

ADDON_DIR = pjoin(GAME_DIR, f'_{GAME_VERSION}_', 'Interface', 'AddOns')
if not isdir(ADDON_DIR):
    exit(f'Error: \'{ADDON_DIR}\' is not a directory.')

CACHE_DIR = pjoin(expanduser('~'), '.cache', 'wow-addon-updates')
if not isdir(CACHE_DIR):
    mkdir(CACHE_DIR)

ADDONS = Manager().dict({})

for name, last_update in CONFIG.items(GAME_VERSION):
    if last_update is None or OVERWRITE:
        last_update = 0.0
    ADDONS[name] = float(last_update)

ADDONS_LEN = len(ADDONS)
if ADDONS_LEN == 0:
    exit('Error: Empty addon list.')

# codes to filter the latest files page for specific game version
GAME_VERSIONS = {'classic': '1738749986%3A67408', 'retail': '1738749986%3A517'}
GAME_VERSION_FILTER = GAME_VERSIONS[GAME_VERSION]
ALLOWED_RELEASE_TYPES = 'RB'  # [R = release, B = beta, A = alpha]
BASE_URL = 'https://www.curseforge.com'

UPDATEABLE = Manager().dict({})
UPDATED = Manager().dict({})
SIZE = Value('d', 0.0)
IDX = Value('i', 0)


def find_update(addon_name):
    cfs = cfscrape.create_scraper()
    r = cfs.get(f'{BASE_URL}/wow/addons/{addon_name}/files/all?filter-game-version={GAME_VERSION_FILTER}')
    soup = bs(r.text, 'html.parser')
    rows = soup.find_all('tr')

    print_looking_for_update(IDX.value)
    IDX.value += 1

    for row in rows[1:]:
        cols = row.find_all('td')
        release_type = cols[0].text.strip()
        if release_type in ALLOWED_RELEASE_TYPES:
            last_update_curse = int(cols[3].find('abbr').get('data-epoch'))
            if last_update_curse > ADDONS[addon_name]:
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
    UPDATED[addon_name] = addon_start
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

        for addon_name, timestamp in UPDATED.items():
            CONFIG[GAME_VERSION][addon_name] = str(timestamp)

        with open(CONFIG_FILE, 'w') as f:
            CONFIG.write(f)

        print(f'\nsummary: {round(time() - start, ndigits=2)}s, {round(SIZE.value, ndigits=2)}MB')

    deinit()


if __name__ == '__main__':
    main()
