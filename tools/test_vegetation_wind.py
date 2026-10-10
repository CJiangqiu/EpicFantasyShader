"""捕获实际顶点程序输出，验证植物根部、接缝、阴影同步与动画边界。"""
import argparse
import ctypes as c
import json
import numpy as np
from artifact_paths import artifact_path
from gl_context import GLContext
from validate_shaders import SHADERS, configure, expand


class WindScene:
    def __init__(self, gl):
        self.gl = gl
        self.programs = {}
        self.buffers = (c.c_uint * 2)()
        gl.function('glGenBuffers', None, c.c_int, c.POINTER(c.c_uint))(2, self.buffers)
        gl.function('glEnable', None, c.c_uint)(0x8C89)
        gl.function('glEnableClientState', None, c.c_uint)(0x8074)

    def render(self, positions, midpoints, plant=10101, seconds=15.0, camera=(0, 64, 0),
               rain=0, thunder=0, options=None, entry='world0/gbuffers_terrain.vsh', repeats=0):
        gl = self.gl
        options = options or {}
        key = (entry, tuple(sorted(options.items())))
        if key not in self.programs:
            self.programs[key] = gl.program(configure(expand(SHADERS / entry), options),
                '#version 330 compatibility\nvoid main() {}', feedback=('gl_Position',))
        program = self.programs[key]
        gl.function('glUseProgram', None, c.c_uint)(program)
        loc = gl.function('glGetUniformLocation', c.c_int, c.c_uint, c.c_char_p)
        # 阴影与相机使用不同的视图矩阵及非零平移，验证空间转换而不只验证函数值。
        shadow = entry.endswith('/shadow.vsh')
        view = np.eye(4, dtype=np.float32)
        if shadow:
            view[:3, :3] = [[0.8, 0, 0.6], [0, 1, 0], [-0.6, 0, 0.8]]
        view[:3, 3] = [0.25, -0.75, 0.5]
        inverse = np.linalg.inv(view).astype(np.float32)
        projection = np.diag([.01, .01, .01, 1]).astype(np.float32)
        for name, matrix in [('gbufferModelView', view), ('gbufferModelViewInverse', inverse),
                             ('shadowModelView', view), ('shadowModelViewInverse', inverse)]:
            gl.function('glUniformMatrix4fv', None, c.c_int, c.c_int, c.c_ubyte, c.c_void_p)(
                loc(program, name.encode()), 1, 1, matrix.ctypes.data)
        for mode, matrix in [(0x1700, view), (0x1701, projection)]:
            gl.function('glMatrixMode', None, c.c_uint)(mode)
            column_major = np.ascontiguousarray(matrix.T)
            gl.function('glLoadMatrixf', None, c.c_void_p)(column_major.ctypes.data)
        for name, value in [('frameTimeCounter', seconds), ('rainStrength', rain), ('thunderStrength', thunder)]:
            gl.function('glUniform1f', None, c.c_int, c.c_float)(loc(program, name.encode()), value)
        gl.function('glUniform3f', None, c.c_int, c.c_float, c.c_float, c.c_float)(
            loc(program, b'cameraPosition'), *camera)
        attrib = gl.function('glGetAttribLocation', c.c_int, c.c_uint, c.c_char_p)
        material = attrib(program, b'mc_Entity')
        if material >= 0:
            gl.function('glVertexAttrib4f', None, c.c_uint, c.c_float, c.c_float, c.c_float, c.c_float)(material, plant, 0, 0, 0)
        data = np.ascontiguousarray(np.concatenate([positions, midpoints], axis=1), dtype=np.float32)
        bind = gl.function('glBindBuffer', None, c.c_uint, c.c_uint)
        upload = gl.function('glBufferData', None, c.c_uint, c.c_ssize_t, c.c_void_p, c.c_uint)
        bind(0x8892, self.buffers[0])
        upload(0x8892, data.nbytes, data.ctypes.data, 0x88E4)
        gl.function('glVertexPointer', None, c.c_int, c.c_uint, c.c_int, c.c_void_p)(3, 0x1406, 24, None)
        mid = attrib(program, b'at_midBlock')
        if mid >= 0:
            gl.function('glEnableVertexAttribArray', None, c.c_uint)(mid)
            gl.function('glVertexAttribPointer', None, c.c_uint, c.c_int, c.c_uint, c.c_ubyte, c.c_int, c.c_void_p)(mid, 3, 0x1406, 0, 24, 12)
        result = np.empty((len(data), 4), np.float32)
        bind(0x8C8E, self.buffers[1])
        upload(0x8C8E, result.nbytes, None, 0x88E9)
        gl.function('glBindBufferBase', None, c.c_uint, c.c_uint, c.c_uint)(0x8C8E, 0, self.buffers[1])

        def draw():
            gl.function('glBeginTransformFeedback', None, c.c_uint)(0x0000)
            gl.function('glDrawArrays', None, c.c_uint, c.c_int, c.c_int)(0x0000, 0, len(data))
            gl.function('glEndTransformFeedback', None)()

        draw()
        elapsed = None
        if repeats:
            query = c.c_uint()
            gl.function('glGenQueries', None, c.c_int, c.POINTER(c.c_uint))(1, c.byref(query))
            samples = []
            for _ in range(repeats):
                gl.function('glBeginQuery', None, c.c_uint, c.c_uint)(0x88BF, query.value)
                draw()
                gl.function('glEndQuery', None, c.c_uint)(0x88BF)
                ns = c.c_uint64()
                gl.function('glGetQueryObjectui64v', None, c.c_uint, c.c_uint, c.POINTER(c.c_uint64))(query.value, 0x8866, c.byref(ns))
                samples.append(ns.value / 1e6)
            elapsed = float(np.median(samples[3:]))
            gl.function('glDeleteQueries', None, c.c_int, c.POINTER(c.c_uint))(1, c.byref(query))
        gl.function('glGetBufferSubData', None, c.c_uint, c.c_ssize_t, c.c_ssize_t, c.c_void_p)(
            0x8C8E, 0, result.nbytes, result.ctypes.data)
        if mid >= 0:
            gl.function('glDisableVertexAttribArray', None, c.c_uint)(mid)
        error = gl.function('glGetError', c.c_uint)()
        assert error == 0, hex(error)
        assert np.isfinite(result).all()
        # 解开阴影畸变与投影，所有路径都返回相机相对世界坐标。
        if shadow:
            radius = np.linalg.norm(result[:, :2], axis=1)
            result[:, :2] *= (.2 / (1 - .8 * radius))[:, None]
            result[:, 2] *= 2
        world = (result @ np.linalg.inv(projection).T) @ inverse.T
        return (world[:, :3], elapsed) if repeats else world[:, :3]

    def close(self):
        for program in self.programs.values():
            self.gl.delete_program(program)
        self.gl.function('glDisable', None, c.c_uint)(0x8C89)
        self.gl.function('glDisableClientState', None, c.c_uint)(0x8074)
        self.gl.function('glDeleteBuffers', None, c.c_int, c.POINTER(c.c_uint))(2, self.buffers)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--benchmark', action='store_true')
    args = parser.parse_args()
    with GLContext(load_resources=False) as gl:
        scene = WindScene(gl)
        try:
            p = np.array([[x, y, 8.5] for x in (0.5, 3.5, 9.5) for y in (0, .5, 1)], np.float32)
            mid = np.zeros_like(p)
            mid[:, 1] = (.5 - p[:, 1]) * 64
            root = p[:, 1] == 0
            for plant in range(10101, 10111):
                wind = scene.render(p, mid, plant)
                assert np.max(abs(wind - scene.render(p, mid, plant, seconds=16))) > 1e-4
                if plant in (10101, 10102, 10103, 10106, 10107):
                    assert np.allclose(wind[root], p[root], atol=2e-5)
                assert np.allclose(wind[:, 1], p[:, 1], atol=2e-5)
                for seconds in (0, 15, 3579):
                    a = scene.render(p, mid, plant, seconds=seconds)
                    b = scene.render(p, mid, plant, seconds=seconds, entry='world0/shadow.vsh')
                    assert np.allclose(a, b, atol=2e-5), (plant, seconds, np.max(abs(a-b)))
                shifted = scene.render(p - [2, 0, 3], mid, plant, camera=(2, 64, 3)) + [2, 0, 3]
                assert np.allclose(wind, shifted, atol=2e-5)
                for speed in ('0.0', '0.5', '0.75', '1.0', '1.5', '2.0'):
                    options = {'VEGETATION_WIND_SPEED': speed}
                    start = scene.render(p, mid, plant, seconds=0, options=options)
                    assert np.allclose(start, scene.render(p, mid, plant, seconds=3600, options=options), atol=2e-5)
                    assert np.max(abs(start - scene.render(p, mid, plant, seconds=3599.99, options=options))) < .008
                dry = scene.render(p, mid, plant) - p
                wet = scene.render(p, mid, plant, rain=1, thunder=1) - p
                assert np.allclose(wet, dry * (1 if 10106 <= plant <= 10109 else 1.8), atol=2e-5)
            # 两格植物共享下段的根部与相位；叶块、甘蔗、海带不依赖各段中心。
            seam = p.copy(); seam[:, 1] = 1
            lower = mid.copy(); lower[:, 1] = -32
            upper = mid.copy(); upper[:, 1] = 32
            for a, b in ((10103, 10104), (10107, 10108), (10105, 10105), (10109, 10109), (10110, 10110)):
                assert np.allclose(scene.render(seam, lower, a), scene.render(seam, upper, b), atol=2e-5)
            for plant in (0, -1, 10001, 10002, 10100, 10111):
                assert np.allclose(scene.render(p, mid, plant), p, atol=2e-5)
            for entry in ('world-1/gbuffers_terrain.vsh', 'world1/gbuffers_terrain.vsh',
                          'world0/gbuffers_entities.vsh', 'world0/gbuffers_hand.vsh', 'world0/gbuffers_water.vsh'):
                assert np.allclose(scene.render(p, mid, entry=entry), p, atol=2e-5)
            for plant, strength in ((10101,'GRASS'), (10102,'CROP'), (10105,'REED'), (10106,'WATER'), (10110,'LEAF')):
                for options in ({'VEGETATION_WIND':'0'}, {f'WIND_{strength}_STRENGTH':'0.0'}):
                    assert np.allclose(scene.render(p, mid, plant, options=options), p, atol=2e-5)
            far = p + [200, 0, 0]
            assert np.allclose(scene.render(far, mid), far, atol=3e-5)
            assert np.allclose(scene.render(p, mid, seconds=1, options={'VEGETATION_WIND_SPEED':'0.0'}),
                               scene.render(p, mid, seconds=50, options={'VEGETATION_WIND_SPEED':'0.0'}), atol=2e-5)
            print('PASS: roots, double plants, shared edges, shadow alignment, camera translation, weather, time wraps, switches and isolation')
            if args.benchmark:
                # 相同顶点数量与反馈带宽，仅比较实际顶点阶段的开关成本；不代表完整游戏帧时间。
                vertices = np.tile(p, (12000, 1))
                centers = np.tile(mid, (12000, 1))
                report = {'gpu': gl.description(), 'vertices_per_pass': len(vertices), 'median_ms': {}}
                for entry in ('world0/gbuffers_terrain.vsh', 'world0/shadow.vsh'):
                    for enabled in ('0', '1'):
                        _, ms = scene.render(vertices, centers, entry=entry, options={'VEGETATION_WIND':enabled}, repeats=23)
                        report['median_ms'][f'{entry}:{enabled}'] = ms
                artifact_path('vegetation-wind-benchmark.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
                print(json.dumps(report, indent=2))
        finally:
            scene.close()


if __name__ == '__main__':
    main()
