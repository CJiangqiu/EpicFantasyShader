#ifndef EFS_WATER_HANDOFF
#define EFS_WATER_HANDOFF
#ifdef DISTANT_HORIZONS
float waterHandoffDistance() {
    // 提前交接为普通区块边界和远景简化留出余量。
    return max(16.0,far-64.0);
}

bool waterUseDistantFloor(bool nearFound, vec3 nearPoint, vec3 distantPoint) {
    // 近景有效实体优先，避免简化水底随视角变化抢占精细水底。
    if (!nearFound) return true;
    if (length(nearPoint.xz)<waterHandoffDistance()) return false;
    return length(distantPoint)<length(nearPoint);
}

#ifndef DH_WATER
uniform sampler2D colortex6;
bool waterCoveredByDistant(vec2 uv, vec3 position, vec3 normal) {
    vec4 coverage=texelFetch(colortex6,ivec2(gl_FragCoord.xy),0);
    // 仅合并同一高度的水面顶面，瀑布和上下分离的水体保持独立。
    return coverage.a>0.5 && normal.y>0.65 && coverage.z>0.65
        && abs(coverage.y-position.y)<0.35;
}
#endif
#endif
#endif
