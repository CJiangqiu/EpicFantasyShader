#ifndef EFS_UNDERWATER_LIGHT
#define EFS_UNDERWATER_LIGHT
#if defined(WORLD_OVERWORLD) && defined(SHADOWS) && WATER_LIGHT_SHAFTS == 1
#include "/lib/shadow_projection.glsl"
uniform sampler2DShadow shadowtex1;
uniform mat4 shadowModelView;
uniform mat4 shadowProjection;
uniform mat4 gbufferModelViewInverse;
uniform vec3 sunPosition;
uniform float rainStrength;

vec3 underwaterSunbeams(vec2 uv, float waterDistance) {
    vec3 sun=normalize(mat3(gbufferModelViewInverse)*sunPosition);
    float daylight=smoothstep(0.04,0.22,sun.y)*(1.0-clamp(rainStrength,0.0,1.0));
    if (daylight*WATER_SHAFT_STRENGTH<=0.0001) return vec3(0);
    vec4 view=gbufferProjectionInverse*vec4(uv*2.0-1.0,1,1);
    vec3 direction=normalize(mat3(gbufferModelViewInverse)*(view.xyz/view.w));
    // 散射方向与阴影图使用同一太阳方向；遮挡路径不包含水面折射。
    float alignment=clamp(dot(direction,sun),-1.0,1.0);
    // 归一化前向散射相函数：背向太阳的视线只接收很弱的直接散射。
    const float asymmetry=0.72;
    float phase=(1.0-asymmetry*asymmetry)
        /(12.5663706144*pow(1.0+asymmetry*asymmetry-2.0*asymmetry*alignment,1.5));
    float reach=min(waterDistance,40.0);
    // 世界距离固定的积分段不随前景深度重新分布，短路径仅截断最后一段。
    float stepLength=4.0/float(WATER_SHAFT_SAMPLES);
    vec3 sum=vec3(0);
    vec3 extinction=vec3(0.065,0.035,0.022)*max(WATER_FOG_DENSITY/0.35,0.1);
    vec3 attenuation=exp(-extinction*stepLength);
    vec3 segmentIntegral=(vec3(1.0)-attenuation)/extinction;
    int sampleCount=min(int(ceil(reach/stepLength)),WATER_SHAFT_SAMPLES*10);
    float tailLength=reach-float(max(sampleCount-1,0))*stepLength;
    vec3 tailIntegral=(vec3(1.0)-exp(-extinction*tailLength))/extinction;
    vec3 transmission=vec3(1.0);
    // 逆视图矩阵的平移包含镜头偏移，射线起点与几何重建采用同一坐标系。
    vec3 origin=gbufferModelViewInverse[3].xyz;
    vec4 shadowOrigin=shadowProjection*shadowModelView*vec4(origin,1);
    vec4 shadowRay=shadowProjection*shadowModelView*vec4(direction,0);
    for (int i=0;i<sampleCount;++i) {
        float start=float(i)*stepLength;
        float lengthInWater=i==sampleCount-1 ? tailLength : stepLength;
        float travel=start+0.5*lengthInWater;
        vec3 p=origin+direction*travel;
        vec4 projected=shadowOrigin+shadowRay*travel;
        vec3 coordinate=distortShadow(projected.xyz/projected.w)*0.5+0.5;
        // 阴影覆盖之外不推断阳光，避免洞穴及视距边缘漏光。
        float edge=max(abs(coordinate.x*2.0-1.0),abs(coordinate.y*2.0-1.0));
        float coverage=(1.0-smoothstep(0.88,0.98,edge))
            *(1.0-smoothstep(shadowDistance*0.75,shadowDistance,length(p.xz)));
        if (coverage>0.0 && coordinate.z>0.001 && coordinate.z<0.999) {
            float visibility=texture(shadowtex1,vec3(coordinate.xy,coordinate.z-0.00002));
            vec3 integral=i==sampleCount-1 ? tailIntegral : segmentIntegral;
            sum+=transmission*visibility*coverage*integral;
        }
        transmission*=attenuation;
    }
    vec3 tint=mix(vec3(1.0,0.62,0.32),vec3(0.55,0.85,1.0),smoothstep(0.08,0.5,sun.y));
    return sum*tint*(0.014*daylight*phase*WATER_SHAFT_STRENGTH);
}
#else
vec3 underwaterSunbeams(vec2 uv, float waterDistance) { return vec3(0); }
#endif
#endif
