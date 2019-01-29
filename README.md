# Line stickers to telegram

Script to download stickers from line sticker store

## Features
- Download static stickers & scale to fit telegram requirements
- Download animated stickers (APNG format) and convert them to GIF/video
- Download stickers with sound and convert to video


## Usage
```
download.py [-h] [--source SOURCE] [--proxy PROXY] [--no-scale]
                   [--static] [--to-gif] [--to-video] 
                   [-p PATH] [-t THREADS]
                   id
```
```
Positional arguments:
  id                    Product id of sticker set

Optional arguments:
  -h, --help            show this help message and exit
  --source SOURCE       Source to get sticker set information. Default is
                        "line"
  --proxy PROXY         HTTPS proxy, addr:port
  --no-scale            Disable static stickers auto resizing to 512*512
  --static              Download only static images (Will preserve APNG). Will
                        override all other conversion options
  --to-gif              Convert animated PNG (.apng) to GIF
  --to-video            Convert sticker (static/animated/popup) to .mp4 video,
                        with audio (if available). Static stickers without
                        audio cannot be converted to video
  -p PATH, --path PATH  Path to download the stickers
  -t THREADS, --threads THREADS
                        Thread number of downloader, default 4
```

