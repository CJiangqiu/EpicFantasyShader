#include "/lib/color.glsl"

uniform sampler2D gtexture;
uniform sampler2D lightmap;
uniform float alphaTestRef;
in vec2 texcoord;
in vec2 lightcoord;
in vec4 vertexColor;
/* DRAWBUFFERS:0 */
layout(location = 0) out vec4 scene;

void main() {
    vec4 color = vertexColor;
#ifndef UNTEXTURED
    color *= texture(gtexture, texcoord);
#endif
    if (color.a < max(alphaTestRef, 0.001)) discard;
#ifdef LIGHTMAP_ONLY
    color.rgb *= texture(lightmap, lightcoord).rgb;
#endif
    scene = vec4(toLinear(color.rgb), color.a);
}
