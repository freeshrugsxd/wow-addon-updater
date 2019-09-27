# wow addon update script
A script to update all my addons with a single command.

<center><img src="https://i.imgur.com/F6YleIb.gif"></center>

## what it does
As of now, the script
* saves the time of the last update it did to a JSON file in a cache folder
* saves the downloaded zip files to a cache folder
* scrapes relevant information from Curseforge using bs4 (because I'm an idiot and
    thats all I could come up with)
* bypasses cloudflare ddos protection (IUAM) pages 
* determines available upgrades based on upload time of the latest file on Curseforge
* only downloads addons for one game flavor (classic or retail)
* checks for updates, downloads and extracts files synchronously

## what you need
### requirements
This requires at least python 3.6 (because f-strings) to run and depends on the packages [`bs4`](https://www.crummy.com/software/BeautifulSoup/),
[`cfscrape`](https://github.com/Anorov/cloudflare-scrape) (build on [`requests`](https://github.com/psf/requests)), [`colorama`](https://github.com/tartley/colorama)
and [`tqdm`](https://tqdm.github.io/). So either install these via your package manager or do a quick
```
$ pip3 install --user bs4 cfscrape colorama tqdm
```

`cfscrape` also requires [nodejs](https://nodejs.org/en/) 10 or higher to solve Cloudflare's JavaScript challenges.

### addon names
The name of an addon is currently the project name from its Curseforge URL.
If you want an addon to be tracked and updated, you have to look it up on 
Curseforge and copy the last part of the project url. You paste this as a string into the `ADDONS` list at the [beginning of the file](https://github.com/freeshrugsxd/wow-addon-updater/blob/master/update_wow_addons.py#L14444444).



#### example
The addon you want to track is called "<i>T.H.I.S. Addon</i>".
The project url is probably going to be something like `.../wow/addons/this-addon` and we are
going to copy `this-addon` and save it [inside the script](https://github.com/freeshrugsxd/wow-addon-updater/blob/master/update_wow_addons.py#L14) like this:

```python
ADDONS = [
    'this-addon',
    'the-other-addon',
    'thirdaddon',
    'addon-nr-4',
    ...
]
```

After that you only need to specify the path to your AddOn directory
[here](https://github.com/freeshrugsxd/wow-addon-updater/blob/master/update_wow_addons.py#L58) and call the script like this: 

```
$ python3 update_wow_addons.py
```
and it should work.


## to do
* [ ] make code cleaner and more sophisticated i guess?
* [ ] stop reliance on scraped information
* [ ] automatically determine installed addons
* [ ] test if this even works on other machines
* [ ] maybe make it a full fledged cli application? (using argparse)
* [ ] read and write configuration file(s) instead of hardcoding stuff into the script
