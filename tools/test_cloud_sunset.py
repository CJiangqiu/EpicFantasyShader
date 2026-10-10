"""冻结风场并缓慢转动日月方向，验证掠射光下云内阴影的时间连续性。"""
from artifact_paths import artifact_path

import numpy as np
from PIL import Image

from gl_context import GLContext
from test_clouds import CloudScene
from validate_shaders import ROOT


def main():
    previews = []
    worst = np.zeros(3)
    with GLContext() as gl:
        scene = CloudScene(gl, size=192)
        try:
            for camera in ((3651,120,4644), (3970,238,4869)):
                for rain, storm in ((0,0), (1,0), (1,1)):
                    for height in (-0.03, -0.02, 0, 0.02, 0.025, 0.03, 0.05, 0.1, 0.2):
                        view = dict(camera=camera, pitch=50, seconds=0, rain=rain, storm=storm)
                        a = scene.render(**view, sun_direction=(1,height-0.00025,0))
                        b = scene.render(**view, sun_direction=(1,height+0.00025,0))
                        delta = np.abs(b-a)
                        metrics = np.array([delta.mean(), np.quantile(delta,0.99), delta.max()])
                        worst = np.maximum(worst,metrics)
                        # 小幅日月旋转可以改变照明，但不能令局部阴影在相邻时刻突跳。
                        assert np.all(metrics < (0.002,0.015,0.025)), (camera,rain,storm,height,metrics)
                        if camera == (3651,120,4644) and rain == 0:
                            previews.append(np.concatenate((a,b),axis=1)[::-1])
            output = artifact_path('cloud-sunset-preview.png')
            output.parent.mkdir(exist_ok=True)
            Image.fromarray(np.uint8(np.clip(np.concatenate(previews),0,1)**(1/2.2)*255)).save(output)
            print('Sunset maximum mean/p99/pixel change:',worst)
            print('PASS: grazing cloud lighting, sun/moon handover, frozen wind, two locations, three weather states')
        finally:
            scene.close()


if __name__ == '__main__':
    main()
