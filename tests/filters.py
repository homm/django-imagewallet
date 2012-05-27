# -*- coding: utf-8 -*-

from django.test import TestCase

from imagewallet.wallet import ImageFormat
from imagewallet.filter_tools import size_handler
from imagewallet.filters import resize_methods, resize, convert

from PIL import Image


class ToolsTest(TestCase):

    def test_size_handler(self):
        # Значение не задано
        self.assertEqual(size_handler(None)(30), None)
        self.assertEqual(size_handler(None)(-100), None)

        # Значение простое число
        self.assertEqual(size_handler(200)(30), 200)
        self.assertEqual(size_handler(200)(-100), 200)

        # Значение — строка с числом
        self.assertEqual(size_handler('200')(30), 200)
        self.assertEqual(size_handler('200')(-100), 200)
        self.assertEqual(size_handler('+200')(30), 200)
        self.assertEqual(size_handler('+200')(-100), 200)
        self.assertEqual(size_handler('-200')(30), -200)
        self.assertEqual(size_handler('-200')(-100), -200)

        # Значение в пкселях
        with self.assertRaises(ValueError):
            # указание с пикселями без знака не подходит
            size_handler('200px')
        self.assertEqual(size_handler('+0px')(30), 30)
        self.assertEqual(size_handler('-0px')(-100), -100)
        self.assertEqual(size_handler('+200px')(30), 230)
        self.assertEqual(size_handler('+200px')(-100), 100)
        self.assertEqual(size_handler('-200px')(30), -170)
        self.assertEqual(size_handler('-200px')(-100), -300)

        # в процентах
        self.assertEqual(size_handler('10%')(30), 3)
        self.assertEqual(size_handler('10%')(-100), -10)
        self.assertEqual(size_handler('200%')(30), 60)
        self.assertEqual(size_handler('200%')(-100), -200)
        self.assertEqual(size_handler('66.6%')(30), 20)
        self.assertEqual(size_handler('66.6%')(-90), -60)

        # ± проценты
        self.assertEqual(size_handler('+0%')(30), 30)
        self.assertEqual(size_handler('-0%')(-100), -100)
        self.assertEqual(size_handler('+10%')(30), 33)
        self.assertEqual(size_handler('+10%')(-100), -110)
        self.assertEqual(size_handler('-10%')(30), 27)
        self.assertEqual(size_handler('-10%')(-100), -90)
        self.assertEqual(size_handler('+200%')(30), 90)
        self.assertEqual(size_handler('+200%')(-100), -300)
        self.assertEqual(size_handler('-200%')(30), -30)
        self.assertEqual(size_handler('-200%')(-100), 100)
        self.assertEqual(size_handler('+66.6%')(30), 50)
        self.assertEqual(size_handler('+66.6%')(-90), -150)
        self.assertEqual(size_handler('-66.6%')(30), 10)
        self.assertEqual(size_handler('-66.6%')(-90), -30)


class ResizeTest(TestCase):

    def test_resize_method_exactly(self):
        method = resize_methods['exactly']
        self.assertEqual(method(None, None, 300, 200), (300, 200))
        self.assertEqual(method(None, 120, 300, 200), (300, 120))
        self.assertEqual(method(120, None, 300, 200), (120, 200))
        self.assertEqual(method(160, 120, 300, 200), (160, 120))
        self.assertEqual(method(120, 160, 300, 200), (120, 160))

    def test_resize_method_not_more(self):
        method = resize_methods['not_more']

        # Без указания размеров
        self.assertEqual(method(None, None, 500, 300), (500, 300))

        # Задан только width
        self.assertEqual(method(300, None, 200, 300), (300, 450))
        self.assertEqual(method(300, None, 300, 300), (300, 300))
        self.assertEqual(method(300, None, 400, 300), (300, 225))

        # Задан только height
        self.assertEqual(method(None, 300, 300, 200), (450, 300))
        self.assertEqual(method(None, 300, 300, 300), (300, 300))
        self.assertEqual(method(None, 300, 300, 400), (225, 300))

        # Фиксируем нужный размер, пробуем разные фотки.
        # Первая серия на уменьшение
        # Вторая не меняет размер хотя бы одного параметра
        # Третья на увеличение
        # В серии:
        #     Первая фотка более горизонтальная
        #     Вторая пропорции совпадают
        #     Третья более вертикальная

        # Сначала горизонтальный формат
        self.assertEqual(method(300, 200, 500, 300), (300, 180))
        self.assertEqual(method(300, 200, 450, 300), (300, 200))
        self.assertEqual(method(300, 200, 400, 300), (267, 200))

        self.assertEqual(method(300, 200, 300, 166), (300, 166))
        self.assertEqual(method(300, 200, 300, 200), (300, 200))
        self.assertEqual(method(300, 200, 233, 200), (233, 200))

        self.assertEqual(method(300, 200, 180, 100), (300, 167))
        self.assertEqual(method(300, 200, 150, 100), (300, 200))
        self.assertEqual(method(300, 200, 130, 100), (260, 200))

        # Теперь к квадрату
        self.assertEqual(method(300, 300, 410, 400), (300, 293))
        self.assertEqual(method(300, 300, 400, 400), (300, 300))
        self.assertEqual(method(300, 300, 380, 400), (285, 300))

        self.assertEqual(method(300, 300, 300, 280), (300, 280))
        self.assertEqual(method(300, 300, 300, 300), (300, 300))
        self.assertEqual(method(300, 300, 266, 300), (266, 300))

        self.assertEqual(method(300, 300, 210, 200), (300, 286))
        self.assertEqual(method(300, 300, 200, 200), (300, 300))
        self.assertEqual(method(300, 300, 190, 200), (285, 300))

        # И вертикальный формат
        self.assertEqual(method(200, 300, 280, 400), (200, 286))
        self.assertEqual(method(200, 300, 267, 400), (200, 300))
        self.assertEqual(method(200, 300, 260, 400), (195, 300))

        self.assertEqual(method(200, 300, 200, 290), (200, 290))
        self.assertEqual(method(200, 300, 200, 300), (200, 300))
        self.assertEqual(method(200, 300, 190, 300), (190, 300))

        self.assertEqual(method(200, 300, 173, 250), (200, 289))
        self.assertEqual(method(200, 300, 166, 249), (200, 300))
        self.assertEqual(method(200, 300, 162, 250), (194, 300))

    def test_resize_method_not_less(self):
        method = resize_methods['not_less']

        # Без указания размеров
        self.assertEqual(method(None, None, 500, 300), (500, 300))

        # Задан только width
        self.assertEqual(method(300, None, 200, 300), (300, 450))
        self.assertEqual(method(300, None, 300, 300), (300, 300))
        self.assertEqual(method(300, None, 400, 300), (300, 225))

        # Задан только height
        self.assertEqual(method(None, 300, 300, 200), (450, 300))
        self.assertEqual(method(None, 300, 300, 300), (300, 300))
        self.assertEqual(method(None, 300, 300, 400), (225, 300))

        # Фиксируем нужный размер, пробуем разные фотки.
        # Первая серия на уменьшение
        # Вторая не меняет размер хотя бы одного параметра
        # Третья на увеличение
        # В серии:
        #     Первая фотка более горизонтальная
        #     Вторая пропорции совпадают
        #     Третья более вертикальная

        # Сначала горизонтальный формат
        self.assertEqual(method(300, 200, 460, 300), (307, 200))
        self.assertEqual(method(300, 200, 450, 300), (300, 200))
        self.assertEqual(method(300, 200, 440, 300), (300, 205))

        self.assertEqual(method(300, 200, 310, 200), (310, 200))
        self.assertEqual(method(300, 200, 300, 200), (300, 200))
        self.assertEqual(method(300, 200, 300, 220), (300, 220))

        self.assertEqual(method(300, 200, 190, 120), (317, 200))
        self.assertEqual(method(300, 200, 180, 120), (300, 200))
        self.assertEqual(method(300, 200, 170, 120), (300, 212))

        # Теперь к квадрату
        self.assertEqual(method(300, 300, 340, 330), (309, 300))
        self.assertEqual(method(300, 300, 330, 330), (300, 300))
        self.assertEqual(method(300, 300, 320, 330), (300, 309))

        self.assertEqual(method(300, 300, 315, 300), (315, 300))
        self.assertEqual(method(300, 300, 300, 300), (300, 300))
        self.assertEqual(method(300, 300, 300, 315), (300, 315))

        self.assertEqual(method(300, 300, 140, 130), (323, 300))
        self.assertEqual(method(300, 300, 130, 130), (300, 300))
        self.assertEqual(method(300, 300, 120, 130), (300, 325))

        # И вертикальный формат
        self.assertEqual(method(200, 300, 300, 430), (209, 300))
        self.assertEqual(method(200, 300, 286, 429), (200, 300))
        self.assertEqual(method(200, 300, 240, 430), (200, 358))

        self.assertEqual(method(200, 300, 215, 300), (215, 300))
        self.assertEqual(method(200, 300, 200, 300), (200, 300))
        self.assertEqual(method(200, 300, 200, 315), (200, 315))

        self.assertEqual(method(200, 300, 173, 250), (208, 300))
        self.assertEqual(method(200, 300, 166, 249), (200, 300))
        self.assertEqual(method(200, 300, 162, 250), (200, 309))

    def test_resize_method_square(self):
        method = resize_methods['square']

        with self.assertRaises(ValueError):
            method(300, None, 420, 400)

        self.assertEqual(method(300, 300, 420, 400), (307, 293))
        self.assertEqual(method(300, 300, 400, 400), (300, 300))
        self.assertEqual(method(300, 300, 390, 400), (296, 304))

        self.assertEqual(method(300, 300, 300, 300), (300, 300))

        self.assertEqual(method(300, 300, 215, 200), (311, 289))
        self.assertEqual(method(300, 300, 200, 200), (300, 300))
        self.assertEqual(method(300, 300, 195, 200), (296, 304))

    def test_resize(self):
        # Создание и измнение размеров пустых картинок стоит очень дешево.
        f = ImageFormat()

        def img(*args):
            return Image.new('1', args)

        # Всегда должен давать исходный размер
        resizer = resize()
        self.assertEqual(resizer(img(40, 50), f).size, (40, 50))
        self.assertEqual(resizer(img(50, 50), f).size, (50, 50))
        self.assertEqual(resizer(img(60, 50), f).size, (60, 50))

        # Непропорционально уменьшить ширину до 50
        resizer = resize(width=50, method='exactly')
        self.assertEqual(resizer(img(40, 50), f).size, (40, 50))
        self.assertEqual(resizer(img(50, 50), f).size, (50, 50))
        self.assertEqual(resizer(img(60, 50), f).size, (50, 50))

        # Пропорционально уменьшить до ширины 50
        resizer = resize(width=50)
        self.assertEqual(resizer(img(40, 50), f).size, (40, 50))
        self.assertEqual(resizer(img(50, 50), f).size, (50, 50))
        self.assertEqual(resizer(img(60, 50), f).size, (50, 42))

        # Пропорционально уменьшить до высоты 50
        resizer = resize(height=50)
        self.assertEqual(resizer(img(50, 40), f).size, (50, 40))
        self.assertEqual(resizer(img(50, 50), f).size, (50, 50))
        self.assertEqual(resizer(img(50, 60), f).size, (42, 50))

        # Пропорционально изменяет размер до высоты 50
        resizer = resize(height=50, enlarge=True)
        self.assertEqual(resizer(img(51, 40), f).size, (64, 50))
        self.assertEqual(resizer(img(50, 50), f).size, (50, 50))
        self.assertEqual(resizer(img(50, 60), f).size, (42, 50))

        # Пропорционально изменяет размер до высоты 50, другой метод
        resizer = resize(height=50, method='not_less', enlarge=True)
        self.assertEqual(resizer(img(51, 40), f).size, (64, 50))
        self.assertEqual(resizer(img(50, 50), f).size, (50, 50))
        self.assertEqual(resizer(img(50, 60), f).size, (42, 50))

        # Пропорционально уменьшение до 50%
        resizer = resize('66.6%', '50%')
        self.assertEqual(resizer(img(40, 40), f).size, (20, 20))

        # Пропорционально уменьшение до 66.6%
        resizer = resize('66.6%', '50%', method='not_less')
        self.assertEqual(resizer(img(40, 40), f).size, (27, 27))

        # +20% вносит больший вклад и в конце +10px ограничивает больше
        resizer = resize('+10px', '+20%', enlarge=True)
        self.assertEqual(resizer(img(40, 40), f).size, (48, 48))
        self.assertEqual(resizer(img(50, 50), f).size, (60, 60))
        self.assertEqual(resizer(img(60, 60), f).size, (70, 70))

        # +20% вносит больший вклад и в конце +10px ограничивает больше
        resizer = resize('+10px', '+20%', method='not_less', enlarge=True)
        self.assertEqual(resizer(img(40, 40), f).size, (50, 50))
        self.assertEqual(resizer(img(50, 50), f).size, (60, 60))
        self.assertEqual(resizer(img(60, 60), f).size, (72, 72))


class ConvertTest(TestCase):

    def im(self, w=10, h=10, mode='RGB', info={}):
        im = Image.new(mode, (w, h))
        im.info.update(info)
        return im

    def palette_color(self, image, pixel):
        entry = image.getpixel(pixel)
        p = image.getpalette()
        return p[entry * 3], p[entry * 3 + 1], p[entry * 3 + 2]

    def test_convert(self):
        f = ImageFormat()

        converter = convert('RGBA')
        self.assertEqual(converter(self.im(mode='RGB'), f).mode, 'RGBA')
        self.assertEqual(converter(self.im(mode='LA'), f).mode, 'RGBA')
        self.assertEqual(converter(self.im(mode='P'), f).mode, 'RGBA')

        converter = convert('RgBa')
        self.assertEqual(converter(self.im(mode='RGB'), f).mode, 'RGBA')
        self.assertEqual(converter(self.im(mode='LA'), f).mode, 'RGBA')
        self.assertEqual(converter(self.im(mode='P'), f).mode, 'RGBA')

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
        im = convert('RGBA')(sample, f)
        self.assertEqual([im.getpixel((i, 0)) for i in r3],
            [(0, 0, 0, 0), (127, 127, 127, 0), (255, 255, 255, 0)])
        self.assertEqual([im.getpixel((i, 1)) for i in r3],
            [(0, 0, 0, 127), (127, 127, 127, 127), (255, 255, 255, 127)])
        self.assertEqual([im.getpixel((i, 2)) for i in r3],
            [(0, 0, 0, 255), (127, 127, 127, 255), (255, 255, 255, 255)])

        # При преобразовании в RGB должно накладываться на белый фон
        im = convert('RGB')(sample, f)
        self.assertEqual([im.getpixel((i, 0)) for i in r3],
            [(255, 255, 255), (255, 255, 255), (255, 255, 255)])
        self.assertEqual([im.getpixel((i, 1)) for i in r3],
            [(128, 128, 128), (191, 191, 191), (255, 255, 255)])
        self.assertEqual([im.getpixel((i, 2)) for i in r3],
            [(0, 0, 0), (127, 127, 127), (255, 255, 255)])

        # При преобразовании в RGB должно накладываться на синий
        im = convert('RGB', background='blue')(sample, f)
        self.assertEqual([im.getpixel((i, 0)) for i in r3],
            [(0, 0, 255), (0, 0, 255), (0, 0, 255)])
        self.assertEqual([im.getpixel((i, 1)) for i in r3],
            [(0, 0, 128), (63, 63, 191), (127, 127, 255)])
        self.assertEqual([im.getpixel((i, 2)) for i in r3],
            [(0, 0, 0), (127, 127, 127), (255, 255, 255)])

        # При преобразовании в P по-умолчанию используется палитра WEB
        im = convert('P', background='blue')(sample, f)
        self.assertEqual([self.palette_color(im, (i, 0)) for i in r3],
            [(0, 0, 255), (0, 0, 255), (0, 0, 255)])
        self.assertEqual([self.palette_color(im, (i, 1)) for i in r3],
            [(0, 0, 153), (51, 51, 204), (153, 153, 255)])
        self.assertEqual([self.palette_color(im, (i, 2)) for i in r3],
            [(0, 0, 0), (102, 102, 102), (255, 255, 255)])

        # При преобразовании в P используем более точную палитру.
        im = convert('P', background='blue', palette=Image.ADAPTIVE)(sample, f)
        self.assertEqual([self.palette_color(im, (i, 0)) for i in r3],
            [(0, 0, 255), (0, 0, 255), (0, 0, 255)])
        self.assertEqual([self.palette_color(im, (i, 1)) for i in r3],
            [(0, 0, 128), (63, 63, 191), (127, 127, 255)])
        self.assertEqual([self.palette_color(im, (i, 2)) for i in r3],
            [(0, 0, 0), (127, 127, 127), (255, 255, 255)])

        # Картинка с палитрой, где 3-й элемент прозрачный.
        sample = self.im(mode='P')
        for i in range(4):
            sample.putpixel((i, 0), i)
        p = sample.getpalette()
        p[0:9] = [10, 20, 30, 115, 117, 127, 255, 255, 255]
        sample.putpalette(p)
        sample.info['transparency'] = 3

        im = convert('RGB', background='blue')(sample, f)
        self.assertEqual([im.getpixel((i, 0)) for i in range(4)],
            [(10, 20, 30), (115, 117, 127), (255, 255, 255), (0, 0, 255)])

        im = convert('P', background='blue')(sample, f)
        self.assertEqual([self.palette_color(im, (i, 0)) for i in range(4)],
            [(10, 20, 30), (115, 117, 127), (255, 255, 255), (3, 3, 3)])

        im = convert('RGBA', background='blue')(sample, f)
        self.assertEqual([im.getpixel((i, 0)) for i in range(4)],
            [(10, 20, 30, 255), (115, 117, 127, 255), (255, 255, 255, 255),
                (3, 3, 3, 0)])

        # Тут должен был быть тест на преобразование изображений с палитрой
        # и полупрозрачностью в RGB, но PIL игнорирует альфу в 8-битных PNG.
