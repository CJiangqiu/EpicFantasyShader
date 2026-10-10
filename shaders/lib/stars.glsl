#ifndef EFS_STARS
#define EFS_STARS
#include "/lib/settings.glsl"

uniform mat4 gbufferProjectionInverse;
uniform mat4 gbufferModelViewInverse;
uniform vec3 sunPosition;
uniform float rainStrength;
uniform float viewWidth;
uniform float viewHeight;
uniform float frameTimeCounter;

vec3 skyDirection(vec2 uv) {
    vec4 view = gbufferProjectionInverse * vec4(uv * 2.0 - 1.0, 1.0, 1.0);
    return normalize(mat3(gbufferModelViewInverse) * view.xyz);
}

vec3 starHash(vec3 p) {
    p = fract(p * vec3(0.1031, 0.1030, 0.0973));
    p += dot(p, p.yxz + 33.33);
    return fract((p.xxy + p.yxx) * p.zyx);
}

vec3 starColor(float choice) {
    // 白色占多数，色温差异只使用蓝白、暖黄与低饱和橙红。
    if (choice < 0.70) return vec3(1.0, 0.97, 0.92);
    if (choice < 0.84) return vec3(0.70, 0.83, 1.0);
    if (choice < 0.95) return vec3(1.0, 0.84, 0.60);
    return vec3(1.0, 0.62, 0.44);
}

float nightSkyVisibility(vec3 direction) {
    float sunHeight = normalize(mat3(gbufferModelViewInverse) * sunPosition).y;
    float visibility = (1.0 - smoothstep(-0.16, -0.02, sunHeight))
                     * smoothstep(0.02, 0.22, direction.y)
                     * pow(1.0 - clamp(rainStrength, 0.0, 1.0), 2.0);
    return visibility;
}

vec3 proceduralStars(vec3 direction) {
#if STARS_ENABLED == 0
    return vec3(0.0);
#else
    float footprint = max(length(dFdx(direction)), length(dFdy(direction)));
    float visibility = nightSkyVisibility(direction);
    if (visibility <= 0.0) return vec3(0.0);

    // 六个方向面只负责分配星点；距离在单位球面计算，避免边缘星点拉长。
    vec3 a = abs(direction);
    vec3 n, u, v;
    float face;
    if (a.x >= a.y && a.x >= a.z) {
        n = vec3(sign(direction.x), 0, 0); u = vec3(0, 0, 1); v = vec3(0, 1, 0);
        face = direction.x > 0.0 ? 0.0 : 1.0;
    } else if (a.y >= a.z) {
        n = vec3(0, sign(direction.y), 0); u = vec3(1, 0, 0); v = vec3(0, 0, 1);
        face = direction.y > 0.0 ? 2.0 : 3.0;
    } else {
        n = vec3(0, 0, sign(direction.z)); u = vec3(1, 0, 0); v = vec3(0, 1, 0);
        face = direction.z > 0.0 ? 4.0 : 5.0;
    }
    vec2 plane = vec2(dot(direction, u), dot(direction, v)) / dot(direction, n);
    vec2 cell = floor((plane * 0.5 + 0.5) * 24.0);
    vec3 random = starHash(vec3(cell, face + 11.0));
    if (random.z > 0.20 * STAR_DENSITY) return vec3(0.0);
    vec2 center = (cell + mix(vec2(0.20), vec2(0.80), random.xy)) / 24.0 * 2.0 - 1.0;
    vec3 point = normalize(n + u * center.x + v * center.y);
    vec3 variation = starHash(vec3(cell + 47.0, face + 29.0));
    float radius = mix(0.00045, 0.0015, pow(variation.x, 2.0)) * STAR_SIZE;
    // 亚像素星点通过覆盖率衰减保留能量，避免所有星星变成同样大的亮块。
    float width = max(footprint * 0.65, 0.00001);
    float disk = 1.0 - smoothstep(max(radius - width, 0.0), radius + width, length(direction - point));
    float energy = min(1.0, radius * radius / (width * width));
    float brightness = mix(0.45, 2.8, pow(variation.y, 3.0));
    // 平滑闪烁只改变亮度，星点方向与轮廓不随时间漂移。
    float twinkle = 1.0 + STAR_TWINKLE * sin(frameTimeCounter * STAR_TWINKLE_SPEED
                                          * (1.0 + variation.z) + variation.x * 6.2831853);
    vec3 color = mix(vec3(1.0), starColor(variation.z), STAR_COLOR_STRENGTH);
    return color * disk * energy * brightness * visibility * STAR_BRIGHTNESS * twinkle;
#endif
}

#endif
