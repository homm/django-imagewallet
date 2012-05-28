# -*- coding: utf-8 -*-

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
