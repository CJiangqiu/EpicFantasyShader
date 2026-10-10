"""验证云影附件插值、世界坐标对齐、缓存边界及当帧天气更新。"""

from unittest.mock import patch

import numpy as np

import test_clouds
from gl_context import GLContext
from test_clouds import CloudScene


def main():
    original = test_clouds.expand
    def direct_source(path):
        # 参考路径保留相同十六点积分，仅旁路附件读取。
        return original(path).replace('if (world.y < CLOUD_ALTITUDE) {','if (false) {')
    worst = np.zeros(3)
    with GLContext() as gl:
        cached, direct = CloudScene(gl,128), CloudScene(gl,128)
        try:
            for camera in ((0,80,0),(3970,80,4869),(-1800,80,-2400)):
                for rain,storm in ((0,0),(1,0),(1,1)):
                    for height in (80,450,900):
                        for light in ((0.4,1,0.2),(1,0.1,0.2)):
                            view = dict(shadow=True,camera=camera,shadow_center=(camera[0],height,camera[2]),
                                        shadow_span=512,rain=rain,storm=storm,sun_direction=light)
                            actual = cached.render(**view)
                            assert actual.min()>=0 and actual.max()<=1, '三次重建不能产生负透射率或过亮边缘'
                            with patch.object(test_clouds,'expand',direct_source):
                                reference = direct.render(**view)
                            error = abs(actual-reference)
                            metrics = np.array([error.mean(),np.quantile(error,.99),error.max()])
                            worst = np.maximum(worst,metrics)
                            assert metrics[0]<0.003 and metrics[1]<0.03, (view,metrics)
            # 固定世界位置，跨越相机对齐格点时不得让近景投影随相机滑动。
            view = dict(shadow=True,shadow_center=(4000,80,4870),shadow_span=128)
            fixed = cached.render(**view,camera=(3970,80,4869))
            moved = cached.render(**view,camera=(3981,80,4869))
            assert np.max(abs(fixed-moved))<0.00001, '相机移动导致世界投影变化'
            # 外围连续交接，并验证未缓存区域仍保持原积分。
            for x in (800,900,1000,1024,1100,1600):
                view = dict(shadow=True,camera=(0,80,0),shadow_center=(x,80,0),shadow_span=128)
                actual = cached.render(**view)
                with patch.object(test_clouds,'expand',direct_source):
                    reference = direct.render(**view)
                assert np.mean(abs(actual-reference))<0.003
                if x>=1100:
                    assert np.allclose(actual,reference,atol=1e-6)
            assert np.allclose(cached.render(shadow=True,sun_direction=(1,0.01,0)),1)
            a = cached.render(shadow=True,camera=(3970,80,4869),shadow_span=1024)
            b = cached.render(shadow=True,camera=(3970,80,4869),shadow_span=1024,seconds=60)
            assert np.mean(abs(a-b))>0.005, '附件须随当帧风场更新'
            print('Cache error maximum mean/p99/pixel:',worst)
            print('PASS: current-frame weather/wind, snapped camera, edge fallback, cloud interior/above, low sun')
        finally:
            cached.close()
            direct.close()


if __name__ == '__main__':
    main()
