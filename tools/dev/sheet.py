import sys
from PIL import Image
d=sys.argv[1]; out=sys.argv[2]; fs=sys.argv[3:]
ims=[Image.open(f'{d}/{f}.png').convert('RGB') for f in fs]
w,h=ims[0].size; n=len(ims); c=3 if n>4 else 2
o=Image.new('RGB',(w*c,h*((n+c-1)//c)))
for k,i in enumerate(ims): o.paste(i,((k%c)*w,(k//c)*h))
o=o.resize((o.width*2//3,o.height*2//3))
o.save(out)
