"""验证真实最终阶段的水下光束遮挡、天气、维度与近景深度边界。"""
from artifact_paths import artifact_path
import ctypes as c
import argparse
import json
import numpy as np
from PIL import Image
from gl_context import GLContext
from test_clouds import CloudScene
from test_sky_background import VERTEX
from validate_shaders import ROOT, SHADERS, expand, configure
from benchmark_clouds import measure
from underwater_pipeline import UnderwaterPipeline


class UnderwaterScene(CloudScene):
    def __init__(self,gl,size=256):
        super().__init__(gl,size)
        self.water_pipeline=UnderwaterPipeline(gl,size)
        self.shadow=c.c_uint()
        gl.function('glGenTextures',None,c.c_int,c.POINTER(c.c_uint))(1,c.byref(self.shadow))

    def render(self,enabled=1,samples=8,eye=1,dimension='world0',distance=16,dh=False,
               blocked=False,rain=0,night=False,seconds=0,pattern=False,shadows=True,reference=False,foreground=False,
               sun_direction=None, silhouette=False, slope=False, camera_offset=None):
        gl,size=self.gl,self.size
        key=(enabled,samples,dimension,shadows,reference)
        options={'WATER_LIGHT_SHAFTS':str(enabled),'WATER_SHAFT_SAMPLES':str(samples)}
        if not shadows: options['SHADOWS']=None
        if key not in self.programs:
            source=expand(SHADERS/dimension/'final.fsh').replace('#version 330 compatibility','#version 330 compatibility\n#define DISTANT_HORIZONS')
            if reference:
                source=source.replace('underwaterFog(color,distance)+underwaterLightReconstruct(uv,distance)',
                                      'underwaterFog(color,distance)+underwaterSunbeams(uv,distance)')
            options={'WATER_LIGHT_SHAFTS':str(enabled),'WATER_SHAFT_SAMPLES':str(samples)}
            if not shadows: options['SHADOWS']=None
            self.programs[key]=gl.program(VERTEX,configure(source,options))
        p=self.programs[key]
        gl.function('glUseProgram',None,c.c_uint)(p)
        gl.function('glBindFramebuffer',None,c.c_uint,c.c_uint)(0x8D40,self.target.fbo)
        gl.function('glViewport',None,c.c_int,c.c_int,c.c_int,c.c_int)(0,0,size,size)
        def loc(name): return gl.function('glGetUniformLocation',c.c_int,c.c_uint,c.c_char_p)(p,name.encode())
        angle=np.radians(25)
        model=np.array([[1,0,0,0],[0,np.cos(angle),-np.sin(angle),0],[0,np.sin(angle),np.cos(angle),0],[0,0,0,1]],np.float32)
        shadow_model=np.eye(4,dtype=np.float32)
        if camera_offset is not None:
            model[:3,3]=camera_offset
            shadow_model[:3,3]=-np.array(camera_offset)
        projection=np.array([[1,0,0,0],[0,1,0,0],[0,0,-1.0008,-.20008],[0,0,-1,0]],np.float32)
        for name,m in [('gbufferModelViewInverse',model),('gbufferProjectionInverse',np.linalg.inv(projection)),
                       ('dhProjectionInverse',np.linalg.inv(projection)),('shadowModelView',shadow_model),
                       ('shadowProjection',np.diag([1/64,1/64,1/128,1]))]:
            data=np.ascontiguousarray(m.T,dtype=np.float32)
            gl.function('glUniformMatrix4fv',None,c.c_int,c.c_int,c.c_ubyte,c.c_void_p)(loc(name),1,0,data.ctypes.data_as(c.c_void_p))
        sun=model[:3,:3].T@np.array([.3,-1 if night else 1,.2] if sun_direction is None else sun_direction)
        for name,value in [('sunPosition',sun),('cameraPosition',(3694,55,4782))]:
            gl.function('glUniform3f',None,c.c_int,c.c_float,c.c_float,c.c_float)(loc(name),*value)
        for name,value in [('rainStrength',rain),('frameTimeCounter',seconds),('waterOcean',1)]:
            gl.function('glUniform1f',None,c.c_int,c.c_float)(loc(name),value)
        gl.function('glUniform1i',None,c.c_int,c.c_int)(loc('isEyeInWater'),eye)
        axis=(np.arange(size)+.5)/size*2-1
        x,y=np.meshgrid(axis,axis)
        ray_distance=distance+x*distance*.5 if slope else distance
        viewz=-ray_distance/np.sqrt(1+x*x+y*y)
        depth=((projection[2,2]*viewz+projection[2,3])/(-viewz)*.5+.5).astype(np.float32)
        if foreground:
            nearz=-.2/np.sqrt(1+x*x+y*y)
            near=((projection[2,2]*nearz+projection[2,3])/(-nearz)*.5+.5).astype(np.float32)
            depth[:,size//2]=near[:,size//2]
        background=np.full((size,size,4),.04,np.float32)
        for unit,name,pixels in [(0,'colortex0',background),(1,'depthtex0',np.ones_like(depth) if dh else depth),
                                 (2,'dhDepthTex0',depth if dh else np.ones_like(depth))]:
            gl.function('glActiveTexture',None,c.c_uint)(0x84C0+unit)
            self.target.bind_texture(self.textures[unit])
            self.target.upload(pixels,0x8814 if unit==0 else 0x822E,size,0x1908 if unit==0 else 0x1903)
            self.target.parameter(0x2801,0x2600); self.target.parameter(0x2800,0x2600)
            gl.function('glUniform1i',None,c.c_int,c.c_int)(loc(name),unit)
        gl.function('glActiveTexture',None,c.c_uint)(0x84C0+3)
        self.target.bind_texture(self.shadow)
        mask=np.full((size,size),0 if blocked else 1,np.float32)
        if pattern: mask[:,np.arange(size)%12<6]=0
        if silhouette:
            # 孤立遮挡物用于检查体积积分是否复制出多层轮廓。
            mask[(abs(x-.12)<.045)&(abs(y-.08)<.08)]=0
        self.target.upload(mask,0x8CAC,size,0x1902)
        for name,value in [(0x2801,0x2601),(0x2800,0x2601),(0x884C,0x884E),(0x884D,0x0203)]:
            self.target.parameter(name,value)
        gl.function('glUniform1i',None,c.c_int,c.c_int)(loc('shadowtex1'),3)
        self.water_pipeline.render(p,options,dimension)
        gl.function('glBindFramebuffer',None,c.c_uint,c.c_uint)(0x8D40,self.target.fbo)
        gl.function('glViewport',None,c.c_int,c.c_int,c.c_int,c.c_int)(0,0,size,size)
        gl.function('glDrawArrays',None,c.c_uint,c.c_int,c.c_int)(0x0004,0,3)
        result=np.empty((size,size,4),np.float32)
        gl.function('glReadPixels',None,c.c_int,c.c_int,c.c_int,c.c_int,c.c_uint,c.c_uint,c.c_void_p)(0,0,size,size,0x1908,0x1406,result.ctypes.data_as(c.c_void_p))
        assert np.isfinite(result).all() and gl.function('glGetError',c.c_uint)()==0
        return result

    def close(self):
        self.water_pipeline.close()
        self.gl.function('glDeleteTextures',None,c.c_int,c.POINTER(c.c_uint))(1,c.byref(self.shadow))
        super().close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--benchmark',action='store_true')
    args=parser.parse_args()
    with GLContext() as gl:
        scene=UnderwaterScene(gl,512 if args.benchmark else 256)
        try:
            base=scene.render(enabled=0)
            lit=scene.render()
            assert (lit-base)[...,:3].max()>.05 and (lit-base).min()>-1e-6
            for kwargs in ({'blocked':True},{'rain':1},{'night':True},{'eye':0},{'eye':2},
                           {'dimension':'world-1'},{'dimension':'world1'},{'shadows':False},{'distance':100000}):
                assert np.allclose(scene.render(**kwargs),scene.render(enabled=0,**kwargs),atol=1e-6), kwargs
            assert np.allclose(lit,scene.render(dh=True),atol=1e-5)
            assert np.mean(abs(lit-scene.render(reference=True)))<.015, '半分辨率重建应保持散射亮度'
            edge=scene.render(foreground=True)
            edge_base=scene.render(foreground=True,enabled=0)
            assert (edge-edge_base)[:,scene.size//2,:3].mean()<.01, '单像素前景不能泄漏远处光束'
            assert np.allclose(edge,scene.render(foreground=True,dh=True),atol=1e-5)
            short=scene.render(distance=.2)-scene.render(distance=.2,enabled=0)
            assert short[...,:3].mean()<(lit-base)[...,:3].mean()*.1, '前景与出水界面必须终止光束'
            moving=scene.render(seconds=3)
            assert np.allclose(lit,moving,atol=1e-6), '无遮挡均匀水体不能凭空产生流动光柱'
            toward=scene.render(sun_direction=(0,.45,-1),reference=True)
            away=scene.render(sun_direction=(0,.45,1),reference=True)
            assert toward[...,:3].mean()>away[...,:3].mean()+.01, '朝向太阳时散射应更强'
            # 对称光源高度排除昼夜强度变化，只比较观察方向的散射响应。
            forward_sun=(0,.4226,-.9063)
            forward=scene.render(sun_direction=forward_sun)
            backward=scene.render(sun_direction=(0,.4226,.9063))
            center=scene.size//2
            forward_light=(forward-base)[center,center,:3].mean()
            backward_light=(backward-base)[center,center,:3].mean()
            assert backward_light<forward_light*.05, '背向阳光不能保留强直射散射并放大实体体积暗影'
            for sun in (None,forward_sun):
                original=scene.render(silhouette=True,sun_direction=sun)
                offset=scene.render(silhouette=True,sun_direction=sun,camera_offset=(.8,-.2,.5))
                assert np.allclose(original,offset,atol=1e-5), '镜头与阴影坐标的配对平移不能移动体积遮挡'
            # 均匀介质的解析积分不应随采样数改变，也不应出现逐像素格纹。
            smooth=scene.render(reference=True)
            for count in (4,12):
                assert np.max(abs(smooth-scene.render(samples=count,reference=True)))<1e-4, '均匀受光积分须与采样数无关'
            curvature=np.diff(smooth[...,:3],n=2,axis=1)
            assert np.max(abs(curvature))<.001, '均匀受光区域不能出现高频像素纹理'
            patterned=scene.render(pattern=True)
            assert base.mean()<patterned.mean()<lit.mean(), '遮挡须切断阳光'
            silhouette=scene.render(silhouette=True)
            silhouette_reference=scene.render(silhouette=True,samples=128,reference=True)
            error=float(np.sqrt(np.mean((silhouette-silhouette_reference)**2)))
            assert error<.0014, ('孤立遮挡物不能被积分层复制为多重轮廓',error)
            # 只统计遮挡附近，避免大面积无变化背景稀释噪声和轮廓误差。
            for sloped in (False,True):
                result=scene.render(silhouette=True,slope=sloped,sun_direction=forward_sun)
                reference=scene.render(silhouette=True,slope=sloped,samples=128,reference=True,sun_direction=forward_sun)
                unblocked=scene.render(slope=sloped,samples=128,reference=True,sun_direction=forward_sun)
                region=np.max(abs(reference-unblocked),axis=2)>.003
                difference=result-reference
                assert region.any()
                local_error=float(np.sqrt(np.mean(difference[region,:3]**2)))
                assert local_error<.0012, ('遮挡附近的局部误差过大',sloped,local_error)
                curvature_error=float(np.sqrt(np.mean(np.diff(difference[...,:3],n=2,axis=1)**2)))
                assert curvature_error<.00015, ('遮挡附近存在高频颗粒或条纹',sloped,curvature_error)
            assert np.allclose(silhouette,scene.render(silhouette=True,dh=True),atol=1e-5)
            assert np.allclose(silhouette,scene.render(silhouette=True,seconds=3),atol=1e-6)
            for count in (4,12):
                assert np.mean(abs(lit-scene.render(samples=count)))<.025
            odd=UnderwaterScene(gl,257)
            try:
                assert np.mean(abs(odd.render()-odd.render(reference=True)))<.015, '奇数分辨率应保持重建一致'
            finally: odd.close()
            preview=np.concatenate([base,lit,patterned],axis=1)[...,:3]
            Image.fromarray(np.uint8(np.clip(preview[::-1],0,1)*255)).save(artifact_path('underwater-light-preview.png'))
            comparison=np.concatenate([silhouette,silhouette_reference,abs(silhouette-silhouette_reference)*10],axis=1)[...,:3]
            Image.fromarray(np.uint8(np.clip(comparison[::-1],0,1)*255)).save(artifact_path('underwater-silhouette-preview.png'))
            print('PASS: sunlight direction, occlusion, weather, dimensions, medium, DH, interface distance, smooth integration and quality')
            if args.benchmark:
                report={'renderer':gl.description(),'size':scene.size,'power_state':'未控制','cases':[]}
                for count in (0,4,8,12):
                    result=measure(gl,scene,dict(enabled=int(count>0),samples=count or 8),21)
                    report['cases'].append(dict(samples=count,**result))
                    print(count,round(result['median_ms'],3),'ms',flush=True)
                (artifact_path('underwater-light-benchmark.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        finally: scene.close()


if __name__=='__main__': main()
