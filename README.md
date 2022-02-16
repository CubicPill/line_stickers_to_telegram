# Line stickers to telegram

Script to download stickers from line sticker store.

(And convert them to formats that could be imported to telegram)

## Features
- Download static stickers & scale to fit telegram requirements
- Download animated stickers (APNG format) and convert them to GIF/video/WebM
- Download stickers with sound and convert to video

### Supported Line Sticker Type to Download
- Regular ✅
- Animated ✅
- Emoji ✅
- Animated with Sound ✅
- Static with Sound ✅
- Custom (Text-filling) ✅

### Supported Telegram Sticker Type to Export
- Regular sticker ✅
- GIF ✅
- Animated Sticker ❌
- Video Sticker ✅
## Usage
```
download.py [-h] [--source SOURCE] [--lang LANG] [--proxy PROXY] [--no-scale] [--static] [--to-gif] [--to-webm] [--to-video] [-p PATH] [-t THREADS] id
```

```
Download stickers from line store

positional arguments:
  id                    Product id of sticker set

optional arguments:
  -h, --help            show this help message and exit
  --source SOURCE       Source to get sticker set information. Default is "line"
  --lang LANG           Language(Zone) to get sticker. Could be "en", "ja", "zh-Hant" and others. Default is "en"
  --proxy PROXY         HTTPS proxy, addr:port
  --no-scale            Disable static stickers auto resizing to 512*512
  --static              Download only static images (Will preserve APNG). Will override all other conversion options
  --to-gif              Convert animated PNG (.apng) to GIF, no scaling
  --to-webm             Convert animated PNG (.apng) to WEBM, to be used in telegram video stickers, will scale to 512*(<512)
  --to-video            Convert sticker (static/animated/popup) to .mp4 video, with audio (if available). No scaling. Static stickers without audio cannot be
                        converted to video
  -p PATH, --path PATH  Path to download the stickers
  -t THREADS, --threads THREADS
                        Thread number of downloader, default 4
```
Examples:

```
python .\download.py --source yabe --to-webm 10154
```

Simply download [對自己吐槽的白熊（動了動了篇）](https://yabeline.tw/Stickers_Data.php?Number=10154) and convert to WebM format.
It could then be used to create [Telegram Video Stickers](https://core.telegram.org/stickers#video-stickers).

```
python .\download.py --to-gif --source yabe --proxy 127.0.0.1:1080 6533
```
will download sticker set [白白日記 · 好熱啊!](https://yabeline.tw/Stickers_Data.php?Number=6533) from `yabe` source, and convert them to GIF. `127.0.0.1:1080` will be used as proxy.
## Selection of Source
The `source` argument is only to be used for getting the list of stickers. All stickers are download directly from Line.

This feature is added because some stickers are only available in specific regions or the official page has been take down.

## Implementation Details

This project uses [`ffmpeg`](https://www.ffmpeg.org/) to process images/videos. [`ffmpeg-python`](https://github.com/kkroening/ffmpeg-python) is used as python bindings for `ffmmpeg`.    

The original APNG images comes with Alpha channel and typically has a transparent background. To generate GIF from APNG, the GIF file must have white background (Or there will be frame overlaps). To do this, there are two solutions:

1. Overlay the APNG image on a white background
2. Calculate the color of each pixel, using white as background color.

Method 1 is ~2.5x faster than method 2. But it cannot handle cases with `ya8` pixel format (Comes with Gray and Alpha channels, as I observed). So if the pixel format is `ya8`, method 2 will be used.

## Known issues
- FFmpeg (I'm using v5.0) may not correctly handle frame disposal in APNG sometimes. 
For example, [this image](https://stickershop.line-scdn.net/stickershop/v1/sticker/16955051/IOS/sticker_animation@2x.png).
If this happens, it's recommended to use [APNG Disassembler](http://apngdis.sourceforge.net/) to disassemble frames first.
- Telegram has a limit on the size and length of video stickers, which is 256KiB and 3 seconds, respectively. (As of 01/02/2022)
This script takes care of the length (by splitting the animation to individual frames and re-generate video using a larger framerate),
but the size is not currently considered (In most cases size won't be a problem).

## Extra

### Support for Kakao animation stickers
```
usage: kakao_dl.py [-h] [--proxy PROXY] [--no-processing] [--static] [--to-gif] [--to-webm] [--to-video] [-p PATH] url

Download stickers from Kakao store

positional arguments:
  url                   URL of sticker set

optional arguments:
  -h, --help            show this help message and exit
  --proxy PROXY         HTTPS proxy, addr:port
  --no-processing       No processing
  --static              Download only static images.
  --to-gif              Convert to GIF, no scaling
  --to-webm             Convert to WEBM, to be used in telegram video stickers, will scale to 512*(<512)
  --to-video            Convert sticker (animated) to .mp4 video, with audio (if available). No scaling. Static stickers without audio cannot be converted to video   
  -p PATH, --path PATH  Path to download the stickers
```

The URL of sticker is the URL when sharing sticker set in Kakao mobile client. For example:

https://emoticon.kakao.com/items/sm2j7IoGGxH8xYzR08X8h4sReq4=?lang=en&referer=share_link

Currently, **only Kakao WebP to WebM** is supported. More support may be added later.

#### Known bugs
- The converted WebM video may look blotchy when viewed using system player. However, in telegram the video looks normal.
- The playback speed is too fast in iOS client. Windows and Android client are OK. Might be a bug of Telegram.
