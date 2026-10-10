#ifndef EFS_WATER_REFLECTIONS
#define EFS_WATER_REFLECTIONS
uniform sampler2D colortex5;
uniform mat4 gbufferProjection;
uniform vec3 skyColor;

bool waterScenePoint(vec2 uv, out vec3 point) {
    vec3 unused;
    bool found = waterFloor(depthtex1,gbufferProjectionInverse,uv,vec3(0),point);
#ifdef DISTANT_HORIZONS
    bool distant = waterFloor(dhDepthTex1,dhProjectionInverse,uv,vec3(0),unused);
    if (distant && waterUseDistantFloor(found,point,unused)) { point=unused; found=true; }
#endif
    return found;
}

float waterShoreDistance(vec2 uv, vec3 position) {
    float nearest = 2.0;
#if WATER_FOAM == 1
    // 邻域只接受水面以上的实体岸壁，平坦浅滩不会生成整片泡沫。
    vec2 pixelWorld = vec2(length(dFdx(position)),length(dFdy(position)));
    vec2 radius = clamp(vec2(0.65)/max(pixelWorld,vec2(0.001)),vec2(1),vec2(24))/vec2(viewWidth,viewHeight);
    for (int i=0;i<8;++i) {
        float angle=float(i)*0.7853981634;
        vec2 sampleUV=uv+vec2(cos(angle),sin(angle))*radius;
        vec3 bank;
        if (any(lessThan(sampleUV,vec2(0))) || any(greaterThan(sampleUV,vec2(1)))) continue;
        if (waterScenePoint(sampleUV,bank) && bank.y>=position.y-0.08 && bank.y<position.y+2.0)
            nearest=min(nearest,length(bank.xz-position.xz));
    }
#endif
    return nearest;
}

vec3 waterReflection(vec3 position, vec3 direction, float skyAccess) {
    vec3 fallback=mix(toLinear(fogColor),toLinear(skyColor),smoothstep(0.0,0.6,direction.y))*skyAccess;
    bool submerged=isEyeInWater==1;
    if (submerged) fallback=waterTint(8.0)*0.35+toLinear(skyColor)*0.08*skyAccess;
#if WATER_REFLECTIONS == 1
    // 不透明场景与云的快照独立保存，透明阶段不读取正在写入的颜色附件。
    mat3 worldToView=transpose(mat3(gbufferModelViewInverse));
    float previousGap=-1.0;
    float previousTravel=0.0;
    for (int i=0;i<16;++i) {
        float travel=0.35+float(i)*0.65+float(i*i)*0.22;
        vec3 rayPoint=position+direction*travel;
        vec4 clip=gbufferProjection*vec4(worldToView*rayPoint,1);
        if (clip.w<=0.0) break;
        vec2 uv=clip.xy/clip.w*0.5+0.5;
        if (any(lessThanEqual(uv,vec2(0))) || any(greaterThanEqual(uv,vec2(1)))) break;
        vec3 object;
        bool found=waterScenePoint(uv,object);
        float edge=smoothstep(0.0,0.08,min(min(uv.x,uv.y),min(1.0-uv.x,1.0-uv.y)));
        if (!found) {
            // 仅在无实体遮挡时使用屏幕内的天空和云。
            if (i==15 && !submerged) return mix(fallback,texture(colortex5,uv).rgb,edge*skyAccess);
            previousGap=-1.0;
            previousTravel=travel;
            continue;
        }
        float gap=length(rayPoint)-length(object);
        if (previousGap<0.0 && gap>=0.0) {
            // 深度交叉处细分，避免粗步进把连续倒影切成横条。
            float low=previousTravel, high=travel;
            for (int j=0;j<5;++j) {
                float middle=(low+high)*0.5;
                vec3 probe=position+direction*middle;
                vec4 projected=gbufferProjection*vec4(worldToView*probe,1);
                vec2 sampleUV=projected.xy/projected.w*0.5+0.5;
                vec3 hit;
                if (waterScenePoint(sampleUV,hit) && length(probe)>=length(hit)) high=middle;
                else low=middle;
            }
            rayPoint=position+direction*high;
            clip=gbufferProjection*vec4(worldToView*rayPoint,1);
            uv=clip.xy/clip.w*0.5+0.5;
            if (waterScenePoint(uv,object) && (submerged ? object.y<=position.y+0.08 : object.y>=position.y-0.08)
                && abs(length(rayPoint)-length(object))<0.3+high*0.01)
                return mix(fallback,texture(colortex5,uv).rgb,edge);
        }
        previousGap=gap;
        previousTravel=travel;
    }
#endif
    return fallback;
}
#endif
