# -*- coding: utf-8 -*-

import hashlib
from os.path import splitext

from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.utils.functional import cached_property

from PIL import Image, ImageFile
from PIL.Image import EXTENSION, SAVE
from imagewallet.filters import convert


# Загружаем все доступный кодеки. Нужно для досупа к EXTENSION
Image.init()
# max block size for jpeg save in PIL
MAXBLOCK = 3200 * 2000


class ImageFormat(object):
    """
    Хранит информацию об обработке одного формата изображения. Изоражения
    генерируются в пригодных для веба типах файлов: JPEG, или PNG.
    """

    file_type = None
    # Если исходного типа файла нет в file_types, именно эот тип будет выбран.
    # PNG сохраняет во многих режимах и без потери качества.
    decline_file_type = 'PNG'
    file_types = {
        'JPEG': ('.jpg', ),
        'PNG': ('.png', )
    }

    def __init__(self, filters=None, file_type=None, decline_file_type='PNG',
            mode=None, background='white', **options):
        """
        Filters — список вызываемых объектов которым передается картинка
            во время обработки.
        File_type — тип файла, может быть 'jpeg', 'png' или None. None означает
            что нужно по возможности оставить исходный формат.
        Decline_file_type — тип файла, который будет использован только если
            исходный тип не может быть использован. Не имеет смысла, если явно
            задан file_type.
        Mode, в который нужно перевести изображения перед обработкой.
            None означает, что перевод не нужен.
        Background — предполагаемый фон изображения. Будет использован для
            непрозрачных форматов при увелличении размеров или при переводе
            в другой mode. Для принудительного задания фона прозрачным
            форматам, воспользуйтесь одноименным фильтром.
        Options — дополнительные параметры для file_type и сolorspace. Для
            file_type должны начинаться с префиксов 'png_' и 'jpeg_'. Например,
            'jpeg_quality'. Могут быть указаны даже если file_type опущен. Для
            сolorspace должны начинаться с префикса 'mode_'.
        """
        self.filters = filters or []
        self.file_type = file_type and file_type.upper()
        if file_type and self.file_type not in self.file_types:
            raise ValueError("Not allowed file type: %s" % file_type)
        self.decline_file_type = decline_file_type.upper()
        if self.decline_file_type not in self.file_types:
            raise ValueError("Not allowed file type: %s" % decline_file_type)
        self.mode = mode
        self.background = background
        self.options = options

    def _get_options(self, prefix):
        if not prefix.endswith('_'):
            prefix = prefix + '_'
        return {key[len(prefix):]: value
            for key, value in self.options.iteritems()
            if key.startswith(prefix)}

    def _prepare_for_process(self, image):
        """
        Подготавливает изображение к наложению фильтров.
        """
        if self.mode:
            options = self._get_options('mode')
            filter = convert(self.mode, self.background, **options)
            image = filter(image, self)
        return image

    def process(self, image):
        """
        Делает основную работу. Подготавливает изображение, применяет фильтры.
        """
        image = self._prepare_for_process(image)

        for filter in self.filters:
            image = filter(image, self)

        return image

    def get_file_type(self, original_file_type):
        """
        Возвращает тип файла сгенерированного изображения на основе типа файла,
        из которого генерируется изображение.
        """
        # Если тип файла не задан, он берется из исходного изображения.
        # Но только если это поддерживаемый тип. Иначе сохраняем в PNG.
        if self.file_type is None:
            if original_file_type in self.file_types:
                return original_file_type
            return self.decline_file_type
        return self.file_type

    def _get_save_params(self, image, file_type):
        # Опции для сохранения берутся из изображения и self.options
        save_params = self._get_options(file_type.lower())
        if file_type == 'JPEG' and 'progression' in image.info:
            save_params.setdefault('progressive', image.info['progression'])
        # Индекс прозрачного цвета в палитре должен выставляться вручную.
        if image.mode == 'P' and 'transparency' in image.info:
            save_params.setdefault('transparency', image.info['transparency'])
        return save_params

    def _prepare_for_save(self, image, file_type):
        # Каждый тип файла поддерживает свои режимы. Если картинка не такого
        # режима, нужно перевести к универсальному.
        if file_type == 'JPEG':
            supported = ['1', 'L', 'RGB', 'CMYK', 'YCbCr']
        elif file_type == 'PNG':
            supported = ['1', 'L', 'P', 'RGB', 'RGBA']

        if image.mode not in supported:
            image = convert('RGB', self.background)(image, self)
        return image

    def _save_to_file(self, image, file, file_type, save_params):
        # Если бы библиотека PIL была без приколов, тут была бы одна строчка:
        # image.save(file, format=file_type, **save_params)
        try:
            OLD_MAXBLOCK = ImageFile.MAXBLOCK
            ImageFile.MAXBLOCK = MAXBLOCK
            image.save(file, format=file_type, **save_params)
        except IOError:
            save_params.pop('optimize', None)
            save_params.pop('progression', None)
            save_params.pop('progressive', None)
            image.save(file, format=file_type, **save_params)
        finally:
            ImageFile.MAXBLOCK = OLD_MAXBLOCK

    def save(self, image, file):
        """
        Сохраняет уже готовое изображение в файл. Вызывающий должен
        позаботиться, чтобы image.format было заполнено верно.
        """
        # Если изображение не загружено с диска (format пустой),
        # get_file_type вернет file_type по-умолчанию.
        file_type = self.get_file_type(image.format)

        image = self._prepare_for_save(image, file_type)

        save_params = self._get_save_params(image, file_type)

        self._save_to_file(image, file, file_type, save_params)

        # т.к. файл уже сохранен в этом формате, присвиваем ему его.
        image.format = file_type
        return image


class OriginalImageFormat(ImageFormat):
    """
    Формат для сохранения оргинального типа файла.
    """
    # Типы файлов получаются из типов, в которые может сохранять PIL.
    # Для типов, у которых может быть много расширений, но есть одно
    # общеупотребимое, оно задаются явно.
    file_types = {'TIFF': ('.tif',), 'EPS': ('.eps',), 'PPM': ('.ppm',),
        'JPEG': ('.jpg',), 'WMF': ('.wmf',)}
    for _extension, _file_type in EXTENSION.iteritems():
        if _file_type in SAVE:
            file_types.setdefault(_file_type, (_extension,))
    del _extension, _file_type


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
