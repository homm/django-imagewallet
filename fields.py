# -*- coding: utf-8 -*-

import os
import random
from datetime import datetime

from django.core.files import File
from django.db.models.fields.files import FileField
from django.utils.encoding import force_unicode

import PIL
from imagewallet.wallet import Wallet, ORIGINAL_FORMAT


class WalletDescriptor(object):
    """
    Дескриптор, назначаемый модели, чтобы управлять присвиваниями получениями
    поля. Не несет смысловой нагрузки как отдельный класс, более правильно
    было бы сделать дескриптором WalletField, но тогда он может начать вести
    себя как дескриптор там, где нужно просто доступ к полю.
    """
    def __init__(self, field):
        self.field = field
        self.field_name = field.name
        self.attr_class = field.attr_class

    def __get__(self, instance=None, owner=None):
        if instance is None:
            raise AttributeError(
                "The '%s' attribute can only be accessed from %s instances."
                % (self.field_name, owner.__name__))

        # В value может быть черти что. Давайте гадать.
        value = instance.__dict__[self.field_name]

        # Может быть это None или само хранилище? Его и возвращаем.
        if value is None or isinstance(value, self.attr_class):
            return value

        # Может строка? Значит она пришла из базы, потому что присвивание
        # хранилищу строки по другим причинам не поддерживается.
        elif isinstance(value, basestring):
            try:
                pattern, format = value.rsplit(';', 1)
            except ValueError:
                # Это какое-то испорченное значение.
                value = None
            else:
                # Здесь захардкожены шоткаты хранения в базе самый популярных
                # форматов.
                if format == 'J':
                    format = 'JPEG'
                elif format == 'P':
                    format = 'PNG'
                value = self.attr_class(pattern, format)

        # Значит это пользователь хочет сохранить картинку.
        # Или даже загрузил файл. Джанговский или обычный.
        elif isinstance(value, (File, file, PIL.Image.Image)):
            if isinstance(value, (File, file)):
                filename = value.name or 'generated_file'
                # конвертируем в картинку
                value = PIL.Image.open(value)
            else:
                # Если картинка открыта с диска, у нее будет filename
                filename = getattr(value, 'filename', None) or 'generated'
            file_pattern = self.field.generate_filename(instance, filename)
            # Специальный конструктор создания изображения
            value = self.attr_class.object_from_image(value, file_pattern)

        else:
            raise TypeError("Unknown type %s for converting to Wallet" %
                type(value))

        # Полученное значение сохраняем
        instance.__dict__[self.field_name] = value
        return value

    def __set__(self, instance, value):
        # В большинстве случаев тип присваимого значения обрабатывается
        # при его извлечении (__get__). Но для хранилищ проверяется
        # совместимость при присвоении. Во-первых это дает очень быстро
        # вытаскивать хранилища из моделей. Во-вторых, это дает уверенность,
        # что уж если в модели хранилище, то это хранилище верного типа.
        if isinstance(value, Wallet) and type(value) != self.attr_class:
            # Новый патерн понадобится в любом случае.
            file_pattern = self.field.generate_filename(instance,
                value.path_original())
            # Это формат, в который нужно перевести
            format = self.attr_class.original
            # Сначала пытаемя перенести изображение без пережатия. Конечно,
            # на него не будут наложены фильтры оригинального формата,
            # но оригинальный формат затем и нужен, чтобы хранить изображение,
            # подвергшееся минимальным искажениям.
            # Выясняем тип, в который будет преобразован оргинал.
            file_type = format.get_file_type(value.original_file_type)
            # Если тип тот же, что оригинальный, можно скопировать файл.
            if file_type == value.original_file_type:
                # Открываем файл в чужем сторадже.
                file = value.original_storage.open(value.path_original)
                # Расширение — первый элемент в описании типа файла.
                extension = format.file_types[file_type][0]
                file_name = file_pattern.format(f=ORIGINAL_FORMAT, e=extension)
                # Копируем файл.
                self.attr_class.original_storage.save(file_name, file)

                # Файл скопирован, создаем новое хранилище с известным патерном
                # и форматом оригинального изображения.
                value = self.attr_class(file_pattern, file_type)
            else:
                # Скопирвоать не удастся, будем пересохранять.
                image = value.load_original()
                value = self.attr_class.object_from_image(image, file_pattern)
        # Если же присвивается хранилище такого же типа, вроде ничего страшного
        # не произойдет. В базе будет два указателя на один файл, или не будет,
        # если поле уникальное. Или instance может быть совсем другой модели.
        instance.__dict__[self.field_name] = value


class WalletField(FileField):
    """
    Поле для хранения в базе данных сведений о хранилищах картинок.
    Наследование от FileField имеет смысл, потому что такие поля сохраняются
    в последнюю очередь.
    Attr_class создается динамически для каждого экземпляра поля со своим
    набором форматов и других опций.
    """
    attr_class = None
    attr_class_bases = (Wallet,)
    descriptor_class = WalletDescriptor

    # 12 случайных символов из 36 примерно соответствует 2 ** 62 вариантов
    random_sings = 12
    random_chars = 'abcdefghijklmnopqrstuvwxyz0123456789'

    def __init__(self, verbose_name=None, name=None, upload_to='',
            storage=None, original_storage=None, formats={}, **kwargs):
        """
        Upload_to — строка или функция, которая должна возвращать полное имя
            файла с заменами {f} и {e}. Вызывается с тремя аргументами: поле,
            объект модели, в которую будет сохранен файл и имя оригинального
            файла. Если строка, то обозначает только директоррию. Все вхождения
            строки '%r' заменяются на случайный символ, дальше строка
            передается в метод strftime текущего времени. Также может содержать
            замены {f} и {e}. Имя файла будет сгенерированно случайно.
        Storage и original_storage — передаются в класс модели. На самом деле
            их можно передавать через formats, но так делать не рекомендуется.
        Formats — словарь с форматами, которые будут доступны для закачанных
            картинок.
        """
        # Пустое значение не несет смысла и всегда равно null.
        # Обратная проверка тоже была бы полезна, но south при накатывании
        # миграций создает поле игнорируя параметр blank.
        if kwargs.get('blank', False) and not kwargs.get('null', False):
            raise TypeError('Blank fields should take null values.')

        # Значение по-умолчанию тоже null.
        kwargs['default'] = None

        # Необходимо извлечь из параметров unique, потому что FileField
        # не может быть уникальным, а WalletField может.
        unique = kwargs.pop('unique', False)
        super(WalletField, self).__init__(verbose_name, name, upload_to,
            **kwargs)
        # Восстанавливаем значение.
        self._unique = unique

        # Клонируем на всякий случай, потому что будем изменять
        formats = dict(formats)
        if storage is not None:
            formats['storage'] = storage
            # Если задан просто storage, то принимаем его за сторадж всего.
            # Далее, если задан original_storage, он заменит просто storage.
            formats['original_storage'] = storage
        if original_storage is not None:
            formats['original_storage'] = original_storage
        # Создаем новый тип хранилищ изображений.
        self.attr_class = type('FieldWallet', self.attr_class_bases, formats)

    def pre_save(self, instance, add):
        """
        Метод, извлекающий значение данного поля из экземпляра модели.
        """
        # Если всегда честно выполнять getattr, то при сохранении объекта,
        # в котором есть хранилище изображений, но к которому не обращались,
        # будет происходить это самое обращение, а знаит загрузка.
        # Поэтому пропускам как есть строки и None.
        value = instance.__dict__[self.name]
        if value is None or isinstance(value, basestring):
            return value
        return getattr(instance, self.attname)

    def get_prep_value(self, value):
        """
        Конвертирует текущее содержимое поля у модели в формат, пригодный для
        сохранения в базе данных.
        """
        # Вдруг будет нужно сохранить хранилище как раз того типа, что это поле
        # производит (како сюрприз). Может показаться, что нужно проверять на
        # инстанс самого Wallet. Но два хранилища разных типов даже
        # с одинаковыми патернами, строго говоря, нельзя считать одинаковыми.
        if type(value) == self.attr_class:
            file_type = value.original_file_type
            # Если возможно, сохраняем шоткатами.
            file_type = {'JPEG': 'J', 'PNG': 'P'}.get(file_type, file_type)
            return '{0};{1}'.format(value.file_pattern, file_type)
        return value

    def get_directory_name(self):
        dir = force_unicode(self.upload_to)
        while '%r' in dir:
            dir = dir.replace('%r', random.choice(self.random_chars), 1)
        return os.path.normpath(datetime.now().strftime(dir))

    def get_random_filename(self):
        hash = "".join(random.choice(self.random_chars)
            for _ in range(self.random_sings))
        return hash + '_{f}.{e}'

    def generate_filename(self, instance, filename):
        """
        Возвращает гарантированно не занятое имя файла в сторадже оригиналов.
        """
        dir = self.get_directory_name()
        storage = self.attr_class.original_storage
        while True:
            file_pattern = os.path.join(dir, self.get_random_filename())
            # Проверяем, что файлов с расширением среди поддерживаемых
            # оригинальным форматом расширений, нет.
            for info in self.attr_class.original.file_types.itervalues():
                # Расширение — первый элемент информации о файле.
                file_name = file_pattern.format(f=ORIGINAL_FORMAT, e=info[0])
                if storage.exists(file_name):
                    break
            else:
                # Если не было прервано, можно использовать этот паттерн.
                return file_pattern

    def south_field_triple(self):
        "Returns a suitable description of this field for South."
        # We'll just introspect the _actual_ field.
        from south.modelsinspector import introspector
        field_class = self.__class__.__module__ + "." + self.__class__.__name__
        args, kwargs = introspector(self)
        # That's our definition!
        return (field_class, args, kwargs)
