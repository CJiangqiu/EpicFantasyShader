"""离线绘制当帧云影附件，模拟准备阶段到几何阶段的资源交接。"""

import ctypes as c

import numpy as np

from test_shadow_filter import FilterScene
from test_sky_background import VERTEX
from validate_shaders import SHADERS, configure, expand


class CloudShadowMap:
    def __init__(self,gl):
        self.gl = gl
        self.programs = {}
        self.target = FilterScene(gl,size=256)
        self.target.bind_texture(self.target.textures[0])
        self.target.upload(None,0x881A,256,0x1908)

    def update(self,camera,light=(0.4,1,0.2),rain=0,storm=0,humidity=0.5,highland=0,seconds=0,options=None):
        gl = self.gl
        options = options or {}
        key = tuple(sorted(options.items()))
        if key not in self.programs:
            self.programs[key] = gl.program(VERTEX,configure(expand(SHADERS/'world0/prepare1.fsh'),options))
        program = self.programs[key]
        gl.function('glBindFramebuffer',None,c.c_uint,c.c_uint)(0x8D40,self.target.fbo)
        gl.function('glViewport',None,c.c_int,c.c_int,c.c_int,c.c_int)(0,0,256,256)
        gl.function('glUseProgram',None,c.c_uint)(program)
        locate = gl.function('glGetUniformLocation',c.c_int,c.c_uint,c.c_char_p)
        for name,value in [('cameraPosition',camera),('shadowLightPosition',light)]:
            gl.function('glUniform3f',None,c.c_int,c.c_float,c.c_float,c.c_float)(locate(program,name.encode()),*value)
        for name,value in [('rainStrength',rain),('thunderStrength',storm),('cloudHumidity',humidity),
                           ('cloudHighland',highland),('frameTimeCounter',seconds)]:
            gl.function('glUniform1f',None,c.c_int,c.c_float)(locate(program,name.encode()),value)
        identity = np.eye(4,dtype=np.float32)
        gl.function('glUniformMatrix4fv',None,c.c_int,c.c_int,c.c_ubyte,c.c_void_p)(
            locate(program,b'gbufferModelViewInverse'),1,0,identity.ctypes.data_as(c.c_void_p))
        gl.function('glDrawArrays',None,c.c_uint,c.c_int,c.c_int)(0x0004,0,3)

    def bind(self,program):
        gl = self.gl
        gl.function('glActiveTexture',None,c.c_uint)(0x84C0+14)
        self.target.bind_texture(self.target.textures[0])
        location = gl.function('glGetUniformLocation',c.c_int,c.c_uint,c.c_char_p)(program,b'colortex7')
        gl.function('glUniform1i',None,c.c_int,c.c_int)(location,14)

    def close(self):
        for program in self.programs.values():
            self.gl.delete_program(program)
        self.target.close()
