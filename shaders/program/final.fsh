#include "/lib/settings.glsl"
#include "/lib/color.glsl"
#include "/lib/underwater_view.glsl"

uniform sampler2D colortex0;
in vec2 texcoord;
layout(location = 0) out vec4 outputColor;

void main() {
    vec3 color = max(underwaterView(texture(colortex0, texcoord).rgb,texcoord),vec3(0.0))*EXPOSURE;
    // 按最大颜色通道统一压缩，保留高亮材质的色相。
    float peak = max(color.r, max(color.g, color.b));
    color /= 1.0 + max(peak - 0.8, 0.0);
    outputColor = vec4(toDisplay(color), 1.0);
}
