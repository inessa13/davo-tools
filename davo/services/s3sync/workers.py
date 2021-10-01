import queue
import threading
import time

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
                task, args = self.task_queue.get(timeout=10)
            except queue.Empty:
                break

            try:
                task(*args, worker=self)
                if self.cb_queue:
                    self.cb_queue.put((task.name, 100, task.size()))
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
    def __init__(self, index, cb_queue, output, tasks_total):
        super().__init__()
        self.daemon = True

        self.index = index
        self.cb_queue = cb_queue
        self.output = output

        self.tasks_total = tasks_total
        self.tasks_processed = 0
        self.tasks_processed_d = {}
        self.size = 0

        self._t = time.time()

    def run(self):
        while True:
            data = self.cb_queue.get()
            try:
                self.handler_cb(*data)
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
        size = sum(item['size'] for item in self.tasks_processed_d.values())
        return self._handler(progress, size)

    def _handler(self, progress, size):
        len_full = 40
        progress_len = int(progress) * len_full // 100

        delta = time.time() - self._t
        if delta:
            speed = utils.humanize_size(size / delta)
        else:
            speed = 'n\\a'

        self.output[self.index] = conf.get('UPLOAD_FORMAT').format(
            progress='=' * progress_len,
            left=' ' * (len_full - progress_len),
            progress_percent=progress,
            speed=speed,
            info='{}/{}'.format(self.tasks_processed, self.tasks_total),
        )


class ThreadPool:
    def __init__(self, num_threads, auto_start=False):
        self.num_threads = num_threads
        self.cb_queue = queue.Queue()
        self.task_queue = queue.Queue()
        self.sys = None
        self.tasks_total = 0

        if auto_start:
            self.start()

    def start(self, output=None):
        if self.num_threads > 1:
            self.sys = _System(
                index=0,
                cb_queue=self.cb_queue,
                output=output,
                tasks_total=self.tasks_total)
            self.sys.start()

        for index in range(1, self.num_threads):
            worker = _Worker(
                index=index,
                task_queue=self.task_queue,
                cb_queue=self.cb_queue,
                output=output)
            worker.start()

    def add_task(self, task, bucket, name, data):
        self.tasks_total += 1
        args = bucket, name, data
        self.task_queue.put((task, args))

    def join(self):
        while self.task_queue.unfinished_tasks:
            time.sleep(0.1)

        self.task_queue.join()

        if self.sys is not None:
            self.sys.join(timeout=1)
