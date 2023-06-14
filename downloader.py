import argparse
import hashlib
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
from utils import MESSAGE_STICKER_OVERLAY_DEFAULT, STICKER_SET_URL_REGEX, SourceUrlType, \
    StickerType, sticker_type_properties
from webreq import MultiThreadDownloader, get_metadata, get_real_pack_id_from_yabe_emoji, \
    get_sticker_archive, get_sticker_info_from_line_page


def main():
    arg_parser = argparse.ArgumentParser(description='Download stickers from line store')

    # critical arguments
    arg_parser.add_argument('id_url', type=str, help='Product id of sticker set or the URL (yabe, line)')

    arg_parser.add_argument('--type', type=str,
                            help='Specify the type of the pack', default='sticker',
                            choices=['sticker', 'emoji'])

    # auxiliary
    arg_parser.add_argument('--lang', type=str,
                            help='Language used when accessing Line page.', default='zh-Hant',
                            choices=['zh-Hant', 'en', 'ja', 'ko', 'th', 'id', 'pt-BR', ])
    arg_parser.add_argument('--proxy', type=str, help='proxy, http(s)://addr:port')
    arg_parser.add_argument('-y', action='store_true', help='Skip confirmation')
    arg_parser.add_argument('--redownload', action='store_true', help='Redownload stickers even if they exist')

    # conversion options
    arg_parser.add_argument('--output-fmt', type=str, help='Output format', default='none',
                            choices=['none', 'png', 'gif', 'webm', 'video'])
    # arg_parser.add_argument('--output-fmt', type=str, help='Output format', default='apng',
    #                         choices=['apng', 'gif', 'webm', 'video'])
    arg_parser.add_argument('--scale', help='Scale static stickers to 512*512, preserving aspect ratio',
                            action='store_true')

    # for message stickers only
    arg_parser.add_argument('--no-default-txt-overlay', action='store_true',
                            help='Do not put default text overlay on message stickers')

    # not commonly used
    arg_parser.add_argument('-t', '--threads', type=int, help='Thread number of downloader, default 4')

    args = arg_parser.parse_args()

    # check dependency
    if not shutil.which('magick'):
        print('Error: ImageMagick is missing. Please install missing dependencies are re-run the program')
        exit(1)

    sticker_data_root_dir = os.path.join(os.getcwd(), 'sticker_dl')
    if not os.path.exists(sticker_data_root_dir):
        os.mkdir(sticker_data_root_dir)

    sticker_output_root_dir = os.path.join(os.getcwd(), 'sticker_out')
    if not os.path.exists(sticker_output_root_dir):
        os.mkdir(sticker_output_root_dir)

    proxies = {}
    if args.proxy:
        proxies['https'] = args.proxy
    webreq.set_proxy(proxies)
    thread_num = args.threads or 4

    lang = args.lang

    dl_type = args.type

    # check if input is id or url
    if 'http' not in args.id_url:
        pack_id = args.id_url.strip()
        is_emoji = dl_type == 'emoji'
        if not is_emoji and len(pack_id) >= 24:
            print(
                    'WARNING: You probably want to download an emoji pack, but the sticker type is not specified as emoji.')
    else:
        # input is url
        # extract pack id from url
        for _type, (_regex, _emoji_flag) in STICKER_SET_URL_REGEX.items():
            match = _regex.match(args.id_url)
            if match:
                print(f"URL is matched as: {_type}")
                pack_id = match.group(1)
                is_emoji = _emoji_flag

                if _type == SourceUrlType.YABE_EMOJI:
                    # special processing to get real pack id
                    pack_id = get_real_pack_id_from_yabe_emoji(pack_id)
                break
        else:
            print("URL is not matched as any known source! Please double check the url")
            sys.exit(1)

    # from here, pack_id should be ready. Check if the sticker set has already been downloaded
    for d in os.listdir(sticker_data_root_dir):
        if os.path.isdir(os.path.join(sticker_data_root_dir, d)):
            e_pack_id = d.split('.')[0]
            if pack_id == e_pack_id:
                # exists. open metadata file
                if os.path.exists(os.path.join(sticker_data_root_dir, d, 'info.json')):
                    with open(os.path.join(sticker_data_root_dir, d, 'info.json'), 'r', encoding='utf-8') as f:
                        pack_info = json.load(f)
                        print(f"Found local metadata for pack {pack_id}!")
                        break
    else:
        # get metadata
        try:
            metadata = get_metadata(pack_id, is_emoji)
        except FileNotFoundError:
            print(f'FAILED: Cannot find sticker set {pack_id} with type "{dl_type}"!')
            sys.exit(1)
        title, author_name, author_id = get_sticker_info_from_line_page(pack_id, is_emoji, lang)
        if is_emoji:
            if metadata.get('sticonResourceType') == 'ANIMATION':
                sticker_type = StickerType.ANIMATED_EMOJI
            else:
                sticker_type = StickerType.EMOJI
            id_list = metadata['orders']
        else:
            if 'stickerResourceType' not in metadata:
                sticker_type = StickerType.STATIC_STICKER
            else:
                sticker_type = StickerType(metadata['stickerResourceType'])
            id_list = [i['id'] for i in metadata['stickers']]

        pack_info = {
            'title': title,
            'author_name': author_name,
            'author_id': author_id,
            'pack_id': pack_id,
            'sticker_type': sticker_type.value,
            'count': len(id_list),
            'stickers': id_list,
            'archive_md5': None
        }
    title = pack_info['title']
    sticker_type = StickerType(pack_info['sticker_type'])
    id_list = pack_info['stickers']
    sticker_count = len(id_list)
    has_animation, has_sound, has_popup, has_text_overlay, is_emoji = sticker_type_properties(sticker_type)
    scale_px = 0
    if args.scale and not has_animation:
        scale_px = 512
    elif args.output_fmt == 'webm':
        if is_emoji:
            scale_px = 100
        else:
            scale_px = 512
    print('-----------------Sticker pack info:-----------------')
    print('Title:', title)
    print('Pack ID:', pack_id)
    print('Sticker Type:', sticker_type.name)
    print('Total number of stickers:', sticker_count)
    if args.output_fmt == 'none':
        print('Output format: <Download Only>')
    else:
        print('Output format:', args.output_fmt)
    if scale_px:
        print('Scale:', f'{scale_px}*{scale_px}px')
    if sticker_type == StickerType.MESSAGE_STICKER:
        print('Default text overlay:', not args.no_default_txt_overlay)
    print('----------------------------------------------------')
    if not args.y:
        confirm = input('Do you wish to continue? Y/n: ')
        if confirm.lower() == 'n':
            print('Aborting...')
            sys.exit(0)
        elif confirm and confirm.lower() != 'y':
            print('Invalid input. Aborting...')
            sys.exit(1)

    # create folders
    sanitized_title = '_'.join(re.sub(r'[/:*?"<>|]', '', title).split())
    folder_name = pack_id + '.' + sanitized_title
    sticker_pack_root = os.path.join(sticker_data_root_dir, folder_name)
    if not os.path.isdir(sticker_pack_root):
        os.mkdir(sticker_pack_root)

    sticker_dl_path = os.path.join(sticker_pack_root, 'dl')
    if not os.path.isdir(sticker_dl_path):
        os.mkdir(sticker_dl_path)

    sticker_process_temp_root = tempfile.mkdtemp()
    sticker_temp_store_extracted_zip_path = os.path.join(sticker_process_temp_root, 'extracted')

    # check if the archive has already been downloaded
    archive_path = os.path.join(sticker_dl_path, 'archive.zip')
    download_archive = True
    if os.path.exists(archive_path):
        # verify integrity using md5
        print('Archive exists. Verifying integrity... ', end='')
        with open(archive_path, 'rb') as f:
            archive_content = f.read()
        archive_md5 = hashlib.md5(archive_content).hexdigest()
        if archive_md5 == pack_info['archive_md5']:
            print('OK!')
            download_archive = False
        else:
            print('Verification failed! Redownload...')
            os.remove(archive_path)
    if download_archive:
        # download sticker pack
        print('Downloading sticker pack archive... ', end='')
        archive_content = get_sticker_archive(pack_id, sticker_type)
        print('Complete!')
        # save archive and unzip to temp folder
        with open(archive_path, 'wb') as f:
            f.write(archive_content)
        # calculate md5 for future verification
        archive_md5 = hashlib.md5(archive_content).hexdigest()
        pack_info['archive_md5'] = archive_md5

    with open(os.path.join(sticker_pack_root, 'info.json'), 'w', encoding='utf-8') as f:
        json.dump(pack_info, f, ensure_ascii=False, indent=4)

    sticker_raw_path = os.path.join(sticker_pack_root, 'raw')

    if not os.path.isdir(sticker_raw_path):
        os.mkdir(sticker_raw_path)

        print('Extracting archive... ', end='')
        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            zip_ref.extractall(sticker_temp_store_extracted_zip_path)
        print('Complete!')

        # copy useful files to raw folder and rename
        if is_emoji:
            # emoji
            emoji_path = os.path.join(sticker_raw_path, 'emoji')
            if not os.path.isdir(emoji_path):
                os.mkdir(emoji_path)
            for fn in os.listdir(sticker_temp_store_extracted_zip_path):
                if match := re.match(r'(\d+)(_animation)?\.png', fn):
                    shutil.copy(os.path.join(sticker_temp_store_extracted_zip_path, fn),
                                os.path.join(emoji_path, match.group(1) + '.png'))
            # metadata
            shutil.copy(os.path.join(sticker_temp_store_extracted_zip_path, 'meta.json'),
                        os.path.join(sticker_raw_path, 'meta.json'))
        else:
            # the static stickers exist in all packs
            static_path = os.path.join(sticker_raw_path, 'static')
            if not os.path.isdir(static_path):
                os.mkdir(static_path)
            for fn in os.listdir(sticker_temp_store_extracted_zip_path):
                if match := re.match(r'(\d+)@2x\.png', fn):
                    shutil.copy(os.path.join(sticker_temp_store_extracted_zip_path, fn),
                                os.path.join(static_path, match.group(1) + '.png'))
            # animations
            if os.path.isdir(os.path.join(sticker_temp_store_extracted_zip_path, 'animation@2x')):
                animation_path = os.path.join(sticker_raw_path, 'animation')
                if not os.path.isdir(animation_path):
                    os.mkdir(animation_path)
                for fn in os.listdir(os.path.join(sticker_temp_store_extracted_zip_path, 'animation@2x')):
                    if match := re.match(r'(\d+)@2x\.png', fn):
                        shutil.copy(os.path.join(sticker_temp_store_extracted_zip_path, 'animation@2x', fn),
                                    os.path.join(animation_path, match.group(1) + '.png'))
            # sound
            if os.path.isdir(os.path.join(sticker_temp_store_extracted_zip_path, 'sound')):
                sound_path = os.path.join(sticker_raw_path, 'sound')
                if not os.path.isdir(sound_path):
                    os.mkdir(sound_path)
                for fn in os.listdir(os.path.join(sticker_temp_store_extracted_zip_path, 'sound')):
                    shutil.copy(os.path.join(sticker_temp_store_extracted_zip_path, 'sound', fn),
                                os.path.join(sound_path, fn))
            # popup
            if os.path.isdir(os.path.join(sticker_temp_store_extracted_zip_path, 'popup')):
                popup_path = os.path.join(sticker_raw_path, 'popup')
                if not os.path.isdir(popup_path):
                    os.mkdir(popup_path)
                for fn in os.listdir(os.path.join(sticker_temp_store_extracted_zip_path, 'popup')):
                    shutil.copy(os.path.join(sticker_temp_store_extracted_zip_path, 'popup', fn),
                                os.path.join(popup_path, fn))
            # icon
            shutil.copy(os.path.join(sticker_temp_store_extracted_zip_path, 'tab_on@2x.png'),
                        os.path.join(sticker_raw_path, 'icon.png'))
            # metadata
            shutil.copy(os.path.join(sticker_temp_store_extracted_zip_path, 'productInfo.meta'),
                        os.path.join(sticker_raw_path, 'productInfo.meta'))

        # cleanup temp folder
        shutil.rmtree(sticker_temp_store_extracted_zip_path)
    else:
        print('Sticker pack already exists, skip unarchive...')

    # for message sticker, download default overlay message in advance
    if sticker_type == StickerType.MESSAGE_STICKER:
        default_overlay_dl_path = os.path.join(sticker_dl_path, 'default_overlay')
        if not os.path.isdir(default_overlay_dl_path):
            os.mkdir(default_overlay_dl_path)
            print('Downloading default overlay message for message sticker... ')
            download_queue = Queue()
            download_completed_queue = Queue()
            downloader = [MultiThreadDownloader(download_queue, download_completed_queue) for _ in
                          range(thread_num)]

            for sticker_id in id_list:
                filename = os.path.join(default_overlay_dl_path, f'{sticker_id}.png')
                url = MESSAGE_STICKER_OVERLAY_DEFAULT.format(sticker_id=sticker_id, pack_id=pack_id)
                download_queue.put((sticker_id, url, filename))
            for d in downloader:
                d.start()

            with tqdm(total=sticker_count) as bar:
                last = sticker_count
                while not download_queue.empty():
                    bar.update(last - download_queue.qsize())
                    last = download_queue.qsize()
                    time.sleep(0.1)
                download_queue.join()
                bar.n = sticker_count
                bar.refresh()
                bar.clear()

            print('Message sticker default overlay download done!')
        else:
            print('Message sticker default overlay already exists, skip download...')
        # copy default overlay to sticker pack folder
        shutil.copytree(default_overlay_dl_path, os.path.join(sticker_raw_path, 'default_overlay'), dirs_exist_ok=True)
    if args.output_fmt == 'none':
        print('No processing will be done, exit...')
        sys.exit(0)

    # determine process option
    # for line, all stickers are png/apng
    if args.output_fmt == 'png':
        output_format = OutputFormat.APNG
    elif args.output_fmt == 'gif':
        output_format = OutputFormat.GIF
    elif args.output_fmt == 'webm':
        output_format = OutputFormat.WEBM
    elif args.output_fmt == 'video':
        output_format = OutputFormat.VIDEO

    else:
        print(f'FAILED: Invalid output format {args.output_fmt}!')
        sys.exit(1)

    process_queue = Queue()
    sticker_output_path = os.path.join(sticker_output_root_dir, f'{sanitized_title}({pack_id})',
                                       f'{output_format.value}')
    if scale_px:
        sticker_output_path += f'_scale_{scale_px}'
    if not os.path.isdir(sticker_output_path):
        os.makedirs(sticker_output_path)

    if not has_animation and output_format != OutputFormat.APNG:
        print('ERROR: Sticker pack does not have animation, only PNG output is supported!')
        sys.exit(1)

    for sticker_id in id_list:
        temp_dir = tempfile.mkdtemp()
        sub_folder = 'static'
        if is_emoji:
            sub_folder = 'emoji'
        else:
            if has_animation:
                sub_folder = 'animation'
            if has_popup:
                sub_folder = 'popup'

        in_pic = os.path.join(sticker_raw_path, sub_folder, f'{sticker_id}.png')
        in_audio = os.path.join(sticker_raw_path, 'sound', f'{sticker_id}.m4a')
        in_overlay = os.path.join(sticker_raw_path, 'default_overlay', f'{sticker_id}.png')

        result_output = os.path.sep.join([sticker_output_path, f'{sticker_id}.{output_format.value}'])

        operations = []

        # order of operation: overlay, scale, other conversions (gif, webm, video)
        if has_text_overlay and not args.no_default_txt_overlay:
            operations.append(Operation.OVERLAY)
        if scale_px:
            operations.append(Operation.SCALE)
        if output_format == OutputFormat.GIF:
            operations.append(Operation.TO_GIF)
        elif output_format == OutputFormat.WEBM:
            operations.append(Operation.TO_WEBM)
        # elif output_format==OutputFormat.VIDEO:
        #     operations.append(Operation.TO_VIDEO)

        process_queue.put_nowait(
                ProcessTask(sticker_id, in_pic, in_audio, in_overlay, scale_px, operations, result_output))

    processor = [ImageProcessorThread(process_queue, sticker_process_temp_root, sticker_type, output_format) for _ in
                 range(8)]
    for p in processor:
        p.start()
    with tqdm(total=sticker_count) as bar:
        last = sticker_count
        while not process_queue.empty():
            qsize = process_queue.qsize()
            bar.update(last - qsize)
            bar.refresh()
            last = qsize
            time.sleep(0.5)
        process_queue.join()
        bar.n = sticker_count
        bar.refresh()
        bar.clear()

    # TODO icon for all sticker packs

    print('Process done! Cleaning up...')

    # remove temp dir
    shutil.rmtree(sticker_process_temp_root)
    os.startfile(sticker_output_path)


if __name__ == '__main__':
    main()