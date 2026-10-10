"""使用实际 GLSL 验证逐夜概率、流星运动、外观选项与星点设置。"""
from artifact_paths import artifact_path

import ctypes as c

import numpy as np
from PIL import Image

from gl_context import GLContext
from test_shadow_filter import FilterScene, VERTEX
from validate_shaders import ROOT, SHADERS, configure, expand


def main():
    size = 768
    library = expand(SHADERS / "lib/stars.glsl") + expand(SHADERS / "lib/aurora.glsl") + expand(SHADERS / "lib/meteors.glsl")
    fragment = "#version 330 compatibility\n" + library + """
in vec2 uv;
uniform int testMode;
layout(location=0) out vec4 result;
void main() {
    if (testMode == 1) {
        int day = int(gl_FragCoord.x) + int(gl_FragCoord.y) * 768;
        result = vec4(meteorNight(day) ? 1.0 : 0.0, meteorShowerNight(day) ? 1.0 : 0.0, 0.0, 1.0);
        return;
    }
    float azimuth = uv.x * 6.2831853;
    float elevation = uv.y * 1.5707963;
    vec3 direction = vec3(cos(elevation) * cos(azimuth), sin(elevation), cos(elevation) * sin(azimuth));
    if (testMode == 3) {
        float az = meteorRandom(uint(worldDay) ^ 0xa341316cu) * 6.2831853;
        vec3 center = vec3(cos(0.9) * cos(az), sin(0.9), cos(0.9) * sin(az));
        vec3 right = normalize(cross(center, vec3(0, 1, 0)));
        vec3 vertical = cross(center, right);
        vec3 origin = normalize(center + right * (uv.x - 0.5) + vertical * (uv.y - 0.5));
        uint seed = uint(gl_FragCoord.x) + uint(gl_FragCoord.y) * 768u;
        vec3 tangent = meteorTangent(origin, seed, true);
        // 在朝向流星雨中心的透视相机中测量轨迹方向，而非比较球面切向量。
        vec3 delta = tangent * dot(origin, center) - origin * dot(tangent, center);
        result = vec4(normalize(vec2(dot(delta, right), dot(delta, vertical))), 0, 1);
        return;
    }
    result = vec4(testMode == 2 ? proceduralStars(direction) : proceduralMeteors(direction), 1.0);
}
"""
    with GLContext() as gl:
        target = FilterScene(gl, size=size)
        variants = {
            "shower": {"METEOR_NIGHT_CHANCE": "1.0", "METEOR_SHOWER_CHANCE": "1.0"},
            "conditional_all": {"METEOR_SHOWER_CHANCE": "1.0"},
            "conditional_none": {"METEOR_SHOWER_CHANCE": "0.0"},
            "default": {}, "never": {"METEOR_NIGHT_CHANCE": "0.0"},
            "always": {"METEOR_NIGHT_CHANCE": "1.0"},
            "off": {"METEORS_ENABLED": "0", "METEOR_NIGHT_CHANCE": "1.0"},
            "stars_off": {"STARS_ENABLED": "0"},
            "stars_dim": {"STAR_BRIGHTNESS": "0.5"},
            "stars_sparse": {"STAR_DENSITY": "0.25"},
            "stars_large": {"STAR_SIZE": "2.0"},
            "stars_white": {"STAR_COLOR_STRENGTH": "0.0"},
            "stars_still": {"STAR_TWINKLE": "0.0"},
            "gold": {"METEOR_NIGHT_CHANCE": "1.0", "METEOR_COLOR": "2"},
            "dim": {"METEOR_NIGHT_CHANCE": "1.0", "METEOR_BRIGHTNESS": "0.5"},
            "wide": {"METEOR_NIGHT_CHANCE": "1.0", "METEOR_WIDTH": "2.0"},
            "long": {"METEOR_NIGHT_CHANCE": "1.0", "METEOR_LENGTH": "12.0"},
        }
        programs = {}
        try:
            for key, options in variants.items():
                if key not in ("default", "never", "shower", "conditional_all", "conditional_none"):
                    options = {**options, "METEOR_SHOWER_CHANCE": "0.0"}
                programs[key] = gl.program(VERTEX, configure(fragment, {"FANTASY_SKY": "0", **options}))

            def render(key="always", seconds=0.0, mode=0, day=1, time=18000, rain=0.0, sunlight=-1.0):
                program = programs[key]
                gl.function("glUseProgram", None, c.c_uint)(program)
                locate = gl.function("glGetUniformLocation", c.c_int, c.c_uint, c.c_char_p)
                for name, value in (("worldDay", day), ("worldTime", time), ("testMode", mode)):
                    gl.function("glUniform1i", None, c.c_int, c.c_int)(locate(program, name.encode()), value)
                for name, value in (("frameTimeCounter", seconds), ("rainStrength", rain)):
                    gl.function("glUniform1f", None, c.c_int, c.c_float)(locate(program, name.encode()), value)
                matrix = np.eye(4, dtype=np.float32)
                gl.function("glUniformMatrix4fv", None, c.c_int, c.c_int, c.c_ubyte, c.c_void_p)(
                    locate(program, b"gbufferModelViewInverse"), 1, 0, matrix.ctypes.data_as(c.c_void_p))
                gl.function("glUniform3f", None, c.c_int, c.c_float, c.c_float, c.c_float)(
                    locate(program, b"sunPosition"), 0, sunlight, 0)
                gl.function("glDrawArrays", None, c.c_uint, c.c_int, c.c_int)(0x0004, 0, 3)
                pixels = np.empty((size, size, 4), dtype=np.float32)
                gl.function("glReadPixels", None, c.c_int, c.c_int, c.c_int, c.c_int,
                            c.c_uint, c.c_uint, c.c_void_p)(0, 0, size, size, 0x1908, 0x1406,
                                                          pixels.ctypes.data_as(c.c_void_p))
                assert gl.function("glGetError", c.c_uint)() == 0
                assert np.isfinite(pixels).all()
                return pixels[..., :3]

            chance = render("default", mode=1)
            for day in (1, 17, 2048):
                headings = render("shower", mode=3, day=day)
                assert np.max(np.abs(headings - headings[0, 0])) < 1e-5, "流星雨不同起点应具有统一投影方向"
                assert headings[..., 1].min() > 0, "流星雨应沿相同方向划过"
            fraction = float(chance[..., 0].mean())
            assert abs(fraction - 0.15) < 0.003, fraction
            assert np.array_equal(chance, render("default", mode=1, seconds=999, time=23000))
            assert render("never", mode=1).max() == 0
            assert render("always", mode=1)[..., 0].min() == 1
            conditional = chance[..., 1].sum() / chance[..., 0].sum()
            assert abs(conditional - 0.5) < 0.006, conditional
            assert np.all(chance[..., 1] <= chance[..., 0]), "非流星夜不得成为流星雨夜"
            all_showers = render("conditional_all", mode=1)
            assert np.array_equal(all_showers[..., 0], all_showers[..., 1])
            assert render("conditional_none", mode=1)[..., 1].max() == 0
            assert render("shower", mode=1)[..., :2].min() == 1
            samples = [(float(render(seconds=t).sum()), t) for t in np.arange(0, 30, 0.5)]
            _, moment = max(samples)
            assert max(samples)[0] > 1
            visible = render(seconds=moment)
            assert np.array_equal(visible, render(seconds=moment)), "相同状态应产生相同流星"
            moving = render(seconds=moment + 0.1)
            assert moving.max() > 0 and not np.allclose(visible, moving), "流星应连续移动"
            assert render(seconds=moment + 3).max() == 0, "流星必须在持续时间后消退"
            for key in ("never", "off"):
                assert render(key, seconds=moment).max() == 0
            assert render(seconds=moment, rain=1).max() == 0
            assert render(seconds=moment, sunlight=1).max() == 0
            assert render(seconds=moment, time=6000).max() == 0
            assert np.allclose(render("dim", seconds=moment), visible * 0.5, atol=1e-5)
            assert render("wide", seconds=moment).sum() > visible.sum()
            assert render("long", seconds=moment).sum() > visible.sum()
            gold = render("gold", seconds=moment)
            assert gold[..., 0].sum() > gold[..., 2].sum()
            stars = render("default", mode=2)
            assert render("stars_off", mode=2).max() == 0
            assert np.allclose(render("stars_dim", mode=2), stars * 0.5, atol=1e-5)
            assert render("stars_sparse", mode=2).sum() < stars.sum()
            assert render("stars_large", mode=2).sum() > stars.sum()
            white = render("stars_white", mode=2)
            assert np.allclose(white[..., 0], white[..., 2])
            assert np.array_equal(render("stars_still", mode=2), render("stars_still", mode=2, seconds=5))
            assert not np.allclose(stars, render("default", mode=2, seconds=5))
            shower_samples = [(float(render("shower", seconds=t).sum()), t) for t in np.arange(0, 30, 0.5)]
            assert sum(v for v,t in shower_samples) > sum(v for v,t in samples) * 3
            _, shower_time = max(shower_samples)
            shower = render("shower", seconds=shower_time)
            assert np.array_equal(shower, render("shower", seconds=shower_time))
            assert render("shower", seconds=shower_time, rain=1).max() == 0
            assert render("shower", seconds=shower_time, time=6000).max() == 0
            shower_rgb = shower + np.array([0.002, 0.004, 0.009])
            shower_rgb /= 1 + np.maximum(shower_rgb.max(axis=2, keepdims=True) - 0.8, 0)
            Image.fromarray(np.uint8(np.clip(shower_rgb[::-1], 0, 1) ** (1/2.2) * 255)).save(artifact_path('meteor-shower-preview.png'))
            print(f"PASS: conditional showers {conditional:.4%}, all nights {chance[..., 1].mean():.4%}; nested selection, boundaries, density and weather")
            rgb = visible + render("default", mode=2, seconds=moment) + np.array([0.002, 0.004, 0.009])
            rgb /= 1 + np.maximum(rgb.max(axis=2, keepdims=True) - 0.8, 0)
            path = artifact_path('meteors-preview.png')
            path.parent.mkdir(exist_ok=True)
            Image.fromarray(np.uint8(np.clip(rgb[::-1], 0, 1) ** (1 / 2.2) * 255)).save(path)
            print(f"PASS: {fraction:.4%} meteor nights over {size*size} dates; deterministic selection, motion, fading, weather and options")
            print(f"Preview: {path}")
        finally:
            for program in programs.values():
                gl.delete_program(program)
            target.close()


if __name__ == "__main__":
    main()
