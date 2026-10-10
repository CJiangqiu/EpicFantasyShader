#ifndef EFS_CLOUDS
#define EFS_CLOUDS

#ifndef EFS_WORLD_MOTION
#define EFS_WORLD_MOTION
uniform vec3 cameraPosition;
uniform float frameTimeCounter;
#endif
uniform float cloudHumidity;
uniform float cloudHighland;
uniform float thunderStrength;
uniform sampler2D noisetex;

float cloudThickness() {
    return CLOUD_THICKNESS * mix(1.0, 1.5, rainStrength) * mix(1.0, 1.25, thunderStrength);
}

// 四通道打包横向与高度方向的角点，两次读取取得三维单元的八个角。
// 显式插值保留浮点权重，避免硬件双线性权重量化引起缓慢移动时的台阶。
float cloudNoise(vec3 p) {
    ivec3 cell = ivec3(mod(floor(p) + 32.0, 72.0));
    vec3 f = fract(p);
    f = f * f * f * (f * (f * 6.0 - 15.0) + 10.0);
    ivec2 tile = ivec2(cell.z % 9, cell.z / 9);
    ivec2 pixel = tile * 73 + cell.xy;
    vec4 lower = texelFetch(noisetex, pixel, 0);
    vec4 upper = texelFetch(noisetex, pixel + ivec2(0,1), 0);
    vec4 corners = mix(lower, upper, f.y);
    vec2 slices = mix(corners.xz, corners.yw, f.x);
    return mix(slices.x, slices.y, f.z);
}

float cloudDensity(vec3 world) {
    float h = (world.y - CLOUD_ALTITUDE) / cloudThickness();
    if (h <= 0.0 || h >= 1.0) return 0.0;
    // 环形风场在加载器计时器回绕时保持连续。
    float phase = mod(frameTimeCounter, 3600.0) * (6.28318530718 / 3600.0);
    vec2 wind = vec2(sin(phase), cos(phase)) * (1200.0 * CLOUD_SPEED);
    vec2 horizontal = world.xz + wind;
    vec2 regionPosition = mat2(0.8, 0.6, -0.6, 0.8) * horizontal / (600.0 * CLOUD_SCALE);
    float broadRegion = cloudNoise(vec3(regionPosition.x, 0.0, regionPosition.y));
    vec2 brokenRegion = mat2(0.6, -0.8, 0.8, 0.6) * regionPosition * 2.7;
    float region = 0.72 * broadRegion + 0.28 * cloudNoise(vec3(brokenRegion, 9.3));
    float climate = mix(0.49, mix(0.43, 0.55, clamp(cloudHumidity, 0.0, 1.0)), CLOUD_BIOME_VARIATION);
    climate = mix(climate, 0.32, clamp(cloudHighland, 0.0, 1.0) * CLOUD_BIOME_VARIATION);
    float coverage = mix(climate, 0.86, rainStrength);
    coverage = mix(coverage, 1.0, thunderStrength);
    coverage = clamp(coverage + CLOUD_COVERAGE - 1.0, 0.0, 1.0);
    // 区域场仅排除晴空，云体轮廓由连续的三维场决定。
    float bank = region - (1.0 - coverage);
    if (bank <= 0.0) return 0.0;
    vec3 p = vec3(horizontal.x, world.y - CLOUD_ALTITUDE, horizontal.y) / (160.0 * CLOUD_SCALE);
    p.xz = mat2(0.8, 0.6, -0.6, 0.8) * p.xz;
    float swell = cloudNoise(p * 0.57 + 17.3);
    // 非线性坐标扭曲与不同方向的频段共同打散网格轴向。
    p += (swell - 0.5) * vec3(1.7, 0.8, -1.3);
    float body = cloudNoise(p);
    vec3 q = vec3(p.y+p.z, p.z-p.y, p.x*1.41421356);
    // 云底较平缓，云顶随主体起伏；高度约束通过密度阈值形成隆起。
    float bottom = 0.035 + 0.045 * swell;
    float crown = 0.42 + 0.30 * swell + 0.24 * body;
    float profile = smoothstep(bottom, bottom + 0.12, h)
                  * (1.0 - smoothstep(crown * 0.48, crown, h));
    if (profile <= 0.0) return 0.0;
    float detail = cloudNoise(q * 1.53 + 41.0);
    float structure = 0.55 * body + 0.45 * detail;
    float mass = bank * 1.15 + (structure - 0.43) * 1.4 - (1.0 - profile) * 0.65;
    // 雷暴的连续云幕填合团块间隙，局部隆起仍决定厚薄与明暗层次。
    mass = mix(mass, max(mass, 0.26 * profile), thunderStrength);
    if (mass <= 0.0) return 0.0;
    // 薄处侵蚀形成缺口，厚云内部保留完整体积。
    float erosion = 0.0;
    if (mass < 0.40) {
        float fine = cloudNoise(vec3(q.z+q.y, q.x-q.z, q.y-q.x) * 1.71 + 83.0);
        erosion = (1.0 - fine) * 0.22 * (1.0 - smoothstep(0.16, 0.40, mass));
    }
    mass = max(mass - erosion, 0.0) * smoothstep(0.0, 0.08, bank);
    return mass * profile * CLOUD_DENSITY * mix(0.095, 0.24, rainStrength);
}

// 云体和地表投影沿同一世界空间密度场积分。
float cloudTransmission(vec3 origin, vec3 lightDirection, int samples, bool opaqueShadow) {
    if (lightDirection.y <= 0.02) return 1.0;
    float start = max(0.0, (CLOUD_ALTITUDE - origin.y) / lightDirection.y);
    float end = (CLOUD_ALTITUDE + cloudThickness() - origin.y) / lightDirection.y;
    if (end <= start) return 1.0;
    float stepLength = (end - start) / float(samples);
    float opticalDepth = 0.0;
    for (int i = 0; i < samples; ++i) {
        vec3 p = origin + lightDirection * (start + (float(i) + 0.5) * stepLength);
        opticalDepth += cloudDensity(p) * stepLength;
        // 地面仅使用一次透射率，深度超过九时余量低于万分之二。
        if (opaqueShadow && opticalDepth > 9.0) break;
    }
    return exp(-opticalDepth);
}

float cloudTransmission(vec3 origin, vec3 lightDirection, int samples) {
    return cloudTransmission(origin, lightDirection, samples, false);
}

// 云内光照使用有限邻域，掠射光的采样位置不会随云顶交点移到数千格外。
float cloudLightTransmission(vec3 origin, vec3 lightDirection) {
    float reach = max(cloudThickness(), 384.0 * CLOUD_SCALE);
    if (lightDirection.y > 0.00001) {
        float exitDistance = max(0.0, (CLOUD_ALTITUDE + cloudThickness() - origin.y) / lightDirection.y);
        reach = min(reach, exitDistance);
    }
    float stepLength = reach / 5.0;
    float opticalDepth = 0.0;
    for (int i = 0; i < 5; ++i) {
        opticalDepth += cloudDensity(origin + lightDirection * ((float(i) + 0.5) * stepLength)) * stepLength;
    }
    return exp(-opticalDepth);
}

// 云底投影平面随相机按纹素对齐，移动相机时保留相同世界坐标的采样格点。
float cloudShadowSpan() { return 2048.0 * CLOUD_SCALE; }
vec2 cloudShadowCenter(vec3 lightDirection) {
    vec2 center = cameraPosition.xz + lightDirection.xz
        * max(CLOUD_ALTITUDE - cameraPosition.y, 0.0) / max(lightDirection.y, 0.02);
    float cell = cloudShadowSpan() / 256.0;
    return floor(center / cell) * cell;
}

#ifndef EFS_CLOUD_SHADOW_MAP_WRITE
uniform sampler2D colortex7;
vec4 cloudCubicWeights(float t) {
    float square=t*t, cube=square*t;
    return vec4(-0.5*t+square-0.5*cube, 1.0-2.5*square+1.5*cube,
                0.5*t+2.0*square-1.5*cube, -0.5*square+0.5*cube);
}
float cloudCachedTransmission(vec2 uv, out float variation) {
    // 三次插值保留云影边缘的曲率，避免对每个地表片元重新积分云密度。
    vec2 pixel=uv*256.0-0.5;
    ivec2 base=ivec2(floor(pixel));
    vec4 center=vec4(texelFetch(colortex7,clamp(base,ivec2(0),ivec2(255)),0).r,
        texelFetch(colortex7,clamp(base+ivec2(1,0),ivec2(0),ivec2(255)),0).r,
        texelFetch(colortex7,clamp(base+ivec2(0,1),ivec2(0),ivec2(255)),0).r,
        texelFetch(colortex7,clamp(base+ivec2(1,1),ivec2(0),ivec2(255)),0).r);
    float low=min(min(center.x,center.y),min(center.z,center.w));
    float high=max(max(center.x,center.y),max(center.z,center.w));
    // 全亮或全暗的格点只需双线性读取，不执行边缘重建。
    if (low>0.9995 || high<0.0005) {
        variation=0.0;
        vec2 f=fract(pixel);
        return mix(mix(center.x,center.y,f.x),mix(center.z,center.w,f.x),f.y);
    }
    vec4 wx=cloudCubicWeights(fract(pixel.x)), wy=cloudCubicWeights(fract(pixel.y));
    float sum=0.0;
    float darkest=1.0, brightest=0.0;
    for (int y=0;y<4;++y) for (int x=0;x<4;++x) {
        ivec2 cell=clamp(base+ivec2(x-1,y-1),ivec2(0),ivec2(255));
        float value=texelFetch(colortex7,cell,0).r;
        darkest=min(darkest,value);
        brightest=max(brightest,value);
        sum+=value*wx[x]*wy[y];
    }
    variation=brightest-darkest;
    return clamp(sum,0.0,1.0);
}
#endif

float cloudSurfaceShadow(vec3 world, vec3 lightDirection) {
#if VOLUMETRIC_CLOUDS == 1 && CLOUD_SHADOWS == 1
    if (lightDirection.y <= 0.02 || world.y >= CLOUD_ALTITUDE + cloudThickness()) return 1.0;
#ifndef EFS_CLOUD_SHADOW_MAP_WRITE
    if (world.y < CLOUD_ALTITUDE) {
        vec2 plane = world.xz + lightDirection.xz * ((CLOUD_ALTITUDE - world.y) / lightDirection.y);
        vec2 uv = (plane - cloudShadowCenter(lightDirection)) / cloudShadowSpan() + 0.5;
        float edge = max(abs(uv.x - 0.5), abs(uv.y - 0.5)) * 2.0;
        if (edge < 0.99) {
            float variation;
            float transmission = cloudCachedTransmission(uv,variation);
            // 强变化区域和缓存边缘平滑补充直接积分，云内及缓存外不读取平面投影。
            float directWeight = max(smoothstep(0.55,0.90,variation),smoothstep(0.875,0.99,edge));
            if (directWeight > 0.0) transmission = mix(transmission,
                cloudTransmission(world,lightDirection,16,rainStrength > 0.0),directWeight);
            return mix(1.0,transmission,CLOUD_SHADOW_STRENGTH);
        }
    }
#endif
    return mix(1.0,cloudTransmission(world,lightDirection,16,rainStrength > 0.0),CLOUD_SHADOW_STRENGTH);
#else
    return 1.0;
#endif
}

#endif

