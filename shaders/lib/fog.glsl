#ifndef EFS_FOG
#define EFS_FOG
#include "/lib/water_color.glsl"

uniform vec3 fogColor;
uniform float far;
#ifndef EFS_EYE_MEDIUM
#define EFS_EYE_MEDIUM
uniform int isEyeInWater;
#endif
#ifdef DISTANT_HORIZONS
uniform int dhRenderDistance;
#endif

vec3 applyFog(vec3 color, float distanceToCamera) {
    float range = far;
#ifdef DISTANT_HORIZONS
    range = max(range, float(dhRenderDistance));
#endif
    float fog = 1.0 - exp(-pow(distanceToCamera / max(range, 1.0), 4.0) * FOG_DENSITY);
    // 水雾在透明水面深度完成后统一计算，避免将水上山体的空气段计入吸收。
    if (isEyeInWater == 1) return color;
    return mix(color, toLinear(fogColor), fog);
}

#endif
