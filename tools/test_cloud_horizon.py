"""验证阴雨厚云在距离边界与天空底色衔接，覆盖短视距、远景遮挡和水下。"""
from artifact_paths import artifact_path

import math

import numpy as np
from PIL import Image

from gl_context import GLContext
from test_clouds import CloudScene
from validate_shaders import ROOT


def smooth(low, high, value):
    t = np.clip((value-low)/(high-low),0,1)
    return t*t*(3-2*t)


def main():
    size, pitch, fov = 384, 2, 16
    axis = ((np.arange(size)+0.5)/size*2-1)*math.tan(math.radians(fov)*0.5)
    x,y = np.meshgrid(axis,axis)
    angle = math.radians(pitch)
    elevation = (y*math.cos(angle)+math.sin(angle))/np.sqrt(x*x+y*y+1)
    fog = np.array([0.18,0.20,0.26])
    sky = np.array([0.10,0.13,0.20])
    blend = smooth(0,0.55,elevation)[...,None]
    background = (fog**2.2*(1-blend)+sky**2.2*blend).astype(np.float32)
    previews = []
    with GLContext() as gl:
        scene = CloudScene(gl,size=size)
        try:
            for distance in (2000,4000,6000,8000):
                view = dict(camera=(3714,147,4627),pitch=pitch,fov=fov,rain=1,storm=1,
                            fog=tuple(fog),sky=tuple(sky),background=background,
                            options={'CLOUD_DISTANCE':str(float(distance))})
                cloudy = scene.render(**view)
                # 只在很远处才能进入云层的视线必须与天空连续，不能形成深色截断线。
                edge = (elevation > 0) & (elevation < (320-147)/(distance*0.80))
                assert edge.any()
                assert np.max(abs(cloudy[edge]-background[edge])) < 0.00001, '云层距离边界出现色差'
                display = np.clip(cloudy,0,1)**(1/2.2)
                if distance == 6000:
                    step = float(np.max(abs(np.diff(display.mean(axis=1),axis=0))))
                    assert step < 1/255, '地平线出现可见横向色带'
                    print('Horizon maximum adjacent-row display difference:',step,flush=True)
                    # 深度接收仍使用真实几何，天空色不能覆盖前景或近景地形。
                    half = np.ones((size,size),np.float32)
                    half[:,:size//2] = 0.99
                    for dh in (False,True):
                        occluded = scene.render(**view,dh=dh,**({'dh_depth':half} if dh else {'depth':half}))
                        assert np.allclose(occluded[:,:size//2],background[:,:size//2],atol=1e-6)
                        assert np.allclose(occluded[:,size//2+2:],cloudy[:,size//2+2:],atol=1e-5)
                        reference = scene.render(**view,dh=dh,full_resolution=True,**({'dh_depth':half} if dh else {'depth':half}))
                        assert np.mean(abs(occluded[:,size//2:size//2+2]-reference[:,size//2:size//2+2]))<0.005
                    # 水下背景的低处由水色过渡至空气天空，不使用水雾 fogColor 染天空。
                    water_sky = sky**2.2*(0.75+0.25*blend)
                    water_blend = smooth(-0.12,0.12,elevation)[...,None]
                    water_background = (0.00105*(1-water_blend)+water_sky*water_blend).astype(np.float32)
                    water_view = dict(view,eye=1,background=water_background,fog=(0.01,0.03,0.05))
                    underwater = scene.render(**water_view)
                    assert np.max(abs(underwater[edge]-water_background[edge])) < 0.00001
                previews.append(display[::-1])
            Image.fromarray(np.uint8(np.concatenate(previews,axis=1)*255)).save(artifact_path('cloud-horizon-preview.png'))
            print('PASS: rainy horizon, cloud distance 2000/4000/6000/8000, terrain/DH occlusion, underwater continuity')
        finally:
            scene.close()


if __name__ == '__main__':
    main()
