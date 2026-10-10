#ifndef EFS_SHADOW_PROJECTION
#define EFS_SHADOW_PROJECTION

vec3 distortShadow(vec3 position) {
    // 中心区域分配更多纹素；压缩深度为光源方向上的遮挡物预留范围。
    position.xy /= 0.2 + 0.8 * length(position.xy);
    position.z *= 0.5;
    return position;
}

#endif
