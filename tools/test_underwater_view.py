"""验证水面终止水雾距离，以及近处地形焦散的光照约束。"""
from artifact_paths import artifact_path
import ctypes as c
import numpy as np
from PIL import Image
from gl_context import GLContext
from test_clouds import CloudScene
from test_sky_background import VERTEX
from validate_shaders import ROOT, SHADERS, expand, configure


def main():
    with GLContext() as gl:
        scene=CloudScene(gl,128)
        programs={}
        try:
            def render(mode='view',distance=3,dh=False,eye=1,seconds=0,night=False,sky=1,enabled=1,waves=1,strength=1,speed=1):
                key=(mode,enabled,waves,strength,speed)
                if key not in programs:
                    if mode=='view':
                        source=configure(expand(SHADERS/'world0/final.fsh'),{'WATER_LIGHT_SHAFTS':'0'}).replace('#version 330 compatibility','#version 330 compatibility\n#define DISTANT_HORIZONS')
                    else:
                        source='#version 330 compatibility\n#define WORLD_OVERWORLD\n#define TERRAIN_AO\n'
                        source+=expand(SHADERS/'lib/settings.glsl')+expand(SHADERS/'lib/lighting.glsl')+'''
in vec2 texcoord;
uniform float testSky;
layout(location=0) out vec4 outputColor;
void main() {
    vec3 position=vec3((texcoord.x-0.5)*16,-3,(texcoord.y-0.5)*16);
    outputColor=vec4(surfaceLighting(position,vec3(0,1,0),vec2(0.5,0.5+testSky*15.0)/16.0,1.0)*0.25,1);
}
'''
                        source=configure(source,{'SHADOWS':None,'CLOUD_SHADOWS':'0','WATER_CAUSTICS':str(enabled),'WATER_WAVES':str(waves),'WATER_WAVE_STRENGTH':str(float(strength)),'WATER_WAVE_SPEED':str(float(speed))})
                    programs[key]=gl.program(VERTEX,source)
                p=programs[key]
                gl.function('glUseProgram',None,c.c_uint)(p)
                def loc(name): return gl.function('glGetUniformLocation',c.c_int,c.c_uint,c.c_char_p)(p,name.encode())
                gl.function('glUniform1i',None,c.c_int,c.c_int)(loc('isEyeInWater'),eye)
                for name,value in [('frameTimeCounter',seconds),('testSky',sky)]:
                    gl.function('glUniform1f',None,c.c_int,c.c_float)(loc(name),value)
                for name,value in [('sunPosition',(0,-1 if night else 1,0)),('shadowLightPosition',(0,1,0)),('cameraPosition',(0,64,0))]:
                    gl.function('glUniform3f',None,c.c_int,c.c_float,c.c_float,c.c_float)(loc(name),*value)
                for name,m in [('gbufferModelViewInverse',np.eye(4)),('gbufferProjectionInverse',np.diag([1,1,100,1])),('dhProjectionInverse',np.diag([1,1,200,1]))]:
                    data=np.ascontiguousarray(m.T,dtype=np.float32)
                    gl.function('glUniformMatrix4fv',None,c.c_int,c.c_int,c.c_ubyte,c.c_void_p)(loc(name),1,0,data.ctypes.data_as(c.c_void_p))
                for unit,name,value in [(0,'colortex0',.5),(1,'depthtex0',1 if dh else .5+distance/200),(2,'dhDepthTex0',.5+distance/400 if dh else 1)]:
                    gl.function('glActiveTexture',None,c.c_uint)(0x84C0+unit)
                    scene.target.bind_texture(scene.textures[unit])
                    pixels=np.full((128,128,4) if unit==0 else (128,128),value,np.float32)
                    scene.target.upload(pixels,0x8814 if unit==0 else 0x822E,128,0x1908 if unit==0 else 0x1903)
                    scene.target.parameter(0x2801,0x2600)
                    scene.target.parameter(0x2800,0x2600)
                    gl.function('glUniform1i',None,c.c_int,c.c_int)(loc(name),unit)
                gl.function('glDrawArrays',None,c.c_uint,c.c_int,c.c_int)(0x0004,0,3)
                image=np.empty((128,128,4),np.float32)
                gl.function('glReadPixels',None,c.c_int,c.c_int,c.c_int,c.c_int,c.c_uint,c.c_uint,c.c_void_p)(0,0,128,128,0x1908,0x1406,image.ctypes.data_as(c.c_void_p))
                assert np.isfinite(image).all() and gl.function('glGetError',c.c_uint)()==0
                return image[...,:3]
            short=render(distance=3)
            long=render(distance=80)
            air=render(eye=0)
            assert np.allclose(short,air,atol=1e-5), '三格穿水距离不能把水上景物压黑'
            assert long.mean()<short.mean()*.35, '持续在水中的长视线仍须受到吸收'
            assert np.allclose(short,render(distance=3,dh=True),atol=1e-5)
            assert np.allclose(render(distance=3,eye=0),render(distance=80,eye=0))
            base=render(mode='light',enabled=0)
            lit=render(mode='light')
            moved=render(mode='light',seconds=2)
            assert (lit-base).max()>.05 and (lit-base).min()>=-1e-6
            assert np.mean(abs(lit-moved))>.005
            assert np.allclose(render(mode='light',waves=0),base,atol=1e-5), '关闭波纹时不得保留独立焦散'
            assert np.allclose(render(mode='light',strength=0),base,atol=1e-5), '平静水面不得产生聚光纹理'
            assert np.allclose(render(mode='light',speed=0),render(mode='light',speed=0,seconds=2)), '波面冻结时焦散必须同步冻结'
            for kwargs in ({'eye':0},{'night':True},{'sky':0}):
                assert np.allclose(render(mode='light',**kwargs),render(mode='light',enabled=0,**kwargs))
            preview=np.concatenate([base,lit,moved],axis=1)
            Image.fromarray(np.uint8(np.clip(preview,0,1)**(1/2.2)*255)).save(artifact_path('water-caustics-preview.png'))
            print('PASS: water-interface fog distance, DH reconstruction, air isolation, animated caustics and daylight/sky-access limits')
        finally:
            for p in programs.values(): gl.delete_program(p)
            scene.close()


if __name__=='__main__': main()
