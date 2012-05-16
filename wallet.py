# -*- coding: utf-8 -*-

from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

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
        if not prefix.endswith('_'):
            prefix = prefix + '_'
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
        return image.convert(self.mode, **self._get_options('mode'))

    def process(self, image):
        """
        Делает основную работу. Подготавливает изображение, применяет фильтры.
        """
        image = self.prepare(image)

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
            return self.failback_file_type
        return self.file_type

    def _get_save_params(self, image, file_type):
        # Опции для сохранения берутся из изображения и self.options
        save_params = self._get_options(file_type.lower())
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

        # т.к. файл уже сохранен в этом формате, присвиваем ему его.
        image.format = file_type
        return image


class WalletMetaclass(type):
    def __new__(cls, name, bases, attrs):
        super_new = super(WalletMetaclass, cls).__new__
        parents = [b for b in bases if isinstance(b, WalletMetaclass)]
        if not parents:
            # If this isn't a subclass of Model, don't do anything special.
            return super_new(cls, name, bases, attrs)

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
            if not isinstance(format, ImageFormat):
                continue
            # Если находим среди них ImageFormat
            attrs.update(make_properties(format_name, format))
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

        # Сохраняем файл по тому же пути, чтобы не создавать иерархию папок.
        storage.save(file_path, ContentFile(''))
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

    def __repr__(self, *args, **kwargs):
        return u"<%s '%s' %s at %s>" % (type(self).__name__,
            self.file_pattern, self.original_file_type, id(self))

    @property
    def path_original(self):
        """
        Возвращает путь до файла в сторадже для оргинального изображения.
        """
        # Расширение — первый элемент в описании типа файла.
        extension = self.original.file_types[self.original_file_type][0]
        return self.file_pattern.format(f=ORIGINAL_FORMAT, e=extension)

    @property
    def url_original(self):
        """
        Возаврщает url до оргинального изображения.
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
        функцию load_<name>.
        """
        file_path = self._get_path(name, format)
        storage = self.storage
        if storage.exists(file_path):
            return PIL.Image.open(storage.open(file_path))
        return self._save_format(format, self.load_original(),
            storage, file_path)
