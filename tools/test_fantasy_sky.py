"""验证绚丽星空的日期、开关、卫星遮挡、天气、维度与参数响应。"""
from artifact_paths import artifact_path

import ctypes as c
import math

import numpy as np
from PIL import Image

from gl_context import GLContext
from test_shadow_filter import FilterScene
from validate_shaders import ROOT, SHADERS, configure, expand


VERTEX = """#version 330 compatibility
out vec2 texcoord;
out vec4 vertexColor;
void main() {
    vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
    texcoord = p;
    vertexColor = vec4(0, 0, 0, 1);
    gl_Position = vec4(p * 2.0 - 1.0, 0, 1);
}
"""


def main():
    size = 384
    with GLContext() as gl:
        print(gl.description())
        target = FilterScene(gl, size=size)
        programs = {}
        nebula_options = {
            "blue": {"NEBULA_COLOR": "1"}, "rose": {"NEBULA_COLOR": "2"}, "gold": {"NEBULA_COLOR": "3"},
            "dense": {"NEBULA_DENSITY": "2.0"}, "wide": {"NEBULA_COVERAGE": "2.0"},
            "scale": {"NEBULA_SCALE": "2.0"}, "soft": {"NEBULA_DETAIL": "0.0"},
            "dustless": {"NEBULA_DUST": "0.0"}, "moving": {"NEBULA_SPEED": "4.0"},
            "rotated": {"NEBULA_ROTATION": "90.0"}}
        try:
            for dimension in ("world0", "world-1", "world1", "off", "nebula", "dim", "moon", "daily", "month", "small", "occlusion", "layered", *nebula_options): 
                for entry in ("prepare", "gbuffers_skybasic"):
                    source = expand(SHADERS / (dimension if dimension.startswith("world") else "world0") / (entry + ".fsh"))
                    options = {"STARS_ENABLED": "0", "METEORS_ENABLED": "0", "AURORA_ENABLED": "0", "FANTASY_SKY": "1"}
                    options.update({"off": {"FANTASY_SKY": "0"},
                                    "nebula": {"FANTASY_BLOOD_MOON": "0"},
                                    "dim": {"FANTASY_BLOOD_MOON": "0", "NEBULA_BRIGHTNESS": "0.5"},
                                    "moon": {"FANTASY_NEBULA": "0"},
                                    "daily": {"FANTASY_NEBULA": "0", "BLOOD_MOON_PERIOD": "0"},
                                    "month": {"FANTASY_NEBULA": "0", "BLOOD_MOON_PERIOD": "30"},
                                    "small": {"FANTASY_NEBULA": "0", "BLOOD_MOON_DIAMETER": "12.0"},
                                    "occlusion": {"FANTASY_NEBULA": "0"}, "layered": {"FANTASY_NEBULA": "0"}}.get(dimension, {}))
                    if dimension in nebula_options:
                        options.update({"FANTASY_BLOOD_MOON": "0", **nebula_options[dimension]})
                    if dimension == "layered":
                        source = source.replace("+ proceduralNearSky(direction);", "+ vec3(0.10, 0.20, 0.30);")
                    if dimension == "occlusion":
                        source = source.replace("applyFantasySky(direction, proceduralStars(direction))", "applyFantasySky(direction, vec3(0.8))")
                    source = configure(source, options)
                    source = source.replace("#version 330 compatibility", "#version 330 compatibility\n"
                                            "#define MC_RENDER_STAGE_SKY 1\n#define MC_RENDER_STAGE_STARS 5")
                    programs[dimension, entry] = gl.program(VERTEX, source)

            def render(dimension="world0", entry="prepare", day=False, rain=0.0, stage=1, below=False,
                       seconds=0.0, nighttime=18000, cold=1.0, yaw=0.0, pitch=55, day_index=7):
                program = programs[dimension, entry]
                gl.function("glUseProgram", None, c.c_uint)(program)
                location = gl.function("glGetUniformLocation", c.c_int, c.c_uint, c.c_char_p)
                def scalar(name, value):
                    gl.function("glUniform1f", None, c.c_int, c.c_float)(location(program, name.encode()), value)
                projection = np.array([[1, 0, 0, 0], [0, 1, 0, 0],
                                       [0, 0, -1.002, -0.2002], [0, 0, -1, 0]], dtype=np.float32)
                angle = math.radians(-55 if below else pitch)
                co, si = math.cos(angle), math.sin(angle)
                model = np.array([[1, 0, 0, 0], [0, co, -si, 0], [0, si, co, 0], [0, 0, 0, 1]], dtype=np.float32)
                cy, sy = math.cos(yaw), math.sin(yaw)
                rotation = np.array([[-cy, 0, sy, 0], [0, 1, 0, 0],
                                     [-sy, 0, -cy, 0], [0, 0, 0, 1]], dtype=np.float32)
                model = rotation @ model
                for name, matrix in (("gbufferProjectionInverse", np.linalg.inv(projection)),
                                     ("gbufferModelViewInverse", model)):
                    data = np.ascontiguousarray(matrix.T, dtype=np.float32)
                    gl.function("glUniformMatrix4fv", None, c.c_int, c.c_int, c.c_ubyte, c.c_void_p)(
                        location(program, name.encode()), 1, 0, data.ctypes.data_as(c.c_void_p))
                sun = model[:3, :3].T @ np.array([0, 1 if day else -1, 0])
                gl.function("glUniform3f", None, c.c_int, c.c_float, c.c_float, c.c_float)(
                    location(program, b"sunPosition"), *sun)
                scalar("rainStrength", rain)
                scalar("auroraColdFactor", cold)
                scalar("viewWidth", size)
                scalar("viewHeight", size)
                scalar("frameTimeCounter", seconds)
                gl.function("glUniform1i", None, c.c_int, c.c_int)(location(program, b"worldTime"), nighttime)
                gl.function("glUniform1i", None, c.c_int, c.c_int)(location(program, b"worldDay"), day_index)
                gl.function("glUniform1i", None, c.c_int, c.c_int)(location(program, b"renderStage"), stage)
                gl.function("glClearColor", None, c.c_float, c.c_float, c.c_float, c.c_float)(0, 0, 0, 0)
                gl.function("glClear", None, c.c_uint)(0x4000)
                gl.function("glDrawArrays", None, c.c_uint, c.c_int, c.c_int)(0x0004, 0, 3)
                pixels = np.empty((size, size, 4), dtype=np.float32)
                gl.function("glReadPixels", None, c.c_int, c.c_int, c.c_int, c.c_int,
                            c.c_uint, c.c_uint, c.c_void_p)(0, 0, size, size, 0x1908, 0x1406,
                                                          pixels.ctypes.data_as(c.c_void_p))
                assert gl.function("glGetError", c.c_uint)() == 0
                assert np.isfinite(pixels).all()
                return pixels

            night = render()
            rgb = night[..., :3]
            assert rgb.max() > 0.05
            assert np.array_equal(night, render()), "固定日期和视角必须稳定"
            for dimension in ("world-1", "world1", "off"):
                assert render(dimension)[..., :3].max() == 0
            for arguments in ({"day": True}, {"rain": 1}, {"below": True}):
                assert render(**arguments)[..., :3].max() == 0
            assert np.allclose(render(entry="gbuffers_skybasic"), night, atol=1e-5)
            nebula = render("nebula")[..., :3]
            moon = render("moon")[..., :3]
            assert nebula.max() > 0.01 and moon.max() > 0.05
            assert np.allclose(render("dim")[..., :3], nebula * 0.5, atol=1e-5)
            assert np.allclose(render("nebula", rain=0.5)[..., :3], nebula * 0.25, atol=1e-5)
            for day in range(32):
                visible = render("moon", day_index=day)[..., :3].max() > 0.01
                assert visible == (day % 8 == 7), (day, visible)
            for day in (0, 1, 7, 8, 31):
                assert render("daily", day_index=day)[..., :3].max() > 0.01, "间隔零应每晚出现"
            for day in (0, 7, 28, 29, 30, 58, 59, 60):
                assert (render("month", day_index=day)[..., :3].max() > 0.01) == (day % 30 == 29)
            assert np.allclose(render(day_index=6)[..., :3], nebula), "普通夜晚只显示星云"
            assert moon[..., 0].sum() > moon[..., 1].sum() * 2, "血月应为红褐色"
            assert np.allclose(render("layered")[..., :3], moon + np.array([0.10, 0.20, 0.30]), atol=1e-5), "近层必须叠加在血月之前景"
            area = (moon.max(axis=2) > 0.002).sum()
            small_area = (render("small")[..., :3].max(axis=2) > 0.002).sum()
            assert 3.3 < area / small_area < 4.8, "视直径应控制球体面积"
            occlusion = render("occlusion")[..., :3]
            disk = np.max(np.abs(occlusion - 0.8), axis=2) > 0.10
            interior = disk.copy()
            for dx, dy in ((-4,0), (4,0), (0,-4), (0,4), (-4,-4), (-4,4), (4,-4), (4,4)):
                interior &= np.roll(disk, (dy, dx), axis=(0,1))
            assert np.mean(np.max(np.abs(occlusion - moon), axis=2)[interior] < 1e-4) > 0.95, "卫星内部不得透出背景星点"
            dark = interior & (moon.max(axis=2) < 0.0001)
            dark_fraction = dark.sum() / interior.sum()
            assert 0.35 < dark_fraction < 0.80, "血月应有明显隐入夜空的暗面"
            assert np.max(np.abs(occlusion[dark] - moon[dark])) < 1e-5, "暗面不得透出远处星空"
            assert not np.allclose(moon, render("moon", nighttime=17000)[..., :3]), "血月沿独立轨迹移动"
            sums = nebula.sum(axis=(0,1))
            assert sums[2] > sums[0] > sums[1], "默认薄雾应呈紫色"
            for variant in nebula_options:
                assert not np.allclose(render(variant, seconds=100)[..., :3], nebula), variant
            assert render("dense")[..., :3].sum() > nebula.sum()
            assert render("wide")[..., :3].sum() > nebula.sum()
            assert render("dustless")[..., :3].sum() > nebula.sum()
            assert np.array_equal(render("nebula", seconds=200), render("nebula")), "零速度应静止"
            assert np.mean(np.abs(render("moving", seconds=0.016) - render("moving"))) < 0.0001
            assert np.mean(np.abs(render("moving", seconds=3599.99) - render("moving"))) < 0.0001, "时钟循环应连续"
            colors = [nebula, render("blue")[..., :3], render("rose")[..., :3], render("gold")[..., :3]]
            palette = np.concatenate(colors, axis=1) + np.array([0.002, 0.004, 0.009])
            Image.fromarray(np.uint8(np.clip(palette[::-1], 0, 1) ** (1/2.2) * 255)).save(artifact_path('nebula-preview.png'))
            print("PASS: nebula palettes, density, coverage, detail, scale, dust, orientation and continuous motion")
            previews = [rgb, render(day_index=6)[..., :3], render("daily")[..., :3]]
            preview = np.concatenate(previews, axis=1) + np.array([0.002, 0.004, 0.009])
            preview /= 1 + np.maximum(preview.max(axis=2, keepdims=True) - 0.8, 0)
            path = artifact_path('fantasy-sky-preview.png')
            path.parent.mkdir(exist_ok=True)
            Image.fromarray(np.uint8(np.clip(preview[::-1], 0, 1) ** (1/2.2) * 255)).save(path)
            print("PASS: fantasy sky toggles, dimensions, weather, monthly/daily events, size, orbit and occlusion")
            print(f"Preview: {path}")
        finally:
            for program in programs.values():
                gl.delete_program(program)
            target.close()


if __name__ == "__main__":
    main()
