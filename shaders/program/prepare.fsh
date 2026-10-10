#include "/lib/sky_background.glsl"
#ifdef WORLD_OVERWORLD
#include "/lib/stars.glsl"
#include "/lib/aurora.glsl"
#include "/lib/meteors.glsl"
#endif

in vec2 texcoord;
// 格式名称供加载器识别，数值声明供 GLSL 编译器解析。
const int RGBA16F = 34842;
const int colortex0Format = RGBA16F;
const int colortex5Format = RGBA16F;
const int colortex6Format = RGBA16F;
const bool colortex6Clear = true;
const vec4 colortex6ClearColor = vec4(0.0, 0.0, 0.0, 0.0);
const bool colortex0Clear = true;
/* DRAWBUFFERS:0 */
layout(location = 0) out vec4 scene;

void main() {
    scene = vec4(toLinear(fogColor), 1.0);
#ifdef WORLD_OVERWORLD
    vec3 direction = skyDirection(texcoord);
    scene.rgb = skyBackground(direction) + proceduralNightSky(direction);
#endif
}
