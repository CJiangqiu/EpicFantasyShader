#include "/lib/settings.glsl"
#include "/lib/shadow_projection.glsl"

attribute vec4 mc_Entity;
#if VEGETATION_WIND == 1 && defined WORLD_OVERWORLD
uniform mat4 shadowModelViewInverse;
uniform mat4 shadowModelView;
attribute vec3 at_midBlock;
#include "/lib/vegetation_wind.glsl"
#endif
out vec2 texcoord;
out float vertexAlpha;
flat out int material;

void main() {
    material = int(mc_Entity.x + 0.5);
    vec4 view = gl_ModelViewMatrix * gl_Vertex;
#if VEGETATION_WIND == 1 && defined WORLD_OVERWORLD
    vec3 relativePosition = (shadowModelViewInverse * view).xyz;
    view.xyz += mat3(shadowModelView) * vegetationWindOffset(relativePosition, at_midBlock, material);
#endif
    vec4 clip = gl_ProjectionMatrix * view;
    gl_Position = vec4(distortShadow(clip.xyz / clip.w) * clip.w, clip.w);
    texcoord = (gl_TextureMatrix[0] * gl_MultiTexCoord0).xy;
    vertexAlpha = gl_Color.a;
}
