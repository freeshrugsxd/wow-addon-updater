# wow addon update script
A script to update all my addons with a single command.

<center><img src="https://i.imgur.com/F6YleIb.gif"></center>

## what it does
As of now, the script
* checks for updates, downloads and extracts files synchronously
* updates addons for either classic, retail or both at the same time
* reads and writes a configuration file
* saves downloaded files to a cache folder
* scrapes relevant information from Curseforge using bs4 (because I'm an idiot and
    thats all I could come up with)
* bypasses cloudflare ddos protection (IUAM) pages 
* determines available upgrades based on upload time of the latest file on Curseforge

## what you need
### requirements
This requires at least python 3.6 (because f-strings) to run and depends on the packages [`bs4`](https://www.crummy.com/software/BeautifulSoup/),
[`cfscrape`](https://github.com/Anorov/cloudflare-scrape) (build on [`requests`](https://github.com/psf/requests)), [`colorama`](https://github.com/tartley/colorama)
and [`tqdm`](https://tqdm.github.io/). So either install these via your package manager or do a quick
```
$ pip3 install --user bs4 cfscrape colorama tqdm
```

`cfscrape` also requires [nodejs](https://nodejs.org/en/) 10 or higher to solve Cloudflare's JavaScript challenges.

### configuration file
The configuration file must be in the same directory and have the same name as the
script file (currently`update_wow_addons.config`). It [follows the structure
of INI-files](https://docs.python.org/3/library/configparser.html#supported-ini-file-structure) and
contains three sections. The path to your game installation folder and the WoW version you want to
update addons for should go under`[settings]`. Names of addons you want to keep up-to-date 
go into their respective section,`[classic]`or`[retail]`. 

#### client version
Possible values for the `client` setting are <i>classic</i> and <i>retail</i>. To track addons of
both versions you can simply enter both, separated by a comma. You can also literally just set it to <i>
both</i> (or <i>all</i>) and the program will update retail and classic addons
simultaneously.

#### addon names
The name of an addon is currently the project name from its Curseforge URL.
If you want an addon to be tracked and updated, you have to look it up on 
Curseforge and copy the last part of the project url.

For example, let's say the addon you want to track is called "<i>T.H.I.S. Addon</i>"
then the project url is probably going to be something like `.../wow/addons/this-addon`.
Copy `this-addon` and paste it into the configuration file.



#### example configuration
update_wow_addons.config
```ini
[settings]
client=both
game directory=D:/games/World of Warcraft

[retail]
details
big-wigs
prat-3-0
weakauras-2

[classic]
details
classiccastbars
classicthreatmeter
real-mob-health
```

### execution
Call the script like
```
$ python3 update_wow_addons.py
```
and it should just work™.

## to do
* [ ] make code cleaner and more sophisticated i guess?
* [ ] automatically determine installed addons
* [x] test if this even works on other machines
* [ ] maybe make it a full fledged cli application?
* [x] read and write configuration file(s) instead of hardcoding stuff into the script
* [x] add option to always check updates for both game versions 
