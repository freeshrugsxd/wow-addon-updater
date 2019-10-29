from configparser import ConfigParser
from multiprocessing import Lock, Pool, TimeoutError as mpTimeoutError, Value
from os import cpu_count, mkdir
from os.path import dirname, expanduser, getsize, isdir, isfile, join as pjoin
from platform import system as pf_system
from random import randrange
from sys import exit
from time import time
from zipfile import ZipFile

import cfscrape
from colorama import Fore, Style, deinit, init
from tqdm import tqdm
from bs4 import BeautifulSoup as bs


class Updater:
    def __init__(self, testing=False):
        self.testing = testing  # if true, game dir changes and random addons are updated

        self.windows = pf_system() == 'Windows'
        self.not_windows = not self.windows
        self.base_url = 'https://www.curseforge.com'
        self.timeout = 15  # seconds
        self.worker_timed_out = False

        self.allowed_release_types = 'RB'  # [R = release, B = beta, A = alpha]
        if not self.allowed_release_types.upper() in 'RBA':
            raise RuntimeError(f'{Fore.RED}Release Types must be R, B, A or any combination of them.')

        self.cache_dir = pjoin(expanduser('~'), '.cache', 'wow-addon-updates')

        if not isdir(self.cache_dir):
            if not isdir(dirname(self.cache_dir)):
                mkdir(dirname(self.cache_dir))
            mkdir(self.cache_dir)

        self.config_file = pjoin(dirname(__file__), 'update_wow_addons.config')
        if not isfile(self.config_file):
            raise RuntimeError(f'{Fore.RED}No config file detected at \'{self.config_file}\'')

        if self.testing:
            self.test_dir = '/home/silvio/tmp/updater_test'
            self.config_file = pjoin(self.test_dir, 'update_wow_addons.testing.config')

        with open(self.config_file, 'r') as f:
            self.config = ConfigParser(allow_no_value=True, interpolation=None)
            self.config.read_file(f)

        self.game_dir = self.config['settings']['game directory']
        if not isdir(self.game_dir):
            raise RuntimeError(f'{Fore.RED}\'{self.game_dir}\' is not a valid game directory.')

        if self.testing:
            self.game_dir = self.test_dir
            # print(f'Running in testing mode. Changing game directory to \'{self.test_dir}\''
            #       f' and updating random addons.\n')

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
            self.collect_addons(self.client)
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
                    self.addon_dir(client)  # early check if client is installed
                    self.collect_addons(client)

        self.addons_len = len(self.addons)
        if self.addons_len == 0:
            raise RuntimeError(f'{Fore.RED}No addons found in [{self.client}] section of the configuration file.')

        self.cfs = cfscrape.create_scraper()

        self.main()

    def collect_addons(self, client):

        for name, last_update in self.config.items(client):
            if not last_update or (self.testing and randrange(1, 100) <= 25):
                last_update = 0.0

            self.addons.append(Addon(name=name, client=client, last_update=float(last_update)))

    def find_update(self, addon):
        url = f'{self.base_url}/wow/addons/{addon.name}/files/all?filter-game-version={self.filters[addon.client]}'
        r = self.cfs.get(url)

        if r.status_code != 200:
            r.raise_for_status()

        soup = bs(r.text, 'html.parser')
        rows = soup.find_all('tr')

        lock.acquire()

        self.print_looking_for_update(i=idx.value)
        idx.value += 1

        lock.release()

        for row in rows[1:]:
            cols = row.find_all('td')
            release_type = cols[0].text.strip()

            if release_type in self.allowed_release_types.upper():
                last_update_curse = int(cols[3].find('abbr').get('data-epoch'))
                if last_update_curse > addon.last_update:
                    addon.file_url = cols[1].find('a')['href']
                    addon.latest_file = last_update_curse

                    return addon

    def update_addon(self, addon):
        addon_start = time()
        out_path = pjoin(self.cache_dir, f'{addon.client}_{addon.name}.zip')
        r = self.cfs.get(f'{self.base_url}{addon.file_url}')
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

        ZipFile(out_path).extractall(self.addon_dir(addon.client))
        zip_size = getsize(out_path) / 1024 / 1024

        return addon, zip_size, addon_start

    def main(self):
        num_workers = cpu_count() * 2

        init()
        start = time()

        shared_idx = Value('i', 0)
        print_lock = Lock()
        # check for lates versions
        with Pool(num_workers, initializer=init_globals, initargs=(shared_idx, print_lock)) as p:
            it = p.imap_unordered(self.find_update, self.addons)
            arr = []

            while True:
                try:
                    arr.append(it.next(timeout=self.timeout))

                except mpTimeoutError:
                    self.worker_timed_out = True
                    continue

                except StopIteration:
                    break

        # first filter out NoneTypes, then return only the outdated addons
        outdated = list(filter(lambda x: x and x.outdated, arr))

        eol = '\n\n' if len(outdated) == 0 else f' ({round(time() - start, ndigits=2)}s)\n\n'
        self.print_looking_for_update(eol=eol)

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

            tqdm.get_lock()  # ensures locks exist

            # update out-of-date addons
            with Pool(num_workers) as p:
                it = p.imap_unordered(self.update_addon, outdated)
                pb = tqdm(total=outdated_len,
                          desc=f' {pad * " "} ',
                          bar_format='{n_fmt}/{total_fmt} |{bar}|{desc}')

                while True:
                    try:
                        addon, size, timestamp = it.next(timeout=self.timeout * 2)
                        desc = f' {addon.name + (pad - len(addon.name)) * " "}{Fore.RESET} '
                        pb.set_description_str(desc=desc)
                        pb.update()
                        self.size += size
                        self.config.set(f'{addon.client}', addon.name, str(timestamp))

                    except mpTimeoutError:
                        self.worker_timed_out = True
                        continue

                    except StopIteration:
                        pb.close()
                        break

            if not self.testing:
                with open(self.config_file, 'w') as f:
                    self.config.write(f)

            msg = f'\nsummary: {round(time() - start, ndigits=2)}s, {round(self.size, ndigits=2)}MB'
            if self.worker_timed_out:
                msg += '\nSome worker/s timed out. Run the program again to be certain everything is up-to-date!'
            print(msg)

        deinit()

    def addon_dir(self, client):
        addon_dir = pjoin(self.game_dir, f'_{client}_', 'Interface', 'AddOns')
        if not isdir(addon_dir):
            raise RuntimeError(f'{Fore.RED}{client.capitalize()} addon folder not found at \'{addon_dir}\'.')
        return addon_dir

    def print_looking_for_update(self, i=0, eol=' '):
        anim = ['⠶', '⠦', '⠖', '⠶', '⠲', '⠴']
        symbol = anim[int(i/2) % len(anim)]

        print(f'\r{Style.BRIGHT}{Fore.BLUE}{symbol}{Fore.RESET}'
              f' Checking for latest versions of {Fore.YELLOW}{self.addons_len}'
              f'{Fore.RESET} {"addons" if self.addons_len > 1 else "addon"}.{Style.RESET_ALL}', end=eol)


def init_globals(shared_idx, print_lock):
    global idx, lock
    idx = shared_idx
    lock = print_lock


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
    Updater()
