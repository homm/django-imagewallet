# -*- coding: utf-8 -*-

from django.utils.functional import curry
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files import File
from django.core.files.images import get_image_dimensions

import PIL


ORIGINAL_FORMAT = 'original'
# max block size for jpeg save in PIL
MAXBLOCK = 3200 * 2000


class ImageFormat(object):
    """
    Хранит информацию об обработке одного формата изображения.
    Один формат может быть приязан к нескольким полям, поэтому не содержит
    ссылки на поле.
    """
    file_types = {
        'JPEG': ('jpg', ),
        'PNG': ('png', )
    }
    failback_file_type = 'PNG'

    def __init__(self, filters=None, file_type=None, mode=None,
            background='white', **options):
        """
        Filters — список вызываемых объектов которым передается картинка
            во время обработки.
        File_type — тип файла, может быть 'jpeg', 'png' или None. None означает
            что нужно по возможности оставить исходный формат.
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
            raise ValueError("Not allowed file type: {}".format(file_type))
        self.mode = mode and mode.upper()
        self.background = background
        self.options = options

    def _get_options(self, prefix):
        return {key[len(prefix):]: value
            for key, value in self.options.iteritems()
            if key.startswith(prefix)}

    def prepare(self, image):
        """
        Подготавливает изображение к наложению фильтров. Преобразует в заданный
        mode. Если необходимо, заливает фон.
        """
        if self.mode is None or self.mode == image.mode:
            return image
        # TODO: Если self.mode непрозрачный, а image.mode был прозрачным,
        # нужно под image подложить self.background
        return image.convert(self.mode, **self._get_options('mode_'))

    def process(self, image):
        """
        Делает основную работу. Подготавливает изображение, применяет фильтры.
        """
        image = self.prepare(image)

        for filter in self.filters:
            image = filter(image)

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
            return self.failback_file_type
        return self.file_type

    def _get_save_params(self, image, file_type):
        # Опции для сохранения берутся из изображения и self.options
        save_params = self._get_options(file_type.lower() + '_')
        if file_type == 'JPEG' and 'progression' in image.info:
            save_params.setdefault('progressive', image.info['progression'])
        return save_params

    def _prepare_for_save(self, image, file_type):
        # Каждый тип файла поддерживает свои режимы. Если картинка не такого
        # режима, нужно перевести к универсальному.
        if file_type == 'JPEG':
            supported = ['1', 'L', 'RGB', 'RGBA', 'RGBX', 'CMYK', 'YCbCr']
        elif file_type == 'PNG':
            supported = ['1', 'L', 'P', 'RGB', 'RGBA']

        if image.mode not in supported:
            image = image.convert('RGB')
        return image

    def _save_to_file(self, image, file, file_type, save_params):
        # Если бы библиотека PIL была без приколов, тут была бы одна строчка:
        # image.save(file, format=file_type, **save_params)
        try:
            OLD_MAXBLOCK = PIL.ImageFile.MAXBLOCK
            PIL.ImageFile.MAXBLOCK = MAXBLOCK
            image.save(file, format=file_type, **save_params)
        except IOError:
            save_params.pop('optimize', None)
            save_params.pop('progression', None)
            save_params.pop('progressive', None)
            image.save(file, format=file_type, **save_params)
        finally:
            PIL.ImageFile.MAXBLOCK = OLD_MAXBLOCK

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

        # т.к. файл уже сохранен, в этом формате, присвиваем ему его.
        image.format = file_type
        return image


class WalletMetaclass(type):
    def __new__(cls, name, bases, attrs):
        super_new = super(WalletMetaclass, cls).__new__
        parents = [b for b in bases if isinstance(b, WalletMetaclass)]
        if not parents:
            # If this isn't a subclass of Model, don't do anything special.
            return super_new(cls, name, bases, attrs)

        # Итерируем пользовательские стрибуты
        for name, format in attrs.iteritems():
            if not isinstance(format, ImageFormat):
                continue
#            # Если находим среди них ImageFormat
#            attrs['path_' + name]
        return super_new(cls, name, bases, attrs)


class Wallet(object):
    """
    Объекты хранилищ похожи на модели в django. Для каждого набора форматов
    нужно отнаследоваться от класса Wallet и объявить экземпляры ImageFormat
    как его элементы.
    """
    __metaclass__ = WalletMetaclass

    storage = default_storage
    original_storage = default_storage

    # Единственный формат по-умолчанию, оригинальное изображение. Может быть
    # перекрыто.
    original = ImageFormat(jpeg_quality=95)

    @staticmethod
    def _save_format(format, image, storage, file_path):
        """
        Сохраняет изображение с применением заданного формата.
        """
        # сохраняем на тот случай, если фильтры потрут
        original_file_type = image.format

        # накладываем фильтры
        image = format.process(image)

        file = storage.open(file_path, mode='wb')
        try:
            image.format = original_file_type
            return format.save(image, file)
        finally:
            file.close()

    @classmethod
    def object_from_image(cls, image, file_pattern):
        """
        Создает новый объект подкласса Wallet из изображения.
        """
        format = cls.original

        # Тип файла, которого будет оригинальное изображение.
        original_file_type = format.get_file_type(image.format)
        # Расширение — первый элемент в описании типа файла.
        extension = format.file_types[original_file_type][0]
        file_path = file_pattern.format(f=ORIGINAL_FORMAT, e=extension)

        cls._save_format(cls.original, image, cls.original_storage, file_path)

        return cls(file_pattern, original_file_type)

    def __init__(self, file_pattern, original_file_type):
        assert '{f}' in file_pattern
        self.file_pattern = file_pattern
        self.original_file_type = original_file_type

    def path_original(self):
        """
        Возвращает путь до файла в сторадже для оргинального изображения.
        """
        # Расширение — первый элемент в описании типа файла.
        extension = self.original.file_types[self.original_file_type][0]
        return self.file_pattern.format(f=ORIGINAL_FORMAT, e=extension)

    def url_original(self):
        """
        Возаврщает url до оргинального изображения.
        """
        return self.original_storage.url(self.path_original())

    def load_original(self):
        """
        Загружает экземпляр оригинального изображения.
        """
        file = self.original_storage.open(self.path_original())
        # Наверное, неплохо было бы в format получившеся картинки положить
        # self.original_file_type. Будет странно и непонятно, если они
        # не совпадут. Но возможно если image.format не будет соответствовать
        # image.mode, будет еще хуже.
        return PIL.Image.open(file)

    def _get_path(self, name, format):
        """
        Возвращает путь до файла в сторадже для заданного формата, кроме
        оригинального. Используется через проперти path_<name>.
        """
        file_type = format.get_file_type(self.original_file_type)
        # Расширение — первый элемент в описании типа файла.
        extension = format.file_types[file_type][0]
        return self.file_pattern.format(f=name, e=extension)

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
        проперти load_<name>.
        """
        file_path = self._get_path(name, format)
        storage = self.storage
        if storage.exists(file_path):
            return PIL.Image.open(storage.open(file_path))
        return self._save_format(format, self.load_original(),
            storage, file_path)


class OldWallet(object):
    # this type used when image can be loaded, but it's type not supported
    image_type_fallback = 'PNG'
    image_types_extensions = {
        'PNG':  'png',
        'JPEG': 'jpg',
    }
    # Original Image, stored after saving or loaded from disk
    _loaded_original = False

    def __init__(self, formats, pattern=None, original_image_type=None,
            storage=None):
        """
        Pattern is a string with 2 replaces: "size" and "extension".
        original_image_type is type of saved original image.
        """
        self.formats = formats
        self._pattern = pattern
        self.original_image_type = original_image_type
        self.storage = storage or default_storage

        if original_image_type is not None and not pattern:
            raise ValueError('For saved files pattern is required')

        if pattern and '%(size)s' not in pattern:
            raise ValueError('Pattern string should contain %%(size)s replace.',
                ' Given pattern: %s' % pattern)

    def __unicode__(self):
        if self:
            return u'%s;%s' % (self._pattern, self.original_image_type)
        else:
            return u''

    def set_pattern(self, value):
        if self:
            raise ValueError("Can not change pattern for saved wallet. Delete first.")
        self._pattern = value
    pattern = property(lambda self: self._pattern, set_pattern)

    def __nonzero__(self):
        """
        original_image_type can be only for saved images. If original_image_type
        is None, nothing saved in this wallet.
        """
        return self.original_image_type is not None

    def __reduce__(self):
        """
        Save wallet as string.
        """
        return (unicode, (self.__unicode__(),))

    @classmethod
    def populate_formats(cls, formats):
        cls = OldWallet
        for format in formats:
            url_name = 'url_%s' % format
            if not hasattr(cls, url_name):
                setattr(cls, url_name, property(curry(cls.get_url, format=format)))
            path_name = 'path_%s' % format
            if not hasattr(cls, path_name):
                setattr(cls, path_name, property(curry(cls.get_path, format=format)))
            size_name = 'size_%s' % format
            if not hasattr(cls, size_name):
                setattr(cls, size_name, property(curry(cls.get_size, format=format)))

    def load_original(self):
        if not self:
            return None
        if not self._loaded_original:
            image = self.storage.open(self.get_path(ORIGINAL_FORMAT))
            self._loaded_original = PIL.Image.open(image)
        return self._loaded_original

    def save(self, image):
        """
        Loads new image to wallet.
        image may be path to file, django file or pil image
        Returns original image.
        """
        if self:
            raise ValueError("Can not save another images in saved wallet. Delete first.")

        if not self._pattern:
            raise ValueError("Pattern should be present.")

        if '%(size)s' not in self._pattern:
            raise ValueError('Pattern string should contain %%(size)s replace. Given pattern: %s' % self._pattern)

        if isinstance(image, basestring):
            image = self.storage.open(image)
            image = PIL.Image.open(image)
        elif isinstance(image, (file, File)):
            image = PIL.Image.open(image)
        elif isinstance(image, PIL.Image.Image):
            pass
        else:
            raise ValueError("Argument of this type is not supported.")

        self._loaded_original = image

        self.original_image_type = self.get_image_type(ORIGINAL_FORMAT,
            self._loaded_original.format)

        # process original image
        self._loaded_original = self.process_format(ORIGINAL_FORMAT, save=True)

        return self._loaded_original

    def process_format(self, format, image=None, save=False):
        """
        Process image, make one thumb from given format 
        """
        if image is None:
            image = self.load_original()

        if not image:
            return image

        for filter in self.formats[format]:
            if callable(filter):
                image = filter(image)

        if save:
            save_params = image.info

            # Save empty file to ensure path is exists
            self.storage.save(self.get_path(format), ContentFile(''))
            file = self.storage.open(self.get_path(format), mode='wb')
            try:
                image_type = self.get_image_type(format)
                if image_type == 'JPEG' and image.mode not in PIL.JpegImagePlugin.RAWMODE:
                    image = image.convert('RGB')

                try:
                    # Try save image with big block size
                    OLD_MAXBLOCK = PIL.ImageFile.MAXBLOCK
                    PIL.ImageFile.MAXBLOCK = MAXBLOCK
                    image.save(file, format=image_type, **save_params)
                except IOError:
                    # Else remove all options affected expected block size
                    if 'optimize' in save_params:
                        del save_params['optimize']
                    if 'progression' in save_params:
                        del save_params['progression']
                    if 'progressive' in save_params:
                        del save_params['progressive']
                    image.save(file, format=image_type, **save_params)
                finally:
                    PIL.ImageFile.MAXBLOCK = OLD_MAXBLOCK

            finally:
                file.close()
        return image

    def process_all_formats(self):
        for format in self.formats:
            if format != ORIGINAL_FORMAT:
                self.process_format(format, save=True)

    def copy(self, wallet):
        """
        Copy image from other wallet to this without changing. Filters for original format ignored.
        """
        if self:
            raise ValueError("Can not save another images in saved wallet. Delete first.")
        if not wallet:
            return
        self.original_image_type = wallet.original_image_type
        _from = wallet.get_path(ORIGINAL_FORMAT)
        _to = self.get_path(ORIGINAL_FORMAT)
        self.storage.save(_to, wallet.storage.open(_from))

    def delete(self):
        """
        Mark wallet as not saved and delete all files
        """
        if not self:
            return
        for format in self.formats:
            path = self.get_path(format)
            self.storage.delete(path)
        self.original_image_type = None
        self._loaded_original = False

    def clean(self, format):
        """
        Delete not-original images from disk. Safe for original image.
        """
        if not self or format == ORIGINAL_FORMAT:
            # Use delete() instead.
            return
        path = self.get_path(format)
        self.storage.delete(path)

    def get_size(self, format, image=None):
        " TODO: cache this"
        if not self:
            return (None, None)
        path = self.get_path(format)
        if format != ORIGINAL_FORMAT and not self.storage.exists(path):
            image = self.process_format(format, save=True)
            return image.size
        else:
            return get_image_dimensions(self.storage.open(path))

    def get_url(self, format):
        # url returns only for existing images
        if self:
            path = self.get_path(format)
            # if image not found, it created
            if format != ORIGINAL_FORMAT and not self.storage.exists(path):
                self.process_format(format, save=True)
            return self.storage.url(path)
        else:
            return None

    def get_path(self, format):
        if not self._pattern:
            return None
        image_type = self.get_image_type(format)
        extension = self.image_types_extensions.get(image_type)
        return self._pattern % {'size': format, 'extension': extension}

    def get_image_type(self, format, original_image_type=None):
        if format not in self.formats:
            raise AttributeError("%s has no format %s" %
                (self.__class__.__name__, format))

        # for not original format returns user-defined type
        if format != ORIGINAL_FORMAT and isinstance(self.formats[format][-1], basestring):
            return self.formats[format][-1]

        # for saved wallets return original image type
        if self.original_image_type is not None:
            return self.original_image_type

        # if don't saved, return custom image type for original format
        if isinstance(self.formats[ORIGINAL_FORMAT][-1], basestring):
            return self.formats[ORIGINAL_FORMAT][-1]

        if original_image_type in self.image_types_extensions:
            return original_image_type

        # for unsupported types it will be png
        return self.image_type_fallback
