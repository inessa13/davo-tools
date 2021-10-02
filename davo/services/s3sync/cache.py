import os
import sqlite3
import threading

from . import conf

QUERY_CREATE_TABLE = (
    'CREATE TABLE IF NOT EXISTS s3keys ( '
    'name text unique, '
    'size int, '
    'last_modified text, '
    'etag text, '
    'level int)'
)
QUERY_SELECT_TOTAL = 'SELECT COUNT(*) FROM s3keys'
QUERY_TRUNCATE = 'DELETE FROM s3keys WHERE level > 0'
QUERY_EXISTS = 'SELECT COUNT(*) FROM s3keys WHERE name=?'
QUERY_UPDATE = (
    'UPDATE s3keys SET '
    'name=:name, '
    'size=:size, '
    'last_modified=:last_modified, '
    'etag=:etag, '
    'level=:level '
    'WHERE name=:source'
)
QUERY_INSERT = (
    'INSERT INTO s3keys (name, size, last_modified, etag, level) '
    'VALUES (:name, :size, :last_modified, :etag, :level)'
)
QUERY_DELETE = 'DELETE FROM s3keys WHERE name=?'
QUERY_FILTER = 'SELECT name, size, last_modified, etag FROM s3keys'


class Cache:
    conn = None

    def __init__(self):
        self._lock = threading.RLock()

    def init(self):
        path = os.path.join(
            conf.get('PROJECT_ROOT'), conf.get('CACHE_FILE_NAME'))
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.cursor().execute(QUERY_CREATE_TABLE)

    def update(self, name, data):
        self._lock.acquire()
        try:
            cur = self.conn.cursor()

            level = len(data.get('name').split('/'))
            data = {'level': level, **data}
            exists = cur.execute(QUERY_EXISTS, (name,))
            if exists.fetchone()[0]:
                cur.execute(QUERY_UPDATE, {'source': name, **data})
            else:
                cur.execute(QUERY_INSERT, data)
        finally:
            self._lock.release()

    def select(self, prefix=None, delimiter=None):
        cur = self.conn.cursor()

        query = ' WHERE 1=1'
        if prefix:
            prefix = prefix.strip('/')
            query += ' and name like "{}/%"'.format(prefix)
            prefix_level = len(prefix.split('/')) + 1
        else:
            prefix_level = 1

        if delimiter:
            query += ' and level={}'.format(prefix_level)

        for line in cur.execute(QUERY_FILTER + query).fetchall():
            name, size, last_modified, etag = line
            yield {
                'name': name,
                'size': size,
                'last_modified': last_modified,
                'etag': etag,
            }

    def delete(self, name):
        self._lock.acquire()
        try:
            self.conn.cursor().execute(QUERY_DELETE, (name,))
        finally:
            self._lock.release()

    def total(self):
        return self.conn.cursor().execute(QUERY_SELECT_TOTAL).fetchone()[0]

    def clear(self):
        self._lock.acquire()
        try:
            self.conn.cursor().execute(QUERY_TRUNCATE)
        finally:
            self._lock.release()

    def flush(self):
        self._lock.acquire()
        try:
            self.conn.commit()
        finally:
            self._lock.release()

    def close(self):
        self.conn.close()


cache = Cache()
