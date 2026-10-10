#ifndef EFS_METEORS
#define EFS_METEORS

uniform int worldDay;
uniform int worldTime;

uint meteorHash(uint value) {
    value ^= value >> 16u;
    value *= 0x7feb352du;
    value ^= value >> 15u;
    value *= 0x846ca68bu;
    return value ^ (value >> 16u);
}

float meteorRandom(uint value) {
    return float(meteorHash(value) >> 8u) / 16777216.0;
}

bool meteorNight(int day) {
    // 整数日期决定整晚的抽签结果，不依赖帧数、镜头或光影重载。
    return meteorRandom(uint(day) ^ 0x9e3779b9u) < METEOR_NIGHT_CHANCE;
}

bool meteorShowerNight(int day) {
    // 第二次抽签使用独立种子，且只在流星夜成立时生效。
    return meteorNight(day) && meteorRandom(uint(day) ^ 0x51ed270bu) < METEOR_SHOWER_CHANCE;
}

vec3 meteorTangent(vec3 origin, uint seed, bool shower) {
    vec3 side = normalize(cross(origin, vec3(0, 1, 0)));
    vec3 down = normalize(cross(origin, side));
    if (!shower) return normalize(down + side * mix(-0.9, 0.9, meteorRandom(seed + 3u)));
    // 同一片天空共用运动方向，投影到各起点的切平面以保持球面轨迹。
    float azimuth = meteorRandom(uint(worldDay) ^ 0xa341316cu) * 6.2831853;
    vec3 center = vec3(cos(0.9) * cos(azimuth), sin(0.9), cos(0.9) * sin(azimuth));
    vec3 commonSide = normalize(cross(center, vec3(0, 1, 0)));
    vec3 commonDown = normalize(cross(center, commonSide));
    vec3 travel = normalize(commonDown + commonSide * 0.65);
    return normalize(travel - origin * dot(travel, origin));
}

vec3 renderMeteor(vec3 direction, float pixelWidth, float visibility, int lane, bool shower) {
    // 流星雨由六条独立时间序列组成，每条序列保留完整的出现与消退时间。
    float interval = shower ? max(METEOR_DURATION + 0.5, METEOR_INTERVAL * 0.2) : METEOR_INTERVAL;
    float slot = floor(frameTimeCounter / interval);
    uint seed = meteorHash(uint(worldDay)) ^ meteorHash(uint(slot) + 137u);
    if (shower) seed ^= meteorHash(uint(lane) + 731u);
    float start = meteorRandom(seed) * (interval - METEOR_DURATION);
    float age = mod(frameTimeCounter, interval) - start;
    if (age <= 0.0 || age >= METEOR_DURATION) return vec3(0.0);
    float azimuth = meteorRandom(seed + 1u) * 6.2831853;
    float elevation = mix(0.45, 1.10, meteorRandom(seed + 2u));
    if (shower) {
        // 当晚的流星集中在同一片天空，各自保留起点差异。
        azimuth = meteorRandom(uint(worldDay) ^ 0xa341316cu) * 6.2831853
                + (meteorRandom(seed + 1u) - 0.5) * 1.2;
        elevation = mix(0.65, 1.20, meteorRandom(seed + 2u));
    }
    vec3 origin = vec3(cos(elevation) * cos(azimuth), sin(elevation), cos(elevation) * sin(azimuth));
    vec3 tangent = meteorTangent(origin, seed, shower);
    float travel = age * radians(METEOR_SPEED);
    vec3 head = origin * cos(travel) + tangent * sin(travel);
    vec3 forward = tangent * cos(travel) - origin * sin(travel);
    float along = atan(dot(direction, forward), dot(direction, head));
    float crossTrack = abs(asin(clamp(dot(direction, cross(head, forward)), -1.0, 1.0)));
    float tailLength = min(radians(METEOR_LENGTH), travel);
    float radius = 0.00065 * METEOR_WIDTH;
    float aa = max(pixelWidth * 0.65, 0.00001);
    float trail = 1.0 - smoothstep(max(radius - aa, 0.0), radius + aa, crossTrack);
    trail *= smoothstep(-tailLength, 0.0, along) * (1.0 - smoothstep(0.0, aa, along));
    trail *= min(1.0, radius / aa);
    float headLight = 1.0 - smoothstep(0.0, radius * 2.0 + aa, length(direction - head));
    headLight *= min(1.0, radius * radius * 4.0 / (aa * aa));
    float fade = smoothstep(0.0, 0.12, age) * (1.0 - smoothstep(METEOR_DURATION * 0.65, METEOR_DURATION, age));
#if METEOR_COLOR == 1
    vec3 color = vec3(1.0);
#elif METEOR_COLOR == 2
    vec3 color = vec3(1.0, 0.78, 0.48);
#else
    vec3 color = vec3(0.72, 0.86, 1.0);
#endif
    // 球面背侧与地平线以下不保留尾迹。
    float front = step(0.0, dot(direction, head));
    return color * (trail * 1.8 + headLight * 3.5) * fade * visibility * front * METEOR_BRIGHTNESS;
}

vec3 proceduralMeteors(vec3 direction) {
#if METEORS_ENABLED == 0
    return vec3(0.0);
#else
    float pixelWidth = max(length(dFdx(direction)), length(dFdy(direction)));
    float visibility = nightSkyVisibility(direction);
    if (visibility <= 0.0 || worldTime < 12000 || !meteorNight(worldDay)) return vec3(0.0);
    bool shower = meteorShowerNight(worldDay);
    if (!shower) return renderMeteor(direction, pixelWidth, visibility, 0, false);
    vec3 color = vec3(0.0);
    for (int lane = 0; lane < 6; ++lane) {
        color += renderMeteor(direction, pixelWidth, visibility, lane, true);
    }
    return color;
#endif
}

#include "/lib/fantasy_sky.glsl"

vec3 proceduralNearSky(vec3 direction) {
    return proceduralMeteors(direction) + proceduralAurora(direction);
}

vec3 proceduralNightSky(vec3 direction) {
    return applyFantasySky(direction, proceduralStars(direction)) + proceduralNearSky(direction);
}

#endif
