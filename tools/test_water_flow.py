"""验证坡面及垂直水幕的重力方向、波动与稀疏白沫。"""
from artifact_paths import artifact_path
import ctypes as c
import numpy as np
from PIL import Image
from gl_context import GLContext
from test_clouds import CloudScene
from test_sky_background import VERTEX
from validate_shaders import ROOT, SHADERS, expand


def main():
    fragment='#version 330 compatibility\n'+expand(SHADERS/'lib/settings.glsl')+expand(SHADERS/'lib/water_waves.glsl')+'''
in vec2 texcoord;
uniform vec3 testNormal;
uniform vec3 testOffset;
layout(location=0) out vec4 scene;
void main() {
    vec3 across=abs(testNormal.y)>0.99 ? vec3(1,0,0) : normalize(cross(testNormal,vec3(0,1,0)));
    vec3 along=cross(across,testNormal);
    vec3 world=(across*texcoord.x+along*texcoord.y)*8.0+testOffset;
    vec3 n=waterWaveNormal(world,testNormal,8.0);
    scene=vec4(n*0.5+0.5,waterFlowFoam(world,testNormal,8.0));
}
'''
    with GLContext() as gl:
        target=CloudScene(gl,128)
        program=gl.program(VERTEX,fragment)
        try:
            gl.function('glUseProgram',None,c.c_uint)(program)
            locate=gl.function('glGetUniformLocation',c.c_int,c.c_uint,c.c_char_p)
            def render(normal,seconds=0,offset=(0,0,0)):
                for name,value in [('testNormal',normal),('testOffset',offset)]:
                    gl.function('glUniform3f',None,c.c_int,c.c_float,c.c_float,c.c_float)(locate(program,name.encode()),*value)
                gl.function('glUniform1f',None,c.c_int,c.c_float)(locate(program,b'frameTimeCounter'),seconds)
                gl.function('glDrawArrays',None,c.c_uint,c.c_int,c.c_int)(0x0004,0,3)
                image=np.empty((128,128,4),np.float32)
                gl.function('glReadPixels',None,c.c_int,c.c_int,c.c_int,c.c_int,c.c_uint,c.c_uint,c.c_void_p)(0,0,128,128,0x1908,0x1406,image.ctypes.data_as(c.c_void_p))
                assert np.isfinite(image).all()
                return image
            previews=[]
            for normal in [(0,1,0),(.6,.8,0),(1,0,0),(0,0,1)]:
                still=render(normal)
                moving=render(normal,2)
                assert np.mean(abs(still-moving))>.001
                assert np.allclose(still,render(normal,3600),atol=1e-5)
                if normal[1]<.9:
                    n=np.array(normal,dtype=float)
                    flow=np.array([0,-1,0])+n*n[1]
                    flow/=np.linalg.norm(flow)
                    carried=render(normal,2,flow*(2*600*2*np.pi/3600))
                    assert np.allclose(still[...,:3],carried[...,:3],atol=1e-5), '波纹必须沿坡面下行'
                if normal[1]==0:
                    assert 0<still[...,3].mean()<.025 and still[...,3].max()<.12, '水幕白沫必须稀疏'
                else:
                    assert still[...,3].max()==0, '平静顶面不产生落水白沫'
                previews.append(np.concatenate([still[...,:3],moving[...,:3]],axis=1))
            Image.fromarray(np.uint8(np.clip(np.concatenate(previews,axis=0),0,1)*255)).save(artifact_path('water-flow-normal-preview.png'))
            print('PASS: downhill and waterfall motion, clock wrap, sparse foam and top-surface isolation')
        finally:
            gl.delete_program(program)
            target.close()


if __name__=='__main__': main()
