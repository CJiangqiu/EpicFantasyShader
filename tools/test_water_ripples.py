"""验证水面波纹频谱、远处衰减、时钟连续性，并输出法线与反光预览。"""
from artifact_paths import artifact_path
import ctypes as c
import numpy as np
from PIL import Image
from gl_context import GLContext
from test_shadow_filter import FilterScene
from test_sky_background import VERTEX
from validate_shaders import ROOT, SHADERS, configure, expand


def main():
    size=256
    source='#version 330 compatibility\n'+expand(SHADERS/'lib/settings.glsl')+expand(SHADERS/'lib/water_waves.glsl')+'''
in vec2 texcoord;
uniform float testDistance;
layout(location=0) out vec4 scene;
void main() {
    vec3 n=waterWaveNormal(vec3(texcoord.x*16.0+3970.0,80.0,texcoord.y*16.0+4869.0),vec3(0,1,0),testDistance);
    scene=vec4(n,pow(max(dot(n,normalize(vec3(0.12,1,0.08))),0.0),192.0));
}
'''
    with GLContext() as gl:
        target=FilterScene(gl,size)
        programs=[]
        try:
            def render(seconds=0,distance=8,options=None):
                program=gl.program(VERTEX,configure(source,options or {}))
                programs.append(program)
                gl.function('glUseProgram',None,c.c_uint)(program)
                loc=gl.function('glGetUniformLocation',c.c_int,c.c_uint,c.c_char_p)
                for name,value in [('frameTimeCounter',seconds),('testDistance',distance)]:
                    gl.function('glUniform1f',None,c.c_int,c.c_float)(loc(program,name.encode()),value)
                gl.function('glDrawArrays',None,c.c_uint,c.c_int,c.c_int)(0x0004,0,3)
                result=np.empty((size,size,4),np.float32)
                gl.function('glReadPixels',None,c.c_int,c.c_int,c.c_int,c.c_int,c.c_uint,c.c_uint,c.c_void_p)(0,0,size,size,0x1908,0x1406,result.ctypes.data_as(c.c_void_p))
                assert np.isfinite(result).all()
                return result
            near=render()
            assert np.max(abs(np.linalg.norm(near[...,:3],axis=-1)-1))<1e-5
            assert np.mean(abs(near-render(2)))>.001
            far=render(distance=120)
            assert np.std(far[...,0])<np.std(near[...,0])*.5
            assert np.max(abs(render(distance=200)[...,(0,2)]))==0
            for speed in ('0.0','0.5','0.75','1.0','1.5','2.0'):
                options={'WATER_WAVE_SPEED':speed}
                start=render(options=options)
                assert np.allclose(start,render(3600,options=options),atol=1e-5)
                # 回绕附近的运动不应出现整片跳变。
                assert np.mean(abs(start-render(3599.99,options=options)))<.002
            for options in ({'WATER_WAVES':'0'},{'WATER_WAVE_STRENGTH':'0.0'}):
                assert np.max(abs(render(options=options)[...,(0,2)]))==0
            assert np.allclose(render(options={'WATER_WAVE_SPEED':'0.0'}),render(100,options={'WATER_WAVE_SPEED':'0.0'}))
            # 窗函数抑制边界泄漏；少数固定平面波会将能量集中在几个频率上。
            field=near[...,0]*np.outer(np.hanning(size),np.hanning(size))
            power=abs(np.fft.fft2(field))**2
            concentration=np.sort(power.ravel())[-12:].sum()/power.sum()
            assert concentration<.25, f'波纹频谱过度集中：{concentration}'
            preview=np.concatenate([np.repeat(a[...,3,None],3,axis=-1) for a in (near,render(2),far)],axis=1)
            Image.fromarray(np.uint8(np.clip(preview,0,1)*255)).save(artifact_path('water-ripples-preview.png'))
            print(f'PASS: irregular spectrum ({concentration:.3f}), unit normals, distance filtering, motion, all speed wraps and switches')
        finally:
            for program in programs: gl.delete_program(program)
            target.close()


if __name__=='__main__': main()
