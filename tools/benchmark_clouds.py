"""记录固定人工场景中晴天、降雨和雷暴的云绘制与地面云影 GPU 耗时。"""
from artifact_paths import artifact_path

import argparse
import ctypes as c
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np

from gl_context import GLContext
from test_clouds import CloudScene
import test_clouds
import cloud_pipeline


def measure(gl, scene, view, repeats):
    for _ in range(3):
        scene.render(**view)
    query = c.c_uint()
    function = gl.function
    function('glGenQueries',None,c.c_int,c.POINTER(c.c_uint))(1,c.byref(query))
    begin = function('glBeginQuery',None,c.c_uint,c.c_uint)
    end = function('glEndQuery',None,c.c_uint)
    draw = function('glDrawArrays',None,c.c_uint,c.c_int,c.c_int)

    draw_times = []
    def timed_draw(*arguments):
        begin(0x88BF,query.value)
        draw(*arguments)
        end(0x88BF)
        elapsed = c.c_uint64()
        function('glGetQueryObjectui64v',None,c.c_uint,c.c_uint,c.POINTER(c.c_uint64))(
            query.value,0x8866,c.byref(elapsed))
        draw_times.append(elapsed.value/1e6)

    def timed_function(name,*arguments):
        return timed_draw if name == 'glDrawArrays' else function(name,*arguments)

    times = []
    try:
        gl.function = timed_function
        for _ in range(repeats):
            draw_times.clear()
            scene.render(**view)
            times.append(sum(draw_times))
    finally:
        gl.function = function
        function('glDeleteQueries',None,c.c_int,c.POINTER(c.c_uint))(1,c.byref(query))
    return {'median_ms':float(np.median(times)), 'samples_ms':times}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--size',type=int,default=512,help='正方形渲染尺寸')
    parser.add_argument('--samples',type=int,choices=(16,32,48),default=32,help='云质量对应的基础采样数')
    parser.add_argument('--repeats',type=int,default=7,help='预热后的计时次数')
    parser.add_argument('--diagnose',action='store_true',help='逐项隔离云内照明、密度积分及云影开销')
    parser.add_argument('--compare-resolution',action='store_true',help='比较原分辨率积分与半分辨率积分及合成的总 GPU 耗时')
    parser.add_argument('--compare-lightning',action='store_true',help='比较闪电照云关闭、待机与亮起时的总 GPU 耗时')
    args = parser.parse_args()
    if args.size < 16 or args.repeats < 3:
        parser.error('渲染尺寸至少 16，计时至少 3 次')
    if args.diagnose:
        diagnose(args)
        return
    if args.compare_resolution:
        compare_resolution(args)
        return
    if args.compare_lightning:
        compare_lightning(args)
        return
    with GLContext() as gl:
        scene = CloudScene(gl,size=args.size)
        report = {'renderer':gl.description(),'resolution':[args.size,args.size],
                  'cloud_samples':args.samples,'power_state':'未控制','frame_limit':'无',
                  'scope':'人工场景全部绘制阶段，不含游戏几何、视距设置与加载器调度', 'cases':[]}
        try:
            for shadow in (False,True):
                for weather,rain,storm in (('fair',0,0),('rain',1,0),('storm',1,1)):
                    view = dict(camera=(0,80,0) if shadow else (3970,238,4869),pitch=55,
                                rain=rain,storm=storm,humidity=0.5,highland=0,seconds=0,
                                dh=False,shadow=shadow,options={'CLOUD_SAMPLES':str(args.samples)})
                    result = measure(gl,scene,view,args.repeats)
                    report['cases'].append({'pass':'shadow' if shadow else 'cloud',
                                            'weather':weather,'view':view,**result})
                    print(report['cases'][-1]['pass'],weather,round(result['median_ms'],3),'ms',flush=True)
        finally:
            scene.close()
    path = artifact_path('cloud-benchmark.json')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(path)


def diagnose(args):
    # 仅在离线编译输入中替换照明调用，发布着色器与配置保持不变。
    original = test_clouds.expand
    def density_only(path):
        source = original(path)
        return source.replace('cloudIllumination(p, lightDirection, ray, direct, ambient, density)', 'vec3(1.0)')
    report = {'resolution':[args.size,args.size],'power_state':'未控制',
              'scope':'人工场景全部绘制阶段；逐项关闭的差值不可相加，不能换算成游戏帧率', 'cases':[]}
    with GLContext() as gl:
        report['renderer'] = gl.description()
        print(report['renderer'],flush=True)
        for variant in ('full','density_only','disabled','shadow','shadow_disabled'):
            with patch.object(test_clouds,'expand',density_only if variant=='density_only' else original), \
                 patch.object(cloud_pipeline,'expand',density_only if variant=='density_only' else original):
                scene = CloudScene(gl,size=args.size)
                try:
                    for weather,rain,storm in (('fair',0,0),('rain',1,0),('storm',1,1)):
                        shadow = variant.startswith('shadow')
                        options = {'CLOUD_SAMPLES':str(args.samples)}
                        if variant=='disabled': options['VOLUMETRIC_CLOUDS']='0'
                        if variant=='shadow_disabled': options['CLOUD_SHADOWS']='0'
                        view = dict(camera=(0,80,0) if shadow else (3970,238,4869),pitch=55,
                                    rain=rain,storm=storm,seconds=0,shadow=shadow,options=options)
                        result = measure(gl,scene,view,args.repeats)
                        report['cases'].append(dict(variant=variant,weather=weather,**result))
                        print(variant,weather,round(result['median_ms'],3),'ms',flush=True)
                finally:
                    scene.close()
    path = artifact_path('cloud-diagnosis.json')
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(path)


def compare_lightning(args):
    report = {'resolution':[args.size,args.size],'power_state':'未控制',
              'scope':'雷暴人工场景，包含云积分与合成；脉冲人工注入，不代表游戏整帧开销', 'cases':[]}
    with GLContext() as gl:
        report['renderer'] = gl.description()
        print(report['renderer'],flush=True)
        scene = CloudScene(gl,args.size)
        try:
            for name in ('off','idle','flash'):
                options = {'CLOUD_SAMPLES':str(args.samples),'CLOUD_LIGHTNING':'0' if name=='off' else '1'}
                view = dict(camera=(3970,238,4869),pitch=55,rain=1,storm=1,options=options,
                            lightning=(0,-158,-200,1) if name=='flash' else (0,0,0,0),
                            lightning_pulse=.7 if name=='flash' else 0)
                result = measure(gl,scene,view,args.repeats)
                report['cases'].append(dict(mode=name,**result))
                print(name,round(result['median_ms'],3),'ms',flush=True)
        finally:
            scene.close()
    path = artifact_path('cloud-lightning-benchmark.json')
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(path)


def compare_resolution(args):
    report = {'resolution':[args.size,args.size],'power_state':'未控制',
              'scope':'固定人工场景；计入半分辨率积分及全分辨率合成，不含游戏场景和加载器调度', 'cases':[]}
    with GLContext() as gl:
        report['renderer'] = gl.description()
        print(report['renderer'],flush=True)
        scene = CloudScene(gl,args.size)
        try:
            for pitch in (5,55):
                for rain,storm in ((0,0),(1,0),(1,1)):
                    for full in (True,False):
                        view = dict(camera=(3970,238,4869),pitch=pitch,rain=rain,storm=storm,
                                    options={'CLOUD_SAMPLES':str(args.samples)},full_resolution=full)
                        result = measure(gl,scene,view,args.repeats)
                        report['cases'].append(dict(pitch=pitch,rain=rain,storm=storm,full_resolution=full,**result))
                        print(pitch,rain,storm,'full' if full else 'half',round(result['median_ms'],3),'ms',flush=True)
        finally:
            scene.close()
    path = artifact_path('cloud-resolution-benchmark.json')
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(path)


if __name__ == '__main__':
    main()
