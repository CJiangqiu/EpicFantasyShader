"""验证真实闪电输入驱动的雷暴云局部照明、强度响应及遮挡隔离。"""
from artifact_paths import artifact_path

import numpy as np
from PIL import Image

from gl_context import GLContext
from test_clouds import CloudScene
from validate_shaders import ROOT


def display(color):
    peak = color.max(axis=-1,keepdims=True)
    return np.clip(color/(1+np.maximum(peak-.8,0)),0,1)**(1/2.2)


def main():
    with GLContext() as gl:
        scene = CloudScene(gl,384)
        try:
            view = dict(camera=(3970,238,4869),pitch=55,rain=1,storm=1)
            bolt = (0,-158,-200,1)
            base = scene.render(**view)
            bright = scene.render(**view,lightning=bolt,lightning_pulse=.7)
            assert np.mean(bright-base)>.1, '近处落雷须明显照亮云体'
            assert np.all(bright>=base-1e-4)
            gains = []
            for pulse in (0,.1,.3,.7):
                gains.append(np.mean(scene.render(**view,lightning=bolt,lightning_pulse=pulse)-base))
            assert np.all(np.diff(gains)>0), '闪电亮光须随脉冲连续增强'
            assert np.allclose(scene.render(**view,lightning=bolt),base,atol=1e-6)
            assert np.allclose(scene.render(**view,lightning_pulse=.7),base,atol=1e-6)
            assert np.allclose(scene.render(**view,lightning=bolt,lightning_pulse=.7,options={'CLOUD_LIGHTNING':'0'}),base,atol=1e-6)
            far = scene.render(**view,lightning=(4000,-158,-200,1),lightning_pulse=.7)
            assert np.mean(far-base)<np.mean(bright-base)*.02, '落雷不得统一照亮整片天空'
            left = scene.render(**view,lightning=(-300,-158,-200,1),lightning_pulse=.7)-base
            right = scene.render(**view,lightning=(300,-158,-200,1),lightning_pulse=.7)-base
            assert left[:,:scene.size//2].mean()>left[:,scene.size//2:].mean()*1.2
            assert right[:,scene.size//2:].mean()>right[:,:scene.size//2].mean()*1.2
            for rain,storm in ((0,0),(1,0)):
                weather = dict(view,rain=rain,storm=storm)
                assert np.allclose(scene.render(**weather,lightning=bolt,lightning_pulse=.7),scene.render(**weather),atol=1e-6)
            for dimension in ('world-1','world1'):
                assert np.allclose(scene.render(**view,dimension=dimension,lightning=bolt,lightning_pulse=.7),scene.render(**view,dimension=dimension))
            foreground = np.ones((scene.size,scene.size),np.float32)
            foreground[:,::3] = .99
            for dh in (False,True):
                masked = scene.render(**view,dh=dh,lightning=bolt,lightning_pulse=.7,**({'dh_depth':foreground} if dh else {'depth':foreground}))
                assert np.allclose(masked[:,::3],(.12,.3,.65),atol=1e-6), '闪电照云不得覆盖前景'
            # 黑白背景差检验透射率，亮光不能改变云形或遮住云缝。
            plain = [scene.render(**view,background=(value,)*3) for value in (0,1)]
            lit = [scene.render(**view,background=(value,)*3,lightning=bolt,lightning_pulse=.7) for value in (0,1)]
            assert np.allclose(plain[1]-plain[0],lit[1]-lit[0],atol=1e-5)
            reference = scene.render(**view,lightning=bolt,lightning_pulse=.7,full_resolution=True)
            assert np.mean(abs(bright-reference))<.005
            middle = scene.render(**view,lightning=bolt,lightning_pulse=.15)
            Image.fromarray(np.uint8(display(np.concatenate((base,bright,middle),axis=1)[::-1])*255)).save(artifact_path('cloud-lightning-preview.png'))
            print('Lightning mean brightening:',float(np.mean(bright-base)))
            print('PASS: pulse response, inactive input, switch, thunder gate, local falloff, dimensions, normal/DH occlusion, transmission, half-resolution agreement')
        finally:
            scene.close()


if __name__ == '__main__':
    main()
