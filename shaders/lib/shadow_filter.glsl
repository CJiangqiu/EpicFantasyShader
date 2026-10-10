#ifndef EFS_SHADOW_FILTER
#define EFS_SHADOW_FILTER

uniform sampler2DShadow shadowtex1;

vec2 receiverGradient(vec3 coordinate) {
    vec3 dx = dFdx(coordinate);
    vec3 dy = dFdy(coordinate);
    float determinant = dx.x * dy.y - dx.y * dy.x;
    if (abs(determinant) < 1e-12) return vec2(0.0);
    return clamp(vec2(dy.y * dx.z - dx.y * dy.z,
                      dx.x * dy.z - dy.x * dx.z) / determinant, -4.0, 4.0);
}

float filteredShadow(vec3 coordinate, vec2 gradient) {
#if SHADOW_FILTER == 0
    const int grid = 2;
#elif SHADOW_FILTER == 1
    const int grid = 3;
#else
    const int grid = 4;
#endif
    float texel = 1.0 / float(shadowMapResolution);
    float visibility = 0.0;
    float weights = 0.0;
    for (int y = 0; y < grid; ++y) {
        for (int x = 0; x < grid; ++x) {
            vec2 point = (vec2(x, y) + 0.5) / float(grid) * 2.0 - 1.0;
            vec2 offset = point * (1.5 * SHADOW_SOFTNESS * texel);
            float weight = (1.0 - 0.5 * abs(point.x)) * (1.0 - 0.5 * abs(point.y));
            // 四个硬件比较共用一个参考深度，偏移量需覆盖其中最浅的接收面位置。
            vec2 fraction = fract((coordinate.xy + offset) / texel - 0.5);
            vec2 shallowest = min(-fraction * gradient, (1.0 - fraction) * gradient);
            float comparisonBias = 0.000008 - (shallowest.x + shallowest.y) * texel;
            float depth = coordinate.z + dot(gradient, offset) - comparisonBias;
            visibility += texture(shadowtex1, vec3(coordinate.xy + offset, depth)) * weight;
            weights += weight;
        }
    }
    return visibility / weights;
}

#endif
