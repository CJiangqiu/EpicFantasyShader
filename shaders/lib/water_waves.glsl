#ifndef EFS_WATER_WAVES
#define EFS_WATER_WAVES
#ifndef EFS_WORLD_MOTION
#define EFS_WORLD_MOTION
uniform vec3 cameraPosition;
uniform float frameTimeCounter;
#endif

float waterClock() {
    return mod(frameTimeCounter,3600.0) * (6.28318530718/3600.0) * WATER_WAVE_SPEED;
}

float waterFoamHash(vec2 p) {
    vec3 q = fract(vec3(p.x,p.y,p.x) * 0.1031);
    q += dot(q,q.yzx+33.33);
    return fract((q.x+q.y)*q.z);
}

float waterFoamNoise(vec2 p) {
    vec2 cell = floor(p), f = fract(p);
    f = f*f*(3.0-2.0*f);
    return mix(mix(waterFoamHash(cell),waterFoamHash(cell+vec2(1,0)),f.x),
               mix(waterFoamHash(cell+vec2(0,1)),waterFoamHash(cell+vec2(1,1)),f.x),f.y);
}

// 五次插值的解析梯度在单元边界连续，避免差分采样与硬折线。
vec2 waterRippleGradient(vec2 p) {
    vec2 cell=floor(p), f=fract(p);
    vec2 u=f*f*f*(f*(f*6.0-15.0)+10.0);
    vec2 du=30.0*f*f*(f-1.0)*(f-1.0);
    float a=waterFoamHash(cell), b=waterFoamHash(cell+vec2(1,0));
    float c=waterFoamHash(cell+vec2(0,1)), d=waterFoamHash(cell+vec2(1,1));
    return du*vec2(mix(b-a,d-c,u.y),mix(c-a,d-b,u.x));
}

vec3 waterWaveNormal(vec3 world, vec3 normal, float distance) {
#if WATER_WAVES == 1
    float time = waterClock();
    // 不同方向与速度的连续随机波面叠加；细纹随距离优先衰减。
    mat2 rotation=mat2(0.8,0.6,-0.6,0.8);
    vec2 p=world.xz;
    // 整数角频率的闭合平移使时钟回绕前后保持连续。
    vec2 slope=waterRippleGradient(p*0.65+24.0*vec2(sin(time*4.0),cos(time*4.0)))*0.025;
    slope+=transpose(rotation)*waterRippleGradient(rotation*p*2.1+18.0*vec2(cos(time*8.0),sin(time*8.0)))
        *0.065*(1.0-smoothstep(40.0,140.0,distance));
    slope+=rotation*waterRippleGradient(transpose(rotation)*p*5.3+14.0*vec2(sin(time*12.0),-cos(time*12.0)))
        *0.035*(1.0-smoothstep(12.0,64.0,distance));
    float fade = 1.0-smoothstep(32.0,180.0,distance);
    vec3 gravity=vec3(0,-1,0);
    vec3 downhill=gravity-normal*dot(gravity,normal);
    float tilt=length(downhill);
    vec3 flow=downhill/max(tilt,0.0001);
    vec3 across=cross(normal,flow);
    float travel=dot(world,flow)-time*600.0;
    float lateral=dot(world,across);
    // 重力在水面切平面的分量决定下坡与落水方向。
    vec3 streaming=across*(0.09*sin(lateral*7.0+sin(travel*1.6)))
        +flow*(0.045*cos(travel*3.0+lateral*2.0));
    vec3 calm=vec3(-slope.x,0,-slope.y);
    calm-=normal*dot(calm,normal);
    vec3 disturbance=mix(calm,streaming,smoothstep(0.03,0.35,tilt));
    return normalize(normal+disturbance*WATER_WAVE_STRENGTH*fade);
#else
    return normal;
#endif
}

float waterFlowFoam(vec3 world, vec3 normal, float distance) {
#if WATER_FOAM == 1
    float falling=1.0-smoothstep(0.1,0.6,abs(normal.y));
    vec3 across=normalize(cross(normal,vec3(0,1,0))+vec3(0.00001,0,0));
    float stripe=dot(world,across)*10.0;
    float moving=world.y*3.0+waterClock()*600.0;
    float threads=smoothstep(0.90,1.0,0.5+0.5*sin(stripe+0.5*sin(moving)));
    float breaks=smoothstep(0.4,0.9,0.5+0.5*sin(moving+sin(stripe*0.3)));
    return falling*threads*breaks*0.16*WATER_FOAM_STRENGTH*(1.0-smoothstep(24.0,96.0,distance));
#else
    return 0.0;
#endif
}

float waterShoreFoam(vec3 world, float depth, float top, float distance) {
#if WATER_FOAM == 1
    float shallow = 1.0-smoothstep(0.15,WATER_FOAM_WIDTH,depth);
    float time = waterClock();
    float foamPatch = waterFoamNoise(world.xz*1.3);
    float broken = mix(foamPatch,waterFoamNoise(world.xz*5.2),0.35);
    // 波带按水深等值线流动，细碎覆盖避免形成连续的白色描边。
    float crest = 0.5+0.5*cos(depth*9.0-time*400.0+0.8*sin(world.x*0.9+world.z*1.1));
    float foam = shallow * smoothstep(0.35,0.8,crest) * smoothstep(0.22,0.75,broken);
    return foam * top * WATER_FOAM_STRENGTH * (1.0-smoothstep(80.0,320.0,distance));
#else
    return 0.0;
#endif
}
#endif

