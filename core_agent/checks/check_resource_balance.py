"""Historical 125 EU aggregate-only check; not current crew scheduling validation.
Use check_crew_schedule.py for current settings.
"""
from decimal import Decimal as D
crops=[('lettuce',30,D('585'),D('16')),('potato',90,D('8775'),D('16')),('tomato',90,D('1755'),D('22')),('wheat',90,D('13162.5'),D('10')),('soybean',90,D('12162.15'),D('12'))]
state={'food':D('120000'),'oxygen':D('8000'),'water':D('3000'),'power':D('6000')}
caps={'food':D('200000'),'oxygen':D('15000'),'water':D('4000'),'power':D('10000')}
mins=dict(state)
basefood=D('3054')/24*4
baseoxygen=D('.895')*1000/24*4
basewater=D('3.217')/24*4
plots=[{'crop':c,'age':0} for c in crops for _ in range(4)]
events=[]; harvests=0
for tick in range(1,721):
 for key,cost in [('food',basefood),('oxygen',baseoxygen),('water',basewater)]:
  assert state[key]>=cost,(tick,key,'base shortage')
  state[key]-=cost; mins[key]=min(mins[key],state[key])
 work=min(D(4),state['food']/100,state['oxygen']/25,(caps['power']-state['power'])/125)
 state['food']-=work*100; state['oxygen']-=work*25; state['power']+=work*125
 for key in state: mins[key]=min(mins[key],state[key])
 water=min(D(174)+basewater,D(250),state['power']/2,state['oxygen']/D('.2'),caps['water']-state['water'])
 assert water==D(174)+basewater,(tick,'water shortage')
 state['power']-=water*2; state['oxygen']-=water*D('.2'); state['water']+=water
 for plot in plots:
  assert state['water']>=D('8.7') and state['power']>=5,(tick,'plot shortage')
  state['water']-=D('8.7'); state['power']-=5
  state['oxygen']=min(caps['oxygen'],state['oxygen']+plot['crop'][3])
  plot['age']=min(plot['age']+1,plot['crop'][1])
  for key in state: mins[key]=min(mins[key],state[key])
 for plot in plots:
  if plot['age']==plot['crop'][1] and state['food']+plot['crop'][2]<=caps['food']:
   state['food']+=plot['crop'][2]; plot['age']=0; harvests+=1
 for key in state: assert 0<=state[key]<=caps[key]
 if tick in [30,90,180,720]: events.append({'tick':tick,**{k:round(float(v),4) for k,v in state.items()}})
print('Assumptions: timely 1:1 food/water transfers, no crew task occupancy; baseline irrigation; old work coefficient treated as EXTRA metabolism; harvest when capacity allows; replant same crop. This is a development check, not an Agent simulator.')
print('checkpoints:',events)
print('minimum at any checked substep:',{k:round(float(v),4) for k,v in mins.items()})
print('harvested plots:',harvests)
print('PASS: 720 ticks without aggregate shortage; individual starvation and task scheduling not tested.')
