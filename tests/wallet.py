# -*- coding: utf-8 -*-

from django.test import TestCase

from imagewallet.wallet import ImageFormat, WalletMetaclass, Wallet


class ImageFormatTest(TestCase):

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

        format = ImageFormat(file_type='PNG')
        self.assertEqual(format.get_file_type('GIF'), 'PNG')
        self.assertEqual(format.get_file_type('PNG'), 'PNG')
        self.assertEqual(format.get_file_type('JPEG'), 'PNG')

        format = ImageFormat(file_type='JPEG')
        self.assertEqual(format.get_file_type('GIF'), 'JPEG')
        self.assertEqual(format.get_file_type('PNG'), 'JPEG')
        self.assertEqual(format.get_file_type('JPEG'), 'JPEG')

    def test_prepare(self):
        def new(mode):
            return Image.new(mode, (4, 4))
        from PIL import Image

        format = ImageFormat()
        self.assertEqual(format.prepare(new('RGB')).mode, 'RGB')
        self.assertEqual(format.prepare(new('LA')).mode, 'LA')
        self.assertEqual(format.prepare(new('P')).mode, 'P')

        format = ImageFormat(mode='RGBA')
        self.assertEqual(format.prepare(new('RGB')).mode, 'RGBA')
        self.assertEqual(format.prepare(new('LA')).mode, 'RGBA')
        self.assertEqual(format.prepare(new('P')).mode, 'RGBA')

        format = ImageFormat(mode='RgBa')
        self.assertEqual(format.prepare(new('RGB')).mode, 'RGBA')
        self.assertEqual(format.prepare(new('LA')).mode, 'RGBA')
        self.assertEqual(format.prepare(new('P')).mode, 'RGBA')

        # Картинка с альфаканалом для теста.
        # Первый ряд полностью прозрачный, последний нет.
        r3 = range(3)
        sample = new('LA')
        sample.putpixel((0, 0), (0, 0))
        sample.putpixel((1, 0), (127, 0))
        sample.putpixel((2, 0), (255, 0))
        sample.putpixel((0, 1), (0, 127))
        sample.putpixel((1, 1), (127, 127))
        sample.putpixel((2, 1), (255, 127))
        sample.putpixel((0, 2), (0, 255))
        sample.putpixel((1, 2), (127, 255))
        sample.putpixel((2, 2), (255, 255))

        # При преобразовании RGBA не должны меняться пиксели
        im = ImageFormat(mode='RGBA').prepare(sample)
        self.assertEqual([im.getpixel((i, 0)) for i in r3],
            [(0, 0, 0, 0), (127, 127, 127, 0), (255, 255, 255, 0)])
        self.assertEqual([im.getpixel((i, 1)) for i in r3],
            [(0, 0, 0, 127), (127, 127, 127, 127), (255, 255, 255, 127)])
        self.assertEqual([im.getpixel((i, 2)) for i in r3],
            [(0, 0, 0, 255), (127, 127, 127, 255), (255, 255, 255, 255)])

        # При преобразовании в RGB должно накладываться на белый фон
        im = ImageFormat(mode='RGB').prepare(sample)
        self.assertEqual([im.getpixel((i, 0)) for i in r3],
            [(255, 255, 255), (255, 255, 255), (255, 255, 255)])
        self.assertEqual([im.getpixel((i, 1)) for i in r3],
            [(128, 128, 128), (191, 191, 191), (255, 255, 255)])
        self.assertEqual([im.getpixel((i, 2)) for i in r3],
            [(0, 0, 0), (127, 127, 127), (255, 255, 255)])

        # При преобразовании в RGB должно накладываться на синий
        im = ImageFormat(mode='RGB', background='blue').prepare(sample)
        self.assertEqual([im.getpixel((i, 0)) for i in r3],
            [(0, 0, 255), (0, 0, 255), (0, 0, 255)])
        self.assertEqual([im.getpixel((i, 1)) for i in r3],
            [(0, 0, 128), (63, 63, 191), (127, 127, 255)])
        self.assertEqual([im.getpixel((i, 2)) for i in r3],
            [(0, 0, 0), (127, 127, 127), (255, 255, 255)])

        def palette_color(image, pixel):
            entry = image.getpixel(pixel)
            p = image.getpalette()
            return p[entry * 3], p[entry * 3 + 1], p[entry * 3 + 2]

        # При преобразовании в P по-умолчанию используется палитра WEB
        im = ImageFormat(mode='P', background='blue').prepare(sample)
        self.assertEqual([palette_color(im, (i, 0)) for i in r3],
            [(0, 0, 255), (0, 0, 255), (0, 0, 255)])
        self.assertEqual([palette_color(im, (i, 1)) for i in r3],
            [(0, 0, 153), (51, 51, 204), (153, 153, 255)])
        self.assertEqual([palette_color(im, (i, 2)) for i in r3],
            [(0, 0, 0), (102, 102, 102), (255, 255, 255)])

        # При преобразовании в P используем более точную палитру.
        im = ImageFormat(mode='P', mode_palette=Image.ADAPTIVE,
            background='blue').prepare(sample)
        self.assertEqual([palette_color(im, (i, 0)) for i in r3],
            [(0, 0, 255), (0, 0, 255), (0, 0, 255)])
        self.assertEqual([palette_color(im, (i, 1)) for i in r3],
            [(0, 0, 128), (63, 63, 191), (127, 127, 255)])
        self.assertEqual([palette_color(im, (i, 2)) for i in r3],
            [(0, 0, 0), (127, 127, 127), (255, 255, 255)])

        # Картинка с палитрой, где 3-й элемент прозрачный.
        sample = new('P')
        for i in range(4):
            sample.putpixel((i, 0), i)
        p = sample.getpalette()
        p[0:9] = [10, 20, 30, 115, 117, 127, 255, 255, 255]
        sample.putpalette(p)
        sample.info['transparency'] = 3

        im = ImageFormat(mode='RGB', background='blue').prepare(sample)
        self.assertEqual([im.getpixel((i, 0)) for i in range(4)],
            [(10, 20, 30), (115, 117, 127), (255, 255, 255), (0, 0, 255)])

        im = ImageFormat(mode='P', background='blue').prepare(sample)
        self.assertEqual([palette_color(im, (i, 0)) for i in range(4)],
            [(10, 20, 30), (115, 117, 127), (255, 255, 255), (0, 0, 255)])

    def test_process(self):
        pass

    def test_save(self):
        # _prepare_for_save
        # _get_save_params
        # save
        pass


class WalletMetaclassTest(TestCase):
    def test_construct(self):
        WalletMetaclass


class WalletTest(TestCase):
    def test_construct(self):
        Wallet
