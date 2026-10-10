"""模拟透明阶段后的半分辨率水下光束附件及最终合成。"""
import ctypes as c
from test_shadow_filter import FilterScene
from test_sky_background import VERTEX
from validate_shaders import SHADERS, expand, configure


class UnderwaterPipeline:
    def __init__(self,gl,size):
        self.gl,self.size=gl,max(1,size//2)
        self.target=FilterScene(gl,self.size)
        self.target.bind_texture(self.target.textures[0])
        self.target.upload(None,0x881A,self.size,0x1908)
        self.programs={}

    def render(self,source,options,dimension):
        gl=self.gl
        key=(tuple(sorted(options.items())),dimension)
        if key not in self.programs:
            text=expand(SHADERS/dimension/'composite.fsh').replace('#version 330 compatibility','#version 330 compatibility\n#define DISTANT_HORIZONS')
            self.programs[key]=gl.program(VERTEX,configure(text,options))
        target=self.programs[key]
        gl.function('glUseProgram',None,c.c_uint)(target)
        loc=gl.function('glGetUniformLocation',c.c_int,c.c_uint,c.c_char_p)
        groups=[(1,('rainStrength','frameTimeCounter')),(3,('cameraPosition','sunPosition')),
                (16,('gbufferModelViewInverse','gbufferProjectionInverse','dhProjectionInverse','shadowModelView','shadowProjection'))]
        for count,names in groups:
            for name in names:
                a,b=loc(source,name.encode()),loc(target,name.encode())
                if a<0 or b<0: continue
                value=(c.c_float*count)()
                gl.function('glGetUniformfv',None,c.c_uint,c.c_int,c.POINTER(c.c_float))(source,a,value)
                if count==16:
                    gl.function('glUniformMatrix4fv',None,c.c_int,c.c_int,c.c_ubyte,c.POINTER(c.c_float))(b,1,0,value)
                else:
                    gl.function('glUniform'+str(count)+'fv',None,c.c_int,c.c_int,c.POINTER(c.c_float))(b,1,value)
        for name in ('isEyeInWater','depthtex0','dhDepthTex0','shadowtex1'):
            a,b=loc(source,name.encode()),loc(target,name.encode())
            if a<0 or b<0: continue
            value=c.c_int()
            gl.function('glGetUniformiv',None,c.c_uint,c.c_int,c.POINTER(c.c_int))(source,a,c.byref(value))
            gl.function('glUniform1i',None,c.c_int,c.c_int)(b,value.value)
        gl.function('glBindFramebuffer',None,c.c_uint,c.c_uint)(0x8D40,self.target.fbo)
        gl.function('glViewport',None,c.c_int,c.c_int,c.c_int,c.c_int)(0,0,self.size,self.size)
        gl.function('glDrawArrays',None,c.c_uint,c.c_int,c.c_int)(0x0004,0,3)
        gl.function('glUseProgram',None,c.c_uint)(source)
        gl.function('glActiveTexture',None,c.c_uint)(0x84C0+4)
        self.target.bind_texture(self.target.textures[0])
        gl.function('glUniform1i',None,c.c_int,c.c_int)(loc(source,b'colortex1'),4)

    def close(self):
        for p in self.programs.values(): self.gl.delete_program(p)
        self.target.close()
