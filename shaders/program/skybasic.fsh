#include "/lib/sky_background.glsl"
#ifdef WORLD_OVERWORLD
#include "/lib/stars.glsl"
#include "/lib/aurora.glsl"
#include "/lib/meteors.glsl"
#endif

uniform int renderStage;
in vec4 vertexColor;
/* DRAWBUFFERS:0 */
layout(location = 0) out vec4 scene;

void main() {
    // 加载器即使提交原版星点几何，也不得写入天空颜色。
#ifdef MC_RENDER_STAGE_STARS
    if (renderStage == MC_RENDER_STAGE_STARS) discard;
#endif
    scene = vec4(toLinear(vertexColor.rgb), vertexColor.a);
#ifdef WORLD_OVERWORLD
#ifdef MC_RENDER_STAGE_SKY
    if (renderStage == MC_RENDER_STAGE_SKY) {
        vec3 direction = skyDirection(gl_FragCoord.xy / vec2(viewWidth, viewHeight));
        scene = vec4(skyBackground(direction) + proceduralNightSky(direction), 1.0);
    }
#endif
#endif
}
