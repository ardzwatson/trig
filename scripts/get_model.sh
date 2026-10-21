#!/bin/sh
# Exports YOLOv8n to ONNX -> models/person.onnx. Needs internet; run once (on any machine), then copy the file.
# Note: ultralytics/YOLOv8 is AGPL-3.0 – fine for personal use, check before distributing.
set -e
mkdir -p models
python3 -m venv /tmp/yolo-export && . /tmp/yolo-export/bin/activate
pip install -q ultralytics onnx
yolo export model=yolov8n.pt format=onnx imgsz=640 simplify=False
mv yolov8n.onnx models/person.onnx
echo "done: models/person.onnx"
