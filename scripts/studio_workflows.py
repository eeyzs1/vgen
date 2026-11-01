"""H3 API graphs matched to locally inspected native/plugin interfaces."""
from pathlib import Path

DIT = 'minimax_h3_fl2va_pruned_int8_convrot.safetensors'
REF_DIT = 'minimax_h3_ref2va_pruned_int8_convrot.safetensors'
TE = 'qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors'
VAE = 'minimax_h3_video_vae_int8_convrot.safetensors'
AUDIO_VAE = 'minimax_h3_audio_vae_fp32.safetensors'
TURBO = 'minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors'


def node(kind, **inputs):
    return dict(class_type=kind,inputs=inputs)


def backbone(seed,steps,recipe='base',reference=False,sampler='res_multistep'):
    if reference and recipe=='turbo':
        raise ValueError('FL2VA Turbo is incompatible with REF2VA; use base recipe')
    graph={'model':node('UNETLoader',unet_name=REF_DIT if reference else DIT,weight_dtype='default'),
           'clip':node('CLIPLoader',clip_name=TE,type='minimax',device='default'),
           'vae':node('VAELoader',vae_name=VAE)}
    model=['model',0]
    if recipe=='turbo':
        graph['turbo']=node('LoraLoaderModelOnly',model=model,lora_name=TURBO,strength_model=1.0)
        model=['turbo',0]
        sampler='euler'
    graph['shift']=node('MiniMaxH3SigmaShift',model=model,shift_video=6.0 if recipe=='turbo' else 12.0,shift_audio=3.0)
    graph['noise']=node('RandomNoise',noise_seed=seed)
    graph['sampler']=node('KSamplerSelect',sampler_name=sampler)
    graph['schedule']=node('BasicScheduler',model=['shift',0],scheduler='simple',steps=steps,denoise=1.0)
    return graph


def sampling(graph,condition,latent):
    graph['guider']=node('BasicGuider',model=['shift',0],conditioning=condition)
    graph['sample']=node('SamplerCustomAdvanced',noise=['noise',0],guider=['guider',0],sampler=['sampler',0],sigmas=['schedule',0],latent_image=latent)
    graph['decode']=node('VAEDecode',samples=['sample',0],vae=['vae',0])


def load_media(graph,key,path,kind='image'):
    if kind=='image':
        graph[key]=node('LoadImage',image=str(path));return [key,0]
    if kind=='audio':
        graph[key]=node('LoadAudio',audio=str(path));return [key,0]
    graph[key]=node('LoadVideo',file=str(path))
    graph[key+'_components']=node('GetVideoComponents',video=[key,0])
    return [key+'_components',0]


def image_graph(prompt,seed,steps,prefix,width,height,source=None,references=None,mask=None):
    references=references or []
    if references and not source:raise ValueError('Reference editing requires source image')
    if len(references)>8:raise ValueError('At most eight additional references')
    graph=backbone(seed,steps,reference=bool(source),sampler='er_sde')
    if source:
        image=load_media(graph,'source',source)
        inputs=dict(clip=['clip',0],vae=['vae',0],source_image=image,edit_instruction=prompt,width=width,height=height,
                    quality_profile='recommended | 5 frames',source_fidelity=0.6,source_fit='crop_center',
                    reference_detail='match_generation_area',optimize_for_still=True,reference_transport='native')
        for i,path in enumerate(references,2):inputs['reference_image_'+str(i)]=load_media(graph,'reference_'+str(i),path)
        graph['prepare']=node('H3ReferenceEditPrepare',**inputs)
    else:
        graph['prepare']=node('H3TextToImagePrepare',clip=['clip',0],prompt=prompt,width=width,height=height,
                              quality_profile='recommended | 5 frames',optimize_for_still=True)
    sampling(graph,['prepare',0],['prepare',1])
    graph['pick']=node('ImageFromBatch',image=['decode',0],batch_index=0,length=1)
    result=['pick',0]
    if mask:
        if not source:raise ValueError('Mask edit requires source image')
        graph['mask']=node('LoadImageMask',image=str(mask),channel='red')
        graph['composite']=node('ImageCompositeMasked',destination=['source',0],source=result,mask=['mask',0],x=0,y=0,resize_source=False)
        result=['composite',0]
    graph['save']=node('SaveImage',images=result,filename_prefix=prefix)
    return graph


def video_graph(image,prompt,width,height,length,seed,prefix,steps,recipe='turbo',options=None):
    options=options or {}
    references=options.get('references',[])
    graph=backbone(seed,steps,recipe,bool(references))
    inputs=dict(clip=['clip',0],vae=['vae',0],prompt=prompt,width=width,height=height,length=length)
    if references:
        if len([r for r in references if r['kind']=='image'])>9:raise ValueError('At most nine image references')
        inputs['ref_image_size']='match'
        counts=dict(image=0,video=0,audio=0)
        for index,ref in enumerate(references):
            kind=ref['kind'];count=counts[kind];counts[kind]+=1
            if kind in ('video','audio') and count>=3:raise ValueError('At most three references per AV modality')
            link=load_media(graph,'ref_'+str(index),ref['path'],kind)
            group,stem={'image':('ref_images','ref_image_'),'video':('ref_videos','ref_video_'),'audio':('ref_audios','ref_audio_')}[kind]
            inputs[group+'.'+stem+str(count)]=link
            if kind=='video' and ref.get('include_audio'):
                graph['audio_vae']=node('VAELoader',vae_name=AUDIO_VAE);inputs['audio_vae']=['audio_vae',0]
                inputs['ref_video_audios.ref_video_audio_'+str(count)]=['ref_'+str(index)+'_components',1]
            if kind=='audio':
                graph['audio_vae']=node('VAELoader',vae_name=AUDIO_VAE);inputs['audio_vae']=['audio_vae',0]
        graph['prepare']=node('MiniMaxH3ReferenceToVideo',**inputs)
        if image or options.get('last_image'):raise ValueError('Use guides with REF2VA instead of first/last image')
    else:
        if image:inputs['first_frame']=load_media(graph,'first',image)
        if options.get('last_image'):inputs['last_frame']=load_media(graph,'last',options['last_image'])
        graph['prepare']=node('MiniMaxH3ImageToVideo',**inputs)
    conditioning=['prepare',0]
    for i,guide in enumerate(options.get('guides',[])):
        frame=guide['frame']
        if type(frame) is not int or not 0<=frame<length:raise ValueError('Guide frame outside shot')
        kwargs=dict(positive=conditioning,latent=['prepare',1],frame_idx=frame)
        if guide.get('image'):
            kwargs.update(image=load_media(graph,f'guide_image_{i}',guide['image']),vae=['vae',0])
        if guide.get('audio'):
            graph['audio_vae']=node('VAELoader',vae_name=AUDIO_VAE)
            kwargs.update(audio=load_media(graph,f'guide_audio_{i}',guide['audio'],'audio'),audio_vae=['audio_vae',0])
        if not guide.get('image') and not guide.get('audio'):raise ValueError('Empty guide')
        graph[f'guide_{i}']=node('MiniMaxH3AddGuide',**kwargs);conditioning=[f'guide_{i}',0]
    control=options.get('control')
    if control:
        # Caller supplies a precomputed pose/depth/edge video, not an unprocessed RGB reference.
        if not control.get('model_patch'):raise ValueError('Control requires model_patch filename')
        graph['patch']=node('ModelPatchLoader',name=control['model_patch'])
        graph['control']=node('MiniMaxH3FunControlNetApply',model=graph['shift']['inputs']['model'],model_patch=['patch',0],vae=['vae',0],strength=float(control.get('strength',1)),start_percent=0.0,end_percent=1.0,
                              control_video=load_media(graph,'control_frames',control['path'],'video'))
        graph['shift']['inputs']['model']=['control',0]
    sampling(graph,conditioning,['prepare',1])
    graph['video']=node('CreateVideo',images=['decode',0],fps=24.0)
    if options.get('audio'):
        graph['audio_vae']=node('VAELoader',vae_name=AUDIO_VAE)
        graph['decode_audio']=node('VAEDecodeAudio',samples=['sample',0],vae=['audio_vae',0])
        graph['video']['inputs']['audio']=['decode_audio',0]
        graph['save_audio']=node('SaveAudioAdvanced',audio=['decode_audio',0],filename_prefix=prefix+'_native',format='flac')
    graph['save']=node('SaveVideo',video=['video',0],filename_prefix=prefix,format='mp4')
    return graph


def dependencies(graph,models):
    categories={'unet_name':'diffusion_models','diffusion_model':'diffusion_models','clip_name':'text_encoders',
                'text_encoder':'text_encoders','vae_name':'vae','video_vae':'vae','lora_name':'loras'}
    result=[]
    for value in graph.values():
        for key,name in value['inputs'].items():
            category=categories.get(key)
            if value['class_type']=='ModelPatchLoader' and key=='name':category='model_patches'
            if category:
                path=Path(models)/category/name
                result.append(dict(path=str(path),exists=path.is_file()))
    return dict(nodes=sorted({n['class_type'] for n in graph.values()}),models=result,
                missing_models=[r['path'] for r in result if not r['exists']])
