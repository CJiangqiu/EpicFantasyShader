"""生成周期三维散列图集，四通道保存相邻横坐标和高度的角点。"""

from pathlib import Path

import numpy as np
from PIL import Image


SIZE = 72
TILE = SIZE + 1
COLUMNS = 9
PATH = Path(__file__).resolve().parents[1] / 'shaders/textures/cloud_noise.png'


def generate():
    # 负坐标区间与主体噪声共用散列规则，边界按周期延拓。
    axis = np.arange(SIZE, dtype=np.float32) - 32
    x, y = np.meshgrid(axis, axis)
    fract = lambda value: value - np.floor(value)
    x, y = fract(x * np.float32(0.1031)), fract(y * np.float32(0.1031))
    slices = []
    for z in axis:
        z = fract(z * np.float32(0.1031))
        dot = x * (y + np.float32(33.33)) + y * (z + np.float32(33.33)) + z * (x + np.float32(33.33))
        values = fract(((x + dot) + (y + dot)) * (z + dot))
        slices.append(np.rint(values * 255).astype(np.uint8))
    atlas = np.zeros((COLUMNS*TILE, COLUMNS*TILE, 4), dtype=np.uint8)
    border = np.arange(TILE) % SIZE
    for index in range(SIZE):
        row, column = divmod(index, COLUMNS)
        tile = atlas[row*TILE:(row+1)*TILE, column*TILE:(column+1)*TILE]
        tile[..., 0] = slices[index][np.ix_(border, border)]
        tile[..., 1] = slices[index][np.ix_(border, (border+1) % SIZE)]
        tile[..., 2] = slices[(index+1) % SIZE][np.ix_(border, border)]
        tile[..., 3] = slices[(index+1) % SIZE][np.ix_(border, (border+1) % SIZE)]
    return atlas


if __name__ == '__main__':
    Image.fromarray(generate()).save(PATH)
    print(PATH)
