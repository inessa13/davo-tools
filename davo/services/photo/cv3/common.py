import logging

import cv2

logger = logging.getLogger(__name__)


def debug_write(image, context, name):
    if not context.get("debug"):
        return
    if context.get("file"):
        name = "{}_{}.jpg".format(context["file"], name)
    else:
        name = "{}.jpg".format(name)

    logger.info("%s debug -> %s", context.get("file"), name)
    cv2.imwrite(name, image)
