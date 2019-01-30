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
Example:

```
python .\download.py --to-gif --source yabe --proxy 127.0.0.1:1080 6533
```
will download sticker set [白白日記 · 好熱啊!](https://yabeline.tw/Stickers_Data.php?Number=6533) from `yabe` source, and convert them to GIF. `127.0.0.1:1080` will be used as proxy.

## Implementation Details

This project uses [`ffmpeg`](https://www.ffmpeg.org/) to process images/videos. [`ffmpeg-python`](https://github.com/kkroening/ffmpeg-python) is used as python bindings for `ffmmpeg`.    

The original APNG images comes with Alpha channel and typically has a transparent background. To generate GIF from APNG, the GIF file must have white background (Or there will be frame overlaps). To do this, there are two solutions:

1. Overlay the APNG image on a white background
2. Calculate the color of each pixel, using white as background color.

Method 1 is ~2.5x faster than method 2. But it cannot handle cases with `ya8` pixel format (Comes with Gray and Alpha channels, as I observed). So if the pixel format is `ya8`, method 2 will be used.

