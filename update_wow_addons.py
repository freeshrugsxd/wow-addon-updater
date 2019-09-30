from configparser import ConfigParser
from multiprocessing import Pool
from os import cpu_count, mkdir
from os.path import dirname, expanduser, getsize, isdir, isfile, join as pjoin
from random import randint
from time import time
from zipfile import ZipFile

import cfscrape
from colorama import Fore, Style, deinit, init
from tqdm import tqdm
from bs4 import BeautifulSoup as bs


class Updater:
    def __init__(self):
        self.debug = False  # changes game dir and always updates some random addons

        self.cache_dir = pjoin(expanduser('~'), '.cache', 'wow-addon-updates')
        if not isdir(self.cache_dir):
            if not isdir(dirname(self.cache_dir)):
                mkdir(dirname(self.cache_dir))
            mkdir(self.cache_dir)

        self.config_file = pjoin(dirname(__file__), 'update_wow_addons.config')
        self.config = ConfigParser(allow_no_value=True, interpolation=None)
        assert isfile(self.config_file), exit(f'Error: Config file \'{self.config_file}\' not found.')

        with open(self.config_file, 'r') as f:
            self.config.read_file(f)

        self.game_version = self.config['settings']['version'].lower()
        assert self.game_version in ['classic', 'retail'], exit(f'Error: Game version \'{self.game_version}\' not recognized. Must be either \'classic\' or \'retail\'.')

        self.game_dir = self.config['settings']['game directory']
        assert isdir(self.game_dir), exit(f'Error: \'{self.game_dir}\' is not a directory.')

        if self.debug:
            debug_dir = '/home/silvio/tmp/updater_test'
            self.game_dir = debug_dir
            print(f'Running in debug mode. Changing game directory to \'{debug_dir}\' and updating random addons.')

        self.addon_dir = pjoin(self.game_dir, f'_{self.game_version}_', 'Interface', 'AddOns')
        assert isdir(self.addon_dir), exit(f'Error: \'{self.addon_dir}\' is not a directory.')

        self.addons = {}
        self.size = 0.0

        for name, last_update in self.config.items(self.game_version):
            if last_update is None or (self.debug and bool(randint(0, 1))):
                last_update = 0.0
            self.addons[name] = float(last_update)

        self.addons_len = len(self.addons)
        if self.addons_len == 0:
            exit('Error: Empty addon list.')

        # codes to filter the latest files page for specific game version
        game_versions = {'classic': '1738749986%3A67408', 'retail': '1738749986%3A517'}
        self.game_version_filter = game_versions[self.game_version]
        self.allowed_release_types = 'RB'  # [R = release, B = beta, A = alpha]
        self.base_url = 'https://www.curseforge.com'

    def find_update(self, addon_name):
        cfs = cfscrape.create_scraper()
        r = cfs.get(f'{self.base_url}/wow/addons/{addon_name}/files/all?filter-game-version={self.game_version_filter}')
        soup = bs(r.text, 'html.parser')
        rows = soup.find_all('tr')

        # self.print_looking_for_update(idx.value)
        # idx.value += 1

        for row in rows[1:]:
            cols = row.find_all('td')
            release_type = cols[0].text.strip()
            if release_type in self.allowed_release_types:
                last_update_curse = int(cols[3].find('abbr').get('data-epoch'))
                if last_update_curse > self.addons[addon_name]:
                    file_url = cols[1].find('a')['href']
                    return addon_name, file_url

    def update_addon(self, tup):
        addon_name, file_url = tup
        addon_start = time()
        out_path = pjoin(self.cache_dir, f'{addon_name}.zip')
        cfs = cfscrape.create_scraper()
        r = cfs.get(f'{self.base_url}{file_url}')
        soup = bs(r.text, 'html.parser')
        a_tag_buttons = soup.find_all('a', {'class': 'button button--hollow'})

        for a_tag in a_tag_buttons:
            url = a_tag.get('href')
            if url.startswith(f'/wow/addons/{addon_name}/download/'):
                cfs = cfscrape.create_scraper()
                zip_file = cfs.get(f'{self.base_url}{url}/file')
                with open(out_path, 'wb') as f:
                    f.write(zip_file.content)
                    break

        ZipFile(out_path).extractall(self.addon_dir)
        zip_size = getsize(out_path) / 1024 / 1024
        return addon_name, addon_start, zip_size

    def print_looking_for_update(self, idx, eol=' '):
        anim = ['⠶', '⠦', '⠖', '⠲', '⠴']
        symbol = anim[int(idx / 2) % len(anim)]
        print(f'\r{Style.BRIGHT}{Fore.BLUE}{symbol}{Fore.RESET}'
              f' Checking for latest versions of {Fore.YELLOW}{self.addons_len}'
              f'{Fore.RESET} {"addons" if self.addons_len > 1 else "addon"}.{Style.RESET_ALL}', end=eol)

    def main(self):
        num_workers = cpu_count() * 2

        init()
        start = time()

        self.print_looking_for_update(idx=0, eol='\n\n')

        # check for lates versions
        with Pool(num_workers) as p:
            re = p.map(self.find_update, self.addons)

        keys = []
        updateable = []
        for i in re:
            if i:
                addon_name, file_url = i
                keys.append(addon_name)
                updateable.append((addon_name, file_url))

        # find_update populates updateable
        updateable_len = len(updateable)

        if updateable_len == 0:
            print(f'{Fore.CYAN}=>{Fore.RESET} All addons are up-to-date! '
                  f'We\'re done here! ({round(time() - start, ndigits=2)}s)')

        else:
            print(f'{Style.BRIGHT}{Fore.CYAN}=>{Fore.RESET}'
                  f' Updating {Fore.YELLOW}{updateable_len if updateable_len > 1 else ""}'
                  f'{Fore.RESET}{" addons" if updateable_len > 1 else "addon"}:{Style.RESET_ALL}'
                  f'{Fore.LIGHTGREEN_EX}', ' '.join(sorted(keys)), Fore.RESET, '\n')

            tqdm.get_lock()  # ensures locks exist

            # update out-of-date addons
            with Pool(num_workers) as p:
                for addon, ts, size in tqdm(p.imap_unordered(self.update_addon, updateable), total=updateable_len):
                    self.size += size
                    self.config.set(f'{self.game_version}', addon, str(ts))

            with open(self.config_file, 'w') as f:
                self.config.write(f)

            print(f'\nsummary: {round(time() - start, ndigits=2)}s, {round(self.size, ndigits=2)}MB')

        deinit()


if __name__ == '__main__':
    # idx = Value('i', 0)
    wup = Updater()
    wup.main()