# -*- coding: utf-8 -*-

import types
import StringIO

from django.test import TestCase
from django.core.files.storage import default_storage

from PIL import Image
from imagewallet.tests.storage import DictStorage
from imagewallet.format import ImageFormat, OriginalImageFormat
from imagewallet.wallet import SingleFormatWallet
from imagewallet.wallet import Wallet, HashDirWallet


class ImageFormatTest(TestCase):

    def im(self, w=10, h=10, mode='RGB', info={}):
        im = Image.new(mode, (w, h))
        im.info.update(info)
        return im

    def test_construct(self):
        with self.assertRaises(ValueError):
            format = ImageFormat(file_type='GIF')

        format = ImageFormat(mode_rgb=True, modergb=False, jpeg_quality=90)
        self.assertEqual(format._get_options('mode'), {'rgb': True})
        self.assertEqual(format._get_options('mode_'), {'rgb': True})
        self.assertEqual(format._get_options('jpeg'), {'quality': 90})

    def test_get_file_type(self):
        format = ImageFormat()
        self.assertEqual(format.get_file_type('GIF'), 'PNG')
        self.assertEqual(format.get_file_type('PNG'), 'PNG')
        self.assertEqual(format.get_file_type('JPEG'), 'JPEG')

        format = OriginalImageFormat()
        self.assertEqual(format.get_file_type('GIF'), 'GIF')
        self.assertEqual(format.get_file_type('PNG'), 'PNG')
        self.assertEqual(format.get_file_type('JPEG'), 'JPEG')
        self.assertEqual(format.get_file_type('TIFF'), 'TIFF')
        self.assertEqual(format.get_file_type('EPS'), 'EPS')

        format = ImageFormat(decline_file_type='JPEG')
        self.assertEqual(format.get_file_type('GIF'), 'JPEG')
        self.assertEqual(format.get_file_type('PNG'), 'PNG')
        self.assertEqual(format.get_file_type('JPEG'), 'JPEG')

        format = ImageFormat(file_type='PNG')
        self.assertEqual(format.get_file_type('GIF'), 'PNG')
        self.assertEqual(format.get_file_type('PNG'), 'PNG')
        self.assertEqual(format.get_file_type('JPEG'), 'PNG')

        format = ImageFormat(file_type='JPEG')
        self.assertEqual(format.get_file_type('GIF'), 'JPEG')
        self.assertEqual(format.get_file_type('PNG'), 'JPEG')
        self.assertEqual(format.get_file_type('JPEG'), 'JPEG')

    def test_prepare_for_process(self):
        prepare = ImageFormat()._prepare_for_process
        self.assertEqual(prepare(self.im(mode='RGB')).mode, 'RGB')
        self.assertEqual(prepare(self.im(mode='LA')).mode, 'LA')
        self.assertEqual(prepare(self.im(mode='P')).mode, 'P')

        prepare = ImageFormat(mode='RGBA')._prepare_for_process
        self.assertEqual(prepare(self.im(mode='RGB')).mode, 'RGBA')
        self.assertEqual(prepare(self.im(mode='LA')).mode, 'RGBA')
        self.assertEqual(prepare(self.im(mode='P')).mode, 'RGBA')

        prepare = ImageFormat(mode='P', mode_colors=16)._prepare_for_process
        self.assertEqual(prepare(self.im(mode='RGB')).mode, 'P')

        prepare = ImageFormat(mode='P', mode_unknown=666)._prepare_for_process
        with self.assertRaises(TypeError):
            # параметры с префиксом mode_ передаются в фильтр convert.
            prepare(self.im(mode='RGB'))

    def test_process(self):
        format = ImageFormat([
            lambda im, format: im.resize((im.size[0] * 2, im.size[1] * 2)),
            lambda im, format: im.resize((im.size[0] - 10, im.size[1] - 10)),
        ])
        self.assertEqual(format.process(self.im(10, 10)).size, (10, 10))
        self.assertEqual(format.process(self.im(20, 20)).size, (30, 30))
        self.assertEqual(format.process(self.im(mode='L')).mode, 'L')

        format = ImageFormat([
            lambda im, format: im.resize((im.size[0] * 2, im.size[1] * 2)),
            lambda im, format: im.resize((im.size[0] - 10, im.size[1] - 10)),
        ], mode='L')
        self.assertEqual(format.process(self.im(mode='L')).mode, 'L')
        self.assertEqual(format.process(self.im(mode='RGB')).mode, 'L')

    def test_save(self):
        function = ImageFormat()._get_save_params
        self.assertEqual(function(self.im(), 'JPEG'), {})
        self.assertEqual(function(self.im(), 'PNG'), {})
        self.assertEqual(function(self.im(info={'progression': True}), 'JPEG'),
            {'progressive': True})

        opts = {'jpeg_progressive': False, 'png_optimize': True}
        function = ImageFormat(**opts)._get_save_params
        self.assertEqual(function(self.im(), 'JPEG'), {'progressive': False})
        self.assertEqual(function(self.im(), 'PNG'), {'optimize': True})
        self.assertEqual(function(self.im(info={'progression': True}), 'JPEG'),
            {'progressive': False})
        self.assertEqual(function(self.im(info={'transparent': 66}), 'PNG'),
            {'optimize': True})
        self.assertEqual(function(self.im(mode='P', info={'transparency': 66}),
            'PNG'), {'transparency': 66, 'optimize': True})

        function = ImageFormat(**opts)._prepare_for_save
        self.assertEqual(function(self.im(mode='P'), 'JPEG').mode, 'RGB')
        self.assertEqual(function(self.im(mode='RGBA'), 'JPEG').mode, 'RGB')
        self.assertEqual(function(self.im(mode='CMYK'), 'JPEG').mode, 'CMYK')
        self.assertEqual(function(self.im(mode='P'), 'PNG').mode, 'P')
        self.assertEqual(function(self.im(mode='RGBA'), 'PNG').mode, 'RGBA')
        self.assertEqual(function(self.im(mode='CMYK'), 'PNG').mode, 'RGB')

        file = StringIO.StringIO()
        ImageFormat().save(self.im(34, 16, 'P', {'transparency': 66}), file)
        file.seek(0)
        im = Image.open(file)
        self.assertEqual(im.size, (34, 16))
        self.assertEqual(im.mode, 'P')
        self.assertEqual(im.format, 'PNG')
        self.assertEqual(im.info, {'transparency': 66})

        file = StringIO.StringIO()
        format = ImageFormat([
            lambda im, format: im.resize((im.size[0] * 2, im.size[1] * 2)),
            lambda im, format: im.resize((im.size[0] - 10, im.size[1] - 10)),
        ], mode='L', file_type='JPEG')
        format.save(format.process(self.im(34, 16, 'P', {'transparency': 66})),
            file)
        file.seek(0)
        im = Image.open(file)
        self.assertEqual(im.size, (58, 22))
        self.assertEqual(im.mode, 'L')
        self.assertEqual(im.format, 'JPEG')


class WalletMetaclassTest(TestCase):

    def im(self, w=10, h=10, mode='RGB', info={}):
        im = Image.new(mode, (w, h))
        im.info.update(info)
        return im

    def test_construct(self):
        TW = type('TW', (Wallet,), {
            'original_storage': DictStorage(),
        })
        self.assertEqual(TW.storage, default_storage)
        self.assertEqual(type(TW.original_storage), DictStorage)

        TW = type('TW', (Wallet,), {
            'storage': DictStorage(),
            'original_storage': DictStorage(),
        })
        self.assertEqual(type(TW.storage), DictStorage)
        self.assertEqual(type(TW.original_storage), DictStorage)
        self.assertNotEqual(TW.storage, TW.original_storage)

        TW = type('TW', (Wallet,), {
            'original': ImageFormat(),
            'small': ImageFormat(),
            'storage': DictStorage(),
        })
        self.assertEqual(type(TW.storage), DictStorage)
        self.assertEqual(type(TW.original_storage), DictStorage)
        self.assertEqual(TW.storage, TW.original_storage)

        self.assertEqual(type(TW.path_small), property)
        self.assertEqual(type(TW.url_small), property)
        self.assertEqual(type(TW.load_small), types.MethodType)

        with self.assertRaises(AttributeError):
            TW.path_original
        with self.assertRaises(KeyError):
            TW.__dict__['url_original']
        self.assertEqual(TW.load_original, Wallet.load_original)

        TW = type('TW', (SingleFormatWallet,), {
            'format': ImageFormat(),
            'format_name': 'small',
            'storage': DictStorage(),
        })
        self.assertEqual(type(TW.storage), DictStorage)
        self.assertEqual(type(TW.original_storage), DictStorage)
        self.assertEqual(TW.storage, TW.original_storage)


class WalletTest(TestCase):

    def im(self, w=10, h=10, mode='RGB', info={}):
        im = Image.new(mode, (w, h))
        im.info.update(info)
        return im

    def test_construct(self):
#        self.im(66, 22).save(TW.storage.open('file.jpg'), format='JPEG')
#
#        self.assertEqual(TW('file.jpg').path_small, 'file_small.jpg')
#        self.assertEqual(TW('file.jpg').url_small, '/file_small.jpg')
#        self.assertEqual(TW('file.jpg').load_small().size, (66, 22))
        Wallet
        HashDirWallet
