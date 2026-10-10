#define EFS_UNDERWATER_PASS
#include "/lib/underwater_view.glsl"
in vec2 texcoord;
/* DRAWBUFFERS:1 */
layout(location=0) out vec4 waterLight;
void main() {
    // 云已合成且透明几何已完成，复用半分辨率附件存储水中散射及积分长度。
    waterLight=vec4(0);
    if (isEyeInWater!=1) return;
    float distance=underwaterDistance(texcoord);
    if (distance>=1e9) return;
    waterLight=vec4(underwaterSunbeams(texcoord,distance),min(distance,40.0));
}
