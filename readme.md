# wow addon update script
A script to update all my addons with a single command.

<center><img src="https://i.imgur.com/XEYQ2I1.gif"></center>

## what it does
As of now, the script
* needs a hardcoded list of the addons you want to keep up-to-date
* needs the hardcoded path to the game's addon folder
* saves the time of the last update it did to a JSON file in a cache folder
* saves the downloaded zip files in a cache folder (they are currently not deleted but this will
    definitely change)
* scrapes relevant information from Curseforge using requests and bs4 (because I'm an idiot and
    thats all I could come up with)
* determines available upgrades based on upload time of the latest file on Curseforge
    * time of latest upload is compared to the time of last update on disk
        * this means that on first execute or after deleting the cache folder, all specified addons are going
            to get updated
* only downloads addons for one game flavor (classic or retail)
* checks for updates, downloads and extracts files synchronously

## what you need
### requirements
This requires at least python 3.6 (because f-strings) to run and depends on the packages `bs4`, `requests`, `colorama`
and `tqdm`. So either install these via your package manager or do a quick
```
$ pip3 install --user bs4 requests colorama tqdm
```

### addon names
The name of an addon is currently the project name from its Curseforge URL.
If you want an addon to be tracked and updated, you have to look it up on 
Curseforge and copy the last part of the project url. You paste this as a string into the `addon` list at the [beginning of the file](https://github.com/freeshrugsxd/wow-addon-updater/blob/master/update_wow_addons.py#L13) as a String.



#### example
The addon you want to track is called "<i>T.H.I.S. Addon</i>".
The project url is probably going to be something like `.../wow/addons/this-addon` and we are
going to copy `this-addon` and save it [inside the script](https://github.com/freeshrugsxd/wow-addon-updater/blob/master/update_wow_addons.py#L13) like this:

```python
addon = [
    'this-addon',
    'the-other-addon',
    'thirdaddon',
    'addon-nr-4',
    ...
]
```

that you only need to specify the path to your AddOn directory
[here](https://github.com/freeshrugsxd/wow-addon-updater/blob/master/update_wow_addons.py#L57) and call the script like this: 

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
