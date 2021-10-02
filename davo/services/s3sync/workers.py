import datetime
import queue
import threading
import time

import davo.utils

from . import conf, utils


class _Worker(threading.Thread):
    """
    Thread executing tasks from a given tasks queue.
    """

    def __init__(self, index, task_queue, cb_queue, output=None):
        super().__init__()
        self.index = index
        self.task_queue = task_queue
        self.cb_queue = cb_queue
        self.daemon = True
        self.speed_list = []
        self.output = output

    def run(self):
        while self.task_queue.unfinished_tasks:
            try:
                task = self.task_queue.get(timeout=10)
            except queue.Empty:
                break

            try:
                task.exec(worker=self)
                if self.cb_queue:
                    self.cb_queue.put((task.name, 100, task.size()))
            except Exception as exc:
                utils.output_finish(
                    self.output,
                    'Unhandled error {}: {}'.format(type(exc).__name__, exc),
                )

            finally:
                self.task_queue.task_done()

    def speed(self, current):
        if not self.speed_list:
            return current
        return (sum(
            self.speed_list) + current) / float(len(self.speed_list) + 1)


class _System(threading.Thread):
    """
    System thread. Collect result from workers and draw output.
    """
    def __init__(self, index, cb_queue, output, tasks_total, size_total):
        super().__init__()
        self.daemon = True

        self.index = index
        self.cb_queue = cb_queue
        self.output = output

        self.tasks_total = tasks_total
        self.size_total = size_total
        self.tasks_processed = 0
        self.tasks_processed_d = {}
        self.size = 0

        self._t = time.time()

    def run(self):
        while True:
            data = self.cb_queue.get()
            try:
                self.handler_cb(*data)
            except Exception as exc:
                utils.output_finish(
                    self.output,
                    'Unhandled error {}: {}'.format(type(exc).__name__, exc),
                )
            finally:
                self.cb_queue.task_done()

    def handler_cb(self, name, progress, size):
        if (progress == 100 and self.tasks_processed_d.get(
                name, {}).get('progress') != 100):
            self.tasks_processed += 1

        self.tasks_processed_d[name] = {
            'progress': progress,
            'size': size,
        }

        progress = sum(
            item['progress'] for item in self.tasks_processed_d.values())
        progress = float(progress) / self.tasks_total
        size_all = sum(item['size'] for item in self.tasks_processed_d.values())

        len_full = 40
        progress_len = int(progress) * len_full // 100

        delta = time.time() - self._t
        if delta:
            speed = davo.utils.format.humanize_speed(size_all / delta)
        else:
            speed = 'n\\a'

        if size_all:
            estimate = 'Est: {}'.format(datetime.timedelta(
                seconds=int(delta * (self.size_total - size_all) / size_all)),
            )
        else:
            estimate = 'n\\a'

        elapsed = 'Elapse: {}'.format(datetime.timedelta(seconds=int(delta)))

        self.output[self.index] = conf.get('UPLOAD_FORMAT').format(
            progress='=' * progress_len,
            left=' ' * (len_full - progress_len),
            progress_percent=progress,
            speed=speed,
            estimate=estimate,
            elapsed=elapsed,
            info='{}/{}'.format(self.tasks_processed, self.tasks_total),
        )


class ThreadPool:
    def __init__(self, num_threads, auto_start=False):
        self.num_threads = num_threads
        self.cb_queue = queue.Queue()
        self.task_queue = queue.Queue()
        self.sys = None
        self.total_tasks = 0
        self.total_size = 0

        if auto_start:
            self.start()

    def start(self, output=None):
        if self.num_threads > 1:
            self.sys = _System(
                index=0,
                cb_queue=self.cb_queue,
                output=output,
                tasks_total=self.total_tasks,
                size_total=self.total_size,
            )
            self.sys.start()

        for index in range(1, self.num_threads):
            worker = _Worker(
                index=index,
                task_queue=self.task_queue,
                cb_queue=self.cb_queue,
                output=output)
            worker.start()

    def add_task(self, task):
        self.total_tasks += 1
        self.total_size += task.size()
        self.task_queue.put(task)

    def join(self):
        while self.task_queue.unfinished_tasks:
            time.sleep(0.1)

        self.task_queue.join()

        if self.sys is not None:
            self.sys.join(timeout=1)
