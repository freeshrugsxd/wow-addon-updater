from configparser import ConfigParser
from multiprocessing import Pool, Value
from os import cpu_count, mkdir
from os.path import dirname, expanduser, getsize, isdir, isfile, join as pjoin
from platform import system as pf_system
from random import randint
from time import time
from zipfile import ZipFile

import cfscrape
from colorama import Fore, Style, deinit, init
from tqdm import tqdm
from bs4 import BeautifulSoup as bs


class Updater:
    def __init__(self):
        self.testing = False  # if true, game dir changes and random addons are updated
        self.windows = pf_system() == 'Windows'
        self.not_windows = not self.windows
        self.base_url = 'https://www.curseforge.com'
        self.allowed_release_types = 'RB'  # [R = release, B = beta, A = alpha]
        assert self.allowed_release_types.upper() in 'RBA', 'Release Types must be R, B, A or any combination of them.'

        self.cache_dir = pjoin(expanduser('~'), '.cache', 'wow-addon-updates')
        if not isdir(self.cache_dir):
            if not isdir(dirname(self.cache_dir)):
                mkdir(dirname(self.cache_dir))
            mkdir(self.cache_dir)

        self.config_file = pjoin(dirname(__file__), 'update_wow_addons.config')
        assert isfile(self.config_file), exit(f'Error: No config file detected at \'{self.config_file}\'')

        with open(self.config_file, 'r') as f:
            self.config = ConfigParser(allow_no_value=True, interpolation=None)
            self.config.read_file(f)

        self.game_dir = self.config['settings']['game directory']
        assert isdir(self.game_dir), exit(f'Error: \'{self.game_dir}\' is not a valid'
                                          f' game directory.')

        if self.testing:
            test_dir = '/home/silvio/tmp/updater_test'
            self.game_dir = test_dir
            print(f'Running in testing mode. Changing game directory to \'{test_dir}\''
                  f' and updating random addons.\n')

        self.game_version = self.config['settings']['version']

        # codes to filter the latest files page for specific game version
        self.filters = {
            'classic': '1738749986%3A67408',
            'retail': '1738749986%3A517'
        }

        self.addons = []
        self.addons_len = 0
        self.size = 0.0

        game_versions = list(self.filters.keys())

        if self.game_version not in game_versions:
            versions = None
            if ',' in self.game_version:
                versions = list(set(self.game_version.split(',')))

            elif self.game_version in ['both', 'all']:
                versions = game_versions

            else:
                exit(f'Error: Unknown game version specified. \'{self.game_version}\''
                     f' is not a valid value. Must be either classic or retail')

            for v in versions:
                v = v.strip()
                if v in game_versions and len(v) > 0:
                    self.collect_addons(v)
                else:
                    exit(f'Error: Unknown game version specified. \'{self.game_version}\''
                         f' is not a valid value. Must be either classic, retail or both.')

        elif self.game_version in game_versions:
            self.collect_addons(self.game_version)
        else:
            exit(f'Error: Unknown game version specified. \'{self.game_version}\' '
                 f'is not a valid value. Must be either classic, retail or both.')

        self.addons_len = len(self.addons)
        assert self.addons_len > 0, exit(
            f'Error: No addons found in [{self.game_version}] section of the configuration file.')

        self.main()

    def collect_addons(self, version):

        for name, last_update in self.config.items(version):
            if last_update is None or (self.testing and bool(randint(0, 1))):
                last_update = 0.0
            self.addons.append(Addon(name).set_version(version).set_last_update(last_update))

    def find_update(self, addon):
        cfs = cfscrape.create_scraper()
        r = cfs.get(f'{self.base_url}/wow/addons/{addon.name}/files/all?filter-game-version={self.filters[addon.version]}')
        soup = bs(r.text, 'html.parser')
        rows = soup.find_all('tr')

        if self.not_windows:
            self.print_looking_for_update(i=idx.value)
            idx.value += 1

        for row in rows[1:]:
            cols = row.find_all('td')
            release_type = cols[0].text.strip()
            if release_type in self.allowed_release_types.upper():
                last_update_curse = int(cols[3].find('abbr').get('data-epoch'))
                if last_update_curse > addon.last_update:
                    addon.set_file_url(cols[1].find('a')['href'])
                    addon.set_latest_file(last_update_curse)

                    return addon

    def update_addon(self, addon):
        addon_start = time()
        out_path = pjoin(self.cache_dir, f'{addon.name}.zip')
        cfs = cfscrape.create_scraper()
        r = cfs.get(f'{self.base_url}{addon.file_url}')
        soup = bs(r.text, 'html.parser')
        a_tag_buttons = soup.find_all('a', {'class': 'button button--hollow'})

        for a_tag in a_tag_buttons:
            url = a_tag.get('href')
            if url.startswith(f'/wow/addons/{addon.name}/download/'):
                cfs = cfscrape.create_scraper()
                zip_file = cfs.get(f'{self.base_url}{url}/file')
                with open(out_path, 'wb') as f:
                    f.write(zip_file.content)
                    break

        ZipFile(out_path).extractall(self.addon_dir(addon.version))
        zip_size = getsize(out_path) / 1024 / 1024

        return addon, zip_size, addon_start

    def main(self):
        num_workers = cpu_count() * 2

        init()
        if self.windows:
            self.print_looking_for_update()

        start = time()

        # check for lates versions
        with Pool(num_workers) as p:
            arr = p.map(self.find_update, self.addons)

        outdated = list(filter(lambda x: x and x.outdated, arr))

        eol = '\n\n' if len(outdated) == 0 else f' ({round(time()-start, ndigits=2)}s)\n\n'
        self.print_looking_for_update(eol=eol)
        # find_update populates updateable
        outdated_len = len(outdated)

        if outdated_len == 0:
            print(end='')
            exit(f'{Fore.CYAN}=>{Fore.RESET} All addons are up-to-date! '
                 f'We\'re done here! ({round(time() - start, ndigits=2)}s)')

        else:
            addons_sorted = [a.name for a in sorted(outdated, key=lambda x: (x.version, x.name))]
            print(f'{Style.BRIGHT}{Fore.CYAN}=>{Fore.RESET}'
                  f' Updating {Fore.YELLOW}{outdated_len if outdated_len > 1 else ""}'
                  f'{Fore.RESET}{" addons" if outdated_len > 1 else "addon"}:{Style.RESET_ALL}'
                  f'{Fore.LIGHTGREEN_EX}', ' '.join(addons_sorted), Fore.RESET, '\n')

            tqdm.get_lock()  # ensures locks exist

            # update out-of-date addons
            with Pool(num_workers) as p:
                pbar = tqdm(p.imap_unordered(self.update_addon, outdated), total=outdated_len)
                for addon, size, timestamp in pbar:
                    self.size += size
                    self.config.set(f'{addon.version}', addon.name, str(timestamp))

            if not self.testing:
                with open(self.config_file, 'w') as f:
                    self.config.write(f)

            print(f'\nsummary: {round(time() - start, ndigits=2)}s, {round(self.size, ndigits=2)}MB')

        deinit()

    def addon_dir(self, version):
        addon_dir = pjoin(self.game_dir, f'_{version}_', 'Interface', 'AddOns')
        assert isdir(addon_dir), exit(f'Error: No Addon Folder found at \'{addon_dir}\'.')
        return addon_dir

    def print_looking_for_update(self, i=0, eol=' '):
        anim = ['⠶', '⠦', '⠖', '⠲', '⠴']
        symbol = '::' if self.windows else anim[int(i / 2) % len(anim)]

        print(f'\r{Style.BRIGHT}{Fore.BLUE}{symbol}{Fore.RESET}'
              f' Checking for latest versions of {Fore.YELLOW}{self.addons_len}'
              f'{Fore.RESET} {"addons" if self.addons_len > 1 else "addon"}.{Style.RESET_ALL}', end=eol)


class Addon:
    def __init__(self, name):
        self.name = name
        self.file_url = None
        self.version = None
        self.last_update = None
        self.latest_file = None

    def set_version(self, version):
        self.version = version
        return self

    def set_file_url(self, url):
        self.file_url = url
        return self

    def set_last_update(self, fl):
        self.last_update = float(fl)
        return self

    def set_latest_file(self, fl):
        self.latest_file = float(fl)
        return self

    def name(self):
        return self.name

    def version(self):
        return self.version

    def file_url(self):
        return self.file_url

    def last_update(self):
        return self.last_update

    def latest_file(self):
        return self.latest_file

    def outdated(self):
        if self.last_update is not None and self.latest_file is not None:
            return self.last_update < self.latest_file


if __name__ == '__main__':
    idx = Value('i', 0)
    Updater()
