#ifndef EFS_UNDERWATER_VIEW
#define EFS_UNDERWATER_VIEW
#include "/lib/water_color.glsl"
uniform int isEyeInWater;
uniform sampler2D depthtex0;
uniform mat4 gbufferProjectionInverse;
#ifdef DISTANT_HORIZONS
uniform sampler2D dhDepthTex0;
uniform mat4 dhProjectionInverse;
#endif

#include "/lib/underwater_light.glsl"

float underwaterViewDistance(sampler2D bufferDepth, mat4 inverseProjection, vec2 uv) {
    float depth=texture(bufferDepth,uv).r;
    if (depth>=1.0) return 1e10;
    vec4 view=inverseProjection*vec4(uv*2.0-1.0,depth*2.0-1.0,1);
    return length(view.xyz/view.w);
}

float underwaterDistance(vec2 uv) {
    float distance=underwaterViewDistance(depthtex0,gbufferProjectionInverse,uv);
#ifdef DISTANT_HORIZONS
    distance=min(distance,underwaterViewDistance(dhDepthTex0,dhProjectionInverse,uv));
#endif
    return distance;
}

#if defined(WORLD_OVERWORLD) && defined(SHADOWS) && WATER_LIGHT_SHAFTS == 1 && !defined(EFS_UNDERWATER_PASS)
uniform sampler2D colortex1;
vec3 underwaterLightReconstruct(vec2 uv, float distance) {
    ivec2 size=textureSize(colortex1,0);
    vec2 pixel=uv*vec2(size)-0.5;
    ivec2 base=ivec2(floor(pixel));
    vec2 fraction=fract(pixel);
    vec3 sum=vec3(0);
    float weights=0.0;
    float limit=min(distance,40.0);
    float tolerance=max(0.15,limit*0.04);
    // 完整深度约束双线性重建，避免跨水面和前景混合。
    for (int y=0;y<2;++y) for (int x=0;x<2;++x) {
        vec4 sampleLight=texelFetch(colortex1,clamp(base+ivec2(x,y),ivec2(0),size-1),0);
        vec2 spatial=mix(vec2(1.0)-fraction,fraction,vec2(x,y));
        float weight=spatial.x*spatial.y*(1.0-smoothstep(tolerance*0.5,tolerance,abs(sampleLight.a-limit)));
        sum+=sampleLight.rgb*weight;
        weights+=weight;
    }
    // 水面边缘及细小前景没有匹配深度时，在原始像素处积分。
    if (weights<0.05) return underwaterSunbeams(uv,distance);
    return sum/weights;
}
#else
vec3 underwaterLightReconstruct(vec2 uv, float distance) { return vec3(0); }
#endif

vec3 underwaterView(vec3 color, vec2 uv) {
    if (isEyeInWater!=1) return color;
    // 透明几何绘制完成后，最近深度包含出水界面，空气中的距离不计入水雾。
    float distance=underwaterDistance(uv);
    if (distance>=1e9) return color;
    return underwaterFog(color,distance)+underwaterLightReconstruct(uv,distance);
}
#endif
