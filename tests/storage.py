# -*- coding: utf-8 -*-

import StringIO
import urlparse

from django.core.files.storage import Storage
from django.utils.encoding import filepath_to_uri


class DictStorage(Storage):

    def __init__(self, base_url=None):
        self.storage = {}
        self.base_url = base_url

    def _open(self, name, mode='rb'):
        if name not in self.storage:
            self.storage[name] = StringIO.StringIO()
        self.storage[name].seek(0)
        return self.storage[name]

    def _save(self, name, content):
        if name in self.storage:
            del self.storage[name]
        file = self.storage[name] = StringIO.StringIO()
        file.write(content.read())

    def delete(self, name):
        if name in self.storage:
            del self.storage[name]

    def exists(self, name):
        return name in self.storage

    def size(self, name):
        if name in self.storage:
            return self.storage[name].len

    def url(self, name):
        if self.base_url is None:
            raise ValueError("This file is not accessible via a URL.")
        return urlparse.urljoin(self.base_url, filepath_to_uri(name))

