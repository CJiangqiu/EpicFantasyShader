#include "/lib/settings.glsl"

uniform mat4 gbufferModelViewInverse;
#if VEGETATION_WIND == 1 && defined WORLD_OVERWORLD && defined TERRAIN_AO
uniform mat4 gbufferModelView;
attribute vec3 at_midBlock;
#include "/lib/vegetation_wind.glsl"
#endif
attribute vec4 mc_Entity;
out vec2 texcoord;
out vec2 lightcoord;
out vec4 vertexColor;
out vec3 playerPosition;
out vec3 worldNormal;
flat out int material;

void main() {
    vec4 view = gl_ModelViewMatrix * gl_Vertex;
    material = int(mc_Entity.x + 0.5);
#if VEGETATION_WIND == 1 && defined WORLD_OVERWORLD && defined TERRAIN_AO
    vec3 relativePosition = (gbufferModelViewInverse * view).xyz;
    vec3 windOffset = vegetationWindOffset(relativePosition, at_midBlock, material);
    view.xyz += mat3(gbufferModelView) * windOffset;
#endif
    gl_Position = gl_ProjectionMatrix * view;
    texcoord = (gl_TextureMatrix[0] * gl_MultiTexCoord0).xy;
    lightcoord = (gl_TextureMatrix[1] * gl_MultiTexCoord1).xy;
    vertexColor = gl_Color;
    playerPosition = (gbufferModelViewInverse * view).xyz;
    worldNormal = mat3(gbufferModelViewInverse) * gl_NormalMatrix * gl_Normal;
}
