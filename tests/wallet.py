# -*- coding: utf-8 -*-

from django.test import TestCase

from PIL import Image
from imagewallet.wallet import ImageFormat, WalletMetaclass, Wallet


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

        format = ImageFormat(file_type='PNG')
        self.assertEqual(format.get_file_type('GIF'), 'PNG')
        self.assertEqual(format.get_file_type('PNG'), 'PNG')
        self.assertEqual(format.get_file_type('JPEG'), 'PNG')

        format = ImageFormat(file_type='JPEG')
        self.assertEqual(format.get_file_type('GIF'), 'JPEG')
        self.assertEqual(format.get_file_type('PNG'), 'JPEG')
        self.assertEqual(format.get_file_type('JPEG'), 'JPEG')

    def test_prepare(self):
        def palette_color(image, pixel):
            entry = image.getpixel(pixel)
            p = image.getpalette()
            return p[entry * 3], p[entry * 3 + 1], p[entry * 3 + 2]

        format = ImageFormat()
        self.assertEqual(format.prepare(self.im(mode='RGB')).mode, 'RGB')
        self.assertEqual(format.prepare(self.im(mode='LA')).mode, 'LA')
        self.assertEqual(format.prepare(self.im(mode='P')).mode, 'P')

        format = ImageFormat(mode='RGBA')
        self.assertEqual(format.prepare(self.im(mode='RGB')).mode, 'RGBA')
        self.assertEqual(format.prepare(self.im(mode='LA')).mode, 'RGBA')
        self.assertEqual(format.prepare(self.im(mode='P')).mode, 'RGBA')

        format = ImageFormat(mode='RgBa')
        self.assertEqual(format.prepare(self.im(mode='RGB')).mode, 'RGBA')
        self.assertEqual(format.prepare(self.im(mode='LA')).mode, 'RGBA')
        self.assertEqual(format.prepare(self.im(mode='P')).mode, 'RGBA')

        format = ImageFormat(mode='P', mode_colors=16)
        self.assertEqual(format.prepare(self.im(mode='RGB')).mode, 'P')

        with self.assertRaises(TypeError):
            # параметры с префиксом mode_ передаются в image.convert.
            format = ImageFormat(mode='P', mode_unknown=666)
            format.prepare(self.im(mode='RGB'))

        # Картинка с альфаканалом для теста.
        # Первый ряд полностью прозрачный, последний нет.
        r3 = range(3)
        sample = self.im(mode='LA')
        sample.putpixel((0, 0), (0, 0))
        sample.putpixel((1, 0), (127, 0))
        sample.putpixel((2, 0), (255, 0))
        sample.putpixel((0, 1), (0, 127))
        sample.putpixel((1, 1), (127, 127))
        sample.putpixel((2, 1), (255, 127))
        sample.putpixel((0, 2), (0, 255))
        sample.putpixel((1, 2), (127, 255))
        sample.putpixel((2, 2), (255, 255))

        # Полупрозрачная RGBA
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
        sample = self.im(mode='P')
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
            [(10, 20, 30), (115, 117, 127), (255, 255, 255), (3, 3, 3)])

        im = ImageFormat(mode='RGBA', background='blue').prepare(sample)
        self.assertEqual([im.getpixel((i, 0)) for i in range(4)],
            [(10, 20, 30, 255), (115, 117, 127, 255), (255, 255, 255, 255),
                (3, 3, 3, 0)])

        # Тут должен был быть тест на преобразование изображений с палитрой
        # и полупрозрачностью в RGB, но PIL игнорирует альфу в 8-битных PNG.

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

        # _prepare_for_save
        # save


class WalletMetaclassTest(TestCase):
    def test_construct(self):
        WalletMetaclass


class WalletTest(TestCase):
    def test_construct(self):
        Wallet
