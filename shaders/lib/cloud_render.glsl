#ifndef EFS_CLOUD_RENDER
#define EFS_CLOUD_RENDER
#include "/lib/settings.glsl"
#include "/lib/color.glsl"
#if defined(WORLD_OVERWORLD) && VOLUMETRIC_CLOUDS == 1
uniform sampler2D depthtex0;
uniform mat4 gbufferProjectionInverse;
uniform mat4 gbufferModelViewInverse;
uniform vec3 sunPosition;
uniform float rainStrength;
#if CLOUD_LIGHTNING == 1
uniform vec4 lightningBoltPosition;
uniform float cloudLightningPulse;
#endif
#include "/lib/sky_background.glsl"
#ifdef DISTANT_HORIZONS
uniform sampler2D dhDepthTex0;
uniform mat4 dhProjectionInverse;
#endif
#include "/lib/clouds.glsl"

float cloudSampleJitter(ivec2 pixel, int index) {
    uint value = uint(pixel.x) * 1973u + uint(pixel.y) * 9277u + uint(index) * 26699u;
    value ^= value >> 16u;
    value *= 2246822519u;
    value ^= value >> 13u;
    value *= 3266489917u;
    value ^= value >> 16u;
    return float(value & 0x00ffffffu) / 16777216.0;
}

// 归一化方向散射保留向光亮边，并限制极窄角度的亮度峰值。
float cloudPhase(float cosine, float asymmetry) {
    float square = asymmetry * asymmetry;
    return (1.0 - square) / pow(max(1.0 + square - 2.0 * asymmetry * cosine, 0.05), 1.5);
}

vec3 cloudIllumination(vec3 position, vec3 lightDirection, vec3 ray, vec3 direct, vec3 ambient, float density) {
    // 地平线附近平滑减弱方向性遮蔽，日月方向交接时不产生明暗跳变。
    float grazing = smoothstep(0.0, 0.04, lightDirection.y);
    float sunlight = mix(1.0, cloudLightTransmission(position, lightDirection), grazing);
    float skyTransmission = cloudTransmission(position, vec3(0,1,0), 3);
    float cosine = dot(ray, lightDirection);
    float phase = min(2.8, 0.30 * cloudPhase(cosine, 0.58) + 0.70 * cloudPhase(cosine, -0.12));
    phase = mix(1.0, phase, grazing);
    float height = clamp((position.y - CLOUD_ALTITUDE) / cloudThickness(), 0.0, 1.0);
    float filling = 1.0 - exp(-density * 85.0);
    // 高阶散射用较缓的消光近似，厚云内部保留柔和光照而不形成整片灰色。
    float scattered = 0.46 * pow(sunlight, 0.22) * filling;
    vec3 sky = ambient * (0.65 + 0.60 * sqrt(skyTransmission) + 0.18 * height);
    return sky + direct * (sunlight * phase * 0.65 + scattered);
}

float cloudSceneDistance(sampler2D depth, mat4 inverseProjection, vec2 uv) {
    float z = texture(depth, uv).r;
    if (z >= 1.0) return CLOUD_DISTANCE;
    vec4 view = inverseProjection * vec4(uv * 2.0 - 1.0, z * 2.0 - 1.0, 1.0);
    return length(view.xyz / view.w);
}

float cloudLimit(vec2 uv) {
    float limit = min(CLOUD_DISTANCE, cloudSceneDistance(depthtex0, gbufferProjectionInverse, uv));
#ifdef DISTANT_HORIZONS
    // 此阶段读取实时不透明深度，透明阶段的深度副本尚未生成。
    limit = min(limit, cloudSceneDistance(dhDepthTex0, dhProjectionInverse, uv));
#endif
    return limit;
}

bool cloudInterval(vec2 uv, float limit, out vec3 ray, out float start, out float end) {
    if (isEyeInWater > 1) return false;
    vec4 view = gbufferProjectionInverse * vec4(uv * 2.0 - 1.0, 1.0, 1.0);
    ray = normalize(mat3(gbufferModelViewInverse) * (view.xyz / view.w));
    start = 0.0; end = limit;
    if (abs(ray.y) < 0.00001) {
        if (cameraPosition.y <= CLOUD_ALTITUDE || cameraPosition.y >= CLOUD_ALTITUDE + cloudThickness()) return false;
    } else {
        vec2 bounds = (vec2(CLOUD_ALTITUDE, CLOUD_ALTITUDE + cloudThickness()) - cameraPosition.y) / ray.y;
        start = max(0.0, min(bounds.x, bounds.y));
        end = min(limit, max(bounds.x, bounds.y));
    }
    if (end <= start) return false;
    return true;
}

vec4 renderCloudLayer(vec2 uv, float limit, ivec2 pixel) {
    vec3 ray;
    float start, end;
    if (!cloudInterval(uv,limit,ray,start,end)) return vec4(0.0,0.0,0.0,1.0);
    vec3 sun = normalize(mat3(gbufferModelViewInverse) * sunPosition);
    float day = smoothstep(-0.08, 0.12, sun.y);
    vec3 lightDirection = sun.y >= 0.0 ? sun : -sun;
    vec3 direct = mix(vec3(0.045,0.063,0.10),
        mix(vec3(1.3,0.52,0.22),vec3(1.15,1.08,0.94),smoothstep(0.05,0.45,sun.y)), day);
    vec3 ambient = mix(vec3(0.012,0.02,0.036),vec3(0.19,0.25,0.34),day);
    // 雨云受漫射光照明，雷暴进一步压低亮边和云底亮度。
    direct *= mix(1.0, 0.20, rainStrength) * mix(1.0, 0.25, thunderStrength);
    ambient *= mix(1.0, 0.50, rainStrength) * mix(1.0, 0.38, thunderStrength);
    vec3 cloudHaze = toLinear(isEyeInWater==1 ? skyColor : fogColor)
                   * mix(1.0, 0.50, rainStrength) * mix(1.0, 0.35, thunderStrength);
    vec3 atmosphere = skyBackground(ray);
#if CLOUD_LIGHTNING == 1
    // 位置为相机相对坐标；发光中心置于落雷柱上方的云体内。
    float flash = clamp(cloudLightningPulse * 1.6,0.0,1.0) * clamp(lightningBoltPosition.w,0.0,1.0)
                * rainStrength * smoothstep(0.25,0.75,thunderStrength);
    vec3 flashCenter = vec3(lightningBoltPosition.x,CLOUD_ALTITUDE + cloudThickness()*0.35-cameraPosition.y,lightningBoltPosition.z);
#endif
    // 长视线增加分段，步长同时受云体横向尺度与垂直厚度约束。
    float targetStep = max(4.0, min(16.0 * CLOUD_SCALE, cloudThickness() / 16.0));
    int sampleCount = clamp(int(ceil((end - start) / targetStep)), CLOUD_SAMPLES, CLOUD_SAMPLES * 6);
    float stepLength = (end - start) / float(sampleCount);
    float transmission = 1.0;
    vec3 scattering = vec3(0.0);
    for (int i = 0; i < sampleCount; ++i) {
        // 每个像素的每一段使用独立抖动，避免整条视线共享相位形成斜条纹。
        float jitter = 0.30 + 0.4 * cloudSampleJitter(pixel, i);
        float distance = start + (float(i) + jitter) * stepLength;
        vec3 p = cameraPosition + ray * distance;
        float density = cloudDensity(p);
        if (density > 0.00001) {
            float alpha = 1.0 - exp(-density * stepLength);
            vec3 lit = cloudIllumination(p, lightDirection, ray, direct, ambient, density);
#if CLOUD_LIGHTNING == 1
            if (flash > 0.0001) {
                vec3 separation = (p-cameraPosition-flashCenter) / (vec3(420.0,240.0,420.0)*CLOUD_SCALE);
                float glow = 1.0/(1.0+dot(separation,separation));
                // 体积积分决定云的遮挡和亮光覆盖，只增加局部散射，不改变云形。
                float filling = 1.0-exp(-density*85.0);
                lit += vec3(0.9,1.05,1.3) * (flash*glow*glow*(0.35+0.65*filling));
            }
#endif
            float haze = 1.0 - exp(-distance / 6500.0);
            lit = mix(lit, cloudHaze, haze);
            // 阴雨远云在距离裁剪前接回同一视线的天空底色，避免厚云边界形成色带。
            float atmosphereBlend = rainStrength * smoothstep(CLOUD_DISTANCE * 0.25, CLOUD_DISTANCE * 0.80, distance);
            lit = mix(lit, atmosphere, atmosphereBlend);
            float edge = 1.0 - smoothstep(CLOUD_DISTANCE * 0.65, CLOUD_DISTANCE, distance);
            alpha *= edge;
            scattering += transmission * alpha * lit;
            transmission *= 1.0 - alpha;
            if (transmission < 0.01) break;
        }
    }
    return vec4(scattering,transmission);
}
vec4 cloudFullResolution(vec2 uv) {
    return renderCloudLayer(uv,cloudLimit(uv),ivec2(uv * vec2(textureSize(depthtex0,0))));
}
#endif

#endif
