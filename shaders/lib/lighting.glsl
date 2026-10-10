#ifndef EFS_LIGHTING
#define EFS_LIGHTING

uniform vec3 sunPosition;
uniform vec3 shadowLightPosition;
uniform mat4 gbufferModelViewInverse;
uniform mat4 shadowModelView;
uniform mat4 shadowProjection;
uniform float rainStrength;
uniform float nightVision;
#ifndef EFS_EYE_MEDIUM
#define EFS_EYE_MEDIUM
uniform int isEyeInWater;
#endif

#include "/lib/handheld_light.glsl"
#ifdef WORLD_OVERWORLD
#include "/lib/clouds.glsl"
#if defined(TERRAIN_AO) && WATER_CAUSTICS == 1
#include "/lib/water_caustics.glsl"
#endif
#endif

#ifdef SHADOWS
#if defined(WORLD_OVERWORLD) && !defined(NO_SHADOW_RECEIVE)
#include "/lib/shadow_projection.glsl"
#include "/lib/shadow_filter.glsl"
#endif
#endif

vec3 surfaceLighting(vec3 position, vec3 normal, vec2 light, float ao) {
    light = clamp((light * 16.0 - 0.5) / 15.0, 0.0, 1.0);
    vec3 blockLight = vec3(1.25, 0.75, 0.35) * pow(light.x, 3.0);
#ifdef WORLD_OVERWORLD
    vec3 sunDirection = normalize(mat3(gbufferModelViewInverse) * sunPosition);
    vec3 lightDirection = normalize(mat3(gbufferModelViewInverse) * shadowLightPosition);
    float day = smoothstep(-0.08, 0.12, sunDirection.y);
    float horizon = smoothstep(0.02, 0.14, abs(sunDirection.y));
    float incidence = max(dot(normal, lightDirection), 0.0);
    float skyAccess = smoothstep(0.25, 0.95, light.y);
    float visibility = 1.0;
#ifdef SHADOWS
#ifndef NO_SHADOW_RECEIVE
    float biasScale = shadowDistance / 96.0 * 2048.0 / float(shadowMapResolution);
    vec3 receiver = position + normal * SHADOW_NORMAL_BIAS * biasScale;
    vec4 clip = shadowProjection * shadowModelView * vec4(receiver, 1.0);
    vec3 coordinate = distortShadow(clip.xyz / clip.w) * 0.5 + 0.5;
    // 导数必须在不一致的采样分支和透明度丢弃之前求值。
    vec2 gradient = receiverGradient(coordinate);
    float edge = max(abs(coordinate.x * 2.0 - 1.0), abs(coordinate.y * 2.0 - 1.0));
    float coverage = (1.0 - smoothstep(0.90, 0.98, edge))
                   * (1.0 - smoothstep(shadowDistance * 0.80, shadowDistance, length(position.xz)));
    if (incidence > 0.0 && skyAccess > 0.0 && coverage > 0.0
        && coordinate.z > 0.01 && coordinate.z < 0.99) {
        visibility = mix(1.0, filteredShadow(coordinate, gradient), coverage);
    }
#endif
#endif
    vec3 daylight = mix(vec3(1.55, 0.68, 0.30), vec3(1.45, 1.32, 1.12),
                       smoothstep(0.05, 0.45, sunDirection.y));
    vec3 direct = mix(vec3(0.055, 0.075, 0.12), daylight, day);
    vec3 ambient = mix(vec3(0.022, 0.032, 0.055), vec3(0.20, 0.26, 0.34), day);
    ambient *= light.y * light.y * (0.65 + 0.35 * max(normal.y, 0.0));
    vec3 illumination = (ambient * AMBIENT_STRENGTH + vec3(0.008)) * ao + blockLight;
    float cloudShade = 1.0;
    if (incidence * visibility * skyAccess * horizon > 0.001) {
        cloudShade = cloudSurfaceShadow(cameraPosition + position, lightDirection);
    }
    float caustic=0.0;
#if defined(TERRAIN_AO) && WATER_CAUSTICS == 1
    if (isEyeInWater==1) {
        // 只增强水下近处向上的地形直射光，保留阴影、天气与天空暴露限制。
        float receiver=smoothstep(0.1,0.8,normal.y)*smoothstep(0.0,0.5,-position.y);
        receiver*=1.0-smoothstep(16.0,40.0,length(position));
        caustic=waterCausticPattern(cameraPosition+position,sunDirection)*receiver*day*WATER_CAUSTIC_STRENGTH;
    }
#endif
    illumination += direct * incidence * visibility * cloudShade * skyAccess * horizon * (1.0 - 0.8 * rainStrength)*(1.0+caustic);
#elif defined(WORLD_NETHER)
    vec3 illumination = vec3(0.22, 0.12, 0.09) * AMBIENT_STRENGTH * ao + blockLight;
#else
    vec3 illumination = vec3(0.19, 0.17, 0.28) * AMBIENT_STRENGTH * ao + blockLight;
#endif
    illumination += handheldLighting(position, normal, gbufferModelViewInverse);
    return mix(illumination, max(illumination, vec3(0.8)), clamp(nightVision, 0.0, 1.0));
}

#endif
