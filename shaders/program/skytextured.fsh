#include "/lib/settings.glsl"
#include "/lib/sky_background.glsl"
#include "/lib/moon.glsl"
#include "/lib/sun.glsl"
#ifdef WORLD_OVERWORLD
#include "/lib/stars.glsl"
#include "/lib/aurora.glsl"
#include "/lib/meteors.glsl"
#endif

uniform sampler2D gtexture;
uniform int moonPhase;
in vec2 texcoord;
in vec2 moonCoord;
in vec2 sunCoord;
in vec4 vertexColor;
flat in int isMoon;
/* DRAWBUFFERS:0 */
layout(location = 0) out vec4 scene;

void main() {
#if SUN_STYLE == 1 && defined(WORLD_OVERWORLD)
    if (isMoon == 0) {
        float sunHeight = normalize(mat3(gbufferModelViewInverse) * sunPosition).y;
        vec4 sun = renderSun(sunCoord, sunHeight);
        if (sun.a <= 0.00001) discard;
        vec3 nearSky = proceduralNearSky(skyDirection(gl_FragCoord.xy / vec2(viewWidth, viewHeight)));
        scene = vec4(sun.rgb + nearSky, sun.a * vertexColor.a);
        return;
    }
#endif
#if MOON_STYLE == 1
#ifdef WORLD_OVERWORLD
    if (isMoon == 1) {
        vec3 direction = skyDirection(gl_FragCoord.xy / vec2(viewWidth, viewHeight));
        vec4 moon = renderMoon(moonCoord, moonPhase, MOON_BRIGHTNESS, skyBackground(direction));
        if (moon.a <= 0.0) discard;
        // 背景已含近层发光；源颜色补入同一近层，使透明混合后近层只保留一份。
        vec3 nearSky = proceduralNearSky(skyDirection(gl_FragCoord.xy / vec2(viewWidth, viewHeight)));
        scene = vec4(moon.rgb + nearSky, moon.a * vertexColor.a);
        return;
    }
#endif
#endif
    vec4 color = texture(gtexture, texcoord) * vertexColor;
    if (color.a <= 0.001) discard;
    vec3 linearColor = toLinear(color.rgb);
#ifdef WORLD_OVERWORLD
    if (isMoon == 1) {
        linearColor += proceduralNearSky(skyDirection(gl_FragCoord.xy / vec2(viewWidth, viewHeight)));
    }
#endif
    scene = vec4(linearColor, color.a);
}
