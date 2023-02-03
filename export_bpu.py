import argparse
from io import BytesIO

import onnx
import torch
from ultralytics import YOLO

from models.common import optim

try:
    import onnxsim
except ImportError:
    onnxsim = None


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-w',
                        '--weights',
                        type=str,
                        required=True,
                        help='PyTorch yolov8 weights')
    parser.add_argument('--opset',
                        type=int,
                        default=11,
                        help='ONNX opset version')
    parser.add_argument('--sim',
                        action='store_true',
                        help='simplify onnx model')
    parser.add_argument('--input-shape',
                        nargs='+',
                        type=int,
                        default=[1, 3, 640, 640],
                        help='Model input shape only for api builder')
    parser.add_argument('--device',
                        type=str,
                        default='cpu',
                        help='Export ONNX device')
    args = parser.parse_args()
    assert len(args.input_shape) == 4
    args.det = True
    return args


def main(args):
    YOLOv8 = YOLO(args.weights)
    model = YOLOv8.model.fuse().eval()
    for m in model.modules():
        optim(m, is_bpu=True)
        m.to(args.device)
    model.to(args.device)
    fake_input = torch.randn(args.input_shape).to(args.device)
    for _ in range(2):
        model(fake_input)
    save_path = args.weights.replace('.pt', '.onnx')
    output_names = ['bboxes_80x80', 'scores_80x80',
                    'bboxes_40x40', 'scores_40x40',
                    'bboxes_20x20', 'scores_20x20'] \
        if args.det else ['bboxes_80x80', 'scores_80x80', 'mconf_80x80',
                          'bboxes_40x40', 'scores_40x40', 'mconf_40x40',
                          'bboxes_20x20', 'scores_20x20', 'mconf_20x20',
                          'proto']
    with BytesIO() as f:
        torch.onnx.export(model,
                          fake_input,
                          f,
                          opset_version=args.opset,
                          input_names=['images'],
                          output_names=output_names)
        f.seek(0)
        onnx_model = onnx.load(f)
    onnx.checker.check_model(onnx_model)
    if args.sim:
        try:
            onnx_model, check = onnxsim.simplify(onnx_model)
            assert check, 'assert check failed'
        except Exception as e:
            print(f'Simplifier failure: {e}')
    onnx.save(onnx_model, save_path)
    print(f'ONNX export success, saved as {save_path}')


if __name__ == '__main__':
    main(parse_args())
