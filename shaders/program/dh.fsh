#include "/lib/settings.glsl"
#include "/lib/color.glsl"
#include "/lib/lighting.glsl"
#include "/lib/fog.glsl"

#ifdef DH_WATER
#include "/lib/water_surface.glsl"
flat in int waterMaterial;
#endif
in vec4 vertexColor;
in vec2 lightcoord;
in vec3 playerPosition;
in vec3 worldNormal;
in float viewDepth;
#ifdef DH_WATER
/* DRAWBUFFERS:06 */
layout(location = 1) out vec4 waterCoverage;
#else
/* DRAWBUFFERS:0 */
#endif
layout(location = 0) out vec4 scene;

void main() {
#ifdef DH_WATER
    waterCoverage=vec4(0.0);
    // 透明阶段的普通不透明深度已经完成，用于遮挡前景后方的远景水面。
    vec2 screen = gl_FragCoord.xy / vec2(viewWidth, viewHeight);
    float nearDepth = texture(depthtex1, screen).r;
    vec4 nearView = gbufferProjectionInverse * vec4(screen * 2.0 - 1.0, nearDepth * 2.0 - 1.0, 1.0);
    if (nearDepth < 1.0 && viewDepth > -nearView.z / nearView.w + 0.05) discard;
#endif
    vec3 normal = normalize(worldNormal + vec3(0.0, 1e-8, 0.0));
    if (!gl_FrontFacing) normal = -normal;
#ifdef DH_WATER
    if (waterMaterial == 1) {
        // 无普通水底时保留远景水作为补位，不按固定距离挖空未加载区域。
        if (nearDepth<1.0 && length(playerPosition.xz)<waterHandoffDistance()) discard;
        vec4 water = shadeWater(playerPosition,normal,surfaceLighting(playerPosition,normal,lightcoord,1.0),lightcoord.y);
        scene = vec4(applyFog(water.rgb,length(playerPosition)),water.a);
        waterCoverage=vec4(viewDepth,playerPosition.y,normal.y,1.0);
        return;
    }
#endif
    vec3 color = toLinear(vertexColor.rgb) * surfaceLighting(playerPosition, normal, lightcoord, 1.0);
    scene = vec4(applyFog(color, length(playerPosition)), vertexColor.a);
}
