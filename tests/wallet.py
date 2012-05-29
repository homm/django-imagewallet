# -*- coding: utf-8 -*-

import types

from django.test import TestCase
from django.core.files.storage import default_storage

from PIL import Image
from imagewallet.tests.storage import DictStorage
from imagewallet.format import ImageFormat
from imagewallet.wallet import Wallet, HashDirWallet, SingleFormatWallet
from imagewallet.filters import resize


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
        TW = type('TW', (Wallet,), {
            'original': ImageFormat(),
            'small': ImageFormat([
                resize(50, 50)
            ]),
            'storage': DictStorage('/'),
        })
        self.im(66, 44).save(TW.storage.open('file.jpg'), format='JPEG')

        self.assertEqual(unicode(TW('file.jpg')), 'file.jpg')
        self.assertEqual(TW('file.jpg').path_original, 'file.jpg')
        self.assertEqual(TW('file.jpg').url_original, '/file.jpg')
        self.assertEqual(TW('file.jpg').load_original().size, (66, 44))
        self.assertEqual(TW('file.jpg').path_small, 'file_small.jpg')
        self.assertEqual(TW('file.jpg').url_small, '/file_small.jpg')
        self.assertEqual(TW('file.jpg').load_small().size, (50, 33))


        HashDirWallet
        SingleFormatWallet
