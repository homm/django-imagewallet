# -*- coding: utf-8 -*-


def size_handler(size):
    """
    Принимает размер в виде строки, как её передал пользователь. Возвращает
    функцию, которая по заданному первоначальному размеру вернет расчитанное
    значение.
    """
    if size is None:
        # None — специальное значение, параметр не задан.
        return lambda original: None

    try:
        # пробуем преобразовать в число
        size = int(size)
    except (TypeError, ValueError):
        pass
    else:
        # если успех, то это фиксированное значение
        return lambda original: size

    try:
        # Дальше можем работать только со строками.
        size = str(size)
    except ValueError:
        pass
    else:
        # '+20px', '-500px'
        if size.endswith('px') and size[0] in ('+', '-'):
            negative = -1 if size[0] == '-' else 1
            try:
                size = negative * int(size[1:-2])
            except ValueError:
                pass
            else:
                return lambda original: original + size

        # '+2.5%' '-10%'
        if size.endswith('%') and size[0] in ('+', '-'):
            negative = -1 if size[0] == '-' else 1
            try:
                # т.к. это проценты, нужно поделить на 100
                size = negative * float(size[1:-1]) / 100
            except ValueError:
                pass
            else:
                return lambda original: original + int(round(original * size))

        # '120%' '66.666%'
        if size.endswith('%'):
            try:
                # т.к. это проценты, нужно поделить на 100
                size = float(size[0:-1]) / 100
            except ValueError:
                pass
            else:
                return lambda original: int(round(original * size))

    raise ValueError("Unsupported notation: %s" % size)


def is_transparent_image(image):
    """
    Проверяет, является ли картинка прозрачной.
    """
    if image.mode in ('RGBA', 'LA'):
        return True
    if image.mode == 'P' and 'transparency' in image.info:
        return True
    return False
