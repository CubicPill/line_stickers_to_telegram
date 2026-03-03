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

## Requirements
- FFmpeg 4.4.1 or later
- ImageMagick 7.1.0 or later
- [APNG Disassembler](http://apngdis.sourceforge.net/) 2.8 or later (optional)
- See requirements.txt for python dependencies
Install all requirements and make sure the executables are in your `PATH`.


## Usage

```text
usage: downloader.py [-h] [--type {sticker,emoji}] [--lang {zh-Hant,en,ja,ko,th,id,pt-BR}] [--proxy PROXY] [-y] [--redownload] [--no-subdir] [--show] [-q] [-o OUTPUT_DIR]
                     [--output-fmt {none,png,gif,webm,mp4}] [--scale] [--remove-alpha] [--extra-params EXTRA_PARAMS] [--no-default-txt-overlay] [-t THREADS]
                     id_url

Download stickers from line store

positional arguments:
  id_url                Product id of sticker set or the URL (yabe, line)

options:
  -h, --help            show this help message and exit
  --type {sticker,emoji}
                        Specify the type of the pack
  --lang {zh-Hant,en,ja,ko,th,id,pt-BR}
                        Language used when accessing Line page.
  --proxy PROXY         proxy, http(s)://addr:port
  -y                    Skip confirmation
  --redownload          Redownload stickers even if they exist
  --no-subdir           Do not create subdirectory for different output formats
  --show                Open the download/output directory after download
  -q, --quiet           Do not print information and progress bar
  -o, --output-dir OUTPUT_DIR
                        Output directory for processed stickers
  --output-fmt {none,png,gif,webm,mp4}
                        Output format
  --scale               Scale static stickers to 512*512, preserving aspect ratio
  --remove-alpha        Replace transparent background with white
  --extra-params EXTRA_PARAMS
                        Extra parameters for processing
  --no-default-txt-overlay
                        Do not put default text overlay on message stickers
  -t, --threads THREADS
                        Thread number of processing threads
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

### Concatenate Stickers

A script `concat_stickers.py` is provided to stitch multiple stickers from a pack into a single image sheet.

**Usage:**

```
python concat_stickers.py <sticker_id> [--rows <num>] [--cols <num>] [-o <output_file>]
```

**Arguments:**

- `sticker_id`: The ID of the sticker pack (must be downloaded first).
- `--rows`: Number of rows in the sticker sheet (default: 5).
- `--cols`: Number of columns in the sticker sheet (default: 5).
- `-o, --output`: Path for the output file. Use `.png` for static sheets and `.gif` for animated sheets.

**Example:**

```
python concat_stickers.py 10023 --rows 4 --cols 4 -o 10023_sheet.png
```

This will create a 4x4 PNG sticker sheet from the static sticker pack `10023`.

```
python concat_stickers.py 10154 --rows 6 --cols 5 -o 10154_sheet.gif
```

This will create a 6x5 animated GIF sticker sheet from the animated sticker pack `10154`.

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
