from bs4 import BeautifulSoup as bs
from ctypes import c_float, c_int
from colorama import init, deinit, Fore, Style
from multiprocessing import Manager, Pool, Value
from os import mkdir, cpu_count
from os.path import expanduser, getsize, isfile, isdir, join as pjoin
from requests import get
from time import time
from tqdm import tqdm
from zipfile import ZipFile
import json

addons = [
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

addon_dir = '/usr/local/games/world-of-warcraft/drive_c/World of Warcraft/_retail_/Interface/AddOns/'
game_version = '1738749986%3A517'  # the code to filter the latest files page for retail addons
base_url = 'https://www.curseforge.com'
cache_dir = pjoin(expanduser('~'), '.cache', 'wow-addon-updates')
last_update_timestamps_file = pjoin(cache_dir, 'update-history.json')

if not isdir(cache_dir):
    mkdir(cache_dir)

if not isfile(last_update_timestamps_file):
    with open(last_update_timestamps_file, 'w') as f:
        f.write(json.dumps({addon: 0 for addon in addons}))

last_update = Manager().dict(json.load(open(last_update_timestamps_file)))
last_update_len = len(last_update)
addons_len = len(addons)

if last_update_len != addons_len:
    on_disk = last_update.keys()
    if last_update_len > addons_len:
        for addon in list(set(on_disk) - set(addons)):
            del last_update[addon]
    elif last_update_len < addons_len:
        for addon in list(set(addons) - set(on_disk)):
            if addon not in on_disk:
                last_update[addon] = 0

updateable = Manager().dict({})
size = Value(c_float)
updated = Value(c_int)


def find_update(addon_name):
    r = get(f'{base_url}/wow/addons/{addon_name}/files/all?filter-game-version={game_version}')
    soup = bs(r.text, 'html.parser')
    rows = soup.find_all('tr')

    for row in rows[1:]:
        cols = row.find_all('td')
        release_type = cols[0].text
        if 'R' in release_type:
            last_update_curse = int(cols[3].find('abbr').get('data-epoch'))
            if last_update_curse > last_update[addon_name]:
                file_url = cols[1].find('a')['href']
                updateable[addon_name] = file_url
                break


def update_addon(addon_name):

    file_url = updateable[addon_name]
    addon_start = time()
    out_path = pjoin(cache_dir, f'{addon_name}_latest.zip')
    r = get(f'{base_url}{file_url}')
    soup = bs(r.text, 'html.parser')
    a_tag_buttons = soup.find_all('a', {'class': 'button button--hollow'})

    for a_tag in a_tag_buttons:
        url = a_tag.get('href')
        if url.startswith(f'/wow/addons/{addon_name}/download/'):
            zip_file = get(f'{base_url}{url}/file')
            with open(out_path, 'wb') as f:
                f.write(zip_file.content)
                break

    ZipFile(out_path).extractall(addon_dir)  # extract file content to addon folder
    last_update[addon_name] = addon_start
    zip_size = getsize(out_path) / 1024 / 1024
    size.value += zip_size


def main():
    num_workers = cpu_count() * 2

    init()
    start = time()
    print(f'{Style.BRIGHT}{Fore.BLUE}::{Fore.RESET}'
          f' Checking for latest versions of {Fore.YELLOW}{addons_len}'
          f'{Fore.RESET} {"addons" if addons_len > 1 else "addon"}.{Style.RESET_ALL}\n')

    # check for lates versions
    with Pool(num_workers) as p:
        p.map(find_update, addons)

    # find_update populates updateable
    updateable_len = len(updateable)

    if updateable_len == 0:
        print(f'{Fore.CYAN}=>{Fore.RESET} All addons are up-to-date! '
              f'We\'re done here! ({round(time() - start, ndigits=2)}s)')

    else:
        print(f'{Style.BRIGHT}{Fore.BLUE}::{Fore.RESET}'
              f' Updating {Fore.YELLOW}{updateable_len if updateable_len > 1 else ""}'
              f'{Fore.RESET}{" addons" if updateable_len > 1 else "addon"}:{Style.RESET_ALL}'
              f'{Fore.LIGHTGREEN_EX}', ' '.join(sorted(updateable.keys())), Fore.RESET, '\n')

        tqdm.get_lock()  # ensures locks exist

        # update out-of-date addons
        with Pool(num_workers) as p:
            for _ in tqdm(p.imap_unordered(update_addon, updateable), total=updateable_len):
                pass

        # write updated timestamps to disk
        with open(last_update_timestamps_file, 'w') as fn:
            json.dump(dict(last_update), fn)

        print(f'\nsummary: {round(time() - start, ndigits=2)}s, {round(size.value, ndigits=2)}MB')

    deinit()


if __name__ == '__main__':
    main()
