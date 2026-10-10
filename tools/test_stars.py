"""验证星点背景、天空覆盖、天气淡出、维度隔离与原版星点丢弃。"""
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
            for dimension in ("world0", "world-1", "world1"):
                for entry in ("prepare", "gbuffers_skybasic"):
                    source = expand(SHADERS / dimension / (entry + ".fsh"))
                    source = configure(source, {"FANTASY_SKY": "0", "METEOR_NIGHT_CHANCE": "1.0", "METEOR_SHOWER_CHANCE": "0.0"})
                    source = source.replace("#version 330 compatibility", "#version 330 compatibility\n"
                                            "#define MC_RENDER_STAGE_SKY 1\n#define MC_RENDER_STAGE_STARS 5")
                    programs[dimension, entry] = gl.program(VERTEX, source)

            def render(dimension="world0", entry="prepare", day=False, rain=0.0, stage=1, below=False,
                       seconds=0.0, nighttime=0):
                program = programs[dimension, entry]
                gl.function("glUseProgram", None, c.c_uint)(program)
                location = gl.function("glGetUniformLocation", c.c_int, c.c_uint, c.c_char_p)
                def scalar(name, value):
                    gl.function("glUniform1f", None, c.c_int, c.c_float)(location(program, name.encode()), value)
                projection = np.array([[1, 0, 0, 0], [0, 1, 0, 0],
                                       [0, 0, -1.002, -0.2002], [0, 0, -1, 0]], dtype=np.float32)
                angle = math.radians(-55 if below else 55)
                co, si = math.cos(angle), math.sin(angle)
                model = np.array([[1, 0, 0, 0], [0, co, -si, 0], [0, si, co, 0], [0, 0, 0, 1]], dtype=np.float32)
                for name, matrix in (("gbufferProjectionInverse", np.linalg.inv(projection)),
                                     ("gbufferModelViewInverse", model)):
                    data = np.ascontiguousarray(matrix.T, dtype=np.float32)
                    gl.function("glUniformMatrix4fv", None, c.c_int, c.c_int, c.c_ubyte, c.c_void_p)(
                        location(program, name.encode()), 1, 0, data.ctypes.data_as(c.c_void_p))
                sun = model[:3, :3].T @ np.array([0, 1 if day else -1, 0])
                gl.function("glUniform3f", None, c.c_int, c.c_float, c.c_float, c.c_float)(
                    location(program, b"sunPosition"), *sun)
                scalar("rainStrength", rain)
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
            peak = night[..., :3].max(axis=2)
            occupied = (peak > 0.005).sum()
            assert 20 < occupied < size * size * 0.008, occupied
            assert np.array_equal(night, render()), "固定视角的星空应稳定"
            assert render(day=True)[..., :3].max() == 0, "白天不得显示星点"
            assert render(rain=1)[..., :3].max() == 0, "完全降雨时星点应淡出"
            assert np.allclose(render(rain=0.5)[..., :3], night[..., :3] * 0.25, atol=1e-5)
            assert render(below=True)[..., :3].max() == 0, "地平线以下不得显示星点"
            assert np.allclose(render(entry="gbuffers_skybasic"), night, atol=1e-5), "天空覆盖不能擦除背景星点"
            for dimension in ("world0", "world-1", "world1"):
                assert render(dimension, "gbuffers_skybasic", stage=5).max() == 0, "原版星点几何必须丢弃"
                if dimension != "world0":
                    assert render(dimension)[..., :3].max() == 0, "其他维度不得显示主世界星点"
            colors = night[..., :3][peak > 0.02]
            meteor_seen = False
            for seconds in range(120):
                sky = render(seconds=seconds, nighttime=18000)
                stars_only = render(seconds=seconds)
                if np.max(np.abs(sky - stars_only)) < 0.001:
                    continue
                meteor_seen = True
                assert np.allclose(sky, render(entry="gbuffers_skybasic", seconds=seconds, nighttime=18000), atol=1e-5)
                for dimension in ("world-1", "world1"):
                    assert render(dimension, seconds=seconds, nighttime=18000)[..., :3].max() == 0
                break
            assert meteor_seen, "实际背景入口应显示流星"
            assert (colors[:, 2] > colors[:, 0]).any(), "应包含蓝白星点"
            assert (colors[:, 0] > colors[:, 2] * 1.4).any(), "应包含暖色星点"
            path = artifact_path('stars-preview.png')
            path.parent.mkdir(exist_ok=True)
            rgb = night[..., :3] + np.array([0.002, 0.004, 0.009])
            rgb = rgb / (1.0 + np.maximum(rgb.max(axis=2, keepdims=True) - 0.8, 0.0))
            Image.fromarray(np.uint8(np.clip(rgb[::-1], 0, 1) ** (1 / 2.2) * 255)).save(path)
            print(f"PASS: sparse stable stars ({occupied} lit pixels), colors, day/rain/horizon fade, sky coverage, dimensions, vanilla discard")
            print(f"Preview: {path}")
        finally:
            for program in programs.values():
                gl.delete_program(program)
            target.close()


if __name__ == "__main__":
    main()
