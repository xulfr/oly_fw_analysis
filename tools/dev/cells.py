import json,re,sys
t=open(sys.argv[1]).read()
j=json.loads(re.search(r'^JSON (.*)$',t,re.M).group(1))
c=j['cells']
print(sys.argv[1], {904+i:hex(v) for i,v in enumerate(c) if v})
