"""比较两阶段云与原分辨率积分，验证细前景、深度交界和运动时的误差。"""
from artifact_paths import artifact_path

import numpy as np
from PIL import Image

from gl_context import GLContext
from test_clouds import CloudScene
from validate_shaders import ROOT


def main():
    worst = np.zeros(2)
    previews = []
    with GLContext() as gl:
        scene = CloudScene(gl,512)
        try:
            for camera in ((0,80,0),(3970,238,4869),(3970,420,4869)):
                for pitch in (5,55):
                    for rain,storm in ((0,0),(1,0),(1,1)):
                        view = dict(camera=camera,pitch=pitch,rain=rain,storm=storm)
                        actual = scene.render(**view)
                        reference = scene.render(**view,full_resolution=True)
                        error = abs(actual-reference)
                        metrics = np.array([error.mean(),np.quantile(error,.99)])
                        worst = np.maximum(worst,metrics)
                        assert metrics[0]<0.003 and metrics[1]<0.05, (view,metrics)
                        if camera==(3970,238,4869) and pitch==55:
                            previews.append(np.concatenate((reference,actual,np.clip(error*5,0,1)),axis=1)[::-1])
            size = scene.size
            y,x = np.mgrid[:size,:size]
            foreground = (x%17==0) | (y < 110+35*np.sin(x*0.035))
            depth = np.where(foreground,0.99,1.0).astype(np.float32)
            background = np.stack((0.1+(x%2)*0.4,0.1+(y%2)*0.2,np.full_like(x,.3,dtype=float)),axis=-1).astype(np.float32)
            view = dict(camera=(3970,238,4869),pitch=30,rain=1,background=background)
            for dh in (False,True):
                geometry = dict(dh=dh,**({'dh_depth':depth} if dh else {'depth':depth}))
                actual = scene.render(**view,**geometry)
                reference = scene.render(**view,**geometry,full_resolution=True)
                assert np.allclose(actual[foreground],background[foreground],atol=1e-6), '云不得覆盖单像素前景'
                assert np.mean(abs(actual-reference))<0.004
            # 半分辨率深度完全看不到的天空细缝必须由完整积分补齐。
            slits = np.full((size,size),0.99,np.float32)
            slits[:,::2] = 1.0
            actual = scene.render(**view,depth=slits)
            reference = scene.render(**view,depth=slits,full_resolution=True)
            assert np.allclose(actual,reference,atol=2e-5), '天空细缝的直接积分回退失效'
            # 相邻时刻与轻微视角变化，不得放大时间跳变；静止输入必须完全可重现。
            view = dict(camera=(3970,238,4869),pitch=30,rain=1)
            a = scene.render(**view,seconds=12)
            assert np.array_equal(a,scene.render(**view,seconds=12))
            b = scene.render(**dict(view,pitch=30.02),seconds=12.05)
            ra = scene.render(**view,seconds=12,full_resolution=True)
            rb = scene.render(**dict(view,pitch=30.02),seconds=12.05,full_resolution=True)
            assert np.mean(abs(b-a)) <= np.mean(abs(rb-ra))*1.5+0.0005
            assert np.quantile(abs(b-a),.99) <= np.quantile(abs(rb-ra),.99)*1.5+0.005
            Image.fromarray(np.uint8(np.clip(np.concatenate(previews),0,1)**(1/2.2)*255)).save(artifact_path('cloud-resolution-preview.png'))
        finally:
            scene.close()
        odd = CloudScene(gl,511)
        try:
            a = odd.render(camera=(3970,238,4869),rain=1)
            b = odd.render(camera=(3970,238,4869),rain=1,full_resolution=True)
            assert np.mean(abs(a-b))<0.003
            assert np.mean(abs(a[-1]-b[-1]))<0.01 and np.mean(abs(a[:,-1]-b[:,-1]))<0.01
        finally:
            odd.close()
    print('Maximum scene mean/p99 error:',worst)
    print('PASS: half-resolution weather/interior, normal/DH thin foreground, sky slits, motion, odd viewport')


if __name__ == '__main__':
    main()
