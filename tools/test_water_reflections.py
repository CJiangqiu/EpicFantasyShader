"""用透视岸壁场景验证倒影、波面运动、快照及远景深度。"""
from artifact_paths import artifact_path
import ctypes as c
import numpy as np
from PIL import Image
from gl_context import GLContext
from test_clouds import CloudScene
from test_sky_background import VERTEX
from validate_shaders import ROOT, SHADERS, expand, configure


def main():
    size=256
    x,y=np.meshgrid((np.arange(size)+0.5)/size*2-1,(np.arange(size)+0.5)/size*2-1)
    model=np.array([[1,0,0,0],[0,.98,.2,0],[0,-.2,.98,0],[0,0,0,1]],np.float32)
    model[:3,:3] /= np.linalg.norm(model[:3,:3],axis=0)
    projection=np.array([[1,0,0,0],[0,1,0,0],[0,0,-1.0008,-.20008],[0,0,-1,0]],np.float32)
    ray=np.stack([x,y,-np.ones_like(x)],axis=-1)@model[:3,:3].T
    floor_time=np.where(ray[...,1]<-.001,-5/ray[...,1],1e6)
    wall_time=-25/ray[...,2]
    wall=ray*wall_time[...,None]
    wall_hit=(abs(wall[...,0])<10)&(wall[...,1]>-5)&(wall[...,1]<12)
    distance=np.minimum(floor_time,np.where(wall_hit,wall_time,1e6))
    points=ray*distance[...,None]
    view=points@model[:3,:3]
    depth=(projection[2,2]*view[...,2]+projection[2,3])/(-view[...,2])*.5+.5
    depth=np.where(distance<256,depth,1).astype(np.float32)
    snapshot=np.ones((size,size,4),np.float32)
    sky=np.stack([.12+y*.025,.28+y*.05,.55+y*.12],axis=-1)
    snapshot[...,:3]=sky
    floor_mask=(floor_time<256)&(floor_time<np.where(wall_hit,wall_time,1e6))
    checker=((np.floor(points[...,0])+np.floor(points[...,2]))%2)*.07
    snapshot[...,:3]=np.where(floor_mask[...,None],np.stack([.24+checker,.19+checker,.10+checker],axis=-1),snapshot[...,:3])
    wall_mask=wall_hit&(wall_time<floor_time)
    snapshot[wall_mask,:3]=np.array([.65,.035,.012])
    source='#version 330 compatibility\n#define WORLD_OVERWORLD\n#define DISTANT_HORIZONS\n'
    source+=expand(SHADERS/'lib/settings.glsl')+expand(SHADERS/'lib/color.glsl')
    source+='\nuniform mat4 gbufferModelViewInverse;\nuniform vec3 shadowLightPosition;\nuniform vec3 fogColor;\nuniform int isEyeInWater;\n'
    source+='\nuniform float far;\n'
    source+=expand(SHADERS/'lib/water_surface.glsl')
    source+='''
in vec2 texcoord;
uniform int testReflection;
layout(location=0) out vec4 scene;
void main() {
    vec4 v=gbufferProjectionInverse*vec4(texcoord*2.0-1.0,1,1);
    vec3 ray=normalize(mat3(gbufferModelViewInverse)*v.xyz/v.w);
    vec3 background=texture(colortex5,texcoord).rgb;
    if (ray.y>=-0.001) { scene=vec4(background,1); return; }
    vec3 position=ray*(-2.0/ray.y);
    vec3 object;
    if (waterScenePoint(texcoord,object) && length(object)<length(position)) { scene=vec4(background,1); return; }
    vec4 water=shadeWater(position,vec3(0,1,0),vec3(1),1.0);
    scene=vec4(water.rgb*water.a+background*(1.0-water.a),1);
    if (testReflection==1) scene=vec4(waterReflection(position,reflect(ray,waterWaveNormal(position,vec3(0,1,0),length(position))),1),1);
}
'''
    with GLContext() as gl:
        scene=CloudScene(gl,size)
        programs={}
        try:
            # 双输出附件模拟加载器映射，验证快照包含云合成后的颜色。
            scene.target.bind_texture(scene.target.textures[1])
            scene.target.upload(None,0x8814,size,0x1908)
            gl.function('glFramebufferTexture2D',None,c.c_uint,c.c_uint,c.c_uint,c.c_uint,c.c_int)(0x8D40,0x8CE1,0x0DE1,scene.target.textures[1],0)
            attachments=(c.c_uint*2)(0x8CE0,0x8CE1)
            gl.function('glDrawBuffers',None,c.c_int,c.POINTER(c.c_uint))(2,attachments)
            combined=scene.render(pitch=40)
            gl.function('glReadBuffer',None,c.c_uint)(0x8CE1)
            copied=np.empty((size,size,4),np.float32)
            gl.function('glReadPixels',None,c.c_int,c.c_int,c.c_int,c.c_int,c.c_uint,c.c_uint,c.c_void_p)(0,0,size,size,0x1908,0x1406,copied.ctypes.data_as(c.c_void_p))
            assert np.allclose(combined,copied[...,:3]), '反射快照必须包含不透明颜色与云层'
            gl.function('glReadBuffer',None,c.c_uint)(0x8CE0)
            gl.function('glDrawBuffers',None,c.c_int,c.POINTER(c.c_uint))(1,attachments)
            assert 'DRAWBUFFERS:05' in (SHADERS/'program/deferred.fsh').read_text('utf-8')
            assert 'uniform sampler2D colortex5;' in (SHADERS/'lib/water_reflections.glsl').read_text('utf-8')
            def render(seconds=0,dh=False,waves=1,reflection_only=0, refraction=1):
                key=(waves,refraction)
                if key not in programs:
                    programs[key]=gl.program(VERTEX,configure(source,{'WATER_WAVES':str(waves),'WATER_FOAM':'0','WATER_REFRACTION':str(refraction)}))
                p=programs[key]
                gl.function('glUseProgram',None,c.c_uint)(p)
                locate=gl.function('glGetUniformLocation',c.c_int,c.c_uint,c.c_char_p)
                def loc(name): return locate(p,name.encode())
                for name,value in [('viewWidth',size),('viewHeight',size),('frameTimeCounter',seconds),('waterRiver',1)]:
                    gl.function('glUniform1f',None,c.c_int,c.c_float)(loc(name),value)
                gl.function('glUniform1i',None,c.c_int,c.c_int)(loc('testReflection'),reflection_only)
                for name,value in [('skyColor',(.4,.58,.8)),('fogColor',(.65,.72,.8)),('shadowLightPosition',(0,1,0))]:
                    gl.function('glUniform3f',None,c.c_int,c.c_float,c.c_float,c.c_float)(loc(name),*value)
                for name,m in [('gbufferProjection',projection),('gbufferProjectionInverse',np.linalg.inv(projection)),('dhProjectionInverse',np.linalg.inv(projection)),('gbufferModelViewInverse',model)]:
                    data=np.ascontiguousarray(m.T,dtype=np.float32)
                    gl.function('glUniformMatrix4fv',None,c.c_int,c.c_int,c.c_ubyte,c.c_void_p)(loc(name),1,0,data.ctypes.data_as(c.c_void_p))
                for unit,name,pixels in [(0,'colortex5',snapshot),(1,'depthtex1',np.ones_like(depth) if dh else depth),(2,'dhDepthTex1',depth if dh else np.ones_like(depth))]:
                    gl.function('glActiveTexture',None,c.c_uint)(0x84C0+unit)
                    scene.target.bind_texture(scene.textures[unit])
                    scene.target.upload(np.ascontiguousarray(pixels),0x8814 if unit==0 else 0x822E,size,0x1908 if unit==0 else 0x1903)
                    for key,val in [(0x2801,0x2601 if unit==0 else 0x2600),(0x2800,0x2601 if unit==0 else 0x2600),(0x2802,0x812F),(0x2803,0x812F)]: scene.target.parameter(key,val)
                    gl.function('glUniform1i',None,c.c_int,c.c_int)(loc(name),unit)
                gl.function('glDrawArrays',None,c.c_uint,c.c_int,c.c_int)(0x0004,0,3)
                pixels=np.empty((size,size,4),np.float32)
                gl.function('glReadPixels',None,c.c_int,c.c_int,c.c_int,c.c_int,c.c_uint,c.c_uint,c.c_void_p)(0,0,size,size,0x1908,0x1406,pixels.ctypes.data_as(c.c_void_p))
                assert np.isfinite(pixels).all() and gl.function('glGetError',c.c_uint)()==0
                return pixels
            still=render(waves=0)
            moving=render()
            later=render(seconds=2)
            unrefracted=render(refraction=0)
            assert np.mean(abs(moving[:100]-unrefracted[:100]))>0.0001, '水后景物必须受到波纹折射'
            assert np.allclose(moving[200:],unrefracted[200:]), '水外画面不能受到折射影响'
            reflection=render(reflection_only=1)
            # 下半屏的红色只能来自岸壁倒影，水底与天空均不含该颜色。
            reflected_red=(reflection[:size//2,:,0]>.4)&(reflection[:size//2,:,1]<.08)
            assert reflected_red.sum()>100, '屏幕空间射线必须命中岸壁'
            assert np.mean(abs(moving[:128]-later[:128]))>.001, '波纹必须移动倒影'
            assert np.allclose(moving,render(dh=True),atol=2e-5), '普通与远景倒影必须一致'
            preview=np.concatenate([still,moving,later],axis=1)[::-1,:,:3]
            Image.fromarray(np.uint8(np.clip(preview,0,1)**(1/2.2)*255)).save(artifact_path('water-reflection-preview.png'))
            print('PASS: perspective shoreline reflection, animated distortion, DH equality, finite output')
        finally:
            for p in programs.values(): gl.delete_program(p)
            scene.close()


if __name__=='__main__': main()
