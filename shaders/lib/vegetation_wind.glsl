#ifndef EFS_VEGETATION_WIND
#define EFS_VEGETATION_WIND

uniform vec3 cameraPosition;
uniform float frameTimeCounter;
uniform float rainStrength;
uniform float thunderStrength;

// 可见几何与阴影共用相同的世界坐标风场；材质编号只对应明确列出的植物。
vec3 vegetationWindOffset(vec3 relativePosition, vec3 midBlock, int plant) {
#if VEGETATION_WIND == 1 && defined WORLD_OVERWORLD
    if (plant < 10101 || plant > 10110) return vec3(0.0);
    bool leaves = plant == 10110;
    bool stalk = plant == 10105 || plant == 10109;
    bool aquatic = plant >= 10106 && plant <= 10109;
    bool upper = plant == 10104 || plant == 10108;
    bool tall = upper || plant == 10103 || plant == 10107;

    // at_midBlock 为指向方块中心的偏移，单位为 1/64 方块。
    float height = clamp(0.5 - midBlock.y / 64.0, 0.0, 1.0);
    vec3 anchor = relativePosition + midBlock / 64.0;
    if (upper) anchor.y -= 1.0;
    if (leaves || stalk) anchor = relativePosition;
    float fade = 1.0 - smoothstep(64.0, 160.0, length(anchor));
    if (fade <= 0.0) return vec3(0.0);
    float heightWeight = (height + (upper ? 1.0 : 0.0)) / (tall ? 2.0 : 1.0);
    float bend = leaves || stalk ? 1.0 : heightWeight * heightWeight;

    float strength = 0.15 * WIND_GRASS_STRENGTH;
    if (tall) strength *= 1.7;
    if (plant == 10102) strength = 0.07 * WIND_CROP_STRENGTH;
    if (plant == 10105) strength = 0.018 * WIND_REED_STRENGTH;
    if (aquatic) strength = (plant == 10109 ? 0.025 : (tall ? 0.12 : 0.055)) * WIND_WATER_STRENGTH;
    if (leaves) strength = 0.04 * WIND_LEAF_STRENGTH;

    // 整数空间频率保证坐标回绕连续；所有速度档位的时间相位均在一小时处闭合。
    vec3 p = mod(anchor + cameraPosition, 512.0) * (6.28318530718 / 512.0);
    float t = mod(frameTimeCounter, 3600.0) * (6.28318530718 / 3600.0) * VEGETATION_WIND_SPEED;
    float rate = aquatic ? 0.5 : 1.0;
    float gust = 0.65 + 0.35 * sin(dot(p.xz, vec2(3.0, 2.0)) - t * 32.0);
    float wave = sin(dot(p, vec3(19.0, 4.0, 13.0)) + t * (640.0 * rate));
    float flutter = sin(dot(p, vec3(37.0, 8.0, -23.0)) - t * (1088.0 * rate));
    float weather = aquatic ? 1.0 : 1.0 + 0.5 * rainStrength + 0.3 * thunderStrength;
    // 主风向偏向 X 轴，横向细摆避免所有植物作完全一致的往返运动。
    vec2 drift = vec2(0.92, 0.39) * (0.25 * gust + 0.65 * wave * gust);
    drift += vec2(-0.39, 0.92) * (0.18 * flutter);
    return vec3(drift.x, 0.0, drift.y) * (strength * bend * fade * weather);
#else
    return vec3(0.0);
#endif
}

#endif
