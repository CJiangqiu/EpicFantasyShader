#ifndef EFS_AURORA
#define EFS_AURORA

// 群系温度经配置表达式转换为平滑寒冷权重，跨越边界时光幕逐渐淡入淡出。
uniform float auroraColdFactor;

float auroraNoise(vec2 p) {
    vec2 cell = floor(p);
    vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    float a = starHash(vec3(cell, 71.0)).x;
    float b = starHash(vec3(cell + vec2(1, 0), 71.0)).x;
    float c = starHash(vec3(cell + vec2(0, 1), 71.0)).x;
    float d = starHash(vec3(cell + vec2(1, 1), 71.0)).x;
    return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}

vec3 auroraGroup(vec3 direction, float time, float variation) {
    vec2 horizontal = direction.xz / max(length(direction.xz), 0.0001);
    float elevation = asin(clamp(direction.y, -1.0, 1.0));
    
    vec3 color = vec3(0.0);
    // 三条舒展光带构成主体，短光幕只在局部提供折叠与光柱。
    const float azimuths[4] = float[4](-0.18, 0.10, -0.04, 0.42);
    const float elevations[4] = float[4](0.28, 0.46, 0.67, 0.39);
    const float lengths[4] = float[4](0.72, 0.51, 0.60, 0.23);
    const float slopes[4] = float[4](0.08, -0.07, 0.17, 0.05);
    for (int ribbon = 0; ribbon < 4; ++ribbon) {
        float layer = float(ribbon);
        vec3 seed = starHash(vec3(layer, 37.0 + variation, 19.0));
        float azimuth = azimuths[ribbon];
        vec2 center = vec2(sin(azimuth), cos(azimuth));
        vec2 tangent = vec2(center.y, -center.x);
        float along = atan(dot(horizontal, tangent), dot(horizontal, center));
        float halfWidth = lengths[ribbon] * AURORA_SIZE;
        float extent = 1.0 - smoothstep(halfWidth * 0.60, halfWidth, abs(along));
        if (extent <= 0.0001) continue;
        float phase = seed.z * 6.283185 + time * 0.22;
        // 主光带保持连续、平缓的弧线，细束向上延伸而不整体扭转。
        float folded = along;
        float arc = along * slopes[ribbon] + (0.018 + layer * 0.013) * sin(along * 4.0 + phase);
        float fold = auroraNoise(vec2(along * 3.5 + layer * 13.7, time * 0.25));
        float base = elevations[ribbon] + arc + (fold - 0.5) * 0.035;
        float column = auroraNoise(vec2(along * 9.0 + layer * 17.0, time * 0.18));
        float columnHeight = (0.085 + 0.035 * column) * AURORA_HEIGHT;
        if (ribbon == 3) {
            // 独立的短光幕在有限范围内形成褶皱，端部淡出连接周围夜空。
            float localFold = exp(-along * along * 32.0);
            folded += localFold * 0.022 * sin(elevation * 8.0 + phase);
            base += localFold * 0.060 * sin(along * 12.0 + phase);
            columnHeight = (0.12 + 0.13 * column * column) * AURORA_HEIGHT;
        }
        float height = (elevation - base) / columnHeight;
        float lowerEdge = smoothstep(-0.10, 0.09, height);
        float upperFade = exp(-max(height, 0.0) * 1.6)
                        * (1.0 - smoothstep(0.55, 1.30, height));
        float strands = auroraNoise(vec2(folded * 83.0 + time, layer * 23.0));
        float fine = auroraNoise(vec2(folded * 181.0 + time * 0.65, layer * 7.0));
        float curtain = (0.18 + 0.70 * strands * strands + 0.12 * fine) * lowerEdge * upperFade;
        float edge = exp(-abs(height - 0.07) * 11.0) * lowerEdge;
        float haze = exp(-abs(height - 0.15) * 4.0) * 0.012;
        vec3 tint = mix(vec3(0.27, 1.0, 0.18), vec3(0.10, 0.66, 0.37), smoothstep(0.05, 0.85, height));
        tint = mix(tint, vec3(0.24, 0.29, 0.48), smoothstep(0.85, 1.70, height));
        float gaps = smoothstep(0.15, 0.75, auroraNoise(vec2(folded * 5.5 + layer * 19.0, time * 0.15)));
        color += tint * (curtain * 0.46 + edge * 0.09 + haze) * (0.22 + gaps * 0.78) * extent;
    }
    return color * (1.0 - smoothstep(1.10, 1.35, elevation));
}

vec3 proceduralAurora(vec3 direction) {
#if AURORA_ENABLED == 0
    return vec3(0.0);
#else
    float visibility = nightSkyVisibility(direction) * clamp(auroraColdFactor, 0.0, 1.0);
    if (visibility <= 0.0001 || direction.y <= 0.02) return vec3(0.0);
    float time = frameTimeCounter * 0.025 * AURORA_SPEED;
    // 各区域使用独立正交坐标系，区域内光带同向，天空两侧及头顶均有分布。
    vec3 color = auroraGroup(direction, time, 0.0);
    vec3 opposite = vec3(-direction.x, direction.y, -direction.z);
    color += auroraGroup(opposite, time + 3.0, 7.0) * 0.85;
    vec3 overhead = vec3(direction.x, 0.622 * direction.y - 0.783 * direction.z,
                        0.783 * direction.y + 0.622 * direction.z);
    color += auroraGroup(normalize(overhead), time + 7.0, 19.0) * 0.75;
    return color * visibility * AURORA_BRIGHTNESS;
#endif
}

#endif
