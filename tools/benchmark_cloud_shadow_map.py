"""测量云影附件生成与地表读取的合计 GPU 时间。"""

import argparse
import json
from artifact_paths import artifact_path
from benchmark_clouds import measure
from gl_context import GLContext
from test_clouds import CloudScene


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--size', type=int, default=512)
    parser.add_argument('--output', default='cloud-shadow-map-benchmark.json')
    args = parser.parse_args()
    if args.size < 16:
        parser.error('尺寸至少为 16')
    with GLContext() as gl:
        report = dict(renderer=gl.description(), size=args.size, power_state='未控制',
                      scope='包含云影附件生成与地表接收，不代表游戏帧率', cases=[])
        scene = CloudScene(gl, args.size)
        try:
            for camera in ((0,80,0), (3970,80,4869)):
                for rain, storm in ((0,0), (1,0), (1,1)):
                    result = measure(gl, scene, dict(shadow=True, camera=camera,
                        shadow_span=512, rain=rain, storm=storm), 15)
                    report['cases'].append(dict(camera=camera, rain=rain, storm=storm, **result))
                    print(camera, rain, storm, round(result['median_ms'], 3), 'ms', flush=True)
        finally:
            scene.close()
    artifact_path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
