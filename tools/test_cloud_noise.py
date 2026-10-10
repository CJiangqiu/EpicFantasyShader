"""验证云噪声图集、GPU 插值、负坐标和三轴周期接缝。"""

import ctypes as c

import numpy as np
from PIL import Image

from build_cloud_noise import PATH, SIZE, TILE, COLUMNS, generate
from gl_context import GLContext
from test_shadow_filter import FilterScene
from test_sky_background import VERTEX
from validate_shaders import SHADERS, expand


def main():
    atlas = np.asarray(Image.open(PATH).convert('RGBA'))
    assert np.array_equal(atlas, generate()), '发布纹理必须与确定性生成器一致'
    rng = np.random.default_rng(8271)
    points = rng.uniform(-300, 300, (64,64,4)).astype(np.float32)
    # 接缝两侧和整数格点同时进入实际 GPU 采样。
    for axis in range(3):
        points[axis*2,:,axis] = -32.0001
        points[axis*2+1,:,axis] = -31.9999
    points[6,...,:3] = np.floor(points[6,...,:3])
    position = points[...,:3]
    cell = ((np.floor(position).astype(int)+32) % SIZE)
    f = position-np.floor(position)
    f = f*f*f*(f*(f*6-15)+10)
    x = cell[...,0] + (cell[...,2] % COLUMNS)*TILE
    y = cell[...,1] + (cell[...,2] // COLUMNS)*TILE
    lower, upper = atlas[y,x]/255.0, atlas[y+1,x]/255.0
    corners = lower*(1-f[...,1,None])+upper*f[...,1,None]
    z0 = corners[...,0]*(1-f[...,0])+corners[...,1]*f[...,0]
    z1 = corners[...,2]*(1-f[...,0])+corners[...,3]*f[...,0]
    reference = z0*(1-f[...,2])+z1*f[...,2]
    with GLContext() as gl:
        scene = FilterScene(gl,size=64)
        texture = c.c_uint()
        program = 0
        try:
            source = '#version 330 compatibility\n' + expand(SHADERS/'lib/settings.glsl')
            source += '\nuniform float rainStrength;\n' + expand(SHADERS/'lib/clouds.glsl')
            source += '''
uniform sampler2D testPositions;
in vec2 texcoord;
layout(location=0) out vec4 scene;
void main() {
    vec3 p = texture(testPositions,texcoord).xyz;
    float value = cloudNoise(p);
    float period = cloudNoise(p+vec3(TEST_PERIOD));
    scene = vec4(value,period,cloudNoise(p+vec3(0.0001)),1.0);
}
'''
            source = source.replace('TEST_PERIOD',str(float(SIZE)))
            program = gl.program(VERTEX,source)
            gl.function('glUseProgram',None,c.c_uint)(program)
            gl.function('glActiveTexture',None,c.c_uint)(0x84C0)
            gl.function('glGenTextures',None,c.c_int,c.POINTER(c.c_uint))(1,c.byref(texture))
            scene.bind_texture(texture.value)
            scene.upload(points,0x8814,64,0x1908)
            scene.parameter(0x2801,0x2600)
            scene.parameter(0x2800,0x2600)
            gl.function('glDrawArrays',None,c.c_uint,c.c_int,c.c_int)(0x0004,0,3)
            pixels = np.empty((64,64,4),np.float32)
            gl.function('glReadPixels',None,c.c_int,c.c_int,c.c_int,c.c_int,c.c_uint,c.c_uint,c.c_void_p)(
                0,0,64,64,0x1908,0x1406,pixels.ctypes.data_as(c.c_void_p))
            assert np.isfinite(pixels).all()
            assert np.max(abs(pixels[...,0]-reference)) < 0.00005
            assert np.max(abs(pixels[...,0]-pixels[...,1])) < 0.0001
            assert np.max(abs(pixels[...,0]-pixels[...,2])) < 0.001
            assert gl.function('glGetError',c.c_uint)() == 0
            print('PASS: deterministic atlas, GPU interpolation, negative coordinates, periodic continuity')
        finally:
            if program:
                gl.delete_program(program)
            gl.function('glDeleteTextures',None,c.c_int,c.POINTER(c.c_uint))(1,c.byref(texture))
            scene.close()


if __name__ == '__main__':
    main()
