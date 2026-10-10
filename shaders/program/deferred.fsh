#include "/lib/cloud_reconstruct.glsl"
uniform sampler2D colortex0;
in vec2 texcoord;
/* DRAWBUFFERS:05 */
layout(location=0) out vec4 scene;
layout(location=1) out vec4 reflectionScene;
void main() {
    scene = texture(colortex0,texcoord);
#if defined(WORLD_OVERWORLD) && VOLUMETRIC_CLOUDS == 1
    vec4 cloud = cloudReconstruct(texcoord);
    scene.rgb = scene.rgb * cloud.a + cloud.rgb;
#endif
    reflectionScene = scene;
}
