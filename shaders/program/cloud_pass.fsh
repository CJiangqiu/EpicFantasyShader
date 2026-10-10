#include "/lib/cloud_render.glsl"
in vec2 texcoord;
const int RGBA16F = 34842;
const int R32F = 33326;
const int colortex1Format = RGBA16F;
const int colortex2Format = R32F;
const bool colortex1Clear = false;
const bool colortex2Clear = false;
/* DRAWBUFFERS:12 */
layout(location=0) out vec4 cloudLayer;
layout(location=1) out float cloudDepth;
void main() {
    cloudLayer = vec4(0.0,0.0,0.0,1.0);
    cloudDepth = CLOUD_DISTANCE;
#if defined(WORLD_OVERWORLD) && VOLUMETRIC_CLOUDS == 1
    cloudDepth = cloudLimit(texcoord);
    cloudLayer = renderCloudLayer(texcoord,cloudDepth,ivec2(texcoord * vec2(textureSize(depthtex0,0))));
    vec3 ray;
    float start, end;
    if (cloudInterval(texcoord,cloudDepth,ray,start,end)) {
        // 保存相对天空的散射差值，全分辨率合成时保持地平线底色连续。
        cloudLayer.rgb -= skyBackground(ray) * (1.0-cloudLayer.a);
    }
#endif
}
