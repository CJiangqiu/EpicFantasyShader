"""验证程序太阳的圆形轮廓、角尺寸、光晕、晨昏颜色、天气与原版切换。"""
from artifact_paths import artifact_path

import ctypes as c
import math

import numpy as np
from PIL import Image

from gl_context import GLContext
from test_shadow_filter import FilterScene
from validate_shaders import ROOT, SHADERS, configure, expand


def main():
    size = 192
    with GLContext() as gl:
        print(gl.description())
        target = FilterScene(gl, size=size, resolution=16)
        try:
            # 白色纹理用于检查原版路径与太阳路径，独立纹理单元提供圆月图像。
            target.bind_texture(target.textures[1])
            target.parameter(0x884C, 0)
            target.upload(np.ones((16, 16, 4), dtype=np.float32), 0x8814, 16, 0x1908)
            moon_texture = c.c_uint()
            gl.function("glGenTextures", None, c.c_int, c.POINTER(c.c_uint))(1, c.byref(moon_texture))
            gl.function("glActiveTexture", None, c.c_uint)(0x84C1)
            target.bind_texture(moon_texture.value)
            for key, value in ((0x2801, 0x2601), (0x2800, 0x2601),
                               (0x2802, 0x812F), (0x2803, 0x812F)):
                target.parameter(key, value)
            with Image.open(SHADERS / "textures/moon.png") as source:
                moon_data = np.array(source.convert("RGBA"), dtype=np.float32) / 255.0
            target.upload(moon_data, 0x8058, moon_data.shape[0], 0x1908)
            gl.function("glActiveTexture", None, c.c_uint)(0x84C0)
            programs = {}
            for label, options in (("round", {}), ("vanilla", {"SUN_STYLE": "0"}),
                                   ("large", {"SUN_DIAMETER": "10.0"}),
                                   ("dim", {"SUN_BRIGHTNESS": "0.5"}),
                                   ("nohalo", {"SUN_HALO_STRENGTH": "0.0"}),
                                   ("wide", {"SUN_HALO_SIZE": "2.0"}),
                                   ("extreme", {"SUN_HALO_SIZE": "2.0", "SUN_DIAMETER": "10.0"}),
                                   ("nether", {}), ("end", {})):
                folder = {"nether": "world-1", "end": "world1"}.get(label, "world0")
                options = {"AURORA_ENABLED": "0", "METEORS_ENABLED": "0", **options}
                programs[label] = gl.program(configure(expand(SHADERS / folder / "gbuffers_skytextured.vsh"), options),
                                             configure(expand(SHADERS / folder / "gbuffers_skytextured.fsh"), options))

            def render(label="round", phase=0, alpha=1.0, sun=True, fov=30.0, background=None, height=1.0):
                program = programs[label]
                gl.function("glUseProgram", None, c.c_uint)(program)
                location = gl.function("glGetUniformLocation", c.c_int, c.c_uint, c.c_char_p)
                gl.function("glUniform1i", None, c.c_int, c.c_int)(location(program, b"moonPhase"), phase)
                gl.function("glUniform1i", None, c.c_int, c.c_int)(location(program, b"gtexture"), 0)
                gl.function("glUniform1i", None, c.c_int, c.c_int)(location(program, b"gaux1"), 1)
                gl.function("glUniform3f", None, c.c_int, c.c_float, c.c_float, c.c_float)(
                    location(program, b"moonPosition"), 0, 0, 100 if sun else -100)
                gl.function("glUniform3f", None, c.c_int, c.c_float, c.c_float, c.c_float)(
                    location(program, b"sunPosition"), 0, height, -math.sqrt(max(0, 1-height*height)))
                identity = (c.c_float * 16)(1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1)
                gl.function("glUniformMatrix4fv", None, c.c_int, c.c_int, c.c_ubyte, c.c_void_p)(
                    location(program, b"gbufferModelViewInverse"), 1, 0, c.cast(identity, c.c_void_p))
                scale = 1.0 / math.tan(math.radians(fov * 0.5))
                matrix = (c.c_float * 16)(scale, 0, 0, 0, 0, scale, 0, 0,
                                         0, 0, -1.002, -1, 0, 0, -0.2002, 0)
                projection = np.array(matrix, dtype=np.float32).reshape(4,4).T
                for uniform, transform in (("gbufferProjectionInverse", np.linalg.inv(projection)),
                                           ("gbufferModelViewInverse", np.eye(4))):
                    data = np.ascontiguousarray(transform.T, dtype=np.float32)
                    gl.function("glUniformMatrix4fv", None, c.c_int, c.c_int, c.c_ubyte, c.c_void_p)(
                        location(program, uniform.encode()), 1, 0, data.ctypes.data_as(c.c_void_p))
                for uniform in ("viewWidth", "viewHeight"):
                    gl.function("glUniform1f", None, c.c_int, c.c_float)(location(program, uniform.encode()), size)
                gl.function("glMatrixMode", None, c.c_uint)(0x1701)
                gl.function("glLoadMatrixf", None, c.POINTER(c.c_float))(matrix)
                gl.function("glMatrixMode", None, c.c_uint)(0x1700)
                gl.function("glLoadIdentity", None)()
                if background is None:
                    gl.function("glDisable", None, c.c_uint)(0x0BE2)
                    clear = (0, 0, 0, 0)
                else:
                    gl.function("glEnable", None, c.c_uint)(0x0BE2)
                    gl.function("glBlendFuncSeparate", None, c.c_uint, c.c_uint, c.c_uint, c.c_uint)(0x0302, 0x0303, 1, 0x0303)
                    clear = (*background, 1)
                gl.function("glClearColor", None, c.c_float, c.c_float, c.c_float, c.c_float)(*clear)
                gl.function("glClear", None, c.c_uint)(0x4000)
                gl.function("glColor4f", None, c.c_float, c.c_float, c.c_float, c.c_float)(1, 1, 1, alpha)
                before = gl.function("glGetError", c.c_uint)()
                assert before == 0, f"Draw setup: {before:#x}"
                # 立即模式绘制期间不查询驱动函数地址，避免驱动在查询时触发非法操作。
                texcoord = gl.function("glTexCoord2f", None, c.c_float, c.c_float)
                vertex = gl.function("glVertex3f", None, c.c_float, c.c_float, c.c_float)
                end = gl.function("glEnd", None)
                gl.function("glBegin", None, c.c_uint)(0x0007)
                for x, y, u, v in ((-20, -20, 0, 0), (20, -20, 1, 0), (20, 20, 1, 1), (-20, 20, 0, 1)):
                    tx, ty = (u, v) if sun else ((phase % 4 + u) / 4, (phase // 4 + v) / 2)
                    texcoord(tx, ty)
                    vertex(x, y, -100)
                end()
                pixels = np.empty((size, size, 4), dtype=np.float32)
                gl.function("glReadPixels", None, c.c_int, c.c_int, c.c_int, c.c_int,
                            c.c_uint, c.c_uint, c.c_void_p)(0, 0, size, size, 0x1908, 0x1406,
                                                          pixels.ctypes.data_as(c.c_void_p))
                error = gl.function("glGetError", c.c_uint)()
                assert error == 0, f"OpenGL 错误：{error:#x}"
                assert np.isfinite(pixels).all(), "月面输出不得包含无效数值"
                return pixels

            normal = render()
            nohalo = render("nohalo")
            disk = normal[..., 3] > 0.5
            width = disk[size//2].sum()
            predicted = size * math.tan(math.radians(5.3 * 0.5)) / math.tan(math.radians(15))
            assert abs(width - predicted) < 3, (width, predicted)
            assert abs(width - disk[:,size//2].sum()) <= 1, "太阳必须为圆形"
            assert normal[0,0,3] == 0 and normal[-1,-1,3] == 0
            assert normal[...,3].sum() > nohalo[...,3].sum(), "光晕应在太阳外延伸"
            assert render("wide")[...,3].sum() > normal[...,3].sum()
            extreme = render("extreme", fov=120)
            assert extreme[0,:,3].max() == 0 and extreme[:,0,3].max() == 0, "最大太阳光晕应平滑归零"
            large = render("large")
            assert (large[...,3] > 0.5).sum() > disk.sum() * 3
            assert np.allclose(render("dim")[...,:3], normal[...,:3] * 0.5, atol=1e-5)
            assert np.allclose(render(alpha=0.35)[...,3], normal[...,3] * 0.35, atol=1e-5)
            assert render(alpha=0)[...,3].max() == 0
            dawn = render(height=0.0)
            assert dawn[size//2,size//2,1] < normal[size//2,size//2,1] * 0.5, "晨昏太阳应偏暖"
            assert np.mean(np.abs(render(height=0.2) - render(height=0.201))) < 0.005
            vanilla = render("vanilla")
            assert (vanilla[...,3] > 0.5).sum() > disk.sum() * 5
            assert np.allclose(render("nether"), vanilla) and np.allclose(render("end"), vanilla)
            assert np.allclose(render(sun=False), render("vanilla", sun=False)), "太阳设置不得改变月亮"
            gl.function("glActiveTexture", None, c.c_uint)(0x84C0)
            target.bind_texture(target.textures[1])
            target.upload(np.zeros((16,16,4), dtype=np.float32), 0x8814, 16, 0x1908)
            assert np.allclose(render(), normal), "圆形太阳不依赖太阳贴图"
            assert render("vanilla")[...,3].max() == 0
            frames = [normal, dawn, nohalo, render("wide")]
            panels = []
            for pixels in frames:
                background = np.array([0.05, 0.11, 0.22])
                color = pixels[...,:3] * pixels[...,3:4] + background * (1-pixels[...,3:4])
                color /= 1 + np.maximum(color.max(axis=2,keepdims=True)-0.8,0)
                panels.append(np.uint8(np.clip(color[::-1],0,1)**(1/2.2)*255))
            output = Image.fromarray(np.concatenate(panels,axis=1))
            print("PASS: round sun size, halo, warm twilight, weather, texture independence, vanilla mode and moon/dimension isolation")
            for program in programs.values():
                gl.delete_program(program)
            gl.function("glDeleteTextures", None, c.c_int, c.POINTER(c.c_uint))(1, c.byref(moon_texture))
        finally:
            target.close()
    path = artifact_path('sun-preview.png')
    path.parent.mkdir(exist_ok=True)
    output.save(path)
    print(f"Preview: {path}")


if __name__ == "__main__":
    main()
