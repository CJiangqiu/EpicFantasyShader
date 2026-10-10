#include "/lib/settings.glsl"

uniform vec3 moonPosition;
uniform int moonPhase;
out vec2 texcoord;
out vec2 moonCoord;
out vec2 sunCoord;
out vec4 vertexColor;
flat out int isMoon;

void main() {
    vec4 view = gl_ModelViewMatrix * gl_Vertex;
    vec3 direction = normalize(moonPosition);
    isMoon = dot(view.xyz, direction) > 0.0 ? 1 : 0;
    texcoord = (gl_TextureMatrix[0] * gl_MultiTexCoord0).xy;
    moonCoord = gl_MultiTexCoord0.xy * vec2(4.0, 2.0)
              - vec2(float(moonPhase % 4), float(moonPhase / 4));
    moonCoord = moonCoord * 2.0 - 1.0;
    vertexColor = gl_Color;
    sunCoord = gl_MultiTexCoord0.xy * 2.0 - 1.0;
#if SUN_STYLE == 1 && defined(WORLD_OVERWORLD)
    if (isMoon == 0) {
        vec3 sunDirection = -direction;
        float distanceToCenter = dot(view.xyz, sunDirection);
        vec3 center = sunDirection * distanceToCenter;
        vec3 tangent = view.xyz - center;
        float originalRadius = length(tangent) / max(length(sunCoord), 0.0001);
        float extent = SUN_HALO_STRENGTH > 0.0 ? 1.0 + 3.0 * SUN_HALO_SIZE : 1.03;
        float scale = distanceToCenter * tan(radians(SUN_DIAMETER * 0.5)) / max(originalRadius, 0.0001);
        view.xyz = center + tangent * scale * extent;
        sunCoord *= extent;
    }
#endif
#if MOON_STYLE == 1
#ifdef WORLD_OVERWORLD
    if (isMoon == 1) {
        // 原版月面四边形的半宽为 20，中心距为 100；缩放切向分量控制视直径。
        vec3 center = direction * dot(view.xyz, direction);
        float scale = tan(radians(MOON_DIAMETER * 0.5)) * 100.0 / 20.0;
        // 预留边缘抗锯齿覆盖范围，避免圆面边缘被四边形裁切。
        view.xyz = center + (view.xyz - center) * scale * 1.03;
        moonCoord *= 1.03;
    }
#endif
#endif
    gl_Position = gl_ProjectionMatrix * view;
}
