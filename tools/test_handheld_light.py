"""用实际 GLSL 验证双手光源、距离衰减、朝向与开关。"""

import ctypes as c

from gl_context import GLContext
from test_shadow_filter import FilterScene, VERTEX
from validate_shaders import SHADERS, configure, expand


def main():
    with GLContext() as gl:
        print(gl.description())
        framebuffer = FilterScene(gl, size=16, resolution=16)
        try:
            for enabled in (True, False):
                options = {} if enabled else {"HANDHELD_LIGHT": None}
                source = "#version 330 compatibility\n" + configure(expand(SHADERS / "lib/settings.glsl"), options)
                source += expand(SHADERS / "lib/handheld_light.glsl") + """
uniform vec3 testPosition;
uniform vec3 testNormal;
uniform mat4 testViewInverse;
layout(location=0) out vec4 result;
void main() {
    result = vec4(handheldLighting(testPosition, testNormal, testViewInverse), 1.0);
}
"""
                program = gl.program(VERTEX, source)
                gl.function("glUseProgram", None, c.c_uint)(program)
                location = gl.function("glGetUniformLocation", c.c_int, c.c_uint, c.c_char_p)
                set_int = gl.function("glUniform1i", None, c.c_int, c.c_int)
                set_vec3 = gl.function("glUniform3f", None, c.c_int, c.c_float, c.c_float, c.c_float)
                set_matrix = gl.function("glUniformMatrix4fv", None, c.c_int, c.c_int, c.c_ubyte, c.POINTER(c.c_float))

                def evaluate(main_id=-1, off_id=-1, main_level=0, off_level=0,
                             distance=2.0, normal=(0.0, 0.0, 1.0), translation=(0.0, 0.0, 0.0)):
                    for name, value in (("heldItemId", main_id), ("heldItemId2", off_id),
                                        ("heldBlockLightValue", main_level), ("heldBlockLightValue2", off_level)):
                        set_int(location(program, name.encode()), value)
                    set_vec3(location(program, b"testPosition"), translation[0], translation[1] - 0.25,
                             translation[2] - 0.4 - distance)
                    set_vec3(location(program, b"testNormal"), *normal)
                    matrix = (c.c_float * 16)(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, *translation, 1)
                    set_matrix(location(program, b"testViewInverse"), 1, 0, matrix)
                    gl.function("glDrawArrays", None, c.c_uint, c.c_int, c.c_int)(0x0004, 0, 3)
                    pixel = (c.c_float * 4)()
                    gl.function("glReadPixels", None, c.c_int, c.c_int, c.c_int, c.c_int,
                                c.c_uint, c.c_uint, c.c_void_p)(0, 0, 1, 1, 0x1908, 0x1406, pixel)
                    return tuple(pixel[:3])

                def close(a, b):
                    return max(abs(x - y) for x, y in zip(a, b)) < 1e-5

                dark = (0.0, 0.0, 0.0)
                assert close(evaluate(), dark), "空手不得发光"
                if not enabled:
                    assert close(evaluate(11002, 11003, 15, 10), dark), "关闭时必须移除双手照明"
                else:
                    main_light = evaluate(main_id=11001)
                    off_light = evaluate(off_id=11003)
                    assert main_light[0] > main_light[1] > main_light[2] > 0, "火把光色"
                    assert off_light[2] > off_light[1] > off_light[0] > 0, "灵魂光色"
                    assert close(evaluate(11001, 11003), tuple(a+b for a, b in zip(main_light, off_light))), "双手叠加"
                    assert evaluate(main_id=11004)[0] > evaluate(main_id=11004)[2] * 10, "红石光色"
                    assert evaluate(main_level=12)[0] > 0, "未分类发光方块回退"
                    assert close(evaluate(main_id=11002, distance=12), dark), "范围外停止照明"
                    assert close(evaluate(main_id=11002, normal=(0, 0, -1)), dark), "背光面不应受直射光"
                    distances = [evaluate(main_id=11002, distance=i * 0.05)[0] for i in range(1, 261)]
                    assert all(a >= b - 1e-5 for a, b in zip(distances, distances[1:])), "距离衰减应单调"
                    assert max(abs(a-b) for a, b in zip(distances, distances[1:])) < 0.1, "范围边缘应连续"
                    assert close(evaluate(main_id=11001, translation=(12, 1.62, -8)), main_light), "相机位移后的坐标一致性"
                    assert close(evaluate(), dark), "移走光源后不得残留"
                error = gl.function("glGetError", c.c_uint)()
                assert error == 0, f"OpenGL 错误：{error:#x}"
                gl.delete_program(program)
                print(f"PASS: handheld enabled={enabled}")
        finally:
            framebuffer.close()
    print("PASS: 双手光色、叠加、空手、物品回退、范围、背光面、坐标一致性和开关")


if __name__ == "__main__":
    main()
