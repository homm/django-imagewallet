# -*- coding: utf-8 -*-

import hashlib
from os.path import splitext

from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.utils.functional import cached_property

from PIL import Image
from PIL.Image import EXTENSION
from format import ImageFormat


__all__ = ['Wallet', 'HashDirWallet', 'SingleFormatWallet']


class BaseWalletMetaclass(type):

    def __new__(cls, name, bases, attrs):
        super_new = super(BaseWalletMetaclass, cls).__new__

        if 'storage' in attrs and 'original_storage' not in attrs:
            attrs['original_storage'] = attrs['storage']

        return super_new(cls, name, bases, attrs)


class BaseWallet(object):
    """
    Базовый тип для хранилищ.
    """
    __metaclass__ = BaseWalletMetaclass

    storage = default_storage
    original_storage = default_storage

    @staticmethod
    def _save_format(format, image, storage, file_path):
        """
        Сохраняет изображение с применением заданного формата.
        """
        # сохраняем на тот случай, если фильтры потрут
        original_file_type = image.format

        # накладываем фильтры
        image = format.process(image)
        image.format = original_file_type

        # Сохраняем файл по тому же пути, чтобы не создавать иерархию папок.
        storage.save(file_path, ContentFile(''))
        file = storage.open(file_path, mode='wb')
        try:
            return format.save(image, file)
        finally:
            file.close()

    def __init__(self, path_original):
        """
        Принимает только путь до оригинального изображения.
        """
        self.path_original = path_original

    def __unicode__(self):
        return self.path_original

    def __repr__(self, *args, **kwargs):
        class_ = type(self).__name__
        return u"<%s '%s' at %s>" % (class_, self.path_original, id(self))

    @cached_property
    def _path_info(self):
        """
        Возвращает имя оригинального файла без расширения
        и тип этого файла по расширению.
        """
        # Путь равен оригиналу без расширения.
        # Тип получается на основе расширения.
        path, ext = splitext(self.path_original)
        return path + '_', EXTENSION.get(ext, None)

    @cached_property
    def url_original(self):
        """
        Возаврщает url до оригинального изображения.
        """
        return self.original_storage.url(self.path_original)

    def load_original(self):
        """
        Загружает экземпляр оригинального изображения.
        """
        # Предыдущая реализация кешировала оригинальное изображение,
        # на случай, если придется обрабатывать обработать несколько форматов.
        # На самом деле открытие изображения довольно быстрая операция
        # по сравнению с остальным, а память при обработке в цикле течет.
        file = self.original_storage.open(self.path_original)
        original = Image.open(file)
        # Проблема: _get_path(), который занимается генерацией пути до разных
        # форматов, должен спросить у формата тип файла. Формату, чтобы этот
        # тип узнать, нужно знать тип файла оригинального изображения.
        # Но _get_path() может взять его только из имени файла.
        # Картинка original часто попадает в метод save() формата изображения,
        # где уже не основе original.format снова выясняется тип файла готового
        # изображения. Теоретически original.format может не совпасть
        # с форматом, определенным из имени. Тогда сгенерированная картинка,
        # как и оригинальная будет иметь неверное расширение. Присваивая
        # original.format тип файла, полученный из имени, мы разрываем
        # порочный круг.
        original.format = self._path_info[1]
        return original

    def _get_path(self, name, format):
        """
        Возвращает путь до файла в сторадже для заданного формата.
        Используется через проперти path_<name>.
        """
        file_type = format.get_file_type(self._path_info[1])
        # Расширение — первый элемент в описании типа файла.
        extension = format.file_types[file_type][0]
        return self._path_info[0] + name + extension

    def _get_url(self, name, format):
        """
        Возаврщает url до формата, кроме оригинального, проверяет что
        изображение существует. Используется через проперти url_<name>.
        """
        file_path = self._get_path(name, format)
        storage = self.storage
        if not storage.exists(file_path):
            self._save_format(format, self.load_original(), storage, file_path)
        return storage.url(file_path)

    def _load_format(self, name, format):
        """
        Загружает экземпляр изображения любого формата. Используется через
        функцию load_<name>.
        """
        file_path = self._get_path(name, format)
        storage = self.storage
        if storage.exists(file_path):
            return Image.open(storage.open(file_path))
        return self._save_format(format, self.load_original(),
            storage, file_path)


class WalletMetaclass(BaseWalletMetaclass):
    """
    Управляет созданием хранилищь. Для кажого объявленногофвормата создает
    свойства path_<format> и url_<format>, а так же метод load_<format>.
    """

    def __new__(cls, name, bases, attrs):
        super_new = super(WalletMetaclass, cls).__new__

        # Одно замыкание на все три функции.
        def make_properties(name, format):
            get_path = lambda self: Wallet._get_path(self, name, format)
            get_url = lambda self: Wallet._get_url(self, name, format)
            load_format = lambda self: Wallet._load_format(self, name, format)
            return {'path_' + name: property(get_path),
                'url_' + name: property(get_url),
                'load_' + name: load_format}

        # Итерируем пользовательские свойства. items делает копию в памяти,
        # поэтому можно делать attrs.update
        for format_name, format in attrs.items():
            if isinstance(format, ImageFormat) and format_name != 'original':
                # Если находим среди них ImageFormat.
                attrs.update(make_properties(format_name, format))

        return super_new(cls, name, bases, attrs)


class Wallet(BaseWallet):
    """
    Объекты хранилищ похожи на модели в django. Для каждого набора форматов
    нужно отнаследоваться от класса Wallet и объявить экземпляры ImageFormat
    как его элементы.
    """
    __metaclass__ = WalletMetaclass


class HashDirWallet(Wallet):
    """
    Версия, которая хранит сгенерированные картинки не рядом с оригиналом,
    а в отдельной папке и именем как хэш.
    """
    file_path_prefix = 'walletcache/'

    @cached_property
    def _path_info(self):
        # От оригинального имени файла берется хэш.
        # Работает достаточно быстро: 660к генераций в секунду.
        hex = hashlib.md5(self.path_original).hexdigest()
        # Из префикса и хэша строится путь.
        path = self.file_path_prefix + '%s/%s/%s_' % (hex[-2:], hex[-3], hex)
        # Тип получается на основе расширения.
        file_type = EXTENSION.get(splitext(self.path_original)[1], None)
        return (path, file_type)


class SingleFormatWallet(BaseWallet):
    """
    Специальный тип хранилища с одним форматом, который должен быть объявлен
    как атрибут format, а его имя как format_name.
    """

    @property
    def path(self):
        return self._get_path(self.format_name, self.format)

    @property
    def url(self):
        return self._get_url(self.format_name, self.format)

    def load(self):
        return self._load_format(self.format_name, self.format)
