"""使用实际云层入口验证天气、群系、深度遮挡与世界空间投影。"""
from artifact_paths import artifact_path

import ctypes as c
import math
import time

import numpy as np
from PIL import Image

from gl_context import GLContext
from test_shadow_filter import FilterScene
from test_sky_background import VERTEX
from validate_shaders import ROOT, SHADERS, configure, expand


class CloudScene:
    def __init__(self, gl, size=256):
        self.gl, self.size = gl, size
        self.target = FilterScene(gl, size=size)
        self.programs = {}
        self.shadow_map = None
        self.cloud_pipeline = None
        self.textures = (c.c_uint * 3)()
        gl.function('glGenTextures', None, c.c_int, c.POINTER(c.c_uint))(3, self.textures)

    def render(self, options=None, dimension='world0', dh=False, rain=0.0, storm=0.0,
               humidity=0.5, highland=0.0, pitch=30, camera=(0,80,0), seconds=0,
               background=(0.12,0.3,0.65), depth=1.0, dh_depth=1.0, shadow=False, night=False, eye=0,
               reference=False, lighting=False, skylight=1.0, blocklight=0.0, density_slice=False,
               fog=(0.65,0.74,0.86), sky=(0,0,0), fov=90, sun_direction=None,
               shadow_center=None, shadow_span=4096, full_resolution=False,
               lightning=(0,0,0,0), lightning_pulse=0):
        gl, size = self.gl, self.size
        gl.function('glBindFramebuffer',None,c.c_uint,c.c_uint)(0x8D40,self.target.fbo)
        gl.function('glViewport',None,c.c_int,c.c_int,c.c_int,c.c_int)(0,0,size,size)
        options = options or {}
        key = (tuple(sorted(options.items())), dimension, dh, shadow, reference, lighting, density_slice, full_resolution)
        if key not in self.programs:
            if shadow or density_slice:
                source = '#version 330 compatibility\n' + expand(SHADERS/'lib/settings.glsl')
                if lighting:
                    source += '\n#define WORLD_OVERWORLD\n#undef SHADOWS\n' + expand(SHADERS/'lib/lighting.glsl')
                else:
                    source += '\nuniform float rainStrength;\n' + expand(SHADERS/'lib/clouds.glsl')
                source += '''
in vec2 texcoord;
uniform vec3 testShadowCenter;
uniform float testShadowSpan;
layout(location=0) out vec4 scene;
void main() {
    vec3 world = testShadowCenter + vec3((texcoord.x - 0.5) * testShadowSpan, 0, (texcoord.y - 0.5) * testShadowSpan);
    float shadow = cloudSurfaceShadow(world, normalize(vec3(0.4, 1, 0.2)));
    scene = vec4(vec3(shadow), 1);
}
'''
                if density_slice:
                    source = source.replace('cloudSurfaceShadow(world, normalize(vec3(0.4, 1, 0.2)))',
                                            'cloudDensity(world) * 50.0')
                if reference:
                    source = source.replace('cloudSurfaceShadow(world, normalize(vec3(0.4, 1, 0.2)))',
                                            'mix(1.0, cloudTransmission(world, normalize(vec3(0.4, 1, 0.2)), 128), CLOUD_SHADOW_STRENGTH)')
                if lighting:
                    source = source.replace('in vec2 texcoord;', 'uniform float testSkylight;\nuniform float testBlocklight;\nin vec2 texcoord;')
                    source = source.replace('scene = vec4(vec3(shadow), 1);',
                                            'scene = vec4(surfaceLighting(world-cameraPosition, vec3(0,1,0), vec2(testBlocklight, testSkylight), 1.0), 1);')
            else:
                source = expand(SHADERS/dimension/('deferred1.fsh' if dimension=='world0' else 'deferred.fsh'))
                if full_resolution:
                    source = source.replace('cloudReconstruct(texcoord)','cloudFullResolution(texcoord)')
                if dh:
                    source = source.replace('#version 330 compatibility', '#version 330 compatibility\n#define DISTANT_HORIZONS')
            source = source.replace('normalize(vec3(0.4, 1, 0.2))','normalize(mat3(gbufferModelViewInverse) * shadowLightPosition)') if lighting else source
            if shadow and not lighting:
                source = source.replace('in vec2 texcoord;', 'uniform vec3 testShadowLight;\nin vec2 texcoord;')
                source = source.replace('normalize(vec3(0.4, 1, 0.2))','normalize(testShadowLight)')
            self.programs[key] = gl.program(VERTEX, configure(source, options))
        program = self.programs[key]
        gl.function('glUseProgram', None, c.c_uint)(program)
        locate = gl.function('glGetUniformLocation', c.c_int, c.c_uint, c.c_char_p)

        def scalar(name, value):
            gl.function('glUniform1f', None, c.c_int, c.c_float)(locate(program,name.encode()), value)

        for unit, (name, data) in enumerate((('colortex0', background), ('depthtex0', depth), ('dhDepthTex0', dh_depth))):
            gl.function('glActiveTexture', None, c.c_uint)(0x84C0 + unit)
            self.target.bind_texture(self.textures[unit])
            if unit == 0:
                pixels = np.empty((size,size,4), np.float32)
                pixels[...,:3] = data
                pixels[...,3] = 1
                internal, fmt = 0x8814, 0x1908
            else:
                pixels = np.full((size,size),data,np.float32) if np.isscalar(data) else np.asarray(data,np.float32)
                internal, fmt = 0x822E, 0x1903
            self.target.upload(pixels, internal, size, fmt)
            self.target.parameter(0x2801,0x2600)
            self.target.parameter(0x2800,0x2600)
            gl.function('glUniform1i', None, c.c_int, c.c_int)(locate(program,name.encode()),unit)
        projection = np.array([[1,0,0,0],[0,1,0,0],[0,0,-1.00002,-0.200002],[0,0,-1,0]],np.float32)
        projection[0,0] = projection[1,1] = 1.0 / math.tan(math.radians(fov)*0.5)
        angle = math.radians(pitch)
        co, si = math.cos(angle), math.sin(angle)
        model = np.array([[1,0,0,0],[0,co,-si,0],[0,si,co,0],[0,0,0,1]],np.float32)
        for name,matrix in [('gbufferProjectionInverse',np.linalg.inv(projection)),
                            ('dhProjectionInverse',np.linalg.inv(projection)),('gbufferModelViewInverse',model)]:
            data = np.ascontiguousarray(matrix.T)
            gl.function('glUniformMatrix4fv',None,c.c_int,c.c_int,c.c_ubyte,c.c_void_p)(
                locate(program,name.encode()),1,0,data.ctypes.data_as(c.c_void_p))
        sun = model[:3,:3].T @ np.array(sun_direction if sun_direction is not None else [0.4, -1 if night else 1, 0.2])
        for name,data in [('cameraPosition',camera),('sunPosition',sun),('shadowLightPosition',sun),('fogColor',fog),('skyColor',sky)]:
            gl.function('glUniform3f',None,c.c_int,c.c_float,c.c_float,c.c_float)(locate(program,name.encode()),*data)
        for name,data in [('testShadowCenter',camera if shadow_center is None else shadow_center),
                          ('testShadowLight',(0.4,1,0.2) if sun_direction is None else sun_direction)]:
            gl.function('glUniform3f',None,c.c_int,c.c_float,c.c_float,c.c_float)(locate(program,name.encode()),*data)
        scalar('testShadowSpan',shadow_span)
        gl.function('glUniform4f',None,c.c_int,c.c_float,c.c_float,c.c_float,c.c_float)(locate(program,b'lightningBoltPosition'),*lightning)
        scalar('cloudLightningPulse',lightning_pulse)
        for name,value in [('rainStrength',rain),('thunderStrength',storm),('cloudHumidity',humidity),
                           ('cloudHighland',highland),('frameTimeCounter',seconds),
                           ('testSkylight',skylight),('testBlocklight',blocklight)]:
            scalar(name,value)
        gl.function('glUniform1i',None,c.c_int,c.c_int)(locate(program,b'isEyeInWater'),eye)
        if shadow and not reference and not density_slice:
            self.update_cloud_shadow(camera=camera,rain=rain,storm=storm,humidity=humidity,
                                     highland=highland,seconds=seconds,options=options,
                                     light=sun_direction if sun_direction is not None else (0.4,-1 if night and lighting else 1,0.2))
        if not shadow and not density_slice and not full_resolution and dimension=='world0':
            self.update_cloud_pipeline(program,options,dh)
        gl.function('glDrawArrays',None,c.c_uint,c.c_int,c.c_int)(0x0004,0,3)
        result = np.empty((size,size,4),np.float32)
        gl.function('glReadPixels',None,c.c_int,c.c_int,c.c_int,c.c_int,c.c_uint,c.c_uint,c.c_void_p)(
            0,0,size,size,0x1908,0x1406,result.ctypes.data_as(c.c_void_p))
        assert gl.function('glGetError',c.c_uint)() == 0
        assert np.isfinite(result).all()
        return result[...,:3]

    def update_cloud_pipeline(self,program,options,dh):
        from cloud_pipeline import CloudPipeline
        gl = self.gl
        get = gl.function('glGetIntegerv',None,c.c_uint,c.POINTER(c.c_int))
        framebuffer,active,texture = c.c_int(),c.c_int(),c.c_int()
        viewport = (c.c_int*4)()
        for parameter,value in ((0x8CA6,framebuffer),(0x84E0,active),(0x8069,texture)):
            get(parameter,c.byref(value))
        get(0x0BA2,viewport)
        if self.cloud_pipeline is None:
            self.cloud_pipeline = CloudPipeline(gl,self.size)
            gl.function('glBindTexture',None,c.c_uint,c.c_uint)(0x0DE1,texture.value)
        self.cloud_pipeline.render(program,options,dh)
        gl.function('glBindFramebuffer',None,c.c_uint,c.c_uint)(0x8D40,framebuffer.value)
        gl.function('glViewport',None,c.c_int,c.c_int,c.c_int,c.c_int)(*viewport)
        gl.function('glUseProgram',None,c.c_uint)(program)
        self.cloud_pipeline.bind(program)
        gl.function('glActiveTexture',None,c.c_uint)(active.value)
        gl.function('glBindTexture',None,c.c_uint,c.c_uint)(0x0DE1,texture.value)

    def update_cloud_shadow(self,**view):
        from cloud_shadow_map import CloudShadowMap
        gl = self.gl
        get = gl.function('glGetIntegerv',None,c.c_uint,c.POINTER(c.c_int))
        program, framebuffer, active, texture = c.c_int(), c.c_int(), c.c_int(), c.c_int()
        viewport = (c.c_int*4)()
        for parameter,value in ((0x8B8D,program),(0x8CA6,framebuffer),(0x84E0,active),(0x8069,texture)):
            get(parameter,c.byref(value))
        get(0x0BA2,viewport)
        if self.shadow_map is None:
            self.shadow_map = CloudShadowMap(gl)
        self.shadow_map.update(**view)
        gl.function('glBindFramebuffer',None,c.c_uint,c.c_uint)(0x8D40,framebuffer.value)
        gl.function('glViewport',None,c.c_int,c.c_int,c.c_int,c.c_int)(*viewport)
        gl.function('glUseProgram',None,c.c_uint)(program.value)
        self.shadow_map.bind(program.value)
        gl.function('glActiveTexture',None,c.c_uint)(active.value)
        gl.function('glBindTexture',None,c.c_uint,c.c_uint)(0x0DE1,texture.value)

    def close(self):
        if self.cloud_pipeline is not None:
            self.cloud_pipeline.close()
        if self.shadow_map is not None:
            self.shadow_map.close()
        for program in self.programs.values():
            self.gl.delete_program(program)
        self.gl.function('glDeleteTextures',None,c.c_int,c.POINTER(c.c_uint))(3,self.textures)
        self.target.close()


def main():
    with GLContext() as gl:
        print(gl.description(), flush=True)
        scene = CloudScene(gl)
        try:
            start = time.perf_counter()
            clear = scene.render()
            rain = scene.render(rain=1)
            storm = scene.render(rain=1,storm=1)
            highland = scene.render(highland=1)
            bg = np.array([0.12,0.3,0.65])
            coverages = []
            for args in ({},{'rain':1},{'rain':1,'storm':1},{'highland':1}):
                # 黑白背景差直接给出云层的透射率，避免把明暗误当成覆盖率。
                black = scene.render(background=(0,0,0),**args)
                white = scene.render(background=(1,1,1),**args)
                opacity = 1 - (white-black)[...,0]
                assert opacity.min() > -1e-5 and opacity.max() <= 1.0001
                coverages.append(float(np.mean(opacity > 0.1)))
            print('Coverage: fair / rain / storm / highland',coverages,flush=True)
            assert coverages[2] > coverages[1] > coverages[0] > coverages[3]
            assert coverages[3] < 0.25 and coverages[1] < 0.98
            # 高仰角视野全部落在云层范围内，直接检验阴雨覆盖率与云色。
            weather_previews = []
            for camera in ((0,80,0),(3970,238,4869),(-1800,80,-2400)):
                weather_levels = []
                row = [scene.render(camera=camera,pitch=65)]
                for storm_value in (0,1):
                    view = dict(camera=camera,pitch=65,rain=1,storm=storm_value)
                    black = scene.render(background=(0,0,0),**view)
                    white = scene.render(background=(1,1,1),**view)
                    opacity = 1-(white-black)[...,0]
                    coverage = float(np.mean(opacity > 0.1))
                    if storm_value:
                        assert coverage > 0.995, '雷暴须形成完整云幕'
                        assert float(np.mean(opacity)) > 0.98, '雷暴云幕须遮住远层天空'
                    else:
                        assert 0.70 < coverage < 0.995, '雨云须覆盖大部分天空并保留云缝'
                    color = black / np.maximum(opacity[...,None],0.001)
                    level = float(np.mean(color[opacity > 0.8]))
                    weather_levels.append(level)
                    row.append(scene.render(**view))
                assert weather_levels[0] < 0.25
                assert weather_levels[1] < min(0.07,weather_levels[0]*0.5), '雷暴云须比雨云更深暗'
                weather_previews.append(np.concatenate(row,axis=1))
            weather_preview = np.concatenate([row[::-1] for row in weather_previews],axis=0)
            Image.fromarray(np.uint8(np.clip(weather_preview,0,1)**(1/2.2)*255)).save(artifact_path('cloud-weather-preview.png'))
            for dim in ('world-1','world1'):
                assert np.allclose(scene.render(dimension=dim),bg,atol=1e-6)
            assert np.allclose(scene.render(options={'VOLUMETRIC_CLOUDS':'0'}),bg,atol=1e-6)
            assert np.allclose(scene.render(depth=0.99),bg,atol=1e-6)
            assert np.allclose(scene.render(dh=True,dh_depth=0.99),bg,atol=1e-6)
            assert np.allclose(scene.render(dh=True),clear,atol=1e-5)
            half = np.ones((scene.size,scene.size),np.float32)
            half[:,:scene.size//2] = 0.99
            partial = scene.render(dh=True,dh_depth=half)
            assert np.allclose(partial[:,:scene.size//2],bg,atol=1e-6)
            # 深度重建的两像素邻域独立与原分辨率参考比较，远离轮廓的天空保持一致。
            edge = scene.size//2
            assert np.allclose(partial[:,edge+2:],clear[:,edge+2:],atol=1e-5)
            edge_reference = scene.render(dh=True,dh_depth=half,full_resolution=True)
            assert np.mean(abs(partial[:,edge:edge+2]-edge_reference[:,edge:edge+2]))<0.015
            assert np.allclose(scene.render(pitch=-65),bg,atol=1e-6)
            assert np.mean(abs(scene.render(eye=1)-bg))>0.001, "水下向上观察必须保留云层"
            for eye in (2,3):
                assert np.allclose(scene.render(eye=eye),bg,atol=1e-6)
            scene.render(camera=(0,420,0),pitch=0)
            scene.render(camera=(0,700,0),pitch=-50)
            assert np.max(np.abs(scene.render(seconds=3600)-clear)) < 0.001
            assert np.mean(np.abs(scene.render(seconds=60)-clear)) > 0.005
            assert np.allclose(scene.render(options={'CLOUD_SPEED':'0.0'},seconds=0),
                               scene.render(options={'CLOUD_SPEED':'0.0'},seconds=600))
            assert np.allclose(scene.render(options={'CLOUD_BIOME_VARIATION':'0.0'},humidity=0,highland=1),
                               scene.render(options={'CLOUD_BIOME_VARIATION':'0.0'},humidity=1,highland=0))
            # 水平与垂直微移不得在覆盖场裁剪处形成密度断面。
            density = scene.render(density_slice=True,camera=(0,400,0))
            assert density.max() > 0.1 and np.mean(density == 0) > 0.1
            for camera in ((0.01,400,0),(0,400.01,0),(0,400,0.01)):
                shifted = scene.render(density_slice=True,camera=camera)
                assert np.max(abs(shifted-density)) < 0.005, '云密度场须随世界坐标连续变化'
            for height in (319,577):
                assert np.allclose(scene.render(density_slice=True,camera=(0,height,0)),0)
            shadows = scene.render(shadow=True)
            assert shadows.min() < 0.4 and shadows.max() > 0.99
            assert np.allclose(scene.render(shadow=True,options={'CLOUD_SHADOWS':'0'}),1)
            assert np.allclose(scene.render(shadow=True,options={'VOLUMETRIC_CLOUDS':'0'}),1)
            assert np.allclose(scene.render(shadow=True,camera=(0,700,0)),1)
            reference = scene.render(shadow=True,reference=True)
            error = np.abs(reference-shadows)
            assert error.mean() < 0.015 and np.percentile(error,99) < 0.06, '地表投影须接近高采样密度场积分'
            for storm_value in (0,1):
                shadow_view = dict(shadow=True,rain=1,storm=storm_value)
                error = abs(scene.render(**shadow_view)-scene.render(reference=True,**shadow_view))
                assert error.mean() < 0.015 and np.percentile(error,99) < 0.06, '厚云投影提前终止须保持积分精度'
            lit = scene.render(shadow=True,lighting=True)
            unshadowed = scene.render(shadow=True,lighting=True,options={'CLOUD_SHADOWS':'0'})
            assert np.mean(unshadowed-lit) > 0.03
            assert np.all(lit <= unshadowed+1e-5) and lit.min() > 0.01
            for blocklight in (0.0,1.0):
                assert np.allclose(scene.render(shadow=True,lighting=True,skylight=0,blocklight=blocklight),
                                   scene.render(shadow=True,lighting=True,skylight=0,blocklight=blocklight,options={'CLOUD_SHADOWS':'0'}))
            night = scene.render(night=True,background=(0.001,0.002,0.004))
            assert night.mean() < clear.mean()*0.5
            for samples in (16,32,48):
                scene.render(options={'CLOUD_SAMPLES':str(samples)})
            # 低仰角的长视线与高采样参考对照，防止规则条带被普通覆盖测试遗漏。
            comparisons = []
            for rain_value,storm_value in ((0,0),(1,0),(1,1)):
                for pitch in (5,25):
                    view = dict(camera=(3969,256,4924),pitch=pitch,highland=0.5,rain=rain_value,storm=storm_value)
                    sampled = scene.render(**view)
                    reference = scene.render(options={'CLOUD_SAMPLES':'256'},**view)
                    error = np.abs(sampled-reference)
                    assert error.mean() < 0.004 and np.percentile(error,99) < 0.04, '晴雨长视线积分误差过大'
                    comparisons.append(np.concatenate([sampled,reference],axis=1))
            comparison = np.concatenate(comparisons,axis=0)
            Image.fromarray(np.uint8(np.clip(comparison[::-1],0,1)**(1/2.2)*255)).save(artifact_path('cloud-sampling-preview.png'))
            preview = np.concatenate([clear,rain,storm,highland],axis=1)
            path = artifact_path('clouds-preview.png')
            Image.fromarray(np.uint8(np.clip(preview[::-1],0,1)**(1/2.2)*255)).save(path)
            Image.fromarray(np.uint8(np.clip(shadows[::-1],0,1)*255)).save(artifact_path('cloud-shadows-preview.png'))
            print(f'PASS: weather, biomes, near/DH occlusion, dimensions, immersion, clock wrap, switches, shadow range; {time.perf_counter()-start:.2f}s',flush=True)
            print(path)
        finally:
            scene.close()


if __name__ == '__main__':
    main()
