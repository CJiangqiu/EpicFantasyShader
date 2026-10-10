#ifndef EFS_HANDHELD_LIGHT
#define EFS_HANDHELD_LIGHT

uniform int heldItemId;
uniform int heldItemId2;
uniform int heldBlockLightValue;
uniform int heldBlockLightValue2;

vec4 heldEmission(int item, int blockLight) {
    // item.properties 提供主副手物品的光色与亮度分类编号。
    // 未分类物品沿用加载器提供的亮度，已分类物品提供对应的光色与最低亮度。
    vec3 color = vec3(1.0, 0.63, 0.28);
    float level = float(clamp(blockLight, 0, 15));
    if (item == 11001) level = max(level, 14.0);
    if (item == 11002) level = max(level, 15.0);
    if (item == 11003) {
        color = vec3(0.25, 0.72, 1.0);
        level = max(level, 10.0);
    }
    if (item == 11004) {
        color = vec3(1.0, 0.12, 0.045);
        level = max(level, 7.0);
    }
    if (item == 11005) {
        color = vec3(0.68, 0.86, 1.0);
        level = max(level, 15.0);
    }
    if (item == 11006) {
        color = vec3(0.88, 0.80, 1.0);
        level = max(level, 14.0);
    }
    return vec4(color, level / 15.0);
}

vec3 illuminateHeldItem(vec3 displacement, vec3 normal, vec4 emission) {
    float distanceSquared = dot(displacement, displacement);
    float radius = HANDHELD_LIGHT_RANGE * sqrt(emission.a);
    if (radius <= 0.0 || distanceSquared >= radius * radius) return vec3(0.0);
    float distanceToLight = sqrt(max(distanceSquared, 1e-6));
    float edge = 1.0 - smoothstep(0.65 * radius, radius, distanceToLight);
    float incidence = max(dot(normal, displacement / distanceToLight), 0.0);
    // 距离衰减和范围边缘均连续；近光源保留有限亮度，避免除零与过曝。
    float attenuation = edge / (1.0 + 0.12 * distanceSquared);
    return emission.rgb * emission.a * attenuation * incidence * HANDHELD_LIGHT_STRENGTH * 2.0;
}

vec3 handheldLighting(vec3 position, vec3 normal, mat4 viewInverse) {
#ifdef HANDHELD_LIGHT
    // 光源位于相机附近，近似手持位置，不依赖手部动画或实体坐标列表。
    vec3 source = (viewInverse * vec4(0.0, -0.25, -0.4, 1.0)).xyz;
    vec3 displacement = source - position;
    return illuminateHeldItem(displacement, normal, heldEmission(heldItemId, heldBlockLightValue))
         + illuminateHeldItem(displacement, normal, heldEmission(heldItemId2, heldBlockLightValue2));
#else
    return vec3(0.0);
#endif
}

#endif
