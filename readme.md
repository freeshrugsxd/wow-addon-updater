# wow addon update script
A script to update all my addons with a single command.

## what it does
As of now, the script
* needs a hardcoded list of the addons you want to keep up-to-date
* needs the hardcoded path to the game's addon folder
* saves the last time of the last update it did to a JSON file in a cache folder
* scrapes relevant information from Curseforge using requests and bs4 (because I'm an idiot and
    thats all I could come up with)
* determines available upgrades based on upload time of the latest file on Curseforge
    * time of latest upload is compared to the time of last update on disk
        * this means that on first execute or after deleting the cache folder, all addons are going
            to be updated
* only downloads addons for one game flavor (classic or retail)
* checks for updates, downloads and extracts files synchronously

## to do
* [ ] make code cleaner and more sophisticated i guess?
* [ ] stop relying on scraped information
* [ ] determine installed addons
* [ ] test if this even works on other machines
* [ ] maybe make it a full fledged cli application? (using argparse)

