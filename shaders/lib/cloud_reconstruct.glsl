#ifndef EFS_CLOUD_RECONSTRUCT
#define EFS_CLOUD_RECONSTRUCT
#include "/lib/cloud_render.glsl"
#if defined(WORLD_OVERWORLD) && VOLUMETRIC_CLOUDS == 1
uniform sampler2D colortex1;
uniform sampler2D colortex2;
vec4 cloudReconstruct(vec2 uv) {
    float limit = cloudLimit(uv);
    vec3 ray;
    float start, end;
    // 原始分辨率深度先排除云前地形，细树枝与山体轮廓不依赖缩小后的深度。
    if (!cloudInterval(uv,limit,ray,start,end)) return vec4(0.0,0.0,0.0,1.0);
    ivec2 size = textureSize(colortex1,0);
    vec2 pixel = uv * vec2(size) - 0.5;
    ivec2 base = ivec2(floor(pixel));
    vec2 fraction = fract(pixel);
    vec4 sum = vec4(0.0);
    float weights = 0.0;
    float minTransmission = 1.0, maxTransmission = 0.0;
    float tolerance = max(1.0,limit * 0.002);
    for (int y=0;y<2;++y) {
        for (int x=0;x<2;++x) {
            ivec2 cell = clamp(base + ivec2(x,y),ivec2(0),size-1);
            float sampleLimit = texelFetch(colortex2,cell,0).r;
            vec2 spatial = mix(vec2(1.0)-fraction,fraction,vec2(x,y));
            float weight = spatial.x * spatial.y
                * (1.0-smoothstep(tolerance*0.5,tolerance,abs(sampleLimit-limit)));
            vec4 sampleLayer = texelFetch(colortex1,cell,0);
            sum += sampleLayer * weight;
            if (weight > 0.0001) {
                minTransmission = min(minTransmission,sampleLayer.a);
                maxTransmission = max(maxTransmission,sampleLayer.a);
            }
            weights += weight;
        }
    }
    // 遮挡轮廓附近缺少同深度邻居时直接积分，避免漏云及沿山体的无云细边。
    if (weights < 0.05) return cloudFullResolution(uv);
    vec4 layer = sum / weights;
    layer.rgb += skyBackground(ray) * (1.0-layer.a);
    // 薄云与晴空交界变化过快时补充原分辨率积分，保留细云轮廓。
    float detail = max(smoothstep(0.15,0.35,maxTransmission-minTransmission),
                       1.0-smoothstep(0.05,0.25,weights));
    if (detail > 0.0) layer = mix(layer,cloudFullResolution(uv),detail);
    return layer;
}
#endif
#endif
