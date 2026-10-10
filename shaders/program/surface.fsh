#include "/lib/settings.glsl"
#include "/lib/color.glsl"
#include "/lib/lighting.glsl"
#include "/lib/fog.glsl"
#ifdef TRANSLUCENT_TERRAIN
#include "/lib/water_surface.glsl"
#endif

uniform sampler2D gtexture;
uniform vec4 entityColor;
uniform float alphaTestRef;
in vec2 texcoord;
in vec2 lightcoord;
in vec4 vertexColor;
in vec3 playerPosition;
in vec3 worldNormal;
flat in int material;
/* DRAWBUFFERS:0 */
layout(location = 0) out vec4 scene;

void main() {
    vec4 albedo = texture(gtexture, texcoord);
    albedo.rgb *= vertexColor.rgb;
    float ao = 1.0;
#ifdef TERRAIN_AO
    ao = clamp(vertexColor.a, 0.0, 1.0);
#else
    albedo.a *= vertexColor.a;
#endif
#ifdef ENTITY_COLOR
    albedo.rgb = mix(albedo.rgb, entityColor.rgb, entityColor.a);
#endif
    vec3 normal = normalize(worldNormal + vec3(0.0, 1e-8, 0.0));
    if (!gl_FrontFacing) normal = -normal;
    vec3 illumination = surfaceLighting(playerPosition, normal, lightcoord, ao);
#ifdef ENTITY_COLOR
    // 实体程序也承接船舱的只写深度遮罩；裁剪关闭时必须保留零透明度片元的深度。
    if (albedo.a < alphaTestRef) discard;
#else
    if (albedo.a < max(alphaTestRef, 0.001)) discard;
#endif
#ifdef TRANSLUCENT_TERRAIN
    if (material == 10001) {
#ifdef DISTANT_HORIZONS
        if (waterCoveredByDistant(gl_FragCoord.xy/vec2(viewWidth,viewHeight),playerPosition,normal)) discard;
#endif
        vec4 water = shadeWater(playerPosition,normal,illumination,lightcoord.y);
        scene = vec4(applyFog(water.rgb,length(playerPosition)),water.a);
        return;
    }
#endif
    vec3 color = toLinear(albedo.rgb) * illumination;
    scene = vec4(applyFog(color, length(playerPosition)), albedo.a);
}
