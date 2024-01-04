import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import time
import zipfile
from queue import Queue

from tqdm import tqdm

import webreq
from processing import ImageProcessorThread, Operation, OutputFormat, ProcessTask
from utils import (
    MESSAGE_STICKER_OVERLAY_DEFAULT,
    PackNotFoundException,
    STICKER_SET_URL_REGEX,
    SourceUrlType,
    StickerType,
    get_counter_value,
    reset_counter,
    sticker_type_properties,
)
from webreq import (
    MultiThreadDownloader,
    get_metadata,
    get_real_pack_id_from_yabe_emoji,
    get_sticker_archive,
)

err_print = print
norm_print = print
sticker_process_temp_root = None


def wait_for_queue_with_progress(quiet: bool, queue: Queue, total: int):
    if not quiet:
        reset_counter()
        with tqdm(total=total) as bar:
            last = 0
            while not (completed := get_counter_value()) == total:
                bar.update(completed - last)
                bar.refresh()
                last = completed
                time.sleep(0.5)
            queue.join()
            bar.n = total
            bar.refresh()
            bar.clear()
    else:
        queue.join()


def main():
    arg_parser = argparse.ArgumentParser(
        description="Download stickers from line store"
    )

    # critical arguments
    arg_parser.add_argument(
        "id_url", type=str, help="Product id of sticker set or the URL (yabe, line)"
    )

    arg_parser.add_argument(
        "--type",
        type=str,
        help="Specify the type of the pack",
        default="sticker",
        choices=["sticker", "emoji"],
    )

    # auxiliary
    arg_parser.add_argument(
        "--lang",
        type=str,
        help="Language used when accessing Line page.",
        default="zh-Hant",
        choices=[
            "zh-Hant",
            "en",
            "ja",
            "ko",
            "th",
            "id",
            "pt-BR",
        ],
    )
    arg_parser.add_argument("--proxy", type=str, help="proxy, http(s)://addr:port")
    arg_parser.add_argument("-y", action="store_true", help="Skip confirmation")
    arg_parser.add_argument(
        "--redownload",
        action="store_true",
        help="Redownload stickers even if they exist",
    )
    arg_parser.add_argument(
        "--no-subdir",
        action="store_true",
        help="Do not create subdirectory for different output formats",
    )
    arg_parser.add_argument(
        "--show",
        action="store_true",
        help="Open the download/output directory after download",
    )
    arg_parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Do not print information and progress bar",
    )
    arg_parser.add_argument(
        "-o", "--output-dir", type=str, help="Output directory for processed stickers"
    )
    # conversion options

    # webm won't have audio track
    arg_parser.add_argument(
        "--output-fmt",
        type=str,
        help="Output format",
        default="none",
        choices=["none", "png", "gif", "webm", "mp4"],
    )

    arg_parser.add_argument(
        "--scale",
        help="Scale static stickers to 512*512, preserving aspect ratio",
        action="store_true",
    )

    # works for gif, png and webm. For mp4 video, alpha is always removed
    arg_parser.add_argument(
        "--remove-alpha",
        help="Replace transparent background with white",
        action="store_true",
    )

    # for message stickers only
    arg_parser.add_argument(
        "--no-default-txt-overlay",
        action="store_true",
        help="Do not put default text overlay on message stickers",
    )

    # not commonly used
    arg_parser.add_argument(
        "-t",
        "--threads",
        type=int,
        help="Thread number of processing threads",
        default=8,
    )

    args = arg_parser.parse_args()

    sticker_data_root_dir = os.path.join(os.getcwd(), "sticker_dl")
    if not os.path.exists(sticker_data_root_dir):
        os.mkdir(sticker_data_root_dir)

    # gather arguments

    # handle proxies
    proxies = {}
    if os.path.exists("./PROXY"):
        with open("./PROXY") as f:
            proxies["https"] = f.read().strip()
    if args.proxy:
        # proxy in args will override the PROXY file
        proxies["https"] = args.proxy
    webreq.set_proxy(proxies)

    thread_num = args.threads
    lang = args.lang
    pack_type = args.type
    remove_alpha = args.remove_alpha
    id_url = args.id_url.strip()
    scale_to_512_square = args.scale
    re_download = args.redownload
    output_fmt = args.output_fmt
    no_default_txt_overlay = args.no_default_txt_overlay
    skip_confirmation = args.y
    no_sub_dir = args.no_subdir
    open_folder = args.show
    quiet = args.quiet
    if not args.output_dir:
        default_sticker_output_root_dir = os.path.join(os.getcwd(), "sticker_out")
    else:
        default_sticker_output_root_dir = args.output_dir
    global norm_print
    if quiet:
        norm_print = lambda *args, **kwargs: None
        skip_confirmation = True
    if not os.path.exists(default_sticker_output_root_dir):
        os.mkdir(default_sticker_output_root_dir)
    # check if input is id or url
    if "http" not in id_url:
        pack_id = id_url
        is_emoji = pack_type == "emoji"
        if not is_emoji and len(pack_id) >= 24:
            err_print(
                "WARNING: You probably want to download an emoji pack, but the sticker type is not specified as emoji."
            )
    else:
        # input is url
        # extract pack id from url
        for _type, (_regex, _emoji_flag) in STICKER_SET_URL_REGEX.items():
            match = _regex.match(id_url)
            if match:
                norm_print(f"URL is matched as: {_type}")
                pack_id = match.group(1)
                is_emoji = _emoji_flag

                if _type == SourceUrlType.YABE_EMOJI:
                    # special processing to get real pack id
                    pack_id = get_real_pack_id_from_yabe_emoji(pack_id)
                break
        else:
            norm_print(
                "URL is not matched as any known source! Please double check the url"
            )
            sys.exit(1)

    # from here, pack_id should be ready

    # Check if the sticker set archive exists
    sticker_pack_dl_root = os.path.join(sticker_data_root_dir, pack_id)
    pack_archive_path = os.path.join(sticker_pack_dl_root, "pack.zip")
    pack_archive_exists = os.path.isfile(pack_archive_path)
    download_pack = True
    if pack_archive_exists and not re_download:
        norm_print(f"Found local archive for pack {pack_id}!")
        archive = zipfile.ZipFile(pack_archive_path, "r")
        metadata = json.loads(archive.read("productInfo.meta"))
        download_pack = False
    else:
        # get metadata from line store
        try:
            metadata = get_metadata(pack_id, is_emoji)
        except PackNotFoundException:
            err_print(
                f'ERROR: Cannot find sticker set {pack_id} with type "{pack_type}"!'
            )
            sys.exit(1)
    pack_info = extract_pack_info_from_metadata(metadata, pack_id, lang, is_emoji)

    # from here, pack_info should be ready

    title = pack_info["title"]
    sticker_type = StickerType(pack_info["sticker_type"])
    id_list = pack_info["stickers"]
    sticker_count = len(id_list)
    (
        has_animation,
        has_sound,
        has_popup,
        has_text_overlay,
        is_emoji,
    ) = sticker_type_properties(sticker_type)

    scale_px = 0
    if scale_to_512_square and not has_animation:
        scale_px = 512
    elif output_fmt == "webm":
        if is_emoji:
            scale_px = 100
        else:
            scale_px = 512
    norm_print("-----------------Sticker pack info:-----------------")
    norm_print("Title:", title)
    norm_print("Pack ID:", pack_id)
    norm_print("Sticker Type:", sticker_type.name)
    norm_print("Total number of stickers:", sticker_count)
    processing_needed = output_fmt != "none"
    if not processing_needed:
        norm_print("Output format: RAW")
    else:
        norm_print("Output format:", output_fmt)
        if scale_px:
            norm_print("Scale:", f"{scale_px}*{scale_px}px")
        if sticker_type == StickerType.MESSAGE_STICKER:
            norm_print("Default text overlay:", not no_default_txt_overlay)
            norm_print("Output directory:", default_sticker_output_root_dir)

    norm_print("----------------------------------------------------")

    if not skip_confirmation:
        confirm = input("Do you wish to continue? Y/n: ")
        if confirm.lower() == "n":
            norm_print("Aborting...")
            sys.exit(0)
        elif confirm and confirm.lower() != "y":
            norm_print("Invalid input. Aborting...")
            sys.exit(1)

    # create folders
    if not os.path.isdir(sticker_pack_dl_root):
        os.mkdir(sticker_pack_dl_root)

    if download_pack:
        # download sticker pack
        norm_print("Downloading sticker pack archive... ", end="")
        archive_content = get_sticker_archive(pack_id, sticker_type)
        norm_print("Complete!")

        # save archive and unzip to temp folder
        with open(pack_archive_path, "wb") as f:
            f.write(archive_content)

    global sticker_process_temp_root
    sticker_process_temp_root = tempfile.mkdtemp()
    # starting from here, use return to exit with cleaning up the temp folder

    sticker_temp_raw_path = os.path.join(sticker_process_temp_root, "raw")
    sticker_temp_extracted_zip_path = os.path.join(
        sticker_process_temp_root, "unarchive"
    )

    if not os.path.isdir(sticker_temp_raw_path):
        os.mkdir(sticker_temp_raw_path)
    if not os.path.isdir(sticker_temp_extracted_zip_path):
        os.mkdir(sticker_temp_extracted_zip_path)

    norm_print("Extracting archive... ", end="")
    with zipfile.ZipFile(pack_archive_path, "r") as zip_ref:
        zip_ref.extractall(sticker_temp_extracted_zip_path)
    norm_print("Complete!")

    rearrange_pack_content(
        sticker_temp_extracted_zip_path, sticker_temp_raw_path, is_emoji
    )

    # for message sticker, download default overlay message in advance
    if sticker_type == StickerType.MESSAGE_STICKER:
        default_overlay_dl_path = os.path.join(sticker_pack_dl_root, "default_overlay")
        if not os.path.isdir(default_overlay_dl_path):
            os.mkdir(default_overlay_dl_path)
        norm_print("Downloading default overlay message for message sticker... ")
        download_queue = Queue()
        downloader = [MultiThreadDownloader(download_queue) for _ in range(4)]

        for sticker_id in id_list:
            filename = os.path.join(default_overlay_dl_path, f"{sticker_id}.png")
            url = MESSAGE_STICKER_OVERLAY_DEFAULT.format(
                sticker_id=sticker_id, pack_id=pack_id
            )
            download_queue.put((sticker_id, url, filename))
        for d in downloader:
            d.start()
        wait_for_queue_with_progress(quiet, download_queue, sticker_count)

        norm_print("Message sticker default overlay download done!")

        # copy default overlay to raw folder
        shutil.copytree(
            default_overlay_dl_path,
            os.path.join(sticker_temp_raw_path, "default_overlay"),
            dirs_exist_ok=True,
        )

    # determine process option
    # for line, all stickers are png/apng
    if output_fmt == "png":
        output_format = OutputFormat.APNG
    elif output_fmt == "gif":
        output_format = OutputFormat.GIF
    elif output_fmt == "webm":
        output_format = OutputFormat.WEBM
    elif output_fmt == "video":
        output_format = OutputFormat.MP4
    elif output_fmt == "none":
        output_format = OutputFormat.RAW

    else:
        # that should not happen since we have checked the input in argparse
        err_print(f"FAILED: Invalid output format {output_fmt}!")
        return

    sanitized_title = "_".join(re.sub(r'[/:*?"<>|]', "", title).split())
    if no_sub_dir:
        sticker_output_path = os.path.join(
            default_sticker_output_root_dir, f"{sanitized_title}({pack_id})"
        )
    else:
        sticker_output_path = os.path.join(
            default_sticker_output_root_dir,
            f"{sanitized_title}({pack_id})",
            f"{output_format.value}",
        )

    if output_format == OutputFormat.RAW:
        norm_print("Copying raw sticker files to output folder... ", end="")
        shutil.copytree(
            sticker_temp_raw_path,
            sticker_output_path,
            dirs_exist_ok=True,
        )
        if open_folder:
            os.startfile(sticker_output_path)
        return

    # check dependency for processing
    if not shutil.which("magick"):
        err_print(
            "Error: ImageMagick is missing. Please install missing dependencies are re-run the program"
        )
        return

    process_queue = Queue()

    if scale_px:
        sticker_output_path += f"_scale_{scale_px}"
    if not os.path.isdir(sticker_output_path):
        os.makedirs(sticker_output_path)

    if not has_animation and output_format not in [OutputFormat.APNG, OutputFormat.GIF]:
        err_print(
            "ERROR: Sticker pack does not have animation, only PNG and GIF output are supported!"
        )
        return

    for sticker_id in id_list:
        sub_folder = "static"
        if is_emoji:
            sub_folder = "emoji"
        else:
            if has_animation:
                sub_folder = "animation"
            if has_popup:
                sub_folder = "popup"

        in_pic = os.path.join(sticker_temp_raw_path, sub_folder, f"{sticker_id}.png")
        in_audio = os.path.join(sticker_temp_raw_path, "sound", f"{sticker_id}.m4a")
        in_overlay = os.path.join(
            sticker_temp_raw_path, "default_overlay", f"{sticker_id}.png"
        )

        result_output = os.path.join(
            sticker_output_path, f"{sticker_id}.{output_format.value}"
        )

        operations = []

        # order of operation: overlay, scale, other conversions (gif, webm, video)
        if has_text_overlay and not no_default_txt_overlay:
            operations.append(Operation.OVERLAY)
        if scale_px:
            operations.append(Operation.SCALE)
        if remove_alpha:
            operations.append(Operation.REMOVE_ALPHA)

        if output_format == OutputFormat.GIF:
            operations.append(Operation.TO_GIF)
        elif output_format == OutputFormat.WEBM:
            operations.append(Operation.TO_WEBM)
        elif output_format == OutputFormat.MP4:
            operations.append(Operation.TO_MP4)

        process_queue.put_nowait(
            ProcessTask(
                sticker_id,
                in_pic,
                in_audio,
                in_overlay,
                scale_px,
                operations,
                result_output,
            )
        )

    processor = [
        ImageProcessorThread(
            process_queue, sticker_process_temp_root, sticker_type, output_format
        )
        for _ in range(thread_num)
    ]
    for p in processor:
        p.start()
    print("Processing stickers...")
    wait_for_queue_with_progress(quiet, process_queue, sticker_count)

    # TODO icon for all sticker packs

    norm_print("Process done! Cleaning up...")

    # os.startfile(sticker_process_temp_root)
    if open_folder:
        os.startfile(sticker_output_path)


def rearrange_pack_content(sticker_extracted_zip_path, sticker_raw_path, is_emoji):
    # copy useful files to raw folder and rename
    if is_emoji:
        # emoji
        emoji_path = os.path.join(sticker_raw_path, "emoji")
        if not os.path.isdir(emoji_path):
            os.mkdir(emoji_path)
        for fn in os.listdir(sticker_extracted_zip_path):
            if match := re.match(r"(\d+)(_animation)?\.png", fn):
                shutil.copy(
                    os.path.join(sticker_extracted_zip_path, fn),
                    os.path.join(emoji_path, match.group(1) + ".png"),
                )
        # metadata
        shutil.copy(
            os.path.join(sticker_extracted_zip_path, "meta.json"),
            os.path.join(sticker_raw_path, "meta.json"),
        )
    else:
        # the static stickers exist in all packs
        static_path = os.path.join(sticker_raw_path, "static")
        if not os.path.isdir(static_path):
            os.mkdir(static_path)
        for fn in os.listdir(sticker_extracted_zip_path):
            if match := re.match(r"(\d+)@2x\.png", fn):
                shutil.copy(
                    os.path.join(sticker_extracted_zip_path, fn),
                    os.path.join(static_path, match.group(1) + ".png"),
                )
        # animations
        if os.path.isdir(os.path.join(sticker_extracted_zip_path, "animation@2x")):
            animation_path = os.path.join(sticker_raw_path, "animation")
            if not os.path.isdir(animation_path):
                os.mkdir(animation_path)
            for fn in os.listdir(
                os.path.join(sticker_extracted_zip_path, "animation@2x")
            ):
                if match := re.match(r"(\d+)@2x\.png", fn):
                    shutil.copy(
                        os.path.join(
                            sticker_extracted_zip_path,
                            "animation@2x",
                            fn,
                        ),
                        os.path.join(animation_path, match.group(1) + ".png"),
                    )
        # sound
        if os.path.isdir(os.path.join(sticker_extracted_zip_path, "sound")):
            sound_path = os.path.join(sticker_raw_path, "sound")
            if not os.path.isdir(sound_path):
                os.mkdir(sound_path)
            for fn in os.listdir(os.path.join(sticker_extracted_zip_path, "sound")):
                shutil.copy(
                    os.path.join(sticker_extracted_zip_path, "sound", fn),
                    os.path.join(sound_path, fn),
                )
        # popup
        if os.path.isdir(os.path.join(sticker_extracted_zip_path, "popup")):
            popup_path = os.path.join(sticker_raw_path, "popup")
            if not os.path.isdir(popup_path):
                os.mkdir(popup_path)
            for fn in os.listdir(os.path.join(sticker_extracted_zip_path, "popup")):
                shutil.copy(
                    os.path.join(sticker_extracted_zip_path, "popup", fn),
                    os.path.join(popup_path, fn),
                )
        # icon
        shutil.copy(
            os.path.join(sticker_extracted_zip_path, "tab_on@2x.png"),
            os.path.join(sticker_raw_path, "icon.png"),
        )
        # metadata
        shutil.copy(
            os.path.join(sticker_extracted_zip_path, "productInfo.meta"),
            os.path.join(sticker_raw_path, "productInfo.meta"),
        )


def extract_pack_info_from_metadata(metadata, pack_id, lang, is_emoji):
    lang_used = lang
    if metadata["title"].get(lang):
        title = metadata["title"][lang]
        author_name = metadata["author"][lang]
    else:
        # en should always be available
        title = metadata["title"]["en"]
        author_name = metadata["author"]["en"]
        lang_used = "en"
    if is_emoji:
        if metadata.get("sticonResourceType") == "ANIMATION":
            sticker_type = StickerType.ANIMATED_EMOJI
        else:
            sticker_type = StickerType.EMOJI
        id_list = metadata["orders"]
    else:
        if "stickerResourceType" not in metadata:
            sticker_type = StickerType.STATIC_STICKER
        else:
            sticker_type = StickerType(metadata["stickerResourceType"])
        id_list = [i["id"] for i in metadata["stickers"]]
    pack_info = {
        "title": title,
        "author_name": author_name,
        "lang_used": lang_used,
        "pack_id": pack_id,
        "sticker_type": sticker_type.value,
        "count": len(id_list),
        "stickers": id_list,
    }
    return pack_info


if __name__ == "__main__":
    main()
    # do cleanup
    # remove temp dir
    shutil.rmtree(sticker_process_temp_root)
