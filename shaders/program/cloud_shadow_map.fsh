#include "/lib/settings.glsl"
uniform float rainStrength;
uniform vec3 shadowLightPosition;
uniform mat4 gbufferModelViewInverse;
#define EFS_CLOUD_SHADOW_MAP_WRITE
#include "/lib/clouds.glsl"
in vec2 texcoord;
// 固定尺寸附件只由准备阶段写入，几何阶段读取当帧透射率。
const int RGBA16F = 34842;
const int colortex7Format = RGBA16F;
const bool colortex7Clear = false;
/* DRAWBUFFERS:7 */
layout(location=0) out vec4 shadowMap;
void main() {
    float transmission = 1.0;
#if defined(WORLD_OVERWORLD) && VOLUMETRIC_CLOUDS == 1 && CLOUD_SHADOWS == 1
    vec3 light = normalize(mat3(gbufferModelViewInverse) * shadowLightPosition);
    if (light.y > 0.02) {
        vec2 plane = cloudShadowCenter(light) + (texcoord - 0.5) * cloudShadowSpan();
        transmission = cloudTransmission(vec3(plane.x,CLOUD_ALTITUDE,plane.y),light,16,rainStrength > 0.0);
    }
#endif
    shadowMap = vec4(transmission,0.0,0.0,1.0);
}
