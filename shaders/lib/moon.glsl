#ifndef EFS_MOON
#define EFS_MOON

uniform sampler2D gaux1;

vec4 renderMoon(vec2 p, int phase, float brightness, vec3 background) {
    float radial = length(p);
    float pixelWidth = max(fwidth(radial), 0.0001);
    float coverage = 1.0 - smoothstep(1.0 - pixelWidth, 1.0 + pixelWidth, radial);
    if (coverage <= 0.0) return vec4(0.0);
    float z = sqrt(max(1.0 - dot(p, p), 0.0));
    float angle = float(phase % 8) * 0.78539816339;
    vec3 light = vec3(-sin(angle), 0.0, cos(angle));
    float terminator = dot(vec3(p, z), light);
    float lit = smoothstep(-pixelWidth, pixelWidth, terminator);
    // 新月不保留边缘亮环；其余月相由球面上的光照分界确定。
    if (phase % 8 == 4) lit = 0.0;
    // 月面图采用正面圆盘投影，与原版月相图集的局部坐标保持一致。
    vec4 surface = texture(gaux1, clamp(p * 0.5 + 0.5, 0.0, 1.0));
    // 图片已含满月的明暗细节，不额外叠加球面边缘压暗。
    // 暗面保留天空底色，但完整月盘遮住更远的星点和星云。
    vec3 color = mix(background, toLinear(surface.rgb) * brightness, lit);
    return vec4(color, coverage * surface.a);
}

#endif
