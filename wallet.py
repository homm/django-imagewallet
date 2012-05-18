# -*- coding: utf-8 -*-

import hashlib

from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.utils.functional import cached_property

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
        # Преобразования не требуется
        if self.mode is None or self.mode == image.mode:
            return image

        # Если режим, к которому нужно преобразовать, не поддерживает
        # прозрачность, а исходное изображение в одном из режимов,
        # поддерживающих, нужны подложить под прозрачные пиксели фон.
        # Причем, режим с палитрой считается неподдерживающим прозрачность,
        # потому что адекватно преобразовать в него альфаканал все равно не
        # получится.
        if self.mode not in ('RGBA', 'LA'):
            # Черно-белые с альфаканалом преобразуем в RGBA. Можно было бы
            # заморочиться с извлечением L и А и передачей их в paste отдельно,
            # что сократило бы потребление памяти.
            if image.mode == 'LA':
                # Конвертируем без опций, для RGBA они не применимы.
                image = image.convert('RGBA')

            # Тут нет else. Предыдущий случай тоже обрабатывается здесь.
            if image.mode == 'RGBA':
                # Картинка - подложка, состоящая из залитого фона.
                bg = PIL.Image.new('RGB', image.size, self.background)
                # Вставляем изображение. paste вставляет пикселы первого
                # аргумента с помошью альфаканала третьего.
                # Альфаканал первого игнорируется.
                bg.paste(image, None, image)
                # Теперь bg и есть искомое изображение.
                image = bg

            # Палитру не нужно смешивать, достаточно заменить цвет, указанный
            # как прозрачный на цвет фона.
            elif image.mode == 'P' and 'transparency' in image.info:
                # Будем менять палитру, картинку портить нельзя.
                image = image.copy()
                color = PIL.ImageColor.getrgb(self.background)
                palette = image.getpalette()
                # Тут предполагается, что палитра в формате RGB.
                offset = image.info['transparency'] * 3
                palette[offset:offset + 3] = color
                # Кладем на место.
                image.putpalette(palette)

        # С палитрой бида. Если преобразовывать из нее в формат, поддерживающий
        # прозрачность, прозрачный цвет палитры становится непрозрачным.
        elif image.mode == 'P' and 'transparency' in image.info:
            # Из прозрачного цвета нужно получить маску.
            mask = image.convert('L').point(lambda i:
                0 if i == image.info['transparency'] else 255)
            # Конвертируем без опций, для RGBA они не применимы.
            image = image.convert('RGBA')
            image.putalpha(mask)

        # Теперь можно конвертировать.
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
        # Индекс прозрачного цвета в палитре должен выставляться вручную.
        if image.mode == 'P' and 'transparency' in image.info:
            save_params.setdefault('transparency', image.info['transparency'])
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
            # TODO:: А тут разве не нужно игнорировать original?
            # Если находим среди них ImageFormat.
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

    file_path_prefix = 'walletcache/'

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
    def file_type_original(self):
        """
        Возвращает тип оригинального файла на основе его имени.
        """
        ext = self.path_original[-4:].lower()
        if ext == '.png':
            return 'PNG'
        if ext == '.jpg' or ext == 'jpeg':
            return 'JPEG'
        # Остальное не интересует.
        return None

    @cached_property
    def _hash_original(self):
        # Работает достаточно быстро: 660к генераций в секунду.
        # Это даже не сильно медленнее "%x" % hash().
        return hashlib.md5(self.path_original).hexdigest()

    def load_original(self):
        """
        Загружает экземпляр оригинального изображения.
        """
        # Предыдущая реализация кешировала оригинальное изображение,
        # на случай, если придется обрабатывать обработать несколько форматов.
        # На самом деле открытие изображения довольно быстрая операция
        # по сравнению с остальным, а память при обработке в цикле течет.
        file = self.original_storage.open(self.path_original)
        original = PIL.Image.open(file)
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
        original.format = self.file_type_original
        return original

    def _get_path(self, name, format):
        """
        Возвращает путь до файла в сторадже для заданного формата.
        Используется через проперти path_<name>.
        """
        file_type = format.get_file_type(self.file_type_original)
        # Можно кастомизировать префикс.
        return (self.file_path_prefix + self._hash_original + '_' +
            # Расширение — первый элемент в описании типа файла.
            name + '.' + format.file_types[file_type][0])

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
