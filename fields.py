# -*- coding: utf-8 -*-

import os
import random
from datetime import datetime

from django.db.models.fields.files import FileField
from django.core.files import File
from django.utils.encoding import force_unicode, smart_str

from imagewallet import Wallet
from imagewallet.wallet import ImageFormat, ORIGINAL_FORMAT


class NewWalletDescriptor(object):
    """
    Дескриптор, назначаемый модели, чтобы управлять присвиваниями получениями
    поля. Не несет смысловой нагрузки как отдельный класс, более правильно
    было бы сделать дескриптором WalletField, но тогда он может начать вести
    себя как дескриптор там, где нужно просто доступ к полю.
    """
    def __init__(self, field):
        self.field = field
        self.field_name = field.name

    def __get__(self, instance=None, owner=None):
        return instance.__dict__[self.field_name]

    def __set__(self, instance, value):
        instance.__dict__[self.field_name] = value


class NewWalletField(FileField):
    """
    Поле для хранения в базе данных сведений о хранилищах картинок.
    Наследование от FileField имеет смысл, потому что такие поля сохраняются
    в последнюю очередь.
    Attr_class создается динамически для каждого экземпляра поля со своим
    набором форматов и других опций.
    """
    attr_class = None
    attr_class_bases = (Wallet,)
    descriptor_class = NewWalletDescriptor

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

        # Необходимо извлеч из параметров unique, потому что FileField не может
        # быть уникальным, а WalletField может.
        unique = kwargs.pop('unique', False)
        super = super(NewWalletField, self)
        super.__init__(verbose_name, name, upload_to, **kwargs)
        # Восстанавливаем значение.
        self._unique = unique

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


class FieldWallet(Wallet):
    def __init__(self, instance, field, *args, **kwargs):
        super(FieldWallet, self).__init__(field.formats, storage=field.storage,
            *args, **kwargs)
        self.instance = instance
        self.field = field

    def save(self, image, save=True):
        super(FieldWallet, self).save(image)
        if self.field.process_all_formats:
            self.process_all_formats()
        if save:
            self.instance.save()
    save.alters_data = True

    def copy(self, wallet):
        if self:
            raise ValueError("Can not save another images in saved wallet. Delete first.")
        if not wallet:
            return
        self.pattern = self.field.generate_filename(self.instance,
            wallet.get_path(ORIGINAL_FORMAT))
        super(FieldWallet, self).copy(wallet)

    def delete(self, save=True):
        super(FieldWallet, self).delete()
        if save:
            self.instance.save()
    delete.alters_data = True


class WalletDescriptor(object):
    def __init__(self, field):
        self.field = field

    def __get__(self, instance=None, owner=None):
        field = self.field
        wallet = value = instance.__dict__[field.name]
        # In most cases strings and Nones comes from database
        if isinstance(value, basestring) or value is None:
            pattern = None
            format = None
            if value:
                try:
                    pattern, format = value.rsplit(';', 1)
                except ValueError:
                    pass
            wallet = field.attr_class(instance, field, pattern, format)
            instance.__dict__[field.name] = wallet
        # value uploaded from form
        elif isinstance(value, File):
            wallet = field.attr_class(instance, field)
            # code moved from wallet.save
            if wallet:
                wallet.delete(save=False)
            wallet.pattern = field.generate_filename(instance, value.name)
            wallet.save(value, save=False)
            instance.__dict__[field.name] = wallet
        # copy image from foreign wallets
        elif isinstance(value, Wallet) and (
                not isinstance(value, field.attr_class)
                or value.instance != instance
                or value.field != field):
            wallet = field.attr_class(instance, field)
            wallet.copy(value)
            instance.__dict__[field.name] = wallet
        return wallet

    def __set__(self, instance, value):
        instance.__dict__[self.field.name] = value

    def __delete__(self, instance):
        return self.__set__(instance, None)


original_image_format = ImageFormat(jpeg_quality=95)


class WalletField(FileField):
    attr_class = FieldWallet
    descriptor_class = WalletDescriptor
    random_chars = 'abcdefghijklmnopqrstuvwxyz0123456789'
    random_sings = 12

    def __init__(self, verbose_name=None, name=None, upload_to='', storage=None,
            formats={}, process_all_formats=False, **kwargs):
        kwargs.setdefault('max_length', 255)
        unique = kwargs.pop('unique', False)
        # set upload_to to empty string to prevent wrong handle
        super(WalletField, self).__init__(verbose_name, name, '', storage, **kwargs)
        # unlike file fields, wallet fields can be unique
        self._unique = unique
        self.upload_to = upload_to
        if callable(upload_to):
            self.get_directory_name = upload_to

        self.formats = {
            ORIGINAL_FORMAT: original_image_format,
        }
        self.formats.update(formats)
        self.process_all_formats = process_all_formats
        self.attr_class.populate_formats(self.formats.keys())

    def pre_save(self, model_instance, add):
        value = model_instance.__dict__[self.name]
        if value is None or isinstance(value, basestring):
            # instance.__dict__ may contain string and null if no one access
            # to field since object loading from database
            return value
        # in other cases it can be anything
        return getattr(model_instance, self.attname)

    def get_prep_value(self, value):
        if value is None:
            return None
        value = unicode(value)
        if not value and self.null:
            # auto-convert empty wallets to null for null fields
            return None
        return value

    def get_directory_name(self, instance):
        upload_to = smart_str(self.upload_to)
        while '%r' in upload_to:
            r = random.choice(self.random_chars)
            upload_to = upload_to.replace('%r', r, 1)
        return os.path.normpath(force_unicode(datetime.now()
            .strftime(upload_to)))

    def get_filename(self, filename):
        " Generated name MUST contain %(size)s and %(extension)s replaces "
        hash = "".join([random.choice(self.random_chars)
            for _ in xrange(self.random_sings)])
        return hash + u'_%(size)s.%(extension)s'

    def generate_filename(self, instance, filename):
        """
        generate_filename for wallet is more intelligent then for files.
        """
        dir = self.get_directory_name(instance)
        filename = os.path.basename(filename or '')
        while True:
            file = os.path.join(dir, self.get_filename(filename))
            # it is stupid, to check all extensions, but I can't find better way
            candidates = [file % {'size': ORIGINAL_FORMAT, 'extension': extension} 
                for extension in self.attr_class.image_types_extensions.values()]
            if not any((self.storage.exists(candidate) for candidate in candidates)):
                break
        return file

    def delete_file(self, instance, sender, **kwargs):
        # connected to post_delete signal
        # do nothing
        pass

    def south_field_triple(self):
        "Returns a suitable description of this field for South."
        # We'll just introspect the _actual_ field.
        from south.modelsinspector import introspector
        field_class = self.__class__.__module__ + "." + self.__class__.__name__
        args, kwargs = introspector(self)
        # That's our definition!
        return (field_class, args, kwargs)
