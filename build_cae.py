"""Run inside Abaqus/CAE from the extracted job directory."""
import json
from pathlib import Path
from abaqus import mdb
from abaqusConstants import DEFORMABLE_BODY, ON, THREE_D

root=Path.cwd()


def member(model,name,origin,size):
    x,y,z=size
    sketch=model.ConstrainedSketch(name='profile',sheetSize=max(x,y)*2)
    sketch.rectangle(point1=(0.0,0.0),point2=(x,y))
    part=model.Part(name=name,dimensionality=THREE_D,type=DEFORMABLE_BODY)
    part.BaseSolidExtrude(sketch=sketch,depth=z)
    del model.sketches['profile']
    assembly=model.rootAssembly
    instance=assembly.Instance(name=name,part=part,dependent=ON)
    assembly.translate(instanceList=(instance.name,),vector=origin)


with (root/'model_parameters.json').open(encoding='utf-8') as handle:
    data=json.load(handle)
for item in data['models']:
    name=item['name']
    if name in mdb.models or (root/(name+'.cae')).exists():
        raise RuntimeError('Output already exists: '+name)
for item in data['models']:
    name,p=item['name'],item['parameters']
    m=mdb.Model(name=name)
    x,y,h,w,cx,cy,ch=(p[k] for k in ('lx','ly','beam_depth','beam_width','column_x','column_y','column_height'))
    member(m,'Column',( -cx/2,-cy/2,-ch),(cx,cy,ch+h))
    member(m,'Beam_X_minus',(-x,-w/2,0),(x-cx/2,w,h))
    member(m,'Beam_X_plus',(cx/2,-w/2,0),(x-cx/2,w,h))
    member(m,'Beam_Y_plus',(-w/2,cy/2,0),(w,y-cy/2,h))
    if p['layout']=='cross':
        member(m,'Beam_Y_minus',(-w/2,-y,0),(w,y-cy/2,h))
    m.rootAssembly.regenerate()
if 'Model-1' in mdb.models:
    del mdb.models['Model-1']
if (root/'white-models.cae').exists():
    raise RuntimeError('white-models.cae already exists')
mdb.saveAs(pathName=str(root/'white-models.cae'))
