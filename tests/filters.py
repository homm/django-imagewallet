# -*- coding: utf-8 -*-

from django.test import TestCase

from imagewallet.filter_tools import size_handler
from imagewallet.filters import resize_methods


class ToolsTest(TestCase):
    def test_size_handler(self):
        # Значение не задано
        self.assertEqual(size_handler(None)(30), 30)
        self.assertEqual(size_handler(None)(-100), -100)

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
            self.assertEqual(size_handler('200px')(30), 200)
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


class FiltersTest(TestCase):

    def test_resize_method_exactly(self):
        method = resize_methods['exactly']
        self.assertEqual(method(160, 120, 300, 200), (160, 120))
        self.assertEqual(method(120, 160, 300, 200), (120, 160))

    def test_resize_method_not_more(self):
        # Фиксируем нужный размер, пробуем разные фотки.
        # Первая серия на уменьшение
        # Вторая не меняет размер хотя бы одного параметра
        # Третья на увеличение
        # В серии:
        #     Первая фотка более горизонтальная
        #     Вторая пропорции совпадают
        #     Третья более вертикальная
        method = resize_methods['not_more']

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

