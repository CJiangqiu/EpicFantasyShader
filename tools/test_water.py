"""验证实际水面入口的水深、群系色、远景深度与透明材质隔离。"""
from artifact_paths import artifact_path
import ctypes as c
import numpy as np
from PIL import Image
from gl_context import GLContext
from test_clouds import CloudScene
from validate_shaders import ROOT, SHADERS, expand, configure

VERTEX = '''#version 330 compatibility
out vec2 texcoord;
out vec2 lightcoord;
out vec4 vertexColor;
out vec3 playerPosition;
out vec3 worldNormal;
out float viewDepth;
flat out int material;
flat out int waterMaterial;
uniform int testWater;
uniform float testOffset;
uniform int testAbove;
void main() {
    vec2 p=vec2((gl_VertexID<<1)&2, gl_VertexID&2);
    gl_Position=vec4(p*2.0-1.0,0,1);
    texcoord=p;
    lightcoord=vec2(0.5,15.5)/16.0;
    vertexColor=vec4(1);
    playerPosition=vec3((p.x*2.0-1.0)*10.0,-5.0,-(p.y*2.0-1.0)*10.0);
    playerPosition.x+=testOffset;
    worldNormal=vec3(0,1,0);
    if (testAbove==1) { playerPosition.y=5.0; worldNormal=vec3(0,-1,0); }
    viewDepth=5.0;
    material=testWater==1?10001:0;
    waterMaterial=testWater;
}
'''

def main():
    with GLContext() as gl:
        scene=CloudScene(gl,128)
        scene.render(background=(1,1,1))
        programs={}
        coverage_texture=c.c_uint()
        gl.function('glGenTextures',None,c.c_int,c.POINTER(c.c_uint))(1,c.byref(coverage_texture))
        scene.target.bind_texture(scene.target.textures[1])
        scene.target.upload(None,0x8814,scene.size,0x1908)
        gl.function('glFramebufferTexture2D',None,c.c_uint,c.c_uint,c.c_uint,c.c_uint,c.c_int)(0x8D40,0x8CE1,0x0DE1,scene.target.textures[1],0)
        attachments=(c.c_uint*2)(0x8CE0,0x8CE1)
        try:
            def render(depth=2.0, distant=None, biome=(0,0), dh=False, water=1, eye=0, waves=0, foam=0, seconds=0, reflections=0, bank=False, offset=0, far_distance=1000, coverage=None, blend=False, clear=True, above=False):
                key=(dh,waves,foam,reflections)
                if key not in programs:
                    source=expand(SHADERS/'world0'/('dh_water.fsh' if dh else 'gbuffers_water.fsh'))
                    source=source.replace('#version 330 compatibility','#version 330 compatibility\n#define DISTANT_HORIZONS')
                    source=configure(source,{'SHADOWS':None,'CLOUD_SHADOWS':'0','FOG_DENSITY':'0.0','WATER_WAVES':str(waves),'WATER_FOAM':str(foam),'WATER_REFLECTIONS':str(reflections)})
                    programs[key]=gl.program(VERTEX,source)
                program=programs[key]
                gl.function('glUseProgram',None,c.c_uint)(program)
                location=gl.function('glGetUniformLocation',c.c_int,c.c_uint,c.c_char_p)
                def scalar(name,value):
                    gl.function('glUniform1f',None,c.c_int,c.c_float)(location(program,name.encode()),value)
                for name,value in [('viewWidth',scene.size),('viewHeight',scene.size),('far',far_distance),('testOffset',offset),('waterOcean',biome[0]),('waterRiver',biome[1]),('frameTimeCounter',seconds)]:
                    scalar(name,value)
                for name,value in [('testWater',water),('testAbove',int(above)),('isEyeInWater',eye),('gtexture',0),('colortex5',0)]:
                    gl.function('glUniform1i',None,c.c_int,c.c_int)(location(program,name.encode()),value)
                for name in ('sunPosition','shadowLightPosition'):
                    gl.function('glUniform3f',None,c.c_int,c.c_float,c.c_float,c.c_float)(location(program,name.encode()),0,0,1)
                for name,matrix in [('gbufferProjection',[[.1,0,0,0],[0,.1,0,0],[0,0,-1/64,0],[0,0,0,1]]),('gbufferModelViewInverse',[[1,0,0,offset],[0,0,1,0],[0,-1,0,0],[0,0,0,1]]),
                                    ('gbufferProjectionInverse',[[10,0,0,0],[0,10,0,0],[0,0,-64,0],[0,0,0,1]]),
                                    ('dhProjectionInverse',[[10,0,0,0],[0,10,0,0],[0,0,-128,0],[0,0,0,1]])]:
                    data=np.ascontiguousarray(np.array(matrix,dtype=np.float32).T)
                    gl.function('glUniformMatrix4fv',None,c.c_int,c.c_int,c.c_ubyte,c.c_void_p)(location(program,name.encode()),1,0,data.ctypes.data_as(c.c_void_p))
                for unit,name,value,scale in [(1,'depthtex1',depth,128),(2,'dhDepthTex1',distant,256)]:
                    gl.function('glActiveTexture',None,c.c_uint)(0x84C0+unit)
                    scene.target.bind_texture(scene.textures[unit])
                    pixels=np.full((scene.size,scene.size),1.0 if value is None else 0.5+(5+value)/scale,np.float32)
                    if bank and value is not None: pixels[:,64:]=0.5+4.8/scale
                    scene.target.upload(pixels,0x822E,scene.size,0x1903)
                    gl.function('glUniform1i',None,c.c_int,c.c_int)(location(program,name.encode()),unit)
                gl.function('glActiveTexture',None,c.c_uint)(0x84C0+3)
                scene.target.bind_texture(coverage_texture)
                coverage_pixels=np.zeros((scene.size,scene.size,4),np.float32) if coverage is None else coverage
                scene.target.upload(coverage_pixels,0x8814,scene.size,0x1908)
                scene.target.parameter(0x2801,0x2600)
                scene.target.parameter(0x2800,0x2600)
                gl.function('glUniform1i',None,c.c_int,c.c_int)(location(program,b'colortex6'),3)
                gl.function('glDrawBuffers',None,c.c_int,c.POINTER(c.c_uint))(2 if dh else 1,attachments)
                gl.function('glEnable' if blend else 'glDisable',None,c.c_uint)(0x0BE2)
                gl.function('glBlendFuncSeparate',None,c.c_uint,c.c_uint,c.c_uint,c.c_uint)(0x0302,0x0303,1,0x0303)
                gl.function('glDisablei',None,c.c_uint,c.c_uint)(0x0BE2,1)
                gl.function('glClearColor',None,c.c_float,c.c_float,c.c_float,c.c_float)(0,0,0,0)
                if clear: gl.function('glClear',None,c.c_uint)(0x4000)
                gl.function('glDrawArrays',None,c.c_uint,c.c_int,c.c_int)(0x0004,0,3)
                pixels=np.empty((scene.size,scene.size,4),np.float32)
                gl.function('glReadPixels',None,c.c_int,c.c_int,c.c_int,c.c_int,c.c_uint,c.c_uint,c.c_void_p)(0,0,scene.size,scene.size,0x1908,0x1406,pixels.ctypes.data_as(c.c_void_p))
                assert gl.function('glGetError',c.c_uint)()==0 and np.isfinite(pixels).all()
                return pixels
            # 两次真实透明混合模拟 DH 先绘制、普通水后绘制。
            for offset in (0,8,15.5,15.9,16,16.1,16.5,24,40):
                single=render(depth=8,distant=8,offset=offset,far_distance=80)
                expected=single.copy()
                expected[...,:3]*=single[...,3:]
                render(depth=8,distant=8,offset=offset,far_distance=80,dh=True,blend=True)
                gl.function('glReadBuffer',None,c.c_uint)(0x8CE1)
                mask=np.empty_like(single)
                gl.function('glReadPixels',None,c.c_int,c.c_int,c.c_int,c.c_int,c.c_uint,c.c_uint,c.c_void_p)(0,0,scene.size,scene.size,0x1908,0x1406,mask.ctypes.data_as(c.c_void_p))
                gl.function('glReadBuffer',None,c.c_uint)(0x8CE0)
                combined=render(depth=8,distant=8,offset=offset,far_distance=80,coverage=mask,blend=True,clear=False)
                assert np.allclose(combined,expected,atol=2e-5), '跨越交接边界时只能混合一层水'
            assert render(depth=8,dh=True,far_distance=80).max()==0, '有精细水底的近景排除远景水'
            assert render(depth=None,distant=8,dh=True,far_distance=80)[...,3].min()>0, '缺少精细地形时保留远景水补位'
            mask=np.zeros((scene.size,scene.size,4),np.float32)
            mask[:]=[5,-5,1,1]
            assert render(depth=8,coverage=mask).max()==0
            assert render(depth=8,coverage=mask,water=0)[...,3].min()>.99, '其他透明材质不受水面标记影响'
            mask[...,1]=-7
            assert render(depth=8,coverage=mask)[...,3].min()>0, '不同高度的水面不能误判成重叠'
            assert np.allclose(render(depth=None,distant=None,eye=1,above=True)[...,3],1.0), '水下无实体遮挡的天空必须在水面处完成透射合成'
            interface=render(depth=None,distant=None,eye=1,above=True,waves=1,reflections=1)
            assert interface[64,64,:3].mean()>interface[5,5,:3].mean()+.08, '水下反射随视角增强'
            assert interface[...,:3].min()>.35, '斜视水面仍须保留水上景物的透射'
            assert np.mean(abs(interface-render(depth=None,distant=None,eye=1,above=True,waves=1,reflections=1,seconds=2)))>.0003, '水面背面必须呈现动态波纹'
            Image.fromarray(np.uint8(np.clip(interface[...,:3],0,1)**(1/2.2)*255)).save(artifact_path('water-underside-preview.png'))
            # 斜视区域的彩色背景用于验证透射保留了景物轮廓，而非只透出纯色天空。
            snapshot=np.ones((scene.size,scene.size,4),np.float32)
            snapshot[:,:,:3]=[.04,.12,.4]
            snapshot[:,4:20,:3]=[.8,.05,.02]
            gl.function('glActiveTexture',None,c.c_uint)(0x84C0)
            scene.target.bind_texture(scene.textures[0])
            scene.target.upload(snapshot,0x8814,scene.size,0x1908)
            outlined=render(depth=None,distant=None,eye=1,above=True,reflections=1)
            assert outlined[8,10,0]>outlined[8,25,0]+.3, '斜视必须看见水上景物的颜色轮廓'
            assert np.allclose(outlined,render(depth=None,distant=None,eye=1,above=True,reflections=1,dh=True),atol=1e-5)
            gl.function('glActiveTexture',None,c.c_uint)(0x84C0)
            scene.target.bind_texture(scene.textures[0])
            scene.target.upload(np.ones_like(snapshot),0x8814,scene.size,0x1908)
            previews=[]
            for biome in [(1,0),(0,1),(0,0)]:
                frames=[render(depth=d,biome=biome) for d in [0.5,2,2.1,4,8,16,32]]
                alpha=[f[...,3].mean() for f in frames]
                assert alpha[0]<0.02 and alpha[1]<0.02
                assert np.min(np.diff(alpha))>=-1e-6 and alpha[-1]>0.95
                assert alpha[2]-alpha[1]<0.003
                for d in (2,8,32):
                    assert np.allclose(render(depth=d,biome=biome),render(depth=None,distant=d,biome=biome,dh=True),atol=1e-5)
                a=frames[-1][64,64,:3]
                if biome==(1,0): assert a[2]>a[1]>a[0]
                if biome==(0,1): assert a[1]>a[0] and a[1]>a[2]
                previews.append(np.concatenate([f[...,:3]*f[...,3:]+0.45*(1-f[...,3:]) for f in frames],axis=1))
            assert np.allclose(render(depth=2,distant=16),render(depth=2),atol=1e-5)
            assert np.allclose(render(depth=16,distant=2),render(depth=16),atol=1e-5)
            assert np.allclose(render(depth=None,distant=None),render(depth=24),atol=1e-5)
            assert render(depth=-1,dh=True).max()==0
            assert render(water=0)[...,3].min()>0.99
            assert render(water=0,dh=True)[...,3].min()>0.99
            assert np.allclose(render(depth=32,eye=1)[...,3],0.015)
            ripple=render(depth=2,waves=1)
            moving=render(depth=2,waves=1,seconds=2)
            assert np.mean(abs(ripple-moving))>0.001, '波面高光必须随时间流动'
            assert np.allclose(ripple[...,3],0.015), '波纹不得染浑浅水'
            assert np.allclose(render(depth=0.5,foam=1),render(depth=0.5)), '平坦浅滩不应覆盖泡沫'
            shore=render(depth=0.5,foam=1,bank=True)
            assert shore[...,3].max()>0.1 and shore[...,3].min()<0.02
            assert np.mean(abs(shore-render(depth=0.5,foam=1,seconds=2,bank=True)))>0.0001
            assert np.allclose(render(depth=4,foam=1),render(depth=4)), '深水不产生岸边浪花'
            assert np.allclose(render(depth=0.5,foam=1,eye=1),render(depth=0.5,eye=1)), '水内不显示水面浪花'
            assert np.allclose(render(depth=0.5,foam=1,waves=1),render(depth=None,distant=0.5,foam=1,waves=1,dh=True),atol=1e-5)
            assert np.allclose(render(depth=0.5,foam=1,waves=1,seconds=3600),render(depth=0.5,foam=1,waves=1),atol=1e-5)
            reflective=render(depth=2,waves=1,reflections=1)
            assert reflective[...,3].mean()>ripple[...,3].mean(), '反射必须参与能量与透明度合成'
            assert np.allclose(render(depth=2,reflections=1,eye=1),render(depth=2,eye=1))
            u,v=np.meshgrid(np.arange(scene.size),np.arange(scene.size))
            bed=np.where(((u//12+v//12)%2)[...,None]==0,0.24,0.4)
            frames=[render(depth=d,foam=1,waves=1) for d in (0.25,0.75,2.0,8.0)]
            appearance=np.concatenate([f[...,:3]*f[...,3:]+bed*(1-f[...,3:]) for f in frames],axis=1)
            Image.fromarray(np.uint8(np.clip(appearance,0,1)**(1/2.2)*255)).save(artifact_path('water-waves-preview.png'))
            fog_source = '#version 330 compatibility\n' + expand(SHADERS/'lib/water_color.glsl') + '\nin vec2 texcoord;\nlayout(location=0) out vec4 scene;\nvoid main() { scene=vec4(underwaterFog(vec3(0.8),texcoord.x*40.0),1); }\n'
            fog_program = gl.program(VERTEX,fog_source)
            programs['fog'] = fog_program
            gl.function('glUseProgram',None,c.c_uint)(fog_program)
            location = gl.function('glGetUniformLocation',c.c_int,c.c_uint,c.c_char_p)
            gl.function('glUniform1f',None,c.c_int,c.c_float)(location(fog_program,b'waterOcean'),1)
            gl.function('glDrawArrays',None,c.c_uint,c.c_int,c.c_int)(0x0004,0,3)
            fog_pixels=np.empty((scene.size,scene.size,4),np.float32)
            gl.function('glReadPixels',None,c.c_int,c.c_int,c.c_int,c.c_int,c.c_uint,c.c_uint,c.c_void_p)(0,0,scene.size,scene.size,0x1908,0x1406,fog_pixels.ctypes.data_as(c.c_void_p))
            assert np.allclose(fog_pixels[:,:6,:3],0.8), '近距离水下视野须清澈'
            assert np.max(np.diff(fog_pixels[64,:,:3],axis=0))<1e-5, '水雾应随距离连续吸收'
            assert fog_pixels[64,-1,2]>fog_pixels[64,-1,0]
            preview=np.concatenate(previews,axis=0)
            Image.fromarray(np.uint8(np.clip(preview,0,1)**(1/2.2)*255)).save(artifact_path('water-depth-preview.png'))
            print('PASS: two-pass water handoff, moving boundary, missing chunks, material/height isolation; shallow threshold, continuous deep absorption, ocean/river colors, ordinary/DH equality, nearest depth, missing bottom and material isolation')
        finally:
            for p in programs.values(): gl.delete_program(p)
            gl.function('glDeleteTextures',None,c.c_int,c.POINTER(c.c_uint))(1,c.byref(coverage_texture))
            scene.close()

if __name__=='__main__': main()
