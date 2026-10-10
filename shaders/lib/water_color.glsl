#ifndef EFS_WATER_COLOR
#define EFS_WATER_COLOR
#include "/lib/settings.glsl"

uniform float waterOcean;
uniform float waterRiver;

vec3 waterTint(float depth) {
    float ocean = clamp(waterOcean, 0.0, 1.0);
    float river = clamp(waterRiver, 0.0, 1.0) * (1.0-ocean);
    float deep = 1.0-exp(-max(depth-2.0,0.0)/12.0);
    vec3 neutral = mix(vec3(0.012),vec3(0.003),deep);
    vec3 sea = mix(vec3(0.025,0.16,0.32),vec3(0.006,0.027,0.105),deep);
    vec3 stream = mix(vec3(0.075,0.20,0.11),vec3(0.012,0.065,0.033),deep);
    return neutral * (1.0-ocean-river) + sea * ocean + stream * river;
}

float waterAbsorption(float depth) {
    // 两格以内只保留极轻的表面覆盖，深水吸收在阈值处平滑接入。
    float excess = max(depth-2.0,0.0);
    float optical = excess * excess / (excess + 2.0);
    return 1.0-exp(-optical * WATER_OPACITY * 0.30);
}

vec3 underwaterFog(vec3 color, float waterDistance) {
    float depth = max(waterDistance,0.0);
    float absorption = waterAbsorption(depth * WATER_FOG_DENSITY);
    return mix(color,waterTint(depth) * 0.35,absorption);
}

#endif
