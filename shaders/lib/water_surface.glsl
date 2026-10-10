#ifndef EFS_WATER_SURFACE
#define EFS_WATER_SURFACE

#include "/lib/water_color.glsl"
#include "/lib/water_waves.glsl"
uniform sampler2D depthtex1;
uniform mat4 gbufferProjectionInverse;
uniform float viewWidth;
uniform float viewHeight;
#ifdef DISTANT_HORIZONS
uniform sampler2D dhDepthTex1;
uniform mat4 dhProjectionInverse;
#endif

#include "/lib/water_handoff.glsl"

bool waterFloor(sampler2D bufferDepth, mat4 inverseProjection, vec2 uv, vec3 surface, out vec3 floorPosition) {
    float depth = texture(bufferDepth,uv).r;
    if (depth >= 1.0) return false;
    vec4 view = inverseProjection * vec4(uv*2.0-1.0,depth*2.0-1.0,1.0);
    floorPosition = (gbufferModelViewInverse * vec4(view.xyz/view.w,1.0)).xyz;
    // 前景地形不作为水下地形，比较同一相机空间中的距离。
    return length(floorPosition) > length(surface)+0.001;
}

#include "/lib/water_reflections.glsl"

vec4 shadeWater(vec3 position, vec3 normal, vec3 illumination, float skyLight) {
    // 顶点法线可能仍朝上，几何导数提供实际流水坡面的倾斜方向。
    vec3 geometric=cross(dFdx(position),dFdy(position));
    if (dot(geometric,geometric)>0.000001 && abs(normal.y)>0.65) {
        geometric=normalize(geometric);
        if (dot(geometric,normal)<0.0) geometric=-geometric;
        normal=geometric;
    }
    vec2 uv = gl_FragCoord.xy / vec2(viewWidth,viewHeight);
    vec3 bottom;
    bool found = waterFloor(depthtex1,gbufferProjectionInverse,uv,position,bottom);
#ifdef DISTANT_HORIZONS
    vec3 distantBottom;
    bool distantFound = waterFloor(dhDepthTex1,dhProjectionInverse,uv,position,distantBottom);
    if (distantFound && waterUseDistantFloor(found,bottom,distantBottom)) {
        bottom = distantBottom;
        found = true;
    }
#endif
    // 顶面使用水面到可见水底的垂直高度；侧面使用穿水距离。
    float depth = found ? mix(length(bottom-position),max(position.y-bottom.y,0.0),smoothstep(0.5,0.85,abs(normal.y))) : 24.0;
    float alpha = 0.015 + 0.985 * waterAbsorption(depth);
    // 从水内看向水面时，视线路径的水雾由几何雾负责，表面只保留轻微覆盖。
    if (isEyeInWater == 1) alpha = 0.015;
    if (isEyeInWater==1 && position.y>0.0 && normal.y< -0.5) {
        // 水面上下使用同一波面，朝水内的法线由朝外法线翻转得到。
        vec3 wave=-waterWaveNormal(cameraPosition+position,-normal,length(position));
        vec3 incoming=normalize(position);
        float cosine=clamp(dot(-incoming,wave),0.0,1.0);
        // 屏幕空间透射无法重建折射视锥外的景物，保留透射以维持岸上轮廓。
        // 这是可读性优先的近似，不模拟临界角处的完全内反射。
        float fresnel=0.02+0.63*pow(1.0-cosine,3.0);
        vec2 bend=(transpose(mat3(gbufferModelViewInverse))*(wave-normal)).xy;
        vec2 through=uv;
#if WATER_REFRACTION == 1
        vec2 candidate=uv+bend*0.035/max(cosine,0.25);
        if (all(greaterThan(candidate,vec2(0))) && all(lessThan(candidate,vec2(1)))) {
            vec3 object;
            if (!waterScenePoint(candidate,object) || length(object)>length(position)+0.05) through=candidate;
        }
#endif
        vec3 transmitted=texture(colortex5,through).rgb;
#if WATER_REFLECTIONS == 1
        vec3 reflected=waterReflection(position,reflect(incoming,wave),smoothstep(0.2,0.95,skyLight));
        transmitted=mix(transmitted,reflected,clamp(fresnel,0.0,1.0));
#endif
        // 已合成透射与内反射，最终水雾仍只计算到水面。
        return vec4(transmitted,1.0);
    }
    vec3 color = waterTint(depth) * illumination;
#ifdef WORLD_OVERWORLD
    if (isEyeInWater == 0) {
        vec3 world = cameraPosition + position;
        float distance = length(position);
        vec3 waveNormal = waterWaveNormal(world,normal,distance);
        vec3 view = normalize(-position);
        vec3 light = normalize(mat3(gbufferModelViewInverse) * shadowLightPosition);
        vec3 halfVector = normalize(light+view+vec3(0,0.00001,0));
        float top = smoothstep(0.65,0.95,normal.y);
        float shore = waterShoreDistance(uv,position);
        float foam = found ? waterShoreFoam(world,depth,top,distance) * (1.0-smoothstep(0.12,0.8,shore)) : 0.0;
        foam=max(foam,waterFlowFoam(world,normal,distance));
        float fresnel = 0.0;
        vec3 reflected = vec3(0);
#if WATER_REFLECTIONS == 1
        fresnel = 0.02+0.98*pow(1.0-max(dot(waveNormal,view),0.0),5.0);
        reflected = waterReflection(position,reflect(-view,waveNormal),smoothstep(0.2,0.95,skyLight));
#endif
        float combinedAlpha = 1.0-(1.0-alpha)*(1.0-fresnel)*(1.0-foam);
        vec3 premultiplied = (color*alpha*(1.0-fresnel)+reflected*fresnel)*(1.0-foam)
            + vec3(0.86,0.89,0.88)*illumination*foam;
        // 有限宽度的镜面亮部表现日月在细小波面上的反光。
        float glint = pow(max(dot(waveNormal,halfVector),0.0),192.0);
        premultiplied += illumination*glint*0.32*(1.0-foam)*smoothstep(0.2,0.95,skyLight);
#if WATER_REFRACTION == 1
        // 只扰动已存在的水后实体，拒绝前景岸壁，避免把岸上颜色拉入水内。
        vec2 bend=(transpose(mat3(gbufferModelViewInverse))*(waveNormal-normal)).xy;
        vec2 shifted=uv+bend*0.012*min(depth,3.0);
        vec3 transmitted;
        if (found && all(greaterThan(shifted,vec2(0))) && all(lessThan(shifted,vec2(1)))
            && waterScenePoint(shifted,transmitted) && length(transmitted)>length(position)+0.05
            && (top<0.5 || transmitted.y<position.y-0.05)) {
            vec3 difference=texture(colortex5,shifted).rgb-texture(colortex5,uv).rgb;
            premultiplied+=difference*(1.0-combinedAlpha);
        }
#endif
        return vec4(premultiplied/max(combinedAlpha,0.001),combinedAlpha);
    }
#endif
    return vec4(color,alpha);
}

#endif
