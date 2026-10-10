"""固定透视水面逐项关闭效果，记录实际水面与表面光照函数的 GPU 绘制耗时。"""
from artifact_paths import artifact_path

import argparse
import ctypes as c
import json
import math

import numpy as np

from benchmark_clouds import measure
from gl_context import GLContext
from test_clouds import CloudScene
from test_sky_background import VERTEX
from validate_shaders import ROOT, SHADERS, configure, expand


class WaterScene(CloudScene):
    def render(self, options=None, dh=True, rain=0, storm=0, cache=True):
        gl, size = self.gl, self.size
        options = dict(options or {}, SHADOWS=None)
        key = (tuple(sorted(options.items())), dh, cache)
        if key not in self.programs:
            source = '#version 330 compatibility\n#define WORLD_OVERWORLD\n'
            if dh:
                source += '#define DISTANT_HORIZONS\n'
            source += expand(SHADERS/'lib/settings.glsl')+expand(SHADERS/'lib/color.glsl')
            source += '\nuniform vec3 fogColor;\nuniform float far;\n'
            source += expand(SHADERS/'lib/lighting.glsl')+expand(SHADERS/'lib/water_surface.glsl')
            source += '''
in vec2 texcoord;
layout(location=0) out vec4 scene;
void main() {
    vec4 v=gbufferProjectionInverse*vec4(texcoord*2.0-1.0,1,1);
    vec3 ray=normalize(mat3(gbufferModelViewInverse)*(v.xyz/v.w));
    vec3 position=ray*(-2.0/ray.y);
    vec3 light=surfaceLighting(position,vec3(0,1,0),vec2(0.5,15.5)/16.0,1.0);
    scene=shadeWater(position,vec3(0,1,0),light,1.0);
}
'''
            if not cache:
                source = source.replace('if (world.y < CLOUD_ALTITUDE) {','if (false) {')
            self.programs[key] = gl.program(VERTEX, configure(source,options))
        program = self.programs[key]
        gl.function('glUseProgram',None,c.c_uint)(program)
        locate = gl.function('glGetUniformLocation',c.c_int,c.c_uint,c.c_char_p)
        def loc(name):
            return locate(program,name.encode())
        angle = math.radians(-35)
        model = np.array([[1,0,0,0],[0,math.cos(angle),-math.sin(angle),0],
                          [0,math.sin(angle),math.cos(angle),0],[0,0,0,1]],np.float32)
        focal = 1/math.tan(math.radians(22.5))
        projection = np.array([[focal,0,0,0],[0,focal,0,0],[0,0,-1.0002,-0.20002],[0,0,-1,0]],np.float32)
        axis = ((np.arange(size)+0.5)/size*2-1)/focal
        x,y = np.meshgrid(axis,axis)
        ray = np.stack((x,y,-np.ones_like(x)),axis=-1)@model[:3,:3].T
        floor = ray*(-18/ray[...,1])[...,None]
        view = floor@model[:3,:3]
        depth = ((projection[2,2]*view[...,2]+projection[2,3])/(-view[...,2])*0.5+0.5).astype(np.float32)
        for name,matrix in [('gbufferProjection',projection),('gbufferProjectionInverse',np.linalg.inv(projection)),
                            ('dhProjectionInverse',np.linalg.inv(projection)),('gbufferModelViewInverse',model)]:
            data = np.ascontiguousarray(matrix.T)
            gl.function('glUniformMatrix4fv',None,c.c_int,c.c_int,c.c_ubyte,c.c_void_p)(loc(name),1,0,data.ctypes.data_as(c.c_void_p))
        sun = model[:3,:3].T@np.array([0.4,1,0.2])
        for name,value in [('cameraPosition',(3970,80,4869)),('sunPosition',sun),('shadowLightPosition',sun),
                           ('fogColor',(0.65,0.74,0.86)),('skyColor',(0.4,0.58,0.8))]:
            gl.function('glUniform3f',None,c.c_int,c.c_float,c.c_float,c.c_float)(loc(name),*value)
        for name,value in [('viewWidth',size),('viewHeight',size),('far',256),('cloudHumidity',0.5),
                           ('rainStrength',rain),('thunderStrength',storm),('waterOcean',1)]:
            gl.function('glUniform1f',None,c.c_int,c.c_float)(loc(name),value)
        gl.function('glUniform1i',None,c.c_int,c.c_int)(loc('isEyeInWater'),0)
        background = np.full((size,size,4),0.25,np.float32)
        for unit,name,pixels in ((0,'colortex5',background),(1,'depthtex1',depth),(2,'dhDepthTex1',np.ones_like(depth))):
            gl.function('glActiveTexture',None,c.c_uint)(0x84C0+unit)
            self.target.bind_texture(self.textures[unit])
            self.target.upload(pixels,0x8814 if unit==0 else 0x822E,size,0x1908 if unit==0 else 0x1903)
            for parameter,value in ((0x2801,0x2600),(0x2800,0x2600),(0x2802,0x812F),(0x2803,0x812F)):
                self.target.parameter(parameter,value)
            gl.function('glUniform1i',None,c.c_int,c.c_int)(loc(name),unit)
        if cache and options.get('CLOUD_SHADOWS','1') != '0':
            self.update_cloud_shadow(camera=(3970,80,4869),rain=rain,storm=storm,options=options)
        gl.function('glDrawArrays',None,c.c_uint,c.c_int,c.c_int)(0x0004,0,3)
        result = np.empty((size,size,4),np.float32)
        gl.function('glReadPixels',None,c.c_int,c.c_int,c.c_int,c.c_int,c.c_uint,c.c_uint,c.c_void_p)(
            0,0,size,size,0x1908,0x1406,result.ctypes.data_as(c.c_void_p))
        assert np.isfinite(result).all() and gl.function('glGetError',c.c_uint)()==0
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--size',type=int,default=512)
    parser.add_argument('--repeats',type=int,default=11)
    parser.add_argument('--output',default=str(artifact_path('water-benchmark.json')))
    parser.add_argument('--compare-cache',action='store_true',help='在同一进程比较直接积分和含准备阶段的云影缓存')
    args = parser.parse_args()
    if args.size<16 or args.repeats<3:
        parser.error('尺寸至少 16，重复次数至少 3')
    with GLContext() as gl:
        scene = WaterScene(gl,args.size)
        report = {'renderer':gl.description(),'size':args.size,'power_state':'未控制',
                  'scope':'全屏深水人工场景，包含云影准备阶段与水面绘制，不含地形阴影图、游戏几何及多层透明覆盖；各行不能相加', 'cases':[]}
        print(report['renderer'],flush=True)
        try:
            disabled = {name:'0' for name in ('CLOUD_SHADOWS','WATER_REFLECTIONS','WATER_FOAM','WATER_REFRACTION','WATER_WAVES')}
            variants = [('full',{}),('minimal',disabled)]+[(name,{name:'0'}) for name in disabled]
            for dh in (False,True):
                if args.compare_cache:
                    for rain,storm in ((0,0),(1,0),(1,1)):
                        for cache in (False,True):
                            result = measure(gl,scene,dict(dh=dh,rain=rain,storm=storm,cache=cache),args.repeats)
                            report['cases'].append(dict(cache=cache,dh=dh,rain=rain,storm=storm,**result))
                            print('DH' if dh else 'normal',rain,storm,'cache' if cache else 'direct',round(result['median_ms'],3),'ms',flush=True)
                    continue
                for name,options in variants:
                    result = measure(gl,scene,dict(options=options,dh=dh),args.repeats)
                    report['cases'].append(dict(variant=name,dh=dh,**result))
                    print('DH' if dh else 'normal',name,round(result['median_ms'],3),'ms',flush=True)
        finally:
            scene.close()
    path = ROOT/args.output
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(path)


if __name__ == '__main__':
    main()
