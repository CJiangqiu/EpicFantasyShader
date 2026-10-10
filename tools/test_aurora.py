"""验证极光的寒冷群系权重、昼夜天气、天空覆盖与外观设置。"""
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
    size = 768
    with GLContext() as gl:
        print(gl.description())
        target = FilterScene(gl, size=size)
        programs = {}
        try:
            for dimension in ("world0", "world-1", "world1", "off", "dim", "still", "tall", "wide"): 
                for entry in ("prepare", "gbuffers_skybasic"):
                    source = expand(SHADERS / (dimension if dimension.startswith("world") else "world0") / (entry + ".fsh"))
                    options = {"FANTASY_SKY": "0", "STARS_ENABLED": "0", "METEORS_ENABLED": "0"}
                    options.update({"off": {"AURORA_ENABLED": "0"}, "dim": {"AURORA_BRIGHTNESS": "0.5"},
                                    "still": {"AURORA_SPEED": "0.0"}, "tall": {"AURORA_HEIGHT": "2.0"},
                                    "wide": {"AURORA_SIZE": "2.0"}}.get(dimension, {}))
                    source = configure(source, options)
                    source = source.replace("#version 330 compatibility", "#version 330 compatibility\n"
                                            "#define MC_RENDER_STAGE_SKY 1\n#define MC_RENDER_STAGE_STARS 5")
                    programs[dimension, entry] = gl.program(VERTEX, source)

            def render(dimension="world0", entry="prepare", day=False, rain=0.0, stage=1, below=False,
                       seconds=0.0, nighttime=0, cold=1.0, yaw=0.0, pitch=55):
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
                gl.function("glUniform1i", None, c.c_int, c.c_int)(location(program, b"worldDay"), 1)
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
            assert rgb.max() > 0.05, "寒冷夜晚应显示极光"
            coverage = (rgb.max(axis=2) > 0.01).mean()
            assert 0.02 < coverage < 0.75, "局部光带应可见并保留开阔夜空"
            views = [render(yaw=angle)[..., :3] for angle in (-0.45, 0, 0.45)]
            assert all(view.max() > 0.05 for view in views), "共同朝向内应显示多片光幕"
            assert render(yaw=math.pi, pitch=25)[..., :3].max() > 0.05, "相反方向应有独立极光区域"
            assert render(pitch=85)[..., :3].max() > 0.05, "头顶应有极光区域"
            assert all(not np.allclose(views[0], view) for view in views[1:]), "光幕轮廓应有位置差异"
            assert np.array_equal(night, render()), "固定时间和视角应稳定"
            assert render(cold=0)[..., :3].max() == 0, "温暖群系不得显示极光"
            assert np.allclose(render(cold=0.5)[..., :3], rgb * 0.5, atol=1e-5)
            for arguments in ({"day": True}, {"rain": 1}, {"below": True}):
                assert render(**arguments)[..., :3].max() == 0
            assert np.allclose(render(rain=0.5)[..., :3], rgb * 0.25, atol=1e-5)
            assert np.allclose(render(entry="gbuffers_skybasic"), night, atol=1e-5)
            for dimension in ("world-1", "world1", "off"):
                assert render(dimension)[..., :3].max() == 0
            assert np.allclose(render("dim")[..., :3], rgb * 0.5, atol=1e-5)
            assert render("tall")[..., :3].sum() > rgb.sum()
            assert render("wide")[..., :3].sum() > rgb.sum()
            assert np.array_equal(render("still"), render("still", seconds=30))
            assert not np.allclose(night, render(seconds=30))
            assert np.mean(np.abs(night - render(seconds=0.016))) < 0.001, "动画应连续"
            preview = np.concatenate([rgb, render(yaw=math.pi)[..., :3], render(pitch=85)[..., :3]], axis=1) + np.array([0.002, 0.004, 0.009])
            preview /= 1 + np.maximum(preview.max(axis=2, keepdims=True) - 0.8, 0)
            path = artifact_path('aurora-preview.png')
            path.parent.mkdir(exist_ok=True)
            Image.fromarray(np.uint8(np.clip(preview[::-1], 0, 1) ** (1/2.2) * 255)).save(path)
            print("PASS: aurora coverage, cold weighting, day/rain/horizon fade, dimensions, sky composition and options")
            print(f"Preview: {path}")
        finally:
            for program in programs.values():
                gl.delete_program(program)
            target.close()


if __name__ == "__main__":
    main()
