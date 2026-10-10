"""检查着色器引用、入口和配置，并支持本机 OpenGL 编译。"""

import argparse
import json
import re
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHADERS = ROOT / "shaders"
PROFILES = {
    "VEGETATION_OFF": {"VEGETATION_WIND": "0"},
    "WATER_SHAFTS_OFF": {"WATER_LIGHT_SHAFTS": "0"},
    "WATER_DISABLED": {"WATER_REFLECTIONS": "0", "WATER_WAVES": "0", "WATER_FOAM": "0"},
    "FANTASY": {"FANTASY_SKY": "1"},
    "FANTASY_DAILY": {"FANTASY_SKY": "1", "BLOOD_MOON_PERIOD": "0"},
    "FANTASY_NEBULA": {"FANTASY_SKY": "1", "FANTASY_BLOOD_MOON": "0"},
    "FANTASY_MOON": {"FANTASY_SKY": "1", "FANTASY_NEBULA": "0", "BLOOD_MOON_DIAMETER": "36.0"},
    "POTATO": {"shadowMapResolution": "1024", "shadowDistance": "64.0", "SHADOW_FILTER": "0", "CLOUD_SAMPLES": "16", "WATER_SHAFT_SAMPLES": "4"},
    "DEFAULT": {"shadowMapResolution": "2048", "shadowDistance": "96.0", "SHADOW_FILTER": "1", "CLOUD_SAMPLES": "32", "WATER_SHAFT_SAMPLES": "8"},
    "CLOUDS_OFF": {"VOLUMETRIC_CLOUDS": "0"},
    "CLOUD_SHADOWS_OFF": {"CLOUD_SHADOWS": "0"},
    "CLOUD_LIGHTNING_OFF": {"CLOUD_LIGHTNING": "0"},
    "EXTREME": {"shadowMapResolution": "4096", "shadowDistance": "128.0", "SHADOW_FILTER": "2", "CLOUD_SAMPLES": "48", "WATER_SHAFT_SAMPLES": "12"},
    "DISABLED": {"SHADOWS": None},
    "HANDHELD_DISABLED": {"HANDHELD_LIGHT": None},
    "VANILLA_SUN": {"SUN_STYLE": "0"},
    "LARGE_SUN": {"SUN_DIAMETER": "10.0", "SUN_HALO_SIZE": "2.0"},
    "SUN_NO_HALO": {"SUN_HALO_STRENGTH": "0.0"},
    "VANILLA_MOON": {"MOON_STYLE": "0"},
    "AURORA_OFF": {"AURORA_ENABLED": "0"},
    "AURORA_LARGE": {"AURORA_HEIGHT": "2.0", "AURORA_SIZE": "2.0"},
    "SHOWER_NEVER": {"METEOR_SHOWER_CHANCE": "0.0"},
    "SHOWER_ALWAYS": {"METEOR_NIGHT_CHANCE": "1.0", "METEOR_SHOWER_CHANCE": "1.0"},
    "STARS_OFF": {"STARS_ENABLED": "0"},
    "METEORS_OFF": {"METEORS_ENABLED": "0"},
    "SKY_MAX": {"STAR_DENSITY": "2.0", "STAR_SIZE": "2.0", "METEOR_NIGHT_CHANCE": "1.0", "METEOR_COLOR": "1"},
    "METEOR_GOLD": {"METEOR_COLOR": "2", "METEOR_DURATION": "3.0", "METEOR_SPEED": "24.0"},
    "LARGE_MOON": {"MOON_DIAMETER": "16.0"},
}

# 三档完整声明同一组选项，编译验证与预设往返切换覆盖相同的效果组合。
for profile_name in ("POTATO", "DEFAULT", "EXTREME"):
    PROFILES[profile_name].update({"SHADOWS": "", "HANDHELD_LIGHT": ""})
    for option in ("VOLUMETRIC_CLOUDS", "CLOUD_LIGHTNING", "WATER_WAVES", "STARS_ENABLED",
                   "METEORS_ENABLED", "FANTASY_SKY", "FANTASY_BLOOD_MOON", "VEGETATION_WIND"):
        PROFILES[profile_name][option] = "1"
    for option in ("CLOUD_SHADOWS", "WATER_REFLECTIONS", "WATER_LIGHT_SHAFTS", "FANTASY_NEBULA",
                   "AURORA_ENABLED", "WATER_FOAM", "WATER_CAUSTICS", "WATER_REFRACTION"):
        PROFILES[profile_name][option] = "0" if profile_name == "POTATO" else "1"


def expand(path, stack=()):
    path = path.resolve()
    if not path.is_relative_to(SHADERS.resolve()):
        raise ValueError(f"Include outside shader root: {path}")
    if path in stack:
        raise ValueError(f"Include cycle: {path}")
    source = path.read_text(encoding="utf-8")

    def include(match):
        name = match.group(1)
        target = SHADERS / name.lstrip("/") if name.startswith("/") else path.parent / name
        return expand(target, (*stack, path))

    return re.sub(r'^\s*#include\s+"([^"]+)"\s*$', include, source, flags=re.M)


def configure(source, options):
    for name, value in options.items():
        define = rf"^(#define[ \t]+{re.escape(name)})(?:[ \t]+[^\n]*)?$"
        if value is None:
            source = re.sub(define, "", source, flags=re.M)
        elif re.search(define, source, re.M):
            source = re.sub(define, lambda m: m[1] + " " + value, source, flags=re.M)
        else:
            source = re.sub(rf"(const\s+(?:int|float)\s+{re.escape(name)}\s*=\s*)[^;]+;",
                            lambda m: m[1] + value + ";", source)
    return source


def properties(path):
    return dict(line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.lstrip().startswith("#") and "=" in line)


def validate(compile_gpu=False):
    # 加载器按四个标量解析清屏颜色，不支持 GLSL 的单参数向量构造。
    scalar = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?[fF]?"
    for source_path in SHADERS.rglob("*"):
        if source_path.suffix not in (".fsh", ".vsh", ".glsl"):
            continue
        source = source_path.read_text(encoding="utf-8")
        for name, value in re.findall(r"const\s+vec4\s+(\w+ClearColor)\s*=\s*([^;]+);", source):
            if not re.fullmatch(r"vec4\s*\(\s*" + scalar + (r"\s*,\s*" + scalar) * 3 + r"\s*\)", value.strip()):
                raise ValueError(f"清屏颜色必须显式填写四个标量：{source_path} / {name}")
    # 加载器以 Latin-1 读取属性，再按 Java 的换行规则分行；UTF-8 的 0x85 会截断中文注释。
    for path in SHADERS.rglob("*.properties"):
        if b"\x85" in path.read_bytes():
            raise ValueError(f"配置包含会被加载器误判为换行的字节，请将中文说明放入对应 GLSL：{path}")
    entries = sorted(path for path in SHADERS.rglob("*.vsh")
                     if path.parent == SHADERS or path.parent.name in ("world0", "world-1", "world1"))
    if not entries:
        raise ValueError("No shader entry points.")
    pairs = []
    for vertex in entries:
        fragment = vertex.with_suffix(".fsh")
        for path in (vertex, fragment):
            if not path.read_text(encoding="utf-8").startswith("#version 330 compatibility\n"):
                raise ValueError(f"Invalid version declaration: {path}")
        pairs.append((vertex.relative_to(SHADERS), expand(vertex), expand(fragment)))
    for fragment in SHADERS.rglob("*.fsh"):
        if fragment.parent == SHADERS or fragment.parent.name.startswith("world"):
            if not fragment.with_suffix(".vsh").is_file():
                raise ValueError(f"Unpaired fragment entry: {fragment}")
    en = properties(SHADERS / "lang/en_us.lang")
    zh = properties(SHADERS / "lang/zh_cn.lang")
    if en.keys() != zh.keys():
        raise ValueError(f"Translation keys differ: {en.keys() ^ zh.keys()}")
    settings = (SHADERS / "lib/settings.glsl").read_text(encoding="utf-8")
    options = re.findall(r"^#define\s+(\w+).*//\s*\[", settings, re.M)
    options += re.findall(r"^const\s+\w+\s+(\w+).*//\s*\[", settings, re.M) + ["SHADOWS", "HANDHELD_LIGHT"]
    for option in options:
        if "option." + option not in en or "option." + option + ".comment" not in en:
            raise ValueError(f"Missing option translation: {option}")
    props = properties(SHADERS / "shaders.properties")
    if props.get('size.buffer.colortex7') != '256 256':
        raise ValueError('云影附件须为 256×256，与世界投影采样格点匹配')
    for name in ('colortex1','colortex2'):
        if props.get('size.buffer.'+name) != '0.5 0.5':
            raise ValueError('云层颜色和深度附件须使用相同的半宽半高尺寸')
    cloud_pass = (SHADERS/'program/cloud_pass.fsh').read_text(encoding='utf-8')
    if 'DRAWBUFFERS:12' not in cloud_pass or 'colortex2Format = R32F' not in cloud_pass:
        raise ValueError('云层缩小附件须独立写入颜色及浮点距离，不能混写全分辨率背景')
    for directory in (SHADERS,SHADERS/'world0'):
        if '/program/cloud_pass.fsh' not in (directory/'deferred.fsh').read_text(encoding='utf-8'):
            raise ValueError('体积云须先生成独立的颜色和距离附件')
        if '/program/deferred.fsh' not in (directory/'deferred1.fsh').read_text(encoding='utf-8'):
            raise ValueError('反射快照须在完整分辨率云合成阶段输出')
    if any(key.startswith('texture.') and key.endswith(('.colortex7','.gaux4')) for key in props):
        raise ValueError('云影附件不能被自定义纹理覆盖')
    shadow_map = (SHADERS/'program/cloud_shadow_map.fsh').read_text(encoding='utf-8')
    if 'DRAWBUFFERS:7' not in shadow_map:
        raise ValueError('固定尺寸云影附件须独立写入，不能与全分辨率附件混写')
    if props.get('texture.noise') != 'textures/cloud_noise.png':
        raise ValueError('云噪声图集必须绑定到 noisetex')
    noise = (SHADERS / props['texture.noise']).read_bytes()
    if noise[:8] != b'\x89PNG\r\n\x1a\n' or struct.unpack('>II',noise[16:24]) != (657,657) or noise[24:26] != bytes((8,6)):
        raise ValueError('云噪声图集须为 657×657 的 RGBA8 PNG')
    metadata = json.loads((SHADERS/'textures/cloud_noise.png.mcmeta').read_text(encoding='utf-8'))
    if metadata.get('texture') != {'blur':False,'clamp':True}:
        raise ValueError('云噪声图集使用精确角点读取与边界夹取')
    def check_screen(name, parents=()):
        if name in parents:
            raise ValueError(f"配置分组循环引用：{name}")
        if name not in props:
            raise ValueError(f"配置分组缺失：{name}")
        for token in props[name].split():
            if token.startswith("["):
                group = "screen." + token[1:-1]
                if group not in en:
                    raise ValueError(f"配置分组翻译缺失：{group}")
                check_screen(group, (*parents, name))
            elif not token.startswith("<") and token not in options:
                raise ValueError(f"未知配置选项：{token}")
    check_screen("screen")
    if {key[8:] for key in props if key.startswith("profile.")} != {"POTATO", "DEFAULT", "EXTREME"}:
        raise ValueError("Exactly three quality profiles are required.")
    for name, overrides in PROFILES.items():
        if name not in ("POTATO", "DEFAULT", "EXTREME"):
            continue
        expected = {option if value == "" else f"{option}:{value}" for option, value in overrides.items()}
        actual = props["profile." + name].split()
        if set(actual) != expected or len(actual) != len(expected):
            raise ValueError(f"Profile mismatch: {name}")
    print(f"PASS: {len(pairs)} program pairs, includes, option translations, and profiles")
    if compile_gpu:
        from gl_context import GLContext
        with GLContext(load_resources=False) as gl:
            print(gl.description())
            unique = set()
            for profile, options in PROFILES.items():
                for dh_enabled in (False, True):
                    for path, vertex, fragment in pairs:
                        if path.name.startswith("dh_") and not dh_enabled:
                            continue
                        v, f = configure(vertex, options), configure(fragment, options)
                        stages = "#version 330 compatibility\n#define MC_RENDER_STAGE_SKY 1\n#define MC_RENDER_STAGE_STARS 5"
                        v = v.replace("#version 330 compatibility", stages)
                        f = f.replace("#version 330 compatibility", stages)
                        if dh_enabled:
                            v = v.replace("#version 330 compatibility", "#version 330 compatibility\n#define DISTANT_HORIZONS")
                            f = f.replace("#version 330 compatibility", "#version 330 compatibility\n#define DISTANT_HORIZONS")
                        if (v, f) in unique:
                            continue
                        try:
                            program = gl.program(v, f)
                            gl.delete_program(program)
                        except RuntimeError as error:
                            raise RuntimeError(f"{profile}, DH={dh_enabled}: {path}\n{error}") from error
                        unique.add((v, f))
            print(f"PASS: {len(unique)} unique native GLSL program variants compiled and linked")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compile", action="store_true", help="Compile with the local Windows OpenGL driver")
    validate(parser.parse_args().compile)
