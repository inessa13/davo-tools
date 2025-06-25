import logging
import os

import cv2
import numpy as np
import yaml

from . import cv3

logger = logging.getLogger(__name__)

STAT_FILE = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', 'cv2stat.yaml'))


def init_stat_yaml():
    if not os.path.exists(STAT_FILE):
        return {}
    with open(STAT_FILE, 'rt') as file:
        stat = yaml.safe_load(file)
    return stat


def flush_stat_yaml(data):
    data['stat'] = dict(sorted(
        data['stat'].items(), key=lambda i: i[1].get('success'), reverse=True))
    with open(STAT_FILE, 'wt') as file:
        yaml.dump(data, file, sort_keys=False)


def image_recover(
        image,
        context: dict,
        pipelines: dict,
        algo: str = None,
        scale: float = 1,
        min_contour: float = None,
        max_contour: float = None,
        debug: bool = False,
        verbose: bool = False,
):
    # scale down to speed up
    try:
        image = cv2.resize(image, (0, 0), fx=scale, fy=scale)
    except Exception as exc:
        logger.error(
            '%s: downscale failed (%s)',
            context.get('file'),
            str(exc).split('\n')[0],
        )
        return None

    if algo:
        pipelines = {k: v for k, v in pipelines if k == algo}

    ths = {}
    for name, pipeline in pipelines.items():
        ths[name] = pipeline(image, context)

    debug_contour = image.copy()
    max_area = 0
    img_size = image.shape[0] * image.shape[1]
    min_cnt = img_size * min_contour
    max_cnt = img_size * max_contour

    best_c = None
    has_some = False
    stat = init_stat_yaml()
    try:
        for name, t in ths.items():
            _stat = stat.setdefault('stat', {}).setdefault(name, {
                'try': 0,
                'success': 0,
                'min': 0,
                'max': 0,
            })
            _stat['try'] += 1

            try:
                c = find_contours(image, context, t, min_cnt, max_cnt, debug=debug)
            except Exception as exc:
                if verbose:
                    logger.error('%s - %s: failed (%s)', context.get('file'), name, str(exc).split('\n')[0])
                continue

            if c is None:
                continue

            a = cv2.contourArea(c)
            if a > max_area and a >= min_cnt and a <= max_cnt:
                if verbose:
                    logger.info('%s - %s: %.2f' % (context.get('file'), name, a / img_size * 100))
                max_area = a
                best_c = c

                a_rel = a / img_size * 100
                _stat['success'] += 1
                _stat['min'] = min(_stat['min'], a_rel)
                _stat['max'] = min(_stat['max'], a_rel)

            has_some = True
            cv2.drawContours(debug_contour, [c], -1, (0, 255, 0), 3)
    except KeyboardInterrupt:
        flush_stat_yaml(stat)
        raise

    if has_some:
        cv3.debug_write(debug_contour, context, '8_cont')
        flush_stat_yaml(stat)

    if best_c is not None:
        best_c = np.array(
            [[[int(pt[0][0] / scale), int(pt[0][1] / scale)]] for pt in best_c],
            dtype=np.int32)

    return best_c


def find_contours(image, context, edged, min_cnt, max_cnt, debug=False):
    contours, _ = cv2.findContours(
        edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)

    contours = [c for c in contours if min_cnt <= cv2.contourArea(c) <= max_cnt]

    photo_contour = None
    debug_contour = image.copy()
    for i, contour in enumerate(contours):
        peri = cv2.arcLength(contour, True)
        # TODO:  Настроить epsilon в approxPolyDP (0.01, 0.05).
        approx = cv2.approxPolyDP(contour, 0.02 * peri, True)

        if len(approx) == 4:
            photo_contour = approx

        if debug:
            cv2.drawContours(debug_contour, [contour], -1, (0, 255, 0), 3)
            cv2.drawContours(debug_contour, [approx], -1, (255, 0, 0), 2)

            try:
                hull = cv2.convexHull(contour)
                approx2 = cv2.approxPolyDP(hull, 0.02 * cv2.arcLength(hull, True), False)
                cv2.drawContours(debug, [approx2], -1, (0, 0, 255), 4)
            except:
                pass

    if debug and contours:
        cv3.debug_write(debug_contour, context, '9_cont')

    return photo_contour


def rotate(image, contour, file_name):
    warped = cv3.four_point_transform(image, contour)
    cv2.imwrite(file_name, warped)
