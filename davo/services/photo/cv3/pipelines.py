import cv2
import numpy as np

from .common import debug_write


def get_pipelines(verbose):
    alogs_thresh = (
        (_thresh_otsu, 100, 200, 5),
        (_thresh_otsu, 100, 200, 7),
        (_thresh_otsu, 100, 200, 11),
        (_thresh_otsu, 80, 160, 5),
        (_thresh_otsu, 80, 160, 7),
        (_thresh_otsu, 80, 160, 11),
        (_thresh_norm, 120, 255, 5),
        (_thresh_norm, 120, 255, 7),
        (_thresh_norm, 120, 255, 11),
        (_thresh_norm, 150, 255, 5),
        (_thresh_norm, 180, 255, 5),
        (_thresh_norm, 200, 255, 5),
        (_thresh_norm, 200, 255, 7),
        (_thresh_norm, 200, 255, 11),
        (_thresh_norm, 210, 255, 5),
        (_thresh_norm, 215, 255, 5),
        (_thresh_adap, False, 255, 5, 2, False),
        # Пайплайн для текстурированных фонов (например, фото на столе)
        (_thresh_adap, True, 255, 51, 10, False),
        # Пайплайн для тёмных или засвеченных изображений + вариации
        (_algo_clahe, 3.0, False),
        (_algo_clahe, 2.0, False),
        (_algo_clahe, 4.0, False),
        (_algo_clahe, 3.0, True),
        (_algo_clahe, 2.0, True),
        (_algo_clahe, 4.0, True),
        # (_thresh_adap, 255, 7, 0),
        # (_thresh_adap, 255, 11, 0),
        # (_thresh_adap, 255, 5, 1),
        # (_thresh_adap, 255, 7, 1),
        # (_thresh_adap, 255, 11, 1),
    )
    algos_edges = [
        _canny,
        _canny_morph,
        _sobel,
        _sobel_morph,
        _sobel_hough,
        _sobel_morph_hough,
        _sobel_hough_dilate,
        _sobel_hough_extend,
    ]
    if verbose:
        print('Detection started with {} threshold and {} detection algos'.format(len(alogs_thresh), len(algos_edges)))

    pipelines = {}
    for args in alogs_thresh:
        prep = args[0]
        args = args[1:]
        for detector in algos_edges:
            name = '{}{}-{}'.format(prep.__name__.strip('_'), '-'.join(map(str, args)), detector.__name__.strip('_'))
            # pipelines[name] = lambda image, context: detector(prep(image, *args, algo=name, **context), **context)
            pipelines[name] = pipeline(prep, detector, args, name)
    return pipelines


def pipeline(thresh, edge, args, name):
    def _wrap(image, context):
        i1 = thresh(image, *args, algo=name, **context)
        debug_write(i1, context, name)
        return edge(image, **context)
    return _wrap


def _thresh_adap(image, blur=False, max_val=255, block_size=5, c=2, rev=False, **context):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if blur:
        gray = cv2.GaussianBlur(gray, (9, 9), 0)
    result = cv2.adaptiveThreshold(
        gray,
        max_val,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY,
        block_size,
        c
    )
    if rev:
        result = cv2.bitwise_not(result)
    # debug_write(result, context, '2_thresh_adapt')
    return result


def _thresh_otsu(image, thresh=0, max_val=255, block_size=5, **context):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (block_size, block_size), 0)

    _, result = cv2.threshold(
        blur,
        thresh,
        max_val,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU,
    )
    # debug_write(result, context, '2_thresh_otsu')
    return result


def _thresh_norm(image, thresh=0, max_val=255, block_size=5, **context):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (block_size, block_size), 0)

    _, result = cv2.threshold(
        blur,
        thresh,
        max_val,
        cv2.THRESH_BINARY,
    )
    # debug_write(result, context, '2_thresh_norm')
    return result


def _low_contrast(image, alpha=100, beta=200, **context):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    result = cv2.normalize(
        gray, None, alpha=alpha, beta=beta, norm_type=cv2.NORM_MINMAX)
    # result = cv2.GaussianBlur(result, (5, 5), 0)
    # debug_write(result, context, '2_low_contrast')
    return result


def _algo_clahe(image, clip_limit=3.0, inv=False, **context):
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8))
    l = clahe.apply(l)
    lab = cv2.merge((l, a, b))
    gray = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
    if inv:
        tt = cv2.THRESH_BINARY_INV
    else:
        tt = cv2.THRESH_BINARY
    return cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        tt, 11, 2)


def _canny(thresh, **context):
    # thresh = clear_thresh_otsu(image, 100, 200, 5, debug=True)
    # thresh = clear_thresh(image, 120, 200, 5, debug=True)

    edged = cv2.Canny(thresh, 75, 150)
    # debug_write(edged, context, '3_canny')
    return edged


def _canny_morph(thresh, **context):
    edged = _canny(thresh, **context)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    image = cv2.morphologyEx(edged, cv2.MORPH_CLOSE, kernel)
    # debug_write(image, context, '4_canny_morph')
    return image
    # return find_contours(image, edged, debug=True)


def _sobel_(thresh):
    # thresh = clear_thresh_otsu(image, 100, 200, 5, debug=True)

    grad_x = cv2.Sobel(thresh, cv2.CV_64F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(thresh, cv2.CV_64F, 0, 1, ksize=3)

    magnitude = cv2.magnitude(grad_x, grad_y)
    magnitude = cv2.convertScaleAbs(magnitude)
    return magnitude


def _sobel(thresh, **context):
    image = _sobel_(thresh)
    # debug_write(image, context, '3_sobel')
    return image


def _sobel_morph(thresh, **context):
    magnitude = _sobel_(thresh)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    closed = cv2.morphologyEx(magnitude, cv2.MORPH_CLOSE, kernel)
    # debug_write(closed, context, '4_sobel_morph')
    return closed


def _sobel_hough_(thresh, dilate=False, extend=False):
    if dilate:
        kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT, (3, 3))
        thresh = cv2.dilate(thresh, kernel, iterations=1)

    if thresh.dtype != np.uint8 or len(thresh.shape) != 2:
        thresh = cv2.cvtColor(thresh, cv2.COLOR_BGR2GRAY)

    # 6. Метод Хафа для поиска прямых (Hough Transform)
    lines = cv2.HoughLinesP(
        thresh,
        rho=1,  # точность по расстоянию (пиксели)
        theta=np.pi / 180,  # точность по углу (радианы)
        threshold=100,  # минимальное число пересечений
        minLineLength=300,  # минимальная длина линии
        maxLineGap=50)  # максимальный разрыв между сегментами

    line_img = thresh.copy()
    if lines is not None:
        for line in lines:
            x1, y1, x2, y2 = line[0]
            if extend:
                height, width = thresh.shape[:2]
                x1, y1, x2, y2 = _extend_hough_line(x1, y1, x2, y2, width, height)
            cv2.line(line_img, (x1, y1), (x2, y2), (255, 255, 255), 3)
    return line_img


def _extend_hough_line(x1, y1, x2, y2, w, h):
    # Уравнение прямой: (x - x1) / dx = (y - y1) / dy
    dx = x2 - x1
    dy = y2 - y1

    if dx == 0:
        return x1, 0, x1, h
    if dy == 0:
        return 0, y1, w, y1

    # Найдём пересечения с 4 краями
    points = []
    for x in [0, w]:
        y = int(y1 + dy * (x - x1) / dx)
        if 0 <= y <= h:
            points.append((x, y))
    for y in [0, h]:
        x = int(x1 + dx * (y - y1) / dy)
        if 0 <= x <= w:
            points.append((x, y))

    if len(points) >= 2:
        return points[0][0], points[0][1], points[1][0], points[1][1]
    else:
        return x1, y1, x2, y2  # fallback


def _sobel_hough(thresh, **context):
    image = _sobel_hough_(_sobel_(thresh))
    # debug_write(image, context, '4_sobel_hough')
    return image


def _sobel_morph_hough(thresh, **context):
    image = _sobel_hough_(_sobel_morph(thresh, **context))
    # debug_write(image, context, '4_sobel_hough_morph')
    return image


def _sobel_hough_dilate(thresh, **context):
    image = _sobel_hough_(_sobel_(thresh), dilate=True, extend=False)
    # debug_write(image, context, '4_sobel_hough_dilate')
    return image


def _sobel_hough_extend(thresh, **context):
    image = _sobel_hough_(_sobel_(thresh), dilate=False, extend=True)
    # debug_write(image, context, '4_sobel_hough_dilate_extend')
    return image


# TODO:
# Пайплайн для чеков (высокий контраст, но много шума)
# gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
# binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_TRIANGLE)[1]
# kernel = np.ones((3, 3), np.uint8)
# opened = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=2)
# contours, _ = cv2.findContours(opened, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
# Вариации:
# - Использовать MORPH_CLOSE если есть разрывы в границах.
# - Применить dilate перед findContours.
