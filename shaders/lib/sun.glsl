#ifndef EFS_SUN
#define EFS_SUN

vec4 renderSun(vec2 p, float sunHeight) {
    float radial = length(p);
    float width = max(fwidth(radial), 0.0001);
    float disk = 1.0 - smoothstep(max(1.0 - width, 0.0), 1.0 + width, radial);
    float extent = 1.0 + 3.0 * SUN_HALO_SIZE;
    // 光晕在扩大的绘制范围内平滑归零，避免四边形边界裁切。
    float halo = exp(-max(radial - 1.0, 0.0) / (0.70 * SUN_HALO_SIZE))
               * (1.0 - smoothstep(extent * 0.75, extent, radial)) * 0.075 * SUN_HALO_STRENGTH;
    float coverage = disk + (1.0 - disk) * halo;
    float daytime = smoothstep(0.02, 0.45, sunHeight);
    vec3 tint = mix(vec3(1.0, 0.30, 0.065), vec3(1.0, 0.93, 0.76), daytime);
    float limb = mix(0.88, 1.0, sqrt(max(1.0 - min(radial * radial, 1.0), 0.0)));
    return vec4(tint * limb * 3.0 * SUN_BRIGHTNESS, coverage);
}
#endif
