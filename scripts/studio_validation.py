"""ComfyUI schema and graph checks without importing GPU modules."""
import math
from fractions import Fraction


def validate_media_specs(info,kind,expected):
    stream_kind='video' if kind in ('image','video') else 'audio'
    stream=next(s for s in info['streams'] if s['codec_type']==stream_kind)
    for key in ('width','height','sample_rate','channels'):
        if key in expected and int(stream.get(key,0))!=expected[key]:
            raise ValueError(f'Output {key} differs from requested specification')
    if kind=='video':
        rate=float(Fraction(stream.get('avg_frame_rate','0/1')))
        if abs(rate-expected.get('fps',rate))>0.001:raise ValueError('Output frame rate mismatch')
        count=int(stream['nb_frames']) if str(stream.get('nb_frames','')).isdigit() else round(float(info['format']['duration'])*rate)
        if 'frames' in expected and count!=expected['frames']:raise ValueError('Output frame count mismatch')
    if 'duration' in expected and abs(float(info['format']['duration'])-expected['duration'])>0.05:
        raise ValueError('Output duration mismatch')


def validate_workflow(graph,schemas):
    missing={n['class_type'] for n in graph.values()}-set(schemas)
    if missing:raise ValueError('Missing nodes: '+', '.join(sorted(missing)))
    edges={key:[] for key in graph}
    for key,node in graph.items():
        schema=schemas[node['class_type']]
        interface=schema.get('input',{})
        required=interface.get('required',{})
        optional=interface.get('optional',{})
        definitions={**required,**optional}
        values=node['inputs']
        for name,definition in required.items():
            # Dynamic inputs expand to dotted children, rather than one root value.
            if name not in values and not any(k.startswith(name+'.') for k in values):
                raise ValueError(f'{key}: missing required input {name}')
        for name,value in values.items():
            definition=definitions.get(name)
            if definition is None and interface:
                group=name.split('.')[0]
                if '.' not in name or group not in definitions:
                    raise ValueError(f'{key}: unknown input {name}')
            dtype=definition[0] if definition else None
            limits=definition[1] if definition and len(definition)>1 and isinstance(definition[1],dict) else {}
            if isinstance(value,list) and len(value)==2 and isinstance(value[0],str) and type(value[1]) is int:
                source,index=value
                if source not in graph:raise ValueError('Dangling graph link: '+source)
                outputs=schemas[graph[source]['class_type']].get('output')
                if index<0 or (outputs is not None and index>=len(outputs)):raise ValueError('Invalid output index')
                if outputs is not None and isinstance(dtype,str) and dtype not in ('*','COMFY_AUTOGROW_V3','COMFY_DYNAMICCOMBO_V3') and outputs[index] not in ('*',dtype):
                    raise ValueError(f'{key}.{name}: incompatible link {outputs[index]} -> {dtype}')
                edges[key].append(source)
            elif dtype in ('INT','FLOAT'):
                if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):raise ValueError(f'{key}.{name}: invalid number')
                if dtype=='INT' and type(value) is not int:raise ValueError('Integer required')
                if 'min' in limits and value<limits['min'] or 'max' in limits and value>limits['max']:raise ValueError('Input outside node range')
            elif dtype=='BOOLEAN' and type(value) is not bool:raise ValueError('Boolean required')
            elif isinstance(dtype,list) and node['class_type'] not in ('LoadImage','LoadImageMask','LoadAudio','LoadVideo') and value not in dtype:
                raise ValueError(f'{key}.{name}: unsupported choice {value}')
    done=set();visiting=set()
    def visit(key):
        if key in visiting:raise ValueError('Workflow graph cycle')
        if key in done:return
        visiting.add(key)
        for dependency in edges[key]:visit(dependency)
        visiting.remove(key);done.add(key)
    for key in graph:visit(key)
