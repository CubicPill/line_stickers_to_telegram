from queue import Queue
from threading import Thread

import requests

from download import proxies
from utils import FAKE_HEADERS


# TODO: convert APNG to GIF / Video(with sounds)

def download_file(url, filename):
    print(url)
    r = requests.get(url, proxies=proxies, headers=FAKE_HEADERS)
    with open(filename, 'wb') as f:
        f.write(r.content)


class DownloadThread(Thread):
    def __init__(self, queue: Queue):
        Thread.__init__(self,name='DownloadThread')
        self.queue = queue

    def run(self):
        while not self.queue.empty():
            (url, path, sticker_type) = self.queue.get()
            try:
                download_file(url, path)
            except requests.RequestException:
                self.queue.put((url, path, sticker_type))
            finally:
                self.queue.task_done()


