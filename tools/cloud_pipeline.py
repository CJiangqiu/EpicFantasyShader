"""模拟半分辨率云附件及全分辨率合成前的加载器资源交接。"""

import ctypes as c

from test_shadow_filter import FilterScene
from test_sky_background import VERTEX
from validate_shaders import SHADERS, configure, expand


def copy_uniforms(gl,source,target):
    locate = gl.function('glGetUniformLocation',c.c_int,c.c_uint,c.c_char_p)
    scalar = ('rainStrength','thunderStrength','cloudHumidity','cloudHighland','frameTimeCounter','cloudLightningPulse')
    vectors = ('cameraPosition','sunPosition','fogColor','skyColor')
    matrices = ('gbufferProjectionInverse','gbufferModelViewInverse','dhProjectionInverse')
    for names,count in ((scalar,1),(vectors,3),(('lightningBoltPosition',),4),(matrices,16)):
        for name in names:
            a,b = locate(source,name.encode()),locate(target,name.encode())
            if a<0 or b<0: continue
            data = (c.c_float*count)()
            gl.function('glGetUniformfv',None,c.c_uint,c.c_int,c.POINTER(c.c_float))(source,a,data)
            if count==16:
                gl.function('glUniformMatrix4fv',None,c.c_int,c.c_int,c.c_ubyte,c.POINTER(c.c_float))(b,1,0,data)
            else:
                gl.function('glUniform'+str(count)+'fv',None,c.c_int,c.c_int,c.POINTER(c.c_float))(b,1,data)
    for name in ('depthtex0','dhDepthTex0','noisetex','isEyeInWater'):
        a,b = locate(source,name.encode()),locate(target,name.encode())
        if a<0 or b<0: continue
        value = c.c_int()
        gl.function('glGetUniformiv',None,c.c_uint,c.c_int,c.POINTER(c.c_int))(source,a,c.byref(value))
        gl.function('glUniform1i',None,c.c_int,c.c_int)(b,value.value)


class CloudPipeline:
    def __init__(self,gl,size):
        self.gl, self.size = gl,max(1,size//2)
        self.programs = {}
        self.target = FilterScene(gl,self.size)
        for index,internal,fmt in ((0,0x881A,0x1908),(1,0x822E,0x1903)):
            self.target.bind_texture(self.target.textures[index])
            self.target.upload(None,internal,self.size,fmt)
            for name,value in ((0x2801,0x2600),(0x2800,0x2600),(0x884C,0)):
                self.target.parameter(name,value)
            gl.function('glFramebufferTexture2D',None,c.c_uint,c.c_uint,c.c_uint,c.c_uint,c.c_int)(
                0x8D40,0x8CE0+index,0x0DE1,self.target.textures[index],0)
        attachments = (c.c_uint*2)(0x8CE0,0x8CE1)
        gl.function('glDrawBuffers',None,c.c_int,c.POINTER(c.c_uint))(2,attachments)
        assert gl.function('glCheckFramebufferStatus',c.c_uint,c.c_uint)(0x8D40)==0x8CD5

    def render(self,source,options,dh):
        gl = self.gl
        key = (tuple(sorted(options.items())),dh)
        if key not in self.programs:
            text = expand(SHADERS/'world0/deferred.fsh')
            if dh: text = text.replace('#version 330 compatibility','#version 330 compatibility\n#define DISTANT_HORIZONS')
            self.programs[key] = gl.program(VERTEX,configure(text,options))
        target = self.programs[key]
        gl.function('glBindFramebuffer',None,c.c_uint,c.c_uint)(0x8D40,self.target.fbo)
        gl.function('glViewport',None,c.c_int,c.c_int,c.c_int,c.c_int)(0,0,self.size,self.size)
        gl.function('glUseProgram',None,c.c_uint)(target)
        copy_uniforms(gl,source,target)
        gl.function('glDrawArrays',None,c.c_uint,c.c_int,c.c_int)(0x0004,0,3)

    def bind(self,program):
        gl = self.gl
        for index,unit in ((0,12),(1,13)):
            gl.function('glActiveTexture',None,c.c_uint)(0x84C0+unit)
            self.target.bind_texture(self.target.textures[index])
            location = gl.function('glGetUniformLocation',c.c_int,c.c_uint,c.c_char_p)(program,('colortex'+str(index+1)).encode())
            gl.function('glUniform1i',None,c.c_int,c.c_int)(location,unit)

    def close(self):
        for program in self.programs.values(): self.gl.delete_program(program)
        self.target.close()
