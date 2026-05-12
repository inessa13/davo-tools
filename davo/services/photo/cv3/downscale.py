import logging

import cv2
from skimage.metrics import structural_similarity as ssim

logger = logging.getLogger(__name__)


def image_downscale(
    image,
    min_width: int,
    min_height: int,
    speed: float,
    ssim_threshold: float,
):
    """
    :param image:
    :param min_width: минимально допустимая ширина
    :param min_height: минимально допустимая высота
    :param speed:
    :param ssim_threshold: коэффициент сохранения деталей (SSIM)
    :return: уменьшенное изображение
    """
    gray_original = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    h, w = gray_original.shape
    scale = 1.0

    best_img = image
    best_ssim = 1.0

    while True:
        scale -= speed
        if scale <= 0.1:
            break

        new_w = int(w * scale)
        new_h = int(h * scale)

        if new_w < min_width or new_h < min_height:
            break

        resized = cv2.resize(
            image, (new_w, new_h), interpolation=cv2.INTER_AREA
        )
        gray_resized = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        gray_upscaled = cv2.resize(
            gray_resized, (w, h), interpolation=cv2.INTER_LINEAR
        )

        ssim_val = ssim(gray_original, gray_upscaled)
        if ssim_val >= ssim_threshold:
            best_img = resized
            best_ssim = ssim_val
        else:
            break

    return best_img, best_ssim
