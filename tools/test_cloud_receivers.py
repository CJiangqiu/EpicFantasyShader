"""对普通地形和远景地形的实际片元入口验证云影接收。"""
from artifact_paths import artifact_path

import ctypes as c

import numpy as np
from PIL import Image

from gl_context import GLContext
from test_clouds import CloudScene
from validate_shaders import ROOT, SHADERS, configure, expand


VERTEX = '''#version 330 compatibility
out vec2 texcoord;
out vec2 lightcoord;
out vec4 vertexColor;
out vec3 playerPosition;
out vec3 worldNormal;
out float viewDepth;
flat out int material;
uniform vec3 testCamera;
uniform float testHeight;
void main() {
    vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
    gl_Position = vec4(p * 2.0 - 1.0, 0, 1);
    texcoord = p;
    lightcoord = vec2(0.5,15.5)/16.0;
    vertexColor = vec4(1);
    playerPosition = vec3((p.x-0.5)*4096.0, testHeight-testCamera.y, (p.y-0.5)*4096.0);
    worldNormal = vec3(0,1,0);
    viewDepth = length(playerPosition);
    material = 0;
}
'''


def main():
    with GLContext() as gl:
        scene = CloudScene(gl)
        programs = []
        try:
            # 共用测试纹理、渲染目标和初始状态，实际绘制使用各自的片元入口。
            scene.render(background=(1,1,1))

            def render(entry, enabled=True, highland=0.0, height=64, seconds=0):
                source = configure(expand(SHADERS/'world0'/entry),
                                   {'SHADOWS':None,'CLOUD_SHADOWS':str(int(enabled)), 'FOG_DENSITY':'0.0'})
                program = gl.program(VERTEX,source)
                programs.append(program)
                gl.function('glUseProgram',None,c.c_uint)(program)
                location = gl.function('glGetUniformLocation',c.c_int,c.c_uint,c.c_char_p)
                def scalar(name,value):
                    gl.function('glUniform1f',None,c.c_int,c.c_float)(location(program,name.encode()),value)
                for name,value in [('far',8192),('cloudHumidity',0.5),('cloudHighland',highland),
                                   ('frameTimeCounter',seconds),('testHeight',height)]:
                    scalar(name,value)
                for name,value in [('sunPosition',(0.4,1,0.2)),('shadowLightPosition',(0.4,1,0.2)),
                                   ('cameraPosition',(3970,238,4869)),('testCamera',(3970,238,4869))]:
                    gl.function('glUniform3f',None,c.c_int,c.c_float,c.c_float,c.c_float)(location(program,name.encode()),*value)
                identity = np.eye(4,dtype=np.float32)
                gl.function('glUniformMatrix4fv',None,c.c_int,c.c_int,c.c_ubyte,c.c_void_p)(
                    location(program,b'gbufferModelViewInverse'),1,0,identity.ctypes.data_as(c.c_void_p))
                gl.function('glUniform1i',None,c.c_int,c.c_int)(location(program,b'gtexture'),0)
                scene.update_cloud_shadow(camera=(3970,238,4869),highland=highland,seconds=seconds,
                                          options={'CLOUD_SHADOWS':str(int(enabled))})
                gl.function('glDrawArrays',None,c.c_uint,c.c_int,c.c_int)(0x0004,0,3)
                pixels = np.empty((scene.size,scene.size,4),np.float32)
                gl.function('glReadPixels',None,c.c_int,c.c_int,c.c_int,c.c_int,c.c_uint,c.c_uint,c.c_void_p)(
                    0,0,scene.size,scene.size,0x1908,0x1406,pixels.ctypes.data_as(c.c_void_p))
                assert gl.function('glGetError',c.c_uint)() == 0
                assert np.isfinite(pixels).all()
                return pixels[...,:3]

            previews = []
            for highland in (0.0,1.0):
                near = render('gbuffers_terrain.fsh',highland=highland)
                distant = render('dh_terrain.fsh',highland=highland)
                plain = render('dh_terrain.fsh',False,highland=highland)
                assert np.allclose(near,distant,atol=1e-5), '普通与远景地形应在同一世界位置接收同一片云影'
                ratio = distant[...,0]/plain[...,0]
                assert ratio.min() < 0.4 and ratio.max() > 0.99
                assert np.mean(ratio<0.8)>0.01, '高原稀疏云也须产生有对比度的投影'
                assert np.mean(abs(distant-render('dh_terrain.fsh',highland=highland,seconds=60)))>0.005
                above = render('dh_terrain.fsh',height=700)
                assert np.allclose(above,render('dh_terrain.fsh',False,height=700),atol=1e-5)
                print('PASS:', 'highland' if highland else 'normal', 'terrain/DH equality; shadow range',float(ratio.min()),float(ratio.max()))
                previews.extend([plain,distant])
            preview = np.concatenate(previews,axis=1)
            preview = preview/(1+preview)
            Image.fromarray(np.uint8(preview[::-1]**(1/2.2)*255)).save(artifact_path('cloud-receivers-preview.png'))
        finally:
            for program in programs:
                gl.delete_program(program)
            scene.close()


if __name__ == '__main__':
    main()
