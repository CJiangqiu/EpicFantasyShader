#ifndef EFS_WATER_CAUSTICS
#define EFS_WATER_CAUSTICS
#include "/lib/water_waves.glsl"

vec2 waterLightLanding(vec2 surface, float height, float depth, vec3 sunDirection) {
    vec3 normal=waterWaveNormal(vec3(surface.x,height,surface.y),vec3(0,1,0),0.0);
    vec3 ray=refract(-sunDirection,normal,1.0/1.333);
    return surface+ray.xz*(depth/max(-ray.y,0.15));
}

float waterCausticPattern(vec3 world, vec3 sunDirection) {
#if WATER_WAVES == 1
    // 局部平面近似：相机上方一格作为入射面，实际水位尚无逐像素体积数据。
    float height=cameraPosition.y+1.0;
    float depth=clamp(height-world.y,0.25,12.0);
    vec3 flatRay=refract(-sunDirection,vec3(0,1,0),1.0/1.333);
    vec2 surface=world.xz-flatRay.xz*depth/max(-flatRay.y,0.15);
    // 反求照到当前接收点的水面位置，聚光面积由相邻折射光线的落点差决定。
    for (int i=0;i<2;++i)
        surface+=clamp(world.xz-waterLightLanding(surface,height,depth,sunDirection),vec2(-0.5),vec2(0.5));
    float stepSize=0.10;
    vec2 dx=(waterLightLanding(surface+vec2(stepSize,0),height,depth,sunDirection)
        -waterLightLanding(surface-vec2(stepSize,0),height,depth,sunDirection))/(2.0*stepSize);
    vec2 dz=(waterLightLanding(surface+vec2(0,stepSize),height,depth,sunDirection)
        -waterLightLanding(surface-vec2(0,stepSize),height,depth,sunDirection))/(2.0*stepSize);
    float area=abs(dx.x*dz.y-dx.y*dz.x);
    float concentration=1.0/max(area,0.35)-1.0;
    return clamp(concentration,0.0,1.2)*0.45;
#else
    return 0.0;
#endif
}
#endif
