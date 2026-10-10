#ifndef EFS_SKY_BACKGROUND
#define EFS_SKY_BACKGROUND
#include "/lib/color.glsl"
#include "/lib/water_color.glsl"

uniform vec3 fogColor;
uniform vec3 skyColor;
uniform int isEyeInWater;

vec3 skyBackground(vec3 direction) {
    // 颜色由视线高度决定，背景与天空几何共用同一渐变，不依赖几何边界。
    if (isEyeInWater == 1) {
        // 水面上方仍是天空；低处无几何背景才使用深水散射色。
        // 水中 fogColor 属于水雾颜色，不能作为空气天空的地平线颜色。
        vec3 sky=toLinear(skyColor)*mix(0.75,1.0,smoothstep(0.0,0.55,direction.y));
        return mix(waterTint(256.0)*0.35,sky,smoothstep(-0.12,0.12,direction.y));
    }
    float elevation = smoothstep(0.0, 0.55, direction.y);
    if (isEyeInWater != 0) elevation = 0.0;
    return mix(toLinear(fogColor), toLinear(skyColor), elevation);
}
#endif
