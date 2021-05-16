from configparser import ConfigParser
from multiprocessing import Lock, Pool, TimeoutError as mpTimeoutError, Value
from os import cpu_count, getenv
from pathlib import Path
from platform import system as pf_system
from random import randrange
from sys import exit
from time import time
from zipfile import ZipFile

import cloudscraper
from colorama import Fore, Style, deinit, init
from tqdm import tqdm
from bs4 import BeautifulSoup as bs


class Updater:
    def __init__(self, testing=False):
        self.testing = testing  # if true, game dir changes and random addons are updated

        self.base_url = 'https://www.curseforge.com'
        self.timeout = 20  # seconds
        self.worker_timed_out = False

        self.allowed_release_types = 'RB'  # [R = release, B = beta, A = alpha]

        self.cache_dirs = {
            'Windows': Path(str(getenv('temp'))),
            'Linux': Path.home() / '.cache',
            'Darwin': Path.home() / '.cache'
        }

        self.cache_dir = self.cache_dirs[pf_system()] / 'wow-addon-updates'

        if not self.cache_dir.is_dir():
            try:
                self.cache_dir.mkdir()

            except PermissionError as e:
                raise RuntimeError(f'{Fore.RED}Do not have permissions to access {self.cache_dir}, error:\n {e}')

        self.config_file = Path(__file__).resolve().parent / 'update_wow_addons.config'

        with open(self.config_file, 'r') as f:
            self.config = ConfigParser(allow_no_value=True, interpolation=None)
            self.config.read_file(f)

        if self.testing:
            self.game_dir = Path(__file__).resolve().parent / 'testing'
            print(f'{Fore.YELLOW}### Running in testing mode. Changing game directory to '
                  f'\'{self.game_dir}\' and updating random addons.\n{Fore.RESET}')
        else:
            self.game_dir = Path(self.config['settings']['game directory'])

            if not self.game_dir.is_dir():
                raise RuntimeError(f'{Fore.RED}\'{self.game_dir}\' is not a valid game directory.')

        self.client = self.config['settings']['client'].lower()

        # codes to filter the latest files page for specific game version
        self.filters = {
            'classic': '1738749986%3A67408',
            'retail': '1738749986%3A517'
        }

        clients = ['classic', 'retail']

        self.addons = []
        self.addons_len = 0
        self.size = 0.0

        if self.client in clients:
            self._collect_addons(self.client)
        else:
            if ',' in self.client:
                client_list = list(set(self.client.split(',')))
            elif self.client in ['both', 'all']:
                client_list = clients
            else:
                raise RuntimeError(f'{Fore.RED}Invalid game version specified. \'{self.client}\''
                                   f' is not accepted. Must be either classic, retail or both.')

            for client in client_list:
                client = client.strip()

                if client in clients and len(client) > 0:
                    self._addon_dir(client)  # early check if client is installed
                    self._collect_addons(client)

        self.addons_len = len(self.addons)
        if self.addons_len == 0:
            raise RuntimeError(f'{Fore.RED}No addons found in [{self.client}] section of the configuration file.')

        self.cfs = cloudscraper.create_scraper()

        self._main()

    def _collect_addons(self, client):

        for name, last_update in self.config.items(client):
            if self.testing:
                last_update = 0. if randrange(1, 100) <= 25 else time()

            elif not last_update:
                last_update = 0.

            self.addons.append(Addon(name=name, client=client, last_update=float(last_update)))

    def _find_update(self, addon):
        url = f'{self.base_url}/wow/addons/{addon.name}/files/all?filter-game-version={self.filters[addon.client]}'
        r = self.cfs.get(url)
        check_response_status(r)

        soup = bs(r.text, 'html.parser')
        rows = soup.find_all('tr')

        with print_lock:
            self._print_looking_for_update(i=idx.value)
            idx.value += 1

        for row in rows[1:]:
            cols = row.find_all('td')
            release_type = cols[0].text.strip()

            if release_type in self.allowed_release_types.upper():
                last_update_curse = int(cols[3].find('abbr').get('data-epoch'))
                if last_update_curse > addon.last_update:
                    addon.file_url = cols[1].find('a')['href']
                    addon.latest_file = last_update_curse

                    return addon

    def _update_addon(self, addon):
        addon_start = time()
        out_path = self.cache_dir / f'{addon.client}_{addon.name}.zip'
        r = self.cfs.get(f'{self.base_url}{addon.file_url}')
        check_response_status(r)

        soup = bs(r.text, 'html.parser')
        a_tag_buttons = soup.find_all('a', {'class': 'button button--hollow'})

        for a_tag in a_tag_buttons:
            url = a_tag.get('href')
            if url.startswith(f'/wow/addons/{addon.name}/download/'):
                zip_file = self.cfs.get(f'{self.base_url}{url}/file')
                check_response_status(zip_file)
                with open(out_path, 'wb') as f:
                    f.write(zip_file.content)
                    break

        ZipFile(out_path).extractall(self._addon_dir(addon.client))
        zip_size = out_path.stat().st_size / 1000000

        return addon, zip_size, addon_start

    def _main(self):
        num_workers = cpu_count() * 2

        init()
        start = time()

        shared_idx = Value('i', 0)
        global_print_lock = Lock()
        # check for latest versions
        with Pool(processes=min(num_workers, self.addons_len),
                  initializer=init_globals,
                  initargs=(shared_idx, global_print_lock)) as p:

            it = p.imap_unordered(self._find_update, self.addons)
            arr = []

            while True:
                try:
                    arr.append(it.next(timeout=self.timeout))

                except StopIteration:
                    break

                except mpTimeoutError:
                    self.worker_timed_out = True
                    continue

        # first filter out NoneTypes, then return only the outdated addons
        outdated = list(filter(lambda x: x and x.outdated, arr))

        eol = '\n\n' if len(outdated) == 0 else f' ({round(time() - start, ndigits=2)}s)\n\n'
        self._print_looking_for_update(eol=eol)

        outdated_len = len(outdated)

        if outdated_len == 0:
            print(f'{Fore.CYAN}=>{Fore.RESET} All addons are up-to-date! '
                  f'We\'re done here! ({round(time() - start, ndigits=2)}s)')
            exit(0)

        else:
            cols = {
                'classic': Fore.RED,
                'retail': Fore.LIGHTGREEN_EX
            }

            # sort addons by client first, then by name
            addons_sorted = [[a.name, a.client] for a in sorted(outdated, key=lambda x: (x.client, x.name))]
            colored_names = ' '.join([f'{cols[c]}{n[:2]}{Fore.RESET}{n[2:]}' for n, c in addons_sorted])

            pad = len(sorted(addons_sorted, key=lambda x: len(x[0]), reverse=True)[0][0])

            print(f'{Style.BRIGHT}{Fore.CYAN}=>{Fore.RESET} Updating {Fore.YELLOW}'
                  f'{outdated_len if outdated_len > 1 else ""}{Fore.RESET}'
                  f'{" addons" if outdated_len > 1 else "addon"}:{Style.RESET_ALL} '
                  f'{colored_names}', Style.RESET_ALL, '\n')

            # update out-of-date addons
            with Pool(processes=min(num_workers, outdated_len)) as p:

                it = p.imap_unordered(self._update_addon, outdated)
                pb = tqdm(total=outdated_len,
                          desc=f' {pad * " "} ',
                          bar_format='{n_fmt}/{total_fmt} |{bar}|{desc}')

                pb.set_lock(global_print_lock)

                while True:
                    try:
                        addon, size, timestamp = it.next(timeout=self.timeout)
                        desc = f' {addon.name + (pad - len(addon.name)) * " "}{Fore.RESET} '
                        pb.set_description_str(desc=desc)
                        pb.update()
                        self.size += size
                        self.config.set(f'{addon.client}', addon.name, str(timestamp))

                    except StopIteration:
                        pb.close()
                        break

                    except mpTimeoutError:
                        raise RuntimeError(f'{Fore.RED}Something went wrong while installing one or more addons. '
                                           f'Rerun the script to make sure everything is up-to-date.{Fore.RESET}')

            if not self.testing:
                with open(self.config_file, 'w') as f:
                    self.config.write(f)

            msg = f'\nsummary: {round(time() - start, ndigits=2)}s, {round(self.size, ndigits=2)}MB'
            if self.worker_timed_out:
                msg += '\nSome worker/s timed out. Run the program again to be certain everything is up-to-date!'
            print(msg)

        deinit()

    def _addon_dir(self, client):
        addon_dir = self.game_dir / f'_{client}_' / 'Interface' / 'AddOns'

        if not addon_dir.is_dir():
            if self.testing:
                print(f'{Fore.YELLOW}### Creating addon directory for testing at \'{addon_dir}\'.{Fore.RESET}')
                addon_dir.mkdir(addon_dir, parents=True)
            else:
                raise RuntimeError(f'{Fore.RED}{client.capitalize()} addon folder not found at \'{addon_dir}\'.')
        return addon_dir

    def _print_looking_for_update(self, i=0, eol=' '):

        anims = {
            'dots': ['   ', '. ', '.. ', '...'],
            'braille': ['⠶', '⠦', '⠖', '⠲', '⠴']
        }

        anim = anims['braille']
        symbol = anim[int(i / 2) % len(anim)]

        print(f'\r{Style.BRIGHT}{Fore.BLUE}{symbol}{Fore.RESET}'
              f' Checking for latest versions of {Fore.YELLOW}{self.addons_len}'
              f'{Fore.RESET} {"addons" if self.addons_len > 1 else "addon"}.{Style.RESET_ALL}', end=eol)


def check_response_status(response):
    if not response.ok:
        response.raise_for_status()


def init_globals(shared_idx, lock):
    global idx, print_lock
    idx = shared_idx
    print_lock = lock


class Addon:
    def __init__(self, name=None, client=None, last_update=None, file_url=None, latest_file=None):
        self.name = name
        self.client = client
        self.file_url = file_url
        self.last_update = last_update
        self.latest_file = latest_file

    def __repr__(self):
        return f'<{self.name}:{self.client}>'

    def outdated(self):
        if self.last_update is not None and self.latest_file is not None:
            return self.last_update < self.latest_file


if __name__ == '__main__':
    Updater(testing=False)
