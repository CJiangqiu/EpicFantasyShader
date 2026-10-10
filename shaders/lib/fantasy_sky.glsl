#ifndef EFS_FANTASY_SKY
#define EFS_FANTASY_SKY

float fantasyNoise(vec3 p) {
    vec3 cell = floor(p);
    vec3 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    float a = mix(starHash(cell).x, starHash(cell + vec3(1,0,0)).x, f.x);
    float b = mix(starHash(cell + vec3(0,1,0)).x, starHash(cell + vec3(1,1,0)).x, f.x);
    float c = mix(starHash(cell + vec3(0,0,1)).x, starHash(cell + vec3(1,0,1)).x, f.x);
    float d = mix(starHash(cell + vec3(0,1,1)).x, starHash(cell + vec3(1,1,1)).x, f.x);
    return mix(mix(a,b,f.y), mix(c,d,f.y), f.z);
}

float fantasyCloud(vec3 p) {
    float value = 0.0;
    float weight = 0.57;
    for (int octave = 0; octave < 4; ++octave) {
        value += fantasyNoise(p) * weight;
        p = p * 2.07 + vec3(11.7, 7.3, 19.1);
        weight *= 0.48;
    }
    return value;
}

vec3 fantasyNebula(vec3 direction) {
#if FANTASY_NEBULA == 0
    return vec3(0.0);
#else
    // 三维噪声在球面上连续，较柔和的密度起伏形成透明薄雾与尘埃空隙。
    float angle = radians(NEBULA_ROTATION);
    vec3 sky = vec3(cos(angle) * direction.x - sin(angle) * direction.z,
                    direction.y, sin(angle) * direction.x + cos(angle) * direction.z);
    // 整数速度的闭合轨迹与加载器时钟周期一致，时钟循环时不跳变。
    float phase = frameTimeCounter * (6.2831853 / 3600.0) * NEBULA_SPEED;
    vec3 drift = vec3(sin(phase), cos(phase) - 1.0, sin(phase) * 0.4) * 0.35;
    vec3 p = sky * (4.0 / NEBULA_SCALE) + vec3(7, 13, 2) + drift;
    float cloud = mix(fantasyNoise(p), fantasyCloud(p), NEBULA_DETAIL);
    float dust = fantasyCloud(sky * (11.0 / NEBULA_SCALE) + vec3(23, 4, 17) + drift);
    float band = exp(-pow((dot(sky, normalize(vec3(0.6, -0.35, 0.72)))
                           + (cloud - 0.5) * 0.7) * 3.8 / NEBULA_COVERAGE, 2.0));
    float density = smoothstep(0.22, 0.78, cloud + (NEBULA_DENSITY - 1.0) * 0.18) * band;
    float gaps = mix(1.0, smoothstep(0.25, 0.62, dust), NEBULA_DUST);
#if NEBULA_COLOR == 1
    vec3 low = vec3(0.07, 0.15, 0.48), high = vec3(0.20, 0.48, 0.70);
#elif NEBULA_COLOR == 2
    vec3 low = vec3(0.32, 0.035, 0.16), high = vec3(0.65, 0.18, 0.35);
#elif NEBULA_COLOR == 3
    vec3 low = vec3(0.32, 0.12, 0.035), high = vec3(0.65, 0.42, 0.18);
#else
    vec3 low = vec3(0.20, 0.045, 0.42), high = vec3(0.48, 0.18, 0.65);
#endif
    vec3 tint = mix(low, high, smoothstep(0.25, 0.75, cloud));
    return tint * density * (0.18 + gaps * 0.82) * 0.24 * NEBULA_BRIGHTNESS;
#endif
}

bool bloodMoonNight(int day) {
#if BLOOD_MOON_PERIOD == 0
    return true;
#else
    return ((day % BLOOD_MOON_PERIOD) + BLOOD_MOON_PERIOD) % BLOOD_MOON_PERIOD == BLOOD_MOON_PERIOD - 1;
#endif
}

vec4 fantasySatellite(vec3 direction) {
    // 血月是独立卫星，在每个周期的最后一晚升起，沿独立轨迹穿过天空。
    float orbit = (float(worldTime) - 12000.0) / 12000.0 * 3.14159265;
    vec3 center = normalize(vec3(cos(orbit) * 0.8, sin(orbit) * 0.75, 0.6));
    float radius = sin(radians(BLOOD_MOON_DIAMETER * 0.5));
    float forward = dot(direction, center);
    if (forward <= 0.0) return vec4(0.0);
    vec3 right = normalize(cross(vec3(0,1,0), center));
    vec3 up = cross(center, right);
    vec2 uv = vec2(dot(direction, right), dot(direction, up)) / radius;
    float distanceToCenter = length(uv);
    float aa = max(length(dFdx(direction)), length(dFdy(direction))) / radius;
    float coverage = 1.0 - smoothstep(1.0 - aa, 1.0 + aa, distanceToCenter);
    if (coverage <= 0.0) return vec4(0.0);
    // 球面明暗与不规则陆块保留巨大星体的体积感，轮廓覆盖背景星点。
    vec3 normal = vec3(uv, sqrt(max(0.0, 1.0 - dot(uv,uv))));
    float terrain = fantasyCloud(normal * 5.0 + 31.0);
    float detail = fantasyNoise(normal * 36.0 + 9.0);
    vec3 dark = vec3(0.12, 0.027, 0.016);
    vec3 light = vec3(0.78, 0.32, 0.14);
    vec3 surface = mix(dark, light, smoothstep(0.32, 0.68, terrain));
    surface *= 0.80 + 0.25 * detail;
    // 偏下侧受光形成不满的月面，暗面不自发光，但仍遮挡远处星空。
    float incidence = dot(normal, normalize(vec3(-0.35, -0.80, -0.18)));
    float terminator = smoothstep(-aa, aa, incidence);
    float lighting = 1.10 * max(incidence, 0.0) * terminator;
    return vec4(surface * lighting, coverage);
}

vec3 applyFantasySky(vec3 direction, vec3 background) {
#if FANTASY_SKY == 0
    return background;
#else
    float visibility = nightSkyVisibility(direction);
    if (visibility <= 0.0) return background;
    vec3 color = background + fantasyNebula(direction) * visibility;
#if FANTASY_BLOOD_MOON == 1
    if (bloodMoonNight(worldDay)) {
        vec4 satellite = fantasySatellite(direction);
        color = mix(color, satellite.rgb * visibility, satellite.a);
    }
#endif
    return color;
#endif
}
#endif
