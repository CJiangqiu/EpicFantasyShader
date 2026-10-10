#include "/lib/settings.glsl"

uniform sampler2D gtexture;
in vec2 texcoord;
in float vertexAlpha;
flat in int material;
layout(location = 0) out vec4 shadowColor;

void main() {
    if (material == 10001 || material == 10002) discard;
    if (texture(gtexture, texcoord).a * vertexAlpha < 0.1) discard;
    shadowColor = vec4(1.0);
}
