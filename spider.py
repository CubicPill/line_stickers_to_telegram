from threading import Thread

import requests
import os
from utils import FAKE_HEADERS


def download_file(url, filename, proxies):
    if os.path.isfile(filename):
        # file exist
        return
    r = requests.get(url, proxies=proxies, headers=FAKE_HEADERS)
    with open(filename, 'wb') as f:
        f.write(r.content)


class DownloadThread(Thread):
    def __init__(self, queue, out_queue, proxies=None):
        Thread.__init__(self, name='DownloadThread')
        self.queue = queue
        self.out_queue = out_queue
        self.proxies = proxies

    def run(self):
        while not self.queue.empty():
            _id, url, path = self.queue.get()
            try:
                download_file(url, path, self.proxies)
            except requests.RequestException:
                self.queue.put((_id, url, path))

            else:
                self.out_queue.put(_id)
            finally:
                self.queue.task_done()
