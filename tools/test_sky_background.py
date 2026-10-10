"""验证日间天空背景、几何覆盖和地平线渐变的一致性。"""
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
        try:
            for dimension in ("world0", "world-1", "world1"):
                for entry in ("prepare", "gbuffers_skybasic"):
                    source = expand(SHADERS / dimension / (entry + ".fsh"))
                    source = configure(source, {"STARS_ENABLED": "0", "AURORA_ENABLED": "0", "METEORS_ENABLED": "0", "FANTASY_SKY": "0", "METEOR_NIGHT_CHANCE": "1.0", "METEOR_SHOWER_CHANCE": "0.0"})
                    source = source.replace("#version 330 compatibility", "#version 330 compatibility\n"
                                            "#define MC_RENDER_STAGE_SKY 1\n#define MC_RENDER_STAGE_STARS 5")
                    programs[dimension, entry] = gl.program(VERTEX, source)

            def render(dimension="world0", entry="prepare", day=False, rain=0.0, stage=1, below=False,
                       seconds=0.0, nighttime=0, pitch=0, fog=(0.65,0.72,0.82), sky=(0.30,0.44,0.78), eye=0):
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
                for name, matrix in (("gbufferProjectionInverse", np.linalg.inv(projection)),
                                     ("gbufferModelViewInverse", model)):
                    data = np.ascontiguousarray(matrix.T, dtype=np.float32)
                    gl.function("glUniformMatrix4fv", None, c.c_int, c.c_int, c.c_ubyte, c.c_void_p)(
                        location(program, name.encode()), 1, 0, data.ctypes.data_as(c.c_void_p))
                sun = model[:3, :3].T @ np.array([0, 1 if day else -1, 0])
                gl.function("glUniform3f", None, c.c_int, c.c_float, c.c_float, c.c_float)(
                    location(program, b"sunPosition"), *sun)
                for name, color in (("fogColor", fog), ("skyColor", sky)):
                    gl.function("glUniform3f", None, c.c_int, c.c_float, c.c_float, c.c_float)(location(program, name.encode()), *color)
                gl.function("glUniform1i", None, c.c_int, c.c_int)(location(program, b"isEyeInWater"), eye)
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

            scenarios = [((0.65,0.72,0.82),(0.30,0.44,0.78)),
                         ((0.48,0.49,0.52),(0.31,0.34,0.39)),
                         ((0.01,0.015,0.025),(0.003,0.006,0.015))]
            for fog, sky in scenarios:
                for pitch in (-30, 0, 25, 70):
                    background = render(fog=fog, sky=sky, pitch=pitch)
                    geometry = render(entry="gbuffers_skybasic", fog=fog, sky=sky, pitch=pitch)
                    assert np.allclose(background, geometry, atol=1e-6), "天空几何边界两侧必须使用相同颜色"
                    # 半屏几何覆盖模拟可见天空盘边缘，不允许产生新的接缝。
                    joined = background.copy()
                    joined[:size//2] = geometry[:size//2]
                    assert np.allclose(joined, background, atol=1e-6)
                horizontal = render(fog=fog, sky=sky)[...,:3]
                assert np.max(np.abs(np.diff(horizontal, axis=0))) < 0.01, "地平线渐变不得突跳"
                assert np.allclose(horizontal[0], np.array(fog)**2.2, atol=1e-5)
                assert np.allclose(horizontal[-1], np.array(sky)**2.2, atol=1e-5)
            for eye in (1,2,3):
                immersed = render(eye=eye)[...,:3]
                if eye==1:
                    assert np.allclose(immersed[0],np.full(3,0.003*0.35),atol=1e-5)
                    assert np.allclose(immersed[-1],np.array(scenarios[0][1])**2.2,atol=1e-5)
                    assert immersed[-1].mean()>immersed[0].mean()*20, "水下向上观察必须保留天空"
                else:
                    assert np.allclose(immersed,np.array(scenarios[0][0])**2.2,atol=1e-5)
                assert np.allclose(render(eye=eye), render(entry="gbuffers_skybasic", eye=eye), atol=1e-6)
            for dimension in ("world-1", "world1"):
                assert np.allclose(render(dimension)[...,:3], np.array(scenarios[0][0])**2.2, atol=1e-5)
            assert render(entry="gbuffers_skybasic", stage=5).max() == 0
            preview = np.concatenate([render(fog=fog,sky=sky)[...,:3] for fog,sky in scenarios],axis=1)
            path = artifact_path('sky-background-preview.png')
            Image.fromarray(np.uint8(np.clip(preview[::-1],0,1)**(1/2.2)*255)).save(path)
            print("PASS: sky geometry/background equality, partial coverage, horizon continuity, immersion and dimensions")
            print(f"Preview: {path}")
        finally:
            for program in programs.values():
                gl.delete_program(program)
            target.close()


if __name__ == "__main__":
    main()
