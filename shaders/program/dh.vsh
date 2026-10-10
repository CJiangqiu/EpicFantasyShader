uniform mat4 gbufferModelViewInverse;
out vec4 vertexColor;
out vec2 lightcoord;
out vec3 playerPosition;
out vec3 worldNormal;
out float viewDepth;
#ifdef DH_WATER
flat out int waterMaterial;
#endif

void main() {
    vec4 view = gl_ModelViewMatrix * gl_Vertex;
    gl_Position = gl_ProjectionMatrix * view;
    playerPosition = (gbufferModelViewInverse * view).xyz;
    worldNormal = mat3(gbufferModelViewInverse) * gl_NormalMatrix * gl_Normal;
    vertexColor = gl_Color;
    lightcoord = gl_MultiTexCoord2.xy;
    viewDepth = -view.z;
#ifdef DH_WATER
#ifdef DH_BLOCK_WATER
    waterMaterial = int(dhMaterialId == DH_BLOCK_WATER);
#else
    waterMaterial = 0;
#endif
#endif
}
