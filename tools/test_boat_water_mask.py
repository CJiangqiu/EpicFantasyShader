"""验证实体程序的只写深度挡水遮罩及透明裁剪，不替代加载器内的船体测试。"""
import ctypes as c
import numpy as np
from gl_context import GLContext
from test_shadow_filter import FilterScene
from test_water import VERTEX
from validate_shaders import SHADERS, configure, expand


def main():
    with GLContext(load_resources=False) as gl:
        target = FilterScene(gl, 32)
        depth = c.c_uint()
        programs = []
        gl.function('glGenRenderbuffers', None, c.c_int, c.POINTER(c.c_uint))(1, c.byref(depth))
        gl.function('glBindRenderbuffer', None, c.c_uint, c.c_uint)(0x8D41, depth.value)
        gl.function('glRenderbufferStorage', None, c.c_uint, c.c_uint, c.c_int, c.c_int)(0x8D41, 0x81A6, 32, 32)
        gl.function('glFramebufferRenderbuffer', None, c.c_uint, c.c_uint, c.c_uint, c.c_uint)(0x8D40, 0x8D00, 0x8D41, depth.value)
        gl.function('glEnable', None, c.c_uint)(0x0B71)
        gl.function('glDepthFunc', None, c.c_uint)(0x0201)
        color_mask = gl.function('glColorMask', None, c.c_ubyte, c.c_ubyte, c.c_ubyte, c.c_ubyte)
        read = gl.function('glReadPixels', None, c.c_int, c.c_int, c.c_int, c.c_int, c.c_uint, c.c_uint, c.c_void_p)
        draw = gl.function('glDrawArrays', None, c.c_uint, c.c_int, c.c_int)
        use = gl.function('glUseProgram', None, c.c_uint)
        loc = gl.function('glGetUniformLocation', c.c_int, c.c_uint, c.c_char_p)
        options = {'SHADOWS':None, 'CLOUD_SHADOWS':'0', 'HANDHELD_LIGHT':None, 'FOG_DENSITY':'0.0'}
        try:
            # 透明贴图模拟深度遮罩绘制时无有效颜色的输入。
            target.bind_texture(target.textures[1])
            target.parameter(0x884C, 0)
            target.upload(np.zeros((1, 1, 4), np.float32), 0x8814, 1, 0x1908)
            water = gl.program(VERTEX.replace('0,1);', '0.2,1);'),
                               '#version 330 compatibility\nlayout(location=0) out vec4 scene; void main(){scene=vec4(0,0,1,1);}')
            programs.append(water)
            for dimension in ('', 'world0', 'world-1', 'world1'):
                for dh in (False, True):
                    entry = SHADERS / dimension / 'gbuffers_entities.fsh'
                    source = configure(expand(entry), options)
                    if dh:
                        source = source.replace('#version 330 compatibility', '#version 330 compatibility\n#define DISTANT_HORIZONS')
                    # 实际入口配对编译，同时使用人工顶点控制遮挡的先后深度。
                    linked = gl.program(configure(expand(entry.with_suffix('.vsh')), options), source)
                    gl.delete_program(linked)
                    for old in (False, True):
                        fragment = source.replace('if (albedo.a < alphaTestRef) discard;', 'if (albedo.a < max(alphaTestRef, 0.001)) discard;') if old else source
                        program = gl.program(VERTEX, fragment)
                        programs.append(program)
                        for threshold in (0.0, 0.1):
                            color_mask(1, 1, 1, 1)
                            gl.function('glClearColor', None, c.c_float, c.c_float, c.c_float, c.c_float)(.4, .2, .1, 1)
                            gl.function('glClearDepth', None, c.c_double)(.8)
                            gl.function('glClear', None, c.c_uint)(0x4100)
                            use(program)
                            gl.function('glUniform1f', None, c.c_int, c.c_float)(loc(program, b'alphaTestRef'), threshold)
                            gl.function('glUniform1i', None, c.c_int, c.c_int)(loc(program, b'gtexture'), 0)
                            # 船舱遮罩只覆盖左半屏，颜色写入由游戏的渲染状态关闭。
                            gl.function('glEnable', None, c.c_uint)(0x0C11)
                            gl.function('glScissor', None, c.c_int, c.c_int, c.c_int, c.c_int)(0, 0, 16, 32)
                            color_mask(0, 0, 0, 0)
                            draw(4, 0, 3)
                            color_mask(1, 1, 1, 1)
                            gl.function('glDisable', None, c.c_uint)(0x0C11)
                            before = np.empty((32, 32, 4), np.float32)
                            read(0, 0, 32, 32, 0x1908, 0x1406, before.ctypes.data)
                            assert np.allclose(before, [.4, .2, .1, 1])
                            use(water)
                            draw(4, 0, 3)
                            pixels = np.empty_like(before)
                            depths = np.empty((32, 32), np.float32)
                            read(0, 0, 32, 32, 0x1908, 0x1406, pixels.ctypes.data)
                            read(0, 0, 32, 32, 0x1902, 0x1406, depths.ctypes.data)
                            blocked = not old and threshold == 0
                            assert np.allclose(pixels[:, :16], [.4, .2, .1, 1] if blocked else [0, 0, 1, 1])
                            assert np.allclose(depths[:, :16], .5 if blocked else .6)
                            assert np.allclose(pixels[:, 16:], [0, 0, 1, 1])
                            assert np.allclose(depths[:, 16:], .6)
            assert gl.function('glGetError', c.c_uint)() == 0
            print('PASS: depth-only boat mask, preserved cabin color, water occlusion, alpha cutout, old-code reproduction, all dimensions and DH compilation')
        finally:
            color_mask(1, 1, 1, 1)
            gl.function('glDisable', None, c.c_uint)(0x0B71)
            for program in programs:
                gl.delete_program(program)
            gl.function('glDeleteRenderbuffers', None, c.c_int, c.POINTER(c.c_uint))(1, c.byref(depth))
            target.close()


if __name__ == '__main__':
    main()
