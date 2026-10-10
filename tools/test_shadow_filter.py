"""在 GPU 上使用人工深度场景验证实际的阴影过滤代码。"""
from artifact_paths import artifact_path

import ctypes as c
import json

import numpy as np
from PIL import Image, ImageDraw

from gl_context import GLContext
from validate_shaders import ROOT, SHADERS, configure, expand

VERTEX = """#version 330 compatibility
out vec2 uv;
void main() {
    vec2 vertices[3] = vec2[3](vec2(-1,-1), vec2(3,-1), vec2(-1,3));
    gl_Position = vec4(vertices[gl_VertexID], 0, 1);
    uv = vertices[gl_VertexID] * 0.5 + 0.5;
}
"""


class FilterScene:
    def __init__(self, gl, size=256, resolution=128):
        self.gl, self.size, self.resolution = gl, size, resolution
        self.textures = (c.c_uint * 2)()
        gl.function("glGenTextures", None, c.c_int, c.POINTER(c.c_uint))(2, self.textures)
        self.bind_texture(self.textures[0])
        self.upload(None, 0x8814, size, 0x1908)
        self.parameter(0x2801, 0x2600)
        self.parameter(0x2800, 0x2600)
        self.fbo = c.c_uint()
        gl.function("glGenFramebuffers", None, c.c_int, c.POINTER(c.c_uint))(1, c.byref(self.fbo))
        gl.function("glBindFramebuffer", None, c.c_uint, c.c_uint)(0x8D40, self.fbo)
        gl.function("glFramebufferTexture2D", None, c.c_uint, c.c_uint, c.c_uint,
                    c.c_uint, c.c_int)(0x8D40, 0x8CE0, 0x0DE1, self.textures[0], 0)
        status = gl.function("glCheckFramebufferStatus", c.c_uint, c.c_uint)(0x8D40)
        if status != 0x8CD5:
            raise RuntimeError(f"Incomplete test framebuffer: {status:#x}")
        gl.function("glViewport", None, c.c_int, c.c_int, c.c_int, c.c_int)(0, 0, size, size)
        self.bind_texture(self.textures[1])
        for key, value in ((0x2801, 0x2601), (0x2800, 0x2601),
                           (0x2802, 0x812F), (0x2803, 0x812F),
                           (0x884C, 0x884E), (0x884D, 0x0203)):
            self.parameter(key, value)

    def bind_texture(self, texture):
        self.gl.function("glBindTexture", None, c.c_uint, c.c_uint)(0x0DE1, texture)

    def parameter(self, key, value):
        self.gl.function("glTexParameteri", None, c.c_uint, c.c_uint, c.c_int)(0x0DE1, key, value)

    def upload(self, data, internal, size, pixel_format):
        pointer = None if data is None else data.ctypes.data_as(c.c_void_p)
        self.gl.function("glTexImage2D", None, c.c_uint, c.c_int, c.c_int, c.c_int,
                         c.c_int, c.c_int, c.c_uint, c.c_uint, c.c_void_p)(
            0x0DE1, 0, internal, size, size, 0, pixel_format, 0x1406, pointer)

    def render(self, quality, depth, slope=(0.0, 0.0), softness=1.5, pattern=False):
        self.bind_texture(self.textures[1])
        self.upload(np.ascontiguousarray(depth, dtype=np.float32), 0x8CAC, self.resolution, 0x1902)
        settings = configure(expand(SHADERS / "lib/settings.glsl"), {
            "shadowMapResolution": str(self.resolution), "SHADOW_FILTER": str(quality),
            "SHADOW_SOFTNESS": str(softness)})
        fragment = "#version 330 compatibility\n" + settings + expand(SHADERS / "lib/shadow_filter.glsl") + """
in vec2 uv;
uniform vec2 slope;
uniform int pattern;
layout(location=0) out vec4 result;
void main() {
    vec2 p = mix(vec2(0.2), vec2(0.8), uv);
    vec3 coordinate = vec3(p, 0.5 + dot(p, slope));
    float visibility = filteredShadow(coordinate, receiverGradient(coordinate));
    vec3 color = vec3(visibility);
    if (pattern == 1) {
        float checker = mod(floor(p.x * 32) + floor(p.y * 32), 2);
        vec3 albedo = mix(vec3(0.50, 0.40, 0.29), vec3(0.63, 0.54, 0.40), checker);
        color = pow(albedo * (vec3(0.16, 0.22, 0.32) + visibility * vec3(1.0, 0.83, 0.62)), vec3(1.0/2.2));
    }
    result = vec4(color, 1);
}
"""
        program = self.gl.program(VERTEX, fragment)
        self.gl.function("glUseProgram", None, c.c_uint)(program)
        location = self.gl.function("glGetUniformLocation", c.c_int, c.c_uint, c.c_char_p)
        self.gl.function("glUniform1i", None, c.c_int, c.c_int)(location(program, b"shadowtex1"), 0)
        self.gl.function("glUniform1i", None, c.c_int, c.c_int)(location(program, b"pattern"), int(pattern))
        self.gl.function("glUniform2f", None, c.c_int, c.c_float, c.c_float)(location(program, b"slope"), *slope)
        self.gl.function("glDrawArrays", None, c.c_uint, c.c_int, c.c_int)(0x0004, 0, 3)
        result = np.empty((self.size, self.size, 4), dtype=np.float32)
        self.gl.function("glReadPixels", None, c.c_int, c.c_int, c.c_int, c.c_int,
                         c.c_uint, c.c_uint, c.c_void_p)(0, 0, self.size, self.size,
                                                       0x1908, 0x1406, result.ctypes.data_as(c.c_void_p))
        error = self.gl.function("glGetError", c.c_uint)()
        self.gl.delete_program(program)
        if error:
            raise RuntimeError(f"OpenGL error: {error:#x}")
        if not np.isfinite(result).all():
            raise AssertionError("Non-finite filter output.")
        return result

    def close(self):
        self.gl.function("glDeleteFramebuffers", None, c.c_int, c.POINTER(c.c_uint))(1, c.byref(self.fbo))
        self.gl.function("glDeleteTextures", None, c.c_int, c.POINTER(c.c_uint))(2, self.textures)


def main():
    report = {}
    preview = Image.new("RGB", (768, 288), "#171d26")
    draw = ImageDraw.Draw(preview)
    with GLContext() as gl:
        report["renderer"] = gl.description()
        print(report["renderer"])
        scene = FilterScene(gl)
        try:
            v, u = np.mgrid[:128, :128].astype(np.float32)
            u, v = (u + 0.5) / 128, (v + 0.5) / 128
            for quality, name in enumerate(("Low: 4 taps", "Medium: 9 taps", "High: 16 taps")):
                lit = scene.render(quality, np.full_like(u, 0.5))[..., 0]
                blocked = scene.render(quality, np.full_like(u, 0.3))[..., 0]
                assert lit.min() > 0.999, (quality, "lit plane", lit.min())
                assert blocked.max() < 0.001, (quality, "opaque blocker", blocked.max())
                for slope in ((0.18, 0.12), (-0.30, 0.20), (0.45, -0.25)):
                    plane = 0.5 + u * slope[0] + v * slope[1]
                    result = scene.render(quality, plane, slope)[..., 0]
                    assert result.min() > 0.99, (quality, "receiver acne", slope, result.min())
                plane = 0.5 + u * 0.18 + v * 0.12
                edge_depth = plane - (u < 0.5) * 0.15
                edge = scene.render(quality, edge_depth, (0.18, 0.12))[128, :, 0]
                assert edge[:80].max() < 0.001 and edge[176:].min() > 0.999
                assert np.diff(edge).min() > -0.002, (quality, "non-monotonic edge")
                assert np.abs(np.diff(edge)).max() < 0.20, (quality, "edge discontinuity")
                widths = []
                for softness in (0.5, 1.5, 2.5):
                    line = scene.render(quality, edge_depth, (0.18, 0.12), softness)[128, :, 0]
                    widths.append(int(((line > 0.05) & (line < 0.95)).sum()))
                assert widths[0] < widths[-1], (quality, "softness response", widths)
                # 空深度图代表没有写入不透明投影的几何。
                clear = scene.render(quality, np.ones_like(u))[..., 0]
                assert clear.min() > 0.999
                mask = ((abs(u - 0.42) < 0.055) & (abs(v - 0.51) < 0.20))
                mask |= ((u - 0.64) ** 2 + (v - 0.53) ** 2 < 0.065 ** 2)
                mask |= (abs(u + v * 0.35 - 0.74) < 0.012) & (v < 0.43)
                pixels = scene.render(quality, plane - mask * 0.15, (0.18, 0.12), pattern=True)
                rgb = np.uint8(np.clip(pixels[::-1, :, :3], 0, 1) * 255)
                preview.paste(Image.fromarray(rgb), (quality * 256, 32))
                draw.text((quality * 256 + 10, 10), name, fill="white")
                report[str(quality)] = {"lit_min": float(lit.min()), "blocked_max": float(blocked.max()),
                                       "edge_max_step": float(np.abs(np.diff(edge)).max()),
                                       "softness_transition_pixels": widths}
                print(f"PASS: {name}; lit, blocked, sloped receivers, continuous edges, softness")
        finally:
            scene.close()
    output = artifact_path(".")
    output.mkdir(exist_ok=True)
    preview.save(output / "shadow-filter-preview.png")
    (output / "shadow-filter-results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Preview: {output / 'shadow-filter-preview.png'}")


if __name__ == "__main__":
    main()
