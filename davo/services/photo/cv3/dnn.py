import os

import cv2
import numpy as np


def detect_dnn(image):
    path = os.path.join(os.path.dirname(__file__), '..', '..', 'dnn')
    pb = os.path.abspath(os.path.join(path, 'frozen_inference_graph.pb'))
    # txt = os.path.abspath(os.path.join(path, 'deeplabv3_mnv2_pascal_train_aug.pbtxt'))
    txt = os.path.abspath(os.path.join(path, 'ssd_inception_v2_coco_2017_11_17.pbtxt'))
    # net = cv2.dnn.readNetFromTensorflow(pb, txt)
    # net = cv2.dnn.readNetFromONNX(os.path.abspath(os.path.join(path, 'yolov4-tiny.onnx')))
    net = cv2.dnn.readNet(
        os.path.abspath(os.path.join(path, 'yolov4-tiny.cfg')),
        os.path.abspath(os.path.join(path, 'yolov4-tiny.weights')),
    )
    yolo(net, image)
    return


def yolo(net, image):
    net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)

    # === Загрузка и подготовка изображения ===
    (H, W) = image.shape[:2]
    blob = cv2.dnn.blobFromImage(image, 1 / 255.0, (416, 416), swapRB=True,
                                 crop=False)
    net.setInput(blob)

    # === Выходные слои ===
    ln = net.getLayerNames()
    output_layers = [ln[i - 1] for i in net.getUnconnectedOutLayers()]

    # === Прямой проход ===
    layer_outputs = net.forward(output_layers)

    # === Парсинг выходов ===
    boxes = []
    confidences = []
    conf_threshold = 0.1

    for output in layer_outputs:
        for detection in output:
            scores = detection[5:]
            class_id = np.argmax(scores)
            confidence = scores[class_id]

            if confidence > conf_threshold:
                center_x = int(detection[0] * W)
                center_y = int(detection[1] * H)
                width = int(detection[2] * W)
                height = int(detection[3] * H)

                x = int(center_x - width / 2)
                y = int(center_y - height / 2)

                boxes.append([x, y, width, height])
                confidences.append(float(confidence))

    # === NMS (подавление повторений) ===
    indices = cv2.dnn.NMSBoxes(boxes, confidences,
                               score_threshold=conf_threshold,
                               nms_threshold=0.2)

    # === Вырезание и маскирование фона ===
    debug = image.copy()
    # for i, _ in enumerate(boxes):
    for i in indices:
        i = i[0] if isinstance(i, (list, tuple, np.ndarray)) else i
        x, y, w, h = boxes[i]

        # Вырезаем фото
        cv2.rectangle(debug, (x, y), (x + w, y + h), (0, 255, 0), i)
        cropped = image[y:y + h, x:x + w]

        # Создаем альфа-канал (маска из непрозрачного прямоугольника)
        alpha = np.ones((h, w), dtype=np.uint8) * 255
        # cropped_rgba = cv2.merge((cropped, alpha))
        if cropped.shape[:2] == alpha.shape:
            cropped_rgba = cv2.merge((*cv2.split(cropped), alpha))
            cv2.imwrite("cropped_photo{}.png".format(i), cropped_rgba)
            # Сохраняем результат
            print(f"Сохранили: cropped_photo.png")
        else:
            print("❌ Размеры не совпадают, вырезка невозможна.")
    cv2.imwrite("cropped_photo_d.png", debug)

    # Для отладки — рисуем детекцию
    for i in indices:
        i = i[0] if isinstance(i, (list, tuple, np.ndarray)) else i
        x, y, w, h = boxes[i]
        cv2.rectangle(image, (x, y), (x + w, y + h), (0, 255, 0), 2)

    cv2.imwrite("detection_preview.jpg", image)
