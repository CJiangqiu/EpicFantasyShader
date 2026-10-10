"""在真实月亮入口上验证月相、角尺寸、天气透明度与原版切换，并生成预览。"""
from artifact_paths import artifact_path

import ctypes as c
import math

import numpy as np
from PIL import Image, ImageDraw

from gl_context import GLContext
from test_shadow_filter import FilterScene
from validate_shaders import ROOT, SHADERS, configure, expand


def main():
    size = 192
    output = Image.new("RGB", (size * 4, (size + 24) * 2), "#0d1320")
    draw = ImageDraw.Draw(output)
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
            for label, options in (("round", {}), ("fantasy", {"FANTASY_SKY": "1"}), ("vanilla", {"MOON_STYLE": "0"}),
                                   ("layered", {}), ("layered_vanilla", {"MOON_STYLE": "0"}),
                                   ("large", {"MOON_DIAMETER": "12.0"}),
                                   ("dim", {"MOON_BRIGHTNESS": "0.5"}),
                                   ("nether", {}), ("end", {})):
                options = {"SUN_STYLE": "0", **options}
                folder = {"nether": "world-1", "end": "world1"}.get(label, "world0")
                fragment = configure(expand(SHADERS / folder / "gbuffers_skytextured.fsh"),
                                     {"AURORA_ENABLED": "0", "METEORS_ENABLED": "0", **options})
                if label.startswith("layered"):
                    # 已知近层颜色隔离合成计算，效果本身由独立极光和流星回归覆盖。
                    fragment = fragment.replace("proceduralNearSky(skyDirection(gl_FragCoord.xy / vec2(viewWidth, viewHeight)))", "vec3(0.10, 0.20, 0.30)")
                programs[label] = gl.program(
                    configure(expand(SHADERS / folder / "gbuffers_skytextured.vsh"), options), fragment)


            def render(label="round", phase=0, alpha=1.0, sun=False, fov=10.0, background=None):
                program = programs[label]
                gl.function("glUseProgram", None, c.c_uint)(program)
                location = gl.function("glGetUniformLocation", c.c_int, c.c_uint, c.c_char_p)
                gl.function("glUniform1i", None, c.c_int, c.c_int)(location(program, b"moonPhase"), phase)
                gl.function("glUniform1i", None, c.c_int, c.c_int)(location(program, b"gtexture"), 0)
                gl.function("glUniform1i", None, c.c_int, c.c_int)(location(program, b"gaux1"), 1)
                gl.function("glUniform3f", None, c.c_int, c.c_float, c.c_float, c.c_float)(
                    location(program, b"moonPosition"), 0, 0, 100 if sun else -100)
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

            assert np.allclose(render("fantasy"), render()), "绚丽星空不得替换或染红普通月亮"
            assert np.allclose(render("fantasy", sun=True), render(sun=True)), "绚丽星空不得改变太阳"
            props = (SHADERS / "shaders.properties").read_text(encoding="utf-8")
            assert "blend.gbuffers_skytextured=SRC_ALPHA ONE_MINUS_SRC_ALPHA ONE ONE_MINUS_SRC_ALPHA" in props
            far, near = np.array([0.32, 0.08, 0.40]), np.array([0.10, 0.20, 0.30])
            for original, layered in (("round", "layered"), ("vanilla", "layered_vanilla")):
                for phase in (0, 2, 4):
                    for alpha in (1.0, 0.35):
                        base = render(original, phase=phase, alpha=alpha)
                        composed = render(layered, phase=phase, alpha=alpha, background=far+near)
                        mask = base[..., 3:4]
                        expected = base[..., :3] * mask + far * (1-mask) + near
                        assert np.allclose(composed[..., :3], expected, atol=2e-5), "月面遮挡远层，近层必须保留一份"
            print("PASS: actual moon blend preserves foreground once across phases, weather and vanilla mode")
            areas = []
            phases = []
            for phase in range(8):
                pixels = render(phase=phase)
                phases.append(pixels)
                lit = pixels[..., 0] / np.maximum(phases[0][..., 0], 1e-6)
                areas.append(float((lit * pixels[..., 3]).sum()))
                linear = pixels[..., :3] * pixels[..., 3:4] + np.array([0.004, 0.007, 0.014]) * (1-pixels[..., 3:4])
                rgb = np.uint8(np.clip(linear[::-1], 0, 1) ** (1/2.2) * 255)
                x, y = (phase % 4) * size, (phase // 4) * (size + 24)
                output.paste(Image.fromarray(rgb), (x, y + 24))
                draw.text((x + 8, y + 5), f"Phase {phase}", fill="white")
            assert all(np.allclose(p[..., 3], phases[0][..., 3]) for p in phases), "所有月相应保留完整月盘遮挡"
            expected = [1.0, 0.8536, 0.5, 0.1464, 0.0, 0.1464, 0.5, 0.8536]
            for value, fraction in zip(areas, expected):
                assert abs(value / areas[0] - fraction) < 0.025, (areas, expected)
            assert phases[2][:, :size//2, 0].sum() > phases[2][:, size//2:, 0].sum() * 20
            assert phases[6][:, size//2:, 0].sum() > phases[6][:, :size//2, 0].sum() * 20
            assert np.allclose(render(alpha=0.35)[..., 3], phases[0][..., 3] * 0.35, atol=1e-5)
            assert render(alpha=0)[..., 3].max() == 0
            full = render(fov=30)
            large = render("large", fov=30)
            ratio = large[..., 3].sum() / full[..., 3].sum()
            assert 3.9 < ratio < 4.2, ratio
            width = (full[size//2, :, 3] > 0.5).sum()
            predicted = size * math.tan(math.radians(3)) / math.tan(math.radians(15))
            assert abs(width - predicted) <= 2, (width, predicted)
            assert np.allclose(render("dim")[..., :3], phases[0][..., :3] * 0.5, atol=1e-5)
            # 均匀纹理应消除月海变化，确认实际入口使用独立纹理而非原版图集。
            gl.function("glActiveTexture", None, c.c_uint)(0x84C1)
            target.upload(np.ones_like(moon_data), 0x8058, moon_data.shape[0], 0x1908)
            gl.function("glActiveTexture", None, c.c_uint)(0x84C0)
            flat = render()
            interior = phases[0][..., 3] > 0.99
            assert np.std(phases[0][..., 0][interior]) > 0.01, "月面应保留纹理细节"
            assert np.allclose(flat[..., :3][interior], 1.0), "月面必须读取自定义纹理"
            assert phases[0][0, 0, 3] == 0, "月面图像的方形背景不得遮挡天空"
            gl.function("glActiveTexture", None, c.c_uint)(0x84C1)
            target.upload(moon_data, 0x8058, moon_data.shape[0], 0x1908)
            gl.function("glActiveTexture", None, c.c_uint)(0x84C0)
            vanilla = render("vanilla")
            assert vanilla[..., 3].min() > 0.999, "原版路径应保留纹理四边形"
            assert render(sun=True)[..., 3].min() > 0.999, "太阳不得套用圆月遮罩"
            assert np.allclose(render("nether"), vanilla), "下界不得使用主世界圆月"
            assert np.allclose(render("end"), vanilla), "末地不得使用主世界圆月"
            cloud = gl.program(expand(SHADERS / "world0/gbuffers_clouds.vsh"),
                               expand(SHADERS / "world0/gbuffers_clouds.fsh"))
            gl.function("glUseProgram", None, c.c_uint)(cloud)
            gl.function("glMatrixMode", None, c.c_uint)(0x1701)
            gl.function("glLoadIdentity", None)()
            gl.function("glClearColor", None, c.c_float, c.c_float, c.c_float, c.c_float)(0.2, 0.3, 0.4, 1)
            gl.function("glClear", None, c.c_uint)(0x4000)
            gl.function("glBegin", None, c.c_uint)(0x0007)
            for x, y in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                gl.function("glVertex3f", None, c.c_float, c.c_float, c.c_float)(x, y, 0)
            gl.function("glEnd", None)()
            pixel = (c.c_float * 4)()
            gl.function("glReadPixels", None, c.c_int, c.c_int, c.c_int, c.c_int,
                        c.c_uint, c.c_uint, c.c_void_p)(size//2, size//2, 1, 1, 0x1908, 0x1406, pixel)
            assert np.allclose(pixel[:], (0.2, 0.3, 0.4, 1)), "原版云几何不得写入颜色"
            gl.delete_program(cloud)
            print("PASS: eight phases, angular diameter, brightness, weather fade, sun isolation, dimension isolation")
            print("PASS: vanilla cloud geometry does not write color")
            for program in programs.values():
                gl.delete_program(program)
            gl.function("glDeleteTextures", None, c.c_int, c.POINTER(c.c_uint))(1, c.byref(moon_texture))
        finally:
            target.close()
    path = artifact_path('moon-preview.png')
    path.parent.mkdir(exist_ok=True)
    output.save(path)
    print(f"Preview: {path}")


if __name__ == "__main__":
    main()
